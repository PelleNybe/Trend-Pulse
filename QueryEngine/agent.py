"""
Trend Pulse main class
Integrate all modules to achieve a complete in-depth search process
"""

import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any

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
from .tools import TavilyNewsAgency, TavilyResponse
from .tools.anomaly_tool import MarketAnomalyDetector
from .utils import Settings, format_search_results_for_prompt
from loguru import logger

class TrendPulseAgent:
    """Trend Pulse main class"""
    
    def __init__(self, config: Optional[Settings] = None):
        """
        initializationTrend Pulse
        
        Args:
            config: Configuration object, automatic if not providedLoad
        """

        from config import settings
        self.config = config or settings
        

        self.llm_client = self._initialize_llm()
        

        self.search_agency = TavilyNewsAgency(api_key=self.config.TAVILY_API_KEY)
        self.anomaly_detector = MarketAnomalyDetector()
        

        self._initialize_nodes()
        

        self.state = State()
        

        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        
        logger.info("Query AgentInitialized")
        logger.info(f"useLLM: {self.llm_client.get_model_info()}")
        logger.info("Search toolset: TavilyNewsAgency (Supports 6 search tools)")
    
    def _initialize_llm(self) -> LLMClient:
        """Initialize LLM client"""
        return LLMClient(
            api_key=self.config.QUERY_ENGINE_API_KEY,
            model_name=self.config.QUERY_ENGINE_MODEL_NAME,
            base_url=self.config.QUERY_ENGINE_BASE_URL,
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
    
    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> TavilyResponse:
        """
        ExecuteSpecified search tools
        
        Args:
            tool_name: tool name, optional value：
                - "basic_search_news": Basic news search (quick、Universal）
                - "advanced_search_news": In-depth news analysis
                - "search_news_last_24_hours": 24Latest news within hours
                - "search_news_last_week": News this week
                - "search_images_for_news": News photo search
                - "search_news_by_date": Search news by date range
            query: search query
            **kwargs: Additional parameters (such as start_date, end_date, max_results)
            
        Returns:
            TavilyResponse object
        """
        logger.info(f"  → ExecuteSearch tool: {tool_name}")
        
        if tool_name == "detect_market_anomalies":
            logger.info(f"    → Call exception detection: {query}")
            try:
                import yfinance as yf
                from .tools.search import SearchResult
                hist = yf.download(query, period="6mo", progress=False)
                if len(hist) > 0:
                    prices = hist['Close']
                    anomaly_result = self.anomaly_detector.detect_anomalies(prices)
                    anomalies = anomaly_result.get("anomalies", [])
                    results = []
                    for a in anomalies:
                        results.append(SearchResult(
                            title=f"Anomaly: {a['type']} on {a['date']}",
                            content=f"Price: {a['value']:.2f}, Z-Score: {a['z_score']:.2f}",
                            url="",
                            published_date=a['date']
                        ))
                    return TavilyResponse(query=query, results=results)
                else:
                    return TavilyResponse(query=query, results=[])
            except Exception as e:
                logger.error(f"Anomaly detectionError: {str(e)}")
                return TavilyResponse(query=query, results=[])
        elif tool_name == "basic_search_news":
            max_results = kwargs.get("max_results", 7)
            return self.search_agency.basic_search_news(query, max_results)
        elif tool_name == "advanced_search_news":
            return self.search_agency.advanced_search_news(query)
        elif tool_name == "search_news_last_24_hours":
            return self.search_agency.search_news_last_24_hours(query)
        elif tool_name == "search_news_last_week":
            return self.search_agency.search_news_last_week(query)
        elif tool_name == "search_images_for_news":
            return self.search_agency.search_images_for_news(query)
        elif tool_name == "search_news_by_date":
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            if not start_date or not end_date:
                raise ValueError("search_news_by_dateTool requires start_date and end_date parameters")
            return self.search_agency.search_news_by_date(query, start_date, end_date)
        else:
            logger.warning(f"  ⚠️  Unknownsearch tools: {tool_name}，Use default base search")
            return self.search_agency.basic_search_news(query)
    
    def research(self, query: str, save_report: bool = True) -> str:
        """
        Executein-depth research
        
        Args:
            query: research query
            save_report: Whether to save the report to a file
            
        Returns:
            Final report content
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"Startin-depth research: {query}")
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
            logger.error(f"occurred during the researchError: {str(e)} \nErrorstack: {error_traceback}")
            raise e
    
    def _generate_report_structure(self, query: str):
        """Generate report structure"""
        logger.info("\n[step 1] Generate report structure...")
        

        report_structure_node = ReportStructureNode(self.llm_client, query)
        

        self.state = report_structure_node.mutate_state(state=self.state)
        
        _message_parts = [f"The report structure has been generated with a total of {len(self.state.paragraphs)} paragraphs:"]
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
        """ExecuteInitial search and summary"""
        paragraph = self.state.paragraphs[paragraph_index]
        

        search_input = {
            "title": paragraph.title,
            "content": paragraph.content
        }
        

        logger.info("  - Generate search query...")
        search_output = self.first_search_node.run(search_input)
        search_query = search_output["search_query"]
        search_tool = search_output.get("search_tool", "basic_search_news")
        reasoning = search_output["reasoning"]
        
        logger.info(f"  - search query: {search_query}")
        logger.info(f"  - Tools of choice: {search_tool}")
        logger.info(f"  - reasoning: {reasoning}")
        

        logger.info("  - Executeweb search...")
        

        search_kwargs = {}
        if search_tool == "search_news_by_date":
            start_date = search_output.get("start_date")
            end_date = search_output.get("end_date")
            
            if start_date and end_date:

                if self._validate_date_format(start_date) and self._validate_date_format(end_date):
                    search_kwargs["start_date"] = start_date
                    search_kwargs["end_date"] = end_date
                    logger.info(f"  - time range: {start_date} arrive {end_date}")
                else:
                    logger.info("  ⚠️  Date format Error (should beYYYY-MM-DD），Use basic search instead")
                    logger.info(f"      Date provided: start_date={start_date}, end_date={end_date}")
                    search_tool = "basic_search_news"
            else:
                logger.info("  ⚠️  search_news_by_dateTool is missing time parameter, use basic search instead")
                search_tool = "basic_search_news"
        
        search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
        

        search_results = []
        if search_response and search_response.results:

            max_results = min(len(search_response.results), 10)
            for result in search_response.results[:max_results]:
                search_results.append({
                    'title': result.title,
                    'url': result.url,
                    'content': result.content,
                    'score': result.score,
                    'raw_content': result.raw_content,
                    'published_date': result.published_date
                })
        
        if search_results:
            _message_parts = [f"  - turn up {len(search_results)} search results"]
            for j, result in enumerate(search_results, 1):
                date_info = f" (Posted in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
                _message_parts.append(f"\n    {j}. {result['title'][:50]}...{date_info}")
            logger.info("".join(_message_parts))
        else:
            logger.info("  - Not foundSearch results")

        paragraph.research.add_search_results(search_query, search_results)
        

        logger.info("  - Generate initial summary...")
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
        """Executereflective cycle"""
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
            search_tool = reflection_output.get("search_tool", "basic_search_news")
            reasoning = reflection_output["reasoning"]
            
            logger.info(f"    reflective inquiry: {search_query}")
            logger.info(f"    Tools of choice: {search_tool}")
            logger.info(f"    reflective reasoning: {reasoning}")
            


            search_kwargs = {}
            if search_tool == "search_news_by_date":
                start_date = reflection_output.get("start_date")
                end_date = reflection_output.get("end_date")
                
                if start_date and end_date:

                    if self._validate_date_format(start_date) and self._validate_date_format(end_date):
                        search_kwargs["start_date"] = start_date
                        search_kwargs["end_date"] = end_date
                        logger.info(f"    time range: {start_date} arrive {end_date}")
                    else:
                        logger.info("    ⚠️  Date format Error (should beYYYY-MM-DD），Use basic search instead")
                        logger.info(f"        Date provided: start_date={start_date}, end_date={end_date}")
                        search_tool = "basic_search_news"
                else:
                    logger.info("    ⚠️  search_news_by_dateTool is missing time parameter, use basic search instead")
                    search_tool = "basic_search_news"
            
            search_response = self.execute_search_tool(search_tool, search_query, **search_kwargs)
            

            search_results = []
            if search_response and search_response.results:

                max_results = min(len(search_response.results), 10)
                for result in search_response.results[:max_results]:
                    search_results.append({
                        'title': result.title,
                        'url': result.url,
                        'content': result.content,
                        'score': result.score,
                        'raw_content': result.raw_content,
                        'published_date': result.published_date
                    })
            
            if search_results:
                logger.info(f"    turn up {len(search_results)} Reflection search results")
                for j, result in enumerate(search_results, 1):
                    date_info = f" (Posted in: {result.get('published_date', 'N/A')})" if result.get('published_date') else ""
                    logger.info(f"      {j}. {result['title'][:50]}...{date_info}")
            else:
                logger.info("    Not foundReflect on search results")
            

            paragraph.research.add_search_results(search_query, search_results)
            

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
        logger.info("\n[step 3] Generate final report...")
        

        report_data = []
        for paragraph in self.state.paragraphs:
            report_data.append({
                "title": paragraph.title,
                "paragraph_latest_state": paragraph.research.latest_summary
            })
        

        try:
            final_report = self.report_formatting_node.run(report_data)
        except Exception as e:
            logger.error(f"LLMFormat failed, use backup method: {str(e)}")
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
        logger.info(f"Status has changed from {filepath} Load")
    
    def save_state(self, filepath: str):
        """Save state to file"""
        self.state.save_to_file(filepath)
        logger.info(f"Status saved to {filepath}")


def create_agent() -> TrendPulseAgent:
    """
    Convenience functions for creating Trend Pulse instances
    
    Returns:
        TrendPulseAgentExample
    """
    from config import Settings
    config = Settings()
    return TrendPulseAgent(config)
