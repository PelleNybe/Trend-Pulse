"""
Streamlit Webinterface
Provide a friendly web interface for Insight Agent
"""

import os
import sys
import streamlit as st
import pandas as pd
import numpy as np
from InsightEngine.tools.backtest_tool import PortfolioBacktester
from QueryEngine.tools.anomaly_tool import MarketAnomalyDetector
from InsightEngine.tools.custom_db_tool import CustomBusinessDBTool
from datetime import datetime
import json
import locale
from loguru import logger


os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'


try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except locale.Error as e:
        import sys
        print(f"Failed to set backup locale: {e}", file=sys.stderr)


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from InsightEngine import TrendPulseAgent, Settings
from config import settings
from utils.github_issues import error_with_issue_link


def main():
    """main function"""
    st.set_page_config(
        page_title="Insight Agent",
        page_icon="",
        layout="wide"
    )

    st.title("Insight Agent")
    st.markdown("Deep analysis AI agent for private financial market databases powered by [Corax CoLAB](https://coraxcolab.com)")
    st.markdown("Comprehensive dive into proprietary financial databases, quantitative metrics, and runs portfolio backtesting.")
    st.caption("Trend Pulse by [Corax CoLAB](https://coraxcolab.com) | Developer: [Pelle](https://github.com/PelleNybe) | [Sponsor](https://buymeacoffee.com/pellenybe)")


    try:

        query_params = st.query_params
        auto_query = query_params.get('query', '')
        auto_search = query_params.get('auto_search', 'false').lower() == 'true'
    except AttributeError:

        query_params = st.experimental_get_query_params()
        auto_query = query_params.get('query', [''])[0]
        auto_search = query_params.get('auto_search', ['false'])[0].lower() == 'true'



    model_name = settings.INSIGHT_ENGINE_MODEL_NAME or "kimi-k2-0711-preview"

    max_reflections = 2
    max_content_length = 500000




    display_query = auto_query if auto_query else "Waiting to receive analysis content from main page..."


    st.text_area(
        "Current Query",
        value=display_query,
        height=100,
        disabled=True,
        help="Query content is controlled by the search box on the main page",
        label_visibility="hidden"
    )


    start_research = False
    query = auto_query

    if auto_search and auto_query and 'auto_search_executed' not in st.session_state:
        st.session_state.auto_search_executed = True
        start_research = True
    elif auto_query and not auto_search:
        st.warning("Waiting for search start signal...")


    if start_research:
        if not query.strip():
            st.error("Please enter a research query")
            logger.error("Please enter a research query")
            return


        if not settings.INSIGHT_ENGINE_API_KEY:
            st.error("Please set INSIGHT_ENGINE_API_KEY in your environment variables")
            logger.error("Please set INSIGHT_ENGINE_API_KEY in your environment variables")
            return


        db_host = settings.DB_HOST
        db_user = settings.DB_USER
        db_password = settings.DB_PASSWORD
        db_name = settings.DB_NAME
        db_port = settings.DB_PORT
        db_charset = settings.DB_CHARSET


        config = Settings(
            INSIGHT_ENGINE_API_KEY=settings.INSIGHT_ENGINE_API_KEY,
            INSIGHT_ENGINE_BASE_URL=settings.INSIGHT_ENGINE_BASE_URL,
            INSIGHT_ENGINE_MODEL_NAME=model_name,
            DB_HOST=db_host,
            DB_USER=db_user,
            DB_PASSWORD=db_password,
            DB_NAME=db_name,
            DB_PORT=db_port,
            DB_CHARSET=db_charset,
            DB_DIALECT=settings.DB_DIALECT,
            MAX_REFLECTIONS=max_reflections,
            MAX_CONTENT_LENGTH=max_content_length,
            OUTPUT_DIR="insight_engine_streamlit_reports"
        )


        execute_research(query, config)


def execute_research(query: str, config: Settings):
    """Execute research"""
    try:

        progress_bar = st.progress(0)
        status_text = st.empty()


        status_text.text("Initializing Agent...")
        agent = TrendPulseAgent(config)
        st.session_state.agent = agent

        progress_bar.progress(10)


        status_text.text("Generating report structure...")
        agent._generate_report_structure(query)
        progress_bar.progress(20)


        total_paragraphs = len(agent.state.paragraphs)
        for i in range(total_paragraphs):
            status_text.text(f"Processing paragraph {i + 1}/{total_paragraphs}: {agent.state.paragraphs[i].title}")


            agent._initial_search_and_summary(i)
            progress_value = 20 + (i + 0.5) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))


            agent._reflection_loop(i)
            agent.state.paragraphs[i].research.mark_completed()

            progress_value = 20 + (i + 1) / total_paragraphs * 60
            progress_bar.progress(int(progress_value))


        status_text.text("Generating final report...")
        final_report = agent._generate_final_report()
        progress_bar.progress(90)


        status_text.text("Saving report...")
        agent._save_report(final_report)
        progress_bar.progress(100)

        status_text.text("Research completed!")


        display_results(agent, final_report)

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        error_display = error_with_issue_link(
            f"Error occurred during research: {str(e)}",
            error_traceback,
            app_name="Insight Engine Streamlit App"
        )
        st.error(error_display)
        logger.exception(f"Error occurred during research: {str(e)}")


