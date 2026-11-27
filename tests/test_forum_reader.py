import sys
import os
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Mock loguru to avoid missing dependency
sys.modules['loguru'] = MagicMock()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.forum_reader import (
    get_latest_host_speech,
    get_all_host_speeches,
    get_recent_agent_speeches,
    format_host_speech_for_prompt
)

class TestForumReader(unittest.TestCase):
    def test_get_latest_host_speech_directory_not_found(self):
        """Test that get_latest_host_speech returns None when directory does not exist"""
        result = get_latest_host_speech("/path/that/absolutely/does/not/exist/ever/123456")
        self.assertIsNone(result)

    def test_get_latest_host_speech_file_not_found(self):
        """Test that get_latest_host_speech returns None when directory exists but file doesn't"""
        with patch('pathlib.Path.exists', return_value=False):
             result = get_latest_host_speech("/fake/dir")
             self.assertIsNone(result)

    def test_get_latest_host_speech_success(self):
        mock_file_content = "[12:00:00] [HOST] First speech\n[12:01:00] [HOST] Second speech\n[12:02:00] [INSIGHT] Insight says something\n"
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                result = get_latest_host_speech("/fake/dir")
                self.assertEqual(result, "Second speech")

    def test_get_all_host_speeches_success(self):
        mock_file_content = "[12:00:00] [HOST] First speech\n[12:01:00] [HOST] Second speech\n[12:02:00] [INSIGHT] Insight says something\n"
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                result = get_all_host_speeches("/fake/dir")
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0]['timestamp'], "12:00:00")
                self.assertEqual(result[0]['content'], "First speech")
                self.assertEqual(result[1]['timestamp'], "12:01:00")
                self.assertEqual(result[1]['content'], "Second speech")

    def test_get_all_host_speeches_not_found(self):
        with patch('pathlib.Path.exists', return_value=False):
            result = get_all_host_speeches("/fake/dir")
            self.assertEqual(result, [])

    def test_get_recent_agent_speeches_success(self):
        mock_file_content = "[12:00:00] [HOST] First speech\n[12:01:00] [INSIGHT] Insight says something\n[12:02:00] [MEDIA] Media says something\n"
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                result = get_recent_agent_speeches("/fake/dir")
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0]['agent'], "INSIGHT")
                self.assertEqual(result[0]['content'], "Insight says something")
                self.assertEqual(result[1]['agent'], "MEDIA")
                self.assertEqual(result[1]['content'], "Media says something")

    def test_get_recent_agent_speeches_limit(self):
        mock_file_content = "[12:00:00] [QUERY] Speech 1\n[12:01:00] [INSIGHT] Speech 2\n[12:02:00] [MEDIA] Speech 3\n"
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                result = get_recent_agent_speeches("/fake/dir", limit=2)
                self.assertEqual(len(result), 2)
                self.assertEqual(result[0]['content'], "Speech 2")
                self.assertEqual(result[1]['content'], "Speech 3")

    def test_get_recent_agent_speeches_not_found(self):
        with patch('pathlib.Path.exists', return_value=False):
            result = get_recent_agent_speeches("/fake/dir")
            self.assertEqual(result, [])

    def test_format_host_speech_for_prompt_success(self):
        speech = "This is a summary."
        result = format_host_speech_for_prompt(speech)
        self.assertIn(speech, result)
        self.assertIn("The following is the forum moderator", result)

    def test_format_host_speech_for_prompt_empty(self):
        result = format_host_speech_for_prompt("")
        self.assertEqual(result, "")

    def test_format_host_speech_for_prompt_none(self):
        result = format_host_speech_for_prompt(None)
        self.assertEqual(result, "")


    def test_get_latest_host_speech_no_host_statement(self):
        """Test get_latest_host_speech when file exists but has no HOST statement"""
        mock_file_content = "[12:00:00] [INSIGHT] Something\n"
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=mock_file_content)):
                result = get_latest_host_speech("/fake/dir")
                self.assertIsNone(result)

    def test_get_latest_host_speech_exception(self):
        """Test get_latest_host_speech exception handling"""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("Read error")):
                result = get_latest_host_speech("/fake/dir")
                self.assertIsNone(result)

    def test_get_all_host_speeches_exception(self):
        """Test get_all_host_speeches exception handling"""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("Read error")):
                result = get_all_host_speeches("/fake/dir")
                self.assertEqual(result, [])

    def test_get_recent_agent_speeches_exception(self):
        """Test get_recent_agent_speeches exception handling"""
        with patch('pathlib.Path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("Read error")):
                result = get_recent_agent_speeches("/fake/dir")
                self.assertEqual(result, [])

if __name__ == '__main__':
    unittest.main()
