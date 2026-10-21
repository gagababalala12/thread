"""
meme_harvester.py - Tự động săn kho nhạc nền (BGM), âm thanh SFX và Video Meme từ YouTube qua yt-dlp.
"""

import os
import shutil
import subprocess
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
import yt_dlp

BGM_QUERIES = [
    {
        "name": "funny_quirky.mp3",
        "query": "funny quirky background music no copyright",
        "fallback_url": "https://www.youtube.com/watch?v=8MgA3SUwFHc",
        "trim_range": (0.0, 75.0),
    },
    {
        "name": "sneaky_snitch.mp3",
        "query": "sneaky snitch kevin macleod",
        "fallback_url": "https://www.youtube.com/watch?v=Cm0qaXi9THA",
        "trim_range": (0.0, 80.0),
    },
    {
        "name": "monkeys_spinning.mp3",
        "query": "monkeys spinning monkeys kevin macleod",
        "fallback_url": "https://www.youtube.com/watch?v=uou5Vp44e24",
        "trim_range": (0.0, 70.0),
    },
]

SFX_QUERIES = {
    "huh.mp3": {
        "query": "huh meme sound effect short",
        "fallback_url": "https://www.youtube.com/watch?v=6AaKkGrTqjE",
        "max_duration": 7.5,
    },
    "cai_gi_do.mp3": {
        "query": "cái gì dợ sound effect meme",
        "fallback_url": "https://www.youtube.com/watch?v=gtTjH695UHQ",
        "max_duration": 7.5,
    },
    "laugh.mp3": {
        "query": "short funny giggle laugh sound effect",
        "fallback_url": "https://www.youtube.com/watch?v=pbTfkku2yxA",
        "max_duration": 7.5,
    },
    "vine_boom.mp3": {
        "query": "vine boom sound effect",
        "fallback_url": "https://www.youtube.com/watch?v=Oc7Cin_87H4",
        "max_duration": 7.5,
    },
    "wow.mp3": {
        "query": "anime wow sound effect",
        "fallback_url": "https://www.youtube.com/watch?v=BnTdfA5aTpY",
        "max_duration": 7.5,
    },
}

VIDEO_MEME_QUERIES = [
    {
        "name": "troi_dat_oi.mp4",
        "query": "trời đất ơi tự nhiên cái tôi tỉnh lại liền meme",
        "fallback_url": "https://www.youtube.com/watch?v=HX3vO5_aTZo",
        "climax_start": 0.0,
        "climax_duration": 3.4,
    },
    {
        "name": "ao_that_day.mp4",
        "query": "ảo thật đấy meme ngắn",
        "fallback_url": "https://www.youtube.com/watch?v=D5CGS7o-eV4",
        "climax_start": 0.0,
        "climax_duration": 3.0,
    },
    {
        "name": "so_qua_co.mp4",
        "query": "sợ quá sợ quá phải ban nó thôi meme",
        "fallback_url": "https://www.youtube.com/watch?v=W_THTokiLoU",
        "climax_start": 0.0,
        "climax_duration": 3.8,
    },
]


def get_media_duration(file_path: Path) -> float:
    """Lấy thời lượng chính xác của file media bằng ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(file_path)
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(out)
        return float(data.get("format", {}).get("duration", 0.0))
    except Exception:
        return 0.0


def trim_media_file(
    input_file: Path,
    output_file: Path,
    start: float,
    duration: float,
    is_video: bool = False
):
    """Cắt file audio hoặc video bằng ffmpeg với độ trễ tối thiểu và tránh negative timestamps."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_target = output_file.parent / f"_trim_tmp_{output_file.name}"
    if temp_target.exists():
        temp_target.unlink()

    if is_video:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(input_file),
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            str(temp_target)
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(input_file),
            "-t", str(duration),
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(temp_target)
        ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if output_file.exists():
        output_file.unlink()
    shutil.move(str(temp_target), str(output_file))


