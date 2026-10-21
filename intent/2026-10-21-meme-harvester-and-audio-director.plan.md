# Plan — Meme Harvester, Multi-Voice Audio Director & Viral Meme Reactions

## Files & Changes
1. `meme_harvester.py` (New):
   - Hàm `harvest_bgm(target_dir, force=False)`: Tải 2-3 bản nhạc beat hài hước từ YouTube qua `ytsearch5:`, kiểm tra thời lượng 30-120 giây (cắt bằng ffmpeg nếu cần), lưu vào `assets/bgm/`.
   - Hàm `harvest_sfx(target_dir, force=False)`: Tải 5 âm thanh meme (`huh.mp3`, `cai_gi_do.mp3`, `laugh.mp3`, `vine_boom.mp3`, `wow.mp3`), kiểm tra thời lượng < 8s, lưu vào `assets/sfx/`.
   - Hàm `harvest_video_memes(target_dir, force=False)`: Tải 2-3 clip reaction Việt Nam ngắn, dùng ffmpeg cắt đúng đoạn cao trào 2-5 giây, lưu vào `assets/video_memes/`.
   - Hàm `harvest_all(assets_dir)` và CLI `python meme_harvester.py`.

2. `threads_scraper.py` & `threads_scraper_ai.py`:
   - Định nghĩa Pydantic model `StoryLine(text, voice, sfx_after)` với validator hỗ trợ chuỗi cũ `str`.
   - Cập nhật `ThreadCard` dùng `lines: List[StoryLine]`.
   - Cập nhật `StorySelection` thêm `use_video_meme_outro: bool = True`.
   - Cập nhật prompt Gemini làm đạo diễn âm thanh & hội thoại nhân vật nam/nữ.
   - Đồng bộ hóa re-export trong `threads_scraper_ai.py`.

3. `threads_video_builder.py`:
   - Cập nhật `SAMPLE_STORIES` cả 5 câu chuyện thành cấu trúc `StoryLine` với phân vai Nam/Nữ và chọn SFX phù hợp.
   - Cập nhật `build_threads_html` hỗ trợ cả `StoryLine` lẫn `str`.
   - Trong `prepare_media_assets`: sinh TTS theo `line.voice`.
   - Trong `build_final_video`:
     + Tải/chọn BGM ngẫu nhiên từ `assets/bgm/`, hạ âm lượng 12% (`with_volume_scaled(0.12)`/`volumex(0.12)`).
     + Chèn SFX giữa câu nếu `sfx_after != "none"`, cộng độ nghỉ 0.5s.
     + Chèn video meme reaction cuối video (resize 750px, canh giữa nửa dưới màn hình) khi `use_video_meme_outro` là True.

4. `auto_threads_video.py` (New):
   - Script chạy CLI và API chính theo yêu cầu đề bài, tái sử dụng các hàm từ `threads_video_builder.py`.

5. Tests:
   - Cập nhật `test_threads_scraper.py` và `test_threads_video_builder.py`.
   - Bổ sung `test_meme_harvester.py` để kiểm thử logic harvester.

## Reviewer Fixes & Hardening
- `meme_harvester.py`: Bổ sung hàm `trim_audio_silence_sfx` tự động cắt sạch khoảng lặng chết (> 2.9s ở `huh.mp3`, > 3.9s ở `laugh.mp3`) để âm thanh meme phát tức thì ngay khi dứt câu thoại.
- `threads_scraper.py`: Bổ sung `@field_validator` chuẩn hóa giọng đọc linh hoạt ("female", "hoaimy", "nam", "male") và chuẩn hóa SFX ("huh.mp3" -> "huh"), tránh lỗi `ValidationError` khi LLM sinh dữ liệu lệch chuẩn; đảm bảo `ThreadCard.use_video_meme_outro: bool = True`.
- `threads_video_builder.py`:
  + Sửa lỗi tràn âm Mid-SFX: subclip `sfx_clip` về đúng `sfx_play_duration` để âm thanh không tràn lấn sang câu tiếp theo trong thời gian nghỉ 0.5s.
  + Sửa lỗi đè khung hình Video Meme: tính toán vị trí `pos_y` động dựa trên đáy thực tế của card (`card_bottom`), giới hạn chiều cao meme tối đa 440px (16:9 750x422) để video meme luôn nằm hoàn toàn bên dưới Threads card, không che khuất phần kết và nút like/reply.
  + Hỗ trợ cờ `--output` trong CLI.

## Verification
- Chạy unit tests: `python -m unittest discover` (35/35 PASS)
- Chạy `python meme_harvester.py` để nạp và làm sạch kho tài nguyên thật.
- Chạy `python auto_threads_video.py` để xuất video kiểm tra chất lượng thực tế.

