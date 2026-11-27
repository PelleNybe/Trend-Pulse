"""
Trend Pulse main class
Integrate all modules，Implement a complete in-depth search process
"""

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

import numpy as np
from loguru import logger
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from .llms import LLMClient
from .nodes import (
    FirstSearchNode,
    FirstSummaryNode,
    ReflectionNode,
    ReflectionSummaryNode,
    ReportFormattingNode,
    ReportStructureNode,
)
from .state import State
from .tools import (
    TechnicalIndicators,
    PortfolioOptimizer,
    TradingSignalGenerator,
    CustomBusinessDBTool,
    PortfolioBacktester,
    DBResponse,
    TrendPulseDB,
    keyword_optimizer,
    FinancialSentimentAnalyzer,
)
from .utils import format_search_results_for_prompt
from config import Settings, settings

ENABLE_CLUSTERING: bool = True
MAX_CLUSTERED_RESULTS: int = 50
RESULTS_PER_CLUSTER: int = 5


class TrendPulseAgent:
    """Trend Pulse main class"""

    def __init__(self, config: Optional[Settings] = None):
        """
        Initialize Trend Pulse

        Args:
            config: optional configuration object（If left blank, use globalsettings）
        """
        self.config = config or settings


        self.llm_client = self._initialize_llm()


        self.search_agency = TrendPulseDB()
        self.custom_db_tool = CustomBusinessDBTool()
        self.backtester = PortfolioBacktester()


        self._clustering_model = None


        self.sentiment_analyzer = FinancialSentimentAnalyzer()


        self._initialize_nodes()


        self.state = State()


        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)

        logger.info("Insight AgentInitialized")
        logger.info(f"useLLM: {self.llm_client.get_model_info()}")
        logger.info("Search toolset: TrendPulseDB (supports 5 local database query tools)")
        logger.info("Sentiment Analysis: FinancialSentimentAnalyzer (domain-weighted financial lexicon + optional transformer backend)")

    def _initialize_llm(self) -> LLMClient:
        """Initialize LLM client"""
        return LLMClient(
            api_key=self.config.INSIGHT_ENGINE_API_KEY,
            model_name=self.config.INSIGHT_ENGINE_MODEL_NAME,
            base_url=self.config.INSIGHT_ENGINE_BASE_URL,
        )

    def _initialize_nodes(self):
        """Initialize processing node"""
        self.first_search_node = FirstSearchNode(self.llm_client)
        self.reflection_node = ReflectionNode(self.llm_client)
        self.first_summary_node = FirstSummaryNode(self.llm_client)
        self.reflection_summary_node = ReflectionSummaryNode(self.llm_client)
        self.report_formatting_node = ReportFormattingNode(self.llm_client)

    def _get_clustering_model(self):
        """Lazy loading of clustering models with TF-IDF fallback if SentenceTransformer is absent."""
        if self._clustering_model is None:
            if SentenceTransformer is not None:
                try:
                    logger.info("  Load clustering model (paraphrase-multilingual-MiniLM-L12-v2)...")
                    self._clustering_model = SentenceTransformer(
                        "paraphrase-multilingual-MiniLM-L12-v2"
                    )
                except Exception as exc:
                    logger.warning(f"  SentenceTransformer unavailable ({exc}), falling back to TF-IDF")
                    self._clustering_model = "tfidf"
            else:
                logger.info("  sentence_transformers not installed, using TF-IDF vectorization for clustering")
                self._clustering_model = "tfidf"
        return self._clustering_model

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


        pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(pattern, date_str):
            return False


        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _cluster_and_sample_results(
        self,
        results: List,
        max_results: int = MAX_CLUSTERED_RESULTS,
        results_per_cluster: int = RESULTS_PER_CLUSTER,
    ) -> List:
        """
        Cluster and sample search results

        Args:
            results: search results list
            max_results: Maximum number of results returned
            results_per_cluster: Number of results returned per cluster

        Returns:
            Result list after sampling
        """
        if len(results) <= max_results:
            return results

        try:

            texts = [r.title_or_content[:500] for r in results]


            model = self._get_clustering_model()
            if model == "tfidf":
                embeddings = TfidfVectorizer(max_features=256).fit_transform(texts).toarray()
            else:
                embeddings = model.encode(texts, show_progress_bar=False)


            n_clusters = min(max(2, max_results // results_per_cluster), len(results))


            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)


            sampled_results = []
            for cluster_id in range(n_clusters):
                cluster_indices = np.flatnonzero(labels == cluster_id)
                cluster_results = [(results[i], i) for i in cluster_indices]
                cluster_results.sort(
                    key=lambda x: x[0].hotness_score or 0, reverse=True
                )

                for result, _ in cluster_results[:results_per_cluster]:
                    sampled_results.append(result)
                    if len(sampled_results) >= max_results:
                        break

                if len(sampled_results) >= max_results:
                    break

            logger.info(
                f"  Clustering completed: {len(results)} strip -> {n_clusters} topics -> {len(sampled_results)} representative results"
            )
            return sampled_results

        except Exception as e:
            logger.warning(f"  Clustering failed，before return{max_results}strip: {str(e)}")
            return results[:max_results]

    def execute_search_tool(self, tool_name: str, query: str, **kwargs) -> DBResponse:
        """
        Execute the specified database query tool（Integrated keyword optimization middleware and sentiment analysis）

        Args:
            tool_name: Tool name，Optional value：
                - "search_hot_content": Find hot content
                - "search_topic_globally": Global topic search
                - "search_topic_by_date": Search topics by date
                - "get_comments_for_topic": Get topic comments
                - "search_topic_on_platform": Platform targeted search
                - "analyze_sentiment": Perform sentiment analysis on query results
            query: search keywords/topics
            **kwargs: extra parameters（Such as start_date, end_date, platform, limit, enable_sentiment, etc.）
                     enable_sentiment: Whether to automatically perform sentiment analysis on search results（defaultTrue）

        Returns:
            DBResponseobject（May contain sentiment analysis results）
        """
        logger.info(f"  → Execute database query tool: {tool_name}")


        if tool_name == "run_portfolio_backtest":
            logger.info(f"    → Call the backtest tool: {query}")
            try:
                import yfinance as yf
                from .tools.search import QueryResult
                hist = yf.download(query, period="1y", progress=False)
                if len(hist) > 0:
                    prices = hist['Close']
                    # Real MACD-like signal: fast EMA vs slow EMA crossover
                    fast_ema = prices.ewm(span=12, adjust=False).mean()
                    slow_ema = prices.ewm(span=26, adjust=False).mean()
                    macd = fast_ema - slow_ema
                    signal_line = macd.ewm(span=9, adjust=False).mean()

                    # 1 (buy) if MACD > signal_line, -1 (sell) otherwise
                    signals = (macd > signal_line).astype(int).replace(0, -1)

                    backtest_result = self.backtester.run_backtest(prices, signals)
                    results = [QueryResult(
                        ticker=query,
                        asset_class="Backtest",
                        title_or_content=f"Backtest Results for {query}",
                        source=f"Total Return: {backtest_result['total_return']:.2%}, Sharpe: {backtest_result['sharpe_ratio']:.2f}"
                    )]
                    return DBResponse(tool_name, {"query": query}, results=results)
                else:
                    return DBResponse(tool_name, {"query": query}, results=[])
            except Exception as e:
                logger.error(f"backtestError: {str(e)}")
                return DBResponse(tool_name, {"query": query}, results=[], error_message=str(e))
        elif tool_name == "search_business_data":
            logger.info(f"    → Call a custom business database: {query}")
            table = kwargs.get("table", "default")
            result_dict = self.custom_db_tool.search_business_data(query, table)
            results = result_dict.get("data", [])
            from .tools.search import QueryResult
            # Convert to QueryResult
            qr_results = []
            for item in results:
                qr_results.append(QueryResult(
                    ticker=query,
                    asset_class="BusinessData",
                    title_or_content=item.get("topic", "") + ": " + item.get("content", ""),
                    source=result_dict.get("source", "CustomBusinessDBTool")
                ))
            return DBResponse(tool_name, {"query": query, "table": table}, results=qr_results, error_message=result_dict.get("error"))

        elif tool_name == "search_hot_content":
            time_period = kwargs.get("time_period", "week")
            limit = kwargs.get("limit", 100)
            response = self.search_agency.search_hot_content(
                time_period=time_period, limit=limit
            )


            enable_sentiment = kwargs.get("enable_sentiment", True)
            if enable_sentiment and response.results and len(response.results) > 0:
                logger.info("  🎭 Start sentiment analysis on hot content...")
                sentiment_analysis = self._perform_sentiment_analysis(response.results)
                if sentiment_analysis:

                    response.parameters["sentiment_analysis"] = sentiment_analysis
                    logger.info("  ✅ Sentiment analysis completed")

            return response


        if tool_name == "analyze_sentiment":
            texts = kwargs.get("texts", query)
            sentiment_result = self.analyze_sentiment_only(texts)


            return DBResponse(
                tool_name="analyze_sentiment",
                parameters={
                    "texts": texts if isinstance(texts, list) else [texts],
                    **kwargs,
                },
                results=[],
                results_count=0,
                metadata=sentiment_result,
            )


        optimized_response = keyword_optimizer.optimize_keywords(
            original_query=query, context=f"use{tool_name}Tools for querying"
        )

        logger.info(f"  🔍 original query: '{query}'")
        logger.info(f"  ✨ Optimized keywords: {optimized_response.optimized_keywords}")


        all_results = []
        total_count = 0

        async def _async_search(keyword: str):
            logger.info(f"    Query keywords: '{keyword}'")

            try:
                if tool_name == "search_topic_globally":

                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                    )
                    response = await asyncio.to_thread(
                        self.search_agency.search_topic_globally,
                        topic=keyword, limit_per_table=limit_per_table
                    )
                elif tool_name == "search_topic_by_date":
                    start_date = kwargs.get("start_date")
                    end_date = kwargs.get("end_date")

                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                    )
                    if not start_date or not end_date:
                        raise ValueError(
                            "search_topic_by_dateTool requires start_date and end_date parameters"
                        )
                    response = await asyncio.to_thread(
                        self.search_agency.search_topic_by_date,
                        topic=keyword,
                        start_date=start_date,
                        end_date=end_date,
                        limit_per_table=limit_per_table,
                    )
                elif tool_name == "get_comments_for_topic":

                    limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT // len(
                        optimized_response.optimized_keywords
                    )
                    limit = max(limit, 50)
                    response = await asyncio.to_thread(
                        self.search_agency.get_comments_for_topic,
                        topic=keyword, limit=limit
                    )
                elif tool_name == "search_topic_on_platform":
                    platform = kwargs.get("platform")
                    start_date = kwargs.get("start_date")
                    end_date = kwargs.get("end_date")

                    limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT // len(
                        optimized_response.optimized_keywords
                    )
                    limit = max(limit, 30)
                    if not platform:
                        raise ValueError("search_topic_on_platformTool requires platform parameter")
                    response = await asyncio.to_thread(
                        self.search_agency.search_topic_on_platform,
                        platform=platform,
                        topic=keyword,
                        start_date=start_date,
                        end_date=end_date,
                        limit=limit,
                    )
                else:
                    logger.info(f"    Unknown search tool: {tool_name}，Use default global search")
                    response = await asyncio.to_thread(
                        self.search_agency.search_topic_globally,
                        topic=keyword,
                        limit_per_table=self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE,
                    )


                if response.results:
                    logger.info(f"     turn up {len(response.results)} results")
                    return response.results
                else:
                    logger.info("     No results found")
                    return []

            except Exception as e:
                logger.error(f"      Query'{keyword}'error: {str(e)}")
                return []

        async def _run_all_searches():
            tasks = [_async_search(kw) for kw in optimized_response.optimized_keywords]
            return await asyncio.gather(*tasks)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        results_list = loop.run_until_complete(_run_all_searches())
        for res in results_list:
            all_results.extend(res)
            total_count += len(res)

        unique_results = self._deduplicate_results(all_results)
        logger.info(f"  Total found {total_count} results，After deduplication {len(unique_results)} strip")

        if ENABLE_CLUSTERING:
            unique_results = self._cluster_and_sample_results(
                unique_results,
                max_results=MAX_CLUSTERED_RESULTS,
                results_per_cluster=RESULTS_PER_CLUSTER,
            )


        integrated_response = DBResponse(
            tool_name=f"{tool_name}_optimized",
            parameters={
                "original_query": query,
                "optimized_keywords": optimized_response.optimized_keywords,
                "optimization_reasoning": optimized_response.reasoning,
                **kwargs,
            },
            results=unique_results,
            results_count=len(unique_results),
        )


        enable_sentiment = kwargs.get("enable_sentiment", True)
        if enable_sentiment and unique_results and len(unique_results) > 0:
            logger.info("  🎭 Start sentiment analysis of search results...")
            sentiment_analysis = self._perform_sentiment_analysis(unique_results)
            if sentiment_analysis:

                integrated_response.parameters["sentiment_analysis"] = (
                    sentiment_analysis
                )
                logger.info("  ✅ Sentiment analysis completed")

        return integrated_response

    def _deduplicate_results(self, results: List) -> List:
        """
        Deduplication search results
        """
        seen = set()
        unique_results = []

        for result in results:

            identifier = result.url if result.url else result.title_or_content[:100]
            if identifier not in seen:
                seen.add(identifier)
                unique_results.append(result)

        return unique_results

    def _perform_sentiment_analysis(self, results: List) -> Optional[Dict[str, Any]]:
        """
        Perform sentiment analysis on search results

        Args:
            results: search results list

        Returns:
            Sentiment analysis result dictionary，Return if failedNone
        """
        try:

            if (
                not self.sentiment_analyzer.is_initialized
                and not self.sentiment_analyzer.is_disabled
            ):
                logger.info("    Initialize sentiment analysis model...")
                if not self.sentiment_analyzer.initialize():
                    logger.info("     Sentiment analysis model initialization failed，The original text will be transmitted directly")
            elif self.sentiment_analyzer.is_disabled:
                logger.info("     Sentiment analysis feature is disabled，Transmit original text directly")


            results_dict = []
            for result in results:
                result_dict = {
                    "content": result.title_or_content,
                    "platform": result.platform,
                    "author": result.author_nickname,
                    "url": result.url,
                    "publish_time": str(result.publish_time)
                    if result.publish_time
                    else None,
                }
                results_dict.append(result_dict)


            sentiment_analysis = self.sentiment_analyzer.analyze_query_results(
                query_results=results_dict, text_field="content", min_confidence=0.5
            )

            return sentiment_analysis.get("sentiment_analysis")

        except Exception as e:
            logger.exception(f"    ❌ An error occurred during sentiment analysis: {str(e)}")
            return None

    def analyze_sentiment_only(self, texts: Union[str, List[str]]) -> Dict[str, Any]:
        """
        Standalone sentiment analysis tool

        Args:
            texts: single text or text list

        Returns:
            Sentiment analysis results
        """
        logger.info("  → Perform independent sentiment analysis")

        try:

            if (
                not self.sentiment_analyzer.is_initialized
                and not self.sentiment_analyzer.is_disabled
            ):
                logger.info("    Initialize sentiment analysis model...")
                if not self.sentiment_analyzer.initialize():
                    logger.info("     Sentiment analysis model initialization failed，The original text will be transmitted directly")
            elif self.sentiment_analyzer.is_disabled:
                logger.warning("     Sentiment analysis feature is disabled，Transmit original text directly")


            if isinstance(texts, str):
                result = self.sentiment_analyzer.analyze_single_text(texts)
                result_dict = result.__dict__
                response = {
                    "success": result.success and result.analysis_performed,
                    "total_analyzed": 1
                    if result.analysis_performed and result.success
                    else 0,
                    "results": [result_dict],
                }
                if not result.analysis_performed:
                    response["success"] = False
                    response["warning"] = (
                        result.error_message or "Sentiment analysis function is not available，The original text has been returned directly"
                    )
                return response
            else:
                texts_list = list(texts)
                batch_result = self.sentiment_analyzer.analyze_batch(
                    texts_list, show_progress=True
                )
                response = {
                    "success": batch_result.analysis_performed
                    and batch_result.success_count > 0,
                    "total_analyzed": batch_result.total_processed
                    if batch_result.analysis_performed
                    else 0,
                    "success_count": batch_result.success_count,
                    "failed_count": batch_result.failed_count,
                    "average_confidence": batch_result.average_confidence
                    if batch_result.analysis_performed
                    else 0.0,
                    "results": [result.__dict__ for result in batch_result.results],
                }
                if not batch_result.analysis_performed:
                    warning = next(
                        (
                            r.error_message
                            for r in batch_result.results
                            if r.error_message
                        ),
                        "Sentiment analysis function is not available，The original text has been returned directly",
                    )
                    response["success"] = False
                    response["warning"] = warning
                return response

        except Exception as e:
            logger.exception(f"    ❌ An error occurred during sentiment analysis: {str(e)}")
            return {"success": False, "error": str(e), "results": []}

    def research(self, query: str, save_report: bool = True) -> str:
        """
        Perform in-depth research

        Args:
            query: research query
            save_report: whether to save the report to a file

        Returns:
            Final report content
        """
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Start in-depth research: {query}")
        logger.info(f"{'=' * 60}")

        try:

            self._generate_report_structure(query)


            self._process_paragraphs()


            final_report = self._generate_final_report()


            if save_report:
                self._save_report(final_report)

            logger.info("In-depth research completed！")

            return final_report

        except Exception as e:
            logger.exception(f"An error occurred during research: {str(e)}")
            raise e

    def _generate_report_structure(self, query: str):
        """Generate report structure"""
        logger.info("\n[Step 1] Generate report structure...")


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
            logger.info(
                f"\n[step 2.{i + 1}] Process paragraphs: {self.state.paragraphs[i].title}"
            )
            logger.info("-" * 50)


            self._initial_search_and_summary(i)


            self._reflection_loop(i)


            self.state.paragraphs[i].research.mark_completed()

            progress = (i + 1) / total_paragraphs * 100
            logger.info(f"Paragraph processing completed ({progress:.1f}%)")

    def _initial_search_and_summary(self, paragraph_index: int):
        """Perform initial search and summary"""
        paragraph = self.state.paragraphs[paragraph_index]


        search_input = {"title": paragraph.title, "content": paragraph.content}


        logger.info("  - Generate search query...")
        search_output = self.first_search_node.run(search_input)
        search_query = search_output["search_query"]
        search_tool = search_output.get(
            "search_tool", "search_topic_globally"
        )
        reasoning = search_output["reasoning"]

        logger.info(f"  - search query: {search_query}")
        logger.info(f"  - Tools of choice: {search_tool}")
        logger.info(f"  - reasoning: {reasoning}")


        logger.info("  - Execute database query...")


        search_kwargs = {}


        if search_tool in ["search_topic_by_date", "search_topic_on_platform"]:
            start_date = search_output.get("start_date")
            end_date = search_output.get("end_date")

            if start_date and end_date:

                if self._validate_date_format(
                    start_date
                ) and self._validate_date_format(end_date):
                    search_kwargs["start_date"] = start_date
                    search_kwargs["end_date"] = end_date
                    logger.info(f"  - time range: {start_date} arrive {end_date}")
                else:
                    logger.info("    Date format error（should beYYYY-MM-DD），Use global search instead")
                    logger.info(
                        f"      Date provided: start_date={start_date}, end_date={end_date}"
                    )
                    search_tool = "search_topic_globally"
            elif search_tool == "search_topic_by_date":
                logger.info("    search_topic_by_dateTool is missing time parameter，Use global search instead")
                search_tool = "search_topic_globally"


        if search_tool == "search_topic_on_platform":
            platform = search_output.get("platform")
            if platform:
                search_kwargs["platform"] = platform
                logger.info(f"  - designated platform: {platform}")
            else:
                logger.warning(
                    "    search_topic_on_platformTool is missing platform parameters，Use global search instead"
                )
                search_tool = "search_topic_globally"


        if search_tool == "search_hot_content":
            time_period = search_output.get("time_period", "week")
            limit = self.config.DEFAULT_SEARCH_HOT_CONTENT_LIMIT
            search_kwargs["time_period"] = time_period
            search_kwargs["limit"] = limit
        elif search_tool in ["search_topic_globally", "search_topic_by_date"]:
            if search_tool == "search_topic_globally":
                limit_per_table = (
                    self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                )
            else:  # search_topic_by_date
                limit_per_table = (
                    self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                )
            search_kwargs["limit_per_table"] = limit_per_table
        elif search_tool in ["get_comments_for_topic", "search_topic_on_platform"]:
            if search_tool == "get_comments_for_topic":
                limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT
            else:  # search_topic_on_platform
                limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT
            search_kwargs["limit"] = limit

        search_response = self.execute_search_tool(
            search_tool, search_query, **search_kwargs
        )


        search_results = []
        if search_response and search_response.results:

            if self.config.MAX_SEARCH_RESULTS_FOR_LLM > 0:
                max_results = min(
                    len(search_response.results), self.config.MAX_SEARCH_RESULTS_FOR_LLM
                )
            else:
                max_results = len(search_response.results)
            for result in search_response.results[:max_results]:
                search_results.append(
                    {
                        "title": result.title_or_content,
                        "url": result.url or "",
                        "content": result.title_or_content,
                        "score": result.hotness_score,
                        "raw_content": result.title_or_content,
                        "published_date": result.publish_time.isoformat()
                        if result.publish_time
                        else None,
                        "platform": result.platform,
                        "content_type": result.content_type,
                        "author": result.author_nickname,
                        "engagement": result.engagement,
                    }
                )

        if search_results:
            _message_parts = [f"  - turn up {len(search_results)} search results"]
            for j, result in enumerate(search_results, 1):
                date_info = (
                    f" (Posted in: {result.get('published_date', 'N/A')})"
                    if result.get("published_date")
                    else ""
                )
                _message_parts.append(f"\n    {j}. {result['title'][:50]}...{date_info}")
            logger.info("".join(_message_parts))
        else:
            logger.info("  - No search results found")


        paragraph.research.add_search_results(search_query, search_results)


        logger.info("  - chapters...")
        summary_input = {
            "title": paragraph.title,
            "content": paragraph.content,
            "search_query": search_query,
            "search_results": format_search_results_for_prompt(
                search_results, self.config.MAX_CONTENT_LENGTH
            ),
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
                "paragraph_latest_state": paragraph.research.latest_summary,
            }


            reflection_output = self.reflection_node.run(reflection_input)
            search_query = reflection_output["search_query"]
            search_tool = reflection_output.get(
                "search_tool", "search_topic_globally"
            )
            reasoning = reflection_output["reasoning"]

            logger.info(f"    reflective inquiry: {search_query}")
            logger.info(f"    Tools of choice: {search_tool}")
            logger.info(f"    reflective reasoning: {reasoning}")



            search_kwargs = {}


            if search_tool in ["search_topic_by_date", "search_topic_on_platform"]:
                start_date = reflection_output.get("start_date")
                end_date = reflection_output.get("end_date")

                if start_date and end_date:

                    if self._validate_date_format(
                        start_date
                    ) and self._validate_date_format(end_date):
                        search_kwargs["start_date"] = start_date
                        search_kwargs["end_date"] = end_date
                        logger.info(f"    time range: {start_date} arrive {end_date}")
                    else:
                        logger.info(
                            "      Date format error（should beYYYY-MM-DD），Use global search instead"
                        )
                        logger.info(
                            f"        Date provided: start_date={start_date}, end_date={end_date}"
                        )
                        search_tool = "search_topic_globally"
                elif search_tool == "search_topic_by_date":
                    logger.warning(
                        "      search_topic_by_dateTool is missing time parameter，Use global search instead"
                    )
                    search_tool = "search_topic_globally"


            if search_tool == "search_topic_on_platform":
                platform = reflection_output.get("platform")
                if platform:
                    search_kwargs["platform"] = platform
                    logger.info(f"    designated platform: {platform}")
                else:
                    logger.warning(
                        "      search_topic_on_platformTool is missing platform parameters，Use global search instead"
                    )
                    search_tool = "search_topic_globally"


            if search_tool == "search_hot_content":
                time_period = reflection_output.get("time_period", "week")

                limit = self.config.DEFAULT_SEARCH_HOT_CONTENT_LIMIT
                search_kwargs["time_period"] = time_period
                search_kwargs["limit"] = limit
            elif search_tool in ["search_topic_globally", "search_topic_by_date"]:

                if search_tool == "search_topic_globally":
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_GLOBALLY_LIMIT_PER_TABLE
                    )
                else:  # search_topic_by_date
                    limit_per_table = (
                        self.config.DEFAULT_SEARCH_TOPIC_BY_DATE_LIMIT_PER_TABLE
                    )
                search_kwargs["limit_per_table"] = limit_per_table
            elif search_tool in ["get_comments_for_topic", "search_topic_on_platform"]:

                if search_tool == "get_comments_for_topic":
                    limit = self.config.DEFAULT_GET_COMMENTS_FOR_TOPIC_LIMIT
                else:  # search_topic_on_platform
                    limit = self.config.DEFAULT_SEARCH_TOPIC_ON_PLATFORM_LIMIT
                search_kwargs["limit"] = limit

            search_response = self.execute_search_tool(
                search_tool, search_query, **search_kwargs
            )


            search_results = []
            if search_response and search_response.results:

                if self.config.MAX_SEARCH_RESULTS_FOR_LLM > 0:
                    max_results = min(
                        len(search_response.results),
                        self.config.MAX_SEARCH_RESULTS_FOR_LLM,
                    )
                else:
                    max_results = len(search_response.results)
                for result in search_response.results[:max_results]:
                    search_results.append(
                        {
                            "title": result.title_or_content,
                            "url": result.url or "",
                            "content": result.title_or_content,
                            "score": result.hotness_score,
                            "raw_content": result.title_or_content,
                            "published_date": result.publish_time.isoformat()
                            if result.publish_time
                            else None,
                            "platform": result.platform,
                            "content_type": result.content_type,
                            "author": result.author_nickname,
                            "engagement": result.engagement,
                        }
                    )

            if search_results:
                _message_parts = [f"    turn up {len(search_results)} Reflection search results"]
                for j, result in enumerate(search_results, 1):
                    date_info = (
                        f" (Posted in: {result.get('published_date', 'N/A')})"
                        if result.get("published_date")
                        else ""
                    )
                    _message_parts.append(f"\n      {j}. {result['title'][:50]}...{date_info}")
                logger.info("".join(_message_parts))
            else:
                logger.info("    No reflection search results found")


            paragraph.research.add_search_results(search_query, search_results)


            reflection_summary_input = {
                "title": paragraph.title,
                "content": paragraph.content,
                "search_query": search_query,
                "search_results": format_search_results_for_prompt(
                    search_results, self.config.MAX_CONTENT_LENGTH
                ),
                "paragraph_latest_state": paragraph.research.latest_summary,
            }


            self.state = self.reflection_summary_node.mutate_state(
                reflection_summary_input, self.state, paragraph_index
            )

            logger.info(f"    Reflection {reflection_i + 1} Finish")

    def _generate_final_report(self) -> str:
        """Generate final report"""
        logger.info("\n[Step 3] Generate final report...")


        report_data = []
        for paragraph in self.state.paragraphs:
            report_data.append(
                {
                    "title": paragraph.title,
                    "paragraph_latest_state": paragraph.research.latest_summary,
                }
            )


        try:
            final_report = self.report_formatting_node.run(report_data)
        except Exception as e:
            logger.exception(f"LLMFormat failed，Use backup methods: {str(e)}")
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
        query_safe = "".join(
            c for c in self.state.query if c.isalnum() or c in (" ", "-", "_")
        ).rstrip()
        query_safe = query_safe.replace(" ", "_")[:30]

        filename = f"trend_pulse_report_{query_safe}_{timestamp}.md"
        filepath = os.path.join(self.config.OUTPUT_DIR, filename)


        with open(filepath, "w", encoding="utf-8") as f:
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


def create_agent(config_file: Optional[str] = None) -> TrendPulseAgent:
    """
    Convenience functions for creating Trend Pulse instances

    Args:
        config_file: configuration file path

    Returns:
        TrendPulseAgent instance
    """
    config = Settings()
    return TrendPulseAgent(config)
