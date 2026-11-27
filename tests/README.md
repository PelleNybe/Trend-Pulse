# Trend Pulse Test Suite

This directory contains unit and integration tests for the Trend Pulse platform, alongside additional parser and chart validator tests located under [`ReportEngine/utils/`](../ReportEngine/utils/).

## Test Files

- `test_app_routes.py` — Tests typed `Settings` / `generate_config.py`, Flask routes (`/`, `/api/health`, `/api/status`, `/api/search`, `/api/search/suggest`, `/api/mem0/feed`, `/api/nexus/debate`, `/api/oracle/paths`, `/api/oracle/simulate`), and `@admin_required` (`X-API-Key`) enforcement.
- `test_engines_and_tools.py` — Tests shared `parse_search_node_output` behavior across `InsightEngine`, `MediaEngine`, and `QueryEngine`; `FinancialSentimentAnalyzer` scoring & negation; `TrendPulseDB` & `QueryResult`; `TrendPulseAgent` initialization and TF-IDF clustering fallback; `TokenTracker` and `WebhookAlerter`.
- `test_mindspider_and_forum.py` — Tests `FinancialCommitteeHost` (`mem0` dict/list handling and unconfigured LLM error handling), `generate_host_speech`, `BroadTopicExtractor`, `DeepSentimentCrawler`, `persist_collection_results`, `compute_technical_indicators`, and SQLite schema initialization via `init_database` & `DatabaseManager`.
- `test_monitor.py` — Tests `ForumEngine.monitor.LogMonitor` log parsing across both legacy `[HH:MM:SS]` and `loguru` formats using fixtures from `forum_log_test_data.py`.
- `test_forum_reader.py` — Unit tests for `utils/forum_reader.py`.
- `test_forum_log_auth.py` — Verification that sensitive log and export endpoints enforce `@admin_required`.
- `test_github_issues_unit.py` — Unit tests for GitHub issue URL generation and error helpers.
- `test_media_text_processing.py` & `test_media_text_processing_unit.py` — Unit tests for `MediaEngine/utils/text_processing.py`.
- `forum_log_test_data.py` — Minimal sample log fixtures for `LogMonitor` tests.
- `run_tests.py` — Standalone runner executing `TestLogMonitor`.

Additional engine tests in the repository:
- `ReportEngine/utils/test_chart_validator.py` — Chart structure validation and repair tests.
- `ReportEngine/utils/test_json_parser.py` — Robust LLM JSON parsing and repair tests.

## Running Tests

Ensure `config.py` is generated (`python generate_config.py`) and set `SECRET_KEY` for Flask tests:

```bash
# Run the full pytest suite
SECRET_KEY=test-secret-key pytest -v tests/ ReportEngine/utils/test_chart_validator.py ReportEngine/utils/test_json_parser.py

# Run a single test file
SECRET_KEY=test-secret-key pytest -v tests/test_monitor.py

# Run the standalone ForumEngine monitor runner
python tests/run_tests.py
```

### Tested `LogMonitor` Methods
1. `is_target_log_line` — Matches `FirstSummaryNode`, `ReflectionSummaryNode`, and summary node module logs while excluding errors.
2. `is_json_start_line` / `is_json_end_line` — Detects multiline JSON log boundaries.
3. `extract_json_content` — Parses single-line and multiline JSON log entries across legacy and loguru formats.
4. `format_json_content` — Extracts `updated_paragraph_latest_state` / `paragraph_latest_state` fields.
5. `extract_node_content` — Strips timestamps, log levels, node tags, and formatting prefixes.
6. `process_lines_for_json` — Buffers multiline JSON blocks and skips `ERROR` blocks until the next `INFO` entry.
7. `is_valuable_content` — Filters noise lines while retaining actionable summaries.
8. `fix_json_string` — Escapes stray quotes inside string values so malformed JSON remains parseable.
