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

### 1. Quét từ danh sách link Threads:
```bash
python threads_scraper.py --urls "https://www.threads.net/@vietnam_crossover"
```

### 2. Tự động sáng tác không cần quét:
```bash
python threads_scraper.py --no-scrape
```

### 3. Tích hợp dạng thư viện Python:
```python
import asyncio
from threads_scraper import get_automated_story

async def main():
    urls = ["https://www.threads.net/@user1", "https://www.threads.net/@user2"]
    story = await get_automated_story(urls)
    print(story)

asyncio.run(main())
```
