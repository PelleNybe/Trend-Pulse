"""
Unified JSON parsing and repair tool.

Provides robust JSON parsing capabilities and supports：
1. Automatically clean markdown code block tags and reflection content
2. Local syntax fixes (bracket balancing、comma completion、Control character escaping, etc.）
3. Advanced repair using json_repair library
4. LLMAssisted restoration (optional）
5. Detailed error logs and debugging information
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Callable
from loguru import logger

try:
    from json_repair import repair_json as _json_repair_fn
except ImportError:
    _json_repair_fn = None


class JSONParseError(ValueError):
    """JSONException thrown when parsing fails, with original text attached for easy troubleshooting。"""

    def __init__(self, message: str, raw_text: Optional[str] = None):
        """
        Construct exceptions and attach raw output for easy locating in logs。

        Args:
            message: Human-readable error description。
            raw_text: Full LLM output of triggered exception。
        """
        super().__init__(message)
        self.raw_text = raw_text


class RobustJSONParser:
    """
    Robust JSON parser.

    Integrate multiple repair strategies to ensure that the content returned by LLM can be correctly parsed：
    - Clean markdown package、additional information such as reflection content
    - Fix common syntax errors (missing comma、Unbalanced brackets etc.）
    - Escape unescaped control characters
    - Use third-party libraries for advanced repairs
    - Optional LLM-assisted repair
    """


    _THINKING_PATTERNS = [
        r"^\s*<thinking>.*?</thinking>\s*",
        r"^\s*<thought>.*?</thought>\s*",
        r"^\s*let me think.*?(?=\{|\[|$)",
        r"^\s*first.*?(?=\{|\[|$)",
        r"^\s*analyze.*?(?=\{|\[|$)",
        r"^\s*according to.*?(?=\{|\[|$)",
    ]


    _COLON_EQUALS_PATTERN = re.compile(r'(":\s*)=')

    def __init__(
        self,
        llm_repair_fn: Optional[Callable[[str, str], Optional[str]]] = None,
        enable_json_repair: bool = True,
        enable_llm_repair: bool = False,
        max_repair_attempts: int = 3,
    ):
        """
        Initialize JSON parser。

        Args:
            llm_repair_fn: Optional LLM repair function, receiving(originalJSON, error message)Return to the repairedJSON
            enable_json_repair: Whether to enable json_repair library
            enable_llm_repair: Whether to enable LLM-assisted repair
            max_repair_attempts: Maximum number of repair attempts
        """
        self.llm_repair_fn = llm_repair_fn
        self.enable_json_repair = enable_json_repair and _json_repair_fn is not None
        self.enable_llm_repair = enable_llm_repair
        self.max_repair_attempts = max_repair_attempts

    def parse(
        self,
        raw_text: str,
        context_name: str = "JSON",
        expected_keys: Optional[List[str]] = None,
        extract_wrapper_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse the JSON text returned by LLM.

        parameter:
            raw_text: LLMRaw output (may contain```pack、Thinking content etc.）
            context_name: Context name, used for error messages
            expected_keys: List of expected keys, used for validation
            extract_wrapper_key: If the JSON is wrapped in a key, specify the key name for extraction

        Return:
            dict: Parsed JSON object

        Abnormal:
            JSONParseError: Various repair strategies still cannot parse the legalJSON
        """
        if not raw_text or not raw_text.strip():
            raise JSONParseError(f"{context_name}Return empty content")


        original_text = raw_text


        candidates = self._build_candidate_payloads(raw_text, context_name)


        last_error: Optional[json.JSONDecodeError] = None
        for i, candidate in enumerate(candidates):
            try:
                data = json.loads(candidate)
                logger.debug(f"{context_name} JSONParsed successfully (candidate{i + 1}/{len(candidates)}）")
                return self._extract_and_validate(
                    data, expected_keys, extract_wrapper_key, context_name
                )
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.debug(f"{context_name} candidate{i + 1}Parsing failed: {exc}")

        cleaned = candidates[0] if candidates else original_text


        if self.enable_json_repair:
            repaired = self._attempt_json_repair(cleaned, context_name)
            if repaired:
                try:
                    data = json.loads(repaired)
                    logger.info(f"{context_name} JSONSuccessfully repaired through json_repair library")
                    return self._extract_and_validate(
                        data, expected_keys, extract_wrapper_key, context_name
                    )
                except json.JSONDecodeError as exc:
                    last_error = exc
                    logger.debug(f"{context_name} json_repairStill cannot be parsed after repair: {exc}")


        if self.enable_llm_repair and self.llm_repair_fn:
            llm_repaired = self._attempt_llm_repair(cleaned, str(last_error), context_name)
            if llm_repaired:
                try:
                    data = json.loads(llm_repaired)
                    logger.info(f"{context_name} JSONSuccessfully repaired through LLM")
                    return self._extract_and_validate(
                        data, expected_keys, extract_wrapper_key, context_name
                    )
                except json.JSONDecodeError as exc:
                    last_error = exc
                    logger.warning(f"{context_name} LLMStill cannot be parsed after repair: {exc}")


        error_msg = f"{context_name} JSONParsing failed: {last_error}"
        logger.error(error_msg)
        logger.debug(f"First 500 characters of original text: {original_text[:500]}")
        raise JSONParseError(error_msg, raw_text=original_text) from last_error

    def _build_candidate_payloads(self, raw_text: str, context_name: str) -> List[str]:
        """
        Construct multiple candidate JSON strings against the original text, covering different cleaning strategies.

        return:
            List[str]: List of candidate JSON texts
        """
        cleaned = self._clean_response(raw_text)
        candidates = [cleaned]

        local_repaired = self._apply_local_repairs(cleaned)
        if local_repaired != cleaned:
            candidates.append(local_repaired)


        flattened = self._flatten_nested_arrays(local_repaired)
        if flattened not in candidates:
            candidates.append(flattened)

        return candidates

    def _clean_response(self, raw: str) -> str:
        """
        Clean LLM response, remove markdown tags and reflection content.

        parameter:
            raw: LLMraw output

        Return:
            str: Cleaned text
        """
        cleaned = raw.strip()


        for pattern in self._THINKING_PATTERNS:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE)


        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fenced_match:
            cleaned = fenced_match.group(1).strip()
        else:

            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]

            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]

            cleaned = cleaned.strip()


        cleaned = self._extract_first_json_structure(cleaned)

        return cleaned

    def _extract_first_json_structure(self, text: str) -> str:
        """
        Extract the first complete JSON object or array from the text.

        This is useful for handling situations where LLM adds descriptive text before and after the JSON.

        parameter:
            text: Text that may contain JSON

        Return:
            str: Extracted JSON text, if not found, returns the original text
        """

        start_brace = text.find("{")
        start_bracket = text.find("[")

        if start_brace == -1 and start_bracket == -1:
            return text


        if start_brace == -1:
            start = start_bracket
            opener = "["
            closer = "]"
        elif start_bracket == -1:
            start = start_brace
            opener = "{"
            closer = "}"
        else:
            start = min(start_brace, start_bracket)
            opener = text[start]
            closer = "}" if opener == "{" else "]"


        depth = 0
        in_string = False
        escaped = False

        for i in range(start, len(text)):
            ch = text[i]

            if escaped:
                escaped = False
                continue

            if ch == "\\":
                escaped = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]


        return text[start:] if start < len(text) else text

    def _apply_local_repairs(self, text: str) -> str:
        """
        Apply local remediation strategies.

        parameter:
            text: Raw JSON text

        Return:
            str: Repaired text
        """
        repaired = text
        mutated = False


        new_text = self._COLON_EQUALS_PATTERN.sub(r"\1", repaired)
        if new_text != repaired:
            logger.warning("detected\":=\"characters, redundant ones have been automatically removed'='Number")
            repaired = new_text
            mutated = True


        repaired, escaped = self._escape_control_characters(repaired)
        if escaped:
            logger.warning("Unescaped control character detected, automatically converted to escape sequence")
            mutated = True


        repaired, commas_fixed = self._fix_missing_commas(repaired)
        if commas_fixed:
            logger.warning("Object detected/There is a missing comma between the arrays, which has been automatically completed.")
            mutated = True


        repaired, brackets_collapsed = self._collapse_redundant_brackets(repaired)
        if brackets_collapsed:
            logger.warning("Continuous nesting of square brackets detected, attempted collapse into 2D structure")
            mutated = True


        repaired, balanced = self._balance_brackets(repaired)
        if balanced:
            logger.warning("Unbalanced brackets detected and automatically completed/Remove exception parentheses")
            mutated = True


        repaired, trailing_removed = self._remove_trailing_commas(repaired)
        if trailing_removed:
            logger.warning("Trailing comma detected, automatically removed")
            mutated = True

        return repaired if mutated else text

    def _escape_control_characters(self, text: str) -> Tuple[str, bool]:
        """
        Wrap naked newlines in string literals/tab character/Control characters are replaced with JSON legal escape sequences.

        parameter:
            text: Raw JSON text

        Return:
            Tuple[str, bool]: (Repaired text, Is there any modification?)
        """
        if not text:
            return text, False

        result: List[str] = []
        in_string = False
        escaped = False
        mutated = False
        control_map = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

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
        """
        in object/Commas are automatically added between array elements.

        parameter:
            text: Raw JSON text

        Return:
            Tuple[str, bool]: (Repaired text, Is there any modification?)
        """
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

                if in_string:

                    j = i + 1
                    while j < length and text[j] in " \t\r\n":
                        j += 1

                    if j < length:
                        next_ch = text[j]
                        if next_ch in "\"[{" or next_ch.isdigit():


                            has_opener = False
                            for k in range(len(chars) - 1, -1, -1):
                                if chars[k] in "{[":
                                    has_opener = True
                                    break
                                elif chars[k] in "]}":
                                    break

                            if has_opener:
                                chars.append(",")
                                mutated = True

                in_string = not in_string
                i += 1
                continue


            if not in_string and ch in "}]":
                j = i + 1

                while j < length and text[j] in " \t\r\n":
                    j += 1

                if j < length:
                    next_ch = text[j]
                    if next_ch in "{[\"" or next_ch.isdigit():
                        chars.append(",")
                        mutated = True

            i += 1

        return "".join(chars), mutated

    def _collapse_redundant_brackets(self, text: str) -> Tuple[str, bool]:
        """
        Arrays with three or more layers generated for LLM (e.g.]]], [[ / [[[）Make folds and avoid tables/List writes extra dimensions.

        return:
            Tuple[str, bool]: (Repaired text, Is there any modification?)
        """
        if not text:
            return text, False

        mutated = False

        patterns = [

            (re.compile(r"\]\s*\]\s*\]\s*,\s*\[\s*\["), "]],["),

            (re.compile(r"\[\s*\[\s*\["), "[["),

            (re.compile(r"\]\s*\]\s*\]"), "]]"),
        ]

        repaired = text
        for pattern, replacement in patterns:
            new_text, count = pattern.subn(replacement, repaired)
            if count > 0:
                mutated = True
                repaired = new_text

        return repaired, mutated

    def _flatten_nested_arrays(self, text: str) -> str:
        """
        Collapse an obviously redundant one-level list, for example [[[x]]] -> [[x]]。
        """
        if not text:
            return text
        text = re.sub(r"\]\s*\]\s*\]", "]]", text)
        text = re.sub(r"\[\s*\[\s*\[", "[[", text)
        return text

    def _balance_brackets(self, text: str) -> Tuple[str, bool]:
        """
        Try to fix overwriting due to LLM/Unbalanced structure caused by writing less parentheses.

        parameter:
            text: Raw JSON text

        Return:
            Tuple[str, bool]: (Repaired text, Is there any modification?)
        """
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
                if stack and (
                    (ch == "}" and stack[-1] == "{") or (ch == "]" and stack[-1] == "[")
                ):
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

    def _remove_trailing_commas(self, text: str) -> Tuple[str, bool]:
        """
        Remove trailing commas from JSON objects and arrays.

        parameter:
            text: Raw JSON text

        Return:
            Tuple[str, bool]: (Repaired text, Is there any modification?)
        """
        if not text:
            return text, False



        pattern = r",(\s*[}\]])"
        new_text = re.sub(pattern, r"\1", text)

        return new_text, new_text != text

    def _attempt_json_repair(self, text: str, context_name: str) -> Optional[str]:
        """
        Use the json_repair library for advanced repair.

        parameter:
            text: Raw JSON text
            context_name: context name

        Return:
            Optional[str]: Repaired JSON text, returned on failureNone
        """
        if not _json_repair_fn:
            return None

        try:
            fixed = _json_repair_fn(text)
            if fixed and fixed != text:
                logger.info(f"{context_name} Automatic repair using json_repair libraryJSON")
                return fixed
        except Exception as exc:
            logger.debug(f"{context_name} json_repairRepair failed: {exc}")

        return None

    def _attempt_llm_repair(
        self, text: str, error_msg: str, context_name: str
    ) -> Optional[str]:
        """
        JSON repair using LLM.

        parameter:
            text: Raw JSON text
            error_msg: Parse error message
            context_name: context name

        Return:
            Optional[str]: Repaired JSON text, returned on failureNone
        """
        if not self.llm_repair_fn:
            return None

        try:
            logger.info(f"{context_name} Try using LLM to fixJSON")
            repaired = self.llm_repair_fn(text, error_msg)
            if repaired and repaired != text:
                return repaired
        except Exception as exc:
            logger.warning(f"{context_name} LLMRepair failed: {exc}")

        return None

    def _extract_and_validate(
        self,
        data: Any,
        expected_keys: Optional[List[str]],
        extract_wrapper_key: Optional[str],
        context_name: str,
    ) -> Dict[str, Any]:
        """
        Extract and validate JSON data.

        parameter:
            data: parsed data
            expected_keys: expected key list
            extract_wrapper_key: Package key name
            context_name: context name

        Return:
            Dict[str, Any]: Extracted and verified data

        Abnormal:
            JSONParseError: If the data format is not as expected
        """

        if extract_wrapper_key and isinstance(data, dict):
            if extract_wrapper_key in data:
                data = data[extract_wrapper_key]
            else:
                logger.warning(
                    f"{context_name} Package key not found'{extract_wrapper_key}'，Use raw data"
                )


        if not isinstance(data, dict):
            if isinstance(data, list):
                if len(data) > 0:

                    best_match = None
                    max_match_count = 0

                    for item in data:
                        if isinstance(item, dict):
                            if expected_keys:

                                match_count = sum(1 for key in expected_keys if key in item)
                                if match_count > max_match_count:
                                    max_match_count = match_count
                                    best_match = item
                            elif best_match is None:
                                best_match = item

                    if best_match:
                        logger.warning(
                            f"{context_name} Returns an array, automatically extracting the best matching element (matching{max_match_count}/{len(expected_keys or [])}keys）"
                        )
                        data = best_match
                    else:
                        raise JSONParseError(
                            f"{context_name} There are no valid objects in the returned array"
                        )
                else:
                    raise JSONParseError(f"{context_name} Return empty array")
            else:
                raise JSONParseError(
                    f"{context_name} What is returned is not a JSON object: {type(data).__name__}"
                )


        if expected_keys:
            missing_keys = [key for key in expected_keys if key not in data]
            if missing_keys:
                logger.warning(
                    f"{context_name} Expected key missing: {', '.join(missing_keys)}"
                )

                data = self._try_recover_missing_keys(data, missing_keys, context_name)

        return data

    def _try_recover_missing_keys(
        self, data: Dict[str, Any], missing_keys: List[str], context_name: str
    ) -> Dict[str, Any]:
        """
        Attempts to recover missing keys from the data by finding similar key names.

        parameter:
            data: raw data
            missing_keys: Missing key list
            context_name: context name

        Return:
            Dict[str, Any]: Repaired data
        """

        key_aliases = {
            "template_name": ["templateName", "name", "template"],
            "selection_reason": ["selectionReason", "reason", "explanation"],
            "title": ["reportTitle", "documentTitle"],
            "chapters": ["chapterList", "chapterPlan", "sections"],
            "totalWords": ["total_words", "wordCount", "totalWordCount"],
        }

        for missing_key in missing_keys:
            if missing_key in key_aliases:
                for alias in key_aliases[missing_key]:
                    if alias in data:
                        logger.info(
                            f"{context_name} find key'{missing_key}'alias'{alias}'，automatic mapping"
                        )
                        data[missing_key] = data[alias]
                        break

        return data


__all__ = ["RobustJSONParser", "JSONParseError"]
