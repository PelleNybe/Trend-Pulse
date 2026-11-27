"""
Forum log test data

Contains minimal examples of various log formats for testingForumEngine/monitor.pyLog parsing function in .
Covers old formats（[HH:MM:SS]）and logging example in new format (loguru default format)。
"""




OLD_FORMAT_SINGLE_LINE_JSON = """[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {"paragraph_latest_state": "This is the first summary content"}"""


OLD_FORMAT_MULTILINE_JSON = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "[17:42:31] \"paragraph_latest_state\": \"This is multiple lines\\nJSONcontent\"",
    "[17:42:31] }"
]


OLD_FORMAT_FIRST_SUMMARY = """[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - FirstSummaryNode Cleaned output: {"paragraph_latest_state": "First summary"}"""


OLD_FORMAT_REFLECTION_SUMMARY = """[17:43:00] 2025-11-05 17:43:00.272 | INFO | InsightEngine.nodes.summary_node:process_output:296 - ReflectionSummaryNode Cleaned output: {"updated_paragraph_latest_state": "Reflection and summary"}"""


OLD_FORMAT_NON_TARGET = """[17:41:16] 2025-11-05 17:41:16.742 | INFO | InsightEngine.nodes.report_structure_node:run:52 - Generating report structure for query"""





NEW_FORMAT_SINGLE_LINE_JSON = """2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {"paragraph_latest_state": "This is the first summary content"}"""


NEW_FORMAT_MULTILINE_JSON = [
    "2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO     | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"This is multiple lines\\nJSONcontent\"",
    "2025-11-05 17:42:31.289 | INFO     | InsightEngine.nodes.summary_node:process_output:133 - }"
]


NEW_FORMAT_FIRST_SUMMARY = """2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - FirstSummaryNode Cleaned output: {"paragraph_latest_state": "First summary"}"""


NEW_FORMAT_REFLECTION_SUMMARY = """2025-11-05 17:43:00.272 | INFO     | InsightEngine.nodes.summary_node:process_output:296 - ReflectionSummaryNode Cleaned output: {"updated_paragraph_latest_state": "Reflection and summary"}"""


NEW_FORMAT_NON_TARGET = """2025-11-05 17:41:16.742 | INFO     | InsightEngine.nodes.report_structure_node:run:52 - Generating report structure for query: China Molybdenum expected stock price changes"""


NEW_FORMAT_FORUM_ENGINE = """2025-11-05 22:31:09.964 | INFO     | ForumEngine.monitor:monitor_logs:457 - ForumEngine: Forum is being created..."""





COMPLEX_JSON_WITH_UPDATED = [
    "2025-11-05 17:43:00.272 | INFO     | InsightEngine.nodes.summary_node:process_output:296 - Cleaned output: {",
    "2025-11-05 17:43:00.273 | INFO     | InsightEngine.nodes.summary_node:process_output:297 - \"updated_paragraph_latest_state\": \"Updated version\\nCore findings\"",
    "2025-11-05 17:43:00.274 | INFO     | InsightEngine.nodes.summary_node:process_output:298 - }"
]


COMPLEX_JSON_WITH_PARAGRAPH = [
    "2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO     | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"First summary of content\\nCore findings\"",
    "2025-11-05 17:42:31.289 | INFO     | InsightEngine.nodes.summary_node:process_output:133 - }"
]


COMPLEX_JSON_WITH_NEWLINES = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "[17:42:31] \"paragraph_latest_state\": \"First line of content\\nSecond line of content\\nThe third line of content\"",
    "[17:42:31] }"
]




LINE_WITHOUT_CLEAN_OUTPUT = """2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - JSONParsed successfully"""


LINE_WITH_CLEAN_OUTPUT_NOT_JSON = """2025-11-05 17:42:31.287 | INFO     | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: This is not in JSON format"""


EMPTY_LINE = ""


LINE_WITH_ONLY_TIMESTAMP_OLD = "[17:42:31]"
LINE_WITH_ONLY_TIMESTAMP_NEW = "2025-11-05 17:42:31.287 | INFO | module:function:1 -"


INVALID_JSON = [
    "2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"Missing closing quote",
    "2025-11-05 17:42:31.289 | INFO | InsightEngine.nodes.summary_node:process_output:133 - }"
]


MIXED_FORMAT_LINES = [
    "[17:42:31] 2025-11-05 17:42:31.287 | INFO | InsightEngine.nodes.summary_node:process_output:131 - Cleaned output: {",
    "2025-11-05 17:42:31.288 | INFO     | InsightEngine.nodes.summary_node:process_output:132 - \"paragraph_latest_state\": \"Mixed format content\"",
    "[17:42:31] }"
]




