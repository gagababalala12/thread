---
status: planned
---
# Kế hoạch triển khai: Module Auto Publisher & Web Dashboard

## Files to Modify & Create
1. `.gitignore`: Thêm `publish_status.json`, `browser_profile/`, `published_videos/`, `temp_current_build/`.
2. `threads_scraper.py`: Định nghĩa và xuất `TARGET_THREADS_URLS`.
3. `threads_scraper_ai.py`: Xuất `TARGET_THREADS_URLS` trong `__all__` để khớp với `from threads_scraper_ai import get_automated_story, TARGET_THREADS_URLS`.
4. `threads_video_builder.py`:
   - Nâng cấp `prepare_media_assets(story_data_or_temp_dir=None, temp_dir=None)` hỗ trợ nhận 1 đối số `temp_dir` hoặc 2 đối số `(story_data, temp_dir)`.
   - Lấy `story_data` từ `auto_threads_video.STORY_DATA` hoặc `threads_video_builder.STORY_DATA` hoặc fallback sample.
   - Bổ sung `Path(output_file).parent.mkdir(parents=True, exist_ok=True)` trong `build_final_video` để hỗ trợ xuất video vào thư mục con (`published_videos/`).
5. `auto_threads_video.py`:
   - Xuất biến `STORY_DATA` và đồng bộ cùng `threads_video_builder`.
6. `auto_publisher.py`:
   - Tích hợp trọn vẹn toàn bộ mã nguồn người dùng cung cấp.
   - Thêm cờ `--once` (chạy 1 chu kỳ rồi kết thúc) song song với `--login` và vòng lặp mặc định 4 tiếng.
   - Dùng `allow_reuse_address = True` cho Dashboard HTTP Server.
7. `test_auto_publisher.py`:
   - Kiểm thử các hàm: `load_status_list`, `save_status_record`.
   - Kiểm thử Web Dashboard HTTP server handler (GET request trả về mã 200, HTML chứa dữ liệu status và đếm ngược).
   - Kiểm thử CLI flags (`--login`, `--once`, `INTERVAL_HOURS`).
8. `README.md`:
   - Hướng dẫn vận hành tính năng đăng video tự động, lệnh `--login`, lệnh chạy chu kỳ 4 tiếng và xem Web Dashboard tại `http://localhost:8080`.

## Risks & Mitigations
- **Risk 1: Chromium crash khi chạy dưới quyền root trong Docker/Linux container.**
  - *Mitigation*: Bổ sung `args=["--no-sandbox", "--disable-setuid-sandbox"]` khi khởi tạo `persistent_context`.
- **Risk 2: Lỗi import `TARGET_THREADS_URLS` từ `threads_scraper_ai`.**
  - *Mitigation*: Đồng bộ định nghĩa và xuất ở cả `threads_scraper.py` và `threads_scraper_ai.py`.
- **Risk 3: `prepare_media_assets(temp_dir)` thiếu tham số `story_data`.**
  - *Mitigation*: Hỗ trợ flexible arguments tự động trích xuất `story_data` từ `auto_threads_video.STORY_DATA`.
- **Risk 4: Xung đột cổng 8080 khi khởi động Dashboard.**
  - *Mitigation*: Bật `allow_reuse_address = True` và cho phép cấu hình port qua biến môi trường `DASHBOARD_PORT`.

## Proof of Completion
- Chạy toàn bộ test suite `.venv/bin/python -m unittest discover` đạt 100% PASS.
- Khởi động thử Dashboard HTTP Server và thực hiện `curl -I http://localhost:8080` trả về HTTP 200 OK kèm mã nguồn HTML bảng theo dõi.
- Kiểm tra tính tương thích `python auto_publisher.py --help` hoặc test `--dry-run` không gây lỗi cú pháp.
