"""
Extended social and media platform SQLAlchemy ORM models for MindSpider / Trend Pulse.
Compatible with MySQL, PostgreSQL, and SQLite.
Core tables are defined in MindSpider/schema/models_sa.py.
"""

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, BigInteger, Text, ForeignKey


try:
    from .models_sa import Base
except ImportError:
    from models_sa import Base

class YoutubeVideo(Base):
    __tablename__ = "youtube_video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, unique=True)
    video_url: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    liked_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    disliked_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_play_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_favorite_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_share_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_coin_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_danmaku: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class YoutubeVideoComment(Base):
    __tablename__ = "youtube_video_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    video_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sub_comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    like_count: Mapped[str | None] = mapped_column(Text, default='0', nullable=True)


class YoutubeUpInfo(Base):
    __tablename__ = "youtube_up_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    sex: Mapped[str | None] = mapped_column(Text, nullable=True)
    sign: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_fans: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_liked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_official: Mapped[int | None] = mapped_column(Integer, nullable=True)


class YoutubeContactInfo(Base):
    __tablename__ = "youtube_contact_info"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    up_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    fan_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    up_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    fan_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    up_sign: Mapped[str | None] = mapped_column(Text, nullable=True)
    fan_sign: Mapped[str | None] = mapped_column(Text, nullable=True)
    up_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    fan_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class YoutubeUpDynamic(Base):
    __tablename__ = "youtube_up_dynamic"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dynamic_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    pub_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_forwards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_liked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class TiktokVideo(Base):
    __tablename__ = "tiktok_video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sec_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    video_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    liked_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class TiktokVideoComment(Base):
    __tablename__ = "tiktok_video_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sec_uid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_unique_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sub_comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    like_count: Mapped[str | None] = mapped_column(Text, default='0', nullable=True)
    pictures: Mapped[str | None] = mapped_column(Text, default='', nullable=True)


class DyCreator(Base):
    __tablename__ = "dy_creator"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    follows: Mapped[str | None] = mapped_column(Text, nullable=True)
    fans: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    videos_count: Mapped[str | None] = mapped_column(String(255), nullable=True)


class YoutubeShortVideo(Base):
    __tablename__ = "youtube_short_video"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    video_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    liked_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewd_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_play_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class YoutubeShortVideoComment(Base):
    __tablename__ = "youtube_short_video_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sub_comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)

class TwitterPost(Base):
    __tablename__ = "twitter_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    post_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    create_date_time: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    liked_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class TwitterPostComment(Base):
    __tablename__ = "twitter_post_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    post_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    create_date_time: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    comment_like_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class TwitterCreator(Base):
    __tablename__ = "twitter_creator"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    follows: Mapped[str | None] = mapped_column(Text, nullable=True)
    fans: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)


class InstagramCreator(Base):
    __tablename__ = "instagram_creator"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    follows: Mapped[str | None] = mapped_column(Text, nullable=True)
    fans: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)


class InstagramPost(Base):
    __tablename__ = "instagram_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    last_update_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    liked_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_count: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    tag_list: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    xsec_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)


class InstagramPostComment(Base):
    __tablename__ = "instagram_post_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    comment_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    create_time: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pictures: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    like_count: Mapped[str | None] = mapped_column(Text, nullable=True)

class RedditPost(Base):
    __tablename__ = "reddit_post"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[str | None] = mapped_column(String(644), index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_time: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    user_link: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    reddit_id: Mapped[str | None] = mapped_column(String(255), default='', nullable=True)
    reddit_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reddit_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_replay_num: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    total_replay_page: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class RedditComment(Base):
    __tablename__ = "reddit_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(255), default='', nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_link: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    reddit_id: Mapped[str | None] = mapped_column(String(255), default='', nullable=True)
    reddit_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reddit_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_time: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, default='', nullable=True)
    sub_comment_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    post_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class RedditCreator(Base):
    __tablename__ = "reddit_creator"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    follows: Mapped[str | None] = mapped_column(Text, nullable=True)
    fans: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_duration: Mapped[str | None] = mapped_column(Text, nullable=True)


class HackernewsContent(Base):
    __tablename__ = "hackernews_content"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_time: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    updated_time: Mapped[str | None] = mapped_column(Text, nullable=True)
    voteup_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    source_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_url_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    topic_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("daily_topics.topic_id", ondelete="SET NULL"), nullable=True)
    crawling_task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("crawling_tasks.task_id", ondelete="SET NULL"), nullable=True)

class HackernewsComment(Base):
    __tablename__ = "hackernews_comment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    comment_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    parent_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    publish_time: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_comment_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    dislike_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    content_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class HackernewsCreator(Base):
    __tablename__ = "hackernews_creator"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    user_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    follows: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    fans: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    anwser_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    video_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    question_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    article_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    get_voteup_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=True)
    add_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modify_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
