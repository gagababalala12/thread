---
status: verified
---
# Tự động hóa đăng video đa nền tảng (TikTok, YouTube Shorts, Facebook Reels) & Web Dashboard

**Problem**
Sau khi pipeline tạo video Shorts hoàn chỉnh với kịch bản Threads, đa giọng đọc và kho meme được xây dựng thành công, việc đăng tải video lên các mạng xã hội (TikTok Studio, YouTube Studio, Facebook Reels) vẫn phải thực hiện thủ công, tốn thời gian và không thể duy trì lịch đăng đều đặn mỗi 4 tiếng. Ngoài ra, người dùng thiếu một giao diện trực quan để theo dõi trạng thái đăng, mã video và lịch đăng kế tiếp.

**Outcome**
1. Module `auto_publisher.py` tự động hóa toàn bộ quy trình:
   - Quản lý trạng thái xuất bản dạng cơ sở dữ liệu JSON (`publish_status.json`).
   - Sử dụng Playwright với persistent context (`browser_profile/`) để lưu giữ phiên đăng nhập của người dùng.
   - Hỗ trợ chế độ `--login` để người dùng đăng nhập 1 lần ban đầu vào TikTok, YouTube Studio và Facebook.
   - Tự động đăng video lên 3 nền tảng: YouTube Shorts, TikTok Studio, Facebook Reels kèm caption/hashtags phù hợp.
   - Vòng lặp tự động sản xuất và đăng video mỗi chu kỳ 4 tiếng (`INTERVAL_HOURS = 4`), đồng thời hỗ trợ flag `--once` để chạy kiểm thử 1 chu kỳ duy nhất.
2. Web Dashboard trực tuyến (Port 8080):
   - Chạy trên background thread `http.server` phục vụ giao diện HTML/CSS phong cách Dark mode hiện đại.
   - Hiển thị danh sách video đã dựng, trạng thái đăng từng nền tảng (YouTube, Facebook, TikTok), thời gian tạo, file video và đếm ngược thời gian chạy tiếp theo (`NEXT_RUN_TIME`).
   - Tự động làm mới trang (`<meta http-equiv="refresh" content="15">`).
3. Tương thích 100% với các module hiện có:
   - `threads_scraper_ai.py` và `threads_scraper.py` xuất `TARGET_THREADS_URLS`.
   - `threads_video_builder.py` hỗ trợ linh hoạt chữ ký `prepare_media_assets(temp_dir)` và `prepare_media_assets(story_data, temp_dir)` đồng bộ với `auto_threads_video.STORY_DATA`.
   - `.gitignore` bảo vệ thông tin cá nhân: loại trừ `publish_status.json`, `browser_profile/`, `published_videos/`, `temp_current_build/`.
4. Toàn bộ test suite tự động đạt 100% PASS (bao gồm các test mới cho `auto_publisher.py`).

**Constraints**
- Giữ nguyên toàn bộ logic đăng video và giao diện Dashboard mà người dùng đã thiết kế.
- Không sử dụng thư viện bên ngoài mới ngoài những gì đã có (`playwright`, `http.server`, `threading`, `json`, `asyncio`, `moviepy`, `edge-tts`).
- Đảm bảo an toàn bảo mật tuyệt đối cho thư mục cookie/session `browser_profile/`.

**Out of scope**
- Tự động giải CAPTCHA phức tạp (người dùng xác thực thủ công trong bước `--login` khi cần).
- Đăng tải lên các nền tảng khác ngoài TikTok, YouTube Shorts và Facebook Reels.

**Open questions**
- Không có (yêu cầu và mã nguồn đã được định nghĩa đầy đủ).
