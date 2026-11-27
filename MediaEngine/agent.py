"""
Trend Pulse main class
Integrate all modules，Implement a complete in-depth search process
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from loguru import logger
from .llms import LLMClient
from .nodes import (
    ReportStructureNode,
    FirstSearchNode, 
    ReflectionNode,
    FirstSummaryNode,
    ReflectionSummaryNode,
    ReportFormattingNode
)
from .state import State
from .tools import BochaMultimodalSearch, BochaResponse, AnspireAISearch, AnspireResponse
from .utils import settings, Settings, format_search_results_for_prompt


class TrendPulseAgent:
    """Trend Pulse main class"""
    
    def __init__(self, config: Optional[Settings] = None):
        """
        Initialize Trend Pulse
        
        Args:
            config: configuration object，If not provided, it will be loaded automatically.
        """
        self.config = config or settings
        

        self.llm_client = self._initialize_llm()
        

        self.search_agency = BochaMultimodalSearch(api_key=(self.config.BOCHA_API_KEY or self.config.BOCHA_WEB_SEARCH_API_KEY))
        

        self._initialize_nodes()
        

        self.state = State()
        

        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        
        logger.info(f"Media AgentInitialized")
        logger.info(f"useLLM: {self.llm_client.get_model_info()}")
        logger.info(f"Search toolset: BochaMultimodalSearch (supports 5 multimodal search tools)")
    
    def _initialize_llm(self) -> LLMClient:
        """Initialize LLM client"""
        return LLMClient(
            api_key=(self.config.MEDIA_ENGINE_API_KEY or self.config.MINDSPIDER_API_KEY),
            model_name=(self.config.MEDIA_ENGINE_MODEL_NAME or self.config.MINDSPIDER_MODEL_NAME),
            base_url=(self.config.MEDIA_ENGINE_BASE_URL or self.config.MINDSPIDER_BASE_URL),
        )
    
    def _initialize_nodes(self):
        """Initialize processing node"""
        self.first_search_node = FirstSearchNode(self.llm_client)
        self.reflection_node = ReflectionNode(self.llm_client)
        self.first_summary_node = FirstSummaryNode(self.llm_client)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm_client)
        self.report_formatting_node = ReportFormattingNode(self.llm_client)
    
    def _validate_date_format(self, date_str: str) -> bool:
        """
        Verify that the date format is YYYY-MM-DD
        
        Args:
            date_str: date string
            
        Returns:
            Is it a valid format?
        """
        if not date_str:
            return False
        

        pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(pattern, date_str):
            return False
        

        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> BochaResponse:
        """
        Execute the specified search tool
        
        Args:
            tool_name: tool name，Optional value：
                - "comprehensive_search": Comprehensive comprehensive search（default）
                - "web_search_only": Pure web search
                - "search_for_structured_data": Structured data query
                - "search_last_24_hours": 24Latest information within hours
                - "search_last_week": Information of the week
            query: search query
            **kwargs: extra parameters（likemax_results）
            
        Returns:
            BochaResponseobject
        """
        logger.info(f"  → Execute search tool: {tool_name}")
        
        if tool_name == "comprehensive_search":
            max_results = kwargs.get("max_results", 10)
            return self.search_agency.comprehensive_search(query, max_results)
        elif tool_name == "web_search_only":
            max_results = kwargs.get("max_results", 15)
            return self.search_agency.web_search_only(query, max_results)
        elif tool_name == "search_for_structured_data":
            return self.search_agency.search_for_structured_data(query)
        elif tool_name == "search_last_24_hours":
            return self.search_agency.search_last_24_hours(query)
        elif tool_name == "search_last_week":
            return self.search_agency.search_last_week(query)
        else:
            logger.info(f"  ⚠️  Unknown search tool: {tool_name}，Use default comprehensive search")
            return self.search_agency.comprehensive_search(query)
    
    def research(self, query: str, save_report: bool = True) -> str:
        """
        Perform in-depth research
        
        Args:
            query: research query
            save_report: whether to save the report to a file
            
        Returns:
            Final report content
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Start in-depth research: {query}")
        logger.info(f"{'='*60}")
        
        try:

            self._generate_report_structure(query)
            

            self._process_paragraphs()
            

            final_report = self._generate_final_report()
            

            if save_report:
                self._save_report(final_report)
            
            logger.info(f"\n{'='*60}")
            logger.info("In-depth research completed！")
            logger.info(f"{'='*60}")
            
            return final_report
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"An error occurred during research: {str(e)} \nerror stack: {error_traceback}")
            raise e
    
    def _generate_report_structure(self, query: str):
        """Generate report structure"""
        logger.info(f"\n[Step 1] Generate report structure...")
        

        report_structure_node = ReportStructureNode(self.llm_client, query)
        

        self.state = report_structure_node.mutate_state(state=self.state)
        
        _message_parts = [f"Report structure generated，common {len(self.state.paragraphs)} paragraphs:"]
        for i, paragraph in enumerate(self.state.paragraphs, 1):
            _message_parts.append(f"\n  {i}. {paragraph.title}")
        logger.info("".join(_message_parts))
    
    def _process_paragraphs(self):
        """process all paragraphs"""
        total_paragraphs = len(self.state.paragraphs)
        
        for i in range(total_paragraphs):
            logger.info(f"\n[step 2.{i+1}] Process paragraphs: {self.state.paragraphs[i].title}")
            logger.info("-" * 50)
            

            self._initial_search_and_summary(i)
            

            self._reflection_loop(i)
            

            self.state.paragraphs[i].research.mark_completed()
            
            progress = (i + 1) / total_paragraphs * 100
            logger.info(f"Paragraph processing completed ({progress:.1f}%)")
    
    def _initial_search_and_summary(self, paragraph_index: int):
        """Perform initial search and summary"""
        paragraph = self.state.paragraphs[paragraph_index]
        

        search_input = {
            "title": paragraph.title,
            "content": paragraph.content
        }
        

        logger.info("  - Generate search query...")
        search_output = self.first_search_node.run(search_input)
        search_query = search_output["search_query"]
        search_tool = search_output.get("search_tool", "comprehensive_search")
        reasoning = search_output["reasoning"]
        
        logger.info(f"  - search query: {search_query}")
        logger.info(f"  - Tools of choice: {search_tool}")
        logger.info(f"  - reasoning: {reasoning}")
        

        logger.info("  - Perform a web search...")
        

        search_kwargs = {}
        if search_tool in ["comprehensive_search", "web_search_only"]:

            search_kwargs["max_results"] = 10
        
        search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
        

        search_results = []
        if search_response and search_response.webpages:

            max_results = min(len(search_response.webpages), 10)
            for result in search_response.webpages[:max_results]:
                search_results.append({
                    'title': result.name,
                    'url': result.url,
                    'content': result.snippet,
                    'score': None,
                    'raw_content': result.snippet,
                    'published_date': result.date_last_crawled
                })
        
        if search_results:
            _message_parts = [f"  - turn up {len(search_results)} search results"]
            for j, result in enumerate(search_results, 1):
                date_info = f" (Posted in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
                _message_parts.append(f"\n    {j}. {result['title'][:50]}...{date_info}")
            logger.info("".join(_message_parts))
        else:
            logger.info("  - No search results found")
        

        paragraph.research.add_search_results(
            search_query,
            search_results,
            search_tool=search_tool,
            paragraph_title=paragraph.title,
        )
        

        logger.info("  - chapters...")
        summary_input = {
            "title": paragraph.title,
            "content": paragraph.content,
            "search_query": search_query,
            "search_results": format_search_results_for_prompt(
                search_results, self.config.SEARCH_CONTENT_MAX_LENGTH
            )
        }
        

        self.state = self.first_summary_node.mutate_state(
            summary_input, self.state, paragraph_index
        )
        
        logger.info("  - Initial summary completed")
    
    def _reflection_loop(self, paragraph_index: int):
        """Execute a reflective cycle"""
        paragraph = self.state.paragraphs[paragraph_index]
        
        for reflection_i in range(self.config.MAX_REFLECTIONS):
            logger.info(f"  - Reflection {reflection_i + 1}/{self.config.MAX_REFLECTIONS}...")
            

            reflection_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "paragraph_latest_state": paragraph.research.latest_summary
            }
            

            reflection_output = self.reflection_node.run(reflection_input)
            search_query = reflection_output["search_query"]
            search_tool = reflection_output.get("search_tool", "comprehensive_search")
            reasoning = reflection_output["reasoning"]
            
            logger.info(f"    reflective inquiry: {search_query}")
            logger.info(f"    Tools of choice: {search_tool}")
            logger.info(f"    reflective reasoning: {reasoning}")
            


            search_kwargs = {}
            if search_tool in ["comprehensive_search", "web_search_only"]:

                search_kwargs["max_results"] = 10
            
            search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
            

            search_results = []
            if search_response and search_response.webpages:

                max_results = min(len(search_response.webpages), 10)
                for result in search_response.webpages[:max_results]:
                    search_results.append({
                        'title': result.name,
                        'url': result.url,
                        'content': result.snippet,
                        'score': None,
                        'raw_content': result.snippet,
                        'published_date': result.date_last_crawled
                    })
            
            if search_results:
                _message_parts = [f"    turn up {len(search_results)} Reflection search results"]
                for j, result in enumerate(search_results, 1):
                    date_info = f" (Posted in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
                    _message_parts.append(f"\n      {j}. {result['title'][:50]}...{date_info}")
                logger.info("".join(_message_parts))
            else:
                logger.info("    No reflection search results found")
            

            paragraph.research.add_search_results(
                search_query,
                search_results,
                search_tool=search_tool,
                paragraph_title=paragraph.title,
            )
            

            reflection_summary_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "search_query": search_query,
                "search_results": format_search_results_for_prompt(
                    search_results, self.config.SEARCH_CONTENT_MAX_LENGTH
                ),
                "paragraph_latest_state": paragraph.research.latest_summary
            }
            

            self.state = self.reflection_summary_node.mutate_state(
                reflection_summary_input, self.state, paragraph_index
            )
            
            logger.info(f"    Reflection {reflection_i + 1} Finish")
    
    def _generate_final_report(self) -> str:
        """Generate final report"""
        logger.info(f"\n[Step 3] Generate final report...")
        

        report_data = []
        for paragraph in self.state.paragraphs:
            report_data.append({
                "title": paragraph.title,
                "paragraph_latest_state": paragraph.research.latest_summary
            })
        

        try:
            final_report = self.report_formatting_node.run(report_data)
        except Exception as e:
            logger.info(f"LLMFormat failed，Use backup methods: {str(e)}")
            final_report = self.report_formatting_node.format_report_manually(
                report_data, self.state.report_title
            )
        

        self.state.final_report = final_report
        self.state.mark_completed()
        
        logger.info("Final report generation completed")
        return final_report
    
    def _save_report(self, report_content: str):
        """Save report to file"""

        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y%m%d_%H%M%S")
        query_safe = "".join(c for c in self.state.query if c.isalnum() or c in (' ', '-', '_')).rstrip()
        query_safe = query_safe.replace(' ', '_')[:30]
        
        filename = f"trend_pulse_report_{query_safe}_{timestamp}.md"
        filepath = os.path.join(self.config.OUTPUT_DIR, filename)
        

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        logger.info(f"Report saved to: {filepath}")
        

        if self.config.SAVE_INTERMEDIATE_STATES:
            state_filename = f"state_{query_safe}_{timestamp}.json"
            state_filepath = os.path.join(self.config.OUTPUT_DIR, state_filename)
            self.state.save_to_file(state_filepath)
            logger.info(f"Status saved to: {state_filepath}")
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get progress summary"""
        return self.state.get_progress_summary()
    
    def load_state(self, filepath: str):
        """Load status from file"""
        self.state = State.load_from_file(filepath)
        logger.info(f"Status has changed from {filepath} load")
    
    def save_state(self, filepath: str):
        """Save state to file"""
        self.state.save_to_file(filepath)
        logger.info(f"Status saved to {filepath}")

class AnspireSearchAgent(TrendPulseAgent):
    """Call Anspire search engine Trend Pulse"""
    
    def __init__(self, config: Settings | None = None):
        self.config = config or settings
        

        self.llm_client = self._initialize_llm()
        

        self.search_agency = AnspireAISearch(api_key=self.config.ANSPIRE_API_KEY)


        self._initialize_nodes()
        

        self.state = State()
        

        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        
        logger.info(f"Media AgentInitialized")
        logger.info(f"useLLM: {self.llm_client.get_model_info()}")
        logger.info(f"Search toolset: AnspireSearch")

    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> AnspireResponse:

        """
        Execute the specified search tool
        
        Args:
            tool_name: tool name，Optional value：
                - "comprehensive_search": Comprehensive comprehensive search（default）
                - "search_last_24_hours": 24Latest information within hours
                - "search_last_week": Information of the week
            query: search query
            **kwargs: extra parameters（likemax_results）
            
        Returns:
            AnspireResponseobject
        """
        logger.info(f"  → Execute search tool: {tool_name}")
        
        if tool_name == "comprehensive_search":
            max_results = kwargs.get("max_results", 10)
            return self.search_agency.comprehensive_search(query, max_results)
        elif tool_name == "search_last_24_hours":
            return self.search_agency.search_last_24_hours(query)
        elif tool_name == "search_last_week":
            return self.search_agency.search_last_week(query)
        else:
            logger.info(f"  ⚠️  Unknown search tool: {tool_name}，Use default comprehensive search")
            return self.search_agency.comprehensive_search(query)


def create_agent(config_file: Optional[str] = None) -> TrendPulseAgent:
    """
    Convenience functions for creating Trend Pulse instances
    
    Args:
        config_file: configuration file path
        
    Returns:
        TrendPulseAgent instance
    """
    settings = Settings()
    if settings.SEARCH_TOOL_TYPE == "AnspireAPI":
        return AnspireSearchAgent(settings)
    return TrendPulseAgent(settings)
