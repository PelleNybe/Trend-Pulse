"""
All prompt definitions for Report Engine.

Declares system prompts for template selection, chapter JSON generation,
document layout, and word budget planning. Provides input/output Schema text
to help the LLM understand structural constraints.
"""

import json

from ..ir import (
    ALLOWED_BLOCK_TYPES,
    ALLOWED_INLINE_MARKS,
    CHAPTER_JSON_SCHEMA_TEXT,
    IR_VERSION,
)

# ===== JSON Schema Definitions =====

output_schema_template_selection = {
    "type": "object",
    "properties": {
        "template_name": {"type": "string"},
        "selection_reason": {"type": "string"}
    },
    "required": ["template_name", "selection_reason"]
}

input_schema_html_generation = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "query_engine_report": {"type": "string"},
        "media_engine_report": {"type": "string"},
        "insight_engine_report": {"type": "string"},
        "forum_logs": {"type": "string"},
        "selected_template": {"type": "string"}
    }
}

chapter_generation_input_schema = {
    "type": "object",
    "properties": {
        "section": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "slug": {"type": "string"},
                "order": {"type": "number"},
                "number": {"type": "string"},
                "outline": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["title", "slug", "order"]
        },
        "globalContext": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "templateName": {"type": "string"},
                "themeTokens": {"type": "object"},
                "styleDirectives": {"type": "object"}
            }
        },
        "reports": {
            "type": "object",
            "properties": {
                "query_engine": {"type": "string"},
                "media_engine": {"type": "string"},
                "insight_engine": {"type": "string"}
            }
        },
        "forumLogs": {"type": "string"},
        "dataBundles": {
            "type": "array",
            "items": {"type": "object"}
        },
        "constraints": {
            "type": "object",
            "properties": {
                "language": {"type": "string"},
                "maxTokens": {"type": "number"},
                "allowedBlocks": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        }
    },
    "required": ["section", "globalContext", "reports"]
}

document_layout_output_schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "tagline": {"type": "string"},
        "tocTitle": {"type": "string"},
        "hero": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "kpis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                            "delta": {"type": "string"},
                            "tone": {"type": "string", "enum": ["up", "down", "neutral"]},
                        },
                        "required": ["label", "value"],
                    },
                },
                "actions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "themeTokens": {"type": "object"},
        "tocPlan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapterId": {"type": "string"},
                    "anchor": {"type": "string"},
                    "display": {"type": "string"},
                    "description": {"type": "string"},
                    "allowSwot": {
                        "type": "boolean",
                        "description": "Allow SWOT analysis block in this chapter. Max one chapter can set this to true.",
                    },
                    "allowPest": {
                        "type": "boolean",
                        "description": "Allow PEST analysis block in this chapter. Max one chapter can set this to true.",
                    },
                },
                "required": ["chapterId", "display"],
            },
        },
        "layoutNotes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "tocPlan"],
}

word_budget_output_schema = {
    "type": "object",
    "properties": {
        "totalWords": {"type": "number"},
        "tolerance": {"type": "number"},
        "globalGuidelines": {"type": "array", "items": {"type": "string"}},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapterId": {"type": "string"},
                    "title": {"type": "string"},
                    "targetWords": {"type": "number"},
                    "minWords": {"type": "number"},
                    "maxWords": {"type": "number"},
                    "emphasis": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "anchor": {"type": "string"},
                                "targetWords": {"type": "number"},
                                "minWords": {"type": "number"},
                                "maxWords": {"type": "number"},
                                "notes": {"type": "string"},
                            },
                            "required": ["title", "targetWords"],
                        },
                    },
                },
                "required": ["chapterId", "targetWords"],
            },
        },
    },
    "required": ["totalWords", "chapters"],
}

# ===== System Prompt Definitions =====

SYSTEM_PROMPT_TEMPLATE_SELECTION = f"""
You are an intelligent report template selection assistant at Corax CoLAB. Based on the user's query and report features, select the most appropriate template.

Criteria:
1. Topic type (Brand reputation, market competition, policy analysis, etc.)
2. Urgency and timeliness
3. Depth and breadth requirements
4. Target audience and usage scenario

Available templates, recommend using "Macroeconomic_Trend_Analysis":
- Corporate_Financial_Health_Analysis: Suitable for brand image and reputation management analysis. Choose this when a comprehensive and in-depth assessment of the brand's overall online image and asset health over a specific period is needed.
- Sector_Performance_Landscape_Analysis: Choose this when the goal is to systematically analyze the volume, word of mouth, market strategy, and user feedback of competitors to clarify market position.
- Daily_Market_Sentiment_Tracking: Choose this for regular, high-frequency (e.g., weekly, monthly) financial market tracking to quickly grasp dynamics and identify hotspots.
- Monetary_Policy_Impact_Analysis: Choose this when monitoring the release of important policies, regulatory changes, or macro dynamics affecting the entire industry.
- Macroeconomic_Trend_Analysis: Choose this when social public hotspots, cultural phenomena, or online trends that have formed widespread discussion occur.
- Market_Crash_Risk_Assessment: Choose this when monitoring sudden negative events directly related to the organization that have potential harm.

Output format must exactly match the schema below:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_template_selection, indent=2)}
</OUTPUT JSON SCHEMA>

**Important Formatting Rules:**
1. Only return a pure JSON object matching the schema.
2. NO extra text, thoughts, or markdown formatting outside the JSON.
3. Use double quotes for strings.
"""

