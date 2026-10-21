---
status: verified
---
# Shorts Video Quality & Real Assets Upgrade

**Problem** — Video Shorts tạo từ Threads gặp các vấn đề về chất lượng hiển thị và dữ liệu giả lập:
1. Giao diện khung Threads bị nhảy giật khung hình lên xuống mỗi khi đọc đến câu tiếp theo do thêm dần thẻ HTML làm thay đổi chiều cao card.
2. Cỡ chữ (35px) và chiều rộng (940px) chưa tối ưu độ nổi bật và dễ đọc trên điện thoại chuẩn Shorts (1080x1920).
3. Tài sản video nền và âm thanh đang là dummy (video màu trơn, sfx sóng sine điện tử giả lập).
4. Chuỗi văn bản tiếng Việt còn lỗi mất dấu (như trong lịch sử) và thiếu kho truyện cười dự phòng học đường/gia đình chất lượng cao khi Threads/Gemini không khả dụng.

**Outcome** —
1. Toàn bộ văn bản tiếng Việt chuẩn UTF-8, 100% có dấu, không viết tắt ("ko", "dc", "hlv"). Kho 5 kịch bản truyện cười học đường/gia đình hài hước có twist rõ ràng ở câu chốt hạ.
2. Tích hợp `yt-dlp` tự động tải video Minecraft Parkour Gameplay No Copyright 9:16 vertical thật (độ dài 1-3 phút) vào `assets/background.mp4`.
3. Tải hiệu ứng âm thanh SFX thật: "Bubble Pop" thật cho `assets/pop.mp3` và meme sound thật (Vine Boom / Rimshot) cho `assets/final_sfx.mp3`.
4. Cơ chế chống giật khung Threads chuẩn CapCut Mask: Đưa toàn bộ các câu của card vào HTML ngay từ đầu; câu chưa đọc áp dụng `opacity: 0;`; hàng `.actions` áp dụng `opacity: 0;` và chỉ đổi thành `opacity: 1;` ở câu cuối cùng của card. Giữ nguyên kích thước khung card cố định giữa màn hình.
5. Cỡ chữ `.content p` nâng lên `40px`, `font-weight: 500`, độ rộng `.threads-card` là `960px`.
6. Xuất ra 1 video `output_short.mp4` hoàn chỉnh đạt đầy đủ tiêu chuẩn nghiệm thu.

**Constraints** —
- Tuyệt đối không dùng dữ liệu giả lập (dummy assets).
- Đảm bảo tương thích ngược với bộ test tự động hiện có (`unittest`).
- Playwright Chromium headless, MoviePy v1 & v2 compatibility, Edge-TTS, Pydub.

**Out of scope** —
- Tự động upload lên YouTube Studio API hoặc TikTok.

**Open questions** —
*(Trống — đã xác định đầy đủ theo 5 yêu cầu bắt buộc)*

## Verification & Proof
- **Unit Tests**: 19/19 tests passed (`python -m unittest discover`).
- **Asset Integrity**:
  - `assets/background.mp4`: Real Minecraft Parkour video (31.5 MB, 1080x1920, 60fps, 87.9s).
  - `assets/pop.mp3`: Real Bubble Pop SFX (2,525 bytes, ~250ms).
  - `assets/final_sfx.mp3`: Real Vine Boom meme sound (21,230 bytes, 1.33s).
  - `assets/avatar.svg`: Cached local avatar (8,087 bytes) preventing offline network failures.
- **Card Jitter Elimination**: Playwright bounding box tests confirmed card heights are 100% invariant across all progressive reveal steps.
- **Text Normalization**: `normalize_vietnamese_text` strictly expands forbidden abbreviations ("ko", "dc", "hlv", "vs", "j") to full accented Vietnamese words.
- **Render Output**: Generated full video `output_short.mp4` (24.57s, 1080x1920, 30fps h264 + aac) using the school/family story 'Tiểu Minh và bài văn tả người hùng'.

