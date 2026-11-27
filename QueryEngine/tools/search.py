"""
Public opinion search tool set specially designed for AI Agent (Tavily)

Version: 1.5
Last updated: 2025-08-22

This script breaks down the complex Tavily search functionality into a series of well-targeted、A stand-alone tool with very few parameters,
Designed specifically for AI Agent calls. The agent only needs to select the appropriate tool based on the task intention.
No need to understand complex parameter combinations. All tools search for "News" by default”(topic='news')。

New features:
- New `basic_search_news` Tools for enforcing standards、Universal news search.
- Every search result now contains `published_date` (News release date)。

Main tools:
- basic_search_news: (New) Implementation standards、Fast universal news search.
- advanced_search_news: The most comprehensive in-depth analysis of a topic.
- search_news_last_24_hours: Get the latest news within 24 hours.
- search_news_last_week: Get the main stories of the past week.
- search_images_for_news: Find images related to news topics.
- search_news_by_date: Search within the specified historical date range。
"""

import os
import sys
from typing import List, Dict, Any, Optional


current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(root_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from retry_helper import with_graceful_retry, SEARCH_API_RETRY_CONFIG
from dataclasses import dataclass, field


try:
    from tavily import TavilyClient
except ImportError as e:
    import sys
    print(f"Failed to import TavilyClient: {e}", file=sys.stderr)



@dataclass
class SearchResult:
    """
    Web search result data class
    Contains published_date attribute to store news publication date
    """
    title: str
    url: str
    content: str
    score: Optional[float] = None
    raw_content: Optional[str] = None
    published_date: Optional[str] = None

@dataclass
class ImageResult:
    """Image search result data class"""
    url: str
    description: Optional[str] = None

@dataclass
class TavilyResponse:
    """Encapsulate the complete return results of the Tavily API so that they can be passed between tools"""
    query: str
    answer: Optional[str] = None
    results: List[SearchResult] = field(default_factory=list)
    images: List[ImageResult] = field(default_factory=list)
    response_time: Optional[float] = None




class TavilyNewsAgency:
    """
    A client that contains a variety of dedicated news and opinion search tools.
    Each public method is designed as a tool for the AI ​​Agent to call independently。
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the client.
        Args:
            api_key: Tavily API key, if not provided, it will be read from the environment variable TAVILY_API_KEY。
        """
        if api_key is None:
            api_key = os.getenv("TAVILY_API_KEY")
            if not api_key:
                raise ValueError("Tavily API Keynot found! Please set the TAVILY_API_KEY environment variable or provide it during initialization")
        self._client = TavilyClient(api_key=api_key)

    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=TavilyResponse(query="Search failed"))
    def _search_internal(self, **kwargs) -> TavilyResponse:
        """Internally common search executor, all tools ultimately call this method"""
        try:
            kwargs['topic'] = 'general'
            api_params = {k: v for k, v in kwargs.items() if v is not None}
            response_dict = self._client.search(**api_params)
            
            search_results = [
                SearchResult(
                    title=item.get('title'),
                    url=item.get('url'),
                    content=item.get('content'),
                    score=item.get('score'),
                    raw_content=item.get('raw_content'),
                    published_date=item.get('published_date')
                ) for item in response_dict.get('results', [])
            ]
            
            image_results = [ImageResult(url=item.get('url'), description=item.get('description')) for item in response_dict.get('images', [])]

            return TavilyResponse(
                query=response_dict.get('query'), answer=response_dict.get('answer'),
                results=search_results, images=image_results,
                response_time=response_dict.get('response_time')
            )
        except Exception as e:
            print(f"An error occurred while searching: {str(e)}")
            raise e



    def basic_search_news(self, query: str, max_results: int = 7) -> TavilyResponse:
        """
        【Tools】Basic News Search: Execute a Criteria、Quick news search.
        This is the most common general search tool used when you are not sure what specific search you need.
        Agent can provide search queries(query)and optional maximum number of results(max_results)。
        """
        print(f"--- TOOL: Basic news search (query: {query}) ---")
        return self._search_internal(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False
        )

    def advanced_search_news(self, query: str) -> TavilyResponse:
        """
        【Tools】In-depth news analysis: the most comprehensive analysis of a topic、The most advanced search.
        Returns AI-generated "advanced" detailed summary answers and up to 20 of the most relevant news results. Suitable for scenarios where a comprehensive understanding of the background of an event is required.
        The agent only needs to provide the search query(query)。
        """
        print(f"--- TOOL: In-depth news analysis (query: {query}) ---")
        return self._search_internal(
            query=query, search_depth="advanced", max_results=20, include_answer="advanced"
        )

    def search_news_last_24_hours(self, query: str) -> TavilyResponse:
        """
        【Tools] Search news within 24 hours: Get the latest updates on a certain topic.
        This tool specifically looks for news published within the past 24 hours. Suitable for tracking emergencies or latest developments.
        The agent only needs to provide the search query(query)。
        """
        print(f"--- TOOL: Search news within 24 hours (query: {query}) ---")
        return self._search_internal(query=query, time_range='d', max_results=10)

    def search_news_last_week(self, query: str) -> TavilyResponse:
        """
        【Tools] Search this week's news: Get the main news reports on a topic in the past week.
        Suitable for weekly public opinion summary or review.
        The agent only needs to provide the search query(query)。
        """
        print(f"--- TOOL: Search this week's news (query: {query}) ---")
        return self._search_internal(query=query, time_range='w', max_results=10)

    def search_images_for_news(self, query: str) -> TavilyResponse:
        """
        【Tools】Find News Pictures: Search for pictures related to a news topic.
        This tool returns image links and descriptions, and is suitable for scenarios where you need to illustrate reports or articles.
        The agent only needs to provide the search query(query)。
        """
        print(f"--- TOOL: Find news pictures (query: {query}) ---")
        return self._search_internal(
            query=query, include_images=True, include_image_descriptions=True, max_results=5
        )

    def search_news_by_date(self, query: str, start_date: str, end_date: str) -> TavilyResponse:
        """
        【Tools] Search news by specified date range: Search for news within a clear historical time period.
        This is the only tool that requires the Agent to provide detailed time parameters. Suitable for scenarios that require analysis of specific historical events.
        Agent needs to provide query(query)、start date(start_date)and end date(end_date)，The format is 'YYYY-MM-DD'。
        """
        print(f"--- TOOL: Search news by specified date range (query: {query}, from: {start_date}, to: {end_date}) ---")
        return self._search_internal(
            query=query, start_date=start_date, end_date=end_date, max_results=15
        )




