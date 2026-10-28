import asyncio
import os
import sys
import random
import shutil
import argparse
import html
import base64
from pathlib import Path
from typing import List, Optional, Union
import requests
import yt_dlp
import edge_tts
from playwright.async_api import async_playwright
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from threads_scraper import get_automated_story, normalize_vietnamese_text, StoryLine
from meme_harvester import harvest_all

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from moviepy import (
        VideoFileClip, ImageClip, AudioFileClip,
        CompositeVideoClip, CompositeAudioClip
    )
    MOVIEPY_V2 = True
except ImportError:
    from moviepy.editor import (
        VideoFileClip, ImageClip, AudioFileClip,
        CompositeVideoClip, CompositeAudioClip
    )
    MOVIEPY_V2 = False

CONFIG = {
    "channel_watermark": "chuyện vui trên thờ rét",
    "username": "chuyenvuithoret",
    "avatar_url": "https://api.dicebear.com/9.x/shapes/svg?seed=chuyenvuithoret",
    "voice": "vi-VN-HoaiMyNeural",
    "voice_rate": "+18%",
    "video_width": 1080,
    "video_height": 1920,
    "fps": 30
}

TARGET_THREADS_URLS = [
    "https://www.threads.net/search?q=chuy%E1%BB%87n%20h%C3%A0i&serp_type=default",
    "https://www.threads.net/search?q=c%C6%B0%E1%BB%9Di%20x%E1%BB%89u&serp_type=default"
]

STORY_DATA = {}


def ensure_real_sfx(assets_dir: Path = Path("assets"), force: bool = False):
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)
    pop_path = assets_dir / "pop.mp3"
    final_sfx_path = assets_dir / "final_sfx.mp3"
    avatar_path = assets_dir / "avatar.svg"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. Bubble Pop thật (file mẫu thật > 2KB)
    if force or not pop_path.exists() or pop_path.stat().st_size < 2000:
        print("[+] Đang tải hiệu ứng âm thanh Bubble Pop thật vào assets/pop.mp3...")
        pop_urls = [
            "https://www.myinstants.com/media/sounds/bubble-pop.mp3",
            "https://www.myinstants.com/media/sounds/pop-sound-effect.mp3",
        ]
        success = False
        for url in pop_urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200 and len(r.content) > 1000:
                    pop_path.write_bytes(r.content)
                    success = True
                    print(f"[✓] Đã lưu Bubble Pop thật ({len(r.content)} bytes)")
                    break
            except Exception as e:
                print(f"[!] Lỗi khi tải {url}: {e}")
        if not success and not pop_path.exists():
            raise RuntimeError("Không thể tải file âm thanh Bubble Pop thật.")

    # 2. SFX meme hài hước thật (Vine Boom / Rimshot, file thật > 10KB)
    if force or not final_sfx_path.exists() or final_sfx_path.stat().st_size < 10000:
        print("[+] Đang tải hiệu ứng âm thanh meme thật (Vine Boom) vào assets/final_sfx.mp3...")
        sfx_urls = [
            "https://www.myinstants.com/media/sounds/vine-boom.mp3",
            "https://www.myinstants.com/media/sounds/rimshot.mp3",
        ]
        success = False
        for url in sfx_urls:
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200 and len(r.content) > 5000:
                    final_sfx_path.write_bytes(r.content)
                    success = True
                    print(f"[✓] Đã lưu final SFX meme thật ({len(r.content)} bytes)")
                    break
            except Exception as e:
                print(f"[!] Lỗi khi tải {url}: {e}")
        if not success and not final_sfx_path.exists():
            raise RuntimeError("Không thể tải file âm thanh meme thật.")

    # 3. Cache avatar SVG cục bộ để Playwright render mượt mà không phụ thuộc mạng
    if force or not avatar_path.exists() or avatar_path.stat().st_size < 500:
        try:
            r = requests.get(CONFIG["avatar_url"], headers=headers, timeout=10)
            if r.status_code == 200 and len(r.content) > 500:
                avatar_path.write_bytes(r.content)
                print(f"[✓] Đã lưu avatar cục bộ vào assets/avatar.svg ({len(r.content)} bytes)")
        except Exception as e:
            print(f"[!] Bỏ qua lưu avatar cục bộ ({e}), sẽ dùng URL trực tiếp.")


