"""
PDFlayout optimizer

Automatically analyze and optimize PDF layout to ensure content does not overflow、The layout is beautiful.
support：
- Automatically adjust font size
- Optimize line spacing
- Adjust color block size
- Smart arrangement of Info blocks
- Save and load optimization solutions
- Text width detection and overflow prevention
- Color block boundary detection and automatic adjustment
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from loguru import logger


@dataclass
class KPICardLayout:
    """KPICard layout configuration"""
    font_size_value: int = 32
    font_size_label: int = 14
    font_size_change: int = 13
    padding: int = 20
    min_height: int = 120
    value_max_length: int = 10


@dataclass
class CalloutLayout:
    """Prompt box layout configuration"""
    font_size_title: int = 16
    font_size_content: int = 14
    padding: int = 20
    line_height: float = 1.6
    max_width: str = "100%"


@dataclass
class TableLayout:
    """Table layout configuration"""
    font_size_header: int = 13
    font_size_body: int = 12
    cell_padding: int = 12
    max_cell_width: int = 200
    overflow_strategy: str = "wrap"


@dataclass
class ChartLayout:
    """Chart layout configuration"""
    font_size_title: int = 16
    font_size_label: int = 12
    min_height: int = 300
    max_height: int = 600
    padding: int = 20


@dataclass
class GridLayout:
    """Grid layout configuration"""
    columns: int = 3
    gap: int = 20
    responsive_breakpoint: int = 768


@dataclass
class DataBlockLayout:
    """data block (color block、KPI、scale configuration for tables, etc.)"""
    overview_text_scale: float = 0.93
    overview_kpi_scale: float = 0.88
    body_text_scale: float = 0.8
    body_kpi_scale: float = 0.76
    min_overview_font: int = 12
    min_body_font: int = 11


@dataclass
class PageLayout:
    """Overall page layout configuration"""
    font_size_base: int = 14
    font_size_h1: int = 28
    font_size_h2: int = 24
    font_size_h3: int = 20
    font_size_h4: int = 16
    line_height: float = 1.6
    paragraph_spacing: int = 16
    section_spacing: int = 32
    page_padding: int = 40
    max_content_width: int = 800


@dataclass
class PDFLayoutConfig:
    """Complete PDF layout configuration"""
    page: PageLayout
    kpi_card: KPICardLayout
    callout: CalloutLayout
    table: TableLayout
    chart: ChartLayout
    grid: GridLayout
    data_block: DataBlockLayout


    auto_adjust_font_size: bool = True
    auto_adjust_grid_columns: bool = True
    prevent_orphan_headers: bool = True
    optimize_for_print: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'page': asdict(self.page),
            'kpi_card': asdict(self.kpi_card),
            'callout': asdict(self.callout),
            'table': asdict(self.table),
            'chart': asdict(self.chart),
            'grid': asdict(self.grid),
            'data_block': asdict(self.data_block),
            'auto_adjust_font_size': self.auto_adjust_font_size,
            'auto_adjust_grid_columns': self.auto_adjust_grid_columns,
            'prevent_orphan_headers': self.prevent_orphan_headers,
            'optimize_for_print': self.optimize_for_print,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFLayoutConfig:
        """Create configuration from dictionary"""
        return cls(
            page=PageLayout(**data['page']),
            kpi_card=KPICardLayout(**data['kpi_card']),
            callout=CalloutLayout(**data['callout']),
            table=TableLayout(**data['table']),
            chart=ChartLayout(**data['chart']),
            grid=GridLayout(**data['grid']),
            data_block=DataBlockLayout(**data.get('data_block', {})),
            auto_adjust_font_size=data.get('auto_adjust_font_size', True),
            auto_adjust_grid_columns=data.get('auto_adjust_grid_columns', True),
            prevent_orphan_headers=data.get('prevent_orphan_headers', True),
            optimize_for_print=data.get('optimize_for_print', True),
        )


class PDFLayoutOptimizer:
    """
    PDFlayout optimizer

    Automatically optimize PDF layout based on content characteristics to prevent overflow and typesetting problems。
    """





    CHAR_WIDTH_FACTOR = {
        'chinese': 1.05,
        'english': 0.58,
        'number': 0.65,
        'symbol': 0.45,
        'percent': 0.7,
    }

    def __init__(self, config: Optional[PDFLayoutConfig] = None):
        """
        Initialize the optimizer

        parameters:
            config: Layout configuration, if None the default configuration is used
        """
        self.config = config or self._create_default_config()
        self.optimization_log = []

    @staticmethod
    def _create_default_config() -> PDFLayoutConfig:
        """Create default configuration"""
        return PDFLayoutConfig(
            page=PageLayout(),
            kpi_card=KPICardLayout(),
            callout=CalloutLayout(),
            table=TableLayout(),
            chart=ChartLayout(),
            grid=GridLayout(),
            data_block=DataBlockLayout(),
        )

    def optimize_for_document(self, document_ir: Dict[str, Any]) -> PDFLayoutConfig:
        """
        Optimize layout configuration based on document IR content

        parameters:
            document_ir: Document IRdata

        Return:
            PDFLayoutConfig: Optimized layout configuration
        """
        logger.info("Start analyzing documents and optimizing layout...")


        stats = self._analyze_document(document_ir)


        optimized_config = self._adjust_config_based_on_stats(stats)


        self._log_optimization(stats, optimized_config)

        return optimized_config

    def _analyze_document(self, document_ir: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze document content characteristics

        Return statisticsInfo：
        - kpi_count: KPINumber of cards
        - table_count: number of tables
        - chart_count: number of charts
        - max_kpi_value_length: The longest KPI value length
        - max_table_columns: Maximum number of table columns
        - total_content_length: total content length
        - hero_kpi_count: HeroNumber of KPIs in the region
        - max_hero_kpi_value_length: HeroThe longest KPI value length in the region
        """
        stats = {
            'kpi_count': 0,
            'table_count': 0,
            'chart_count': 0,
            'callout_count': 0,
            'max_kpi_value_length': 0,
            'max_table_columns': 0,
            'max_table_rows': 0,
            'total_content_length': 0,
            'has_long_text': False,
            'hero_kpi_count': 0,
            'max_hero_kpi_value_length': 0,
        }


        metadata = document_ir.get('metadata', {})
        hero = metadata.get('hero', {})
        if hero:
            hero_kpis = hero.get('kpis', [])
            stats['hero_kpi_count'] = len(hero_kpis)
            for kpi in hero_kpis:
                value = str(kpi.get('value', ''))
                stats['max_hero_kpi_value_length'] = max(
                    stats['max_hero_kpi_value_length'],
                    len(value)
                )


        chapters = document_ir.get('chapters', [])
        if not chapters:
            chapters = document_ir.get('sections', [])


        for chapter in chapters:
            self._analyze_chapter(chapter, stats)

        logger.info(f"Document analysisCompleted: {stats}")
        return stats

    def _analyze_chapter(self, chapter: Dict[str, Any], stats: Dict[str, Any]):
        """Analyze a single chapter"""

        blocks = chapter.get('blocks', [])
        for block in blocks:
            self._analyze_block(block, stats)


        children = chapter.get('children', [])
        for child in children:
            if isinstance(child, dict):
                self._analyze_chapter(child, stats)

    def _analyze_block(self, block: Dict[str, Any], stats: Dict[str, Any]):
        """Analyze a single block node"""
        if not isinstance(block, dict):
            return

        node_type = block.get('type')

        if node_type == 'kpiGrid':
            kpis = block.get('items', [])
            stats['kpi_count'] += len(kpis)


            for kpi in kpis:
                value = str(kpi.get('value', ''))
                stats['max_kpi_value_length'] = max(
                    stats['max_kpi_value_length'],
                    len(value)
                )

        elif node_type == 'table':
            stats['table_count'] += 1


            headers = block.get('headers', [])
            rows = block.get('rows', [])
            if rows and isinstance(rows[0], dict):

                cells = rows[0].get('cells', [])
                stats['max_table_columns'] = max(
                    stats['max_table_columns'],
                    len(cells)
                )
            else:
                stats['max_table_columns'] = max(
                    stats['max_table_columns'],
                    len(headers)
                )
            stats['max_table_rows'] = max(
                stats['max_table_rows'],
                len(rows)
            )

        elif node_type == 'chart' or node_type == 'widget':
            stats['chart_count'] += 1

        elif node_type == 'callout':
            stats['callout_count'] += 1

            callout_blocks = block.get('blocks', [])
            for cb in callout_blocks:
                if isinstance(cb, dict) and cb.get('type') == 'paragraph':
                    text = self._extract_text_from_paragraph(cb)
                    if len(text) > 200:
                        stats['has_long_text'] = True

        elif node_type == 'paragraph':
            text = self._extract_text_from_paragraph(block)
            stats['total_content_length'] += len(text)
            if len(text) > 500:
                stats['has_long_text'] = True


        nested_blocks = block.get('blocks', [])
        if nested_blocks:
            for nested in nested_blocks:
                self._analyze_block(nested, stats)

    def _extract_text_from_paragraph(self, paragraph: Dict[str, Any]) -> str:
        """Extract plain text from paragraph block"""
        text_parts = []
        inlines = paragraph.get('inlines', [])
        for inline in inlines:
            if isinstance(inline, dict):
                text = inline.get('text', '')
                if text:
                    text_parts.append(str(text))
            elif isinstance(inline, str):
                text_parts.append(inline)
        return ''.join(text_parts)

    def _analyze_section(self, section: Dict[str, Any], stats: Dict[str, Any]):
        """Recursive Analysis Chapter (reserved for backward compatibility）"""

        self._analyze_chapter(section, stats)

    def _estimate_text_width(self, text: str, font_size: int) -> float:
        """
        Estimate text width in pixels

        parameters:
            text: text to measure
            font_size: Font size (pixels)

        Return:
            float: Estimated width (pixels）
        """
        if not text:
            return 0.0

        width = 0.0
        for char in text:
            if '\u4e00' <= char <= '\u9fff':
                width += font_size * self.CHAR_WIDTH_FACTOR['chinese']
            elif char.isalpha():
                width += font_size * self.CHAR_WIDTH_FACTOR['english']
            elif char.isdigit():
                width += font_size * self.CHAR_WIDTH_FACTOR['number']
            elif char in '%％':
                width += font_size * self.CHAR_WIDTH_FACTOR['percent']
            else:
                width += font_size * self.CHAR_WIDTH_FACTOR['symbol']

        return width

    def _check_text_overflow(self, text: str, font_size: int, max_width: int) -> bool:
        """
        Check if text will overflow

        parameters:
            text: text to check
            font_size: Font size (pixels）
            max_width: Maximum width (pixels)

        Return:
            bool: Truemeans it will overflow
        """
        estimated_width = self._estimate_text_width(text, font_size)
        return estimated_width > max_width

    def _calculate_safe_font_size(
        self,
        text: str,
        max_width: int,
        min_font_size: int = 10,
        max_font_size: int = 32
    ) -> Tuple[int, bool]:
        """
        Calculate safe font sizes to avoid overflow

        parameters:
            text: text to display
            max_width: Maximum width (pixels）
            min_font_size: Minimum font size
            max_font_size: Maximum font size

        Return:
            Tuple[int, bool]: (Recommended font size, Does it need to be adjusted?)
        """
        if not text:
            return max_font_size, False


        for font_size in range(max_font_size, min_font_size - 1, -1):
            if not self._check_text_overflow(text, font_size, max_width):

                needs_adjustment = font_size < max_font_size
                return font_size, needs_adjustment


        return min_font_size, True

    def _detect_kpi_overflow_issues(self, stats: Dict[str, Any]) -> List[str]:
        """
        Detect possible overflow issues in KPI cards

        parameters:
            stats: Document StatisticsInfo

        Return:
            List[str]: List of detected issues
        """
        issues = []



        kpi_card_width = (800 - 20) // 2 - 40


        max_kpi_length = stats.get('max_kpi_value_length', 0)
        if max_kpi_length > 0:

            sample_text = '1' * max_kpi_length + 'billion'
            current_font_size = self.config.kpi_card.font_size_value

            if self._check_text_overflow(sample_text, current_font_size, kpi_card_width):
                issues.append(
                    f"KPIValue is too long({max_kpi_length}character)，"
                    f"Font size{current_font_size}pxmay cause overflow"
                )

        return issues

    def _adjust_config_based_on_stats(
        self,
        stats: Dict[str, Any]
    ) -> PDFLayoutConfig:
        """Adjust configuration based on statistical information"""
        config = PDFLayoutConfig(
            page=PageLayout(**asdict(self.config.page)),
            kpi_card=KPICardLayout(**asdict(self.config.kpi_card)),
            callout=CalloutLayout(**asdict(self.config.callout)),
            table=TableLayout(**asdict(self.config.table)),
            chart=ChartLayout(**asdict(self.config.chart)),
            grid=GridLayout(**asdict(self.config.grid)),
            data_block=DataBlockLayout(**asdict(self.config.data_block)),
            auto_adjust_font_size=self.config.auto_adjust_font_size,
            auto_adjust_grid_columns=self.config.auto_adjust_grid_columns,
            prevent_orphan_headers=self.config.prevent_orphan_headers,
            optimize_for_print=self.config.optimize_for_print,
        )


        overflow_issues = self._detect_kpi_overflow_issues(stats)
        if overflow_issues:
            for issue in overflow_issues:
                logger.warning(f"Layout issue detected: {issue}")


        kpi_card_width = (800 - 20) // 2 - 60


        if stats['hero_kpi_count'] > 0 and stats['max_hero_kpi_value_length'] > 0:

            hero_kpi_width = 250
            sample_text = '9' * stats['max_hero_kpi_value_length'] + 'Yuan'
            safe_font_size, needs_adjustment = self._calculate_safe_font_size(
                sample_text,
                hero_kpi_width,
                min_font_size=14,
                max_font_size=24
            )

            if needs_adjustment or stats['max_hero_kpi_value_length'] > 6:

                config.kpi_card.font_size_value = max(14, safe_font_size - 2)
                self.optimization_log.append(
                    f"Hero KPIThe value is longer({stats['max_hero_kpi_value_length']}character)，"
                    f"Adjust the font size to{config.kpi_card.font_size_value}px"
                )


        if stats['max_kpi_value_length'] > 0:

            sample_text = '9' * stats['max_kpi_value_length'] + '100 million'
            safe_font_size, needs_adjustment = self._calculate_safe_font_size(
                sample_text,
                kpi_card_width,
                min_font_size=16,
                max_font_size=28
            )

            if needs_adjustment:
                config.kpi_card.font_size_value = safe_font_size

                config.kpi_card.font_size_value = max(16, safe_font_size - 2)
                self.optimization_log.append(
                    f"KPIValue is too long({stats['max_kpi_value_length']}character)，"
                    f"The font size is automatically adjusted to{config.kpi_card.font_size_value}pxto prevent overflow"
                )
            elif stats['max_kpi_value_length'] > 8:

                config.kpi_card.font_size_value = min(24, safe_font_size)
                self.optimization_log.append(
                    f"KPIThe value is longer({stats['max_kpi_value_length']}character)，"
                    f"Preventive adjustment of font size is{config.kpi_card.font_size_value}px"
                )


        base = config.page.font_size_base
        kpi_value_cap = max(base + 6, 20)
        kpi_label_cap = max(base - 1, 12)
        kpi_change_cap = max(base, 12)

        original_value = config.kpi_card.font_size_value
        original_label = config.kpi_card.font_size_label
        original_change = config.kpi_card.font_size_change

        config.kpi_card.font_size_value = min(original_value, kpi_value_cap)
        config.kpi_card.font_size_value = max(config.kpi_card.font_size_value, base + 1)
        config.kpi_card.font_size_label = min(original_label, kpi_label_cap)
        config.kpi_card.font_size_label = max(config.kpi_card.font_size_label, 12)
        config.kpi_card.font_size_change = min(original_change, kpi_change_cap)
        config.kpi_card.font_size_change = max(config.kpi_card.font_size_change, 12)
        self.optimization_log.append(
            f"KPITightening the upper limit of font size: numerical value{original_value}px→{config.kpi_card.font_size_value}px，"
            f"Label{original_label}px→{config.kpi_card.font_size_label}px，"
            f"change{original_change}px→{config.kpi_card.font_size_change}px"
        )

        total_blocks = (stats['kpi_count'] + stats['table_count'] +
                        stats['chart_count'] + stats['callout_count'])


        if stats['hero_kpi_count'] >= 3 or stats['max_hero_kpi_value_length'] > 6:
            prev = config.data_block.overview_kpi_scale
            config.data_block.overview_kpi_scale = min(prev, 0.86)
            if config.data_block.overview_kpi_scale != prev:
                self.optimization_log.append(
                    f"Article overview KPIs are dense and the scaling factor {prev:.2f}→{config.data_block.overview_kpi_scale:.2f}"
                )

        if stats['has_long_text'] or stats['max_table_columns'] > 6:
            prev_text = config.data_block.body_text_scale
            prev_kpi = config.data_block.body_kpi_scale
            config.data_block.body_text_scale = min(prev_text, 0.78)
            config.data_block.body_kpi_scale = min(prev_kpi, 0.74)
            self.optimization_log.append(
                f"Text block compression: long text/Wide table trigger, text scales to{config.data_block.body_text_scale*100:.0f}%，"
                f"KPIZoom to{config.data_block.body_kpi_scale*100:.0f}%"
            )
        elif total_blocks > 16:
            prev_text = config.data_block.body_text_scale
            prev_kpi = config.data_block.body_kpi_scale
            config.data_block.body_text_scale = min(prev_text, 0.80)
            config.data_block.body_kpi_scale = min(prev_kpi, 0.75)
            self.optimization_log.append(
                f"Body data block scaling: more content blocks({total_blocks}indivual)，Text zoom to{config.data_block.body_text_scale*100:.0f}%，"
                f"KPIZoom to{config.data_block.body_kpi_scale*100:.0f}%"
            )
        elif total_blocks > 10:
            prev_text = config.data_block.body_text_scale
            config.data_block.body_text_scale = min(prev_text, 0.82)
            if config.data_block.body_text_scale != prev_text:
                self.optimization_log.append(
                    f"Lightweight scaling of text data blocks({total_blocks}blocks)，Text scaling factor {prev_text:.2f}→{config.data_block.body_text_scale:.2f}"
                )


        config.grid.columns = 3
        if stats['kpi_count'] > 6:
            config.kpi_card.min_height = 100
            config.kpi_card.padding = 14
            config.grid.gap = 16
            self.optimization_log.append(
                f"KPIMore cards({stats['kpi_count']}indivual)，"
                f"Keep the three-column layout and reduce the padding and spacing"
            )
        elif stats['kpi_count'] > 4:
            config.kpi_card.padding = 16
            config.grid.gap = 18
            self.optimization_log.append(
                f"KPIModerate card({stats['kpi_count']}indivual)，Maintain a three-column layout and adjust spacing appropriately"
            )
        elif stats['kpi_count'] <= 2:
            config.kpi_card.padding = 22
            config.grid.gap = 20
            self.optimization_log.append(
                f"KPIfewer cards({stats['kpi_count']}indivual)，"
                f"Keep the three-column layout and add padding"
            )


        if stats['max_table_columns'] > 8:
            config.table.font_size_header = 10
            config.table.font_size_body = 9
            config.table.cell_padding = 6
            self.optimization_log.append(
                f"The table has many columns({stats['max_table_columns']}List)，"
                f"Dramatically reduce font size and padding"
            )
        elif stats['max_table_columns'] > 6:
            config.table.font_size_header = 11
            config.table.font_size_body = 10
            config.table.cell_padding = 8
            self.optimization_log.append(
                f"The table has many columns({stats['max_table_columns']}List)，"
                f"Reduce font size and padding"
            )
        elif stats['max_table_columns'] > 4:
            config.table.font_size_header = 12
            config.table.font_size_body = 11
            config.table.cell_padding = 10
            self.optimization_log.append(
                f"The table has a moderate number of columns({stats['max_table_columns']}List)，"
                f"Adjust font size appropriately"
            )


        if stats['has_long_text']:
            config.page.line_height = 1.75
            config.callout.line_height = 1.75
            config.page.paragraph_spacing = 16
            self.optimization_log.append(
                "Long text detected, increase line height to1.75and paragraph spacing to improve readability"
            )
        else:

            config.page.line_height = 1.5
            config.callout.line_height = 1.6
            config.page.paragraph_spacing = 14
            self.optimization_log.append(
                "Text is of moderate length, using standard line heights and paragraph spacing"
            )


        if total_blocks > 20:
            config.page.font_size_base = 13
            config.page.font_size_h2 = 22
            config.page.font_size_h3 = 18
            self.optimization_log.append(
                f"More content blocks({total_blocks}indivual)，"
                f"Moderately reduce the overall font size to optimize layout"
            )

        return config

    def _log_optimization(
        self,
        stats: Dict[str, Any],
        config: PDFLayoutConfig
    ):
        """Record optimization process"""
        log_entry = {
            'timestamp': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            'document_stats': stats,
            'optimizations': self.optimization_log.copy(),
            'final_config': config.to_dict(),
        }

        logger.info(f"Layout optimization Completed, applied{len(self.optimization_log)}Item optimization")
        for opt in self.optimization_log:
            logger.info(f"  - {opt}")


        self.optimization_log.clear()

        return log_entry

    def save_config(self, path: str | Path, log_entry: Optional[Dict] = None):
        """
        Save configuration to file

        parameters:
            path: save path
            log_entry: Optimize Logs entries (optional）
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            'config': self.config.to_dict(),
        }

        if log_entry:
            data['optimization_log'] = log_entry

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Layout configuration saved: {path}")

    @classmethod
    def load_config(cls, path: str | Path) -> PDFLayoutOptimizer:
        """
        Load configuration from file

        parameters:
            path: Configuration file path

        Return:
            PDFLayoutOptimizer: Optimizer instance loaded with configuration
        """
        path = Path(path)

        if not path.exists():
            logger.warning(f"Configuration file does not exist: {path}，Use default configuration")
            return cls()

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        config = PDFLayoutConfig.from_dict(data['config'])
        optimizer = cls(config)

        logger.info(f"Layout configuration loaded: {path}")
        return optimizer

    def generate_pdf_css(self) -> str:
        """
        Generate PDF-specific CSS based on current configuration

        Return:
            str: CSSstyle string
        """
        cfg = self.config
        db = cfg.data_block

        def _scaled(value: float, scale: float, minimum: int) -> int:
            """Proportional scaling and lower limit protection to prevent data block text from being too large or too small"""
            try:
                return max(int(round(value * scale)), minimum)
            except Exception:
                return minimum


        overview_summary_font = _scaled(cfg.page.font_size_base, db.overview_text_scale, db.min_overview_font)
        overview_badge_font = _scaled(max(cfg.page.font_size_base - 2, db.min_overview_font), db.overview_text_scale, db.min_overview_font)
        overview_kpi_value = _scaled(cfg.kpi_card.font_size_value, db.overview_kpi_scale, db.min_overview_font + 1)
        overview_kpi_label = _scaled(cfg.kpi_card.font_size_label, db.overview_kpi_scale, db.min_overview_font)
        overview_kpi_delta = _scaled(cfg.kpi_card.font_size_change, db.overview_kpi_scale, db.min_overview_font)


        body_kpi_value = _scaled(cfg.kpi_card.font_size_value, db.body_kpi_scale, db.min_body_font + 1)
        body_kpi_label = _scaled(cfg.kpi_card.font_size_label, db.body_kpi_scale, db.min_body_font)
        body_kpi_delta = _scaled(cfg.kpi_card.font_size_change, db.body_kpi_scale, db.min_body_font)
        body_callout_title = _scaled(cfg.callout.font_size_title, db.body_text_scale, db.min_body_font + 1)
        body_callout_content = _scaled(cfg.callout.font_size_content, db.body_text_scale, db.min_body_font)
        body_table_header = _scaled(cfg.table.font_size_header, db.body_text_scale, db.min_body_font)
        body_table_body = _scaled(cfg.table.font_size_body, db.body_text_scale, db.min_body_font)
        body_chart_title = _scaled(cfg.chart.font_size_title, db.body_text_scale, db.min_body_font + 1)
        body_badge_font = _scaled(max(cfg.page.font_size_base - 2, db.min_body_font), db.body_text_scale, db.min_body_font)

        css = f"""
