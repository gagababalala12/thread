# Threads Story Scraper & Gemini Story Formatter

Module tự động cào bài đăng từ Threads bằng **Playwright** và sử dụng **Google Gemini AI** (SDK `google-genai`) để chọn lọc, biên tập thành kịch bản 2-Card hài hước phục vụ sản xuất YouTube Shorts / TikTok.

## Tính năng

1. **Playwright Scraper**:
   - Tự động cuộn trang Threads (`max_scrolls`).
   - Lọc các bài viết có độ dài phù hợp (80 - 650 ký tự), bỏ qua các link spam.
   - Hỗ trợ đóng các popup/overlay đăng nhập của Threads.

2. **Gemini AI Audio Director & Multi-Voice Formatter**:
   - Sử dụng model `gemini-3.5-flash-lite` / `gemini-3.8-flash` tốc độ cao với Structured Outputs (`StoryLine` schema).
   - Phân vai đa giọng đọc: Nam (`vi-VN-NamMinhNeural`) & Nữ (`vi-VN-HoaiMyNeural`) sinh động cho từng câu thoại.
   - Tự động chọn hiệu ứng âm thanh Mid-SFX (`huh`, `cai_gi_do`, `laugh`, `vine_boom`, `wow`) khớp cảm xúc.
   - Hỗ trợ cờ `use_video_meme_outro: bool` để chèn clip meme reaction vào cuối video.
   - Đánh giá điểm hài hước (`humor_score` từ 1-10) và lưu lịch sử (`story_history.json`).

3. **Meme Harvester (yt-dlp)**:
   - Tự động tìm kiếm và tải kho nhạc nền TikTok BGM (`assets/bgm/`, 30-120s).
   - Bộ 5 SFX meme kinh điển (`assets/sfx/`: `huh`, `cai_gi_do`, `laugh`, `vine_boom`, `wow` < 8s).
   - Bộ 3 Video Meme reaction Việt Nam kinh điển (`assets/video_memes/`: Trời đất ơi..., Ảo thật đấy..., Sợ quá cơ... 2-5s cắt đoạn cao trào).

4. **Auto Threads Video Generator**:
   - Lồng nhạc nền BGM xuyên suốt video với âm lượng 12% (`volumex(0.12)` / `with_volume_scaled(0.12)`).
   - Chèn Mid-SFX ngay sau khi dứt câu và nghỉ 0.5s trước khi sang câu kế tiếp.
   - Nối clip Video Meme reaction ở nửa dưới màn hình sau câu chốt hạ của Card 2.
   - Chống giật khung Threads bằng CSS mask `opacity` giữ cố định chiều cao DOM.

## Cài đặt

```bash
pip install -r requirements.txt
playwright install chromium
```

## Cấu hình

Tạo file `.env` hoặc export biến môi trường:
```bash
cp .env.example .env
export GEMINI_API_KEY="your_api_key_here"
```

## Cách chạy

### 1. Tự động săn kho tài nguyên BGM, SFX và Video Meme từ YouTube:
```bash
python meme_harvester.py
```

### 2. Quét từ danh sách link Threads và xuất JSON kịch bản:
```bash
python threads_scraper.py --urls "https://www.threads.net/@vietnam_crossover"
```

### 3. Tự động tạo Video Shorts hoàn chỉnh (Triệu view style Động Threads):
```bash
# Tạo 1 video chuẩn với BGM, Mid-SFX và Video Meme Reaction
python auto_threads_video.py --count 1

# Hoặc dùng threads_video_builder.py
python threads_video_builder.py --count 1 --watermark "hamster kể chuyện"
```

> **Ghi chú về Video nền**: Hãy đặt video nền yêu thích của bạn (Minecraft parkour, gameplay, satisfying,...) vào đường dẫn `assets/background.mp4`. Hệ thống sẽ tự động crop và canh giữa theo chuẩn tỷ lệ 9:16 (1080x1920).

### 4. Tích hợp dạng thư viện Python:
```python
import asyncio
from threads_scraper_ai import get_automated_story
from threads_video_builder import render_story_video

async def main():
    urls = ["https://www.threads.net/search?q=chuy%E1%BB%87n%20h%C3%A0i"]
    # 1. Cào bài và chọn câu chuyện bằng Gemini AI
    story = await get_automated_story(urls)
    # 2. Render thành video Shorts MP4 hoàn chỉnh
    await render_story_video(story, output_file="my_viral_short.mp4")

asyncio.run(main())
```
