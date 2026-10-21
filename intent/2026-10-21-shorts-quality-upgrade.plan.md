# Plan — Shorts Video Quality & Real Assets Upgrade

## Files
1. `requirements.txt`: Bổ sung `yt-dlp>=2024.0.0`.
2. `story_history.json`: Chuẩn hóa tiếng Việt có dấu 100%.
3. `threads_video_builder.py`:
   - Hàm `download_minecraft_background()` dùng `yt-dlp` tự động tìm kiếm và tải video Minecraft Parkour thật 9:16 (1-3 phút).
   - Hàm `ensure_real_sfx()` tải SFX thật (Bubble Pop & Vine Boom).
   - Hàm `build_threads_html()`: Nâng cấp nhận toàn bộ các câu, áp dụng `opacity: 0;` cho câu chưa đọc, điều khiển `.actions` chỉ hiển thị `opacity: 1;` ở câu cuối cùng của Card.
   - Nâng cấp CSS `.content p` lên `40px`, `font-weight: 500`, `.threads-card` lên `960px`.
   - Cập nhật kho 5 truyện cười học đường/gia đình thật sự hài hước, có twist chuẩn trong `SAMPLE_STORIES`.
   - Bổ sung fallback tự động sang kho 5 truyện nếu lấy bài từ Threads/Gemini gặp lỗi.
4. `test_threads_video_builder.py`: Bổ sung test kiểm tra chống giật (opacity), kích thước font 40px, font-weight 500, card 960px, và fallback stories.

## Risks & Mitigations
- **Risk 1**: yt-dlp gặp lỗi mạng hoặc YouTube throttling.
  *Mitigation*: Sử dụng format chuẩn, tự động chọn URL phù hợp, xử lý ngoại lệ và lưu file an toàn.
- **Risk 2**: Lệch chiều cao card giữa các câu gây nhảy khung.
  *Mitigation*: Tất cả các thẻ `<p>` đều render trong DOM ngay từ step 1, chỉ ẩn/hiện bằng CSS `opacity: 0 / 1`. Chiều cao DOM giữ nguyên 100%.
- **Risk 3**: Thiếu asset khi chạy offline hoặc server không có internet.
  *Mitigation*: Kiểm tra file trước khi tải, nếu file thật đã có thì tái sử dụng mà không cần tải lại.

## Proof
- `python -m unittest discover`: Toàn bộ test suite vượt qua 100%.
- Kiểm tra dung lượng và codec của `assets/background.mp4` (> 5MB, 1080x1920, thật).
- Kiểm tra dung lượng và waveform của `assets/pop.mp3` và `assets/final_sfx.mp3` (âm thanh thật, không phải sóng sine).
- Render thành công 1 video thực tế `output_short.mp4` và kiểm tra thời lượng, độ phân giải, âm thanh và chuyển động mượt mà không bị giật khung.