/* PDFLayout optimization style - Automatically generated by PDFLayoutOptimizer */

/* Hide the independent cover section, which has been merged intohero */
.cover {{
    display: none !important;
}}

/* PDFShow hero actions in (recommended/action items） */
.hero-actions {{
    display: flex !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
    margin-top: 14px !important;
    padding: 0 !important;
}}

.hero-actions .ghost-btn {{
    display: inline-flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    background: none !important;
    background-color: #f3f4f6 !important;
    background-image: none !important;
    border: none !important;
    border-width: 0 !important;
    border-style: none !important;
    border-radius: 999px !important;
    padding: 5px 10px !important;
    font-size: {max(cfg.page.font_size_base - 2, 11)}px !important;
    color: #222 !important;
    width: auto !important;
    height: auto !important;
    white-space: normal !important;
    line-height: 1.5 !important;
    text-align: left !important;
    box-shadow: none !important;
    cursor: default !important;
    -webkit-appearance: none !important;
    appearance: none !important;
    outline: none !important;
    word-break: break-word !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}}

/* Basic page style */
body {{
    font-size: {cfg.page.font_size_base}px;
    line-height: {cfg.page.line_height};
}}

main {{
    padding: {cfg.page.page_padding}px !important;
    max-width: {cfg.page.max_content_width}px;
    margin: 0 auto;
}}

