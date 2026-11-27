"""
Unit tests for ForumEngine.monitor.LogMonitor log parsing and JSON extraction.
"""

import json
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
for _path in (str(TESTS_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import forum_log_test_data as data
from ForumEngine.monitor import LogMonitor


class TestLogMonitor:
    """Tests covering both legacy [HH:MM:SS] and loguru log formats."""

    def setup_method(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.monitor = LogMonitor(log_dir=self._tmpdir.name)

    def test_is_target_log_line_accepts_summary_nodes(self):
        assert self.monitor.is_target_log_line(data.OLD_FORMAT_SINGLE_LINE_JSON) is True
        assert self.monitor.is_target_log_line(data.NEW_FORMAT_FIRST_SUMMARY) is True
        assert self.monitor.is_target_log_line(data.NEW_FORMAT_REFLECTION_SUMMARY) is True

    def test_is_target_log_line_rejects_errors_and_non_targets(self):
        assert self.monitor.is_target_log_line(data.OLD_FORMAT_NON_TARGET) is False
        assert self.monitor.is_target_log_line(data.NEW_FORMAT_NON_TARGET) is False
        assert self.monitor.is_target_log_line(data.SUMMARY_NODE_JSON_ERROR) is False
        assert self.monitor.is_target_log_line(data.SUMMARY_NODE_JSON_FIX_ERROR) is False
        assert self.monitor.is_target_log_line(data.SUMMARY_NODE_ERROR_LOG) is False
        assert self.monitor.is_target_log_line(data.SUMMARY_NODE_TRACEBACK) is False

    def test_is_json_start_and_end_line(self):
        assert self.monitor.is_json_start_line(data.NEW_FORMAT_MULTILINE_JSON[0]) is True
        assert self.monitor.is_json_start_line(data.LINE_WITHOUT_CLEAN_OUTPUT) is False

        assert self.monitor.is_json_end_line("}") is True
        assert self.monitor.is_json_end_line("] }") is True
        assert self.monitor.is_json_end_line("[17:42:31] }") is False
        assert self.monitor.is_json_end_line("2025-11-05 17:42:31.289 }") is False

    def test_extract_json_content_old_and_new_single_line(self):
        old_res = self.monitor.extract_json_content([data.OLD_FORMAT_SINGLE_LINE_JSON])
        new_res = self.monitor.extract_json_content([data.NEW_FORMAT_SINGLE_LINE_JSON])
        assert old_res == "This is the first summary content"
        assert new_res == "This is the first summary content"

    def test_extract_json_content_old_and_new_multiline(self):
        old_res = self.monitor.extract_json_content(data.OLD_FORMAT_MULTILINE_JSON)
        new_res = self.monitor.extract_json_content(data.NEW_FORMAT_MULTILINE_JSON)
        mixed_res = self.monitor.extract_json_content(data.MIXED_FORMAT_LINES)
        assert "This is multiple lines" in old_res
        assert "This is multiple lines" in new_res
        assert mixed_res == "Mixed format content"

    def test_format_json_content_priority(self):
        updated = self.monitor.format_json_content({
            "updated_paragraph_latest_state": "Updated summary",
            "paragraph_latest_state": "Initial summary",
        })
        assert updated == "Updated summary"

        fallback = self.monitor.format_json_content({"other": "value"})
        assert fallback.startswith("Cleaned output:")
        parsed = json.loads(fallback.replace("Cleaned output:", "", 1).strip())
        assert parsed == {"other": "value"}

    def test_extract_node_content(self):
        extracted = self.monitor.extract_node_content(data.NEW_FORMAT_SINGLE_LINE_JSON)
        assert extracted is not None
        assert "This is the first summary content" in extracted
        assert "2025-11-05" not in extracted

    def test_process_lines_for_json_captures_and_filters_errors(self):
        captured_multiline = self.monitor.process_lines_for_json(
            data.REAL_QUERY_ENGINE_REFLECTION, "query"
        )
        assert len(captured_multiline) == 1
        assert "China Molybdenum Group" in captured_multiline[0]

        lines_with_error = [
            data.SUMMARY_NODE_ERROR_LOG,
            data.NEW_FORMAT_FIRST_SUMMARY,
        ]
        captured_after_error = self.monitor.process_lines_for_json(lines_with_error, "insight")
        assert len(captured_after_error) == 1
        assert captured_after_error[0] == "First summary"

    def test_is_valuable_content_and_fix_json_string(self):
        assert self.monitor.is_valuable_content(data.NEW_FORMAT_FIRST_SUMMARY) is True
        assert self.monitor.is_valuable_content(data.LINE_WITHOUT_CLEAN_OUTPUT) is False
        assert self.monitor.is_valuable_content(data.EMPTY_LINE) is False

        broken = '{"paragraph_latest_state": "Quote with "unescaped" word inside"}'
        fixed = self.monitor.fix_json_string(broken)
        assert fixed is not None
        parsed = json.loads(fixed)
        assert "unescaped" in parsed["paragraph_latest_state"]
