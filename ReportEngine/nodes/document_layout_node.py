"""
Generate the title of the entire report based on the template directory and multi-source reports/Table of contents/theme design。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from loguru import logger

from ..core import TemplateSection
from ..prompts import (
    SYSTEM_PROMPT_DOCUMENT_LAYOUT,
    build_document_layout_prompt,
)
from ..utils.json_parser import RobustJSONParser, JSONParseError
from .base_node import BaseNode



@dataclass
class DocumentLayoutContext:
    sections: List[TemplateSection]
    template_markdown: str
    reports: Dict[str, str]
    forum_logs: str
    query: str
    template_overview: Dict[str, Any] | None = None

class DocumentLayoutNode(BaseNode):
    """
    Responsible for generating global titles、Catalog and Hero design.

    Combine template slicing、Report summaries and forum discussions guide the visual and structural tone of the entire book.。
    """

    def __init__(self, llm_client):
        """Record the LLM client and set the node name for BaseNode log use"""
        super().__init__(llm_client, "DocumentLayoutNode")

        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
            max_repair_attempts=3,
        )

    def run(self, context: DocumentLayoutContext) -> Dict[str, Any]:
        """
        Comprehensive template+Multi-source content, generate the title of the entire book、Directory structure and theme swatches.

        parameter:
            context: DocumentLayoutContext containing the necessary context.

        return:
            dict: Include title/subtitle/toc/hero/themeTokens Dictionary of design information。
        """

        payload = {
            "query": context.query,
            "template": {
                "raw": context.template_markdown,
                "sections": [section.to_dict() for section in context.sections],
            },
            "templateOverview": context.template_overview
            or {
                "title": context.sections[0].title if context.sections else "",
                "chapters": [section.to_dict() for section in context.sections],
            },
            "reports": context.reports,
            "forumLogs": context.forum_logs,
        }

        user_message = build_document_layout_prompt(payload)
        response = self.llm_client.stream_invoke_to_string(
            SYSTEM_PROMPT_DOCUMENT_LAYOUT,
            user_message,
            temperature=0.3,
            top_p=0.9,
        )
        design = self._parse_response(response)
        logger.info("Document title/TOC design generated")
        return design

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """
        Parse the JSON text returned by LLM and throw a friendly error if it fails.

        Multiple repair attempts using a robust JSON parser：
        1. Clean up markdown markup and reflection content
        2. Local syntax fixes (bracket balancing、comma completion、Control character escaping, etc.）
        3. Advanced repair using json_repair library
        4. Optional LLM-assisted repair

        parameters:
            raw: LLMOriginal return string, allowed with```pack、Think content, etc.

        return:
            dict: Structured design draft.

        abnormal:
            ValueError: Thrown when the response is empty or JSON parsing fails。
        """
        try:
            result = self.json_parser.parse(
                raw,
                context_name="Document design",

                expected_keys=["title", "tocPlan", "hero"],
            )

            if not isinstance(result.get("title"), str):
                logger.warning("Document design missing title field or type error, using default")
                result.setdefault("title", "Unnamed Report")


            toc_plan = result.get("tocPlan", [])
            if not isinstance(toc_plan, list):
                logger.warning("Document design missing tocPlan field or type error, using empty list")
                result["tocPlan"] = []
            else:

                result["tocPlan"] = self._clean_toc_plan_descriptions(toc_plan)

            if not isinstance(result.get("hero"), dict):
                logger.warning("Document design missing hero field or type error, using empty object")
                result.setdefault("hero", {})

            return result
        except JSONParseError as exc:

            raise ValueError(f"Document design JSON parsing failed: {exc}") from exc

    def _clean_toc_plan_descriptions(self, toc_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Clean the description field of each entry in tocPlan, removing possible JSON fragments.

        parameter:
            toc_plan: Original directory plan listing

        Return:
            List[Dict[str, Any]]: Cleaned directory plan list
        """
        import re

        def clean_text(text: Any) -> str:
            """Cleaning JSON fragments from text"""
            if not text or not isinstance(text, str):
                return ""

            cleaned = text


            cleaned = re.sub(r',\s*\{[^}]*$', '', cleaned)


            cleaned = re.sub(r',\s*\[[^\]]*$', '', cleaned)


            open_brace_pos = cleaned.rfind('{')
            if open_brace_pos != -1:
                close_brace_pos = cleaned.rfind('}')
                if close_brace_pos < open_brace_pos:
                    cleaned = cleaned[:open_brace_pos].rstrip(',，、 \t\n')


            open_bracket_pos = cleaned.rfind('[')
            if open_bracket_pos != -1:
                close_bracket_pos = cleaned.rfind(']')
                if close_bracket_pos < open_bracket_pos:
                    cleaned = cleaned[:open_bracket_pos].rstrip(',，、 \t\n')


            cleaned = re.sub(r',?\s*"[^"]+"\s*:\s*"[^"]*$', '', cleaned)
            cleaned = re.sub(r',?\s*"[^"]+"\s*:\s*[^,}\]]*$', '', cleaned)


            cleaned = cleaned.rstrip(',，、 \t\n')

            return cleaned.strip()

        cleaned_plan = []
        for entry in toc_plan:
            if not isinstance(entry, dict):
                continue


            if "description" in entry:
                original_desc = entry["description"]
                cleaned_desc = clean_text(original_desc)

                if cleaned_desc != original_desc:
                    logger.warning(
                        f"Clean directory entries '{entry.get('display', 'unknown')}' JSON fragment in the description field:\n"
                        f"  original: {original_desc[:100]}...\n"
                        f"  After cleaning: {cleaned_desc[:100]}..."
                    )
                    entry["description"] = cleaned_desc

            cleaned_plan.append(entry)

        return cleaned_plan


__all__ = ["DocumentLayoutNode", "DocumentLayoutContext"]