/* Title style */
h1 {{ font-size: {cfg.page.font_size_h1}px !important; }}
h2 {{ font-size: {cfg.page.font_size_h2}px !important; }}
h3 {{ font-size: {cfg.page.font_size_h3}px !important; }}
h4 {{ font-size: {cfg.page.font_size_h4}px !important; }}

/* paragraph spacing */
p {{
    margin-bottom: {cfg.page.paragraph_spacing}px;
}}

.chapter {{
    margin-bottom: {cfg.page.section_spacing}px;
}}

/* KPICard Optimization - Prevent Overflow */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    grid-auto-rows: minmax(auto, 1fr);
    grid-auto-flow: row dense;
    gap: {cfg.grid.gap}px;
    margin: 20px 0;
    align-items: stretch;
}}

.kpi-grid .kpi-card {{
    grid-column: span 2;
}}

/* Single/Double/Three special columns */
.chapter .kpi-grid[data-kpi-count="1"] {{
    grid-template-columns: repeat(1, minmax(0, 1fr));
    grid-auto-flow: row;
}}
.chapter .kpi-grid[data-kpi-count="1"] .kpi-card {{
    grid-column: span 1;
}}
.chapter .kpi-grid[data-kpi-count="2"] {{
    grid-template-columns: repeat(4, minmax(0, 1fr));
}}
.chapter .kpi-grid[data-kpi-count="2"] .kpi-card {{
    grid-column: span 2;
}}
.chapter .kpi-grid[data-kpi-count="3"] {{
    grid-template-columns: repeat(6, minmax(0, 1fr));
}}

