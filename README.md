# Threads Story Scraper & Gemini Story Formatter

Module tự động cào bài đăng từ Threads bằng **Playwright** và sử dụng **Google Gemini AI** (SDK `google-genai`) để chọn lọc, biên tập thành kịch bản 2-Card hài hước phục vụ sản xuất YouTube Shorts / TikTok.

## Tính năng

1. **Playwright Scraper**:
   - Tự động cuộn trang Threads (`max_scrolls`).
   - Lọc các bài viết có độ dài phù hợp (80 - 650 ký tự), bỏ qua các link spam.
   - Hỗ trợ đóng các popup/overlay đăng nhập của Threads.

2. **Gemini AI Curation & Formatting**:
   - Sử dụng model `gemini-3.8-flash` tốc độ cao với Structured Outputs (Pydantic schema).
   - Đánh giá điểm hài hước (`humor_score` từ 1-10).
   - Định dạng chuẩn 2 Cards (Card 1: dẫn dắt/tò mò, Card 2: chốt hạ/twist gây cười).
   - Tự động lưu và kiểm tra lịch sử (`story_history.json`) để tránh trùng lặp nội dung.

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

### 1. Quét từ danh sách link Threads và xuất JSON kịch bản:
```bash
python threads_scraper.py --urls "https://www.threads.net/@vietnam_crossover"
```

### 2. Tự động sáng tác không cần quét:
```bash
python threads_scraper.py --no-scrape
```

### 3. Tự động tạo Video Shorts hoàn chỉnh (TTS + Giao diện Cards + Video nền):
```bash
# Tạo 1 video đơn lẻ
python threads_video_builder.py --count 1

# Tạo batch 5 video liên tiếp với watermark tùy chỉnh
python threads_video_builder.py --count 5 --watermark "hamster kể chuyện"
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