def trim_audio_silence_sfx(file_path: Path, max_duration: float = 7.5, silence_thresh: int = -40, padding_ms: int = 50):
    """Cắt bỏ hoàn toàn khoảng lặng ở đầu và cuối file SFX để âm thanh phát tức thì khi dứt câu thoại."""
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent
        audio = AudioSegment.from_file(str(file_path))
        nonsilent_ranges = detect_nonsilent(audio, min_silence_len=80, silence_thresh=silence_thresh)
        if not nonsilent_ranges:
            return
        start_ms = max(0, nonsilent_ranges[0][0] - padding_ms)
        end_ms = min(len(audio), nonsilent_ranges[-1][1] + padding_ms)
        if (end_ms - start_ms) > max_duration * 1000:
            end_ms = start_ms + int(max_duration * 1000)
        trimmed = audio[start_ms:end_ms]
        out_f = trimmed.export(str(file_path), format="mp3")
        out_f.close()
    except Exception as e:
        print(f"[!] Không thể cắt khoảng lặng file SFX {file_path.name}: {e}")


def _search_youtube_url(query: str, target_min_dur: float = 0.0, target_max_dur: float = 9999.0) -> Optional[str]:
    """Tìm URL video YouTube phù hợp nhất từ truy vấn ytsearch5:."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "extract_flat": "in_playlist",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = res.get("entries", []) or []
            # Ưu tiên các kết quả nằm trong khoảng thời lượng mục tiêu
            for entry in entries:
                if not entry:
                    continue
                dur = entry.get("duration")
                if dur is not None and target_min_dur <= dur <= target_max_dur:
                    return entry.get("url") or entry.get("webpage_url")
            # Nếu không tìm thấy đúng khoảng, chọn kết quả đầu tiên hợp lệ
            for entry in entries:
                if entry and (entry.get("url") or entry.get("webpage_url")):
                    return entry.get("url") or entry.get("webpage_url")
    except Exception as e:
        print(f"[!] Lỗi tìm kiếm yt-dlp cho '{query}': {e}")
    return None


def harvest_sfx(assets_dir: Path = Path("assets"), force: bool = False) -> Dict[str, Path]:
    """
    Tự động tìm và tải bộ 5 âm thanh meme kinh điển (< 8s) vào assets/sfx/:
    - huh.mp3
    - cai_gi_do.mp3
    - laugh.mp3
    - vine_boom.mp3
    - wow.mp3
    """
    sfx_dir = assets_dir / "sfx"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for filename, meta in SFX_QUERIES.items():
        dest = sfx_dir / filename
        if dest.exists() and dest.stat().st_size > 1000 and not force:
            # Tỉa khoảng lặng đầu/đuôi file nếu còn sót
            trim_audio_silence_sfx(dest, max_duration=meta.get("max_duration", 7.5))
            dur = get_media_duration(dest)
            if dur < 8.0:
                print(f"[✓] SFX đã có sẵn và hợp lệ: {dest} ({dur:.2f}s)")
                results[filename] = dest
                continue

        print(f"[+] Đang săn SFX '{filename}' (Từ khóa: '{meta['query']}')...")
        found_url = _search_youtube_url(meta["query"], target_min_dur=0.5, target_max_dur=10.0)
        target_url = found_url or meta.get("fallback_url")

        temp_template = str(sfx_dir / f"tmp_sfx_{Path(filename).stem}.%(ext)s")
        # Dọn sạch các file tạm cũ nếu có
        for old in sfx_dir.glob(f"tmp_sfx_{Path(filename).stem}*"):
            try:
                old.unlink()
            except Exception:
                pass

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_template,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }

        downloaded_ok = False
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target_url])
            candidates = list(sfx_dir.glob(f"tmp_sfx_{Path(filename).stem}*.mp3"))
            if candidates:
                downloaded_file = candidates[0]
                dur = get_media_duration(downloaded_file)
                max_d = meta.get("max_duration", 7.5)
                if dur > max_d:
                    print(f"[+] Cắt bớt thời lượng SFX {filename} từ {dur:.2f}s xuống {max_d}s...")
                    trim_media_file(downloaded_file, dest, start=0.0, duration=max_d, is_video=False)
                    downloaded_file.unlink()
                else:
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(downloaded_file), str(dest))
                trim_audio_silence_sfx(dest, max_duration=max_d)
                downloaded_ok = True
                print(f"[✓] Đã lưu SFX thành công: {dest} ({get_media_duration(dest):.2f}s)")
        except Exception as e:
            print(f"[!] Lỗi khi tải SFX {filename}: {e}")

        # Thử fallback URL nếu tìm kiếm thất bại
        if not downloaded_ok and target_url != meta.get("fallback_url") and meta.get("fallback_url"):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([meta["fallback_url"]])
                candidates = list(sfx_dir.glob(f"tmp_sfx_{Path(filename).stem}*.mp3"))
                if candidates:
                    downloaded_file = candidates[0]
                    dur = get_media_duration(downloaded_file)
                    max_d = meta.get("max_duration", 7.5)
                    if dur > max_d:
                        trim_media_file(downloaded_file, dest, start=0.0, duration=max_d, is_video=False)
                        downloaded_file.unlink()
                    else:
                        if dest.exists():
                            dest.unlink()
                        shutil.move(str(downloaded_file), str(dest))
                    trim_audio_silence_sfx(dest, max_duration=max_d)
                    downloaded_ok = True
                    print(f"[✓] Đã lưu SFX từ fallback: {dest} ({get_media_duration(dest):.2f}s)")
            except Exception as e:
                print(f"[!] Lỗi fallback SFX {filename}: {e}")

        if dest.exists():
            results[filename] = dest

    return results


def harvest_bgm(assets_dir: Path = Path("assets"), force: bool = False) -> List[Path]:
    """
    Tải 2-3 bài nhạc nền beat vui nhộn TikTok (30-120 giây) vào assets/bgm/.
    """
    bgm_dir = assets_dir / "bgm"
    bgm_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for item in BGM_QUERIES:
        filename = item["name"]
        dest = bgm_dir / filename
        if dest.exists() and dest.stat().st_size > 5000 and not force:
            dur = get_media_duration(dest)
            if 30.0 <= dur <= 120.0:
                print(f"[✓] BGM đã có sẵn và hợp lệ: {dest} ({dur:.2f}s)")
                results.append(dest)
                continue

        print(f"[+] Đang săn BGM '{filename}' (Từ khóa: '{item['query']}')...")
        found_url = _search_youtube_url(item["query"], target_min_dur=30.0, target_max_dur=180.0)
        target_url = found_url or item.get("fallback_url")

        temp_template = str(bgm_dir / f"tmp_bgm_{Path(filename).stem}.%(ext)s")
        for old in bgm_dir.glob(f"tmp_bgm_{Path(filename).stem}*"):
            try:
                old.unlink()
            except Exception:
                pass

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_template,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target_url])
            candidates = list(bgm_dir.glob(f"tmp_bgm_{Path(filename).stem}*.mp3"))
            if candidates:
                downloaded_file = candidates[0]
                dur = get_media_duration(downloaded_file)
                # Kiểm tra và cắt để đảm bảo thời lượng 30 - 120 giây
                if dur < 30.0 or dur > 120.0:
                    start_s, target_dur = item.get("trim_range", (0.0, 60.0))
                    if dur < target_dur:
                        target_dur = max(30.0, dur)
                    print(f"[+] Cắt chuẩn hóa BGM {filename} về thời lượng {target_dur}s...")
                    trim_media_file(downloaded_file, dest, start=start_s, duration=target_dur, is_video=False)
                    downloaded_file.unlink()
                else:
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(downloaded_file), str(dest))
                print(f"[✓] Đã lưu BGM thành công: {dest} ({get_media_duration(dest):.2f}s)")
                results.append(dest)
        except Exception as e:
            print(f"[!] Lỗi khi tải BGM {filename}: {e}")

    return results


def harvest_video_memes(assets_dir: Path = Path("assets"), force: bool = False) -> List[Path]:
    """
    Tự động tải 2-3 video meme reaction ngắn của Việt Nam (2-5 giây, cắt lấy đoạn cao trào) vào assets/video_memes/.
    """
    vm_dir = assets_dir / "video_memes"
    vm_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for item in VIDEO_MEME_QUERIES:
        filename = item["name"]
        dest = vm_dir / filename
        if dest.exists() and dest.stat().st_size > 10000 and not force:
            dur = get_media_duration(dest)
            if 1.9 <= dur <= 5.1:
                print(f"[✓] Video Meme đã có sẵn và hợp lệ: {dest} ({dur:.2f}s)")
                results.append(dest)
                continue

        print(f"[+] Đang săn Video Meme '{filename}' (Từ khóa: '{item['query']}')...")
        found_url = _search_youtube_url(item["query"], target_min_dur=1.0, target_max_dur=30.0)
        target_url = found_url or item.get("fallback_url")

        temp_template = str(vm_dir / f"tmp_vm_{Path(filename).stem}.%(ext)s")
        for old in vm_dir.glob(f"tmp_vm_{Path(filename).stem}*"):
            try:
                old.unlink()
            except Exception:
                pass

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": temp_template,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "merge_output_format": "mp4",
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([target_url])
            candidates = list(vm_dir.glob(f"tmp_vm_{Path(filename).stem}*.mp4"))
            if candidates:
                downloaded_file = candidates[0]
                dur = get_media_duration(downloaded_file)
                c_start = item.get("climax_start", 0.0)
                c_dur = item.get("climax_duration", 3.0)

                # Đảm bảo thời lượng video meme nằm trong khoảng 2-5 giây
                c_dur = max(2.0, min(5.0, c_dur))
                if dur <= 5.0 and dur >= 2.0 and c_start == 0.0:
                    c_dur = dur

                print(f"[+] Cắt đúng đoạn cao trào Video Meme ({c_start}s -> {c_start + c_dur}s)...")
                trim_media_file(downloaded_file, dest, start=c_start, duration=c_dur, is_video=True)
                downloaded_file.unlink()
                print(f"[✓] Đã lưu Video Meme thành công: {dest} ({get_media_duration(dest):.2f}s)")
                results.append(dest)
        except Exception as e:
            print(f"[!] Lỗi khi tải Video Meme {filename}: {e}")

    return results


def harvest_all(assets_dir: Path = Path("assets"), force: bool = False) -> dict:
    """Săn toàn bộ kho BGM, SFX và Video Meme từ YouTube."""
    assets_dir = Path(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 50)
    print("🚀 BẮT ĐẦU SĂN KHO TÀI NGUYÊN TỪ YOUTUBE (BGM, SFX, VIDEO MEME)")
    print("=" * 50)

    bgm_files = harvest_bgm(assets_dir=assets_dir, force=force)
    sfx_files = harvest_sfx(assets_dir=assets_dir, force=force)
    vm_files = harvest_video_memes(assets_dir=assets_dir, force=force)

    print("\n" + "=" * 50)
    print("🎉 HOÀN TẤT THU THẬP TÀI NGUYÊN:")
    print(f"- BGM ({len(bgm_files)} bài): {[f.name for f in bgm_files]}")
    print(f"- SFX ({len(sfx_files)} hiệu ứng): {list(sfx_files.keys())}")
    print(f"- Video Meme ({len(vm_files)} clip): {[f.name for f in vm_files]}")
    print("=" * 50 + "\n")

    return {
        "bgm": bgm_files,
        "sfx": sfx_files,
        "video_memes": vm_files,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meme Harvester - Tự động tải BGM, SFX và Video Meme từ YouTube")
    parser.add_argument("--assets-dir", default="assets", help="Thư mục chứa tài nguyên assets")
    parser.add_argument("--force", action="store_true", help="Bắt buộc tải lại dù file đã tồn tại")
    args = parser.parse_args()

    harvest_all(assets_dir=Path(args.assets_dir), force=args.force)
