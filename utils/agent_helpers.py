"""Shared utilities for Deep Search Engine nodes across InsightEngine, MediaEngine, and QueryEngine."""

import json
from json.decoder import JSONDecodeError
from typing import Any, Callable, Dict, Iterable
from loguru import logger

OPTIONAL_SEARCH_NODE_KEYS: tuple[str, ...] = (
    "search_tool",
    "start_date",
    "end_date",
    "platform",
    "time_period",
)


def parse_search_node_output(
    output: str,
    *,
    remove_reasoning_fn: Callable[[str], str],
    clean_json_tags_fn: Callable[[str], str],
    extract_clean_response_fn: Callable[[str], Dict[str, Any]],
    fix_incomplete_json_fn: Callable[[str], str],
    default_fn: Callable[[], Dict[str, Any]],
    extra_keys: Iterable[str] = OPTIONAL_SEARCH_NODE_KEYS,
) -> Dict[str, Any]:
    """
    Parse raw LLM JSON output for FirstSearchNode/ReflectionNode while preserving
    tool selection and filter parameters alongside search_query and reasoning.
    """
    try:
        cleaned_output = remove_reasoning_fn(output)
        cleaned_output = clean_json_tags_fn(cleaned_output)
        logger.info(f"Cleaned output: {cleaned_output}")

        try:
            result = json.loads(cleaned_output)
            logger.info("JSON parsed successfully")
        except JSONDecodeError as exc:
            logger.error(f"JSON parsing failed: {exc}")
            result = extract_clean_response_fn(cleaned_output)
            if "error" in result:
                logger.error("JSON parsing failed, attempting repair...")
                fixed_json = fix_incomplete_json_fn(cleaned_output)
                if not fixed_json:
                    logger.error("Unable to fix JSON, using default query")
                    return default_fn()
                try:
                    result = json.loads(fixed_json)
                    logger.info("JSON repair successful")
                except JSONDecodeError:
                    logger.error("JSON repair failed")
                    return default_fn()

        if not isinstance(result, dict):
            return default_fn()

        search_query = str(result.get("search_query", "") or "").strip()
        reasoning = str(result.get("reasoning", "") or "")
        if not search_query:
            logger.warning("Search query not found, using default query")
            return default_fn()

        parsed: Dict[str, Any] = {
            "search_query": search_query,
            "reasoning": reasoning,
        }
        for key in extra_keys:
            val = result.get(key)
            if val is not None and val != "":
                parsed[key] = val
        return parsed
    except Exception as exc:
        logger.exception(f"Failed to process search node output: {exc}")
        return default_fn()
