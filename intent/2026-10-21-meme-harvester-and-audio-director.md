---
status: verified
---
# Meme Harvester, Multi-Voice Audio Director & Viral Meme Reactions Upgrade

**Problem** — Video Shorts tạo từ Threads hiện tại chỉ có 1 giọng đọc đơn điệu (`CONFIG["voice"]`), chưa có nhạc nền BGM vui nhộn xuyên suốt, chỉ có tiếng pop cơ bản và thiếu các âm thanh meme bắt tai (SFX) giữa các câu thoại cũng như clip video meme reaction ở đoạn chốt hạ vốn là đặc trưng triệu view của các kênh như Động Threads.

**Outcome** —
1. Xây dựng module `meme_harvester.py` tự động săn tài nguyên từ YouTube qua `yt-dlp` (`ytsearch5:`):
   - `assets/bgm/`: 2-3 bài nhạc nền beat vui nhộn TikTok (30-120 giây).
   - `assets/sfx/`: 5 âm thanh meme kinh điển (`huh.mp3`, `cai_gi_do.mp3`, `laugh.mp3`, `vine_boom.mp3`, `wow.mp3` < 8 giây).
   - `assets/video_memes/`: 2-3 video meme reaction Việt Nam ("Trời đất ơi...", "Ảo thật đấy...", "Sợ quá sợ quá..." 2-5 giây cắt đoạn cao trào).
2. Nâng cấp `threads_scraper_ai.py` và `threads_scraper.py`:
   - Schema Pydantic `ThreadCard` sử dụng `lines: List[StoryLine]` với:
     + `text`: chuỗi văn bản tiếng Việt có dấu chuẩn UTF-8.
     + `voice`: `"vi-VN-HoaiMyNeural"` (nữ) hoặc `"vi-VN-NamMinhNeural"` (nam).
     + `sfx_after`: `"none"`, `"huh"`, `"cai_gi_do"`, `"laugh"`, `"vine_boom"`, `"wow"`.
   - `StorySelection` hỗ trợ `use_video_meme_outro: bool = True`.
   - Đảm bảo export đồng bộ giữa `threads_scraper.py` và `threads_scraper_ai.py`.
   - Cập nhật kho 5 truyện mẫu `SAMPLE_STORIES` với cấu trúc `StoryLine` sinh động đa giọng và SFX.
3. Nâng cấp bộ dựng video (`threads_video_builder.py` & `auto_threads_video.py`):
   - Lồng BGM xuyên suốt video với âm lượng 12% (`with_volume_scaled(0.12)` / `volumex(0.12)`).
   - Phát âm thanh TTS theo đúng giọng nam/nữ chỉ định, chèn Mid-SFX ngay khi dứt câu và nghỉ 0.4s-0.6s.
   - Nối video meme reaction cuối bài (resize rộng 750px đặt ở nửa dưới màn hình).
   - Duy trì tương thích MoviePy v1 / v2.
4. Chạy harvest tài nguyên và xuất 1 video thực tế hoàn chỉnh nghiệm thu.

**Constraints** —
- MoviePy v1 và v2 tương thích hoàn toàn.
- Không phá vỡ các test case hiện có; bổ sung test case mới cho `meme_harvester`, `StoryLine`, BGM, Mid-SFX và Video Meme outro.
- Giữ vững cơ chế chống giật khung Threads (opacity-based reveal).

## Verification & Proof
- **Unit Tests**: 35/35 passed (`.venv/bin/python -m unittest discover`).
- **Harvested Real Assets**:
  - `assets/bgm/`: `funny_quirky.mp3` (75.02s), `sneaky_snitch.mp3` (80.04s), `monkeys_spinning.mp3` (70.03s). All within 30-120s.
  - `assets/sfx/`: `huh.mp3` (0.46s), `cai_gi_do.mp3` (1.25s), `laugh.mp3` (3.29s), `vine_boom.mp3` (2.93s), `wow.mp3` (1.78s). All < 8s, dead air / leading silence trimmed so sounds play immediately when voice ends.
  - `assets/video_memes/`: `ao_that_day.mp4` (3.00s), `troi_dat_oi.mp4` (3.42s), `so_qua_co.mp4` (4.71s). All within 2-5s.
- **Render Output**:
  - `output_short.mp4`: 1080x1920 30fps, duration 33.37s, file size ~17.4MB.
  - Verified layout: Threads card rendered cleanly with no jitter; Mid-SFX subclipped with 0.5s pause; BGM balanced at 12%; Video Meme Outro positioned dynamically strictly below Card 2 bottom (y=1310 to y=1732), leaving zero card overlap and full punchline/action visibility.


