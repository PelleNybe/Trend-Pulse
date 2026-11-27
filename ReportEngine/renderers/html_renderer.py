"""
Chapter IR-based HTML/PDFRenderer to achieve consistent interaction and vision with the sample report.

New points:
1. Built-in Chart.js data validation/repair（ChartValidator+LLMCover) to prevent injection or crash caused by illegal configuration;
2. MathJax/Chart.js/html2canvas/jspdfDependencies are inlined with CDN backup to adapt to offline or blocked environments.;
3. Preset Base64 fonts of Siyuan Songti subset for PDF/HTML integrated export to avoid missing characters or additional system dependencies.。
"""

from __future__ import annotations

import copy
import html
from dataclasses import dataclass
import json
import os
import re
import base64
from pathlib import Path
from typing import Any, Dict, List
from loguru import logger

from ReportEngine.ir.schema import ENGINE_AGENT_TITLES
from ReportEngine.utils.chart_validator import (
    ChartValidator,
    ChartRepairer,
    ValidationResult,
    create_chart_validator,
    create_chart_repairer
)
from ReportEngine.utils.chart_repair_api import create_llm_repair_functions
from ReportEngine.utils.chart_review_service import get_chart_review_service



@dataclass
class ScriptConfig:
    inline_code: str
    cdn_url: str
    check_expression: str
    lib_name: str
    is_defer: bool = False

