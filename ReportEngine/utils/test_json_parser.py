"""
Test various repair capabilities of RobustJSONParser.

Verify that the parser can handle：
1. Basic markdown wrapper
2. Think content cleanup
3. Missing comma fix
4. Fix for unbalanced brackets
5. Control character escaping
6. Trailing comma removal
"""

import json
import unittest
from ReportEngine.utils.json_parser import RobustJSONParser, JSONParseError


class TestRobustJSONParser(unittest.TestCase):
    """Test various repair strategies for a robust JSON parser。"""

    def setUp(self):
        """Initialize the parser。"""
        self.parser = RobustJSONParser(
            enable_json_repair=False,
            enable_llm_repair=False,
        )

    def test_basic_json(self):
        """Test parsing basic legalityJSON。"""
        json_str = '{"name": "test", "value": 123}'
        result = self.parser.parse(json_str, "basic test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_markdown_wrapped(self):
        """Test parsing is```jsonwrappedJSON。"""
        json_str = """```json
{
  "name": "test",
  "value": 123
}
```"""
        result = self.parser.parse(json_str, "Markdownpackage test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_thinking_content_removal(self):
        """Test clear thinking content。"""
        json_str = """<thinking>Let me think about how to construct thisJSON</thinking>
{
  "name": "test",
  "value": 123
}"""
        result = self.parser.parse(json_str, "Thinking About Content Cleanup Testing")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_missing_comma_fix(self):
        """Test fix missing comma。"""

        json_str = """{
  "totalWords": 40000,
  "globalGuidelines": [
    "Focus on the unbalanced distribution of technological dividends"
    "Detailed strategy: technological innovation"
  ],
  "chapters": []
}"""
        result = self.parser.parse(json_str, "Missing comma fix test")
        self.assertEqual(len(result["globalGuidelines"]), 2)

    def test_unbalanced_brackets(self):
        """Test fix bracket imbalance。"""

        json_str = """{
  "name": "test",
  "nested": {
    "value": 123
  }
"""
        result = self.parser.parse(json_str, "Bracket imbalance test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["nested"]["value"], 123)

    def test_control_character_escape(self):
        """Test for escaping control characters。"""

        json_str = """{
  "text": "This is the first line
This is the second line",
  "value": 123
}"""
        result = self.parser.parse(json_str, "Control character escape test")

        self.assertIn("first line", result["text"])
        self.assertIn("second line", result["text"])

    def test_trailing_comma_removal(self):
        """Test removing trailing commas。"""
        json_str = """{
  "name": "test",
  "value": 123,
  "items": [1, 2, 3,],
}"""
        result = self.parser.parse(json_str, "Trailing comma test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(len(result["items"]), 3)

    def test_colon_equals_fix(self):
        """Test fix colon equal sign error。"""
        json_str = """{
  "name":= "test",
  "value": 123
}"""
        result = self.parser.parse(json_str, "colon equal sign test")
        self.assertEqual(result["name"], "test")

    def test_extract_first_json(self):
        """Test to extract the first JSON structure from text。"""
        json_str = """Here are some captions, belowJSON：
{
  "name": "test",
  "value": 123
}
There are some other words behind it"""
        result = self.parser.parse(json_str, "Extract JSON test")
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_unterminated_string_with_json_repair(self):
        """Test to repair unterminated strings using json_repair library。"""

        parser_with_repair = RobustJSONParser(
            enable_json_repair=True,
            enable_llm_repair=False,
        )


        json_str = """{
  "template_name": "specific policy reports",
  "selection_reason": "This is test content"
}"""
        result = parser_with_repair.parse(json_str, "Unterminated string test")

        self.assertIsInstance(result, dict)
        self.assertIn("template_name", result)

    def test_array_with_best_match(self):
        """Test to extract the best matching element from an array。"""
        json_str = """[
  {
    "name": "test",
    "value": 123
  },
  {
    "totalWords": 40000,
    "globalGuidelines": ["guide1", "guide2"],
    "chapters": []
  }
]"""
        result = self.parser.parse(
            json_str,
            "Array best match test",
            expected_keys=["totalWords", "globalGuidelines", "chapters"],
        )

        self.assertEqual(result["totalWords"], 40000)
        self.assertEqual(len(result["globalGuidelines"]), 2)

    def test_key_alias_recovery(self):
        """Test key alias recovery。"""
        json_str = """{
  "templateName": "test_template",
  "selectionReason": "This is a test"
}"""
        result = self.parser.parse(
            json_str,
            "Key alias testing",
            expected_keys=["template_name", "selection_reason"],
        )

        self.assertEqual(result["template_name"], "test_template")
        self.assertEqual(result["selection_reason"], "This is a test")

    def test_complex_real_world_case(self):
        """Test real-world complex cases (similar to actual bugs）。"""

        json_str = """<thinking>I need to construct a space plan</thinking>
```json
{
  "totalWords": 40000,
  "tolerance": 2000,
  "globalGuidelines": [
    "Focus on the unbalanced distribution of technological dividends、Structural contradictions such as brain drain and professional identity crisis"
    "Detailed strategy: the collision of technological innovation and traditional skills"
    "Case-oriented: Prioritize citing real data and research"
  ],
  "chapters": [
    {
      "chapterId": "ch1",
      "targetWords": 5000
    }
  ]
}
```"""
        result = self.parser.parse(json_str, "Complex real case testing")
        self.assertEqual(result["totalWords"], 40000)
        self.assertEqual(result["tolerance"], 2000)
        self.assertEqual(len(result["globalGuidelines"]), 3)
        self.assertEqual(len(result["chapters"]), 1)

    def test_expected_keys_validation(self):
        """Test validation of expected keys。"""
        json_str = '{"name": "test"}'

        result = self.parser.parse(
            json_str, "Key verification test", expected_keys=["name", "value"]
        )
        self.assertIn("name", result)

    def test_wrapper_key_extraction(self):
        """Test extracting data from package key。"""
        json_str = """{
  "wrapper": {
    "name": "test",
    "value": 123
  }
}"""
        result = self.parser.parse(
            json_str, "Wrap key test", extract_wrapper_key="wrapper"
        )
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 123)

    def test_empty_input(self):
        """Test empty input。"""
        with self.assertRaises(JSONParseError):
            self.parser.parse("", "Empty input test")

    def test_invalid_json_after_all_repairs(self):
        """Test situations that all repair strategies fail to handle。"""

        json_str = "{Content that is not in JSON format at all###"
        with self.assertRaises(JSONParseError):
            self.parser.parse(json_str, "Unable to fix test")


def run_manual_test():
    """Run tests manually, print details。"""
    print("=" * 60)
    print("Start testingRobustJSONParser")
    print("=" * 60)

    parser = RobustJSONParser(enable_json_repair=False, enable_llm_repair=False)


    test_case = """```json
{
  "totalWords": 40000,
  "tolerance": 2000,
  "globalGuidelines": [
    "Focus on the unbalanced distribution of technological dividends、Structural contradictions such as brain drain and professional identity crisis"
    "Detailed strategy: the collision of technological innovation and traditional skills"
  ],
  "chapters": []
}
```"""

    print("\ntest case：")
    print(test_case)
    print("\n" + "=" * 60)

    try:
        result = parser.parse(test_case, "Manual testing")
        print("\n✓ Parsed successfully！")
        print("\nParse results：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"\n✗ Parsing failed: {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":

    run_manual_test()


    print("\n\nRun unit tests...")
    unittest.main(verbosity=2)