def download_minecraft_background(
    output_path: Path = Path("assets/background.mp4"),
    query: str = "Minecraft Parkour Gameplay No Copyright 9:16 vertical",
    force: bool = False
) -> Path:
    output_path = Path(output_path)
    # File video thật 1-3 phút > 5MB
    if output_path.exists() and output_path.stat().st_size >= 5_000_000 and not force:
        return output_path

    print(f"[+] Đang dùng yt-dlp tìm kiếm và tải video nền Minecraft Parkour thật (Từ khóa: '{query}')...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for old_temp in output_path.parent.glob("temp_mc_bg*"):
        try:
            old_temp.unlink()
        except Exception:
            pass

    temp_template = str(output_path.parent / "temp_mc_bg.%(ext)s")
    search_query = f"ytsearch10:{query}"
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    selected_url = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(search_query, download=False)
            entries = res.get("entries", []) or []
            for entry in entries:
                if not entry:
                    continue
                duration = entry.get("duration") or 0
                if 60 <= duration <= 240:
                    selected_url = entry.get("webpage_url")
                    print(f"[+] Chọn video Minecraft phù hợp: {entry.get('title')} ({duration}s)")
                    break

            if not selected_url:
                for entry in entries:
                    if entry and (entry.get("duration") or 0) >= 45:
                        selected_url = entry.get("webpage_url")
                        print(f"[+] Chọn video Minecraft thay thế: {entry.get('title')} ({entry.get('duration')}s)")
                        break
    except Exception as e:
        print(f"[!] Lỗi khi tìm kiếm qua yt-dlp: {e}")

    if not selected_url:
        selected_url = "https://www.youtube.com/watch?v=2VpG0WS4uCo"

    print(f"[+] Đang tải video Minecraft từ: {selected_url}")
    download_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": temp_template,
        "noplaylist": True,
        "quiet": False,
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(download_opts) as ydl:
        ydl.download([selected_url])

    candidates = list(output_path.parent.glob("temp_mc_bg*.mp4"))
    if not candidates:
        candidates = list(output_path.parent.glob("temp_mc_bg*"))
    if candidates:
        downloaded = candidates[0]
        if output_path.exists():
            output_path.unlink()
        shutil.move(str(downloaded), str(output_path))
        print(f"[✓] Đã tải và lưu video nền vào: {output_path} ({output_path.stat().st_size / (1024*1024):.1f} MB)")
    else:
        raise RuntimeError("Không tìm thấy file video sau khi yt-dlp hoàn thành.")

    return output_path


def build_threads_html(
    username: str,
    avatar_url: str,
    time_ago: str,
    lines: list,
    likes: str,
    replies: str,
    visible_count: Optional[int] = None,
) -> str:
    if visible_count is None:
        visible_count = len(lines)

    # Sử dụng avatar đã cache cục bộ dưới dạng data URI nếu có
    effective_avatar_url = avatar_url
    local_avatar = Path("assets/avatar.svg")
    if local_avatar.exists():
        try:
            svg_b64 = base64.b64encode(local_avatar.read_bytes()).decode("utf-8")
            effective_avatar_url = f"data:image/svg+xml;base64,{svg_b64}"
        except Exception:
            effective_avatar_url = avatar_url

    p_elements = []
    for idx, line in enumerate(lines):
        if isinstance(line, dict):
            line_str = line.get("text", "")
        elif hasattr(line, "text"):
            line_str = line.text
        else:
            line_str = str(line)
        norm_line = normalize_vietnamese_text(line_str)
        escaped_line = html.escape(norm_line)
        opacity = "1" if idx < visible_count else "0"
        p_elements.append(f'<p style="opacity: {opacity};">{escaped_line}</p>')
    paragraphs = "".join(p_elements)

    actions_opacity = "1" if visible_count >= len(lines) else "0"

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: transparent;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 20px;
        }}
        .threads-card {{
            width: 960px;
            background-color: #181818;
            border: 2px solid #2f2f2f;
            border-radius: 32px;
            padding: 40px 44px;
            color: #f3f5f7;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.65);
        }}
        .header {{ display: flex; align-items: center; margin-bottom: 24px; }}
        .avatar {{ width: 76px; height: 76px; border-radius: 50%; background: #333; margin-right: 22px; object-fit: cover; border: 2px solid #3a3a3a; }}
        .user-meta {{ display: flex; align-items: center; gap: 12px; }}
        .username {{ font-size: 32px; font-weight: 700; color: #ffffff; }}
        .verified {{ width: 28px; height: 28px; fill: #0095f6; }}
        .time {{ font-size: 28px; color: #777777; margin-left: 6px; }}
        .content p {{ font-size: 40px; line-height: 1.48; color: #f3f5f7; margin-bottom: 20px; font-weight: 500; word-break: break-word; overflow-wrap: break-word; }}
        .content p:last-child {{ margin-bottom: 28px; }}
        .actions {{ display: flex; align-items: center; gap: 38px; color: #cccccc; font-size: 28px; padding-top: 8px; opacity: {actions_opacity}; }}
        .action-item {{ display: flex; align-items: center; gap: 12px; }}
        .action-item svg {{ width: 36px; height: 36px; stroke: #e0e0e0; stroke-width: 2; fill: none; }}
        .heart svg {{ fill: #ff3040; stroke: #ff3040; }}
    </style>
    </head>
    <body>
        <div class="threads-card" id="card">
            <div class="header">
                <img class="avatar" src="{effective_avatar_url}" />
                <div class="user-meta">
                    <span class="username">{username}</span>
                    <svg class="verified" viewBox="0 0 40 40"><path d="M19.998 3.094 14.638 0l-2.972 5.15H5.432v6.354L0 14.64 3.094 20 0 25.359l5.432 3.137v5.905h5.975L14.638 40l5.36-3.094L25.358 40l3.232-5.6h6.162v-6.01L40 25.359 36.905 20 40 14.641l-5.248-3.03v-6.46h-6.419L25.358 0l-5.36 3.094Zm7.415 11.225 2.254 2.287-11.43 11.5-6.835-6.93 2.244-2.258 4.587 4.581 9.18-9.18Z"/></svg>
                    <span class="time">{time_ago}</span>
                </div>
            </div>
            <div class="content">{paragraphs}</div>
            <div class="actions" style="opacity: {actions_opacity};">
                <div class="action-item heart">
                    <svg viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>
                    <span>{likes}</span>
                </div>
                <div class="action-item">
                    <svg viewBox="0 0 24 24"><path d="M20.656 17.008a9.993 9.993 0 1 0-3.59 3.615L22 22Z"/></svg>
                    <span>{replies}</span>
                </div>
            </div>
        </div>
    </body>
    </html>
    """


def build_watermark_html(text: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8">
    <style>
        body {{ background: transparent; margin: 0; padding: 15px; }}
        .wm {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 38px; font-weight: 800; color: rgba(255, 255, 255, 0.85); text-shadow: 0 4px 12px rgba(0, 0, 0, 0.8); letter-spacing: 1px; display: inline-block; }}
    </style>
    </head>
    <body><div class="wm" id="wm">{text}</div></body>
    </html>
    """


def clip_subclip(clip, t_start, t_end):
    return clip.subclipped(t_start, t_end) if MOVIEPY_V2 else clip.subclip(t_start, t_end)


def clip_set_start(clip, t):
    return clip.with_start(t) if MOVIEPY_V2 else clip.set_start(t)


def clip_set_duration(clip, d):
    return clip.with_duration(d) if MOVIEPY_V2 else clip.set_duration(d)


def clip_set_position(clip, pos):
    return clip.with_position(pos) if MOVIEPY_V2 else clip.set_position(pos)


def clip_with_audio(video_clip, audio_clip):
    return video_clip.with_audio(audio_clip) if MOVIEPY_V2 else video_clip.set_audio(audio_clip)


def clip_set_volume(clip, factor: float):
    if hasattr(clip, "with_volume_scaled"):
        return clip.with_volume_scaled(factor)
    elif hasattr(clip, "volumex"):
        return clip.volumex(factor)
    return clip


def clip_resize_width(clip, width: int):
    if hasattr(clip, "resized"):
        return clip.resized(width=width)
    elif hasattr(clip, "resize"):
        return clip.resize(width=width)
    return clip


def crop_to_9_16(clip, target_w=1080, target_h=1920):
    w, h = clip.size
    target_ratio = target_w / target_h
    current_ratio = w / h
    if abs(current_ratio - target_ratio) > 0.02:
        if current_ratio > target_ratio:
            new_w = int(h * target_ratio)
            x1 = (w - new_w) // 2
            clip = clip.cropped(x1=x1, x2=x1 + new_w) if MOVIEPY_V2 else clip.crop(x1=x1, x2=x1 + new_w)
        else:
            new_h = int(w / target_ratio)
            y1 = (h - new_h) // 2
            clip = clip.cropped(y1=y1, y2=y1 + new_h) if MOVIEPY_V2 else clip.crop(y1=y1, y2=y1 + new_h)
    return clip.resized((target_w, target_h)) if MOVIEPY_V2 else clip.resize((target_w, target_h))


async def generate_tts(text: str, output_path: Path, max_retries: int = 5, voice: Optional[str] = None):
    primary_voice = voice or CONFIG["voice"]
    voices = [primary_voice]
    for v in ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"]:
        if v not in voices:
            voices.append(v)

    norm_text = normalize_vietnamese_text(text)
    last_error = None
    for attempt in range(max_retries):
        chosen_voice = voices[attempt % len(voices)]
        rate = CONFIG["voice_rate"] if attempt < 2 else "+0%"
        try:
            communicate = edge_tts.Communicate(text=norm_text, voice=chosen_voice, rate=rate)
            await communicate.save(str(output_path))
            if output_path.exists() and output_path.stat().st_size > 0:
                return
            raise RuntimeError("File TTS sinh ra rỗng (0 bytes).")
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                wait_time = 2.0 * (attempt + 1)
                print(f"[!] TTS thử lại lần {attempt + 1} sau {wait_time:.1f}s cho câu: '{norm_text[:30]}...'")
                await asyncio.sleep(wait_time)

    # Dự phòng cứu cánh gTTS nếu Microsoft Edge-TTS bị nghẽn
    try:
        from gtts import gTTS
        print(f"[!] Chuyển sang gTTS dự phòng cho câu: '{norm_text[:30]}...'")
        tts = gTTS(text=norm_text, lang='vi')
        tts.save(str(output_path))
        if output_path.exists() and output_path.stat().st_size > 0:
            return
    except Exception as g_err:
        print(f"[!] Lỗi gTTS dự phòng: {g_err}")

    raise RuntimeError(f"Không thể tạo âm thanh TTS sau {max_retries} lần thử: {last_error}")


def trim_audio_silence(file_path: Path, silence_thresh: int = -40, padding_ms: int = 80):
    try:
        audio = AudioSegment.from_file(str(file_path))
        nonsilent_ranges = detect_nonsilent(audio, min_silence_len=100, silence_thresh=silence_thresh)
        if not nonsilent_ranges:
            return
        start_i = max(0, nonsilent_ranges[0][0] - padding_ms)
        end_i = min(len(audio), nonsilent_ranges[-1][1] + padding_ms)
        audio[start_i:end_i].export(str(file_path), format="mp3")
    except Exception as e:
        print(f"[!] Không thể cắt khoảng lặng file {file_path.name}: {e}")


async def prepare_media_assets(story_data_or_temp_dir=None, temp_dir: Path = None):
    global STORY_DATA
    # Hỗ trợ cả 2 cách gọi: (story_data, temp_dir) hoặc (temp_dir)
    if temp_dir is None:
        if isinstance(story_data_or_temp_dir, (str, Path)):
            temp_dir = Path(story_data_or_temp_dir)
            auto_mod = sys.modules.get("auto_threads_video")
            story_data = getattr(auto_mod, "STORY_DATA", None) or STORY_DATA or (SAMPLE_STORIES[0] if SAMPLE_STORIES else {})
        elif isinstance(story_data_or_temp_dir, dict):
            story_data = story_data_or_temp_dir
            temp_dir = Path("temp_current_build")
        else:
            temp_dir = Path("temp_current_build")
            story_data = STORY_DATA or (SAMPLE_STORIES[0] if SAMPLE_STORIES else {})
    else:
        story_data = story_data_or_temp_dir or STORY_DATA or (SAMPLE_STORIES[0] if SAMPLE_STORIES else {})
        temp_dir = Path(temp_dir)

    temp_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page(viewport={"width": 1080, "height": 1920})

        wm_html = build_watermark_html(CONFIG["channel_watermark"])
        await page.set_content(wm_html)
        wm_path = temp_dir / "watermark.png"
        await page.locator("#wm").screenshot(path=str(wm_path), omit_background=True)

        cards = story_data.get("cards", [])
        for card_idx, card in enumerate(cards):
            card_id = card.get("card_id", card_idx + 1) if isinstance(card, dict) else getattr(card, "card_id", card_idx + 1)
            time_ago = card.get("time_ago", "1 giờ") if isinstance(card, dict) else getattr(card, "time_ago", "1 giờ")
            likes = card.get("likes", "10K") if isinstance(card, dict) else getattr(card, "likes", "10K")
            replies = card.get("replies", "200") if isinstance(card, dict) else getattr(card, "replies", "200")
            card_lines = card.get("lines", []) if isinstance(card, dict) else getattr(card, "lines", [])

            for idx, line_obj in enumerate(card_lines):
                step_name = f"c{card_id}_s{idx + 1}"

                if isinstance(line_obj, dict):
                    line_text = line_obj.get("text", "")
                    line_voice = line_obj.get("voice", CONFIG["voice"])
                    line_sfx = line_obj.get("sfx_after", "none")
                elif hasattr(line_obj, "text"):
                    line_text = line_obj.text
                    line_voice = getattr(line_obj, "voice", CONFIG["voice"])
                    line_sfx = getattr(line_obj, "sfx_after", "none")
                else:
                    line_text = str(line_obj)
                    line_voice = CONFIG["voice"]
                    line_sfx = "none"

                audio_path = temp_dir / f"{step_name}.mp3"
                await generate_tts(line_text, audio_path, voice=line_voice)
                await asyncio.sleep(0.3)
                trim_audio_silence(audio_path)

                # Chống giật khung: Luôn truyền TOÀN BỘ các câu của Card đó vào HTML
                # Câu chưa đọc dùng CSS opacity: 0; Hàng .actions chỉ hiện ở câu cuối cùng
                html_content = build_threads_html(
                    username=CONFIG["username"],
                    avatar_url=CONFIG["avatar_url"],
                    time_ago=time_ago,
                    lines=card_lines,
                    likes=likes,
                    replies=replies,
                    visible_count=idx + 1,
                )
                await page.set_content(html_content, wait_until="networkidle")
                img_path = temp_dir / f"{step_name}.png"
                await page.locator("#card").screenshot(path=str(img_path), omit_background=True)

                is_final_line = (card_idx == len(cards) - 1) and (idx == len(card_lines) - 1)

                segments.append({
                    "image": img_path,
                    "audio": audio_path,
                    "sfx_after": line_sfx,
                    "is_final_line": is_final_line,
                })

        await browser.close()
    return segments, wm_path


def build_final_video(
    segments: list,
    wm_path: Path,
    output_file: str = "output_short.mp4",
    use_video_meme_outro: bool = True
):
    # Đảm bảo video nền Minecraft thật, SFX thật và kho meme luôn sẵn sàng
    download_minecraft_background()
    ensure_real_sfx()
    harvest_all()

    bg_path = Path("assets/background.mp4")
    if not bg_path.exists():
        raise FileNotFoundError("Không tìm thấy file 'assets/background.mp4'.")

    pop_path = Path("assets/pop.mp3")
    final_sfx_path = Path("assets/final_sfx.mp3")

    visual_clips = []
    audio_clips = []
    current_time = 0.0

    for seg in segments:
        voice_clip = AudioFileClip(str(seg["audio"]))
        voice_duration = voice_clip.duration

        voice_clip = clip_set_start(voice_clip, current_time)
        audio_clips.append(voice_clip)

        if pop_path.exists():
            try:
                pop_clip = clip_set_start(AudioFileClip(str(pop_path)), current_time)
                audio_clips.append(pop_clip)
            except Exception as e:
                print(f"[!] Bỏ qua pop sfx do lỗi: {e}")

        # Mid-SFX: Nếu câu có sfx_after != 'none', chèn ngay sau câu đọc và nghỉ 0.4s-0.6s
        sfx_after = seg.get("sfx_after", "none")
        sfx_extra_duration = 0.0

        if sfx_after and sfx_after != "none":
            candidate_paths = [
                Path(f"assets/sfx/{sfx_after}.mp3"),
                Path(f"assets/sfx/{sfx_after}.wav"),
                Path(f"assets/{sfx_after}.mp3"),
            ]
            sfx_file = None
            for cp in candidate_paths:
                if cp.exists():
                    sfx_file = cp
                    break

            if sfx_file:
                try:
                    sfx_clip = AudioFileClip(str(sfx_file))
                    # Giới hạn thời lượng phát SFX tối đa 2.2s và subclip để âm thanh ngắt dứt khoát trước câu sau
                    sfx_play_duration = min(sfx_clip.duration, 2.2)
                    sfx_clip = clip_subclip(sfx_clip, 0, sfx_play_duration)
                    sfx_start = current_time + voice_duration
                    sfx_clip = clip_set_start(sfx_clip, sfx_start)
                    audio_clips.append(sfx_clip)
                    # Độ trễ nghỉ 0.5s (trong khoảng 0.4s-0.6s) để người xem kịp nghe và cười với tiếng meme
                    pause_delay = 0.5
                    sfx_extra_duration = sfx_play_duration + pause_delay
                except Exception as e:
                    print(f"[!] Bỏ qua sfx {sfx_after} do lỗi: {e}")

        step_duration = voice_duration + sfx_extra_duration

        img_clip = ImageClip(str(seg["image"]))
        img_clip = clip_set_start(img_clip, current_time)
        img_clip = clip_set_duration(img_clip, step_duration)
        img_clip = clip_set_position(img_clip, ("center", "center"))
        visual_clips.append(img_clip)

        current_time += step_duration

    # Fallback final_sfx nếu câu cuối cùng không có Mid-SFX VÀ không có video meme outro
    if visual_clips and (not segments or segments[-1].get("sfx_after", "none") == "none") and not use_video_meme_outro and final_sfx_path.exists():
        try:
            sfx_clip = AudioFileClip(str(final_sfx_path))
            sfx_clip = clip_set_start(sfx_clip, max(0, current_time - 0.15))
            audio_clips.append(sfx_clip)
            extra_tail = min(sfx_clip.duration, 1.5)
            visual_clips[-1] = clip_set_duration(visual_clips[-1], visual_clips[-1].duration + extra_tail)
            current_time += extra_tail
        except Exception as e:
            print(f"[!] Bỏ qua final sfx do lỗi: {e}")

    # Video Meme Reaction cuối bài
    meme_clips_to_close = []
    if use_video_meme_outro:
        vm_dir = Path("assets/video_memes")
        vm_candidates = sorted(list(vm_dir.glob("*.mp4")) + list(vm_dir.glob("*.webm")))
        if vm_candidates:
            chosen_meme = random.choice(vm_candidates)
            print(f"[+] Chèn Video Meme reaction cuối bài: {chosen_meme.name}")
            try:
                meme_clip = VideoFileClip(str(chosen_meme))
                # Resize về chiều rộng 750px
                meme_clip = clip_resize_width(meme_clip, 750)

                # Giới hạn chiều cao meme tối đa 440px (chuẩn 16:9 ở width 750 là 422px) để không che khuất card
                if meme_clip.size[1] > 440:
                    target_h = int(750 * 9 / 16)
                    y_crop = (meme_clip.size[1] - target_h) // 2
                    meme_clip = meme_clip.cropped(y1=y_crop, y2=y_crop + target_h) if MOVIEPY_V2 else meme_clip.crop(y1=y_crop, y2=y_crop + target_h)

                meme_start = current_time
                meme_duration = meme_clip.duration

                meme_clip = clip_set_start(meme_clip, meme_start)

                # Đặt ở nửa dưới màn hình bên dưới khung Threads (tính theo card_bottom thực tế)
                card_h = visual_clips[-1].size[1] if visual_clips else 700
                card_bottom = (CONFIG["video_height"] + card_h) / 2
                meme_h = meme_clip.size[1]

                # Đặt cách cạnh dưới card 25px, đảm bảo luôn nằm dưới card và không vượt mép dưới màn hình (1920)
                pos_y = int(card_bottom + 25)
                if pos_y + meme_h > 1880:
                    pos_y = max(int(card_bottom + 10), 1880 - meme_h)

                meme_clip = clip_set_position(meme_clip, ("center", pos_y))

                # Nối thêm thời lượng của clip meme vào khung Threads Card 2 bên trên
                if visual_clips:
                    visual_clips[-1] = clip_set_duration(visual_clips[-1], visual_clips[-1].duration + meme_duration)

                visual_clips.append(meme_clip)
                meme_clips_to_close.append(meme_clip)

                # Nối âm thanh của clip meme
                if meme_clip.audio:
                    meme_audio = clip_set_start(meme_clip.audio, meme_start)
                    audio_clips.append(meme_audio)

                current_time += meme_duration
            except Exception as e:
                print(f"[!] Bỏ qua video meme reaction do lỗi: {e}")

    total_duration = current_time

    # Nhạc nền BGM: chọn ngẫu nhiên, hạ âm lượng xuống 12% và phát xuyên suốt video
    bgm_clips_to_close = []
    bgm_dir = Path("assets/bgm")
    bgm_candidates = sorted(list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav")))
    if bgm_candidates:
        chosen_bgm = random.choice(bgm_candidates)
        print(f"[+] Lồng BGM ngẫu nhiên: {chosen_bgm.name} (Âm lượng 12%)")
        try:
            bgm_clip = AudioFileClip(str(chosen_bgm))
            if bgm_clip.duration < total_duration:
                repeats = int(total_duration // bgm_clip.duration) + 1
                try:
                    from moviepy import concatenate_audioclips
                except ImportError:
                    from moviepy.editor import concatenate_audioclips
                bgm_clip = concatenate_audioclips([bgm_clip] * repeats)

            bgm_clip = clip_subclip(bgm_clip, 0, total_duration)
            bgm_clip = clip_set_start(bgm_clip, 0)
            bgm_clip = clip_set_duration(bgm_clip, total_duration)
            # Giảm âm lượng xuống 12%
            bgm_clip = clip_set_volume(bgm_clip, 0.12)
            audio_clips.insert(0, bgm_clip)
            bgm_clips_to_close.append(bgm_clip)
        except Exception as e:
            print(f"[!] Lỗi khi lồng BGM {chosen_bgm.name}: {e}")

    bg_video = VideoFileClip(str(bg_path))

    # Nếu video nền ngắn hơn độ dài kịch bản, lặp lại video để tránh khung hình đen
    if bg_video.duration < total_duration:
        repeats = int(total_duration // bg_video.duration) + 1
        try:
            from moviepy import concatenate_videoclips
        except ImportError:
            from moviepy.editor import concatenate_videoclips
        bg_video = concatenate_videoclips([bg_video] * repeats)

    if bg_video.duration > total_duration + 2:
        start_pt = random.uniform(0, bg_video.duration - total_duration - 1)
        bg_video = clip_subclip(bg_video, start_pt, start_pt + total_duration)
    else:
        bg_video = clip_subclip(bg_video, 0, total_duration)

    bg_video = crop_to_9_16(bg_video, CONFIG["video_width"], CONFIG["video_height"])

    wm_clip = ImageClip(str(wm_path))
    wm_clip = clip_set_start(wm_clip, 0)
    wm_clip = clip_set_duration(wm_clip, total_duration)
    wm_clip = clip_set_position(wm_clip, ("center", 160))

    final_video = CompositeVideoClip([bg_video, wm_clip] + visual_clips)
    final_audio = CompositeAudioClip(audio_clips)
    final_video = clip_with_audio(final_video, final_audio)

    try:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        final_video.write_videofile(
            output_file,
            fps=CONFIG["fps"],
            codec="libx264",
            audio_codec="aac",
            threads=4
        )
        print(f"[✓] Đã xuất file: {output_file}")
    finally:
        for c in [bg_video, final_video, final_audio] + visual_clips + audio_clips + meme_clips_to_close + bgm_clips_to_close:
            try:
                c.close()
            except Exception:
                pass


async def render_story_video(
    story_data: dict,
    output_file: str = "output_short.mp4",
    temp_dir: Path = None,
    use_video_meme_outro: Optional[bool] = None,
) -> str:
    cleanup_temp = False
    if temp_dir is None:
        temp_dir = Path(f"temp_build_{random.randint(1000, 9999)}")
        cleanup_temp = True

    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        segments, wm_path = await prepare_media_assets(story_data, temp_dir)
        meme_outro = use_video_meme_outro if use_video_meme_outro is not None else story_data.get("use_video_meme_outro", True)
        build_final_video(segments, wm_path, output_file=output_file, use_video_meme_outro=meme_outro)
        return output_file
    finally:
        if cleanup_temp and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


SAMPLE_STORIES = [
    {
        "humor_score": 10,
        "title": "Tiểu Minh và bài văn tả người hùng",
        "use_video_meme_outro": True,
        "cards": [
            {
                "card_id": 1,
                "time_ago": "2 giờ",
                "likes": "18,4K",
                "replies": "412",
                "lines": [
                    StoryLine(
                        text="Trong giờ tập làm văn, cô giáo yêu cầu cả lớp viết về một người hùng thầm lặng trong gia đình.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Tiểu Minh hào hứng viết liền hai trang giấy mà không cần dừng lại suy nghĩ một giây nào.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Cô giáo đọc bài văn thấy rưng rưng nước mắt vì sự hi sinh cao cả của người bố.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="wow",
                    ),
                ],
            },
            {
                "card_id": 2,
                "time_ago": "2 giờ",
                "likes": "18,4K",
                "replies": "412",
                "lines": [
                    StoryLine(
                        text="Đến cuối bài, cô xúc động hỏi: 'Bố em làm công việc nguy hiểm đến thế này thật sao?'",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="huh",
                    ),
                    StoryLine(
                        text="Tiểu Minh ngây thơ đáp: 'Dạ không cô ơi, em tả lại cảnh bố em đi rửa bát đấy ạ!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="cai_gi_do",
                    ),
                    StoryLine(
                        text="'Chỉ cần lỡ tay làm vỡ một cái đĩa là mẹ em cho bay màu ngay lập tức!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="vine_boom",
                    ),
                ],
            },
        ],
    },
    {
        "humor_score": 10,
        "title": "Ai đã lấy cắp nỏ thần của An Dương Vương",
        "use_video_meme_outro": True,
        "cards": [
            {
                "card_id": 1,
                "time_ago": "1 giờ",
                "likes": "24,8K",
                "replies": "652",
                "lines": [
                    StoryLine(
                        text="Trong giờ kiểm tra miệng môn Lịch sử, thầy giáo nghiêm giọng gọi Tiểu Minh đứng lên bảng.",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Thầy chỉ tay hỏi: 'Em hãy cho thầy biết, ai là người đã lấy cắp nỏ thần của An Dương Vương?'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="huh",
                    ),
                    StoryLine(
                        text="Tiểu Minh hoảng hốt, mặt mũi tái mét vội vàng chắp tay thề thốt trước cả lớp.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                ],
            },
            {
                "card_id": 2,
                "time_ago": "1 giờ",
                "likes": "24,8K",
                "replies": "652",
                "lines": [
                    StoryLine(
                        text="Cậu mếu máo nói: 'Thưa thầy, em thề danh dự là cả dòng họ nhà em không ai lấy cắp nỏ thần đâu ạ!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="laugh",
                    ),
                    StoryLine(
                        text="Thầy giáo bực mình gọi điện thoại ngay cho phụ huynh để phàn nàn về thái độ của con trai.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="cai_gi_do",
                    ),
                    StoryLine(
                        text="Đầu dây bên kia, bố Tiểu Minh thở dài: 'Thôi thầy xem cái nỏ đó bao nhiêu tiền để tôi chuyển khoản đền cái khác!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="vine_boom",
                    ),
                ],
            },
        ],
    },
    {
        "humor_score": 9,
        "title": "Bài kiểm tra Toán đạt điểm mười",
        "use_video_meme_outro": True,
        "cards": [
            {
                "card_id": 1,
                "time_ago": "3 giờ",
                "likes": "31,5K",
                "replies": "890",
                "lines": [
                    StoryLine(
                        text="Vừa đi học về, Tiểu Minh đã hớn hở chạy ngay vào phòng khách khoe bài kiểm tra môn Toán.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Bố nhìn thấy con trai đạt điểm mười tuyệt đối thì mừng rỡ rút ngay tờ năm trăm nghìn đồng ra thưởng nóng.",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="wow",
                    ),
                    StoryLine(
                        text="Bố tự hào vỗ ngực: 'Gen thông minh của bố đúng là đỉnh cao, không lẫn đi đâu được!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="none",
                    ),
                ],
            },
            {
                "card_id": 2,
                "time_ago": "3 giờ",
                "likes": "31,5K",
                "replies": "890",
                "lines": [
                    StoryLine(
                        text="Cầm tiền trong tay, Tiểu Minh ghé sát tai bố rồi thỏ thẻ hỏi một câu vô cùng chân thành.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="'Bố ơi, thế bố có muốn chia cho bạn lớp trưởng ngồi cạnh con một nửa số tiền này không?'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="huh",
                    ),
                    StoryLine(
                        text="Đúng lúc đó, mẹ từ trong bếp bước ra với chiếc chổi lông gà trên tay.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="vine_boom",
                    ),
                ],
            },
        ],
    },
    {
        "humor_score": 9,
        "title": "Bát canh xương hầm tẩm bổ",
        "use_video_meme_outro": True,
        "cards": [
            {
                "card_id": 1,
                "time_ago": "4 giờ",
                "likes": "15,2K",
                "replies": "328",
                "lines": [
                    StoryLine(
                        text="Dạo gần đây mẹ hay than phiền bị đau lưng nên bố quyết định đích thân trổ tài nấu ăn tẩm bổ.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Bố cặm cụi dưới bếp suốt bốn tiếng đồng hồ để ninh một nồi canh xương hầm thơm phức.",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="wow",
                    ),
                    StoryLine(
                        text="Mẹ đi làm về thấy bàn ăn thịnh soạn thì cảm động suýt khóc vì sự chu đáo của chồng.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                ],
            },
            {
                "card_id": 2,
                "time_ago": "4 giờ",
                "likes": "15,2K",
                "replies": "328",
                "lines": [
                    StoryLine(
                        text="Ăn xong bát canh, mẹ ân cần hỏi: 'Hôm nay trời bão hay sao mà bố nó tự dưng đảm đang thế?'",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="huh",
                    ),
                    StoryLine(
                        text="Bố gãi đầu cười trừ: 'À thì chiều nay bố lỡ tay làm rơi vỡ bộ ấm chén Bát Tràng của ông ngoại...'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="cai_gi_do",
                    ),
                    StoryLine(
                        text="'Nên bố nấu nồi canh xương này để mẹ có thêm canxi mà giữ bình tĩnh đấy!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="vine_boom",
                    ),
                ],
            },
        ],
    },
    {
        "humor_score": 10,
        "title": "Đi chợ mua cá tươi giúp mẹ",
        "use_video_meme_outro": True,
        "cards": [
            {
                "card_id": 1,
                "time_ago": "5 giờ",
                "likes": "42,1K",
                "replies": "1.230",
                "lines": [
                    StoryLine(
                        text="Mẹ đang bận nấu cơm nên đưa tiền nhờ con trai ra chợ mua một con cá chép thật tươi.",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Mẹ dặn dò rất kỹ: 'Nhớ chọn con nào quẫy thật khỏe, mang đỏ tươi và mắt trong veo nhé!'",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="none",
                    ),
                    StoryLine(
                        text="Hai tiếng trôi qua, con trai mới hớt hải ôm túi cá chạy về với nụ cười rạng rỡ trên môi.",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="wow",
                    ),
                ],
            },
            {
                "card_id": 2,
                "time_ago": "5 giờ",
                "likes": "42,1K",
                "replies": "1.230",
                "lines": [
                    StoryLine(
                        text="Mẹ mở túi ra kiểm tra thì thấy con cá đã nằm im bất động từ bao giờ.",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="cai_gi_do",
                    ),
                    StoryLine(
                        text="Mẹ tức giận quát: 'Mẹ dặn mua cá đang quẫy khỏe, sao giờ đơ ra như khúc gỗ thế này?'",
                        voice="vi-VN-HoaiMyNeural",
                        sfx_after="huh",
                    ),
                    StoryLine(
                        text="Con trai tự hào giải thích: 'Tại trên đường về con sợ nó mệt, nên con đã bế nó đi bộ về đấy mẹ!'",
                        voice="vi-VN-NamMinhNeural",
                        sfx_after="vine_boom",
                    ),
                ],
            },
        ],
    },
]


async def main():
    parser = argparse.ArgumentParser(description="Threads Shorts Video Builder with BGM, Mid-SFX, and Meme Reactions")
    parser.add_argument("--count", type=int, default=1, help="Số lượng video cần tạo (mặc định: 1)")
    parser.add_argument("--urls", nargs="+", default=TARGET_THREADS_URLS, help="Danh sách URL Threads cần quét")
    parser.add_argument("--watermark", default=CONFIG["channel_watermark"], help="Watermark kênh")
    parser.add_argument("--voice", default=CONFIG["voice"], help="Giọng đọc edge-tts mặc định")
    parser.add_argument("--output", default="output_short.mp4", help="Đường dẫn file video đầu ra (mặc định: output_short.mp4)")
    parser.add_argument("--mock", action="store_true", help="Dùng kịch bản mẫu (không cần API key)")
    parser.add_argument("--no-meme", action="store_true", help="Không chèn video meme reaction cuối bài")
    args = parser.parse_args()

    CONFIG["channel_watermark"] = args.watermark
    CONFIG["voice"] = args.voice

    total_videos = args.count
    api_key = os.environ.get("GEMINI_API_KEY")

    for i in range(1, total_videos + 1):
        print(f"\n========================================")
        print(f"🎬 ĐANG XỬ LÝ VIDEO THỨ {i} / {total_videos}")
        print(f"========================================")

        story_data = None
        if not args.mock and api_key:
            print("[+] Đang quét Threads và tạo kịch bản với Gemini AI...")
            try:
                story_data = await get_automated_story(args.urls, api_key=api_key)
            except Exception as e:
                print(f"[!] Không thể quét Threads hoặc gọi Gemini ({e}). Tự động kích hoạt kho kịch bản cười học đường/gia đình chuẩn...")
                story_data = None

        if not story_data:
            if not args.mock and not api_key:
                print("[!] Chưa cấu hình GEMINI_API_KEY trong môi trường. Đang sử dụng kho kịch bản cười học đường/gia đình có twist...")
            story_data = SAMPLE_STORIES[(i - 1) % len(SAMPLE_STORIES)]
            print(f"[✓] Đã chọn kịch bản từ kho: '{story_data.get('title', 'Kịch bản viral')}' (Điểm hài hước: {story_data.get('humor_score', 10)}/10)")

        out_name = f"output_short_batch_{i}.mp4" if total_videos > 1 else args.output
        use_meme = not args.no_meme
        await render_story_video(story_data, output_file=out_name, use_video_meme_outro=use_meme)

    print(f"\n🎉 HOÀN TẤT! Đã xuất xong {total_videos} video.")


if __name__ == "__main__":
    asyncio.run(main())