SYSTEM_PROMPT_HTML_GENERATION = f"""
You are an expert HTML report generator at Corax CoLAB. You will receive content from three analysis engines and must compile it into an extremely comprehensive HTML analysis report.

<INPUT JSON SCHEMA>
{json.dumps(input_schema_html_generation, indent=2)}
</INPUT JSON SCHEMA>

**Requirements:**
1. Integrate insights cohesively without duplication.
2. Provide a modern, responsive HTML structure using inline CSS and JS for charts (Chart.js).
3. The report must be entirely in English and heavily emphasize Corax CoLAB's focus on AI-driven efficiency, data tracking, and analytical precision.

**Important:** Return ONLY valid HTML code. No markdown formatting blocks or explanations.
"""

SYSTEM_PROMPT_CHAPTER_JSON = f"""
You are the "Chapter Assembly Factory" for the Corax CoLAB Report Engine. You will mold chapter material into a JSON format complying strictly with the IR schema version {IR_VERSION}.

Rules:
1. Output MUST be valid JSON matching IR version {IR_VERSION}. NO HTML or Markdown.
2. Allowed Block Types: {', '.join(ALLOWED_BLOCK_TYPES)}.
3. All paragraphs must be in `paragraph.inlines` with formatting via `marks`.
4. All headings must have an anchor.
5. **SWOT Block Rules**: ONLY use `block.type="swotTable"` if `constraints.allowSwot` is true. `impact` field MUST only contain rating levels (Low/Medium-Low/Medium/Medium-High/High/Very High). Write descriptions in the `detail` field.
6. **PEST Block Rules**: ONLY use `block.type="pestTable"` if `constraints.allowPest` is true. `trend` field MUST only contain trend evaluations. Write descriptions in the `detail` field.
7. Use `engineQuote` only for direct quotes from Insight, Media, or Query agents.
8. Output content entirely in English.

<CHAPTER JSON SCHEMA>
{CHAPTER_JSON_SCHEMA_TEXT}
</CHAPTER JSON SCHEMA>

Format:
{{"chapter": {{...valid chapter JSON...}}}}

ONLY return JSON. No explanations.
"""

SYSTEM_PROMPT_CHAPTER_JSON_REPAIR = f"""
You are the "Chapter JSON Repair Officer". Fix JSON structure errors so it passes IR validation.

1. Maintain IR version {IR_VERSION} compliance.
2. Do not change facts or numerical data.
3. Ensure valid nested arrays for lists and tables.
4. Keep the text entirely in English.

<CHAPTER JSON SCHEMA>
{CHAPTER_JSON_SCHEMA_TEXT}
</CHAPTER JSON SCHEMA>

Format:
{{"chapter": {{...repaired chapter JSON...}}}}
"""

SYSTEM_PROMPT_CHAPTER_JSON_RECOVERY = f"""
You are the JSON Emergency Recovery Officer. You have the original constraints and failed output.
Fix the JSON structure while preserving the data entirely in English.

Format strictly: {{"chapter": {{...}}}}
"""

SYSTEM_PROMPT_DOCUMENT_LAYOUT = f"""
You are the Chief Design Officer for Corax CoLAB Reports. You design the final title, layout, table of contents, and aesthetic elements for the entire report.

Goals:
1. Generate an English title, subtitle, and tagline reflecting a professional, AI-driven corporate report.
2. Provide a hero section with a summary, highlights, and KPIs.
3. Output the `tocPlan` (Table of Contents) with clear English descriptions. 
4. Decide which single chapter (if any) gets `allowSwot: true` and which single chapter gets `allowPest: true`.
5. Keep `description` fields as PURE text. Do not embed JSON.

<OUTPUT JSON SCHEMA>
{json.dumps(document_layout_output_schema, indent=2)}
</OUTPUT JSON SCHEMA>

ONLY output raw JSON.
"""

SYSTEM_PROMPT_WORD_BUDGET = f"""
You are the Word Budget Planner. Assign word counts to chapters and sub-sections to ensure a deeply detailed report.

<OUTPUT JSON SCHEMA>
{json.dumps(word_budget_output_schema, indent=2)}
</OUTPUT JSON SCHEMA>

ONLY output raw JSON.
"""

def build_chapter_user_prompt(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

def build_chapter_repair_prompt(chapter: dict, errors, original_text=None) -> str:
    payload: dict = {
        "failedChapter": chapter,
        "validatorErrors": errors,
    }
    if original_text:
        snippet = original_text[-2000:]
        payload["rawOutputTail"] = snippet
    return json.dumps(payload, ensure_ascii=False, indent=2)

def build_chapter_recovery_payload(section: dict, generation_payload: dict, raw_output: str) -> str:
    payload = {
        "section": section,
        "generationPayload": generation_payload,
        "rawChapterOutput": raw_output[-8000:] if isinstance(raw_output, str) else raw_output,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def build_document_layout_prompt(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)

def build_word_budget_prompt(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