/* Use 2x2 arrangement for four strips */
.chapter .kpi-grid[data-kpi-count="4"] {{
    grid-template-columns: repeat(4, minmax(0, 1fr));
}}
.chapter .kpi-grid[data-kpi-count="4"] .kpi-card {{
    grid-column: span 2;
}}

/* Five or more lines default to three columns (6 grids, each card occupies2） */
.chapter .kpi-grid[data-kpi-count="5"],
.chapter .kpi-grid[data-kpi-count="6"],
.chapter .kpi-grid[data-kpi-count="7"],
.chapter .kpi-grid[data-kpi-count="8"],
.chapter .kpi-grid[data-kpi-count="9"],
.chapter .kpi-grid[data-kpi-count="10"],
.chapter .kpi-grid[data-kpi-count="11"],
.chapter .kpi-grid[data-kpi-count="12"],
.chapter .kpi-grid[data-kpi-count="13"],
.chapter .kpi-grid[data-kpi-count="14"],
.chapter .kpi-grid[data-kpi-count="15"],
.chapter .kpi-grid[data-kpi-count="16"] {{
    grid-template-columns: repeat(6, minmax(0, 1fr));
}}

/* When the remainder is 2, the last two pictures equally divide the full width. */
.chapter .kpi-grid[data-kpi-count="5"] .kpi-card:nth-last-child(-n+2),
.chapter .kpi-grid[data-kpi-count="8"] .kpi-card:nth-last-child(-n+2),
.chapter .kpi-grid[data-kpi-count="11"] .kpi-card:nth-last-child(-n+2),
.chapter .kpi-grid[data-kpi-count="14"] .kpi-card:nth-last-child(-n+2) {{
    grid-column: span 3;
}}

