"""
auto_threads_video.py - Tự động tạo video YouTube Shorts từ Threads với BGM, Mid-SFX và Video Meme Reaction.
"""

import asyncio
from threads_video_builder import (
    CONFIG,
    TARGET_THREADS_URLS,
    SAMPLE_STORIES,
    download_minecraft_background,
    ensure_real_sfx,
    build_threads_html,
    build_watermark_html,
    generate_tts,
    trim_audio_silence,
    prepare_media_assets,
    build_final_video,
    render_story_video,
    clip_subclip,
    clip_set_start,
    clip_set_duration,
    clip_set_position,
    clip_with_audio,
    clip_set_volume,
    clip_resize_width,
    crop_to_9_16,
    main,
)

__all__ = [
    "CONFIG",
    "TARGET_THREADS_URLS",
    "SAMPLE_STORIES",
    "download_minecraft_background",
    "ensure_real_sfx",
    "build_threads_html",
    "build_watermark_html",
    "generate_tts",
    "trim_audio_silence",
    "prepare_media_assets",
    "build_final_video",
    "render_story_video",
    "clip_subclip",
    "clip_set_start",
    "clip_set_duration",
    "clip_set_position",
    "clip_with_audio",
    "clip_set_volume",
    "clip_resize_width",
    "crop_to_9_16",
    "main",
]

if __name__ == "__main__":
    asyncio.run(main())
