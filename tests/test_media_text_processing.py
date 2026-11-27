import sys
import os
import pytest

# Add the MediaEngine/utils directory directly to sys.path to bypass __init__.py which fails on import due to loguru
utils_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../MediaEngine/utils'))
sys.path.insert(0, utils_path)

from text_processing import truncate_content

def test_truncate_content_short():
    """Test that content shorter than max_length is returned unmodified."""
    content = "This is a short string."
    assert truncate_content(content, max_length=100) == content

def test_truncate_content_exact_length():
    """Test that content exactly equal to max_length is returned unmodified."""
    content = "0123456789"
    assert truncate_content(content, max_length=10) == content

def test_truncate_content_long_no_space():
    """Test truncation when content exceeds max_length and contains no spaces."""
    content = "a" * 100
    expected = ("a" * 50) + "..."
    assert truncate_content(content, max_length=50) == expected

def test_truncate_content_long_with_space_near_end():
    """
    Test truncation when content exceeds max_length and the last space
    is located within the last 20% of max_length (i.e. index > 40 for max_length 50).
    """
    # 45 'a's, followed by a space, followed by 10 'b's
    # total length 56
    # truncated to 50: "a" * 45 + " " + "b" * 4
    # The space is at index 45, which is > 50 * 0.8 (40).
    # So it truncates AT the space.
    content = "a" * 45 + " " + "b" * 10
    expected = "a" * 45 + "..."
    assert truncate_content(content, max_length=50) == expected

def test_truncate_content_long_with_space_early():
    """
    Test truncation when content exceeds max_length and the last space
    is located before the last 20% of max_length (i.e. index <= 40 for max_length 50).
    """
    # 30 'a's, followed by a space, followed by 30 'b's
    # total length 61
    # truncated to 50: "a" * 30 + " " + "b" * 19
    # The space is at index 30, which is NOT > 50 * 0.8 (40).
    # So it truncates at max_length.
    content = "a" * 30 + " " + "b" * 30
    expected = "a" * 30 + " " + "b" * 19 + "..."
    assert truncate_content(content, max_length=50) == expected

def test_truncate_content_empty_string():
    """Test that empty string returns empty string."""
    assert truncate_content("", max_length=10) == ""

def test_remove_reasoning_from_output_basic():
    from text_processing import remove_reasoning_from_output
    text = "reasoning: I am thinking... {\"key\": \"value\"}"
    assert remove_reasoning_from_output(text) == '{"key": "value"}'

def test_remove_reasoning_from_output_no_json():
    from text_processing import remove_reasoning_from_output
    text = "reasoning: I am thinking..."
    assert remove_reasoning_from_output(text) == ''

def test_remove_reasoning_from_output_no_reasoning():
    from text_processing import remove_reasoning_from_output
    text = "Just some plain text."
    assert remove_reasoning_from_output(text) == "Just some plain text."

def test_remove_reasoning_from_output_with_brackets():
    from text_processing import remove_reasoning_from_output
    text = "analyze: something [1, 2, 3]"
    assert remove_reasoning_from_output(text) == "[1, 2, 3]"


def test_remove_reasoning_from_output_various_patterns():
    from text_processing import remove_reasoning_from_output
    text = "explain: the process\nAnd more"
    assert remove_reasoning_from_output(text) == ""
    text2 = "reasoning：this is some chinese colon"
    assert remove_reasoning_from_output(text2) == ""
    text3 = "explain:\nThis is a multiline\nexplanation."
    assert remove_reasoning_from_output(text3) == ""


def test_remove_reasoning_from_output_with_preceding_text():
    from text_processing import remove_reasoning_from_output
    text = "Here is my reasoning: bla bla \n {\"key\": \"value\"}"
    assert remove_reasoning_from_output(text) == '{"key": "value"}'

def test_remove_reasoning_from_output_starts_with_json():
    from text_processing import remove_reasoning_from_output
    text = "{\"key\": \"value\"} with some trailing text"
    assert remove_reasoning_from_output(text) == "{\"key\": \"value\"} with some trailing text"

def test_remove_reasoning_from_output_only_spaces():
    from text_processing import remove_reasoning_from_output
    text = "   \n  \t  "
    assert remove_reasoning_from_output(text) == ""