/* When the remainder is 1, the last picture occupies the full width */
.chapter .kpi-grid[data-kpi-count="7"] .kpi-card:last-child,
.chapter .kpi-grid[data-kpi-count="10"] .kpi-card:last-child,
.chapter .kpi-grid[data-kpi-count="13"] .kpi-card:last-child,
.chapter .kpi-grid[data-kpi-count="16"] .kpi-card:last-child {{
    grid-column: 1 / -1;
}}

.kpi-card {{
    padding: {cfg.kpi_card.padding}px !important;
    min-height: {cfg.kpi_card.min_height}px;
    break-inside: avoid;
    page-break-inside: avoid;
    box-sizing: border-box;
    max-width: 100%;
    height: auto;
    display: flex;
    flex-direction: column;
    align-items: stretch !important;
    gap: 8px;
}}

.kpi-card .kpi-value {{
    font-size: {body_kpi_value}px !important;
    line-height: 1.25;
    white-space: nowrap;
    width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    display: flex;
    flex-wrap: nowrap;
    align-items: baseline;
    gap: 4px 6px;
}}
.kpi-card .kpi-value small {{
    font-size: 0.65em;
    white-space: nowrap;
    align-self: baseline;
}}
.kpi-card .kpi-label {{
    font-size: {body_kpi_label}px !important;
    word-break: break-word;
    overflow-wrap: break-word;
    max-width: 100%;
    line-height: 1.35;
}}

