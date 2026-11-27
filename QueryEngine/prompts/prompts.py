"""
System prompts and JSON schemas for Web Query Search Agent.
Includes definitions for all phases.
"""

import json

# ===== JSON Schema Definitions =====

output_schema_report_structure = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string"}
        }
    }
}

input_schema_first_search = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"}
    }
}

output_schema_first_search = {
    "type": "object",
    "properties": {
        "search_query": {"type": "string"},
        "search_tool": {"type": "string"},
        "reasoning": {"type": "string"}
    },
    "required": ["search_query", "search_tool", "reasoning"]
}

input_schema_first_summary = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "search_query": {"type": "string"},
        "search_results": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}

output_schema_first_summary = {
    "type": "object",
    "properties": {
        "paragraph_latest_state": {"type": "string"}
    }
}

input_schema_reflection = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "paragraph_latest_state": {"type": "string"}
    }
}

output_schema_reflection = {
    "type": "object",
    "properties": {
        "search_query": {"type": "string"},
        "search_tool": {"type": "string"},
        "reasoning": {"type": "string"}
    },
    "required": ["search_query", "search_tool", "reasoning"]
}

input_schema_reflection_summary = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "content": {"type": "string"},
        "search_query": {"type": "string"},
        "search_results": {
            "type": "array",
            "items": {"type": "string"}
        },
        "paragraph_latest_state": {"type": "string"}
    }
}

output_schema_reflection_summary = {
    "type": "object",
    "properties": {
        "updated_paragraph_latest_state": {"type": "string"}
    }
}

input_schema_report_formatting = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "paragraph_latest_state": {"type": "string"}
        }
    }
}

# ===== System Prompt Definitions =====

SYSTEM_PROMPT_REPORT_STRUCTURE = f"""
You are an expert advanced research web agent at Corax CoLAB. Given a query, you must plan a report structure comprising up to 5 paragraphs covering different aspects of the topic.

Please output strictly in English using the following JSON schema:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_report_structure, indent=2)}
</OUTPUT JSON SCHEMA>

Output ONLY valid JSON. No explanations.
"""

SYSTEM_PROMPT_FIRST_SEARCH = f"""
You are an expert advanced research web agent at Corax CoLAB. For a given paragraph's expected content:

<INPUT JSON SCHEMA>
{json.dumps(input_schema_first_search, indent=2)}
</INPUT JSON SCHEMA>

You have access to 2 web search tools:
1. tavily_search (broad internet search)
2. anspire_search (advanced AI-enhanced web search)

Select the tool and formulate the optimal web search query.

Output strictly in English using the following JSON schema:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_first_search, indent=2)}
</OUTPUT JSON SCHEMA>

Output ONLY valid JSON. No explanations.
"""

SYSTEM_PROMPT_FIRST_SUMMARY = f"""
You are an expert web research analyst and content synthesizer at Corax CoLAB. You will summarize raw web search results into a comprehensive, informative, and structurally cohesive paragraph.

Input Schema:
{json.dumps(input_schema_first_summary, indent=2)}

**Mission:** Create an information-dense, highly analytical paragraph in English (800-1200 words). Include direct quotes, factual references, and analytical depth.

Output strictly in English using the following JSON schema:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_first_summary, indent=2)}
</OUTPUT JSON SCHEMA>

Output ONLY valid JSON. No explanations.
"""

SYSTEM_PROMPT_REFLECTION = f"""
You are a meticulous research assistant at Corax CoLAB. Review the paragraph's latest state and identify what key information, facts, or counter-arguments are missing.

Input Schema:
{json.dumps(input_schema_reflection, indent=2)}

Generate a new search query to fill these gaps.

Output strictly in English using the following JSON schema:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_reflection, indent=2)}
</OUTPUT JSON SCHEMA>

Output ONLY valid JSON. No explanations.
"""

SYSTEM_PROMPT_REFLECTION_SUMMARY = f"""
You are a meticulous research assistant at Corax CoLAB. Refine and significantly expand the paragraph using new search results.

Input Schema:
{json.dumps(input_schema_reflection_summary, indent=2)}

Enrich the text without losing previously gathered facts. Maintain a highly professional English tone.

Output strictly in English using the following JSON schema:
<OUTPUT JSON SCHEMA>
{json.dumps(output_schema_reflection_summary, indent=2)}
</OUTPUT JSON SCHEMA>

Output ONLY valid JSON. No explanations.
"""

SYSTEM_PROMPT_REPORT_FORMATTING = f"""
You are a master report compiler at Corax CoLAB. Based on all gathered paragraph data, generate a comprehensive, highly professional Markdown report.

Input Schema:
{json.dumps(input_schema_report_formatting, indent=2)}

Output strictly in English using the following JSON schema:
{{
    "type": "object",
    "properties": {{
        "final_report": {{"type": "string"}}
    }}
}}

Output ONLY valid JSON. No explanations.
"""