REAL_QUERY_ENGINE_REFLECTION = [
    "[10:56:04] 2025-11-06 10:56:04.759 | INFO     | QueryEngine.nodes.summary_node:process_output:302 - Cleaned output: {",
    "[10:56:04] \"updated_paragraph_latest_state\": \"China Molybdenum Group Co., Ltd. (CMOC) is the leading molybdenum producer in mainland China and one of the world's top producers of non-ferrous metals and rare metals. The company's predecessor can be traced back to the Luanchuan County small mineral processing plant established in 1969 with the approval of the former Ministry of Metallurgy. In 1999, Luoyang Luanchuan Molybdenum Group was formally established and restructured into a joint-stock company in 2006. After two mixed-ownership reforms in 2004 and 2014, CMOC is currently a privately held joint-stock company. The company was listed on the Hong Kong Stock Exchange in 2007 (stock code: 03993), and returned to A-share listing on the Shanghai Stock Exchange in 2012 (stock code:：603993）。\\n\\nCMOC’s core business covers basic metals、Mining of rare metals、select、Smelting and processing, including molybdenum、Tungsten、copper、cobalt、niobium、Phosphorus, etc., while actively developing mineral trading business. The company's business footprint spans Asia、Africa、South America and Europe are the world’s leading copper producers、cobalt、molybdenum、Tungsten、Niobium producer and the leading producer of phosphate fertilizers in Brazil. As of the third quarter of 2025, the company will achieve operating income1454.85billion, net profit attributable to parent company86.71billion, operating net cash flow reached120.09billion, and the asset-liability ratio was further optimized to50.15%。\\n\\n\"",
    "[10:56:04] }"
]


REAL_INSIGHT_ENGINE_REFLECTION = [
    "[10:55:19] 2025-11-06 10:55:19.563 | INFO     | InsightEngine.nodes.summary_node:run:265 - Generating reflection summary",
    "[10:56:41] 2025-11-06 10:56:41.626 | INFO     | InsightEngine.nodes.summary_node:process_output:296 - Cleaned output: {",
    "[10:56:41] \"updated_paragraph_latest_state\": \"Updated version\\nChina Molybdenum’s core discoveries in the third quarter of 2025\"",
    "[10:56:41] }"
]


REAL_MEDIA_ENGINE_REFLECTION = """[10:56:15] 2025-11-06 10:56:15.779 | INFO     | MediaEngine.nodes.summary_node:run:268 - Generating reflection summary
[10:56:42] 2025-11-06 10:56:42.337 | INFO     | MediaEngine.nodes.summary_node:process_output:302 - Cleaned output: {"updated_paragraph_latest_state": "Comprehensive information overview\\nCMOC and other information"}"""




SEARCH_NODE_FIRST_SEARCH = [
    "[11:16:35] 2025-11-06 11:16:35.567 | INFO     | InsightEngine.nodes.search_node:process_output:97 - Cleaned output: {",
    "[11:16:35] \"search_query\": \"What do you think?\"",
    "[11:16:35] \"search_tool\": \"search_topic_globally\"",
    "[11:16:35] \"reasoning\": \"This is the reasoning behind the search query\"",
    "[11:16:35] \"enable_sentiment\": true",
    "[11:16:35] }"
]


SEARCH_NODE_REFLECTION_SEARCH = '[11:17:05] 2025-11-06 11:17:05.547 | INFO     | InsightEngine.nodes.search_node:process_output:232 - Cleaned output: {"search_query": "AIeducation data breach unfair", "search_tool": "search_hot_content", "reasoning": "It is necessary to understand the recent hot controversies about AI education, especially the data security and fairness issues that the public is most concerned about, to supplement specific cases and real public opinion data", "time_period": "week", "enable_sentiment": True}'




SUMMARY_NODE_JSON_ERROR = "[11:55:31] 2025-11-06 11:55:31.763 | ERROR    | MediaEngine.nodes.summary_node:process_output:141 - JSONParsing failed: Unterminated string starting at: line 1 column 28 (char 27)"


SUMMARY_NODE_JSON_FIX_ERROR = "[11:55:31] 2025-11-06 11:55:31.799 | ERROR    | MediaEngine.nodes.summary_node:process_output:149 - JSONRepair fails, use the cleaned text directly"


SUMMARY_NODE_ERROR_LOG = "[11:55:31] 2025-11-06 11:55:31.763 | ERROR    | MediaEngine.nodes.summary_node:process_output:141 - An error occurred: Unable to process output"


SUMMARY_NODE_TRACEBACK = '[11:55:31] File "D:\\\\Programing\\\\TrendPulse\\\\SingleEngineApp\\\\..\\\\MediaEngine\\\\nodes\\\\summary_node.py", line 138, in process_output\n[11:55:31] result = json.loads(cleaned_output)\n'