.kpi-card .change,
.kpi-card .delta {{
    font-size: {body_kpi_delta}px !important;
    word-break: break-word;
    overflow-wrap: break-word;
    line-height: 1.3;
}}

/* Prompt box optimization - prevent overflow */
.callout {{
    padding: {cfg.callout.padding}px !important;
    margin: 20px 0;
    line-height: {cfg.callout.line_height};
    font-size: {body_callout_content}px !important;
    break-inside: avoid;
    page-break-inside: avoid;
    /* Prevent overflow */
    overflow: hidden;
    box-sizing: border-box;
    max-width: 100%;
}}

.callout-title {{
    font-size: {body_callout_title}px !important;
    margin-bottom: 10px;
    word-break: break-word;
    line-height: 1.4;
}}

.callout-content {{
    font-size: {body_callout_content}px !important;
    word-break: break-word;
    overflow-wrap: break-word;
    line-height: {cfg.callout.line_height};
}}

.callout strong {{
    font-size: {body_callout_title}px !important;
}}

.callout p,
.callout li,
.callout table,
.callout td,
.callout th {{
    font-size: {body_callout_content}px !important;
}}

/* Ensure that the last element inside the callout does not overflow the bottom */
.callout > *:last-child,
.callout > *:last-child > *:last-child {{
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}}

