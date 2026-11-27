#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MindSpider AICrawler project - database management tool
Provide database status view、Statistics、Cleaning and other functions
"""

import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from loguru import logger
from urllib.parse import quote_plus


mindspider_root = Path(__file__).resolve().parent.parent
repo_root = mindspider_root.parent
for p in (str(mindspider_root), str(repo_root)):
    if p not in sys.path:
        sys.path.append(p)

try:
    from config import settings
except ImportError:
    logger.error("Error: Unable to import config.py configuration file")
    sys.exit(1)

class DatabaseManager:
    def __init__(self):
        self.engine: Engine = None
        self.connect()
    
    def connect(self):
        """Connect to database"""
        try:
            database_url = getattr(settings, "DATABASE_URL", None)
            if database_url:
                # Normalize async driver suffixes to sync drivers for DatabaseManager
                url = database_url.replace("+asyncpg", "+psycopg2").replace("+aiomysql", "+pymysql")
            else:
                dialect = (settings.DB_DIALECT or "mysql").lower()
                if dialect == "sqlite":
                    db_name = settings.DB_NAME or "mindspider.db"
                    url = f"sqlite:///{db_name}"
                elif dialect in ("postgresql", "postgres"):
                    url = f"postgresql+psycopg2://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD or '')}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
                else:
                    url = f"mysql+pymysql://{settings.DB_USER}:{quote_plus(settings.DB_PASSWORD or '')}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}?charset={settings.DB_CHARSET}"
            self.engine = create_engine(url, future=True)
            logger.info(f"Successfully connected to the database: {settings.DB_NAME}")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            sys.exit(1)
    
    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
    
    def show_tables(self):
        """show all tables"""
        data_list_message_parts = []
        data_list_message_parts.append("\n" + "=" * 60)
        data_list_message_parts.append("Database table list")
        data_list_message_parts.append("=" * 60)
        logger.info("".join(data_list_message_parts))
        
        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        
        if not tables:
            logger.info("There is no table in the database")
            return
        
        table_counts = {}
        try:
            with self.engine.connect() as conn:
                # ⚡ OPTIMIZATION: Use UNION ALL for accurate and fast row counts directly from tables
                if tables:
                    preparer = self.engine.dialect.identifier_preparer
                    union_queries = []
                    for table in tables:
                        if not isinstance(table, str) or not table:
                            continue
                        quoted_table = preparer.quote(table)
                        escaped_label = table.replace("'", "''")
                        union_queries.append(f"SELECT '{escaped_label}', COUNT(*) FROM {quoted_table}")

                    if union_queries:
                        query = text(" UNION ALL ".join(union_queries))
                        results = conn.execute(query).all()
                    else:
                        results = []
                else:
                    results = []
                for row in results:
                    table_counts[row[0]] = row[1] or 0
        except Exception as e:
            logger.error(f"Failed to obtain table statistics: {e}")
        
        mindspider_tables = [t for t in tables if t in ['daily_news', 'daily_topics', 'topic_news_relation', 'crawling_tasks']]
        platform_tables = [t for t in tables if t not in ['daily_news', 'daily_topics', 'topic_news_relation', 'crawling_tasks']]
        
        data_list_message_parts.append("MindSpider core tables:")
        data_list_message_parts.append("\n")
        for table in mindspider_tables:
            count = table_counts.get(table, 0)
            data_list_message_parts.append(f"  - {table:<25} ({count:>6} records)\n")
        
        data_list_message_parts.append("\nTrendPulse platform tables:")
        data_list_message_parts.append("\n")
        for table in platform_tables:
            count = table_counts.get(table, 0)
            data_list_message_parts.append(f"  - {table:<25} ({count:>6} records)\n")
        logger.info("".join(data_list_message_parts))
    
    def show_statistics(self):
        """Display database statistics"""
        data_statistics_message_parts = []
        data_statistics_message_parts.append("\n" + "=" * 60 + "\n")
        data_statistics_message_parts.append("TrendPulse Database Statistics\n")
        data_statistics_message_parts.append("=" * 60 + "\n")
        
        try:
            with self.engine.connect() as conn:
                news_stats = conn.execute(text("SELECT COUNT(*), COUNT(DISTINCT crawl_date), COUNT(DISTINCT source_platform) FROM daily_news")).first()
                news_count, news_days, platforms = news_stats if news_stats else (0, 0, 0)
            
                data_statistics_message_parts.append("news data:\n")
                data_statistics_message_parts.append(f"  - total number of news: {news_count}\n")
                data_statistics_message_parts.append(f"  - Coverage days: {news_days}\n")
                data_statistics_message_parts.append(f"  - News platform: {platforms}\n")

                topic_stats = conn.execute(text("SELECT COUNT(*), COUNT(DISTINCT extract_date) FROM daily_topics")).first()
                topic_count, topic_days = topic_stats if topic_stats else (0, 0)
            
                data_statistics_message_parts.append("topic data:\n")
                data_statistics_message_parts.append(f"  - Total number of topics: {topic_count}\n")
                data_statistics_message_parts.append(f"  - Extraction days: {topic_days}\n")
            
                task_count = conn.execute(text("SELECT COUNT(*) FROM crawling_tasks")).scalar_one()
                task_status = conn.execute(text("SELECT task_status, COUNT(*) FROM crawling_tasks GROUP BY task_status")).all()
            
                data_statistics_message_parts.append("Crawl tasks:\n")
                data_statistics_message_parts.append(f"  - Total number of tasks: {task_count}\n")
                for status, count in task_status:
                    data_statistics_message_parts.append(f"  - {status}: {count}\n")
            
                data_statistics_message_parts.append("Platform content statistics:\n")
                platform_tables = {
                    'instagram_post': 'Instagram',
                    'tiktok_video': 'TikTok',
                    'youtube_short': 'YouTube Shorts',
                    'youtube_video': 'YouTube',
                    'twitter_tweet': 'Twitter',
                    'reddit_post': 'Reddit',
                    'hackernews_post': 'HackerNews'
                }
            
                union_queries = []
                for table in platform_tables.keys():
                    union_queries.append(f"SELECT '{table}', COUNT(*) FROM {table}")

                query = text(" UNION ALL ".join(union_queries))
                try:
                    results = conn.execute(query).all()
                    counts = {row[0]: row[1] or 0 for row in results}
                    for table, platform in platform_tables.items():
                        count = counts.get(table, "table does not exist")
                        data_statistics_message_parts.append(f"  - {platform}: {count}\n")
                except Exception as e:
                    data_statistics_message_parts.append(f"Statistics platform table failed: {e}\n")

            logger.info("".join(data_statistics_message_parts))
        except Exception as e:
            data_statistics_message_parts.append(f"Statistics query failed: {e}\n")
            logger.error("".join(data_statistics_message_parts))
    
    def show_recent_data(self, days=7):
        """Show data for the last few days"""
        data_recent_message_parts = []
        data_recent_message_parts.append("\n" + "=" * 60 + "\n")
        data_recent_message_parts.append(f"recent {days} days of data\n")
        data_recent_message_parts.append("=" * 60 + "\n")
        
        from datetime import date
        start_date = date.today() - timedelta(days=days)

        with self.engine.connect() as conn:
            news_data = conn.execute(
                text(
                    """
                    SELECT crawl_date, COUNT(*) as news_count, COUNT(DISTINCT source_platform) as platforms
                    FROM daily_news 
                    WHERE crawl_date >= :start_date
                    GROUP BY crawl_date 
                    ORDER BY crawl_date DESC
                    """
                ),
                {"start_date": start_date},
            ).all()

            if news_data:
                data_recent_message_parts.append("Daily news statistics:\n")
                for row_date, count, platforms in news_data:
                    data_recent_message_parts.append(f"  {row_date}: {count} news, {platforms} platforms\n")

            topic_data = conn.execute(
                text(
                    """
                    SELECT extract_date, COUNT(*) as topic_count
                    FROM daily_topics 
                    WHERE extract_date >= :start_date
                    GROUP BY extract_date 
                    ORDER BY extract_date DESC
                    """
                ),
                {"start_date": start_date},
            ).all()

            if topic_data:
                data_recent_message_parts.append("Daily topic statistics:\n")
                for row_date, count in topic_data:
                    data_recent_message_parts.append(f"  {row_date}: {count} topics\n")

        logger.info("".join(data_recent_message_parts))
    
    def cleanup_old_data(self, days=90, dry_run=True):
        """Clean old data"""
        cleanup_message_parts = []
        cleanup_message_parts.append("\n" + "=" * 60)
        cleanup_message_parts.append(f"clean up{days}Data from days ago ({'preview mode' if dry_run else 'execution mode'})")
        cleanup_message_parts.append("=" * 60)
        
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        

        cleanup_queries = [
            ("daily_news", "SELECT COUNT(*) FROM daily_news WHERE crawl_date < :cutoff_date"),
            ("daily_topics", "SELECT COUNT(*) FROM daily_topics WHERE extract_date < :cutoff_date"),
            ("crawling_tasks", "SELECT COUNT(*) FROM crawling_tasks WHERE scheduled_date < :cutoff_date")
        ]
        
        def _process_cleanup(table, query, cutoff_date_val, dry_run):
            result_msg_parts = []
            try:
                # Each thread gets its own connection
                with self.engine.begin() as conn:
                    count = conn.execute(text(query), {"cutoff_date": cutoff_date_val}).scalar_one()
                    if count > 0:
                        result_msg_parts.append(f"  {table}: {count} records will be deleted\n")
                        if not dry_run:
                            delete_query = query.replace("SELECT COUNT(*)", "DELETE")
                            conn.execute(text(delete_query), {"cutoff_date": cutoff_date_val})
                            result_msg_parts.append(f"    Deleted {count} records\n")
                    else:
                        result_msg_parts.append(f"  {table}: No need to clean up\n")
            except Exception as e:
                result_msg_parts.append(f"  {table}: Cleanup failed - {e}\n")
            return "".join(result_msg_parts)

        for table, query in cleanup_queries:
            try:
                result_msg = _process_cleanup(table, query, cutoff_date.date(), dry_run)
                cleanup_message_parts.append(result_msg)
            except Exception as e:
                cleanup_message_parts.append(f"  {table}: Task execution exception - {e}\n")

        if dry_run:
            cleanup_message_parts.append("\nThis is preview mode，No data is actually deleted。Use the --execute parameter to perform the actual cleanup。\n")
        logger.info("".join(cleanup_message_parts))

def main():
    parser = argparse.ArgumentParser(description="MindSpiderDatabase management tools")
    parser.add_argument("--tables", action="store_true", help="show all tables")
    parser.add_argument("--stats", action="store_true", help="Show statistics")
    parser.add_argument("--recent", type=int, default=7, help="Display data for the last N days (default 7 days)")
    parser.add_argument("--cleanup", type=int, help="Clean data from N days ago")
    parser.add_argument("--execute", action="store_true", help="Perform actual cleanup operations")
    
    args = parser.parse_args()
    

    if not any([args.tables, args.stats, args.recent != 7, args.cleanup]):
        args.tables = True
        args.stats = True
    
    db_manager = DatabaseManager()
    
    try:
        if args.tables:
            db_manager.show_tables()
        
        if args.stats:
            db_manager.show_statistics()
        
        if args.recent != 7 or not any([args.tables, args.stats, args.cleanup]):
            db_manager.show_recent_data(args.recent)
        
        if args.cleanup:
            db_manager.cleanup_old_data(args.cleanup, dry_run=not args.execute)
    
    finally:
        db_manager.close()

if __name__ == "__main__":
    main()