def print_response_summary(response: TavilyResponse):
    """Simplified print function for displaying test results, now showing release date"""
    if not response or not response.query:
        print("Failed to get valid response。")
        return
        
    print(f"\nQuery: '{response.query}' | time consuming: {response.response_time}s")
    if response.answer:
        print(f"AIsummary: {response.answer[:120]}...")
    print(f"turn up {len(response.results)} web pages, {len(response.images)} pictures。")
    if response.results:
        first_result = response.results[0]
        date_info = f"(Posted in: {first_result.published_date})" if first_result.published_date else ""
        print(f"First result: {first_result.title} {date_info}")
    print("-" * 60)


if __name__ == "__main__":

    
    try:

        agency = TavilyNewsAgency()


        response1 = agency.basic_search_news(query="Latest Olympic Games results", max_results=5)
        print_response_summary(response1)


        response2 = agency.advanced_search_news(query="Global chip technology competition")
        print_response_summary(response2)


        response3 = agency.search_news_last_24_hours(query="Nvidia GTCConference latest releases")
        print_response_summary(response3)
        

        response4 = agency.search_news_last_week(query="Commercialization of autonomous driving")
        print_response_summary(response4)
        

        response5 = agency.search_images_for_news(query="The latest discoveries from the Webb Space Telescope")
        print_response_summary(response5)


        response6 = agency.search_news_by_date(
            query="Artificial Intelligence Regulations",
            start_date="2025-01-01",
            end_date="2025-03-31"
        )
        print_response_summary(response6)

    except ValueError as e:
        print(f"Initialization failed: {e}")
        print("Please make sure the TAVILY_API_KEY environment variable is set correctly。")
    except Exception as e:
        print(f"An unknown error occurred during testing: {e}")