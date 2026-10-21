# Kế hoạch Kỹ thuật: Threads Shorts Video Generator

Hợp đồng kỹ thuật triển khai cho intent: [2026-10-21-threads-video-generator.md](file:///root/.gemini/antigravity/worktrees/jolly-bardeen/threads_story_scraper_gemini/intent/2026-10-21-threads-video-generator.md)

---

## 1. Files sẽ chạm (theo thứ tự)

1. `requirements.txt`: Đã bổ sung `edge-tts>=7.0.0`, `pydub>=0.25.1`, `moviepy>=2.0.0`.
2. `threads_scraper_ai.py`: Module alias / re-export cho `threads_scraper.py` để tương thích các script gọi `from threads_scraper_ai import get_automated_story`.
3. `assets/`: Thư mục chứa tài nguyên media (`background.mp4`, `pop.mp3`, `final_sfx.mp3`). Tạo background video placeholder nếu chưa có video thật.
4. `threads_video_builder.py`: Module render video hoàn chỉnh:
   - Cấu hình video: độ phân giải 1080x1920 (9:16), 30 fps, bitrate cao.
   - Hàm HTML generator: `build_threads_html`, `build_watermark_html`.
   - Helper MoviePy tương thích cả v1 và v2 (`clip_subclip`, `clip_set_start`, `clip_set_duration`, `clip_set_position`, `clip_with_audio`, `crop_to_9_16`).
   - Xử lý âm thanh TTS & Cắt khoảng lặng: `generate_tts`, `trim_audio_silence`.
   - Xử lý chụp ảnh từng phân đoạn: `prepare_media_assets` bằng Playwright.
   - Ghép dựng video: `build_final_video`.
   - Hàm điều phối chạy batch hoặc đơn lẻ: `main()` / `render_story_video()`.
5. `test_threads_video_builder.py`: Kiểm thử tự động kiểm tra sinh HTML card, sinh TTS, cắt khoảng lặng và MoviePy helper functions.
6. `README.md`: Bổ sung hướng dẫn tạo video Shorts.

---

## 2. Risks — Có thể gãy gì & Cách kiểm bắt được

| Risk | Nguy cơ gãy | Cách xử lý & Kiểm soát |
|---|---|---|
| **R1: Thiếu video nền `assets/background.mp4`** | `FileNotFoundError` khi chạy | Tự động tạo thư mục `assets/` và hỗ trợ fallback sinh video nền placeholder 1080x1920 qua ffmpeg/MoviePy nếu chưa có file thật. |
| **R2: MoviePy v1 vs v2 xung đột cú pháp** | `set_duration` vs `with_duration`, `subclip` vs `subclipped` | Viết wrapper functions tương thích cả 2 phiên bản dựa trên cờ `MOVIEPY_V2`. |
| **R3: Playwright Chromium thiếu shared libraries trên Linux** | `TargetClosedError` do thiếu `libnspr4`, `libnss3` | Đảm bảo chạy `playwright install-deps chromium` trong quy trình setup. |
| **R4: Lỗi mạng Edge TTS hoặc khoảng lặng quá dài** | Mất tiếng, audio bị ngắt quãng | Bọc `try/except` trong `trim_audio_silence` và `generate_tts` với retry cơ bản. |

---

## 3. Proof — Định nghĩa xong (Definition of Done)

1. **Syntax Check**:
   ```bash
   .venv/bin/python -m py_compile threads_video_builder.py threads_scraper_ai.py test_threads_video_builder.py
   ```
   *Kỳ vọng*: Exit code 0, không có lỗi cú pháp.

2. **Automated Unit & Integration Tests**:
   ```bash
   .venv/bin/python -m unittest test_threads_video_builder.py
   ```
   *Kỳ vọng*: Tất cả test case (HTML builder, TTS generation, silence trim, MoviePy clip wrappers) đều PASS.

3. **End-to-End Render Check**:
   Chạy thử tạo 1 video ngắn từ mock story hoặc single test run:
   *Kỳ vọng*: Xuất ra file video MP4 dọc 1080x1920 hợp lệ.
