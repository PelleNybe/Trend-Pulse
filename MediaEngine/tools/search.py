"""
Multimodal search toolset designed for AI agents (Bocha)

Version: 1.1
Last updated: 2025-08-22

This script breaks down the complex Bocha AI Search functionality into a series of well-targeted、Standalone tool with few parameters，
Designed specifically for AI Agent calls。Agent Just based on the task intent（Like regular search、Find structured data or timely news）
Choose the right tool，No need to understand complex parameter combinations。

Core features:
- Powerful multi-modal capabilities: can return to web pages at the same time、picture、AISummarize、Ask for suggestions，and rich“modal card”structured data。
- Modal card support: for weather、stock、exchange rate、Encyclopedia、Medical and other specific inquiries，Can directly return structured data cards，Convenient for Agent to directly parse and use。

Main tools:
- comprehensive_search: perform a comprehensive search，Return to web page、picture、AISummary and possible modal cards。
- search_for_structured_data: Specifically used to query weather、stock、Exchange rates, etc. can trigger“modal card”structured information。
- web_search_only: Perform a pure web search，Do not request AI summary，faster。
- search_last_24_hours: Get the latest information from the past 24 hours。
- search_last_week: Get the top stories from the past week。
"""

import os
import json
import sys
import datetime
from typing import List, Dict, Any, Optional, Literal

from loguru import logger
from config import settings


try:
    import requests
except ImportError:
    raise ImportError("requests Library not installed，Please run `pip install requests` to install。")


current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
utils_dir = os.path.join(root_dir, 'utils')
if utils_dir not in sys.path:
    sys.path.append(utils_dir)

from retry_helper import with_graceful_retry, SEARCH_API_RETRY_CONFIG


from dataclasses import dataclass, field

@dataclass
class WebpageResult:
    """Web search results"""
    name: str
    url: str
    snippet: str
    display_url: Optional[str] = None
    date_last_crawled: Optional[str] = None

@dataclass
class ImageResult:
    """Image search results"""
    name: str
    content_url: str
    host_page_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

@dataclass
class ModalCardResult:
    """
    Modal card structured data results
    This is the core feature of Bocha Search，Used to return specific types of structured information。
    """
    card_type: str
    content: Dict[str, Any]

@dataclass
class BochaResponse:
    """Encapsulates the complete return result of Bocha API，to pass between tools"""
    query: str
    conversation_id: Optional[str] = None
    answer: Optional[str] = None
    follow_ups: List[str] = field(default_factory=list)
    webpages: List[WebpageResult] = field(default_factory=list)
    images: List[ImageResult] = field(default_factory=list)
    modal_cards: List[ModalCardResult] = field(default_factory=list)

@dataclass
class AnspireResponse:
    """Encapsulates the complete return results of Anspire API，to pass between tools"""
    query: str
    conversation_id: Optional[str] = None
    score: Optional[float] = None
    webpages: List[WebpageResult] = field(default_factory=list)