def display_results(agent: TrendPulseAgent, final_report: str):
    """Show research results"""
    st.header("Work Completed")


    tab1, tab2, tab3 = st.tabs(["Research Summary", "Citation Information", "Risk Assessment Dashboard"])

    with tab1:
        st.markdown(final_report)

    with tab2:
        # Paragraph Details
        st.subheader("Paragraph Details")
        for i, paragraph in enumerate(agent.state.paragraphs):
            with st.expander(f"Paragraph {i + 1}: {paragraph.title}"):
                st.write("**Expected Content:**", paragraph.content)
                st.write("**Final Content:**", paragraph.research.latest_summary[:300] + "..."
                if len(paragraph.research.latest_summary) > 300
                else paragraph.research.latest_summary)
                st.write("**Search Count:**", paragraph.research.get_search_count())
                st.write("**Reflection Count:**", paragraph.research.reflection_iteration)

        # Search History
        st.subheader("Search History")
        all_searches = []
        for paragraph in agent.state.paragraphs:
            all_searches.extend(paragraph.research.search_history)

        if all_searches:
            for i, search in enumerate(all_searches):
                with st.expander(f"Search {i + 1}: {search.query}"):
                    st.write("**URL:**", search.url)
                    st.write("**title:**", search.title)
                    st.write("**Content Preview:**",
                             search.content[:200] + "..." if len(search.content) > 200 else search.content)
                    if search.score:
                        st.write("**Relevance Score:**", search.score)



    with tab3:
        st.subheader("Interactive Risk Assessment & Backtesting")
        st.markdown("Analyze market sentiment, detect anomalies, and backtest portfolio strategies.")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("##### Sentiment Aggregation")
            # Simulate fetching from custom DB tool
            db_tool = CustomBusinessDBTool()
            sources = [
                {"source": "News", "score": 0.8, "weight": 0.6},
                {"source": "Social Media", "score": 0.3, "weight": 0.4}
            ]
            sentiment_result = db_tool.aggregate_sentiment(sources)
            st.metric("Aggregate Sentiment Score", f"{sentiment_result['aggregate_score']}/1.0")
            st.info(f"Market Sentiment Interpretation: **{sentiment_result['interpretation']}**")

        with col2:
            st.markdown("##### Market Anomaly Detection & Quantitative Data")
            from InsightEngine.tools.technical_indicators import TechnicalIndicators
            from InsightEngine.tools.search import extract_symbol_from_keyword

            default_ticker = extract_symbol_from_keyword(auto_query) if auto_query else "SPY"
            ticker_input = st.text_input("Ticker Symbol", value=default_ticker, key="quant_ticker_input").strip().upper() or "SPY"
            market_df = TechnicalIndicators.fetch_data(ticker_input, period="6mo")

            if not market_df.empty and "Close" in market_df:
                close_col = market_df["Close"]
                prices = close_col.iloc[:, 0] if isinstance(close_col, pd.DataFrame) else close_col.squeeze()
                prices = pd.Series(prices).dropna()

                anomaly_detector = MarketAnomalyDetector(z_score_threshold=2.5)
                anomalies = anomaly_detector.detect_anomalies(prices)

                st.metric("Total Anomalies Detected", anomalies.get('anomalies_found', 0))
                if anomalies.get('anomalies_found', 0) > 0:
                    st.warning(f"Recent price/volume anomalies detected for {ticker_input}.")
            else:
                prices = pd.Series(dtype=float)
                st.warning(f"Could not fetch live market data for {ticker_input}.")

        st.markdown("##### Portfolio Strategy Backtest (EMA 12/26 Crossover)")

        if st.button("Run Backtest", key="run_sim"):
            if prices.empty or len(prices) < 30:
                st.warning("Insufficient historical market data to run EMA crossover backtest.")
            else:
                ema_fast = prices.ewm(span=12, adjust=False).mean()
                ema_slow = prices.ewm(span=26, adjust=False).mean()
                raw_signals = np.where(ema_fast > ema_slow, 1, np.where(ema_fast < ema_slow, -1, 0))
                signals = pd.Series(raw_signals, index=prices.index)

                backtester = PortfolioBacktester(initial_capital=100000.0)
                results = backtester.run_backtest(prices, signals)

                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                col_b1.metric("Final Value", f"${results.get('final_value', 0):,.2f}")
                col_b2.metric("Total Return", f"{results.get('total_return', 0)*100:.2f}%")
                col_b3.metric("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}")
                col_b4.metric("Max Drawdown", f"{results.get('max_drawdown', 0)*100:.2f}%")

                st.line_chart(prices)

if __name__ == "__main__":
    main()