/* Table optimization - Strictly prevent overflow */
table {{
    width: 100%;
    break-inside: avoid;
    page-break-inside: avoid;
    /* Table layout fixed */
    table-layout: fixed;
    max-width: 100%;
    overflow: hidden;
}}

th {{
    font-size: {body_table_header}px !important;
    padding: {cfg.table.cell_padding}px !important;
    /* Header text control */
    word-break: break-word;
    overflow-wrap: break-word;
    hyphens: auto;
    max-width: 100%;
}}

td {{
    font-size: {body_table_body}px !important;
    padding: {cfg.table.cell_padding}px !important;
    max-width: {cfg.table.max_cell_width}px;
    /* Force line breaks to prevent overflow */
    word-wrap: break-word;
    overflow-wrap: break-word;
    word-break: break-word;
    hyphens: auto;
    white-space: normal;
}}

/* Chart optimization */
.chart-card {{
    min-height: {cfg.chart.min_height}px;
    max-height: {cfg.chart.max_height}px;
    padding: {cfg.chart.padding}px;
    break-inside: avoid;
    page-break-inside: avoid;
    /* Prevent chart overflow */
    overflow: hidden;
    max-width: 100%;
    box-sizing: border-box;
}}

.chart-title {{
    font-size: {body_chart_title}px !important;
    word-break: break-word;
}}

/* HeroRegional merged version - Remove the large color blocks and present the article overview in a card-like arrangement on the first screen */
.hero-section-combined {{
    padding: 38px 44px !important;
    margin: 0 auto 34px auto !important;
    min-height: 420px;
    width: 100% !important;
    max-width: 100% !important;
    box-sizing: border-box;
    overflow: visible;
    border-radius: 26px !important;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    box-shadow: 0 18px 44px rgba(15, 23, 42, 0.06);
    page-break-after: always !important;
    page-break-inside: avoid;
}}

/* Herotitle area */
.hero-header {{
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    row-gap: 6px;
    margin-bottom: 22px;
    padding-bottom: 16px;
    border-bottom: 1px solid #eef1f5;
    text-align: left;
}}

.hero-hint {{
    font-size: {max(cfg.page.font_size_base - 2, 11)}px !important;
    color: #556070;
    margin: 0;
    font-weight: 600;
    letter-spacing: 0.04em;
}}

.hero-title {{
    font-size: {max(cfg.page.font_size_base + 5, 19)}px !important;
    font-weight: 700;
    margin: 0;
    color: #0f172a;
    line-height: 1.25;
    letter-spacing: -0.01em;
}}

.hero-subtitle {{
    font-size: {max(cfg.page.font_size_base - 1, 12)}px !important;
    color: #475467;
    margin: 2px 0 0 0;
    font-weight: 500;
}}

/* HeroMain area - grid columns */
.hero-body {{
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
    gap: 22px 28px;
    align-items: flex-start;
    align-content: start;
}}

/* Summary/Highlights on the left */
.hero-content {{
    display: grid;
    gap: 14px;
    min-width: 0;
    align-content: start;
}}

/* KPI area on the right */
.hero-side {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: {max(cfg.grid.gap - 2, 10)}px;
    overflow: hidden;
    box-sizing: border-box;
    width: 100%;
    min-width: 0;
    min-height: 0;
    align-content: flex-start;
}}

/* HeroRegional KPI cards */
.hero-kpi {{
    background: #fdfdfd;
    border-radius: 14px !important;
    border: 1px solid #e5e7eb;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.08);
    padding: 14px 16px !important;
    overflow: hidden;
    box-sizing: border-box;
    min-height: 110px;
    display: flex;
    flex-direction: column;
    gap: 6px;
}}