class BochaMultimodalSearch:
    """
    A client that includes a variety of specialized multimodal search tools。
    Each public method is designed as a tool for the AI ​​Agent to call independently。
    """

    BOCHA_BASE_URL = settings.BOCHA_BASE_URL or "https://api.bocha.cn/v1/ai-search"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize client。
        Args:
            api_key: Bocha APIkey，If not provided, it will be read from the environment variable BOCHA_API_KEY。
        """
        if api_key is None:
            api_key = settings.BOCHA_WEB_SEARCH_API_KEY
            if not api_key:
                raise ValueError("Bocha API Keynot found！Please set the BOCHA_API_KEY environment variable or provide it during initialization")

        self._headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': '*/*'
        }

    def _parse_search_response(self, response_dict: Dict[str, Any], query: str) -> BochaResponse:
        """Parse a structured BochaResponse object from the API's raw dictionary response"""

        final_response = BochaResponse(query=query)
        final_response.conversation_id = response_dict.get('conversation_id')

        messages = response_dict.get('messages', [])
        for msg in messages:
            role = msg.get('role')
            if role != 'assistant':
                continue

            msg_type = msg.get('type')
            content_type = msg.get('content_type')
            content_str = msg.get('content', '{}')

            try:
                content_data = json.loads(content_str)
            except json.JSONDecodeError:

                content_data = content_str

            if msg_type == 'answer' and content_type == 'text':
                final_response.answer = content_data

            elif msg_type == 'follow_up' and content_type == 'text':
                final_response.follow_ups.append(content_data)

            elif msg_type == 'source':
                if content_type == 'webpage':
                    web_results = content_data.get('value', [])
                    for item in web_results:
                        final_response.webpages.append(WebpageResult(
                            name=item.get('name'),
                            url=item.get('url'),
                            snippet=item.get('snippet'),
                            display_url=item.get('displayUrl'),
                            date_last_crawled=item.get('dateLastCrawled')
                        ))
                elif content_type == 'image':
                    final_response.images.append(ImageResult(
                        name=content_data.get('name'),
                        content_url=content_data.get('contentUrl'),
                        host_page_url=content_data.get('hostPageUrl'),
                        thumbnail_url=content_data.get('thumbnailUrl'),
                        width=content_data.get('width'),
                        height=content_data.get('height')
                    ))

                else:
                    final_response.modal_cards.append(ModalCardResult(
                        card_type=content_type,
                        content=content_data
                    ))

        return final_response


    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=BochaResponse(query="Search failed"))
    def _search_internal(self, **kwargs) -> BochaResponse:
        """Internal universal search executor，All tools eventually call this method"""
        query = kwargs.get("query", "Unknown Query")
        payload = {
            "stream": False,
        }
        payload.update(kwargs)

        try:

            response = requests.post(self.BOCHA_BASE_URL, headers=self._headers, json=payload, timeout=30)
            response.raise_for_status()

            response_dict = response.json()
            if response_dict.get("code") != 200:
                logger.error(f"APIreturn error: {response_dict.get('msg', 'unknown error')}")
                return BochaResponse(query=query)

            return self._parse_search_response(response_dict, query)

        except requests.exceptions.RequestException as e:
            logger.exception(f"A network error occurred while searching: {str(e)}")
            raise e
        except Exception as e:
            logger.exception(f"An unknown error occurred while processing the response: {str(e)}")
            raise e



    def comprehensive_search(self, query: str, max_results: int = 10) -> BochaResponse:
        """
        【tool】Comprehensive comprehensive search: perform a standard、Comprehensive search for all information types。
        Return to web page、picture、AISummarize、Ask for suggestions and possible modal cards。This is the most commonly used general search tool。
        AgentSearch query (query) and optional maximum number of results can be provided(max_results)。
        """
        logger.info(f"--- TOOL: Comprehensive comprehensive search (query: {query}) ---")
        return self._search_internal(
            query=query,
            count=max_results,
            answer=True
        )

    def web_search_only(self, query: str, max_results: int = 15) -> BochaResponse:
        """
        【tool】Pure web search: only get web links and abstracts，Don’t ask AI to generate answers。
        Suitable for quickly obtaining original web page information，Scenarios that do not require additional analysis by AI。faster，lower cost。
        """
        logger.info(f"--- TOOL: Pure web search (query: {query}) ---")
        return self._search_internal(
            query=query,
            count=max_results,
            answer=False
        )

    def search_for_structured_data(self, query: str) -> BochaResponse:
        """
        【tool】Structured Data Query: Specialized for possible triggers“modal card”Query。
        When the Agent's intention is to query the weather、stock、exchange rate、Encyclopedia definition、train ticket、When car parameters and other structured information are，This tool should be used first。
        it will return all information，But the Agent should focus on the results `modal_cards` part。
        """
        logger.info(f"--- TOOL: Structured data query (query: {query}) ---")

        return self._search_internal(
            query=query,
            count=5,
            answer=True
        )

    def search_last_24_hours(self, query: str) -> BochaResponse:
        """
        【tool】Search information within 24 hours: Get the latest updates on a topic。
        This tool specifically looks for content published in the past 24 hours。Suitable for tracking emergencies or latest developments。
        """
        logger.info(f"--- TOOL: Search information within 24 hours (query: {query}) ---")
        return self._search_internal(query=query, freshness='oneDay', answer=True)

    def search_last_week(self, query: str) -> BochaResponse:
        """
        【tool】Search this week's news: Get the major stories on a topic from the past week。
        Suitable for weekly public opinion summary or review。
        """
        logger.info(f"--- TOOL: Search this week's information (query: {query}) ---")
        return self._search_internal(query=query, freshness='oneWeek', answer=True)

