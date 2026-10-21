---
status: verified
---
# Threads Story Scraper & Gemini AI Story Curation for Shorts

**Problem** — Cần nguồn nội dung chuyện hài/tình huống viral từ Threads để làm video YouTube Shorts/TikTok dạng 2-Card, nhưng việc lướt tìm thủ công tốn thời gian, khó lọc câu chuyện có cú twist bất ngờ và dễ bị trùng lặp chủ đề đã làm.

**Outcome** —
- Module thư viện độc lập kèm CLI tiện dụng (`threads_scraper.py`), dễ dàng tái sử dụng hoặc tích hợp vào các pipeline khác.
- Tự động cào danh sách bài viết từ Threads ở chế độ ẩn danh (Anonymous guest) bằng Playwright, trang bị cờ chống bot và tự động đóng/bỏ qua login popup/backdrop.
- Dùng Gemini AI (`gemini-3.8-flash`) chấm điểm hài hước (1-10) và format chuẩn 2 Card (Card 1 mở bài/tò mò, Card 2 chốt hạ/twist) theo schema Pydantic.
- Tự động ghi nhớ và loại trừ 50 mẩu chuyện gần nhất qua `story_history.json`.
- Xuất dữ liệu chuẩn JSON (danh sách `cards` gồm `card_id`, `time_ago`, `likes`, `replies`, `lines` và `humor_score`).
- Tiêu chí thành công (Proof): Chạy lệnh CLI hoặc hàm API sinh kịch bản thành công và hợp lệ Pydantic trong < 30 giây (khi có mạng).

**Constraints** —
- Ngôn ngữ & Thư viện: Python 3.10+, `google-genai` SDK (>=2.30.1), `playwright`, `pydantic`.
- Model: Mặc định `gemini-3.8-flash` (tối ưu chi phí và phản hồi có cấu trúc JSON), hỗ trợ cấu hình qua biến môi trường `GEMINI_MODEL`.
- Chế độ cào: Ẩn danh (Guest), không yêu cầu tài khoản/cookie người dùng.
- Kiến trúc lean: Giữ dạng module độc lập, không thêm dependency nặng ngoài Playwright và GenAI SDK.

**Out of scope** —
- Không yêu cầu cookie hay tài khoản đăng nhập Threads.
- Không render trực tiếp ảnh hoặc video hoàn chỉnh (ghép TTS, phụ đề, footage nền, FFmpeg).
- Không tự động đăng tải bài lên YouTube/TikTok.

**Open questions** —
*(Đã giải quyết toàn bộ qua câu hỏi xác nhận)*
