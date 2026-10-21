---
status: shipped
---
# Threads Story Shorts Video Generator

**Problem** — Kịch bản 2-Card từ Threads và Gemini AI mới chỉ ở dạng JSON text, chưa thể tự động chuyển thành video dọc hoàn chỉnh để đăng tải lên YouTube Shorts, TikTok, Facebook Reels. Cần một quy trình tự động biến text thành video: lồng tiếng TTS tiếng Việt, cắt khoảng lặng, render giao diện Threads card từng dòng (progressive reveal) và ghép video nền + âm thanh hoàn chỉnh.

**Outcome** —
- Module tự động hóa sản xuất video Shorts (`threads_video_builder.py`):
  1. Tự động sinh audio giọng đọc cho từng câu bằng `edge-tts` (giọng tự nhiên `vi-VN-HoaiMyNeural` tốc độ `+18%`).
  2. Dùng `pydub` tự động cắt khoảng lặng đầu/đuôi (silence trimming) để nhịp điệu nhanh, dồn dập chuẩn Shorts.
  3. Dùng Playwright chụp ảnh giao diện Threads Card sắc nét từng dòng (progressive reveal: câu sau hiện tiếp câu trước).
  4. Ghép nối bằng MoviePy: Video nền 9:16 (1080x1920 @ 30fps), watermark kênh, hiệu ứng âm thanh pop/sfx cho câu chốt hạ.
  5. Hỗ trợ chạy batch tạo hàng loạt video tự động từ danh sách URL Threads.
- Đo được (Proof): Sinh video MP4 dọc 1080x1920 hoàn chỉnh, audio và hình ảnh đồng bộ chuẩn xác từng câu nói.

**Constraints** —
- Tech: Python 3.10+, MoviePy 2.x, Playwright Chromium, `edge-tts`, `pydub`, ffmpeg.
- Video: 1080x1920 (9:16), 30 FPS, H.264 / AAC.
- Tương thích: Tự động phát hiện và hỗ trợ linh hoạt cả MoviePy v1 và v2.

**Out of scope** —
- Chưa tự động upload lên YouTube Studio API hay TikTok Content API.
- Không can thiệp chỉnh sửa thủ công timeline (hoàn toàn chạy tự động từ kịch bản JSON).

**Open questions** —
*(Trống — đã xác định đầy đủ theo mã nguồn người dùng)*
