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

### 5. Tự động đăng đa nền tảng & Web Dashboard (Port 8080):
Hệ thống hỗ trợ tự động đăng video lên 3 nền tảng: **YouTube Shorts**, **TikTok Studio**, và **Facebook Reels** theo chu kỳ 4 tiếng / video, đi kèm Web Dashboard trực quan và cơ chế quản lý phiên/cookie 100% ổn định:

```bash
# Bước 1: Đăng nhập & nạp phiên tài khoản (hỗ trợ cả WSL2 / Linux / Windows)
python auto_publisher.py --login

# Kiểm tra nhanh trạng thái xác thực của 3 nền tảng từ terminal:
python auto_publisher.py --check-login

# Bước 2: Khởi động vòng lặp tự động (4 tiếng / 1 video) & Dashboard theo dõi:
python auto_publisher.py

# Hoặc chạy thử nghiệm 1 chu kỳ giả lập đăng tải (Dry-Run):
python auto_publisher.py --dry-run --once

# Chỉ mở riêng máy chủ Web Dashboard (cổng 8080):
python auto_publisher.py --server-only
```

#### 🔐 Hướng dẫn Đăng nhập & Nạp Cookie (Khuyên dùng cho WSL2 / Windows):
Trong môi trường WSL2 / Linux headless (không có màn hình GUI trực tiếp):
1. **Nạp Cookie trực tiếp qua Web Dashboard (`http://localhost:8080#accounts`)**:
   - Cài tiện ích [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) trên Cốc Cốc, Chrome, hoặc Edge.
   - Đăng nhập TikTok, YouTube Studio, Facebook trên trình duyệt máy bạn bình thường.
   - Mở tiện ích Cookie-Editor trên tab vừa đăng nhập &rarr; chọn **Export** &rarr; chọn **Export as JSON**.
   - Mở `http://localhost:8080` &rarr; tab **"🔐 Đăng Nhập & Quản Lý Tài Khoản"** &rarr; Dán mã JSON vào khung và bấm **"Lưu & Nạp Cookie"**. Hệ thống sẽ ngay lập tức chuyển trạng thái sang **✅ Đã đăng nhập**.
2. **Dùng file trợ lý Windows Helper**:
   - Chạy file `login_helper_windows.bat` trên Windows để tự động mở sẵn các tab đăng nhập và trang Web Dashboard.
3. **Thả file cookie có sẵn**:
   - Bạn có thể đặt file `auth_state.json` (Playwright storage_state) hoặc `cookies.json` trực tiếp vào thư mục gốc dự án.

- **Web Dashboard**: Truy cập trực tiếp tại `http://localhost:8080`:
  - **Tab 1 - Tiến độ Video**: Thống kê số lượng video, đồng hồ đếm ngược, danh sách trạng thái xuất bản, xem video trực tiếp bằng trình phát modal tích hợp.
  - **Tab 2 - Quản lý Tài khoản & Cookie**: Thẻ trạng thái thời gian thực cho TikTok, YouTube Studio, Facebook Reels kèm công cụ nạp và xuất session cookie một chạm.



