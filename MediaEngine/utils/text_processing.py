"""
Text processing tool functions
Used to clean LLM output、Parse JSON etc.
"""

import re
import json
from typing import Dict, Any, List
from json.decoder import JSONDecodeError


def clean_json_tags(text: str) -> str:
    """
    Clean JSON tags in text
    
    Args:
        text: original text
        
    Returns:
        Cleaned text
    """

    text = re.sub(r'```(?:json)?\s*|```\s*$', '', text)
    
    return text.strip()


def clean_markdown_tags(text: str) -> str:
    """
    Clean Markdown tags in text
    
    Args:
        text: original text
        
    Returns:
        Cleaned text
    """

    text = re.sub(r'```(?:markdown)?\s*|```\s*$', '', text)
    
    return text.strip()


def remove_reasoning_from_output(text: str) -> str:
    """
    Remove inference process text from output
    
    Args:
        text: original text
        
    Returns:
        Cleaned text
    """

    json_start = -1
    
    for i, char in enumerate(text):
        if char in '{[':
            json_start = i
            break
    
    if json_start != -1:
        return text[json_start:].strip()
    
    patterns = [
        r'(?:reasoning|reasoning|think|analyze)[:：]\s*.*?(?=\{|\[|$)',
        r'(?:explanation|explain|illustrate)[:：]\s*.*?(?=\{|\[|$)',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
    
    return text.strip()


def extract_clean_response(text: str) -> Dict[str, Any]:
    """
    Extract and clean the JSON content in the response
    
    Args:
        text: original response text
        
    Returns:
        Parsed JSON dictionary
    """

    cleaned_text = clean_json_tags(text)
    cleaned_text = remove_reasoning_from_output(cleaned_text)
    

    try:
        return json.loads(cleaned_text)
    except JSONDecodeError:
        pass
    

    fixed_text = fix_incomplete_json(cleaned_text)
    if fixed_text:
        try:
            return json.loads(fixed_text)
        except JSONDecodeError:
            pass
    

    json_pattern = r'\{.*\}'
    match = re.search(json_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass
    

    array_pattern = r'\[.*\]'
    match = re.search(array_pattern, cleaned_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except JSONDecodeError:
            pass

    # ⚡ OPTIMIZATION: Fallback to aggressive JSON structural repair for malformed LLM outputs
    aggressive_fixed = fix_aggressive_json(cleaned_text)
    if aggressive_fixed:
        try:
            return json.loads(aggressive_fixed)
        except JSONDecodeError:
            pass
    

    print(f"Unable to parse JSON response: {cleaned_text[:200]}...")
    return {"error": "JSONParsing failed", "raw_text": cleaned_text}


def fix_incomplete_json(text: str) -> str:
    """
    Fix incomplete JSON response
    
    Args:
        text: original text
        
    Returns:
        Repaired JSON text，Returns an empty string if it cannot be repaired
    """

    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    

    try:
        json.loads(text)
        return text
    except JSONDecodeError:
        pass
    

    if text.strip().startswith('{') and not text.strip().startswith('['):

        if text.count('{') > 1:

            text = '[' + text + ']'
        else:

            text = '[' + text + ']'
    

    if text.strip().endswith('}') and not text.strip().endswith(']'):

        if text.count('}') > 1:

            text = '[' + text + ']'
        else:

            text = '[' + text + ']'
    

    open_braces = text.count('{')
    close_braces = text.count('}')
    open_brackets = text.count('[')
    close_brackets = text.count(']')
    

    if open_braces > close_braces:
        text = f"{text}{'}' * (open_braces - close_braces)}"
    if open_brackets > close_brackets:
        text = f"{text}{']' * (open_brackets - close_brackets)}"
    

    try:
        json.loads(text)
        return text
    except JSONDecodeError:

        return fix_aggressive_json(text)


def fix_aggressive_json(text: str) -> str:
    """
    More radical JSON repair methods, using brace counting to support nested structures.
    """
    results = []
    i = 0
    while i < len(text):
        if text[i] == '{':
            start_idx = i
            count = 1
            i += 1
            while i < len(text):
                if text[i] == '{':
                    count += 1
                elif text[i] == '}':
                    count -= 1
                    if count == 0:
                        results.append(text[start_idx:i+1])
                        break
                i += 1
            if count != 0:
                break # unclosed brace
        i += 1

    if not results:
        return "[]"
    elif len(results) == 1:
        return f"[{results[0]}]"
    else:
        return f"[{','.join(results)}]"
    
def update_state_with_search_results(search_results: List[Dict[str, Any]], 
                                   paragraph_index: int, state: Any) -> Any:
    """
    Update search results to status
    
    Args:
        search_results: search results list
        paragraph_index: paragraph index
        state: state object
        
    Returns:
        updated state object
    """
    if 0 <= paragraph_index < len(state.paragraphs):

        current_query = ""
        if search_results:

            current_query = "search query"
        

        state.paragraphs[paragraph_index].research.add_search_results(
            current_query, search_results
        )
    
    return state


def validate_json_schema(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """
    Verify that JSON data contains required fields
    
    Args:
        data: data to be verified
        required_fields: list of required fields
        
    Returns:
        Verification passed
    """
    return all(field in data for field in required_fields)


def truncate_content(content: str, max_length: int = 20000) -> str:
    """
    Truncate content to specified length
    
    Args:
        content: original content
        max_length: maximum length
        
    Returns:
        Truncated content
    """
    if len(content) <= max_length:
        return content
    

    truncated = content[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > (max_length * 4) // 5:
        return truncated[:last_space] + "..."
    else:
        return truncated + "..."


def format_search_results_for_prompt(search_results: List[Dict[str, Any]], 
                                   max_length: int = 20000) -> List[str]:
    """
    Format search results for prompt words
    
    Args:
        search_results: search results list
        max_length: the maximum length of each result
        
    Returns:
        Formatted content list
    """
    formatted_results = []
    
    for result in search_results:
        content = result.get('content', '')
        if content:
            truncated_content = truncate_content(content, max_length)
            formatted_results.append(truncated_content)
    
    return formatted_results