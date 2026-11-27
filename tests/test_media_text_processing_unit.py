import sys
from pathlib import Path
import unittest

project_root = Path(__file__).parent.parent
media_utils_path = project_root / "MediaEngine" / "utils"
sys.path.insert(0, str(media_utils_path))

# Bypass heavy dependencies by adding the directory directly and importing the module
import text_processing

class TestMediaTextProcessing(unittest.TestCase):
    def test_validate_json_schema_happy_path(self):
        """Test with all required fields present."""
        data = {"field1": "value1", "field2": "value2"}
        required = ["field1", "field2"]
        self.assertTrue(text_processing.validate_json_schema(data, required))

    def test_validate_json_schema_missing_field(self):
        """Test with one missing required field."""
        data = {"field1": "value1"}
        required = ["field1", "field2"]
        self.assertFalse(text_processing.validate_json_schema(data, required))

    def test_validate_json_schema_empty_data(self):
        """Test with empty data dictionary."""
        data = {}
        required = ["field1"]
        self.assertFalse(text_processing.validate_json_schema(data, required))

    def test_validate_json_schema_empty_required(self):
        """Test with empty required fields list."""
        data = {"field1": "value1"}
        required = []
        self.assertTrue(text_processing.validate_json_schema(data, required))

    def test_validate_json_schema_extra_fields(self):
        """Test with extra fields not in required list."""
        data = {"field1": "value1", "field2": "value2", "field3": "value3"}
        required = ["field1", "field2"]
        self.assertTrue(text_processing.validate_json_schema(data, required))




    def test_remove_reasoning_from_output_with_brace(self):
        """Test with reasoning text followed by an object."""
        text = "Here is my reasoning: bla bla \n {\"key\": \"value\"}"
        expected = "{\"key\": \"value\"}"
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_from_output_with_bracket(self):
        """Test with reasoning text followed by an array."""
        text = "Thinking process... [1, 2, 3]"
        expected = "[1, 2, 3]"
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_from_output_starts_with_json(self):
        """Test when text already starts with JSON."""
        text = "{\"key\": \"value\"} with some trailing text"
        expected = "{\"key\": \"value\"} with some trailing text"
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_from_output_no_json(self):
        """Test with no JSON braces or brackets."""
        text = "Just some regular text without any json"
        expected = "Just some regular text without any json"
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_from_output_empty(self):
        """Test with empty string."""
        text = ""
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_from_output_only_spaces(self):
        """Test with only whitespace."""
        text = "   \n  \t  "
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)


    def test_remove_reasoning_regex_reasoning(self):
        """Test removing reasoning without braces."""
        text = "reasoning: I am thinking."
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_think(self):
        """Test removing think without braces."""
        text = "think: some process"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_analyze_chinese_colon(self):
        """Test removing analyze with Chinese colon."""
        text = "analyze： analysis text"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_explanation(self):
        """Test removing explanation without braces."""
        text = "explanation: explanation text"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_explain(self):
        """Test removing explain without braces."""
        text = "explain: explain text"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_illustrate_chinese_colon(self):
        """Test removing illustrate with Chinese colon."""
        text = "illustrate： illustrate text"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_case_insensitive(self):
        """Test removing case insensitive keywords."""
        text = "ReAsonInG: mixed case"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_multiple_lines(self):
        """Test removing reasoning across multiple lines."""
        text = "reasoning:\nline 1\nline 2"
        expected = ""
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_remove_reasoning_regex_leaves_preceding_text(self):
        """Test that text before the reasoning keyword is preserved."""
        text = "Some intro text. reasoning: I think..."
        expected = "Some intro text."
        self.assertEqual(text_processing.remove_reasoning_from_output(text), expected)

    def test_format_search_results_happy_path(self):
        """Test with normal search results."""
        results = [
            {"content": "Result 1 content"},
            {"content": "Result 2 content"}
        ]
        formatted = text_processing.format_search_results_for_prompt(results)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0], "Result 1 content")
        self.assertEqual(formatted[1], "Result 2 content")

    def test_format_search_results_empty_list(self):
        """Test with empty search results."""
        results = []
        formatted = text_processing.format_search_results_for_prompt(results)
        self.assertEqual(len(formatted), 0)
        self.assertEqual(formatted, [])

    def test_format_search_results_missing_content(self):
        """Test with results missing the 'content' key or having empty content."""
        results = [
            {"title": "Result 1 title"},
            {"content": ""},
            {"content": "Valid content"}
        ]
        formatted = text_processing.format_search_results_for_prompt(results)
        self.assertEqual(len(formatted), 1)
        self.assertEqual(formatted[0], "Valid content")

    def test_format_search_results_truncation(self):
        """Test with results that need truncation."""
        results = [
            {"content": "This is a very long text that needs to be truncated"},
            {"content": "Short text"}
        ]
        formatted = text_processing.format_search_results_for_prompt(results, max_length=15)
        self.assertEqual(len(formatted), 2)
        self.assertEqual(formatted[0], "This is a very...")
        self.assertEqual(formatted[1], "Short text")

    def test_fix_aggressive_json_multiple_objects(self):
        """Test with multiple JSON objects in text."""
        text = 'Text before {"a": 1} text between {"b": 2} text after'
        fixed = text_processing.fix_aggressive_json(text)
        self.assertEqual(fixed, '[{"a": 1},{"b": 2}]')

    def test_fix_aggressive_json_single_object(self):
        """Test with a single JSON object in text."""
        text = 'Some text {"key": "value"}'
        fixed = text_processing.fix_aggressive_json(text)
        self.assertEqual(fixed, '[{"key": "value"}]')

    def test_fix_aggressive_json_no_objects(self):
        """Test with no JSON objects in text."""
        text = 'Just regular text with no braces'
        fixed = text_processing.fix_aggressive_json(text)
        self.assertEqual(fixed, '[]')

    def test_fix_aggressive_json_nested_objects_limitation(self):
        """
        Test with nested JSON objects.
        Current implementation uses a regex that doesn't handle nesting correctly,
        it only finds the innermost balanced braces.
        """
        text = '{"outer": {"inner": 1}}'
        fixed = text_processing.fix_aggressive_json(text)
        # Regex \{[^{}]*\} matches {"inner": 1}
        self.assertEqual(fixed, '[{"outer": {"inner": 1}}]')

    def test_truncate_content_no_truncation(self):
        """Test with content shorter than max_length."""
        content = "Short content"
        truncated = text_processing.truncate_content(content, max_length=20)
        self.assertEqual(truncated, content)

    def test_truncate_content_exact_length(self):
        """Test with content length exactly equal to max_length."""
        content = "Exact length 15!!"
        truncated = text_processing.truncate_content(content, max_length=17)
        self.assertEqual(truncated, content)

    def test_truncate_content_with_space_in_80_percent(self):
        """Test truncation at last space when it's within the last 20% of max_length."""
        # max_length = 10. 80% threshold is 8.
        # content = "123456789 0123"
        # truncated substring = "123456789 " (len 10)
        # last_space index = 9. 9 > 8 is True.
        # expected: "123456789..."
        content = "123456789 0123"
        truncated = text_processing.truncate_content(content, max_length=10)
        self.assertEqual(truncated, "123456789...")

    def test_truncate_content_with_space_before_80_percent(self):
        """Test truncation at max_length when last space is before the last 20%."""
        # max_length = 10. 80% threshold is 8.
        # content = "12345 67890123"
        # truncated substring = "12345 6789" (len 10)
        # last_space index = 5. 5 > 8 is False.
        # expected: "12345 6789..."
        content = "12345 67890123"
        truncated = text_processing.truncate_content(content, max_length=10)
        self.assertEqual(truncated, "12345 6789...")

    def test_truncate_content_no_space(self):
        """Test truncation when no space is found in the truncated part."""
        content = "123456789012345"
        truncated = text_processing.truncate_content(content, max_length=10)
        self.assertEqual(truncated, "1234567890...")

    def test_truncate_content_default_max_length(self):
        """Test with default max_length (20000)."""
        content = "A" * 20001
        truncated = text_processing.truncate_content(content)
        self.assertEqual(len(truncated), 20003) # 20000 + "..."
        self.assertTrue(truncated.endswith("..."))

if __name__ == "__main__":
    unittest.main()
