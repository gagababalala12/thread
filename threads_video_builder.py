import asyncio
import os
import random
import shutil
import argparse
from pathlib import Path
import edge_tts
from playwright.async_api import async_playwright
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
from threads_scraper_ai import get_automated_story

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
    "channel_watermark": "hamster kể chuyện",
    "username": "tieuminh.page",
    "avatar_url": "https://api.dicebear.com/9.x/adventurer/svg?seed=Felix",
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


def build_threads_html(username: str, avatar_url: str, time_ago: str, lines: list, likes: str, replies: str) -> str:
    paragraphs = "".join([f"<p>{line}</p>" for line in lines])
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
            width: 940px;
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
        .content p {{ font-size: 35px; line-height: 1.48; color: #f3f5f7; margin-bottom: 20px; font-weight: 400; }}
        .content p:last-child {{ margin-bottom: 28px; }}
        .actions {{ display: flex; align-items: center; gap: 38px; color: #cccccc; font-size: 28px; padding-top: 8px; }}
        .action-item {{ display: flex; align-items: center; gap: 12px; }}
        .action-item svg {{ width: 36px; height: 36px; stroke: #e0e0e0; stroke-width: 2; fill: none; }}
        .heart svg {{ fill: #ff3040; stroke: #ff3040; }}
    </style>
    </head>
    <body>
        <div class="threads-card" id="card">
            <div class="header">
                <img class="avatar" src="{avatar_url}" />
                <div class="user-meta">
                    <span class="username">{username}</span>
                    <svg class="verified" viewBox="0 0 40 40"><path d="M19.998 3.094 14.638 0l-2.972 5.15H5.432v6.354L0 14.64 3.094 20 0 25.359l5.432 3.137v5.905h5.975L14.638 40l5.36-3.094L25.358 40l3.232-5.6h6.162v-6.01L40 25.359 36.905 20 40 14.641l-5.248-3.03v-6.46h-6.419L25.358 0l-5.36 3.094Zm7.415 11.225 2.254 2.287-11.43 11.5-6.835-6.93 2.244-2.258 4.587 4.581 9.18-9.18Z"/></svg>
                    <span class="time">{time_ago}</span>
                </div>
            </div>
            <div class="content">{paragraphs}</div>
            <div class="actions">
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


async def generate_tts(text: str, output_path: Path, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text=text, voice=CONFIG["voice"], rate=CONFIG["voice_rate"])
            await communicate.save(str(output_path))
            return
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.8 * (attempt + 1))
            else:
                raise


def trim_audio_silence(file_path: Path, silence_thresh: int = -40, padding_ms: int = 60):
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


async def prepare_media_assets(story_data: dict, temp_dir: Path):
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

        for card in story_data.get("cards", []):
            card_id = card["card_id"]
            accumulated_lines = []

            for idx, line in enumerate(card["lines"]):
                accumulated_lines.append(line)
                step_name = f"c{card_id}_s{idx + 1}"

                audio_path = temp_dir / f"{step_name}.mp3"
                await generate_tts(line, audio_path)
                await asyncio.sleep(0.2)
                trim_audio_silence(audio_path)

                html_content = build_threads_html(
                    CONFIG["username"],
                    CONFIG["avatar_url"],
                    card["time_ago"],
                    accumulated_lines,
                    card["likes"],
                    card["replies"]
                )
                await page.set_content(html_content, wait_until="networkidle")
                img_path = temp_dir / f"{step_name}.png"
                await page.locator("#card").screenshot(path=str(img_path), omit_background=True)

                segments.append({"image": img_path, "audio": audio_path})

        await browser.close()
    return segments, wm_path


def build_final_video(segments: list, wm_path: Path, output_file: str = "output_short.mp4"):
    bg_path = Path("assets/background.mp4")
    if not bg_path.exists():
        raise FileNotFoundError("Không tìm thấy file 'assets/background.mp4'. Hãy bỏ video nền vào thư mục assets/")

    pop_path = Path("assets/pop.mp3")
    final_sfx_path = Path("assets/final_sfx.mp3")

    visual_clips = []
    audio_clips = []
    current_time = 0.0

    for seg in segments:
        voice_clip = AudioFileClip(str(seg["audio"]))
        step_duration = voice_clip.duration

        voice_clip = clip_set_start(voice_clip, current_time)
        audio_clips.append(voice_clip)

        if pop_path.exists():
            try:
                pop_clip = clip_set_start(AudioFileClip(str(pop_path)), current_time)
                audio_clips.append(pop_clip)
            except Exception as e:
                print(f"[!] Bỏ qua pop sfx do lỗi: {e}")

        img_clip = ImageClip(str(seg["image"]))
        img_clip = clip_set_start(img_clip, current_time)
        img_clip = clip_set_duration(img_clip, step_duration)
        img_clip = clip_set_position(img_clip, ("center", "center"))
        visual_clips.append(img_clip)

        current_time += step_duration

    if final_sfx_path.exists() and visual_clips:
        try:
            sfx_clip = AudioFileClip(str(final_sfx_path))
            sfx_clip = clip_set_start(sfx_clip, max(0, current_time - 0.15))
            audio_clips.append(sfx_clip)
            extra_tail = min(sfx_clip.duration, 1.5)
            visual_clips[-1] = clip_set_duration(visual_clips[-1], visual_clips[-1].duration + extra_tail)
            current_time += extra_tail
        except Exception as e:
            print(f"[!] Bỏ qua final sfx do lỗi: {e}")

    total_duration = current_time
    bg_video = VideoFileClip(str(bg_path))
    if bg_video.duration > total_duration + 2:
        start_pt = random.uniform(0, bg_video.duration - total_duration - 1)
        bg_video = clip_subclip(bg_video, start_pt, start_pt + total_duration)
    else:
        bg_video = clip_subclip(bg_video, 0, min(bg_video.duration, total_duration))

    bg_video = crop_to_9_16(bg_video, CONFIG["video_width"], CONFIG["video_height"])

    wm_clip = ImageClip(str(wm_path))
    wm_clip = clip_set_start(wm_clip, 0)
    wm_clip = clip_set_duration(wm_clip, total_duration)
    wm_clip = clip_set_position(wm_clip, ("center", 160))

    final_video = CompositeVideoClip([bg_video, wm_clip] + visual_clips)
    final_audio = CompositeAudioClip(audio_clips)
    final_video = clip_with_audio(final_video, final_audio)

    final_video.write_videofile(
        output_file,
        fps=CONFIG["fps"],
        codec="libx264",
        audio_codec="aac",
        threads=4
    )
    print(f"[✓] Đã xuất file: {output_file}")
    bg_video.close()
    final_video.close()


async def render_story_video(story_data: dict, output_file: str = "output_short.mp4", temp_dir: Path = None) -> str:
    cleanup_temp = False
    if temp_dir is None:
        temp_dir = Path(f"temp_build_{random.randint(1000, 9999)}")
        cleanup_temp = True

    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        segments, wm_path = await prepare_media_assets(story_data, temp_dir)
        build_final_video(segments, wm_path, output_file=output_file)
        return output_file
    finally:
        if cleanup_temp and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    parser = argparse.ArgumentParser(description="Threads Shorts Video Builder")
    parser.add_argument("--count", type=int, default=1, help="Số lượng video cần tạo (mặc định: 1)")
    parser.add_argument("--urls", nargs="+", default=TARGET_THREADS_URLS, help="Danh sách URL Threads cần quét")
    parser.add_argument("--watermark", default=CONFIG["channel_watermark"], help="Watermark kênh")
    parser.add_argument("--voice", default=CONFIG["voice"], help="Giọng đọc edge-tts")
    args = parser.parse_args()

    CONFIG["channel_watermark"] = args.watermark
    CONFIG["voice"] = args.voice

    total_videos = args.count
    for i in range(1, total_videos + 1):
        print(f"\n========================================")
        print(f"🎬 ĐANG XỬ LÝ VIDEO THỨ {i} / {total_videos}")
        print(f"========================================")

        story_data = await get_automated_story(args.urls, api_key=os.environ.get("GEMINI_API_KEY"))
        out_name = f"output_short_batch_{i}.mp4" if total_videos > 1 else "output_short.mp4"
        await render_story_video(story_data, output_file=out_name)

    print(f"\n🎉 HOÀN TẤT! Đã xuất xong {total_videos} video.")


if __name__ == "__main__":
    asyncio.run(main())
