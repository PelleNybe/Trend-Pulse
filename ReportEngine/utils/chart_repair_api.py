"""
Chart API fix module.

Provides 4 callsEngine（ReportEngine, ForumEngine, InsightEngine, MediaEngine）LLM API
To repair the function of chart data。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from loguru import logger

from config import settings



CHART_REPAIR_SYSTEM_PROMPT = """You are a professional chart data repair assistant. Your job is to fixChart.jsFormat Error in chart data, ensure that the chart can be rendered normally。

**Chart.jsstandard data format：**

1. standard chart（line, bar, pie, doughnut, radar, polarArea）：
```json
{
  "type": "widget",
  "widgetType": "chart.js/bar",
  "widgetId": "chart-001",
  "props": {
    "type": "bar",
    "title": "Chart title",
    "options": {
      "responsive": true,
      "plugins": {
        "legend": {
          "display": true
        }
      }
    }
  },
  "data": {
    "labels": ["A", "B", "C"],
    "datasets": [
      {
        "label": "series1",
        "data": [10, 20, 30]
      }
    ]
  }
}
```

2. special chart（scatter, bubble）：
```json
{
  "data": {
    "datasets": [
      {
        "label": "series1",
        "data": [
          {"x": 10, "y": 20},
          {"x": 15, "y": 25}
        ]
      }
    ]
  }
}
```

**Restoration Principle：**
1. **I would rather not change than correct my mistakes.** - If not sure how to fix, keep the original data
2. **minimal changes** - Only fix clear Errors, don’t overdo it
3. **Maintain data integrity** - Don't lose the original data
4. **Verify repair results** - Make sure it meets the requirements after repairChart.jsFormat

**Common Errors and Repair Methods：**
1. labels field missing → Generate defaults based on datalabels
2. datasetsnot an array → Convert to array format
3. Data length mismatch → Truncate or fillnull
4. non-numeric data → Try converting or setting tonull
5. Missing required field → Add default value

