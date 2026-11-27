"""
Chapter length planning nodes。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List

from loguru import logger

from ..core import TemplateSection
from ..prompts import (
    SYSTEM_PROMPT_WORD_BUDGET,
    build_word_budget_prompt,
)
from ..utils.json_parser import RobustJSONParser, JSONParseError
from .base_node import BaseNode



@dataclass
class WordBudgetContext:
    sections: List[TemplateSection]
    design: Dict[str, Any]
    reports: Dict[str, str]
    forum_logs: str
    query: str
    template_overview: Dict[str, Any] | None = None

class WordBudgetNode(BaseNode):
    """
    Plan the word count and focus of each chapter.

    Total number of words output、Global Writing Guidelines and Each Chapter/of small sections target/min/max word count constraint。
    """

    def __init__(self, llm_client):
        """Only LLM client references are recorded to facilitate requests initiated during the run phase."""
        super().__init__(llm_client, "WordBudgetNode")

        self.json_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
            max_repair_attempts=3,
        )

    def run(self, context: WordBudgetContext) -> Dict[str, Any]:
        """
        Plan the word count of chapters based on the design draft and all materials, so that LLM has clear length goals when writing.

        parameter:
            sections: Template chapter list。
            design: Design draft returned by layout node（title/toc/herowait）。
            reports: Three-engine report mapping。
            forum_logs: Forum log original text。
            query: User query words。
            template_overview: Optional template overview with chapter meta-information.

        return:
            dict: Chapter length planning results, including `totalWords`、`globalGuidelines` with chapter by chapter `chapters`。
        """

        payload = {
            "query": context.query,
            "design": context.design,
            "sections": [section.to_dict() for section in context.sections],
            "templateOverview": context.template_overview
            or {
                "title": context.sections[0].title if context.sections else "",
                "chapters": [section.to_dict() for section in context.sections],
            },
            "reports": context.reports,
            "forumLogs": context.forum_logs,
        }
        user = build_word_budget_prompt(payload)
        response = self.llm_client.stream_invoke_to_string(
            SYSTEM_PROMPT_WORD_BUDGET,
            user,
            temperature=0.25,
            top_p=0.85,
        )
        plan = self._parse_response(response)
        logger.info("Chapter word count plan has been generated")
        return plan

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """
        Convert the JSON text output by LLM into a dictionary, and prompt a planning exception when it fails.

        Multiple repair attempts using a robust JSON parser：
        1. Clean up markdown markup and reflection content
        2. Local syntax fixes (bracket balancing、comma completion、Control character escaping, etc.）
        3. Advanced repair using json_repair library
        4. Optional LLM-assisted repair

        parameters:
            raw: LLMReturn value, which may contain```pack、Think content, etc.

        return:
            dict: Legal length planning JSON.

        abnormal:
            ValueError: Thrown when the response is empty or JSON parsing fails。
        """
        try:
            result = self.json_parser.parse(
                raw,
                context_name="Space planning",
                expected_keys=["totalWords", "globalGuidelines", "chapters"],
            )

            if not isinstance(result.get("totalWords"), (int, float)):
                logger.warning("The totalWords field in the space plan is missing or the type is wrong. Use the default value.")
                result.setdefault("totalWords", 10000)
            if not isinstance(result.get("globalGuidelines"), list):
                logger.warning("The globalGuidelines field is missing or the type is wrong in the space plan, and an empty list is used.")
                result.setdefault("globalGuidelines", [])
            if not isinstance(result.get("chapters"), (list, dict)):
                logger.warning("The chapters field is missing or the type is wrong in the space plan, and an empty list is used.")
                result.setdefault("chapters", [])
            return result
        except JSONParseError as exc:

            raise ValueError(f"Space planning JSON parsing failed: {exc}") from exc


__all__ = ["WordBudgetNode", "WordBudgetContext"]