class HTMLRenderer:
    """
    Document IR → HTML Renderer.

    - Read IR metadata/chapters and map the structure to responsive HTML;
    - Dynamically construct directory、anchor point、Chart.jsScript and interaction logic;
    - Provide Theme variables、Auxiliary functions such as number mapping。
    """









    CALLOUT_ALLOWED_TYPES = {
        "paragraph",
        "list",
        "table",
        "blockquote",
        "code",
        "math",
        "figure",
        "kpiGrid",
        "swotTable",
        "pestTable",
        "engineQuote",
    }
    INLINE_ARTIFACT_KEYS = {
        "props",
        "widgetId",
        "widgetType",
        "data",
        "dataRef",
        "datasets",
        "labels",
        "config",
        "options",
    }
    TABLE_COMPLEX_CHARS = set(
        "@％%（）()，,。；;：:、？?！!·…-—_+<>[]{}|\\/\"'`~$^&*#"
    )
    _BOLD_RE = re.compile(r"\*\*(.*?)\*\*", re.DOTALL)

    def __init__(self, config: Dict[str, Any] | None = None):
        """
        Initializes the renderer cache and allows additional configuration to be injected.

        Parameter level description：
        - config: dict | None，For callers to temporarily overrideTheme/Debugging switches, etc., have the highest priority;
          Typical key value：
            - themeOverride: Override themeTokens in metadata;
            - enableDebug: bool, Whether to output additional Logs.
        internal state:
        - self.document/metadata/chapters: Save the IR of a rendering cycle;
        - self.widget_scripts：Collect chart configuration JSON, and then add water to the end of _render_body;
        - self._lib_cache/_pdf_font_base64: cache local libraries and fonts to avoid repeated IO;
        - self.chart_validator/chart_repairer: local and LLM repairer configured by Chart.js;
        - self.chart_validation_stats: Record the total amount/repair source/number of Failed to facilitate Logs auditing。
        """
        self.config = config or {}
        self.document: Dict[str, Any] = {}
        self.widget_scripts: List[str] = []
        self.chart_counter = 0
        self.toc_entries: List[Dict[str, Any]] = []
        self.heading_counter = 0
        self.metadata: Dict[str, Any] = {}
        self.chapters: List[Dict[str, Any]] = []
        self.chapter_anchor_map: Dict[str, str] = {}
        self.heading_label_map: Dict[str, Dict[str, Any]] = {}
        self.primary_heading_index = 0
        self.secondary_heading_index = 0
        self.toc_rendered = False
        self.hero_kpi_signature: tuple | None = None
        self._current_chapter: Dict[str, Any] | None = None
        self._lib_cache: Dict[str, str] = {}
        self._pdf_font_base64: str | None = None


        self.chart_validator = create_chart_validator()
        llm_repair_fns = create_llm_repair_functions()
        self.chart_repairer = create_chart_repairer(
            validator=self.chart_validator,
            llm_repair_fns=llm_repair_fns
        )

        self._llm_repair_count = len(llm_repair_fns)
        if not llm_repair_fns:
            logger.warning("HTMLRenderer: No LLM API is configured, chart API fix function is not available")
        else:
            logger.info(f"HTMLRenderer: configured {len(llm_repair_fns)} LLM repair function")

        self._chart_failure_notes: Dict[str, str] = {}
        self._chart_failure_recorded: set[str] = set()


        self.chart_validation_stats = {
            'total': 0,
            'valid': 0,
            'repaired_locally': 0,
            'repaired_api': 0,
            'failed': 0
        }

    @staticmethod
    def _get_lib_path() -> Path:
        """Get the directory path of the third-party library file"""
        return Path(__file__).parent / "libs"

    @staticmethod
    def _get_font_path() -> Path:
        """Returns the path to the font required for PDF export (using the optimized subset font）"""
        return Path(__file__).parent / "assets" / "fonts" / "SourceHanSerifSC-Medium-Subset.ttf"

    def _load_lib(self, filename: str) -> str:
        """
        Load the contents of the specified third-party library file

        parameters:
            filename: Library file name

        Return:
            str: JavaScript code content of the library file
        """
        if filename in self._lib_cache:
            return self._lib_cache[filename]

        lib_path = self._get_lib_path() / filename
        try:
            with open(lib_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self._lib_cache[filename] = content
                return content
        except FileNotFoundError:
            print(f"Warnings: library file {filename} Not found, CDN backup link will be used")
            return ""
        except Exception as e:
            print(f"Warnings: Read library file {filename} error: {e}")
            return ""

    def _load_pdf_font_data(self) -> str:
        """Load Base64 data of PDF fonts to avoid repeated reading of large files"""
        if self._pdf_font_base64 is not None:
            return self._pdf_font_base64
        font_path = self._get_font_path()
        try:
            data = font_path.read_bytes()
            self._pdf_font_base64 = base64.b64encode(data).decode("ascii")
            return self._pdf_font_base64
        except FileNotFoundError:
            logger.warning("PDFFont file missing：%s", font_path)
        except Exception as exc:
            logger.warning("Read PDF font filesFailed：%s (%s)", font_path, exc)
        self._pdf_font_base64 = ""
        return self._pdf_font_base64

    def _reset_chart_validation_stats(self) -> None:
        """Reset chart validation statistics and clear Failed count flag"""
        self.chart_validation_stats = {
            'total': 0,
            'valid': 0,
            'repaired_locally': 0,
            'repaired_api': 0,
            'failed': 0
        }

        self._chart_failure_recorded = set()

    def _build_script_with_fallback(
        self,
        config: ScriptConfig
    ) -> str:
        """
        Build script tags with CDN backup mechanism

        strategy：
        1. Prioritize embedding local library code
        2. Add a detection script to verify whether the library is successfully loaded.
        3. If Failed is detected, dynamically load the CDN version as a backup

        parameters:
            config: ScriptConfig object containing the configuration for the script tag

        Return:
            str: complete script tagHTML
        """
        defer_attr = ' defer' if config.is_defer else ''

        if config.inline_code:

            return f"""
  <script{defer_attr}>
    // {config.lib_name} - Embedded version
    try {{
      {config.inline_code}
    }} catch (e) {{
      console.error('{config.lib_name}Embedded loadingFailed:', e);
    }}
  </script>
  <script{defer_attr}>
    // {config.lib_name} - CDN FallbackDetection
    (function() {{
      var checkLib = function() {{
        if (!({config.check_expression})) {{
          console.warn('{config.lib_name}Local version loading failed, loading alternate version from CDN...');
          var script = document.createElement('script');
          script.src = '{config.cdn_url}';
          script.onerror = function() {{
            console.error('{config.lib_name} CDNThe backup load also failed.');
          }};
          script.onload = function() {{
            console.log('{config.lib_name} CDNAlternate version loadingSuccess');
          }};
          document.head.appendChild(script);
        }}
      }};

      // Delay detection to ensure embedded code has time to execute
      if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', function() {{
          setTimeout(checkLib, 100);
        }});
      }} else {{
        setTimeout(checkLib, 100);
      }}
    }})();
  </script>""".strip()
        else:

            logger.warning(f"{config.lib_name}The local file is not found or read Failed and will be used directly.CDN")
            return f'  <script{defer_attr} src="{config.cdn_url}"></script>'



    def render(
        self,
        document_ir: Dict[str, Any],
        ir_file_path: str | None = None
    ) -> str:
        """
        Receive Document IR, reset internal state and output full HTML.

        parameter:
            document_ir: Full report data generated by DocumentComposer。
            ir_file_path: Optional, IR file path, when provided it will be automatically saved after repair.

        return:
            str: Full HTML document written directly to disk。
        """
        self.document = document_ir or {}




        chart_service = get_chart_review_service()
        review_stats = chart_service.review_document(
            self.document,
            ir_file_path=ir_file_path,
            reset_stats=True,
            save_on_repair=bool(ir_file_path)
        )


        self.chart_validation_stats.update(review_stats.to_dict())

        self.widget_scripts = []
        self.chart_counter = 0
        self.heading_counter = 0
        self.metadata = self.document.get("metadata", {}) or {}
        raw_chapters = self.document.get("chapters", []) or []
        self.toc_rendered = False
        self.chapters = self._prepare_chapters(raw_chapters)
        self.chapter_anchor_map = {
            chapter.get("chapterId"): chapter.get("anchor")
            for chapter in self.chapters
            if chapter.get("chapterId") and chapter.get("anchor")
        }
        self.heading_label_map = self._compute_heading_labels(self.chapters)
        self.toc_entries = self._collect_toc_entries(self.chapters)

        metadata = self.metadata
        theme_tokens = metadata.get("themeTokens") or self.document.get("themeTokens", {})
        title = metadata.get("title") or metadata.get("query") or "Intelligent public opinion report"
        hero_kpis = (metadata.get("hero") or {}).get("kpis")
        self.hero_kpi_signature = self._kpi_signature_from_items(hero_kpis)

        head = self._render_head(title, theme_tokens)
        body = self._render_body()


        self._log_chart_validation_stats()

        return f"<!DOCTYPE html>\n<html lang=\"zh-CN\" class=\"no-js\">\n{head}\n{body}\n</html>"



    def _resolve_color_value(self, value: Any, backup: str) -> str:
        """Extract string value from color token"""
        if isinstance(value, str):
            value = value.strip()
            return value or backup
        if isinstance(value, dict):
            for key in ("main", "value", "color", "base", "default"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            for candidate in value.values():
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return backup

    def _resolve_color_family(self, value: Any, backup: Dict[str, str]) -> Dict[str, str]:
        """Parse the main/light/dark colors, and fall back to the default value if missing"""
        result = {
            "main": backup.get("main", "#007bff"),
            "light": backup.get("light", backup.get("main", "#007bff")),
            "dark": backup.get("dark", backup.get("main", "#007bff")),
        }
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                result["main"] = stripped
            return result
        if isinstance(value, dict):
            result["main"] = self._resolve_color_value(value.get("main") or value, result["main"])
            result["light"] = self._resolve_color_value(value.get("light") or value.get("lighter"), result["light"])
            result["dark"] = self._resolve_color_value(value.get("dark") or value.get("darker"), result["dark"])
        return result

    def _render_head(self, title: str, theme_tokens: Dict[str, Any]) -> str:
        """
        rendering<head>section, loads ThemeCSS and necessary script dependencies.

        parameter:
            title: The content of the page title tag.
            theme_tokens: Theme variable, used to inject CSS. Support level：
              - colors: {primary/secondary/bg/text/card/border/...}
              - typography: {fontFamily, fonts:{body,heading}}，body/heading Fall back to system font when empty
              - spacing: {container,gutter/pagePadding}

        Return:
            str: head fragmentHTML。
        """
        css = self._build_css(theme_tokens)


        chartjs = self._load_lib("chart.js")
        chartjs_sankey = self._load_lib("chartjs-chart-sankey.js")
        html2canvas = self._load_lib("html2canvas.min.js")
        jspdf = self._load_lib("jspdf.umd.min.js")
        mathjax = self._load_lib("mathjax.js")
        wordcloud2 = self._load_lib("wordcloud2.min.js")



        chartjs_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=chartjs,
            cdn_url="https://cdn.jsdelivr.net/npm/chart.js",
            check_expression="typeof Chart !== 'undefined'",
            lib_name="Chart.js"
        ))


        sankey_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=chartjs_sankey,
            cdn_url="https://cdn.jsdelivr.net/npm/chartjs-chart-sankey@4",
            check_expression="typeof Chart !== 'undefined' && Chart.controllers && Chart.controllers.sankey",
            lib_name="chartjs-chart-sankey"
        ))


        wordcloud_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=wordcloud2,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/wordcloud2.js/1.2.2/wordcloud2.min.js",
            check_expression="typeof WordCloud !== 'undefined'",
            lib_name="wordcloud2"
        ))


        html2canvas_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=html2canvas,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js",
            check_expression="typeof html2canvas !== 'undefined'",
            lib_name="html2canvas"
        ))


        jspdf_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=jspdf,
            cdn_url="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js",
            check_expression="typeof jspdf !== 'undefined'",
            lib_name="jsPDF"
        ))


        mathjax_tag = self._build_script_with_fallback(ScriptConfig(
            inline_code=mathjax,
            cdn_url="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
            check_expression="typeof MathJax !== 'undefined'",
            lib_name="MathJax",
            is_defer=True
        ))


        pdf_font_script = ""

        return f"""
<head>
  <meta charset="utf-8" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{self._escape_html(title)}</title>
  {chartjs_tag}
  {sankey_tag}
  {wordcloud_tag}
  {html2canvas_tag}
  {jspdf_tag}
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
        displayMath: [['$$','$$'], ['\\\\[','\\\\]']]
      }},
      options: {{
        skipHtmlTags: ['script','noscript','style','textarea','pre','code'],
        processEscapes: true
      }}
    }};
  </script>
  {mathjax_tag}
  {pdf_font_script}
  <style>
{css}
  </style>
  <script>
    document.documentElement.classList.remove('no-js');
    document.documentElement.classList.add('js-ready');
  </script>
</head>""".strip()

    def _render_body(self) -> str:
        """
        Assemble<body>Structure, including header、navigation、Chapters and scripts.
        New version: Remove the independent cover section and merge the titles into the hero section.

        return:
            str: bodyfragmentHTML。
        """
        header = self._render_header()

        hero = self._render_hero()
        toc_section = self._render_toc_section()
        chapters = "".join(self._render_chapter(chapter) for chapter in self.chapters)
        widget_scripts = "\n".join(self.widget_scripts)
        hydration = self._hydration_script()
        overlay = """
<div id="export-overlay" class="export-overlay no-print" aria-hidden="true">
  <div class="export-dialog" role="status" aria-live="assertive">
    <div class="export-spinner" aria-hidden="true"></div>
    <p class="export-status">Exporting PDF, please wait....</p>
    <div class="export-progress" role="progressbar" aria-valuetext="Exporting">
      <div class="export-progress-bar"></div>
    </div>
  </div>
</div>
""".strip()

        return f"""
<body>
{header}
{overlay}
<main>
{hero}
{toc_section}
{chapters}
</main>
{widget_scripts}
{hydration}
</body>""".strip()



    def _render_header(self) -> str:
        """
        Render the ceiling header, including the title、Subtitles and function buttons.

        button/Control description (ID is used to bind events in _hydration_script）：
        - <theme-button id="theme-toggle" value="light" size="1.5">：Customize Web Component，
          `value` initialTheme(light/dark)，`size` Control overall scaling; trigger `change` delivered on event detail: 'light'/'dark'。
        - <button id="print-btn">：after click window.print()，for export/printing。
        - <button id="export-btn">：Hidden PDF export button, bound when shown exportPdf()。
          Displayed only when the dependency is ready or the business layer is open for export.

        return:
            str: header HTML。
        """
        metadata = self.metadata
        title = metadata.get("title") or "Intelligent public opinion analysis report"
        subtitle = metadata.get("subtitle") or metadata.get("templateName") or "Automatically generated"
        return f"""
<header class="report-header no-print">
  <div>
    <h1>{self._escape_html(title)}</h1>
    <p class="subtitle">{self._escape_html(subtitle)}</p>
    {self._render_tagline()}
  </div>
  <div class="header-actions">
    <!-- Old version of day and night mode switch button (Web Component style）：
    <theme-button value="light" id="theme-toggle" size="1.5"></theme-button>
    -->
    <button id="theme-toggle-btn" class="action-btn theme-toggle-btn" type="button">
      <svg class="btn-icon sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      </svg>
      <svg class="btn-icon moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none;">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      </svg>
      <span class="theme-label">Switch mode</span>
    </button>
    <button id="print-btn" class="action-btn print-btn" type="button">
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 6 2 18 2 18 9"></polyline>
        <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
        <rect x="6" y="14" width="12" height="8"></rect>
      </svg>
      <span>Print page</span>
    </button>
    <button id="export-btn" class="action-btn" type="button" style="display: none;">⬇️ ExportPDF</button>
  </div>
</header>
""".strip()

    def _render_tagline(self) -> str:
        """
        Render the slogan below the title, or return an empty string if there is no slogan.

        return:
            str: tagline HTMLor empty string。
        """
        tagline = self.metadata.get("tagline")
        if not tagline:
            return ""
        return f'<p class="tagline">{self._escape_html(tagline)}</p>'

    def _render_cover(self) -> str:
        """
        In the cover area at the beginning of the article, the title and "Article Overview" prompt are displayed in the center.

        return:
            str: cover section HTML。
        """
        title = self.metadata.get("title") or "Intelligent public opinion report"
        subtitle = self.metadata.get("subtitle") or self.metadata.get("templateName") or ""
        overview_hint = "Article overview"
        return f"""
<section class="cover">
  <p class="cover-hint">{overview_hint}</p>
  <h1>{self._escape_html(title)}</h1>
  <p class="cover-subtitle">{self._escape_html(subtitle)}</p>
</section>
""".strip()

    def _render_hero(self) -> str:
        """
        Output the summary/KPI/Highlight area based on the hero field in the layout.
        New version: Merge title and overview together, remove elliptical background.

        return:
            str: hero area HTML, if there is no data, it is an empty string。
        """
        hero = self.metadata.get("hero") or {}
        if not hero:
            return ""


        title = self.metadata.get("title") or "Intelligent public opinion report"
        subtitle = self.metadata.get("subtitle") or self.metadata.get("templateName") or ""

        summary = hero.get("summary")
        summary_html = f'<p class="hero-summary">{self._escape_html(summary)}</p>' if summary else ""
        highlights = hero.get("highlights") or []
        highlight_html = "".join(
            f'<li><span class="badge">{self._escape_html(text)}</span></li>'
            for text in highlights
        )
        actions = hero.get("actions") or []
        actions_html = "".join(
            f'<button class="ghost-btn" type="button">{self._escape_html(text)}</button>'
            for text in actions
        )
        kpi_cards_list = []
        for item in hero.get("kpis", []):
            delta = item.get("delta")
            tone = item.get("tone") or "neutral"
            delta_html = f'<span class="delta {tone}">{self._escape_html(delta)}</span>' if delta else ""
            kpi_cards_list.append(f"""
            <div class="hero-kpi">
                <div class="label">{self._escape_html(item.get("label"))}</div>
                <div class="value">{self._escape_html(item.get("value"))}</div>
                {delta_html}
            </div>
            """)
        kpi_cards = "".join(kpi_cards_list)

        return f"""
<section class="hero-section-combined">
  <div class="hero-header">
    <p class="hero-hint">Article overview</p>
    <h1 class="hero-title">{self._escape_html(title)}</h1>
    <p class="hero-subtitle">{self._escape_html(subtitle)}</p>
  </div>
  <div class="hero-body">
    <div class="hero-content">
      {summary_html}
      <ul class="hero-highlights">{highlight_html}</ul>
      <div class="hero-actions">{actions_html}</div>
    </div>
    <div class="hero-side">
      {kpi_cards}
    </div>
  </div>
</section>
""".strip()

    def _render_meta_panel(self) -> str:
        """The current requirement is not to display meta-Info, and the method is reserved for subsequent expansion."""
        return ""

    def _render_toc_section(self) -> str:
        """
        Generate a directory module, and return an empty string if there is no directory data.

        return:
            str: toc HTMLstructure。
        """
        if not self.toc_entries:
            return ""
        if self.toc_rendered:
            return ""
        toc_config = self.metadata.get("toc") or {}
        toc_title = toc_config.get("title") or "📚 Table of contents"
        toc_items = "".join(
            self._format_toc_entry(entry)
            for entry in self.toc_entries
        )
        self.toc_rendered = True
        return f"""
<nav class="toc">
  <div class="toc-title">{self._escape_html(toc_title)}</div>
  <ul>
    {toc_items}
  </ul>
</nav>
""".strip()

    def _collect_toc_entries(self, chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Collect table of contents items based on tocPlan or chapter heading in metadata.

        parameter:
            chapters: Document IRArray of chapters in .

        return:
            list[dict]: Normalized directory entry, containinglevel/text/anchor/description。
        """
        metadata = self.metadata
        toc_config = metadata.get("toc") or {}
        custom_entries = toc_config.get("customEntries")
        entries: List[Dict[str, Any]] = []

        if custom_entries:
            for entry in custom_entries:
                anchor = entry.get("anchor") or self.chapter_anchor_map.get(entry.get("chapterId"))


                if not anchor:
                    logger.warning(
                        f"directory entry '{entry.get('display') or entry.get('title')}' "
                        f"Missing valid anchor, skipped"
                    )
                    continue


                anchor_valid = self._validate_toc_anchor(anchor, chapters)
                if not anchor_valid:
                    logger.warning(
                        f"directory entry '{entry.get('display') or entry.get('title')}' "
                        f"ofanchor '{anchor}' The corresponding chapter was not found in the document"
                    )


                description = entry.get("description")
                if description:
                    description = self._clean_text_from_json_artifacts(description)

                entries.append(
                    {
                        "level": entry.get("level", 2),
                        "text": entry.get("display") or entry.get("title") or "",
                        "anchor": anchor,
                        "description": description,
                    }
                )
            return entries

        for chapter in chapters or []:
            for block in chapter.get("blocks", []):
                if block.get("type") == "heading":
                    anchor = block.get("anchor") or chapter.get("anchor") or ""
                    if not anchor:
                        continue
                    mapped = self.heading_label_map.get(anchor, {})

                    description = mapped.get("description")
                    if description:
                        description = self._clean_text_from_json_artifacts(description)
                    entries.append(
                        {
                            "level": block.get("level", 2),
                            "text": mapped.get("display") or block.get("text", ""),
                            "anchor": anchor,
                            "description": description,
                        }
                    )
        return entries

    def _validate_toc_anchor(self, anchor: str, chapters: List[Dict[str, Any]]) -> bool:
        """
        Verify whether the table of contents anchor has a corresponding chapter or heading in the document.

        parameter:
            anchor: Anchor that needs to be verified
            chapters: array of chapters in Document IR

        Return:
            bool: whether anchor is valid
        """

        if anchor in self.chapter_anchor_map.values():
            return True


        if anchor in self.heading_label_map:
            return True


        for chapter in chapters or []:
            chapter_anchor = chapter.get("anchor")
            if chapter_anchor == anchor:
                return True

            for block in chapter.get("blocks", []):
                block_anchor = block.get("anchor")
                if block_anchor == anchor:
                    return True

        return False

    def _prepare_chapters(self, chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """CopyChapter and Expand the serialized block in it to avoid missing rendering"""
        prepared: List[Dict[str, Any]] = []
        for chapter in chapters or []:
            chapter_copy = copy.deepcopy(chapter)
            chapter_copy["blocks"] = self._expand_blocks_in_place(chapter_copy.get("blocks", []))
            prepared.append(chapter_copy)
        return prepared

    def _expand_blocks_in_place(self, blocks: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
        """Traverse the block list and disassemble the embedded JSON string into independentblock"""
        expanded: List[Dict[str, Any]] = []
        for block in blocks or []:
            extras = self._extract_embedded_blocks(block)
            expanded.append(block)
            if extras:
                expanded.extend(self._expand_blocks_in_place(extras))
        return expanded

    def _extract_embedded_blocks(self, block: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find the block list that is mistakenly written as a string inside the block and return the supplementaryblock
        """
        extracted: List[Dict[str, Any]] = []

        def traverse(node: Any) -> None:
            """Recursively traverse the block tree to identify potential nesting within text fieldsblock JSON"""
            if isinstance(node, dict):
                # ⚡ OPTIMIZATION: Removed unnecessary list() wrapper around node.items()
                # Modifying values (node[key] = "") is safe during view iteration in Python 3.
                # Bypasses O(N) memory copy and iteration overhead.
                for key, value in node.items():
                    if key == "text" and isinstance(value, str):
                        decoded = self._decode_embedded_block_payload(value)
                        if decoded:
                            node[key] = ""
                            extracted.extend(decoded)
                        continue
                    traverse(value)
            elif isinstance(node, list):
                for item in node:
                    traverse(item)

        traverse(block)
        return extracted


    def _decode_embedded_block_payload(self, raw: str) -> List[Dict[str, Any]] | None:
        """
        Restore the block description in string form to a structured list。
        """
        if not isinstance(raw, str):
            return None
        stripped = raw.strip()
        if not stripped or stripped[0] not in "{[":
            return None
        payload: Any | None = None
        decode_targets = [stripped]
        if stripped and stripped[0] != "[":
            decode_targets.append(f"[{stripped}]")
        for candidate in decode_targets:
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue

        if payload is None:
            return None

        blocks = self._collect_blocks_from_payload(payload)
        return blocks or None

    @staticmethod
    def _looks_like_block(payload: Dict[str, Any]) -> bool:
        """Roughly determine whether the dict conforms to the block structure"""
        if not isinstance(payload, dict):
            return False
        block_type = payload.get("type")
        if block_type and isinstance(block_type, str):

            inline_types = {"inlineRun", "inline", "text"}
            if block_type in inline_types:
                return False
            return True
        structural_keys = {"blocks", "rows", "items", "widgetId", "widgetType", "data"}
        return any(key in payload for key in structural_keys)

    def _collect_blocks_from_payload(self, payload: Any) -> List[Dict[str, Any]]:
        """Recursively collect block nodes in the payload"""
        collected: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            block_list = payload.get("blocks")
            block_type = payload.get("type")
            

            inline_types = {"inlineRun", "inline", "text"}
            if block_type in inline_types:
                return collected
            
            if isinstance(block_list, list) and not block_type:
                for candidate in block_list:
                    collected.extend(self._collect_blocks_from_payload(candidate))
                return collected
            if payload.get("cells") and not block_type:
                for cell in payload["cells"]:
                    if isinstance(cell, dict):
                        collected.extend(self._collect_blocks_from_payload(cell.get("blocks")))
                return collected
            if payload.get("items") and not block_type:
                for item in payload["items"]:
                    collected.extend(self._collect_blocks_from_payload(item))
                return collected
            appended = False
            if block_type or payload.get("widgetId") or payload.get("rows"):
                coerced = self._coerce_block_dict(payload)
                if coerced:
                    collected.append(coerced)
                    appended = True
            items = payload.get("items")
            if isinstance(items, list) and not block_type:
                for item in items:
                    collected.extend(self._collect_blocks_from_payload(item))
                return collected
            if appended:
                return collected
        elif isinstance(payload, list):
            for item in payload:
                collected.extend(self._collect_blocks_from_payload(item))
        elif payload is None:
            return collected
        return collected

    def _coerce_block_dict(self, payload: Any) -> Dict[str, Any] | None:
        """Try to supplement the dict into a legal block structure"""
        if not isinstance(payload, dict):
            return None
        block = copy.deepcopy(payload)
        block_type = block.get("type")
        if not block_type:
            if "widgetId" in block:
                block_type = block["type"] = "widget"
            elif "rows" in block or "cells" in block:
                block_type = block["type"] = "table"
                if "rows" not in block and isinstance(block.get("cells"), list):
                    block["rows"] = [{"cells": block.pop("cells")}]
            elif "items" in block:
                block_type = block["type"] = "list"
        return block if block.get("type") else None

    def _format_toc_entry(self, entry: Dict[str, Any]) -> str:
        """
        Convert a single directory entry into an HTML line with description.

        parameter:
            entry: Directory entry, needs to contain `text` and `anchor`。

        return:
            str: `<li>` formalHTML。
        """
        desc = entry.get("description")

        if desc:
            desc = self._clean_text_from_json_artifacts(desc)
        desc_html = f'<p class="toc-desc">{self._escape_html(desc)}</p>' if desc else ""
        level = entry.get("level", 2)
        css_level = 1 if level <= 2 else min(level, 4)
        return f'<li class="level-{css_level}"><a href="#{self._escape_attr(entry["anchor"])}">{self._escape_html(entry["text"])}</a>{desc_html}</li>'

    def _compute_heading_labels(self, chapters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        Precalculate the number of headings at each level (chapter: one、2; section: 1.1; subsection: 1.1.1).

        Parameters:
            chapters: Array of chapters in Document IR.

        Return:
            dict: Mapping of anchor points to numbers/descriptions to facilitate TOC and text citations。
        """
        label_map: Dict[str, Dict[str, Any]] = {}

        for chap_idx, chapter in enumerate(chapters or [], start=1):
            chapter_heading_seen = False
            section_idx = 0
            subsection_idx = 0
            deep_counters: Dict[int, int] = {}

            for block in chapter.get("blocks", []):
                if block.get("type") != "heading":
                    continue
                level = block.get("level", 2)
                anchor = block.get("anchor") or chapter.get("anchor")
                if not anchor:
                    continue

                raw_text = block.get("text", "")
                clean_title = self._strip_order_prefix(raw_text)
                label = None
                display_text = raw_text

                if not chapter_heading_seen:
                    label = f"{self._to_chinese_numeral(chap_idx)}、"
                    display_text = f"{label} {clean_title}".strip()
                    chapter_heading_seen = True
                    section_idx = 0
                    subsection_idx = 0
                    deep_counters.clear()
                elif level <= 2:
                    section_idx += 1
                    subsection_idx = 0
                    deep_counters.clear()
                    label = f"{chap_idx}.{section_idx}"
                    display_text = f"{label} {clean_title}".strip()
                else:
                    if section_idx == 0:
                        section_idx = 1
                    if level == 3:
                        subsection_idx += 1
                        deep_counters.clear()
                        label = f"{chap_idx}.{section_idx}.{subsection_idx}"
                    else:
                        deep_counters[level] = deep_counters.get(level, 0) + 1
                        parts = [str(chap_idx), str(section_idx or 1), str(subsection_idx or 1)]
                        for lvl in sorted(deep_counters.keys()):
                            parts.append(str(deep_counters[lvl]))
                        label = ".".join(parts)
                    display_text = f"{label} {clean_title}".strip()

                label_map[anchor] = {
                    "level": level,
                    "display": display_text,
                    "label": label,
                    "title": clean_title,
                }
        return label_map

    @staticmethod
    def _strip_order_prefix(text: str) -> str:
        """Remove words like "1.0" or "one、”prefix to get the pure title"""
        if not text:
            return ""
        separators = [" ", "、", ".", "．"]
        stripped = text.lstrip()
        for sep in separators:
            parts = stripped.split(sep, 1)
            if len(parts) == 2 and parts[0]:
                return parts[1].strip()
        return stripped.strip()

    @staticmethod
    def _to_chinese_numeral(number: int) -> str:
        """Map 1/2/3 to Chinese serial numbers (within ten）"""
        numerals = ["zero", "one", "two", "three", "Four", "five", "six", "seven", "eight", "Nine", "ten"]
        if number <= 10:
            return numerals[number]
        tens, ones = divmod(number, 10)
        if number < 20:
            return "ten" + (numerals[ones] if ones else "")
        parts = []
        if tens > 0:
            parts.append(numerals[tens] + "ten")
        if ones:
            parts.append(numerals[ones])
        return "".join(parts)



    def _render_chapter(self, chapter: Dict[str, Any]) -> str:
        """
        Wrap chapter blocks in<section>，Convenient for CSS control.

        Parameters:
            chapter: single chapter JSON.

        Return:
            str: section wrappedHTML。
        """
        section_id = self._escape_attr(chapter.get("anchor") or f"chapter-{chapter.get('chapterId', 'x')}")
        prev_chapter = self._current_chapter
        self._current_chapter = chapter
        try:
            blocks_html = self._render_blocks(chapter.get("blocks", []))
        finally:
            self._current_chapter = prev_chapter
        return f'<section id="{section_id}" class="chapter">\n{blocks_html}\n</section>'

    def _render_blocks(self, blocks: List[Dict[str, Any]]) -> str:
        """
        Render Allblocks within chapters sequentially.

        parameter:
            blocks: Block array inside the chapter.

        return:
            str: splicedHTML。
        """
        return "".join(self._render_block(block) for block in blocks or [])

    def _render_block(self, block: Dict[str, Any]) -> str:
        """
        Dispatched to different rendering functions according to block.type.

        parameter:
            block: a single block object.

        Return:
            str: Rendered HTML, unknown types will output JSON debuggingInfo。
        """
        block_type = block.get("type")
        handlers = {
            "heading": self._render_heading,
            "paragraph": self._render_paragraph,
            "list": self._render_list,
            "table": self._render_table,
            "swotTable": self._render_swot_table,
            "pestTable": self._render_pest_table,
            "blockquote": self._render_blockquote,
            "engineQuote": self._render_engine_quote,
            "hr": lambda b: "<hr />",
            "code": self._render_code,
            "math": self._render_math,
            "figure": self._render_figure,
            "callout": self._render_callout,
            "kpiGrid": self._render_kpi_grid,
            "widget": self._render_widget,
            "toc": lambda b: self._render_toc_section(),
        }
        handler = handlers.get(block_type)
        if handler:
            html_fragment = handler(block)
            return self._wrap_error_block(html_fragment, block)

        if isinstance(block, dict) and block.get("inlines"):
            html_fragment = self._render_paragraph({"inlines": block.get("inlines")})
            return self._wrap_error_block(html_fragment, block)

        if isinstance(block, str):
            html_fragment = self._render_paragraph({"inlines": [{"text": block}]})
            return self._wrap_error_block(html_fragment, {"meta": {}, "type": "paragraph"})
        if isinstance(block.get("blocks"), list):
            html_fragment = self._render_blocks(block["blocks"])
            return self._wrap_error_block(html_fragment, block)
        fallback = f'<pre class="unknown-block">{self._escape_html(json.dumps(block, ensure_ascii=False, indent=2))}</pre>'
        return self._wrap_error_block(fallback, block)

    def _wrap_error_block(self, html_fragment: str, block: Dict[str, Any]) -> str:
        """If the block is marked with error metadata, wrap the prompt container and inject ittooltip。"""
        if not html_fragment:
            return html_fragment
        meta = block.get("meta") or {}
        log_ref = meta.get("errorLogRef")
        if not isinstance(log_ref, dict):
            return html_fragment
        raw_preview = (meta.get("rawJsonPreview") or "")[:1200]
        error_message = meta.get("errorMessage") or "LLMReturn block parsingErrors"
        importance = meta.get("importance") or "standard"
        ref_label = ""
        if log_ref.get("relativeFile") and log_ref.get("entryId"):
            ref_label = f"{log_ref['relativeFile']}#{log_ref['entryId']}"
        tooltip = f"{error_message} | {ref_label}".strip()
        attr_raw = self._escape_attr(raw_preview or tooltip)
        attr_title = self._escape_attr(tooltip)
        class_suffix = self._escape_attr(importance)
        return (
            f'<div class="llm-error-block importance-{class_suffix}" '
            f'data-raw="{attr_raw}" title="{attr_title}">{html_fragment}</div>'
        )

    def _render_heading(self, block: Dict[str, Any]) -> str:
        """Render the heading block, ensuring the anchor point exists"""
        original_level = max(1, min(6, block.get("level", 2)))
        if original_level <= 2:
            level = 2
        elif original_level == 3:
            level = 3
        else:
            level = min(original_level, 6)
        anchor = block.get("anchor")
        if anchor:
            anchor_attr = self._escape_attr(anchor)
        else:
            self.heading_counter += 1
            anchor = f"heading-{self.heading_counter}"
            anchor_attr = self._escape_attr(anchor)
        mapping = self.heading_label_map.get(anchor, {})
        display_text = mapping.get("display") or block.get("text", "")
        subtitle = block.get("subtitle")
        subtitle_html = f'<small>{self._escape_html(subtitle)}</small>' if subtitle else ""
        return f'<h{level} id="{anchor_attr}">{self._escape_html(display_text)}{subtitle_html}</h{level}>'

    def _render_paragraph(self, block: Dict[str, Any]) -> str:
        """Render paragraphs and maintain the shuffled style internally through inline run"""
        inlines_data = block.get("inlines", [])
        

        if self._is_metadata_paragraph(inlines_data):
            return ""
        

        if len(inlines_data) == 1:
            standalone = self._render_standalone_math_inline(inlines_data[0])
            if standalone:
                return standalone

        inlines = "".join(self._render_inline(run) for run in inlines_data)
        return f"<p>{inlines}</p>"

    def _is_metadata_paragraph(self, inlines: List[Any]) -> bool:
        """
        Detects whether a paragraph contains only document metadata JSON.
        
        Some LLM-generated content will contain metadata such as xrefs、widgets、footnotes、metadata）
        Errorsoutput as paragraph content, this method recognizes and marks this case so that rendering can be skipped。
        """
        if not inlines or len(inlines) != 1:
            return False
        first = inlines[0]
        if not isinstance(first, dict):
            return False
        text = first.get("text", "")
        if not isinstance(text, str):
            return False
        text = text.strip()
        if not text.startswith("{") or not text.endswith("}"):
            return False

        metadata_indicators = ['"xrefs"', '"widgets"', '"footnotes"', '"metadata"', '"sectionBudgets"']
        return any(indicator in text for indicator in metadata_indicators)

    def _render_standalone_math_inline(self, run: Dict[str, Any] | str) -> str | None:
        """When a paragraph only contains a single display formula, convert it to math-block to avoid destroying the inline layout."""
        if isinstance(run, dict):
            text_value, marks = self._normalize_inline_payload(run)
            if marks:
                return None
            math_id_hint = run.get("mathIds") or run.get("mathId")
        else:
            text_value = "" if run is None else str(run)
            math_id_hint = None
            marks = []

        rendered = self._render_text_with_inline_math(
            text_value,
            math_id_hint,
            allow_display_block=True
        )
        if rendered and rendered.strip().startswith('<div class="math-block"'):
            return rendered
        return None

    def _render_list(self, block: Dict[str, Any]) -> str:
        """Rendering ordered/unordered/task lists"""
        list_type = block.get("listType", "bullet")
        tag = "ol" if list_type == "ordered" else "ul"
        extra_class = "task-list" if list_type == "task" else ""

        # ⚡ OPTIMIZATION: Avoid O(N^2) string concatenation by using list appending and join()
        items = []
        for item in block.get("items", []):
            content = self._render_blocks(item)
            if not content.strip():
                continue
            items.append(f"<li>{content}</li>")

        items_html = "".join(items)
        class_attr = f' class="{extra_class}"' if extra_class else ""
        return f'<{tag}{class_attr}>{items_html}</{tag}>'

    def _flatten_nested_cells(self, cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Flatten Errors nested cell structure.

        In some tabular data generated by LLM, cells are recursively nested Errors：
        cells[0] normal, cells[1].cells[0] normal, cells[1].cells[1].cells[0] normal...
        This method flattens this nested structure into a standard parallel cell array.

        parameter:
            cells: A cell array that may contain nested structures.

        return:
            List[Dict]: Flattened cell array。
        """
        if not cells:
            return []

        flattened: List[Dict[str, Any]] = []

        def _extract_cells(cell_or_list: Any) -> None:
            """Extract All cells recursively"""
            if not isinstance(cell_or_list, dict):
                return


            if "blocks" in cell_or_list:

                clean_cell = {
                    k: v for k, v in cell_or_list.items()
                    if k != "cells"
                }
                flattened.append(clean_cell)


            nested_cells = cell_or_list.get("cells")
            if isinstance(nested_cells, list):
                for nested_cell in nested_cells:
                    _extract_cells(nested_cell)

        for cell in cells:
            _extract_cells(cell)

        return flattened

    def _fix_nested_table_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fix table row structure for nested Errors.

        In some tabular data generated by LLM, the cells in all rows are nested in the first row.
        As a result, the table has only 1 row but contains All data. This method detects and fixes this situation.

        parameter:
            rows: The original array of table rows.

        return:
            List[Dict]: Repaired table row array。
        """
        if not rows:
            return []


        def _get_cell_text(cell: Dict[str, Any]) -> str:
            """Get the text content of a cell"""
            blocks = cell.get("blocks", [])
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    inlines = block.get("inlines", [])
                    for inline in inlines:
                        if isinstance(inline, dict):
                            text = inline.get("text", "")
                            if text:
                                return str(text).strip()
            return ""

        def _is_empty_or_dash_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether the cell is a blank value (such as '--', '-', '—' wait）"""
            text = _get_cell_text(cell)
            return text in ("--", "-", "—", "——", "", "N/A", "n/a")

        def _is_heading_like_cell(cell: Dict[str, Any]) -> bool:
            """Detect whether the chapter/title cells are suspected to be merged into the table by Errors"""
            text = _get_cell_text(cell)
            if not text:
                return False
            stripped = text.strip()

            heading_patterns = (
                r"^\d{1,2}(?:\.\d{1,2}){1,3}\s+",
                r"^No.[One, two, three, four, five, six, seven, eight, ninety]+[Chapter section]",
            )
            return any(re.match(pat, stripped) for pat in heading_patterns)


        header_cells = self._flatten_nested_cells((rows[0] or {}).get("cells", []))
        header_count = len(header_cells)
        overflow_fixed = None
        if header_count >= 2:
            rebuilt_rows: List[Dict[str, Any]] = [
                {
                    **{k: v for k, v in (rows[0] or {}).items() if k != "cells"},
                    "cells": header_cells,
                }
            ]
            changed = False
            for row in rows[1:]:
                cells = self._flatten_nested_cells((row or {}).get("cells", []))
                cell_count = len(cells)
                if cell_count <= header_count:
                    rebuilt_rows.append({**{k: v for k, v in (row or {}).items() if k != "cells"}, "cells": cells})
                    continue

                remainder = cell_count % header_count
                trimmed_cells = cells
                if remainder:
                    trailing = cells[-remainder:]
                    if all(_is_empty_or_dash_cell(c) or _is_heading_like_cell(c) for c in trailing):
                        trimmed_cells = cells[:-remainder]
                        remainder = 0

                if remainder == 0 and len(trimmed_cells) >= header_count * 2:
                    for i in range(0, len(trimmed_cells), header_count):
                        chunk = trimmed_cells[i : i + header_count]
                        rebuilt_rows.append({"cells": chunk})
                    changed = True
                else:
                    rebuilt_rows.append({**{k: v for k, v in (row or {}).items() if k != "cells"}, "cells": cells})

            if changed:
                overflow_fixed = rebuilt_rows

        if overflow_fixed is not None:
            rows = overflow_fixed

        if len(rows) != 1:

            return rows

        first_row = rows[0]
        original_cells = first_row.get("cells", [])


        has_nested = any(
            isinstance(cell.get("cells"), list)
            for cell in original_cells
            if isinstance(cell, dict)
        )

        if not has_nested:
            return rows


        all_cells = self._flatten_nested_cells(original_cells)

        if len(all_cells) <= 2:

            return rows


        all_cells = [c for c in all_cells if not _is_empty_or_dash_cell(c)]

        if len(all_cells) <= 2:
            return rows


        def _is_header_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether the cell looks like a table header (with a bold mark or a typical header word)）"""
            blocks = cell.get("blocks", [])
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "paragraph":
                    inlines = block.get("inlines", [])
                    for inline in inlines:
                        if isinstance(inline, dict):
                            marks = inline.get("marks", [])
                            if any(isinstance(m, dict) and m.get("type") == "bold" for m in marks):
                                return True

            text = _get_cell_text(cell)
            header_keywords = {
                "time", "date", "name", "type", "state", "quantity", "Amount", "Proportion", "index",
                "platform", "channel", "source", "describe", "illustrate", "Remark", "serial number", "serial number",
                "event", "key", "data", "support", "reaction", "market", "emotion", "node",
                "Dimensions", "Main points", "Details", "Label", "Influence", "trend", "weight", "category",
                "Info", "content", "style", "Preference", "main", "user", "core", "feature",
                "Classification", "scope", "object", "project", "stage", "cycle", "frequency", "grade",
            }
            return any(kw in text for kw in header_keywords) and len(text) <= 20


        header_count = 0
        for cell in all_cells:
            if _is_header_cell(cell):
                header_count += 1
            else:

                break


        if header_count == 0:

            total = len(all_cells)
            for possible_cols in [4, 5, 3, 6, 2]:
                if total % possible_cols == 0:
                    header_count = possible_cols
                    break
            else:

                for possible_cols in [4, 5, 3, 6, 2]:
                    remainder = total % possible_cols

                    if remainder <= 3:
                        header_count = possible_cols
                        break
                else:

                    return rows


        total = len(all_cells)
        remainder = total % header_count
        if remainder > 0 and remainder <= 3:

            all_cells = all_cells[:total - remainder]
        elif remainder > 3:

            return rows


        fixed_rows: List[Dict[str, Any]] = []
        for i in range(0, len(all_cells), header_count):
            row_cells = all_cells[i:i + header_count]

            if i == 0:
                for cell in row_cells:
                    cell["header"] = True
            fixed_rows.append({"cells": row_cells})

        return fixed_rows

    def _render_table(self, block: Dict[str, Any]) -> str:
        """
        Render the table while retaining the caption and cell attributes.

        parameter:
            block: tabletype of block.

        Return:
            str: contains<table>structuralHTML。
        """

        raw_rows = block.get("rows") or []
        fixed_rows = self._fix_nested_table_rows(raw_rows)
        rows = self._normalize_table_rows(fixed_rows)

        # ⚡ OPTIMIZATION: Avoid O(N^2) string concatenation by using list appending and join()
        rows_html_list = []
        for row in rows:
            row_cells_list = []

            cells = self._flatten_nested_cells(row.get("cells", []))
            for cell in cells:
                cell_tag = "th" if cell.get("header") or cell.get("isHeader") else "td"
                attr = []
                if cell.get("rowspan"):
                    attr.append(f'rowspan="{int(cell["rowspan"])}"')
                if cell.get("colspan"):
                    attr.append(f'colspan="{int(cell["colspan"])}"')
                if cell.get("align"):
                    attr.append(f'class="align-{cell["align"]}"')
                attr_str = (" " + " ".join(attr)) if attr else ""
                content = self._render_blocks(cell.get("blocks", []))
                row_cells_list.append(f"<{cell_tag}{attr_str}>{content}</{cell_tag}>")

            rows_html_list.append(f"<tr>{''.join(row_cells_list)}</tr>")

        rows_html = "".join(rows_html_list)
        caption = block.get("caption")
        caption_html = f"<caption>{self._escape_html(caption)}</caption>" if caption else ""
        return f'<div class="table-wrap"><table>{caption_html}<tbody>{rows_html}</tbody></table></div>'

    def _render_swot_table(self, block: Dict[str, Any]) -> str:
        """
        Render a four-quadrant SWOT analysis and generate two layouts at the same time:
        1. Card layout (for HTML web page display) - four quadrants of rounded rectangle
        2. Table layout (for PDF export) - Structured table, supports paging
        
        PDF paging strategy:
        - Use table format, each S/W/O/T quadrant is an independent table block
        - Allow paging between different quadrants
        - Keep items in each quadrant together as much as possible
        """
        title = block.get("title") or "SWOT analyze"
        summary = block.get("summary")
        

        card_html = self._render_swot_card_layout(block, title, summary)
        

        table_html = self._render_swot_pdf_table_layout(block, title, summary)
        

        return f"""
        <div class="swot-container">
          {card_html}
          {table_html}
        </div>
        """
    
    def _render_swot_card_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Render SWOT card layout (for HTML web page display）"""
        quadrants = [
            ("strengths", "Advantages Strengths", "S", "strength"),
            ("weaknesses", "Disadvantages Weaknesses", "W", "weakness"),
            ("opportunities", "Chance Opportunities", "O", "opportunity"),
            ("threats", "threaten Threats", "T", "threat"),
        ]
        cells_html_list = []
        for idx, (key, label, code, css) in enumerate(quadrants):
            items = self._normalize_swot_items(block.get(key))
            caption_text = f"{len(items)} key points" if items else "To be added"
            list_html = "".join(self._render_swot_item(item) for item in items) if items else '<li class="swot-empty">No key points have been filled in yet</li>'
            first_cell_class = " swot-cell--first" if idx == 0 else ""
            cells_html_list.append(f"""
        <div class="swot-cell swot-cell--pageable {css}{first_cell_class}" data-swot-key="{key}">
          <div class="swot-cell__meta">
            <span class="swot-pill {css}">{self._escape_html(code)}</span>
            <div>
              <div class="swot-cell__title">{self._escape_html(label)}</div>
              <div class="swot-cell__caption">{self._escape_html(caption_text)}</div>
            </div>
          </div>
          <ul class="swot-list">{list_html}</ul>
        </div>""")
        cells_html = "".join(cells_html_list)
        summary_html = f'<p class="swot-card__summary">{self._escape_html(summary)}</p>' if summary else ""
        title_html = f'<div class="swot-card__title">{self._escape_html(title)}</div>' if title else ""
        legend = """
            <div class="swot-legend">
              <span class="swot-legend__item strength">S Advantages</span>
              <span class="swot-legend__item weakness">W Disadvantages</span>
              <span class="swot-legend__item opportunity">O Chance</span>
              <span class="swot-legend__item threat">T threaten</span>
            </div>
        """
        return f"""
        <div class="swot-card swot-card--html">
          <div class="swot-card__head">
            <div>{title_html}{summary_html}</div>
            {legend}
          </div>
          <div class="swot-grid">{cells_html}</div>
        </div>
        """
    
    def _render_swot_pdf_table_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """
        Render SWOT table layout (for PDF export)
        
        design description：
        - The whole is a large table, including the title row and 4 quadrant areas.
        - Each quadrant area has its own subtitle row and content row
        - Use merged cells to display quadrant titles
        - Control paging behavior through CSS
        """
        quadrants = [
            ("strengths", "S", "Advantages Strengths", "swot-pdf-strength", "#1c7f6e"),
            ("weaknesses", "W", "Disadvantages Weaknesses", "swot-pdf-weakness", "#c0392b"),
            ("opportunities", "O", "Chance Opportunities", "swot-pdf-opportunity", "#1f5ab3"),
            ("threats", "T", "threaten Threats", "swot-pdf-threat", "#b36b16"),
        ]
        

        summary_row = ""
        if summary:
            summary_row = f"""
            <tr class="swot-pdf-summary-row">
              <td colspan="4" class="swot-pdf-summary">{self._escape_html(summary)}</td>
            </tr>"""
        

        quadrant_tables_list = []
        for idx, (key, code, label, css_class, color) in enumerate(quadrants):
            items = self._normalize_swot_items(block.get(key))
            

            items_rows_list = []
            if items:
                for item_idx, item in enumerate(items):
                    item_title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
                    item_detail = item.get("detail") or item.get("description") or ""
                    item_evidence = item.get("evidence") or item.get("source") or ""
                    item_impact = item.get("impact") or item.get("priority") or ""

                    

                    detail_parts = []
                    if item_detail:
                        detail_parts.append(item_detail)
                    if item_evidence:
                        detail_parts.append(f"evidence：{item_evidence}")
                    detail_text = "<br/>".join(detail_parts) if detail_parts else "-"
                    

                    tags = []
                    if item_impact:
                        tags.append(f'<span class="swot-pdf-tag">{self._escape_html(item_impact)}</span>')


                    tags_html = " ".join(tags)
                    

                    if item_idx == 0:
                        rowspan = len(items)
                        items_rows_list.append(f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td rowspan="{rowspan}" class="swot-pdf-quadrant-label {css_class}">
                <span class="swot-pdf-code">{code}</span>
                <span class="swot-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="swot-pdf-item-num">{item_idx + 1}</td>
              <td class="swot-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="swot-pdf-item-detail">{detail_text}</td>
              <td class="swot-pdf-item-tags">{tags_html}</td>
            </tr>""")
                    else:
                        items_rows_list.append(f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td class="swot-pdf-item-num">{item_idx + 1}</td>
              <td class="swot-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="swot-pdf-item-detail">{detail_text}</td>
              <td class="swot-pdf-item-tags">{tags_html}</td>
            </tr>""")
            else:

                items_rows_list = [f"""
            <tr class="swot-pdf-item-row {css_class}">
              <td class="swot-pdf-quadrant-label {css_class}">
                <span class="swot-pdf-code">{code}</span>
                <span class="swot-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="swot-pdf-item-num">-</td>
              <td colspan="3" class="swot-pdf-empty">No key points yet</td>
            </tr>"""]
            

            quadrant_tables_list.append(f"""
          <tbody class="swot-pdf-quadrant {css_class}">
            {"".join(items_rows_list)}
          </tbody>""")
        
        return f"""
        <div class="swot-pdf-wrapper">
          <table class="swot-pdf-table">
            <caption class="swot-pdf-caption">{self._escape_html(title)}</caption>
            <thead class="swot-pdf-thead">
              <tr>
                <th class="swot-pdf-th-quadrant">Quadrant</th>
                <th class="swot-pdf-th-num">serial number</th>
                <th class="swot-pdf-th-title">Main points</th>
                <th class="swot-pdf-th-detail">Detailed description</th>
                <th class="swot-pdf-th-tags">Influence</th>
              </tr>
              {summary_row}
            </thead>
            {"".join(quadrant_tables_list)}
          </table>
        </div>
        """

    def _normalize_swot_items(self, raw: Any) -> List[Dict[str, Any]]:
        """Organize SWOT entries into a unified structure, compatible with both string/object writing methods"""
        normalized: List[Dict[str, Any]] = []
        if raw is None:
            return normalized
        if isinstance(raw, (str, int, float)):
            text = self._safe_text(raw).strip()
            if text:
                normalized.append({"title": text})
            return normalized
        if not isinstance(raw, list):
            return normalized
        for entry in raw:
            if isinstance(entry, (str, int, float)):
                text = self._safe_text(entry).strip()
                if text:
                    normalized.append({"title": text})
                continue
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("label") or entry.get("text")
            detail = entry.get("detail") or entry.get("description")
            evidence = entry.get("evidence") or entry.get("source")
            impact = entry.get("impact") or entry.get("priority")

            if not title and isinstance(detail, str):
                title = detail
                detail = None
            if not (title or detail or evidence):
                continue
            normalized.append(
                {
                    "title": title,
                    "detail": detail,
                    "evidence": evidence,
                    "impact": impact,

                }
            )
        return normalized

    def _render_swot_item(self, item: Dict[str, Any]) -> str:
        """Output HTML snippet of a single SWOT entry"""
        title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
        detail = item.get("detail") or item.get("description")
        evidence = item.get("evidence") or item.get("source")
        impact = item.get("impact") or item.get("priority")

        tags: List[str] = []
        if impact:
            tags.append(f'<span class="swot-tag">{self._escape_html(impact)}</span>')


        tags_html = f'<span class="swot-item-tags">{"".join(tags)}</span>' if tags else ""
        detail_html = f'<div class="swot-item-desc">{self._escape_html(detail)}</div>' if detail else ""
        evidence_html = f'<div class="swot-item-evidence">evidence：{self._escape_html(evidence)}</div>' if evidence else ""
        return f"""
            <li class="swot-item">
              <div class="swot-item-title">{self._escape_html(title)}{tags_html}</div>
              {detail_html}{evidence_html}
            </li>
        """


    
    def _render_pest_table(self, block: Dict[str, Any]) -> str:
        """
        Render a four-dimensional PEST analysis and generate two layouts at the same time:
        1. Card layout (for HTML web page display) - horizontal strip stacking
        2. Table layout (for PDF export) - Structured table, supports paging
        
        PEST analysis dimensions:
        - P: Political (political factors)
        - E: Economic (economic factors)
        - S: Social (social factors)
        - T: Technological）
        """
        title = block.get("title") or "PEST analyze"
        summary = block.get("summary")
        

        card_html = self._render_pest_card_layout(block, title, summary)
        

        table_html = self._render_pest_pdf_table_layout(block, title, summary)
        

        return f"""
        <div class="pest-container">
          {card_html}
          {table_html}
        </div>
        """
    
    def _render_pest_card_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """Rendering PEST card layout (for HTML web page display) - horizontal strip stack design"""
        dimensions = [
            ("political", "political factors Political", "P", "political"),
            ("economic", "economic factors Economic", "E", "economic"),
            ("social", "social factors Social", "S", "social"),
            ("technological", "technical factors Technological", "T", "technological"),
        ]
        strips_html_list = []
        for idx, (key, label, code, css) in enumerate(dimensions):
            items = self._normalize_pest_items(block.get(key))
            caption_text = f"{len(items)} key points" if items else "To be added"
            list_html = "".join(self._render_pest_item(item) for item in items) if items else '<li class="pest-empty">No key points have been filled in yet</li>'
            first_strip_class = " pest-strip--first" if idx == 0 else ""
            strips_html_list.append(f"""
        <div class="pest-strip pest-strip--pageable {css}{first_strip_class}" data-pest-key="{key}">
          <div class="pest-strip__indicator {css}">
            <span class="pest-code">{self._escape_html(code)}</span>
          </div>
          <div class="pest-strip__content">
            <div class="pest-strip__header">
              <div class="pest-strip__title">{self._escape_html(label)}</div>
              <div class="pest-strip__caption">{self._escape_html(caption_text)}</div>
            </div>
            <ul class="pest-list">{list_html}</ul>
          </div>
        </div>""")
        strips_html = "".join(strips_html_list)
        summary_html = f'<p class="pest-card__summary">{self._escape_html(summary)}</p>' if summary else ""
        title_html = f'<div class="pest-card__title">{self._escape_html(title)}</div>' if title else ""
        legend = """
            <div class="pest-legend">
              <span class="pest-legend__item political">P politics</span>
              <span class="pest-legend__item economic">E economy</span>
              <span class="pest-legend__item social">S society</span>
              <span class="pest-legend__item technological">T technology</span>
            </div>
        """
        return f"""
        <div class="pest-card pest-card--html">
          <div class="pest-card__head">
            <div>{title_html}{summary_html}</div>
            {legend}
          </div>
          <div class="pest-strips">{strips_html}</div>
        </div>
        """
    
    def _render_pest_pdf_table_layout(self, block: Dict[str, Any], title: str, summary: str | None) -> str:
        """
        Render PEST table layout (for PDF export)
        
        design description：
        - The whole is a large table, including the title row and 4 dimension areas.
        - Each dimension has its own subtitle row and content row
        - Use merged cells to display dimension titles
        - Control paging behavior through CSS
        """
        dimensions = [
            ("political", "P", "political factors Political", "pest-pdf-political", "#8e44ad"),
            ("economic", "E", "economic factors Economic", "pest-pdf-economic", "#16a085"),
            ("social", "S", "social factors Social", "pest-pdf-social", "#e84393"),
            ("technological", "T", "technical factors Technological", "pest-pdf-technological", "#2980b9"),
        ]
        

        summary_row = ""
        if summary:
            summary_row = f"""
            <tr class="pest-pdf-summary-row">
              <td colspan="4" class="pest-pdf-summary">{self._escape_html(summary)}</td>
            </tr>"""
        

        dimension_tables_list = []
        for idx, (key, code, label, css_class, color) in enumerate(dimensions):
            items = self._normalize_pest_items(block.get(key))
            

            items_rows_list = []
            if items:
                for item_idx, item in enumerate(items):
                    item_title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
                    item_detail = item.get("detail") or item.get("description") or ""
                    item_source = item.get("source") or item.get("evidence") or ""
                    item_trend = item.get("trend") or item.get("impact") or ""
                    

                    detail_parts = []
                    if item_detail:
                        detail_parts.append(item_detail)
                    if item_source:
                        detail_parts.append(f"source：{item_source}")
                    detail_text = "<br/>".join(detail_parts) if detail_parts else "-"
                    

                    tags = []
                    if item_trend:
                        tags.append(f'<span class="pest-pdf-tag">{self._escape_html(item_trend)}</span>')
                    tags_html = " ".join(tags)
                    

                    if item_idx == 0:
                        rowspan = len(items)
                        items_rows_list.append(f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td rowspan="{rowspan}" class="pest-pdf-dimension-label {css_class}">
                <span class="pest-pdf-code">{code}</span>
                <span class="pest-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="pest-pdf-item-num">{item_idx + 1}</td>
              <td class="pest-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="pest-pdf-item-detail">{detail_text}</td>
              <td class="pest-pdf-item-tags">{tags_html}</td>
            </tr>""")
                    else:
                        items_rows_list.append(f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td class="pest-pdf-item-num">{item_idx + 1}</td>
              <td class="pest-pdf-item-title">{self._escape_html(item_title)}</td>
              <td class="pest-pdf-item-detail">{detail_text}</td>
              <td class="pest-pdf-item-tags">{tags_html}</td>
            </tr>""")
            else:

                items_rows_list = [f"""
            <tr class="pest-pdf-item-row {css_class}">
              <td class="pest-pdf-dimension-label {css_class}">
                <span class="pest-pdf-code">{code}</span>
                <span class="pest-pdf-label-text">{self._escape_html(label.split()[0])}</span>
              </td>
              <td class="pest-pdf-item-num">-</td>
              <td colspan="3" class="pest-pdf-empty">No key points yet</td>
            </tr>"""]
            

            dimension_tables_list.append(f"""
          <tbody class="pest-pdf-dimension {css_class}">
            {"".join(items_rows_list)}
          </tbody>""")
        
        return f"""
        <div class="pest-pdf-wrapper">
          <table class="pest-pdf-table">
            <caption class="pest-pdf-caption">{self._escape_html(title)}</caption>
            <thead class="pest-pdf-thead">
              <tr>
                <th class="pest-pdf-th-dimension">Dimensions</th>
                <th class="pest-pdf-th-num">serial number</th>
                <th class="pest-pdf-th-title">Main points</th>
                <th class="pest-pdf-th-detail">Detailed description</th>
                <th class="pest-pdf-th-tags">Trend/Impact</th>
              </tr>
              {summary_row}
            </thead>
            {"".join(dimension_tables_list)}
          </table>
        </div>
        """

    def _normalize_pest_items(self, raw: Any) -> List[Dict[str, Any]]:
        """Organize PEST entries into a unified structure, compatible with both string/object writing methods"""
        normalized: List[Dict[str, Any]] = []
        if raw is None:
            return normalized
        if isinstance(raw, (str, int, float)):
            text = self._safe_text(raw).strip()
            if text:
                normalized.append({"title": text})
            return normalized
        if not isinstance(raw, list):
            return normalized
        for entry in raw:
            if isinstance(entry, (str, int, float)):
                text = self._safe_text(entry).strip()
                if text:
                    normalized.append({"title": text})
                continue
            if not isinstance(entry, dict):
                continue
            title = entry.get("title") or entry.get("label") or entry.get("text")
            detail = entry.get("detail") or entry.get("description")
            source = entry.get("source") or entry.get("evidence")
            trend = entry.get("trend") or entry.get("impact")
            if not title and isinstance(detail, str):
                title = detail
                detail = None
            if not (title or detail or source):
                continue
            normalized.append(
                {
                    "title": title,
                    "detail": detail,
                    "source": source,
                    "trend": trend,
                }
            )
        return normalized

    def _render_pest_item(self, item: Dict[str, Any]) -> str:
        """输出单个PEST条目ofHTMLfragment"""
        title = item.get("title") or item.get("label") or item.get("text") or "unnamed points"
        detail = item.get("detail") or item.get("description")
        source = item.get("source") or item.get("evidence")
        trend = item.get("trend") or item.get("impact")
        tags: List[str] = []
        if trend:
            tags.append(f'<span class="pest-tag">{self._escape_html(trend)}</span>')
        tags_html = f'<span class="pest-item-tags">{"".join(tags)}</span>' if tags else ""
        detail_html = f'<div class="pest-item-desc">{self._escape_html(detail)}</div>' if detail else ""
        source_html = f'<div class="pest-item-source">source：{self._escape_html(source)}</div>' if source else ""
        return f"""
            <li class="pest-item">
              <div class="pest-item-title">{self._escape_html(title)}{tags_html}</div>
              {detail_html}{source_html}
            </li>
        """

    def _normalize_table_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect and correct vertical tables with only one column, converting them to standard grids.

        parameter:
            rows: Original table row.

        return:
            list[dict]: If a vertical table is detected, the transposed row is returned, otherwise it is returned as is.。
        """
        if not rows:
            return []
        if not all(len((row.get("cells") or [])) == 1 for row in rows):
            return rows
        texts = [self._extract_row_text(row) for row in rows]
        header_span = self._detect_transposed_header_span(rows, texts)
        if not header_span:
            return rows
        normalized = self._transpose_single_cell_table(rows, header_span)
        return normalized or rows

    def _detect_transposed_header_span(self, rows: List[Dict[str, Any]], texts: List[str]) -> int:
        """Infer the number of rows in the vertical table header for subsequent transposition"""
        max_fields = min(8, len(rows) // 2)
        header_span = 0
        for idx, text in enumerate(texts):
            if idx >= max_fields:
                break
            if self._is_potential_table_header(text):
                header_span += 1
            else:
                break
        if header_span < 2:
            return 0
        remainder = texts[header_span:]
        if not remainder or (len(rows) - header_span) % header_span != 0:
            return 0
        if not any(self._looks_like_table_value(txt) for txt in remainder):
            return 0
        return header_span

    def _is_potential_table_header(self, text: str) -> bool:
        """Determine whether it looks like a header field based on length and character characteristics"""
        if not text:
            return False
        stripped = text.strip()
        if not stripped or len(stripped) > 12:
            return False
        return not any(ch.isdigit() or ch in self.TABLE_COMPLEX_CHARS for ch in stripped)

    def _looks_like_table_value(self, text: str) -> bool:
        """Determine whether the text is more like a data value, used to assist in determining transposition"""
        if not text:
            return False
        stripped = text.strip()
        if len(stripped) >= 12:
            return True
        return any(ch.isdigit() or ch in self.TABLE_COMPLEX_CHARS for ch in stripped)

    def _transpose_single_cell_table(self, rows: List[Dict[str, Any]], span: int) -> List[Dict[str, Any]]:
        """Convert a single-column, multi-row table to a standard header + several rows of data"""
        total = len(rows)
        if total <= span or (total - span) % span != 0:
            return []
        header_rows = rows[:span]
        data_rows = rows[span:]
        normalized: List[Dict[str, Any]] = []
        header_cells = []
        for row in header_rows:
            cell = copy.deepcopy((row.get("cells") or [{}])[0])
            cell["header"] = True
            header_cells.append(cell)
        normalized.append({"cells": header_cells})
        for start in range(0, len(data_rows), span):
            group = data_rows[start : start + span]
            if len(group) < span:
                break
            normalized.append(
                {
                    "cells": [
                        copy.deepcopy((item.get("cells") or [{}])[0])
                        for item in group
                    ]
                }
            )
        return normalized

    def _extract_row_text(self, row: Dict[str, Any]) -> str:
        """Extract plain text from table rows to facilitate heuristic analysis"""
        cells = row.get("cells") or []
        if not cells:
            return ""
        cell = cells[0]
        texts: List[str] = []
        for block in cell.get("blocks", []):
            if isinstance(block, dict):
                if block.get("type") == "paragraph":
                    for inline in block.get("inlines") or []:
                        if isinstance(inline, dict):
                            value = inline.get("text")
                        else:
                            value = inline
                        if value is None:
                            continue
                        texts.append(str(value))
        return "".join(texts)

    def _render_blockquote(self, block: Dict[str, Any]) -> str:
        """Render reference block, can nest otherblock"""
        inner = self._render_blocks(block.get("blocks", []))
        return f"<blockquote>{inner}</blockquote>"

    def _render_engine_quote(self, block: Dict[str, Any]) -> str:
        """Render a single Engine speech block with independent color matching and title"""
        engine_raw = (block.get("engine") or "").lower()
        engine = engine_raw if engine_raw in ENGINE_AGENT_TITLES else "insight"
        expected_title = ENGINE_AGENT_TITLES.get(engine, ENGINE_AGENT_TITLES["insight"])
        title_raw = block.get("title") if isinstance(block.get("title"), str) else ""
        title = title_raw if title_raw == expected_title else expected_title
        inner = self._render_blocks(block.get("blocks", []))
        return (
            f'<div class="engine-quote engine-{self._escape_attr(engine)}">'
            f'  <div class="engine-quote__header">'
            f'    <span class="engine-quote__dot"></span>'
            f'    <span class="engine-quote__title">{self._escape_html(title)}</span>'
            f'  </div>'
            f'  <div class="engine-quote__body">{inner}</div>'
            f'</div>'
        )

    def _render_code(self, block: Dict[str, Any]) -> str:
        """Rendering code block, withLanguageInfo"""
        lang = block.get("lang") or ""
        content = self._escape_html(block.get("content", ""))
        return f'<pre class="code-block" data-lang="{self._escape_attr(lang)}"><code>{content}</code></pre>'

    def _render_math(self, block: Dict[str, Any]) -> str:
        """Render mathematical formulas, and pass omitted_error_indicators to external MathJax or post-processing"""
        latex_raw = block.get("latex", "")
        latex = self._escape_html(self._normalize_latex_string(latex_raw))
        math_id = self._escape_attr(block.get("mathId", "")) if block.get("mathId") else ""
        id_attr = f' data-math-id="{math_id}"' if math_id else ""
        return f'<div class="math-block"{id_attr}>$$ {latex} $$</div>'

    def _render_figure(self, block: Dict[str, Any]) -> str:
        """According to the new specification, external images are not rendered by default and are changed to friendly prompts."""
        caption = block.get("caption") or "Image content omitted (only HTML native charts and tables allowed）"
        return f'<div class="figure-omitted">{self._escape_html(caption)}</div>'

    def _render_callout(self, block: Dict[str, Any]) -> str:
        """
        Render a highlight prompt box, and tone determines the color.

        parameter:
            block: callouttype of block.

        Return:
            str: callout HTML, if it contains disallowed blocks, it will be split。
        """
        tone = block.get("tone", "info")
        title = block.get("title")
        safe_blocks, trailing_blocks = self._split_callout_content(block.get("blocks"))
        inner = self._render_blocks(safe_blocks)
        title_html = f"<strong>{self._escape_html(title)}</strong>" if title else ""
        callout_html = f'<div class="callout tone-{tone}">{title_html}{inner}</div>'
        trailing_html = self._render_blocks(trailing_blocks) if trailing_blocks else ""
        return callout_html + trailing_html

    def _split_callout_content(
        self, blocks: List[Dict[str, Any]] | None
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Limit the callout to contain only lightweight content, and strip the remaining blocks to the outer layer"""
        if not blocks:
            return [], []
        safe: List[Dict[str, Any]] = []
        trailing: List[Dict[str, Any]] = []
        for idx, child in enumerate(blocks):
            child_type = child.get("type")
            if child_type == "list":
                sanitized, overflow = self._sanitize_callout_list(child)
                if sanitized:
                    safe.append(sanitized)
                if overflow:
                    trailing.extend(overflow)
                    trailing.extend(copy.deepcopy(blocks[idx + 1 :]))
                    break
            elif child_type in self.CALLOUT_ALLOWED_TYPES:
                safe.append(child)
            else:
                trailing.extend(copy.deepcopy(blocks[idx:]))
                break
        else:
            return safe, []
        return safe, trailing

    def _sanitize_callout_list(
        self, block: Dict[str, Any]
    ) -> tuple[Dict[str, Any] | None, List[Dict[str, Any]]]:
        """When the list item contains a structural block, truncate it and remove it.callout"""
        items = block.get("items") or []
        if not items:
            return block, []
        sanitized_items: List[List[Dict[str, Any]]] = []
        trailing: List[Dict[str, Any]] = []
        for idx, item in enumerate(items):
            safe, overflow = self._split_callout_content(item)
            if safe:
                sanitized_items.append(safe)
            if overflow:
                trailing.extend(overflow)
                for rest in items[idx + 1 :]:
                    trailing.extend(copy.deepcopy(rest))
                break
        if not sanitized_items:
            return None, trailing
        new_block = copy.deepcopy(block)
        new_block["items"] = sanitized_items
        return new_block, trailing

    def _render_kpi_grid(self, block: Dict[str, Any]) -> str:
        """Render KPI card raster, including indicator values ​​and increases and decreases"""
        if self._should_skip_overview_kpi(block):
            return ""
        cards_list = []
        items = block.get("items", [])
        for item in items:
            delta = item.get("delta")
            delta_tone = item.get("deltaTone") or "neutral"
            delta_html = f'<span class="delta {delta_tone}">{self._escape_html(delta)}</span>' if delta else ""
            cards_list.append(f"""
            <div class="kpi-card">
              <div class="kpi-value">{self._escape_html(item.get("value", ""))}<small>{self._escape_html(item.get("unit", ""))}</small></div>
              <div class="kpi-label">{self._escape_html(item.get("label", ""))}</div>
              {delta_html}
            </div>
            """)
        cards = "".join(cards_list)
        count_attr = f' data-kpi-count="{len(items)}"' if items else ""
        return f'<div class="kpi-grid"{count_attr}>{cards}</div>'

    def _merge_dicts(
        self, base: Dict[str, Any] | None, override: Dict[str, Any] | None
    ) -> Dict[str, Any]:
        """
        Recursively merge two dictionaries, override covers base, and both are new copies to avoid side effects.。
        """
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        if not isinstance(override, dict):
            return result
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_dicts(result[key], value)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def _looks_like_chart_dataset(self, candidate: Any) -> bool:
        """Heuristically determines whether the object contains the common labels/datasets structure of Chart.js"""
        if not isinstance(candidate, dict):
            return False
        labels = candidate.get("labels")
        datasets = candidate.get("datasets")
        return isinstance(labels, list) or isinstance(datasets, list)

    def _coerce_chart_data_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compatible with the complete configuration of Chart.js output by LLM (including type/data/options).
        If there is a real labels/datasets structure nested in data, extract and return the structure。
        """
        if not isinstance(data, dict):
            return {}
        if self._looks_like_chart_dataset(data):
            return data
        for key in ("data", "chartData", "payload"):
            nested = data.get(key)
            if self._looks_like_chart_dataset(nested):
                return copy.deepcopy(nested)
        return data

    def _prepare_widget_payload(
        self, block: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Preprocess widget data, compatible with some blocksChart.jsConfigure the situation of writing data field.

        return:
            tuple(props, data): Normalized props and chart data
        """
        props = copy.deepcopy(block.get("props") or {})
        raw_data = block.get("data")
        data_copy = copy.deepcopy(raw_data) if isinstance(raw_data, dict) else raw_data
        widget_type = block.get("widgetType") or ""
        chart_like = isinstance(widget_type, str) and widget_type.startswith("chart.js")

        if chart_like and isinstance(data_copy, dict):
            inline_options = data_copy.pop("options", None)
            inline_type = data_copy.pop("type", None)
            normalized_data = self._coerce_chart_data_structure(data_copy)
            if isinstance(inline_options, dict):
                props["options"] = self._merge_dicts(props.get("options"), inline_options)
            if isinstance(inline_type, str) and inline_type and not props.get("type"):
                props["type"] = inline_type
        elif isinstance(data_copy, dict):
            normalized_data = data_copy
        else:
            normalized_data = {}

        return props, normalized_data

    @staticmethod
    def _is_chart_data_empty(data: Dict[str, Any] | None) -> bool:
        """Check if chart data is empty or missing validdatasets"""
        if not isinstance(data, dict):
            return True

        datasets = data.get("datasets")
        if not isinstance(datasets, list) or len(datasets) == 0:
            return True

        for ds in datasets:
            if not isinstance(ds, dict):
                continue
            series = ds.get("data")
            if isinstance(series, list) and len(series) > 0:
                return False

        return True

    def _chart_cache_key(self, block: Dict[str, Any]) -> str:
        """Use the repairer's caching algorithm to generate stable keys to facilitate sharing results across stages"""
        if hasattr(self, "chart_repairer") and block:
            try:
                return self.chart_repairer.build_cache_key(block)
            except Exception:
                pass
        return str(id(block))

    def _note_chart_failure(self, cache_key: str, reason: str) -> None:
        """Record the reason for repairing Failed, and use omitted_error_indicator prompts directly for subsequent renderings."""
        if not cache_key:
            return
        if not reason:
            reason = "LLMThe format of the returned chart Info is incorrect and cannot be displayed normally."
        self._chart_failure_notes[cache_key] = reason

    def _record_chart_failure_stat(self, cache_key: str | None = None) -> None:
        """Ensure that the Failed count is only counted once"""
        if cache_key and cache_key in self._chart_failure_recorded:
            return
        self.chart_validation_stats['failed'] += 1
        if cache_key:
            self._chart_failure_recorded.add(cache_key)

    def _apply_cached_review_stats(self, block: Dict[str, Any]) -> None:
        """
        Re-accumulate statistical information on the reviewed charts to avoid repeated repairs.

        When the rendering process resets statistics but the chart has already been reviewed（_chart_reviewed=True），
        Accumulate various counts directly based on the recorded status to prevent triggering again ChartRepairer。
        """
        if not isinstance(block, dict):
            return

        status = block.get("_chart_review_status") or "valid"
        method = (block.get("_chart_review_method") or "none").lower()
        cache_key = self._chart_cache_key(block)

        self.chart_validation_stats['total'] += 1
        if status == "failed":
            self._record_chart_failure_stat(cache_key)
        elif status == "repaired":
            if method == "api":
                self.chart_validation_stats['repaired_api'] += 1
            else:
                self.chart_validation_stats['repaired_locally'] += 1
        else:
            self.chart_validation_stats['valid'] += 1

    def _format_chart_error_reason(
        self,
        validation_result: ValidationResult | None = None,
        degrade_reason: str | None = None
    ) -> str:
        """Splicing-friendly Failed prompt"""
        base = "LLMThe returned chart Info format is incorrect. We have tried local and multi-model repairs but still cannot display properly.。"
        detail = None
        if validation_result:
            if validation_result.errors:
                detail = validation_result.errors[0]
            elif validation_result.warnings:
                detail = validation_result.warnings[0]
        if not detail and degrade_reason:
            detail = degrade_reason
        if detail:
            text = f"{base} hint：{detail}"
            return text[:180] + ("..." if len(text) > 180 else "")
        return base

    def _render_chart_error_omitted_error_indicator(
        self,
        title: str | None,
        reason: str,
        widget_id: str | None = None
    ) -> str:
        """Concise omitted_error_indicator prompt when outputting chart Failed to avoid damageHTML/PDFlayout"""
        safe_title = self._escape_html(title or "Chart failed to display")
        safe_reason = self._escape_html(reason)
        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        return f"""
        <div class="chart-card chart-card--error"{widget_attr}>
          <div class="chart-error">
            <div class="chart-error__icon">!</div>
            <div class="chart-error__body">
              <div class="chart-error__title">{safe_title}</div>
              <p class="chart-error__desc">{safe_reason}</p>
            </div>
          </div>
        </div>
        """

    def _has_chart_failure(self, block: Dict[str, Any]) -> tuple[bool, str | None]:
        """Check whether there is a repair Failed record"""
        cache_key = self._chart_cache_key(block)
        if block.get("_chart_renderable") is False:
            return True, block.get("_chart_error_reason")
        if cache_key in self._chart_failure_notes:
            return True, self._chart_failure_notes.get(cache_key)
        return False, None

    def _normalize_chart_block(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None = None,
    ) -> None:
        """
        Complete the missing fields in the chart block (such asscales、datasets），Improve fault tolerance。

        - Merge Errors into the scales hanging at the top level of the blockprops.options。
        - When data is missing or datasets are empty, try to use chapter-level data as a backup。
        """

        if not isinstance(block, dict):
            return

        if block.get("type") != "widget":
            return

        widget_type = block.get("widgetType", "")
        if not (isinstance(widget_type, str) and widget_type.startswith("chart.js")):
            return


        props = block.get("props")
        if not isinstance(props, dict):
            block["props"] = {}
            props = block["props"]


        scales = block.get("scales")
        if isinstance(scales, dict):
            options = props.get("options") if isinstance(props.get("options"), dict) else {}
            props["options"] = self._merge_dicts(options, {"scales": scales})


        data = block.get("data")
        if not isinstance(data, dict):
            data = {}
            block["data"] = data


        if chapter_context and self._is_chart_data_empty(data):
            chapter_data = chapter_context.get("data") if isinstance(chapter_context, dict) else None
            if isinstance(chapter_data, dict):
                parent_ds = chapter_data.get("datasets")
                if isinstance(parent_ds, list) and len(parent_ds) > 0:
                    merged_data = copy.deepcopy(data)
                    merged_data["datasets"] = copy.deepcopy(parent_ds)

                    if not merged_data.get("labels") and isinstance(chapter_data.get("labels"), list):
                        merged_data["labels"] = copy.deepcopy(chapter_data["labels"])

                    block["data"] = merged_data


        data_ref = block.get("data")
        if isinstance(data_ref, dict) and not data_ref.get("labels"):
            datasets_ref = data_ref.get("datasets")
            if isinstance(datasets_ref, list) and datasets_ref:
                first_ds = datasets_ref[0]
                ds_data = first_ds.get("data") if isinstance(first_ds, dict) else None
                if isinstance(ds_data, list):
                    labels_from_data = []
                    for idx, point in enumerate(ds_data):
                        if isinstance(point, dict):
                            label_text = point.get("x") or point.get("label") or f"point{idx + 1}"
                        else:
                            label_text = f"point{idx + 1}"
                        labels_from_data.append(str(label_text))

                    if labels_from_data:
                        data_ref["labels"] = labels_from_data

    def _ensure_chart_reviewed(
        self,
        block: Dict[str, Any],
        chapter_context: Dict[str, Any] | None = None,
        *,
        increment_stats: bool = True
    ) -> tuple[bool, str | None]:
        """
        Make sure the chart is Completed for review/Repair and write the results back to the original block.

        return:
            (renderable, fail_reason)
        """
        if not isinstance(block, dict):
            return True, None

        widget_type = block.get('widgetType', '')
        is_chart = isinstance(widget_type, str) and widget_type.startswith('chart.js')
        if not is_chart:
            return True, None

        is_wordcloud = 'wordcloud' in widget_type.lower() if isinstance(widget_type, str) else False
        cache_key = self._chart_cache_key(block)


        if block.get("_chart_renderable") is False:
            if increment_stats:
                self.chart_validation_stats['total'] += 1
                self._record_chart_failure_stat(cache_key)
            reason = block.get("_chart_error_reason")
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = block.get("_chart_review_status") or "failed"
            block["_chart_review_method"] = block.get("_chart_review_method") or "none"
            if reason:
                self._note_chart_failure(cache_key, reason)
            return False, reason

        if block.get("_chart_reviewed"):
            if increment_stats:
                self._apply_cached_review_stats(block)
            failed, cached_reason = self._has_chart_failure(block)
            renderable = not failed and block.get("_chart_renderable", True) is not False
            return renderable, block.get("_chart_error_reason") or cached_reason


        self._normalize_chart_block(block, chapter_context)

        if increment_stats:
            self.chart_validation_stats['total'] += 1

        if is_wordcloud:
            if increment_stats:
                self.chart_validation_stats['valid'] += 1
            block["_chart_reviewed"] = True
            block["_chart_review_status"] = "valid"
            block["_chart_review_method"] = "none"
            return True, None

        validation_result = self.chart_validator.validate(block)

        if not validation_result.is_valid:
            logger.warning(
                f"chart {block.get('widgetId', 'unknown')} verifyFailed: {validation_result.errors}"
            )

            repair_result = self.chart_repairer.repair(block, validation_result)

            if repair_result.success and repair_result.repaired_block:

                repaired_block = repair_result.repaired_block
                block.clear()
                block.update(repaired_block)
                method = repair_result.method or "local"
                logger.info(
                    f"chart {block.get('widgetId', 'unknown')} repairSuccess "
                    f"(method: {method}): {repair_result.changes}"
                )

                if increment_stats:
                    if method == 'local':
                        self.chart_validation_stats['repaired_locally'] += 1
                    elif method == 'api':
                        self.chart_validation_stats['repaired_api'] += 1
                block["_chart_review_status"] = "repaired"
                block["_chart_review_method"] = method
                block["_chart_reviewed"] = True
                return True, None


            fail_reason = self._format_chart_error_reason(validation_result)
            block["_chart_renderable"] = False
            block["_chart_error_reason"] = fail_reason
            block["_chart_review_status"] = "failed"
            block["_chart_review_method"] = "none"
            block["_chart_reviewed"] = True
            self._note_chart_failure(cache_key, fail_reason)
            if increment_stats:
                self._record_chart_failure_stat(cache_key)
            logger.warning(
                f"chart {block.get('widgetId', 'unknown')} Fix Failed, rendering skipped: {fail_reason}"
            )
            return False, fail_reason


        if increment_stats:
            self.chart_validation_stats['valid'] += 1
            if validation_result.warnings:
                logger.info(
                    f"chart {block.get('widgetId', 'unknown')} Verification passed，"
                    f"But there isWarnings: {validation_result.warnings}"
                )
        block["_chart_review_status"] = "valid"
        block["_chart_review_method"] = "none"
        block["_chart_reviewed"] = True
        return True, None

    def review_and_patch_document(
        self,
        document_ir: Dict[str, Any],
        *,
        reset_stats: bool = True,
        clone: bool = False
    ) -> Dict[str, Any]:
        """
        Review and repair graphs globally, writing repair results back to the original IR to avoid repeating repairs on multiple renders.

        parameter:
            document_ir: Original Document IR
            reset_stats: whether to reset statistics
            clone: Whether to return a repaired deep copy (the original IR will still be written back with the repair result)

        Return:
            Repaired IR (may be the original object or its deep copy）
        """
        if reset_stats:
            self._reset_chart_validation_stats()

        target_ir = document_ir or {}

        def _walk_blocks(blocks: list, chapter_ctx: Dict[str, Any] | None = None) -> None:
            for blk in blocks or []:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "widget":
                    self._ensure_chart_reviewed(blk, chapter_ctx, increment_stats=True)

                nested_blocks = blk.get("blocks")
                if isinstance(nested_blocks, list):
                    _walk_blocks(nested_blocks, chapter_ctx)

                if blk.get("type") == "list":
                    for item in blk.get("items", []):
                        if isinstance(item, list):
                            _walk_blocks(item, chapter_ctx)

                if blk.get("type") == "table":
                    for row in blk.get("rows", []):
                        cells = row.get("cells", [])
                        for cell in cells:
                            if isinstance(cell, dict):
                                cell_blocks = cell.get("blocks", [])
                                if isinstance(cell_blocks, list):
                                    _walk_blocks(cell_blocks, chapter_ctx)

        for chapter in target_ir.get("chapters", []) or []:
            if not isinstance(chapter, dict):
                continue
            _walk_blocks(chapter.get("blocks", []), chapter)

        return copy.deepcopy(target_ir) if clone else target_ir

    def _render_widget(self, block: Dict[str, Any]) -> str:
        """
        Render Chart.jsContainer containers for interactive components and record configuration JSON.

        Chart validation and repair before rendering:
        1. validate: ChartValidator checks the data/props/options structure of the block;
        2. repair: If Failed, first repair it locally (cover when labels/datasets/scale is missing), and then call the LLM API;
        3. Failed: write _chart_renderable=False and _chart_error_reason, which outputs Errors omitted_error_indicators instead of throwing exceptions.

        Parameters (corresponding to IR level）：
        - block.widgetType: "chart.js/bar"/"chart.js/line"/"wordcloud" etc., decide the renderer and verification strategy;
        - block.widgetId: unique ID of the component, used for canvas/data script binding;
        - block.props: transparently transmitted to front-end Chart.js options, for example props.title / props.options.legend；
        - block.data: {labels, datasets} Wait for data; if it is missing, it will try to fill it in from chapter-level chapter.data;
        - block.dataRef: External data references are temporarily used as transparent transmission records.

        return:
            str: Contains canvas and configuration scriptHTML。
        """

        widget_type = block.get('widgetType', '')
        is_chart = isinstance(widget_type, str) and widget_type.startswith('chart.js')
        is_wordcloud = isinstance(widget_type, str) and 'wordcloud' in widget_type.lower()
        reviewed = bool(block.get("_chart_reviewed"))
        renderable = True
        fail_reason = None

        if is_chart:
            renderable, fail_reason = self._ensure_chart_reviewed(
                block,
                getattr(self, "_current_chapter", None),
                increment_stats=not reviewed
            )

        widget_id = block.get('widgetId')
        props_snapshot = block.get("props") if isinstance(block.get("props"), dict) else {}
        display_title = props_snapshot.get("title") or block.get("title") or widget_id or "chart"

        if is_chart and not renderable:
            reason = fail_reason or "LLMThe format of the returned chart Info is incorrect and cannot be displayed normally."
            return self._render_chart_error_omitted_error_indicator(display_title, reason, widget_id)


        self.chart_counter += 1
        canvas_id = f"chart-{self.chart_counter}"
        config_id = f"chart-config-{self.chart_counter}"

        props, normalized_data = self._prepare_widget_payload(block)
        payload = {
            "widgetId": block.get("widgetId"),
            "widgetType": block.get("widgetType"),
            "props": props,
            "data": normalized_data,
            "dataRef": block.get("dataRef"),
        }
        config_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        self.widget_scripts.append(
            f'<script type="application/json" id="{config_id}">{config_json}</script>'
        )

        title = props.get("title")
        title_html = f'<div class="chart-title">{self._escape_html(title)}</div>' if title else ""
        degrade_html = (
            self._render_wordcloud_degraded(props, block.get("widgetId"), block.get("data"))
            if is_wordcloud
            else self._render_widget_degraded(normalized_data, block.get("widgetId"))
        )
        return f"""
        <div class="chart-card{' wordcloud-card' if is_wordcloud else ''}">
          {title_html}
          <div class="chart-container">
            <canvas id="{canvas_id}" data-config-id="{config_id}"></canvas>
          </div>
          {degrade_html}
        </div>
        """

    def _render_widget_degraded(self, data: Dict[str, Any], widget_id: str | None = None) -> str:
        """Render the text bottom view of chart data to avoid blanks when Chart.js loads Failed"""
        if not isinstance(data, dict):
            return ""
        labels = data.get("labels") or []
        datasets = data.get("datasets") or []
        if not labels or not datasets:
            return ""

        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        header_cells = "".join(
            f"<th>{self._escape_html(ds.get('label') or f'series{idx + 1}')}</th>"
            for idx, ds in enumerate(datasets)
        )
        body_rows_list = []
        for idx, label in enumerate(labels):
            row_cells = [f"<td>{self._escape_html(label)}</td>"]
            for ds in datasets:
                series = ds.get("data") or []
                value = series[idx] if idx < len(series) else ""
                row_cells.append(f"<td>{self._escape_html(value)}</td>")
            body_rows_list.append(f"<tr>{''.join(row_cells)}</tr>")
        body_rows = "".join(body_rows_list)
        table_html = f"""
        <div class="chart-degraded" data-prebuilt="true"{widget_attr}>
          <table>
            <thead>
              <tr><th>category</th>{header_cells}</tr>
            </thead>
            <tbody>
              {body_rows}
            </tbody>
          </table>
        </div>
        """
        return table_html

    def _render_wordcloud_degraded(
        self,
        props: Dict[str, Any] | None,
        widget_id: str | None = None,
        block_data: Any | None = None,
    ) -> str:
        """Provide table backends for word clouds to avoid page blanks after WordCloud renders Failed"""
        def _collect_items(raw: Any) -> list[dict]:
            """Organize multiple word cloud input formats (array/object/tuple/plain text) into a unified list of terms"""
            collected: list[dict] = []
            skip_keys = {"items", "data", "words", "labels", "datasets", "sourceData"}
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        text = item.get("word") or item.get("text") or item.get("label")
                        weight = item.get("weight")
                        category = item.get("category") or ""
                        if text:
                            collected.append({"word": str(text), "weight": weight, "category": str(category)})

                        for nested_key in ("items", "words", "data"):
                            nested = item.get(nested_key)
                            if isinstance(nested, list):
                                collected.extend(_collect_items(nested))
                    elif isinstance(item, (list, tuple)) and item:
                        text = item[0]
                        weight = item[1] if len(item) > 1 else None
                        category = item[2] if len(item) > 2 else ""
                        if text:
                            collected.append({"word": str(text), "weight": weight, "category": str(category)})
                    elif isinstance(item, str):
                        collected.append({"word": item, "weight": 1.0, "category": ""})
            elif isinstance(raw, dict):

                handled = False
                for nested_key in ("items", "words", "data"):
                    nested = raw.get(nested_key)
                    if isinstance(nested, list):
                        collected.extend(_collect_items(nested))
                        handled = True
                if handled:
                    return collected


                if not {"labels", "datasets"}.intersection(raw.keys()):
                    for text, weight in raw.items():
                        if text in skip_keys:
                            continue
                        collected.append({"word": str(text), "weight": weight, "category": ""})
            return collected

        words: list[dict] = []
        seen: set[str] = set()
        candidates = []
        if isinstance(props, dict):

            if "data" in props and isinstance(props.get("data"), list):
                candidates.append(props["data"])
            if "words" in props and isinstance(props.get("words"), list):
                candidates.append(props["words"])
            if "items" in props and isinstance(props.get("items"), list):
                candidates.append(props["items"])
        candidates.append((props or {}).get("sourceData"))


        if block_data is not None:
            if isinstance(block_data, dict) and "items" in block_data and isinstance(block_data.get("items"), list):
                candidates.append(block_data["items"])
            else:
                candidates.append(block_data)

        for raw in candidates:
            for item in _collect_items(raw):
                key = f"{item['word']}::{item.get('category','')}"
                if key in seen:
                    continue
                seen.add(key)
                words.append(item)

        if not words:
            return ""

        def _format_weight(value: Any) -> str:
            """Unified formatting of weights, supporting percentage/numeric and string parsing"""
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if 0 <= value <= 1.5:
                    return f"{value * 100:.1f}%"
                return f"{value:.2f}".rstrip("0").rstrip(".")
            return str(value)

        widget_attr = f' data-widget-id="{self._escape_attr(widget_id)}"' if widget_id else ""
        rows = "".join(
            f"<tr><td>{self._escape_html(item['word'])}</td>"
            f"<td>{self._escape_html(_format_weight(item['weight']))}</td>"
            f"<td>{self._escape_html(item['category'] or '-')}</td></tr>"
            for item in words
        )
        return f"""
        <div class="chart-degraded" data-prebuilt="true"{widget_attr}>
          <table>
            <thead>
              <tr><th>keywords</th><th>weight</th><th>category</th></tr>
            </thead>
            <tbody>
              {rows}
            </tbody>
          </table>
        </div>
        """

    def _log_chart_validation_stats(self):
        """Output chart validation statisticsInfo"""
        stats = self.chart_validation_stats
        if stats['total'] == 0:
            return

        logger.info("=" * 60)
        logger.info("Chart validation statistics")
        logger.info("=" * 60)
        logger.info(f"Total number of charts: {stats['total']}")
        logger.info(f"  ✓ Verification passed: {stats['valid']} ({stats['valid']/stats['total']*100:.1f}%)")

        if stats['repaired_locally'] > 0:
            logger.info(
                f"  ⚠ local fix: {stats['repaired_locally']} "
                f"({stats['repaired_locally']/stats['total']*100:.1f}%)"
            )

        if stats['repaired_api'] > 0:
            logger.info(
                f"  ⚠ APIrepair: {stats['repaired_api']} "
                f"({stats['repaired_api']/stats['total']*100:.1f}%)"
            )

        if stats['failed'] > 0:
            logger.warning(
                f"  ✗ repairFailed: {stats['failed']} "
                f"({stats['failed']/stats['total']*100:.1f}%) - "
                f"These charts will show concise degraded mode tips"
            )

        logger.info("=" * 60)



    def _kpi_signature_from_items(self, items: Any) -> tuple | None:
        """Convert array of KPIs into comparable signatures"""
        if not isinstance(items, list):
            return None
        normalized = []
        for raw in items:
            normalized_item = self._normalize_kpi_item(raw)
            if normalized_item:
                normalized.append(normalized_item)
        return tuple(normalized) if normalized else None

    def _normalize_kpi_item(self, item: Any) -> tuple[str, str, str, str, str] | None:
        """
        Organize individual KPI records into comparable signatures.

        parameter:
            item: KPIRaw dictionary in array, may have missing fields or mixed types.

        return:
            tuple | None: (label, value, unit, delta, tone) The five-tuple of; if the input is illegal, the rule isNone。
        """
        if not isinstance(item, dict):
            return None

        def normalize(value: Any) -> str:
            """Unify the representation of various values ​​to facilitate the generation of stable signatures"""
            if value is None:
                return ""
            if isinstance(value, (int, float)):
                return str(value)
            return str(value).strip()

        label = normalize(item.get("label"))
        value = normalize(item.get("value"))
        unit = normalize(item.get("unit"))
        delta = normalize(item.get("delta"))
        tone = normalize(item.get("deltaTone") or item.get("tone"))
        return label, value, unit, delta, tone

    def _should_skip_overview_kpi(self, block: Dict[str, Any]) -> bool:
        """If the KPI content is consistent with the cover, it will be determined as a duplicate overview."""
        if not self.hero_kpi_signature:
            return False
        block_signature = self._kpi_signature_from_items(block.get("items"))
        if not block_signature:
            return False
        return block_signature == self.hero_kpi_signature



    def _normalize_inline_payload(self, run: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
        """Flatten nested inline nodes into base text withmarks"""
        if not isinstance(run, dict):
            return ("" if run is None else str(run)), []


        if run.get("type") == "inlineRun":
            inner_inlines = run.get("inlines") or []
            outer_marks = run.get("marks") or []

            texts = []
            all_marks = list(outer_marks)
            for inline in inner_inlines:
                inner_text, inner_marks = self._normalize_inline_payload(inline)
                texts.append(inner_text)
                all_marks.extend(inner_marks)
            return "".join(texts), all_marks

        marks = list(run.get("marks") or [])
        text_value: Any = run.get("text", "")
        seen: set[int] = set()

        # ⚡ OPTIMIZATION: Removed manual while loop and json dumping for degraded rendering
        # This resolves an O(N) iteration bottleneck when parsing complex nested JSON inline text formats.
        if isinstance(text_value, dict):
            text_value = text_value.get("text", "")
            if not text_value:
                try:
                    text_value = json.dumps(text_value, ensure_ascii=False)
                except Exception:
                    text_value = ""

            if "text" in text_value:
                text_value = text_value.get("text")
            else:
                text_value = json.dumps(text_value, ensure_ascii=False)

        if text_value is None:
            text_value = ""
        elif isinstance(text_value, (int, float)):
            text_value = str(text_value)
        elif not isinstance(text_value, str):
            try:
                text_value = json.dumps(text_value, ensure_ascii=False)
            except TypeError:
                text_value = str(text_value)

        if isinstance(text_value, str):
            stripped = text_value.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                payload = None
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    sentinel_keys = {"xrefs", "widgets", "footnotes", "errors", "metadata"}
                    if set(payload.keys()).issubset(sentinel_keys):
                        text_value = ""
                    else:
                        inline_payload = self._coerce_inline_payload(payload)
                        if inline_payload:

                            if inline_payload.get("type") == "inlineRun":
                                return self._normalize_inline_payload(inline_payload)
                            nested_text = inline_payload.get("text")
                            if nested_text is not None:
                                text_value = nested_text
                            nested_marks = inline_payload.get("marks")
                        elif any(key in payload for key in self.INLINE_ARTIFACT_KEYS):
                            text_value = ""

        return text_value, marks

    @staticmethod
    def _normalize_latex_string(raw: Any) -> str:
        """Remove outer mathematical delimiter, compatible with $...$、$$...$$、\\(\\)、\\[\\] Other formats"""
        if not isinstance(raw, str):
            return ""
        latex = raw.strip()
        patterns = [
            r'^\$\$(.*)\$\$$',
            r'^\$(.*)\$$',
            r'^\\\[(.*)\\\]$',
            r'^\\\((.*)\\\)$',
        ]
        for pat in patterns:
            m = re.match(pat, latex, re.DOTALL)
            if m:
                latex = m.group(1).strip()
                break
        return latex

    def _render_text_with_inline_math(
        self,
        text: Any,
        math_id: str | list | None = None,
        allow_display_block: bool = False
    ) -> str | None:
        """
        Recognize math delimiters in plain text and render them as math-inline/math-block to improve compatibility.

        - support $...$、$$...$$、\\(\\)、\\[\\]。
        - If no formula is detected, returnNone。
        """
        if not isinstance(text, str) or not text:
            return None

        pattern = re.compile(r'(\$\$(.+?)\$\$|\$(.+?)\$|\\\((.+?)\\\)|\\\[(.+?)\\\])', re.S)
        matches = list(pattern.finditer(text))
        if not matches:
            return None

        cursor = 0
        parts: List[str] = []
        id_iter = iter(math_id) if isinstance(math_id, list) else None

        for idx, m in enumerate(matches, start=1):
            start, end = m.span()
            prefix = text[cursor:start]
            raw = next(g for g in m.groups()[1:] if g is not None)
            latex = self._normalize_latex_string(raw)

            if id_iter:
                mid = next(id_iter, f"auto-math-{idx}")
            else:
                mid = math_id or f"auto-math-{idx}"
            id_attr = f' data-math-id="{self._escape_attr(mid)}"'
            is_display = m.group(1).startswith('$$') or m.group(1).startswith('\\[')
            is_standalone = (
                len(matches) == 1 and
                not text[:start].strip() and
                not text[end:].strip()
            )
            use_block = allow_display_block and is_display and is_standalone
            if use_block:

                parts.append(f'<div class="math-block"{id_attr}>$$ {self._escape_html(latex)} $$</div>')
                cursor = len(text)
                break
            else:
                if prefix:
                    parts.append(self._escape_html(prefix))
                parts.append(f'<span class="math-inline"{id_attr}>\\( {self._escape_html(latex)} \\)</span>')
            cursor = end

        if cursor < len(text):
            parts.append(self._escape_html(text[cursor:]))
        return "".join(parts)

    @staticmethod
    def _coerce_inline_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
        """Try our best to restore inline nodes in strings to dict and fix rendering omissions"""
        if not isinstance(payload, dict):
            return None
        inline_type = payload.get("type")

        if inline_type == "inlineRun":
            return payload
        if inline_type and inline_type not in {"inline", "text"}:
            return None
        if "text" not in payload and "marks" not in payload and "inlines" not in payload:
            return None
        return payload

    def _render_inline(self, run: Dict[str, Any]) -> str:
        """
        Render a single inline run and support the overlay of multiple marks.

        parameter:
            run: Inline nodes containing text and marks.

        return:
            str: HTML fragment wrapped with tags/styles。
        """
        text_value, marks = self._normalize_inline_payload(run)
        math_mark = next((mark for mark in marks if mark.get("type") == "math"), None)
        if math_mark:
            latex = self._normalize_latex_string(math_mark.get("value"))
            if not isinstance(latex, str) or not latex.strip():
                latex = self._normalize_latex_string(text_value)
            math_id = self._escape_attr(run.get("mathId", "")) if run.get("mathId") else ""
            id_attr = f' data-math-id="{math_id}"' if math_id else ""
            return f'<span class="math-inline"{id_attr}>\\( {self._escape_html(latex)} \\)</span>'


        math_id_hint = run.get("mathIds") or run.get("mathId")
        mathified = self._render_text_with_inline_math(text_value, math_id_hint)
        if mathified is not None:
            return mathified

        text = self._escape_html(text_value)
        styles: List[str] = []
        prefix: List[str] = []
        suffix: List[str] = []
        for mark in marks:
            mark_type = mark.get("type")
            if mark_type == "bold":
                prefix.append("<strong>")
                suffix.insert(0, "</strong>")
            elif mark_type == "italic":
                prefix.append("<em>")
                suffix.insert(0, "</em>")
            elif mark_type == "code":
                prefix.append("<code>")
                suffix.insert(0, "</code>")
            elif mark_type == "highlight":
                prefix.append("<mark>")
                suffix.insert(0, "</mark>")
            elif mark_type == "link":
                href_raw = mark.get("href")
                if href_raw and href_raw != "#":
                    href = self._escape_attr(href_raw)
                    title = self._escape_attr(mark.get("title") or "")
                    prefix.append(f'<a href="{href}" title="{title}" target="_blank" rel="noopener noreferrer">')
                    suffix.insert(0, "</a>")
                else:
                    prefix.append('<span class="broken-link">')
                    suffix.insert(0, "</span>")
            elif mark_type == "color":
                value = mark.get("value")
                if value:
                    styles.append(f"color: {value}")
            elif mark_type == "font":
                family = mark.get("family")
                size = mark.get("size")
                weight = mark.get("weight")
                if family:
                    styles.append(f"font-family: {family}")
                if size:
                    styles.append(f"font-size: {size}")
                if weight:
                    styles.append(f"font-weight: {weight}")
            elif mark_type == "underline":
                styles.append("text-decoration: underline")
            elif mark_type == "strike":
                styles.append("text-decoration: line-through")
            elif mark_type == "subscript":
                prefix.append("<sub>")
                suffix.insert(0, "</sub>")
            elif mark_type == "superscript":
                prefix.append("<sup>")
                suffix.insert(0, "</sup>")

        if styles:
            style_attr = "; ".join(styles)
            prefix.insert(0, f'<span style="{style_attr}">')
            suffix.append("</span>")

        if not marks and "**" in (run.get("text") or ""):
            return self._render_markdown_bold_safe(run.get("text", ""))

        return "".join(prefix) + text + "".join(suffix)

    def _render_markdown_bold_safe(self, text: str) -> str:
        """Convert completely when LLM does not use marks**Bold**"""
        if not text:
            return ""
        escaped = html.escape(text)
        return self._BOLD_RE.sub(r"<strong>\1</strong>", escaped)



    def _clean_text_from_json_artifacts(self, text: Any) -> str:
        """
        Cleaning JSON fragments from textand forged structural markings.

        LLM sometimes mixes in uncompleted JSON fragments in text fields, like：
        "description text，{ \"chapterId\": \"S3" or "description text，{ \"level\": 2"

        This method will:
        1. Remove incomplete JSON objects (starting with { started but not closed correctly)
        2. Remove incomplete JSON array (starting with [ started but not closed correctly)
        3. Remove orphaned JSON key-value pair fragments

        parameters:
            text: Text that may contain JSON fragments

        Return:
            str: Cleaned plain text
        """
        if not text:
            return ""

        text_str = self._safe_text(text)



        text_str = re.sub(r',\s*\{[^}]*$', '', text_str)


        text_str = re.sub(r',\s*\[[^\]]*$', '', text_str)



        open_brace_pos = text_str.rfind('{')
        if open_brace_pos != -1:
            close_brace_pos = text_str.rfind('}')
            if close_brace_pos < open_brace_pos:


                text_str = text_str[:open_brace_pos].rstrip(',，、 \t\n')


        open_bracket_pos = text_str.rfind('[')
        if open_bracket_pos != -1:
            close_bracket_pos = text_str.rfind(']')
            if close_bracket_pos < open_bracket_pos:

                text_str = text_str[:open_bracket_pos].rstrip(',，、 \t\n')



        text_str = re.sub(r',?\s*"[^"]+"\s*:\s*"[^"]*$', '', text_str)
        text_str = re.sub(r',?\s*"[^"]+"\s*:\s*[^,}\]]*$', '', text_str)


        text_str = text_str.rstrip(',，、 \t\n')

        return text_str.strip()

    def _safe_text(self, value: Any) -> str:
        """Safe conversion of arbitrary values ​​to strings, fault-tolerant of None and complex objects"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return str(value)
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)

    def _escape_html(self, value: Any) -> str:
        """HTMLEscaping text context"""
        return html.escape(self._safe_text(value), quote=False)

    def _escape_attr(self, value: Any) -> str:
        """HTMLAttribute context escaping and dangerous newlines removed"""
        escaped = html.escape(self._safe_text(value), quote=True)
        return escaped.replace("\n", " ").replace("\r", " ")



    def _build_css(self, tokens: Dict[str, Any]) -> str:
        """Splicing full-page CSS based on Themetoken, including responsive and print styles"""

        colors_raw = tokens.get("colors")
        colors = colors_raw if isinstance(colors_raw, dict) else {}

        typography_raw = tokens.get("typography")
        typography = typography_raw if isinstance(typography_raw, dict) else {}


        fonts_raw = tokens.get("fonts") or typography.get("fonts")
        if isinstance(fonts_raw, dict):
            fonts = fonts_raw
        else:

            font_family = typography.get("fontFamily")
            if isinstance(font_family, str):
                fonts = {"body": font_family, "heading": font_family}
            else:
                fonts = {}

        spacing_raw = tokens.get("spacing")
        spacing = spacing_raw if isinstance(spacing_raw, dict) else {}

        primary_palette = self._resolve_color_family(
            colors.get("primary"),
            {"main": "#1a365d", "light": "#2d3748", "dark": "#0f1a2d"},
        )
        secondary_palette = self._resolve_color_family(
            colors.get("secondary"),
            {"main": "#e53e3e", "light": "#fc8181", "dark": "#c53030"},
        )
        bg = self._resolve_color_value(
            colors.get("bg") or colors.get("background") or colors.get("surface"),
            "#f8f9fa",
        )
        text_color = self._resolve_color_value(
            colors.get("text") or colors.get("onBackground"),
            "#212529",
        )
        card = self._resolve_color_value(
            colors.get("card") or colors.get("surfaceCard"),
            "#ffffff",
        )
        border = self._resolve_color_value(
            colors.get("border") or colors.get("divider"),
            "#dee2e6",
        )
        shadow = "rgba(0,0,0,0.08)"
        container_width = spacing.get("container") or spacing.get("containerWidth") or "1200px"
        gutter = spacing.get("gutter") or spacing.get("pagePadding") or "24px"
        body_font = fonts.get("body") or fonts.get("primary") or "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
        heading_font = fonts.get("heading") or fonts.get("primary") or fonts.get("secondary") or body_font

        import os
        css_path = os.path.join(os.path.dirname(__file__), "template.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css_template = f.read()

        return css_template.format(
            bg=bg,
            text_color=text_color,
            primary_main=primary_palette["main"],
            primary_light=primary_palette["light"],
            primary_dark=primary_palette["dark"],
            secondary_main=secondary_palette["main"],
            secondary_light=secondary_palette["light"],
            secondary_dark=secondary_palette["dark"],
            card=card,
            border=border,
            shadow=shadow,
            container_width=container_width,
            gutter=gutter,
            body_font=body_font,
            heading_font=heading_font
        )

    def _hydration_script(self) -> str:
        """
        Return to the JS at the bottom of the page, responsible for Chart.js water injection、Word cloud rendering and button interaction.

        Sorting out interaction levels：
        1) Themetoggle (
           Function: switch body.dark-mode、Refresh Chart.js with word cloud colors。
        2) print button（
        3) Export button (
           and display
        4) Chart water filling: scan the canvas of All data-config-id, parse adjacent JSON, and instantiate Chart.js;
           When Failed, it is demoted to a table/word cloud badge display and marked on the card. data-chart-state。
        5) Window resize: redraw the word cloud after debounce to ensure responsiveness。
        """
        try:
            import os
            js_path = os.path.join(os.path.dirname(__file__), 'assets', 'report_hydration.js')
            with open(js_path, 'r', encoding='utf-8') as f:
                js_content = f.read()
            return f"<script>\n{js_content}\n</script>"
        except Exception as e:
            return f"<!-- Failed to load hydration script: {e} -->"