Please repair the chart data based on the Error information and return the repaired complete widget block (JSON format）。
"""



TABLE_REPAIR_SYSTEM_PROMPT = """You are a professional table data repair assistant. Your task is to fix the format error in the IR table data and ensure that the table can be rendered normally.。

**Standard tabular data format：**

```json
{
  "type": "table",
  "rows": [
    {
      "cells": [
        {
          "header": true,
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "Column header", "marks": []}]
            }
          ]
        },
        {
          "header": true,
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "another column", "marks": []}]
            }
          ]
        }
      ]
    },
    {
      "cells": [
        {
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "Data content", "marks": []}]
            }
          ]
        },
        {
          "blocks": [
            {
              "type": "paragraph",
              "inlines": [{"text": "another data", "marks": []}]
            }
          ]
        }
      ]
    }
  ]
}
```

**⚠️ Common Error: Nested cells structure**

This is a very common Error. LLM often nests cells at the same level Error：

❌ **ErrorExample：**
```json
{
  "cells": [
    { "blocks": [...], "colspan": 1 },
    { "cells": [
        { "blocks": [...] },
        { "cells": [...] }
      ]
    }
  ]
}
```

✅ **Correct format：**
```json
{
  "cells": [
    { "blocks": [...], "colspan": 1 },
    { "blocks": [...] },
    { "blocks": [...] }
  ]
}
```

**Restoration Principle：**
1. **flatten nested cells** - Flatten Error nested cells to siblings
2. **Make sure each cell has blocks** - Each cell must have blocks array
3. **blocks For internal use paragraph** - Text content should be placed within paragraph block
4. **Maintain data integrity** - Don't lose the original content

**Fix：**
1. Nested cells structure → Flatten to sibling cells array
2. Missing blocks field → Add containing paragraph blocks
3. empty cells array → Add default empty cells
4. Illegal cell type → Convert to standard format

Please repair the table data according to the Error information and return the complete table block after repair (JSON format）。
"""



WORDCLOUD_REPAIR_SYSTEM_PROMPT = """You are a professional word cloud data repair assistant. Your task is to fix the format error in the word cloud widget data and ensure that the word cloud can be rendered normally.。

**Standard word cloud data format：**

```json
{
  "type": "widget",
  "widgetType": "wordcloud",
  "widgetId": "wordcloud-001",
  "title": "word cloud title",
  "data": {
    "words": [
      {"text": "keywords1", "weight": 10},
      {"text": "keywords2", "weight": 8},
      {"text": "keywords3", "weight": 6}
    ]
  }
}
```

**⚠️ Data path description：**

Word cloud data can be located in the following paths (in order of priority）：
1. `data.words` - Recommended path
2. `data.items` - alternative path
3. `props.words` - alternative path
4. `props.items` - alternative path
5. `props.data` - alternative path

**Word Cloud Project Format：**

Each word cloud item should be an object containing：
- `text` or `word` or `label`: word text (required）
- `weight` or `value`: weight/Frequency (required）
- `category`: Category (optional）

**Restoration Principle：**
1. **Normalized data path** - priority use `data.words`
2. **Ensure required fields** - Each term must have text and weight
3. **Convert compatible formats** - Convert other formats to standard formats
4. **Maintain data integrity** - Don't lose the original words

**Common Errors and Repair Methods：**
1. Data is located in Error path → move to `data.words`
2. Missing weight field → Generate default weights based on location
3. use word instead of text → Unify into text field
4. Array elements are strings → Convert to object format

Please repair the word cloud data according to the Error information and return the complete widget block after repair (JSON format）。
"""


def build_table_repair_prompt(
    table_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """
    Build table repair prompt words。

    Args:
        table_block: original table block
        validation_errors: Verification Error list

    Returns:
        str: prompt word
    """
    block_json = json.dumps(table_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix the following table dataError：

**raw data：**
```json
{block_json}
```

**detectedError：**
{errors_text}

**Require：**
1. Return the complete table block after repair (JSON format）
2. Pay special attention to flattening the nested cells structure
3. Make sure each cell has a blocks array
4. If you cannot determine how to fix it, keep the original data

**Important output format requirements：**
1. Only return pure JSON objects, do not add any description text
2. Do not use```json```mark package
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings
"""
    return prompt


def build_wordcloud_repair_prompt(
    widget_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """
    Build word cloud to repair prompt words。

    Args:
        widget_block: original wordcloud widget block
        validation_errors: Verification Error list

    Returns:
        str: prompt word
    """
    block_json = json.dumps(widget_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix the following word cloud dataError：

**raw data：**
```json
{block_json}
```

**detectedError：**
{errors_text}

**Require：**
1. Returns the complete widget block after repair (JSON format）
2. Make sure the word cloud data is located in data.words path
3. Each term must have text and weight fields
4. If you cannot determine how to fix it, keep the original data

**Important output format requirements：**
1. Only return pure JSON objects, do not add any description text
2. Do not use```json```mark package
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings
"""
    return prompt


def build_chart_repair_prompt(
    widget_block: Dict[str, Any],
    validation_errors: List[str]
) -> str:
    """
    Build diagram repair prompt words。

    Args:
        widget_block: originalwidget block
        validation_errors: Verification Error list

    Returns:
        str: prompt word
    """
    block_json = json.dumps(widget_block, ensure_ascii=False, indent=2)
    errors_text = "\n".join(f"- {error}" for error in validation_errors)

    prompt = f"""Please fix the following chart dataError：

**raw data：**
```json
{block_json}
```

**detectedError：**
{errors_text}

**Require：**
1. Return the repaired complete widget block (JSON format）
2. Only fix explicit Errors, leaving other data unchanged
3. Make sure the repaired data conforms toChart.jsFormat requirements
4. If you cannot determine how to fix it, keep the original data

**Important output format requirements：**
1. Only return pure JSON objects, do not add any description text
2. Do not use```json```mark package
3. Make sure the JSON syntax is completely correct
4. Use double quotes for all strings
"""
    return prompt


def create_llm_repair_functions() -> List:
    """
    Create a list of LLM repair functions.

    Returns the repair function of 4 Engines：
    1. ReportEngine
    2. ForumEngine (passForumHost)
    3. InsightEngine
    4. MediaEngine

    Returns:
        List[Callable]: Fix function list
    """
    repair_functions = []


    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_with_report_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Repair charts using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None


                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngineChart repair failed: {e}")
                return None

        repair_functions.append(repair_with_report_engine)
        logger.debug("ReportEngine chart repair function added")


    if settings.FORUM_HOST_API_KEY and settings.FORUM_HOST_BASE_URL:
        def repair_with_forum_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix charts using ForumEngine’s LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.FORUM_HOST_API_KEY,
                    base_url=settings.FORUM_HOST_BASE_URL,
                    model_name=settings.FORUM_HOST_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ForumEngineChart repair failed: {e}")
                return None

        repair_functions.append(repair_with_forum_engine)
        logger.debug("ForumEngine chart repair function added")


    if settings.INSIGHT_ENGINE_API_KEY and settings.INSIGHT_ENGINE_BASE_URL:
        def repair_with_insight_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Repair charts using InsightEngine’s LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.INSIGHT_ENGINE_API_KEY,
                    base_url=settings.INSIGHT_ENGINE_BASE_URL,
                    model_name=settings.INSIGHT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"InsightEngineChart repair failed: {e}")
                return None

        repair_functions.append(repair_with_insight_engine)
        logger.debug("InsightEngine chart repair function added")


    if settings.MEDIA_ENGINE_API_KEY and settings.MEDIA_ENGINE_BASE_URL:
        def repair_with_media_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix charts using MediaEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.MEDIA_ENGINE_API_KEY,
                    base_url=settings.MEDIA_ENGINE_BASE_URL,
                    model_name=settings.MEDIA_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_chart_repair_prompt(widget_block, errors)
                response = client.invoke(
                    CHART_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None

                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"MediaEngineChart repair failed: {e}")
                return None

        repair_functions.append(repair_with_media_engine)
        logger.debug("MediaEngine chart repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, chart API fix functionality will not be available")
    else:
        logger.info(f"Chart API fixes enabled, total {len(repair_functions)} Engines available")

    return repair_functions


def create_table_repair_functions() -> List:
    """
    Create a tabular LLM repair function list.

    Use the same Engine configuration as the chart fix。

    Returns:
        List[Callable]: Fix function list
    """
    repair_functions = []


    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_table_with_report_engine(table_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Repair tables using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_table_repair_prompt(table_block, errors)
                response = client.invoke(
                    TABLE_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None


                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngine Table repair failed: {e}")
                return None

        repair_functions.append(repair_table_with_report_engine)
        logger.debug("ReportEngine table repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, table API fixes will not be available")
    else:
        logger.info(f"Tables API fixes enabled, total {len(repair_functions)} Engines available")

    return repair_functions


def create_wordcloud_repair_functions() -> List:
    """
    Create a word cloud list of LLM repair functions.

    Use the same Engine configuration as the chart fix。

    Returns:
        List[Callable]: Fix function list
    """
    repair_functions = []


    if settings.REPORT_ENGINE_API_KEY and settings.REPORT_ENGINE_BASE_URL:
        def repair_wordcloud_with_report_engine(widget_block: Dict[str, Any], errors: List[str]) -> Optional[Dict[str, Any]]:
            """Fix word cloud using ReportEngine's LLM"""
            try:
                from ReportEngine.llms import LLMClient

                client = LLMClient(
                    api_key=settings.REPORT_ENGINE_API_KEY,
                    base_url=settings.REPORT_ENGINE_BASE_URL,
                    model_name=settings.REPORT_ENGINE_MODEL_NAME or "gpt-4",
                )

                prompt = build_wordcloud_repair_prompt(widget_block, errors)
                response = client.invoke(
                    WORDCLOUD_REPAIR_SYSTEM_PROMPT,
                    prompt,
                    temperature=0.0,
                    top_p=0.05
                )

                if not response:
                    return None


                repaired = json.loads(response)
                return repaired

            except Exception as e:
                logger.exception(f"ReportEngine Word cloud repair failed: {e}")
                return None

        repair_functions.append(repair_wordcloud_with_report_engine)
        logger.debug("ReportEngine word cloud repair function added")

    if not repair_functions:
        logger.warning("No Engine API is configured, word cloud API fix functionality will not be available")
    else:
        logger.info(f"The word cloud API fix feature has been enabled for a total of {len(repair_functions)} Engines available")

    return repair_functions