.hero-kpi .label {{
    font-size: {overview_kpi_label}px !important;
    word-break: break-word;
    max-width: 100%;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    color: #556070;
}}

.hero-kpi .value {{
    font-size: {overview_kpi_value}px !important;
    white-space: nowrap;
    width: 100%;
    max-width: 100%;
    line-height: 1.1;
    display: block;
    hyphens: auto;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 2px;
    color: #0f172a;
}}

.hero-kpi .delta {{
    font-size: {overview_kpi_delta}px !important;
    word-break: break-word;
    margin-top: 2px;
    display: block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2;
}}

/* Hero summarytext */
.hero-summary {{
    font-size: {overview_summary_font}px !important;
    line-height: 1.65;
    margin: 0 0 12px 0;
    padding: 0;
    word-break: break-word;
    overflow-wrap: break-word;
    white-space: normal;
    width: 100%;
    box-sizing: border-box;
    align-self: start;
    background: transparent;
    border: none;
    border-radius: 0;
    box-shadow: none;
}}

/* Hero highlightsList - grid layout */
.hero-highlights {{
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px 12px;
}}

.hero-highlights li {{
    margin: 0;
    max-width: 100%;
    flex-shrink: 0;
    flex-grow: 0;
}}

/* hero highlightsinbadge - small card items */
.hero-highlights .badge {{
    font-size: {overview_badge_font}px !important;
    padding: 10px 12px !important;
    max-width: 100%;
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    flex-wrap: wrap;
    word-wrap: break-word;
    white-space: normal;
    overflow: hidden;
    text-overflow: ellipsis;
    box-sizing: border-box;
    line-height: 1.5;
    min-height: 40px;
    background: #f3f4f6 !important;
    border-radius: 12px !important;
    border: 1px solid #e5e7eb;
    color: #111827;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
    align-items: flex-start;
    justify-content: flex-start;
}}

/* Hero actionsbutton - PDFShown as wireframe label style in */
.hero-actions {{
    margin-top: 14px;
    display: flex !important;
    flex-wrap: wrap;
    gap: 8px;
    max-width: 100%;
    overflow: visible;
    padding: 0;
}}

.hero-actions button,
.hero-actions .ghost-btn {{
    font-size: {max(cfg.page.font_size_base - 2, 11)}px !important;
    padding: 5px 10px !important;
    max-width: 100%;
    word-break: break-word;
    white-space: normal;
    overflow: visible;
    box-sizing: border-box;
    background: none !important;
    background-color: #f3f4f6 !important;
    background-image: none !important;
    border: none !important;
    border-width: 0 !important;
    border-style: none !important;
    border-radius: 999px !important;
    color: #222 !important;
    line-height: 1.5;
    display: inline-flex !important;
    align-items: center;
    justify-content: flex-start;
    outline: none !important;
    -webkit-appearance: none !important;
    appearance: none !important;
    box-shadow: none !important;
}}

/* Prevent titles from being orphaned */
h1, h2, h3, h4, h5, h6 {{
    break-after: avoid;
    page-break-after: avoid;
    word-break: break-word;
    overflow-wrap: break-word;
}}

/* ===== Force page separation rules ===== */

/* Directory section forces starting a new page and forces paging after that */
.toc-section {{
    page-break-before: always !important;
    page-break-after: always !important;
}}

/* The first chapter is forced to start a new page (the text starts from the third page） */
main > .chapter:first-of-type {{
    page-break-before: always !important;
}}

/* Ensure content blocks are not paginated and do not overflow */
.content-block {{
    break-inside: avoid;
    page-break-inside: avoid;
    overflow: hidden;
    max-width: 100%;
}}

/* Global overflow protection */
* {{
    box-sizing: border-box;
    max-width: 100%;
}}

/* Special control over numbers and long words */
.kpi-value, .value, .delta {{
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;  /* Tighten spacing slightly to save space */
}}

/* Color block (badge) style control - Prevent oversize */
.badge {{
    display: inline-block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: normal;
    /* Limit the maximum size of the badge */
    padding: 4px 12px !important;
    font-size: {body_badge_font}px !important;
    line-height: 1.4 !important;
    /* Prevent the badge from being abnormally large */
    word-break: break-word;
    hyphens: auto;
}}

/* Make sure the callout is not too large */
.callout {{
    max-width: 100% !important;
    margin: 16px 0 !important;
    padding: {cfg.callout.padding}px !important;
    box-sizing: border-box;
    overflow: hidden;
}}

/* Responsive adjustments */
@media print {{
    /* Tighter control when printing */
    * {{
        overflow: visible !important;
        max-width: 100% !important;
    }}

    .kpi-card, .callout, .chart-card {{
        overflow: hidden !important;
    }}
}}
"""

        return css


__all__ = [
    'PDFLayoutOptimizer',
    'PDFLayoutConfig',
    'PageLayout',
    'KPICardLayout',
    'CalloutLayout',
    'TableLayout',
    'ChartLayout',
    'GridLayout',
    'DataBlockLayout',
]
