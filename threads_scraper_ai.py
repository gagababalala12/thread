"""
threads_scraper_ai.py - Cung cấp giao diện AI Story Formatter & Audio Director đồng bộ với threads_scraper.
"""

from threads_scraper import (
    StoryLine,
    ThreadCard,
    StorySelection,
    normalize_vietnamese_text,
    load_history,
    save_history,
    scrape_threads_posts,
    select_and_format_story,
    get_automated_story,
    HISTORY_FILE,
    DEFAULT_MODEL,
    VIETNAMESE_ABBREVIATIONS,
    TARGET_THREADS_URLS,
)

__all__ = [
    "StoryLine",
    "ThreadCard",
    "StorySelection",
    "normalize_vietnamese_text",
    "load_history",
    "save_history",
    "scrape_threads_posts",
    "select_and_format_story",
    "get_automated_story",
    "HISTORY_FILE",
    "DEFAULT_MODEL",
    "VIETNAMESE_ABBREVIATIONS",
    "TARGET_THREADS_URLS",
]
