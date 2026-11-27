"""
Chapter-level JSON generation node.

Each chapter independently calls LLM based on the Markdown template slice and writes the Raw file in a streaming manner.
After completion, verify and download the standardized JSON. This node is only responsible for "getting the compliance chapter”。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple, Callable, Optional, Set

from loguru import logger

from ..core import TemplateSection, ChapterStorage
from ..ir import (
    ALLOWED_BLOCK_TYPES,
    ALLOWED_INLINE_MARKS,
    ENGINE_AGENT_TITLES,
    IRValidator,
)
from ..prompts import (
    SYSTEM_PROMPT_CHAPTER_JSON,
    SYSTEM_PROMPT_CHAPTER_JSON_REPAIR,
    SYSTEM_PROMPT_CHAPTER_JSON_RECOVERY,
    build_chapter_repair_prompt,
    build_chapter_recovery_payload,
    build_chapter_user_prompt,
)
from ..utils.json_parser import RobustJSONParser, JSONParseError
from .base_node import BaseNode

try:
    from json_repair import repair_json as _json_repair_fn
except ImportError:
    _json_repair_fn = None


class ChapterJsonParseError(ValueError):
    """Chapter: Exception thrown when LLM output cannot be parsed into legal JSON. The original text is attached for easy troubleshooting.。"""

    def __init__(self, message: str, raw_text: Optional[str] = None):
        """
        Construct exceptions and attach raw output for easy locating in logs。

        Args:
            message: Human-readable error description。
            raw_text: Full LLM output of triggered exception。
        """
        super().__init__(message)
        self.raw_text = raw_text


class ChapterContentError(ValueError):
    """
    Chapter content is unusually sparse.

    Triggered when LLM only outputs a title or the text is not enough to support a chapter, the driver retries to ensure report quality.。
    """

    def __init__(
        self,
        message: str,
        chapter: Optional[Dict[str, Any]] = None,
        body_characters: int = 0,
        narrative_characters: int = 0,
        non_heading_blocks: int = 0,
    ):
        """Save the text characteristics of this exception for reference for retry and cover-up strategies。"""
        super().__init__(message)
        self.chapter_payload: Optional[Dict[str, Any]] = chapter
        self.body_characters: int = int(body_characters or 0)
        self.narrative_characters: int = int(narrative_characters or 0)
        self.non_heading_blocks: int = int(non_heading_blocks or 0)


class ChapterValidationError(ValueError):
    """
    Thrown when the chapter structure still fails to pass verification after local and LLM repairs.

    This exception is used to trigger a retry at the Agent layer for a single chapter without restarting the entire report.。
    """

    def __init__(self, message: str, errors: Optional[List[str]] | None = None):
        super().__init__(message)
        self.errors: List[str] = list(errors or [])


class ChapterGenerationNode(BaseNode):
    """
    Responsible for calling LLM by chapter and verifying the JSON structure.

    core competencies：
        - Construct chapter-level payload and prompt words；
        - Write raw files in streaming form and pass through delta；
        - try to fix/Parse LLM output and use IRValidator to verify；
        - Make fault-tolerant repairs to the block structure to ensure that the final JSON can be rendered。
    """

    _COLON_EQUALS_PATTERN = re.compile(r'(":\s*)=')
    _LINE_BREAK_SENTINEL = "__LINE_BREAK__"
    _INLINE_MARK_ALIASES = {
        "strong": "bold",
        "b": "bold",
        "em": "italic",
        "emphasis": "italic",
        "i": "italic",
        "u": "underline",
        "strike-through": "strike",
        "strikethrough": "strike",
        "s": "strike",
        "codeblock": "code",
        "monospace": "code",
        "hyperlink": "link",
        "url": "link",
        "colour": "color",
        "textcolor": "color",
        "bgcolor": "highlight",
        "background": "highlight",
        "highlightcolor": "highlight",
        "sub": "subscript",
        "sup": "superscript",
    }

    _MIN_NON_HEADING_BLOCKS = 2
    _MIN_BODY_CHARACTERS = 600
    _MIN_NARRATIVE_CHARACTERS = 300
    _PARAGRAPH_FRAGMENT_MAX_CHARS = 80
    _PARAGRAPH_FRAGMENT_NO_TERMINATOR_MAX_CHARS = 240
    _TERMINATION_PUNCTUATION = set("。！？!?；;……")

    def __init__(
        self,
        llm_client,
        validator: IRValidator,
        storage: ChapterStorage,
        fallback_llm_clients: Optional[List[Tuple[str, Any]]] = None,
        error_log_dir: Optional[str | Path] = None,
    ):
        """
        Logging LLM Client/validator/Chapter memory to facilitate run method scheduling。

        Args:
            llm_client: The client that actually calls the large model
            validator: IRstructure validator
            storage: The storage responsible for streaming chapters to disk
        """
        super().__init__(llm_client, "ChapterGenerationNode")
        self.validator = validator
        self.storage = storage
        self.fallback_llm_clients: List[Tuple[str, Any]] = fallback_llm_clients or [
            ("report_engine", llm_client)
        ]
        error_dir = Path(error_log_dir or "logs/json_repair_failures")
        error_dir.mkdir(parents=True, exist_ok=True)
        self.error_log_dir = error_dir
        self._failed_block_counter = 0
        self._active_run_id: Optional[str] = None
        self._rescue_attempted_labels: Dict[str, Set[str]] = {}
        self._skipped_fallback_chapters: Set[str] = set()
        self._archived_failed_json: Dict[str, str] = {}

        self._robust_parser = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
        )

    def run(
        self,
        section: TemplateSection,
        context: Dict[str, Any],
        run_dir: Path,
        stream_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Call LLM for a single chapter to verify/Download chapter JSON and return structured results.

        parameter:
            section: Chapter object generated by template slicing, including title/order/slug。
            context: AgentConstructed shared context (topic、space、Layout etc.）。
            run_dir: Chapter save directory, by `ChapterStorage.start_session` return。
            stream_callback: Optional streaming callback to push LLM delta to the front end。
            **kwargs: Transparent temperature、top_pand other sampling parameters.

        return:
            dict: Chapter JSON that passes IR verification.

        abnormal:
            ChapterJsonParseError: After multiple attempts, it still cannot be parsed.JSON。
            ChapterContentError: The text density is insufficient or there is only a title, and a retry needs to be triggered.。
        """
        chapter_meta = {
            "chapterId": section.chapter_id,
            "slug": section.slug,
            "title": section.title,
            "order": section.order,
        }
        chapter_dir = self.storage.begin_chapter(run_dir, chapter_meta)
        run_id = run_dir.name
        self._ensure_run_state(run_id)
        llm_payload = self._build_payload(section, context)
        user_message = build_chapter_user_prompt(llm_payload)

        raw_text = self._stream_llm(
            user_message,
            chapter_dir,
            stream_callback=stream_callback,
            section_meta=chapter_meta,
            **kwargs,
        )
        parse_context: List[str] = []
        fallback_created = False
        try:
            chapter_json = self._parse_chapter(raw_text)
        except ChapterJsonParseError as parse_error:
            logger.warning(f"{section.title} Chapter JSON parsing failed, try cross-engine repair: {parse_error}")
            parse_context.append(str(parse_error))
            self._archive_failed_output(section, raw_text)
            recovered = self._attempt_cross_engine_json_rescue(
                section,
                llm_payload,
                raw_text,
                run_id,
            )
            if recovered:
                chapter_json = recovered
                logger.info(f"{section.title} Chapter JSON has been fixed by cross-engine")
            else:
                fallback = self._build_fallback_chapter(section, raw_text, parse_error)
                if not fallback:
                    raise
                chapter_json, fallback_notes = fallback
                parse_context.extend(fallback_notes)
                fallback_created = True


        chapter_json.setdefault("chapterId", section.chapter_id)
        chapter_json.setdefault("anchor", section.slug)
        chapter_json.setdefault("title", section.title)
        chapter_json.setdefault("order", section.order)
        self._sanitize_chapter_blocks(chapter_json)

        valid, errors = self.validator.validate_chapter(chapter_json)
        if not valid and errors:
            repaired = self._attempt_llm_structural_repair(
                chapter_json,
                errors,
                raw_text=raw_text,
            )
            if repaired:
                chapter_json = repaired
                chapter_json.setdefault("chapterId", section.chapter_id)
                chapter_json.setdefault("anchor", section.slug)
                chapter_json.setdefault("title", section.title)
                chapter_json.setdefault("order", section.order)
                self._sanitize_chapter_blocks(chapter_json)
                valid, errors = self.validator.validate_chapter(chapter_json)
        content_error: ChapterContentError | None = None
        if valid and not fallback_created:
            try:
                self._ensure_content_density(chapter_json)
            except ChapterContentError as exc:
                content_error = exc

        error_messages: List[str] = parse_context.copy()
        if not valid and errors:
            error_messages.extend(errors)
        if content_error:
            error_messages.append(str(content_error))

        self.storage.persist_chapter(
            run_dir,
            chapter_meta,
            chapter_json,
            errors=None if not error_messages else error_messages,
        )

        if not valid:
            raise ChapterValidationError(
                f"{section.title} Chapter JSON verification failed: {'; '.join(errors[:5])}",
                errors=errors,
            )
        if content_error:
            raise content_error

        return chapter_json



    def _build_payload(self, section: TemplateSection, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Construct LLM input payload.

        parameter:
            section: The current chapter to be generated, providing a title/serial number/outline。
            context: Global context dictionary, containing topics、tri-engine report、Space planning, etc.

        return:
            dict: It can be directly serialized into the payload of the prompt word, taking into account chapter information and global constraints.。
        """
        reports = context.get("reports", {})

        chapter_plan_map = context.get("chapter_directives", {})
        chapter_plan = chapter_plan_map.get(section.chapter_id) if chapter_plan_map else {}


        allow_swot = self._get_chapter_swot_permission(section.chapter_id, context)
        allow_pest = self._get_chapter_pest_permission(section.chapter_id, context)

        payload = {
            "section": {
                "chapterId": section.chapter_id,
                "title": section.title,
                "slug": section.slug,
                "order": section.order,
                "number": section.number,
                "outline": section.outline,
            },
            "globalContext": {
                "query": context.get("query"),
                "templateName": context.get("template_name"),
                "themeTokens": context.get("theme_tokens", {}),
                "styleDirectives": context.get("style_directives", {}),

                "layout": context.get("layout"),
                "templateOverview": context.get("template_overview", {}),
            },
            "reports": {
                "query_engine": reports.get("query_engine", ""),
                "media_engine": reports.get("media_engine", ""),
                "insight_engine": reports.get("insight_engine", ""),
            },
            "forumLogs": context.get("forum_logs", ""),
            "dataBundles": context.get("data_bundles", []),
            "constraints": {
                "language": "zh-CN",
                "maxTokens": context.get("max_tokens", 4096),
                "allowedBlocks": ALLOWED_BLOCK_TYPES,
                "allowSwot": allow_swot,
                "allowPest": allow_pest,
                "styleHints": {
                    "expectWidgets": True,
                    "forceHeadingAnchors": True,
                    "allowInlineMix": True,
                },
            },
            "chapterPlan": chapter_plan,
            "wordPlan": context.get("word_plan"),
        }
        if chapter_plan:
            constraints = payload["constraints"]
            if chapter_plan.get("targetWords"):
                constraints["wordTarget"] = chapter_plan["targetWords"]
            if chapter_plan.get("minWords"):
                constraints["minWords"] = chapter_plan["minWords"]
            if chapter_plan.get("maxWords"):
                constraints["maxWords"] = chapter_plan["maxWords"]
            if chapter_plan.get("emphasis"):
                constraints["emphasis"] = chapter_plan["emphasis"]
            if chapter_plan.get("sections"):
                constraints["sectionBudgets"] = chapter_plan["sections"]
                payload["globalContext"]["sectionBudgets"] = chapter_plan["sections"]
        return payload

    def _get_chapter_swot_permission(self, chapter_id: str, context: Dict[str, Any]) -> bool:
        """
        Finds whether the SWOT block is allowed in the specified chapter from the layout's tocPlan.

        The SWOT block is allowed in no more than one chapter of the entire text, as specified in the tocPlan during the document design phase.
        Marked via the allowSwot field.

        parameter:
            chapter_id: Current chapterID。
            context: Global context dictionary.

        return:
            bool: Returns True if SWOT blocks are allowed in this chapter, otherwise False。
        """
        layout = context.get("layout")
        if not isinstance(layout, dict):
            return False

        toc_plan = layout.get("tocPlan")
        if not isinstance(toc_plan, list):
            return False

        for entry in toc_plan:
            if not isinstance(entry, dict):
                continue
            if entry.get("chapterId") == chapter_id:
                return bool(entry.get("allowSwot", False))

        return False

    def _get_chapter_pest_permission(self, chapter_id: str, context: Dict[str, Any]) -> bool:
        """
        Finds whether PEST blocks are allowed in the specified chapter from the layout's tocPlan.

        PEST blocks are allowed in at most one chapter of the full text, as determined by the document design phase in tocPlan
        Marked via the allowPest field.

        PEST blocks for macro-environmental analysis：
        - Political（political factors）
        - Economic（economic factors）
        - Social（social factors）
        - Technological（technical factors)

        parameters:
            chapter_id: Current chapterID。
            context: Global context dictionary.

        return:
            bool: Returns True if this section allows PEST blocks, otherwise False。
        """
        layout = context.get("layout")
        if not isinstance(layout, dict):
            return False

        toc_plan = layout.get("tocPlan")
        if not isinstance(toc_plan, list):
            return False

        for entry in toc_plan:
            if not isinstance(entry, dict):
                continue
            if entry.get("chapterId") == chapter_id:
                return bool(entry.get("allowPest", False))

        return False

    def _stream_llm(
        self,
        user_message: str,
        chapter_dir: Path,
        stream_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        section_meta: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> str:
        """
        Streaming calls LLM and writes raw files in real time, while throwing delta through callbacks.

        parameter:
            user_message: Assembled user prompt words。
            chapter_dir: The local cache directory of chapters, used for storage stream.raw。
            stream_callback: SSEStreaming push callback function。
            section_meta: accompanying chaptersID/Title, used for callbackspayload。
            **kwargs: Transparent temperature、top_pand other parameters.

        return:
            str: The original text after concatenating all delta。
        """
        chunks: List[str] = []
        with self.storage.capture_stream(chapter_dir) as stream_fp:
            stream = self.llm_client.stream_invoke(
                SYSTEM_PROMPT_CHAPTER_JSON,
                user_message,
                temperature=kwargs.get("temperature", 0.2),
                top_p=kwargs.get("top_p", 0.95),
            )
            for delta in stream:
                stream_fp.write(delta)
                chunks.append(delta)
                if stream_callback:
                    meta = section_meta or {}
                    try:
                        stream_callback(delta, meta)
                    except Exception as callback_error:
                        logger.warning(f"Chapter streaming callback failed: {callback_error}")
        return "".join(chunks)

    def _attempt_cross_engine_json_rescue(
        self,
        section: TemplateSection,
        generation_payload: Dict[str, Any],
        raw_text: str,
        run_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Called in sequenceReport/Forum/Insight/MediaFour sets of APIs try to fix unresolvedJSON。

        Returns:
            dict | None: Returns chapter JSON when repaired successfully, otherwiseNone。
        """
        if not self.fallback_llm_clients:
            return None
        if self._chapter_already_skipped(section):
            logger.info(f"[{run_id}] {section.title} Marked as handled by fallback and no longer triggers cross-engine fixes")
            return None
        section_payload = {
            "chapterId": section.chapter_id,
            "title": section.title,
            "slug": section.slug,
            "order": section.order,
            "number": section.number,
            "outline": section.outline,
        }
        repair_prompt = build_chapter_recovery_payload(
            section_payload,
            generation_payload,
            raw_text,
        )
        attempted_labels = self._rescue_attempted_labels.setdefault(section.chapter_id, set())
        for label, client in self.fallback_llm_clients:
            if label in attempted_labels:
                continue
            attempt_index = len(attempted_labels) + 1
            attempted_labels.add(label)
            logger.info(
                f"[{run_id}] chapter {section.title} trigger {label} API JSONEmergency repair (No.{attempt_index}attempts）"
            )
            try:
                response = client.invoke(
                    SYSTEM_PROMPT_CHAPTER_JSON_RECOVERY,
                    repair_prompt,
                    temperature=0.0,
                    top_p=0.05,
                )
            except Exception as exc:
                logger.warning(f"{label} JSONRepair call failed: {exc}")
                continue
            if not response:
                continue
            try:
                repaired = self._parse_chapter(response)
            except Exception as exc:
                logger.warning(f"{label} JSONFix output still cannot be parsed: {exc}")
                continue
            logger.warning(f"[{run_id}] {label} APIChapters fixedJSON")
            self._archived_failed_json.pop(section.chapter_id, None)
            return repaired
        return None

    def _ensure_run_state(self, run_id: str):
        """Ensure that the repair status is isolated every time the report is run, preventing the records of the previous task from affecting the new task.。"""
        if self._active_run_id == run_id:
            return
        self._active_run_id = run_id
        self._rescue_attempted_labels = {}
        self._skipped_fallback_chapters = set()
        self._archived_failed_json = {}

    def _archive_failed_output(self, section: TemplateSection, raw_text: str):
        """Cache the original error JSON of the current chapter for subsequent fallback or manual use。"""
        if not raw_text:
            return
        self._archived_failed_json[section.chapter_id] = raw_text

    def _get_archived_failed_output(self, section: TemplateSection) -> Optional[str]:
        """Get the raw output of the chapter's most recent failure。"""
        return self._archived_failed_json.get(section.chapter_id)

    def _mark_chapter_skipped(self, section: TemplateSection):
        """Record that this chapter has been downgraded to a fallback to avoid triggering cross-engine fixes repeatedly。"""
        self._skipped_fallback_chapters.add(section.chapter_id)

    def _chapter_already_skipped(self, section: TemplateSection) -> bool:
        """Determine whether the chapter has been marked as a fallback。"""
        return section.chapter_id in self._skipped_fallback_chapters

    def _build_fallback_chapter(
        self,
        section: TemplateSection,
        raw_text: str,
        parse_error: Exception,
    ) -> Optional[Tuple[Dict[str, Any], List[str]]]:
        """
        Construct a renderable fallback chapter when all repairs fail, and record a log file for subsequent troubleshooting。
        """
        snapshot = self._get_archived_failed_output(section) or raw_text
        log_ref = self._persist_error_payload(section, snapshot, parse_error)
        if not log_ref:
            logger.error(f"{section.title} Chapter JSON is completely corrupted and cannot be written to the log")
            return None
        importance = "critical" if self._is_section_critical(section) else "standard"
        message = (
            f"LLMReturns block parsing error, see details {log_ref['relativeFile']} of {log_ref['entryId']} Record。"
        )
        heading_block = {
            "type": "heading",
            "level": 2 if importance == "critical" else 3,
            "text": section.title,
            "anchor": section.slug,
        }
        callout_block = {
            "type": "callout",
            "tone": "danger" if importance == "critical" else "warning",
            "title": "LLMReturn block parsing error",
            "blocks": [
                {
                    "type": "paragraph",
                    "inlines": [
                        {
                            "text": message,
                        }
                    ],
                }
            ],
            "meta": {
                "errorLogRef": log_ref,
                "rawJsonPreview": (snapshot or "")[:2000],
                "errorMessage": message,
                "importance": importance,
            },
        }
        fallback = {
            "chapterId": section.chapter_id,
            "title": section.title,
            "anchor": section.slug,
            "order": section.order,
            "blocks": [heading_block, callout_block],
            "isErrorFallback": True,
        }
        errors = [
            f"{section.title} Chapter JSON parsing failed and has been handled by fallback. refer to {log_ref['relativeFile']}#{log_ref['entryId']}"
        ]
        self._mark_chapter_skipped(section)
        return fallback, errors

    def _parse_chapter(self, raw_text: str) -> Dict[str, Any]:
        """
        Clean LLM output and parse JSON.

        parameter:
            raw_text: LLMRaw output (may contain```package or additional instructions).

        return:
            dict: Chapter JSON object, containing at least chapterId/title/blocks。

        abnormal:
            ChapterJsonParseError: Various repair strategies still cannot parse the legalJSON。
        """
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if not cleaned:
            raise ChapterJsonParseError("LLMReturn empty content", raw_text=raw_text)

        candidate_payloads = [cleaned]
        repaired = self._repair_llm_json(cleaned)
        if repaired != cleaned:
            candidate_payloads.append(repaired)

        data: Dict[str, Any] | None = None
        try:
            data = self._parse_with_candidates(candidate_payloads)
        except json.JSONDecodeError as exc:
            repaired_payload = self._attempt_json_repair(cleaned)
            if repaired_payload:
                candidate_payloads.append(repaired_payload)
                try:
                    data = self._parse_with_candidates(candidate_payloads[-1:])
                except json.JSONDecodeError:
                    data = None
            if data is None:
                try:
                    data = self._robust_parser.parse(
                        cleaned,
                        context_name="ChapterJSON",
                        expected_keys=["chapter", "blocks", "chapterId", "title"],
                    )
                except JSONParseError as robust_exc:
                    raise ChapterJsonParseError(
                        f"Chapter JSON parsing failed: {robust_exc}", raw_text=cleaned
                    ) from robust_exc

        if "chapter" in data and isinstance(data["chapter"], dict):
            return data["chapter"]
        if isinstance(data, dict) and all(
            key in data for key in ("chapterId", "title", "blocks")
        ):
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    if "chapter" in item and isinstance(item["chapter"], dict):
                        return item["chapter"]
                    if all(key in item for key in ("chapterId", "title", "blocks")):
                        return item
        raise ChapterJsonParseError("The chapter JSON is missing the chapter field or the structure is incomplete", raw_text=cleaned)

    def _persist_error_payload(
        self,
        section: TemplateSection,
        raw_text: str,
        parse_error: Exception,
    ) -> Optional[Dict[str, str]]:
        """Put unparsable JSON text into disk so that it can be pointed to specific files in HTML。"""
        try:
            self._failed_block_counter += 1
            entry_id = f"E{self._failed_block_counter:04d}"
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            slug = section.slug or "section"
            filename = f"{timestamp}-{slug}-{entry_id}.json"
            file_path = self.error_log_dir / filename
            payload = {
                "chapterId": section.chapter_id,
                "title": section.title,
                "slug": section.slug,
                "order": section.order,
                "rawOutput": raw_text,
                "error": str(parse_error),
                "loggedAt": timestamp,
            }
            file_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                relative_path = str(file_path.relative_to(Path.cwd()))
            except ValueError:
                relative_path = str(file_path)
            return {
                "file": str(file_path),
                "relativeFile": relative_path,
                "entryId": entry_id,
                "timestamp": timestamp,
            }
        except Exception as exc:
            logger.error(f"Failed to log chapter JSON error log: {exc}")
            return None

    def _is_section_critical(self, section: TemplateSection) -> bool:
        """Based on chapter depth/The number determines whether it will affect the directory, thereby determining the prompt intensity.。"""
        if not section:
            return False
        if section.depth <= 2:
            return True
        number = section.number or ""
        if number and number.count(".") <= 1:
            return True
        return False

    def _repair_llm_json(self, text: str) -> str:
        """
        Handle common LLM errors (such as":=resulting in illegal JSON).

        parameter:
            text: Raw chapter JSON text.

        return:
            str: Repaired text; returns original content if no changes were made。
        """
        repaired = text
        mutated = False

        new_text = self._COLON_EQUALS_PATTERN.sub(r"\1", repaired)
        if new_text != repaired:
            logger.warning("Detected in chapter JSON\":=\"characters, redundant ones have been automatically removed'='Number")
            repaired = new_text
            mutated = True

        repaired, escaped = self._escape_in_string_controls(repaired)
        if escaped:
            logger.warning("An unescaped control character was detected in the chapter JSON string and was automatically converted to an escape sequence.")
            mutated = True

        repaired, balanced = self._balance_brackets(repaired)
        if balanced:
            logger.warning("Unbalanced chapter JSON brackets detected and automatically completed/Remove exception parentheses")
            mutated = True

        repaired, commas_fixed = self._fix_missing_commas(repaired)
        if commas_fixed:
            logger.warning("Chapter JSON object detected/There is a missing comma between the arrays, which has been automatically completed.")
            mutated = True

        return repaired if mutated else text

    def _escape_in_string_controls(self, text: str) -> Tuple[str, bool]:
        """
        Wrap naked newlines in string literals/tab character/Control characters are replaced with JSON legal escape sequences。
        """
        if not text:
            return text, False

        result: List[str] = []
        in_string = False
        escaped = False
        mutated = False
        control_map = {"\n": "\\n", "\r": "\\n", "\t": "\\t"}

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if in_string and ch in control_map:
                result.append(control_map[ch])
                mutated = True
                continue

            if in_string and ord(ch) < 0x20:
                result.append(f"\\u{ord(ch):04x}")
                mutated = True
                continue

            result.append(ch)

        return "".join(result), mutated

    def _fix_missing_commas(self, text: str) -> Tuple[str, bool]:
        """in object/Automatically add commas when arrays appear consecutively"""
        if not text:
            return text, False

        chars: List[str] = []
        mutated = False
        in_string = False
        escaped = False
        length = len(text)
        i = 0
        while i < length:
            ch = text[i]
            chars.append(ch)
            if escaped:
                escaped = False
                i += 1
                continue
            if ch == "\\":
                escaped = True
                i += 1
                continue
            if ch == '"':
                in_string = not in_string
                i += 1
                continue
            if not in_string and ch in "}]":
                j = i + 1
                while j < length and text[j] in " \t\r\n":
                    j += 1
                if j < length:
                    next_ch = text[j]
                    if next_ch in "{[":
                        chars.append(",")
                        mutated = True
            i += 1
        return "".join(chars), mutated

    def _balance_brackets(self, text: str) -> Tuple[str, bool]:
        """Try to fix overwriting due to LLM/Unbalanced structure caused by writing fewer parentheses"""
        if not text:
            return text, False

        result: List[str] = []
        stack: List[str] = []
        mutated = False
        in_string = False
        escaped = False

        opener_map = {"{": "}", "[": "]"}

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\":
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if in_string:
                result.append(ch)
                continue

            if ch in "{[":
                stack.append(ch)
                result.append(ch)
                continue

            if ch in "}]":
                if stack and ((ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")):
                    stack.pop()
                    result.append(ch)
                else:
                    mutated = True
                continue

            result.append(ch)

        while stack:
            opener = stack.pop()
            result.append(opener_map[opener])
            mutated = True

        return "".join(result), mutated

    def _attempt_json_repair(self, text: str) -> str | None:
        """Further fix complex syntax errors using the optional json_repair library"""
        if not _json_repair_fn:
            return None
        try:
            fixed = _json_repair_fn(text)
        except Exception as exc:
            logger.warning(f"json_repair Fix chapter JSON failure: {exc}")
            return None
        if fixed == text:
            return None
        logger.warning("Chapter JSON syntax has been automatically repaired using json_repair")
        return fixed

    def _attempt_llm_structural_repair(
        self,
        chapter: Dict[str, Any],
        validation_errors: List[str],
        raw_text: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Leave the chapters with structural errors to LLM to fix them, and keep the same API settings of Report Engine.。"""
        if not validation_errors:
            return None
        payload = build_chapter_repair_prompt(chapter, validation_errors, raw_text)
        try:
            response = self.llm_client.invoke(
                SYSTEM_PROMPT_CHAPTER_JSON_REPAIR,
                payload,
                temperature=0.0,
                top_p=0.05,
            )
        except Exception as exc:
            logger.error(f"Chapter JSON LLM repair call failed: {exc}")
            return None
        if not response:
            return None
        try:
            repaired = self._parse_chapter(response)
        except Exception as exc:
            logger.error(f"LLMFixed chapter JSON parsing failure: {exc}")
            return None
        logger.warning("The chapter JSON is still non-compliant after multiple local repairs, and LLM cover-up repair has been successfully enabled.")
        return repaired

    def _sanitize_chapter_blocks(self, chapter: Dict[str, Any]):
        """
        Fix common structural errors (e.g.list.itemsnested too deeply).

        parameter:
            chapter: Chapter JSON objects will be cleaned and organized in place。
        """

        def walk(blocks: List[Dict[str, Any]] | None):
            """Recursively check and repair nested structures to ensure that each block is legal"""
            if not isinstance(blocks, list):
                return

            valid_indices = []
            for idx, block in enumerate(blocks):
                if not isinstance(block, dict):

                    if isinstance(block, str) and block.strip():
                        blocks[idx] = self._as_paragraph_block(block)
                        valid_indices.append(idx)
                        logger.warning(f"walk: Convert string block to paragraph")
                    elif isinstance(block, list):

                        for item in block:
                            if isinstance(item, dict):
                                self._ensure_block_type(item)
                                blocks[idx] = item
                                valid_indices.append(idx)
                                logger.warning(f"walk: Extract dictionary from list block")
                                break
                        else:
                            logger.warning(f"walk: Skip invalid lists block: {block}")
                    else:
                        logger.warning(f"walk: Skip invalid blocks (type: {type(block).__name__}）")
                else:
                    valid_indices.append(idx)

            for idx in valid_indices:
                block = blocks[idx]
                if not isinstance(block, dict):
                    continue
                self._ensure_block_type(block)
                self._sanitize_block_content(block)
                block_type = block.get("type")
                if block_type == "list":

                    self._normalize_list_type(block)
                    items = block.get("items")
                    normalized = self._normalize_list_items(items)
                    if normalized:
                        block["items"] = normalized
                    for entry in block.get("items", []):
                        walk(entry)
                elif block_type in {"callout", "blockquote", "engineQuote"}:
                    walk(block.get("blocks"))
                elif block_type == "table":
                    for row in block.get("rows", []):
                        if not isinstance(row, dict):
                            continue
                        cells = row.get("cells") or []
                        for cell in cells:
                            if not isinstance(cell, dict):
                                continue
                            walk(cell.get("blocks"))
                elif block_type == "widget":
                    self._normalize_widget_block(block)
                else:
                    nested = block.get("blocks")
                    if isinstance(nested, list):
                        walk(nested)

        walk(chapter.get("blocks"))

        blocks = chapter.get("blocks")
        if isinstance(blocks, list):

            filtered_blocks = [b for b in blocks if isinstance(b, dict)]
            chapter["blocks"] = self._merge_fragment_sequences(filtered_blocks)

    def _ensure_content_density(self, chapter: Dict[str, Any]):
        """
        Verify chapter text density.

        If blocks are missing、There are no valid blocks except the title, or the number of text characters is below the threshold.
        If the chapter content is abnormal, ChapterContentError will be triggered so that the upstream can retry.

        parameter:
            chapter: Current chapter JSON.

        abnormal:
            ChapterContentError: Thrown when the number of text blocks or characters does not reach the lower limit。
        """
        blocks = chapter.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ChapterContentError(
                "The chapter is missing the text block and the content cannot be output.",
                chapter=chapter,
                body_characters=0,
                narrative_characters=0,
                non_heading_blocks=0,
            )

        non_heading_blocks = [
            block
            for block in blocks
            if isinstance(block, dict)
            and block.get("type") not in {"heading", "divider", "toc"}
        ]
        valid_block_count = len(non_heading_blocks)
        body_characters = self._count_body_characters(blocks)
        narrative_characters = self._count_narrative_characters(blocks)

        if (
            valid_block_count < self._MIN_NON_HEADING_BLOCKS
            or body_characters < self._MIN_BODY_CHARACTERS
            or narrative_characters < self._MIN_NARRATIVE_CHARACTERS
        ):
            raise ChapterContentError(
                f"{chapter.get('title') or 'This chapter'} Insufficient text: valid block {valid_block_count} , estimated number of characters {body_characters}，Narrative character count {narrative_characters}",
                chapter=chapter,
                body_characters=body_characters,
                narrative_characters=narrative_characters,
                non_heading_blocks=valid_block_count,
            )

    def _count_body_characters(self, blocks: Any) -> int:
        """
        Recursively count the number of text characters。

        - neglectheading/divider/widgetOther non-text types；
        - rightparagraph/list/table/calloutExtract nested text with equal structure；
        - It is only used for coarse-grained judgment whether the length is reasonable.

        parameter:
            blocks: A list or subtree of blocks for chapters.

        return:
            int: Estimated number of text characters。
        """

        def walk(node: Any) -> int:
            """Recursively drill down the block tree and return character estimates, skipping non-text types"""
            if node is None:
                return 0
            if isinstance(node, list):
                return sum(walk(item) for item in node)
            if isinstance(node, str):
                return len(node.strip())
            if not isinstance(node, dict):
                return 0

            block_type = node.get("type")
            if block_type in {"heading", "divider", "toc", "widget"}:
                return 0

            if block_type == "paragraph":
                return self._estimate_paragraph_characters(node)

            if block_type == "list":
                total = 0
                for item in node.get("items", []):
                    total += walk(item)
                return total

            if block_type in {"blockquote", "callout", "engineQuote"}:
                return walk(node.get("blocks"))

            if block_type == "table":
                total = 0
                for row in node.get("rows", []):
                    cells = row.get("cells") or []
                    for cell in cells:
                        total += walk(cell.get("blocks"))
                return total

            nested = node.get("blocks")
            if isinstance(nested, list):
                return walk(nested)

            return len(self._extract_block_text(node).strip())

        return walk(blocks)

    def _count_narrative_characters(self, blocks: Any) -> int:
        """
        statisticsparagraph/callout/list/blockquote/engineQuoteWait for the number of characters in the narrative structure to avoid being tabulated/Chart "Brush Long"”。
        """

        def walk(node: Any) -> int:
            """Recursively traverse narrative nodes, ignoring graphs/Table of contents and other non-text structures"""
            if node is None:
                return 0
            if isinstance(node, list):
                return sum(walk(item) for item in node)
            if isinstance(node, str):
                return len(node.strip())
            if not isinstance(node, dict):
                return 0

            block_type = node.get("type")
            if block_type == "paragraph":
                return self._estimate_paragraph_characters(node)
            if block_type == "list":
                total = 0
                for item in node.get("items", []):
                    total += walk(item)
                return total
            if block_type in {"callout", "blockquote", "engineQuote"}:
                return walk(node.get("blocks"))


            if block_type is None:
                nested = node.get("blocks")
                if isinstance(nested, list):
                    return walk(nested)
            return 0

        return walk(blocks)

    def _estimate_paragraph_characters(self, block: Dict[str, Any]) -> int:
        """Extract paragraph text length and reuse it in various statistics。"""
        inlines = block.get("inlines")
        if isinstance(inlines, list):
            total = 0
            for run in inlines:
                if isinstance(run, dict):
                    text = run.get("text")
                    if isinstance(text, str):
                        total += len(text.strip())
            return total
        text_value = block.get("text")
        if isinstance(text_value, str):
            return len(text_value.strip())
        return len(self._extract_block_text(block).strip())

    def _sanitize_block_content(self, block: Dict[str, Any]):
        """Make detailed repairs based on the type, such as cleaning up illegal ones in the paragraphinline mark"""
        block_type = block.get("type")
        if block_type == "paragraph":
            self._normalize_paragraph_block(block)
        elif block_type == "table":
            self._sanitize_table_block(block)
        elif block_type == "engineQuote":
            self._sanitize_engine_quote_block(block)

    def _sanitize_table_block(self, block: Dict[str, Any]):
        """guarantee formrows/cellsThe structure is legal and each cell contains at least oneblock"""
        raw_rows = block.get("rows")

        if isinstance(raw_rows, list) and len(raw_rows) == 1:
            first_row = raw_rows[0]
            if isinstance(first_row, dict):
                cells = first_row.get("cells", [])

                has_nested = any(
                    isinstance(cell, dict) and "cells" in cell and "blocks" not in cell
                    for cell in cells
                    if isinstance(cell, dict)
                )
                if has_nested:

                    fixed_rows = self._fix_nested_rows_structure(raw_rows)
                    block["rows"] = fixed_rows
                    return

        rows = self._normalize_table_rows(raw_rows)
        block["rows"] = rows

    def _fix_nested_rows_structure(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Fix incorrectly nested table row structure.

        When the table generated by LLM has only 1 row but all data is nested in cells,
        This method will flatten all cells and reorganize them into the correct multi-row structure.

        parameter:
            rows: Original array of table rows (should only have 1 row).

        return:
            List[Dict]: Repaired multi-row table structure。
        """
        if not rows or len(rows) != 1:
            return self._normalize_table_rows(rows)

        first_row = rows[0]
        original_cells = first_row.get("cells", [])


        all_cells = self._flatten_all_cells_recursive(original_cells)

        if len(all_cells) <= 1:
            return self._normalize_table_rows(rows)


        def _get_cell_text(cell: Dict[str, Any]) -> str:
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

        def _is_fallback_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether a cell is a fallback"""
            text = _get_cell_text(cell)
            return text in ("--", "-", "—", "——", "", "N/A", "n/a")

        def _is_header_cell(cell: Dict[str, Any]) -> bool:
            """Determine whether the cell looks like a header (usually has a bold mark or a typical header word)）"""
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
                "information", "content", "style", "Preference", "main", "user", "core", "feature",
                "Classification", "scope", "object", "project", "stage", "cycle", "frequency", "grade",
            }
            return any(kw in text for kw in header_keywords) and len(text) <= 20


        valid_cells = [c for c in all_cells if not _is_fallback_cell(c)]

        if len(valid_cells) <= 1:
            return self._normalize_table_rows(rows)


        header_count = 0
        for cell in valid_cells:
            if _is_header_cell(cell):
                header_count += 1
            else:
                break


        if header_count == 0:
            total = len(valid_cells)
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

                    return self._normalize_table_rows(rows)


        total = len(valid_cells)
        remainder = total % header_count
        if remainder > 0 and remainder <= 3:

            valid_cells = valid_cells[:total - remainder]
        elif remainder > 3:

            return self._normalize_table_rows(rows)


        fixed_rows: List[Dict[str, Any]] = []
        for i in range(0, len(valid_cells), header_count):
            row_cells = valid_cells[i:i + header_count]

            if i == 0:
                for cell in row_cells:
                    cell["header"] = True
            fixed_rows.append({"cells": row_cells})

        return fixed_rows if fixed_rows else self._normalize_table_rows(rows)

    def _flatten_all_cells_recursive(self, cells: List[Any]) -> List[Dict[str, Any]]:
        """
        Recursively flatten all nested cell structures.

        parameter:
            cells: A cell array that may contain nested structures.

        return:
            List[Dict]: Flattened cell array, each cell hasblocks。
        """
        if not cells:
            return []

        flattened: List[Dict[str, Any]] = []

        def _extract_cells(cell_or_list: Any) -> None:
            if not isinstance(cell_or_list, dict):
                if isinstance(cell_or_list, (str, int, float)):
                    flattened.append({"blocks": [self._as_paragraph_block(str(cell_or_list))]})
                return


            if "blocks" in cell_or_list:

                clean_cell = {
                    k: v for k, v in cell_or_list.items()
                    if k != "cells"
                }

                blocks = clean_cell.get("blocks")
                if not isinstance(blocks, list) or not blocks:
                    clean_cell["blocks"] = [self._as_paragraph_block("")]
                flattened.append(clean_cell)


            nested_cells = cell_or_list.get("cells")
            if isinstance(nested_cells, list):
                for nested_cell in nested_cells:
                    _extract_cells(nested_cell)

        for cell in cells:
            _extract_cells(cell)

        return flattened

    def _sanitize_engine_quote_block(self, block: Dict[str, Any]):
        """engineQuoteOnly used for single Agent speech. Only paragraph is allowed internally and the title needs to lock the Agent name."""
        engine_raw = block.get("engine")
        engine = engine_raw.lower() if isinstance(engine_raw, str) else None
        if engine not in ENGINE_AGENT_TITLES:
            engine = "insight"
        block["engine"] = engine
        block["title"] = ENGINE_AGENT_TITLES[engine]
        allowed_marks = {"bold", "italic"}
        raw_blocks = block.get("blocks")
        candidates = raw_blocks if isinstance(raw_blocks, list) else ([raw_blocks] if raw_blocks else [])
        sanitized_blocks: List[Dict[str, Any]] = []

        for item in candidates:
            if isinstance(item, dict) and item.get("type") == "paragraph":
                para = dict(item)
            else:
                text = self._extract_block_text(item) if isinstance(item, dict) else (item or "")
                para = self._as_paragraph_block(str(text))

            inlines = para.get("inlines")
            if not isinstance(inlines, list) or not inlines:
                inlines = [self._as_inline_run(self._extract_block_text(para))]

            cleaned_inlines: List[Dict[str, Any]] = []
            for run in inlines:
                if isinstance(run, dict):
                    text_val = run.get("text")
                    text_str = text_val if isinstance(text_val, str) else ("" if text_val is None else str(text_val))
                    marks_raw = run.get("marks") if isinstance(run.get("marks"), list) else []
                    marks_filtered: List[Dict[str, Any]] = []
                    for mark in marks_raw:
                        if not isinstance(mark, dict):
                            continue
                        mark_type = mark.get("type")
                        if mark_type in allowed_marks:
                            marks_filtered.append({"type": mark_type})
                    cleaned_inlines.append({"text": text_str, "marks": marks_filtered})
                else:
                    cleaned_inlines.append(self._as_inline_run(str(run)))

            if not cleaned_inlines:
                cleaned_inlines.append(self._as_inline_run(""))
            para["inlines"] = cleaned_inlines
            para["type"] = "paragraph"
            para.pop("blocks", None)
            sanitized_blocks.append(para)

        if not sanitized_blocks:
            sanitized_blocks.append(self._as_paragraph_block(""))
        block["blocks"] = sanitized_blocks

    def _normalize_table_rows(self, rows: Any) -> List[Dict[str, Any]]:
        """Make sure rows is always a list of row objects"""
        if rows is None:
            rows_iterable: List[Any] = []
        elif isinstance(rows, list):
            rows_iterable = rows
        else:
            rows_iterable = [rows]

        normalized_rows: List[Dict[str, Any]] = []
        for row in rows_iterable:
            sanitized_row = self._normalize_table_row(row)
            if sanitized_row:
                normalized_rows.append(sanitized_row)

        if not normalized_rows:
            normalized_rows.append({"cells": [self._build_default_table_cell()]})
        return normalized_rows

    def _normalize_table_row(self, row: Any) -> Dict[str, Any] | None:
        """Unify various line expressions into{'cells': [...]}structure"""
        if row is None:
            return None
        if isinstance(row, dict):
            result = dict(row)
            cells_value = result.get("cells")
        else:
            result = {}
            cells_value = row

        cells = self._normalize_table_cells(cells_value)
        if not cells:
            cells = [self._build_default_table_cell()]
        result["cells"] = cells
        return result

    def _normalize_table_cells(self, cells: Any) -> List[Dict[str, Any]]:
        """Clean the cells and ensure that there is non-empty space under each cell.blocks"""
        if cells is None:
            cell_entries: List[Any] = []
        elif isinstance(cells, list):
            cell_entries = cells
        else:
            cell_entries = [cells]

        normalized_cells: List[Dict[str, Any]] = []
        for cell in cell_entries:


            if isinstance(cell, dict) and "cells" in cell and "blocks" not in cell:
                flattened = self._flatten_all_nested_cells(cell)
                normalized_cells.extend(flattened)
            else:
                sanitized = self._normalize_table_cell(cell)
                if sanitized:
                    normalized_cells.append(sanitized)

        return normalized_cells

    def _flatten_all_nested_cells(self, cell: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Flatten incorrectly nested cells structures, returning all flattened cells.

        LLM sometimes generates incorrect structures like this：
        { "cells": [
            { "blocks": [...] },
            { "cells": [
                { "blocks": [...] },
                { "cells": [...] }
              ]
            }
          ]
        }

        should be flattened into a separate list of cells。
        """
        nested_cells = cell.get("cells")
        if not isinstance(nested_cells, list) or not nested_cells:
            return [{"blocks": [self._as_paragraph_block("")]}]

        result: List[Dict[str, Any]] = []
        for nested in nested_cells:
            if isinstance(nested, dict):
                if "blocks" in nested and "cells" not in nested:

                    sanitized = self._normalize_table_cell(nested)
                    if sanitized:
                        result.append(sanitized)
                elif "cells" in nested and "blocks" not in nested:

                    result.extend(self._flatten_all_nested_cells(nested))
                else:

                    sanitized = self._normalize_table_cell(nested)
                    if sanitized:
                        result.append(sanitized)
            elif isinstance(nested, (str, int, float)):
                result.append({"blocks": [self._as_paragraph_block(str(nested))]})

        return result if result else [{"blocks": [self._as_paragraph_block("")]}]

    def _normalize_table_cell(self, cell: Any) -> Dict[str, Any] | None:
        """Organize various cell writing rules into a form recognized by the schema"""
        if cell is None:
            return {"blocks": [self._as_paragraph_block("")]}

        if isinstance(cell, dict):


            if "cells" in cell and "blocks" not in cell:


                return self._flatten_nested_cell(cell)

            normalized = dict(cell)
            blocks = self._coerce_cell_blocks(normalized.get("blocks"), normalized)
        elif isinstance(cell, list):
            normalized = {}
            blocks = self._coerce_cell_blocks(cell, None)
        elif isinstance(cell, (str, int, float)):
            normalized = {}
            blocks = [self._as_paragraph_block(str(cell))]
        else:
            normalized = {}
            blocks = [self._as_paragraph_block(str(cell))]

        normalized["blocks"] = blocks or [self._as_paragraph_block("")]
        return normalized

    def _flatten_nested_cell(self, cell: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten incorrectly nested cell structures.

        LLM sometimes generates incorrect structures like this：
        { "cells": [ { "blocks": [...] }, { "cells": [...] } ] }

        Should return the first valid cell content。
        """
        nested_cells = cell.get("cells")
        if not isinstance(nested_cells, list) or not nested_cells:

            return {"blocks": [self._as_paragraph_block("")]}


        for nested in nested_cells:
            if isinstance(nested, dict):
                if "blocks" in nested:

                    return self._normalize_table_cell(nested)
                elif "cells" in nested:

                    result = self._flatten_nested_cell(nested)
                    if result:
                        return result


        first_nested = nested_cells[0]
        if isinstance(first_nested, dict):
            text = self._extract_block_text(first_nested)
            return {"blocks": [self._as_paragraph_block(text or "")]}

        return {"blocks": [self._as_paragraph_block("")]}

    def _coerce_cell_blocks(
        self, blocks: Any, source: Dict[str, Any] | None
    ) -> List[Dict[str, Any]]:
        """Willcell.blocksFields are coerced into legal block arrays"""
        if isinstance(blocks, list):
            entries = blocks
        elif blocks is None:
            entries = []
        else:
            entries = [blocks]

        normalized_blocks: List[Dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, dict):
                normalized_blocks.append(entry)
            elif isinstance(entry, list):
                normalized_blocks.extend(self._coerce_cell_blocks(entry, None))
            elif isinstance(entry, (str, int, float)):
                normalized_blocks.append(self._as_paragraph_block(str(entry)))
            elif entry is None:
                continue
            else:
                normalized_blocks.append(self._as_paragraph_block(str(entry)))

        if normalized_blocks:
            return normalized_blocks

        text_hint = ""
        if isinstance(source, dict):
            text_hint = self._extract_block_text(source).strip()
        return [self._as_paragraph_block(text_hint or "--")]

    def _build_default_table_cell(self) -> Dict[str, Any]:
        """Generate a minimally renderable blank cell"""
        return {"blocks": [self._as_paragraph_block("--")]}

    def _normalize_paragraph_block(self, block: Dict[str, Any]):
        """Unify and regularize the inlines of the paragraph and eliminate illegal onesmarks"""
        inlines = block.get("inlines")
        normalized_runs: List[Dict[str, Any]] = []
        if isinstance(inlines, list) and inlines:
            for run in inlines:
                normalized_runs.extend(self._coerce_inline_run(run))
        else:
            normalized_runs = [self._as_inline_run(self._extract_block_text(block))]
        if not normalized_runs:
            normalized_runs = [self._as_inline_run("")]
        block["inlines"] = self._strip_inline_artifacts(normalized_runs)

    def _strip_inline_artifacts(self, inlines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove JSON sentinel text mistakenly written by LLM to prevent rendering`{\"type\": \"\"}`Waiting for junk characters"""
        cleaned: List[Dict[str, Any]] = []
        for run in inlines or []:
            if not isinstance(run, dict):
                continue
            text = run.get("text")
            if isinstance(text, str):
                stripped = text.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    try:
                        payload = json.loads(stripped)
                    except json.JSONDecodeError:
                        payload = None
                    if isinstance(payload, dict) and set(payload.keys()).issubset({"type", "value"}):
                        continue
            cleaned.append(run)
        return cleaned or [self._as_inline_run("")]

    def _merge_fragment_sequences(self, blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge sentence fragments split into multiple paragraphs by LLM to avoid a large number of orphans in HTML<p>"""
        if not isinstance(blocks, list):
            return blocks

        merged: List[Dict[str, Any]] = []
        fragment_buffer: List[Dict[str, Any]] = []

        def flush_buffer():
            """Write the current segment buffer into the merged list, merging it into a single segment if necessaryparagraph"""
            nonlocal fragment_buffer
            if not fragment_buffer:
                return
            if len(fragment_buffer) == 1:
                merged.append(fragment_buffer[0])
            else:
                merged.append(self._combine_paragraph_fragments(fragment_buffer))
            fragment_buffer = []

        for block in blocks:

            if not isinstance(block, dict):

                if isinstance(block, str) and block.strip():
                    converted = self._as_paragraph_block(block)
                    logger.warning(f"Non-dict type block (string) detected, converted to paragraph: {block[:50]}...")
                    merged.append(converted)
                elif isinstance(block, list):

                    logger.warning(f"List type block detected, try to extract valid content: {block}")
                    for item in block:
                        if isinstance(item, dict):
                            self._ensure_block_type(item)
                            merged.append(self._merge_nested_fragments(item))
                        elif isinstance(item, str) and item.strip():
                            merged.append(self._as_paragraph_block(item))
                else:
                    logger.warning(f"Skip invalid blocks (type: {type(block).__name__}）: {block}")
                continue
            if self._is_paragraph_fragment(block):
                fragment_buffer.append(block)
                continue
            flush_buffer()
            merged.append(self._merge_nested_fragments(block))

        flush_buffer()
        return merged

    def _merge_nested_fragments(self, block: Dict[str, Any]) -> Dict[str, Any]:
        """for nested structures（callout/blockquote/engineQuote/list/table）Recursively handle fragment merging"""

        if not isinstance(block, dict):

            if isinstance(block, str) and block.strip():
                logger.warning(f"_merge_nested_fragments Received string type, converted to paragraph")
                return self._as_paragraph_block(block)
            elif isinstance(block, list):

                for item in block:
                    if isinstance(item, dict):
                        self._ensure_block_type(item)
                        return self._merge_nested_fragments(item)
                logger.warning(f"_merge_nested_fragments Invalid list received, return empty paragraph")
                return self._as_paragraph_block("")
            else:
                logger.warning(f"_merge_nested_fragments Invalid type received（{type(block).__name__}），Return empty paragraph")
                return self._as_paragraph_block("")

        block_type = block.get("type")
        if block_type in {"callout", "blockquote", "engineQuote"}:
            nested = block.get("blocks")
            if isinstance(nested, list):
                block["blocks"] = self._merge_fragment_sequences(nested)
        elif block_type == "list":
            items = block.get("items")
            if isinstance(items, list):
                for entry in items:
                    if isinstance(entry, list):
                        merged_entry = self._merge_fragment_sequences(entry)
                        entry[:] = merged_entry
        elif block_type == "table":
            for row in block.get("rows", []):
                if not isinstance(row, dict):
                    continue
                cells = row.get("cells") or []
                for cell in cells:
                    if not isinstance(cell, dict):
                        continue
                    nested_blocks = cell.get("blocks")
                    if isinstance(nested_blocks, list):
                        cell["blocks"] = self._merge_fragment_sequences(nested_blocks)
        return block

    def _combine_paragraph_fragments(self, fragments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine multiple sentence fragments into a singleparagraph block"""
        template = dict(fragments[0])
        combined_inlines: List[Dict[str, Any]] = []
        for fragment in fragments:
            runs = fragment.get("inlines")
            if isinstance(runs, list) and runs:
                combined_inlines.extend(runs)
            else:
                fallback_text = self._extract_block_text(fragment)
                combined_inlines.append(self._as_inline_run(fallback_text))
        if not combined_inlines:
            combined_inlines.append(self._as_inline_run(""))
        template["inlines"] = combined_inlines
        return template

    def _is_paragraph_fragment(self, block: Dict[str, Any]) -> bool:
        """Determine whether the paragraph is a short fragment that was incorrectly split"""
        if not isinstance(block, dict) or block.get("type") != "paragraph":
            return False
        inlines = block.get("inlines")
        text = ""
        has_marks = False
        if isinstance(inlines, list) and inlines:
            parts: List[str] = []
            for run in inlines:
                if not isinstance(run, dict):
                    continue
                parts.append(str(run.get("text") or ""))
                marks = run.get("marks")
                if isinstance(marks, list) and any(marks):
                    has_marks = True
            text = "".join(parts)
        else:
            text = self._extract_block_text(block)
        stripped = (text or "").strip()
        if not stripped:
            return True
        if has_marks:
            return False
        if "\n" in stripped:
            return False

        short_limit = self._PARAGRAPH_FRAGMENT_MAX_CHARS
        long_limit = getattr(
            self,
            "_PARAGRAPH_FRAGMENT_NO_TERMINATOR_MAX_CHARS",
            short_limit * 3,
        )

        if stripped[-1] in self._TERMINATION_PUNCTUATION:
            return len(stripped) <= short_limit

        if len(stripped) > long_limit:
            return False
        return True

    def _coerce_inline_run(self, run: Any) -> List[Dict[str, Any]]:
        """Make any inline writing laws legalrun"""
        if isinstance(run, dict):
            normalized_run = dict(run)
            text = normalized_run.get("text")
            if not isinstance(text, str):
                text = "" if text is None else str(text)
            marks = normalized_run.get("marks")
            sanitized_marks, extra_text = self._sanitize_inline_marks(marks)
            normalized_run["marks"] = sanitized_marks
            normalized_run["text"] = (text or "") + extra_text
            return [normalized_run]
        if isinstance(run, str):
            return [self._as_inline_run(run)]
        if isinstance(run, (int, float)):
            return [self._as_inline_run(str(run))]
        if isinstance(run, list):
            normalized: List[Dict[str, Any]] = []
            for item in run:
                normalized.extend(self._coerce_inline_run(item))
            return normalized
        return [self._as_inline_run("" if run is None else str(run))]

    def _sanitize_inline_marks(self, marks: Any) -> Tuple[List[Dict[str, Any]], str]:
        """Filter illegal marks and convert break class control characters into text"""
        text_suffix_parts = []
        if marks is None:
            return [], "".join(text_suffix_parts)
        mark_list = marks if isinstance(marks, list) else [marks]
        sanitized: List[Dict[str, Any]] = []
        for mark in mark_list:
            normalized_mark, extra_text = self._normalize_inline_mark(mark)
            if normalized_mark:
                sanitized.append(normalized_mark)
            if extra_text:
                text_suffix_parts.append(extra_text)
        return sanitized, "".join(text_suffix_parts)

    def _normalize_inline_mark(self, mark: Any) -> Tuple[Dict[str, Any] | None, str]:
        """Compatible mapping of individual marks, or conversion to text if necessary"""
        if not isinstance(mark, dict):
            return None, ""
        canonical_type = self._canonical_inline_mark_type(mark.get("type"))
        if canonical_type == self._LINE_BREAK_SENTINEL:
            return None, "\n"
        if canonical_type in ALLOWED_INLINE_MARKS:
            normalized = dict(mark)
            normalized["type"] = canonical_type
            return normalized, ""
        return None, ""

    def _canonical_inline_mark_type(self, mark_type: Any) -> str | None:
        """Map mark type to values ​​supported by Schema"""
        if not isinstance(mark_type, str):
            return None
        normalized = mark_type.strip()
        if not normalized:
            return None
        lowered = normalized.lower()
        if lowered in {"break", "linebreak", "br"}:
            return self._LINE_BREAK_SENTINEL
        return self._INLINE_MARK_ALIASES.get(lowered, lowered)

    def _extract_block_text(self, block: Dict[str, Any]) -> str:
        """Prioritize fromtext/contentExtract fallback text from other fields"""
        for key in ("text", "content", "value", "title"):
            value = block.get(key)
            if isinstance(value, str):
                return value
            if value is not None:
                return str(value)
        return ""


    _ALLOWED_LIST_TYPES = {"ordered", "bullet", "task"}

    _LIST_TYPE_ALIASES = {
        "unordered": "bullet",
        "ul": "bullet",
        "ol": "ordered",
        "numbered": "ordered",
        "checkbox": "task",
        "check": "task",
        "checklist": "task",
    }

    def _normalize_list_type(self, block: Dict[str, Any]):
        """
        Make sure the listType of the list block is a legal value.

        If listType is missing or illegal, it will be automatically fixed to bullet。
        """
        list_type = block.get("listType")
        if list_type in self._ALLOWED_LIST_TYPES:
            return

        if isinstance(list_type, str):
            lowered = list_type.strip().lower()
            if lowered in self._LIST_TYPE_ALIASES:
                block["listType"] = self._LIST_TYPE_ALIASES[lowered]
                logger.warning(f"Already listType '{list_type}' mapped to '{block['listType']}'")
                return
            if lowered in self._ALLOWED_LIST_TYPES:
                block["listType"] = lowered
                return

        logger.warning(f"Illegal detected listType: {list_type}，Fixed to bullet")
        block["listType"] = "bullet"

    def _normalize_list_items(self, items: Any) -> List[List[Dict[str, Any]]]:
        """Make sure the items of the list block are[[block, block], ...]structure"""
        if not isinstance(items, list):
            return []
        normalized: List[List[Dict[str, Any]]] = []
        for item in items:
            normalized.extend(self._coerce_list_item(item))
        return [entry for entry in normalized if entry]

    def _coerce_list_item(self, item: Any) -> List[List[Dict[str, Any]]]:
        """Convert various nested writing methods into block arrays"""
        result: List[List[Dict[str, Any]]] = []
        if isinstance(item, dict):
            self._ensure_block_type(item)
            result.append([item])
            return result
        if isinstance(item, list):
            dicts = [elem for elem in item if isinstance(elem, dict)]
            if dicts:
                for elem in dicts:
                    self._ensure_block_type(elem)
                result.append(dicts)
            for elem in item:
                if isinstance(elem, list):
                    result.extend(self._coerce_list_item(elem))
                elif isinstance(elem, dict):
                    continue
                elif isinstance(elem, str):
                    result.append([self._as_paragraph_block(elem)])
                elif isinstance(elem, (int, float)):
                    result.append([self._as_paragraph_block(str(elem))])
        elif isinstance(item, str):
            result.append([self._as_paragraph_block(item)])
        elif isinstance(item, (int, float)):
            result.append([self._as_paragraph_block(str(item))])
        return result

    def _normalize_widget_block(self, block: Dict[str, Any]):
        """Make sure the widget has top-level data ordataRef"""
        has_data = block.get("data") is not None or block.get("dataRef") is not None
        if has_data:
            return
        props = block.get("props")
        if isinstance(props, dict) and "data" in props:
            block["data"] = props.pop("data")
            return
        block["data"] = {"labels": [], "datasets": []}

    def _ensure_block_type(self, block: Dict[str, Any]):
        """If the block lacks a legal type, it is downgraded toparagraph"""
        block_type = block.get("type")
        if isinstance(block_type, str) and block_type in ALLOWED_BLOCK_TYPES:
            return
        text = ""
        for key in ("text", "content", "title"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                break
        if not text:
            try:
                text = json.dumps(block, ensure_ascii=False)
            except Exception:
                text = str(block)
        block.clear()
        block["type"] = "paragraph"
        block["inlines"] = [self._as_inline_run(text)]

    @staticmethod
    def _as_paragraph_block(text: str) -> Dict[str, Any]:
        """Quickly package strings into paragraph blocks for easy unified processing"""
        return {
            "type": "paragraph",
            "inlines": [ChapterGenerationNode._as_inline_run(text)],
        }

    @staticmethod
    def _as_inline_run(text: str) -> Dict[str, Any]:
        """Construct a basic inline run to ensure that the marks field exists"""
        return {"text": text or "", "marks": []}

    @staticmethod
    def _parse_with_candidates(payloads: List[str]) -> Dict[str, Any]:
        """Try multiple payloads in sequence until parsing succeeds"""
        last_exc: json.JSONDecodeError | None = None
        for payload in payloads:
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc


__all__ = [
    "ChapterGenerationNode",
    "ChapterJsonParseError",
    "ChapterContentError",
    "ChapterValidationError",
]