class AnspireAISearch:
    """
    Anspire AI Search client
    """
    ANSPIRE_BASE_URL = settings.ANSPIRE_BASE_URL or "https://plugin.anspire.cn/api/ntsearch/search"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize client。
        Args:
            api_key: Anspire APIkey，If not provided, it will be read from the environment variable ANSPIRE_API_KEY。
        """
        if api_key is None:
            api_key = settings.ANSPIRE_API_KEY
            if not api_key:
                raise ValueError("Anspire API Keynot found！Please set the ANSPIRE_API_KEY environment variable or provide it during initialization")

        self._headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Connection': 'keep-alive',
            'Accept': '*/*'
        }

    def _parse_search_response(self, response_dict: Dict[str, Any], query: str) -> AnspireResponse:
        final_response = AnspireResponse(query=query)
        final_response.conversation_id = response_dict.get('Uuid')

        messages = response_dict.get("results", [])
        for msg in messages:
            final_response.score = msg.get("score")
            final_response.webpages.append(WebpageResult(
                name = msg.get("title", ""),
                url = msg.get("url", ""),
                snippet = msg.get("content", ""),
                date_last_crawled = msg.get("date", None)
            ))

        return final_response
    
    @with_graceful_retry(SEARCH_API_RETRY_CONFIG, default_return=AnspireResponse(query="Search failed"))
    def _search_internal(self, **kwargs) -> AnspireResponse:
        """Internal universal search executor，All tools eventually call this method"""
        query = kwargs.get("query", "Unknown Query")
        payload = {
            "query": query,
            "top_k": kwargs.get("top_k", 10),
            "Insite": kwargs.get("Insite", ""),
            "FromTime": kwargs.get("FromTime", ""),
            "ToTime": kwargs.get("ToTime", "")
        }
        
        try:
            response = requests.get(self.ANSPIRE_BASE_URL, headers=self._headers, params=payload, timeout=30)
            response.raise_for_status()

            response_dict = response.json()
            return self._parse_search_response(response_dict, query)
        except requests.exceptions.RequestException as e:
            logger.exception(f"A network error occurred while searching: {str(e)}")
            raise e
        except Exception as e:
            logger.exception(f"An unknown error occurred while processing the response: {str(e)}")
            raise e
    
    def comprehensive_search(self, query: str, max_results: int = 10) -> AnspireResponse:
        """
        【tool】Comprehensive Search: Get comprehensive information on a topic，including web pages。
        Suitable for scenarios that require multiple sources of information。
        """
        logger.info(f"--- TOOL: Comprehensive search (query: {query}) ---")
        return self._search_internal(
            query=query,
            top_k=max_results
        )

    def search_last_24_hours(self, query: str, max_results: int = 10) -> AnspireResponse:
        """
        【tool】Search information within 24 hours: Get the latest updates on a topic。
        This tool specifically looks for content published in the past 24 hours。Suitable for tracking emergencies or latest developments。
        """
        logger.info(f"--- TOOL: Search information within 24 hours (query: {query}) ---")
        to_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        from_time = to_time - datetime.timedelta(days=1)
        return self._search_internal(query=query,
                                     top_k=max_results,
                                     FromTime=from_time.strftime("%Y-%m-%d %H:%M:%S"), 
                                     ToTime=to_time.strftime("%Y-%m-%d %H:%M:%S"))

    def search_last_week(self, query: str, max_results: int = 10) -> AnspireResponse:
        """
        【tool】Search this week's news: Get the major stories on a topic from the past week。
        Suitable for weekly public opinion summary or review。
        """
        logger.info(f"--- TOOL: Search this week's information (query: {query}) ---")
        to_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        from_time = to_time - datetime.timedelta(weeks=1)
        return self._search_internal(query=query,
                                     top_k=max_results,
                                     FromTime=from_time.strftime("%Y-%m-%d %H:%M:%S"),
                                     ToTime=to_time.strftime("%Y-%m-%d %H:%M:%S"))



def load_agent_from_config():
    """Select and load searches based on profileAgent"""
    if settings.BOCHA_WEB_SEARCH_API_KEY:
        logger.info("load BochaMultimodalSearch Agent")
        return BochaMultimodalSearch()
    elif settings.ANSPIRE_API_KEY:
        logger.info("load AnspireAISearch Agent")
        return AnspireAISearch()
    else:
        raise ValueError("No valid search configuredAgent")

def print_response_summary(response):
    """Simplified printing function，Used to display test results"""
    if not response or not response.query:
        logger.error("Failed to get valid response。")
        return

    logger.info(f"\nQuery: '{response.query}' | sessionID: {response.conversation_id}")
    if hasattr(response, 'answer') and response.answer:
        logger.info(f"AIsummary: {response.answer[:150]}...")

    logger.info(f"turn up {len(response.webpages)} web pages")
    if hasattr(response, 'images'):
        logger.info(f"turn up {len(response.images)} pictures")
    if hasattr(response, 'modal_cards'):
        logger.info(f"turn up {len(response.modal_cards)} modal card")

    if hasattr(response, 'modal_cards') and response.modal_cards:
        first_card = response.modal_cards[0]
        logger.info(f"First modal card type: {first_card.card_type}")

    if response.webpages:
        first_result = response.webpages[0]
        logger.info(f"First web result: {first_result.name}")

    if hasattr(response, 'follow_ups') and response.follow_ups:
        logger.info(f"It is recommended to ask: {response.follow_ups}")

    logger.info("-" * 60)


if __name__ == "__main__":


    try:

        search_client = load_agent_from_config()


        response1 = search_client.comprehensive_search(query="The impact of artificial intelligence on future education")
        print_response_summary(response1)


        if isinstance(search_client, BochaMultimodalSearch):
            response2 = search_client.search_for_structured_data(query="What will the weather be like tomorrow in Shanghai?")
            print_response_summary(response2)

            if response2.modal_cards and response2.modal_cards[0].card_type == 'weather_china':
                logger.info("Weather modal card details:", json.dumps(response2.modal_cards[0].content, indent=2, ensure_ascii=False))



        if isinstance(search_client, BochaMultimodalSearch):
            response3 = search_client.search_for_structured_data(query="Oriental Fortune Stock")
            print_response_summary(response3)


        response4 = search_client.search_last_24_hours(query="C929Latest news about large aircraft")
        print_response_summary(response4)


        if isinstance(search_client, BochaMultimodalSearch):
            response5 = search_client.web_search_only(query="Python dataclassesusage")
            print_response_summary(response5)


        response6 = search_client.search_last_week(query="Quantum computing commercialization")
        print_response_summary(response6)

        '''Below is the output of the test program：
        --- TOOL: Comprehensive comprehensive search (query: The impact of artificial intelligence on future education) ---

Query: 'The impact of artificial intelligence on future education' | Session ID: bf43bfe4c7bb4f7b8a3945515d8ab69e
AI summary: Artificial intelligence has many impacts on future education。

From the perspective of positive impact：
- In terms of teaching resources，Artificial intelligence contributes to the balanced distribution of educational resources [Quote:4]。For example, through the artificial intelligence cloud platform，Able to share high-quality resources，This is significant for remote areas，It allows students there to have access to high-quality educational content，Alleviating the problem of teacher shortage to a certain extent，Because AI-driven intelligent teaching assistants or virtual...
Found 10 web pages, 1 image, 1 modal card。
First modal card type: video
First web result: How artificial intelligence affects educational change
It is recommended to ask: [['How artificial intelligence will change the future of education？', 'in future education，What challenges will artificial intelligence bring to teachers?？', 'In future education，How students use artificial intelligence to improve learning outcomes？']]
------------------------------------------------------------
--- TOOL: Structured data query (query: What will the weather be like tomorrow in Shanghai) ---

Query: 'What will the weather be like tomorrow in Shanghai?' | Session ID: e412aa1548cd43a295430e47a62adda2
AI summary: Based on the information given，Unable to determine the weather conditions in Shanghai tomorrow。

first，The information provided relates to weather conditions on August 22, 2025，including the temperature of the day、precipitation、wind force、Humidity and high temperature warning and other information [Quote: 1][Quote: 2][Quote: 3][Quote:5]。However，This information does not relate to tomorrow（8March 23）Weather forecast content。Although it is mentioned that the subtropical high pressure will have high temperatures until the end of August...
Found 5 web pages, 1 image, 2 modal cards。
First modal card type: video
The first web page result: Today’s impact is 38! Shanghai’s number of high-temperature days in August and the number of sustained high-temperature days in summer are expected to both break records_Weather_Low Pressure_Weather Station
It is recommended to ask: [['Can you tell me the temperature range in Shanghai tomorrow?？', 'Will it rain in Shanghai tomorrow?？', 'Will the weather in Shanghai be sunny or cloudy tomorrow?？']]
------------------------------------------------------------
--- TOOL: Structured data query (query: Oriental Fortune Stock) ---

Query: 'Oriental Fortune Stock' | Session ID: 584d62ed97834473b967127852e1eaa0
AI summary: only based on the context provided，Unable to obtain exact information about Oriental Fortune stocks。

Judging from the data given，There is no specific data directly related to Oriental Wealth stocks.。For example，There are no price changes for Oriental Fortune stocks.、Volume、Market value and other specific data [Quote: 1][Quote:3]。There is also no research report involving Oriental Fortune stocks. 、Information on ratings [Citation:2]。at the same time，About stock prices in context、Deal...
Found 5 web pages, 1 image, 2 modal cards。
First modal card type: video
The first web page result: Stock Price_Time-sharing Transaction_Quotes_Trend Chart—Oriental Fortune Network
It is recommended to ask: [['What is the recent trend of Oriental Fortune stocks?？', 'What are the main investment highlights of Oriental Fortune stocks?？', 'What are the historical high and low stock prices of Oriental Fortune stock?？']]
------------------------------------------------------------
--- TOOL: Search for information within 24 hours (query: C929 latest news) ---

Query: 'C929Latest news about large aircraft' | Session ID: 5904021dc29d497e938e04db18d7f2e2
AI Summary: Based on the context provided，There is no direct news about the C929 large aircraft，It is impossible to give the latest news about the C929 large aircraft.。

The context currently provided covers a wide range of aviation-related events，But mostly around Boeing787、Personnel changes among experts related to Airbus A380、Domestic aircraft“C909Journey to the Cloud”、Code CNC’s revenue、Content related to the supply of Russian-made aviation engines and other non-C929 large aircraft。...
Found 10 web pages, 1 image, 1 modal card。
First modal card type: video
First web page result: Giving up tens of millions of annual salary in the United States, top Boeing 787 experts return to China and may help crack C929
It is recommended to ask: [['C929What is the current development progress of large aircraft?？', 'Is there any news about the expected first flight time of the C929 large aircraft?？', 'C929What are the new developments in technological innovation for large aircraft?？']]
------------------------------------------------------------
--- TOOL: Pure web search (query: Python dataclasses usage) ---

Query: 'Python dataclassesusage' | Session ID: 74c742759d2e4b17b52d8b735ce24537
Found 15 web pages, 1 image, 1 modal card。
First modal card type: video
The first web page result: Must-know dataclasses python knowledge_python dataclasses-CSDN blog
------------------------------------------------------------------
--- TOOL: Search this week's information (query: Quantum computing commercialization) ---

AI summary: Commercialization of quantum computing is gradually advancing。

The commercialization of quantum computing has many aspects and driving factors.。From an international perspective，U.S. Department of Energy's Oak Ridge National Laboratory selects IQM Radiance for its first locally deployed quantum computer，Delivery and integration into high-performance computing systems is planned for Q3 2025 [Citation:4]；British quantum computing company Oxford Ionics' full-stack ion trap quantum computing...
Found 10 web pages, 1 image, 1 modal card。
First modal card type: video
The first web page result: The commercial potential of quantum computing is in full swing, and WIMI Hologram (WIMI.US) is stuck in the innovative technology position“ecological highland”
It is recommended to ask: [['What are the current successful cases of quantum computing commercialization?？', 'Which companies are driving the commercialization of quantum computing?？', 'What are the main challenges facing the commercialization of quantum computing?？']]
------------------------------------------------------------'''

    except ValueError as e:
        logger.exception(f"Initialization failed: {e}")
        logger.error("Please make sure the BOCHA_API_KEY environment variable is set correctly。")
    except Exception as e:
        logger.exception(f"An unknown error occurred during testing: {e}")