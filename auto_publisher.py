import asyncio
import json
import os
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from playwright.async_api import async_playwright

# Import hàm sản xuất video từ pipeline hiện tại
from auto_threads_video import prepare_media_assets, build_final_video
from threads_scraper_ai import get_automated_story, TARGET_THREADS_URLS

STATUS_FILE = Path("publish_status.json")
PROFILE_DIR = Path("browser_profile")
INTERVAL_HOURS = 4  # Chu kỳ 4 tiếng 1 video
NEXT_RUN_TIME = None

# ==========================================
# 1. QUẢN LÝ DỮ LIỆU TRẠNG THÁI (JSON DB)
# ==========================================
def load_status_list() -> list:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_status_record(record: dict):
    data = load_status_list()
    # Cập nhật nếu đã tồn tại ID, nếu chưa thì thêm lên đầu danh sách
    for idx, item in enumerate(data):
        if item.get("id") == record.get("id"):
            data[idx] = record
            break
    else:
        data.insert(0, record)
    STATUS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ==========================================
# 2. TỰ ĐỘNG ĐĂNG BÀI ĐA NỀN TẢNG (PLAYWRIGHT)
# ==========================================
async def upload_to_tiktok(page, video_path: Path, caption: str) -> str:
    try:
        print("[TikTok] Đang truy cập TikTok Studio Upload...")
        await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Tải file video lên thẻ input[type="file"]
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(str(video_path.resolve()))
        print("[TikTok] Đã nạp file video, đang chờ xử lý...")
        await asyncio.sleep(12)

        # Điền caption
        caption_box = page.locator('div[contenteditable="true"]').first
        if await caption_box.count() > 0:
            await caption_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(caption, delay=20)

        await asyncio.sleep(3)
        # Bấm nút Đăng (Post)
        post_btn = page.locator('button:has-text("Đăng"), button:has-text("Post")').last
        await post_btn.click()
        await asyncio.sleep(8)
        return "✅ Đã đăng"
    except Exception as e:
        print(f"[!] Lỗi đăng TikTok: {e}")
        return f"❌ Lỗi ({str(e)[:25]}...)"

async def upload_to_youtube_shorts(page, video_path: Path, title: str) -> str:
    try:
        print("[YouTube] Đang truy cập YouTube Studio...")
        await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # Bấm nút Tạo (Create) -> Tải video lên
        create_btn = page.locator('#create-icon, ytcp-button:has-text("Tạo"), ytcp-button:has-text("Create")').first
        await create_btn.click()
        await asyncio.sleep(2)

        upload_item = page.locator('tp-yt-paper-item:has-text("Tải video lên"), tp-yt-paper-item:has-text("Upload videos")').first
        await upload_item.click()
        await asyncio.sleep(2)

        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(str(video_path.resolve()))
        await asyncio.sleep(10)

        # Điền tiêu đề kèm #Shorts
        title_box = page.locator('#textbox').first
        if await title_box.count() > 0:
            await title_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.type(f"{title[:85]} #Shorts", delay=20)

        # Chọn "Không, nội dung này không dành cho trẻ em"
        not_for_kids = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first
        if await not_for_kids.count() > 0:
            await not_for_kids.click()

        # Nhấn Tiếp (Next) 3 lần
        for _ in range(3):
            next_btn = page.locator('#next-button').first
            await next_btn.click()
            await asyncio.sleep(2)

        # Chọn Công khai (Public) và nhấn Xuất bản
        public_radio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"]').first
        if await public_radio.count() > 0:
            await public_radio.click()
            await asyncio.sleep(2)

        done_btn = page.locator('#done-button').first
        await done_btn.click()
        await asyncio.sleep(8)
        return "✅ Đã đăng"
    except Exception as e:
        print(f"[!] Lỗi đăng YouTube: {e}")
        return f"❌ Lỗi ({str(e)[:25]}...)"

async def upload_to_facebook_reels(page, video_path: Path, caption: str) -> str:
    try:
        print("[Facebook] Đang truy cập trang tạo Reels...")
        await page.goto("https://www.facebook.com/reels/create", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        file_input = page.locator('input[type="file"]').first
        await file_input.set_input_files(str(video_path.resolve()))
        await asyncio.sleep(10)

        # Bấm Tiếp (Next) sang bước chỉnh sửa và mô tả
        for _ in range(2):
            next_btn = page.locator('div[role="button"]:has-text("Tiếp"), div[role="button"]:has-text("Next")').last
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(4)

        # Điền mô tả Reels
        desc_box = page.locator('div[role="textbox"]').first
        if await desc_box.count() > 0:
            await desc_box.click()
            await page.keyboard.type(caption, delay=20)
            await asyncio.sleep(2)

        publish_btn = page.locator('div[role="button"]:has-text("Đăng"), div[role="button"]:has-text("Publish")').last
        await publish_btn.click()
        await asyncio.sleep(10)
        return "✅ Đã đăng"
    except Exception as e:
        print(f"[!] Lỗi đăng Facebook: {e}")
        return f"❌ Lỗi ({str(e)[:25]}...)"

async def publish_all_platforms(video_path: Path, caption: str, record: dict):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR.resolve()),
            headless=True,  # Đổi thành False nếu muốn nhìn trình duyệt tự bấm
            viewport={"width": 1280, "height": 800},
            locale="vi-VN",
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await context.new_page()

        record["youtube"] = "⏳ Đang đăng..."
        save_status_record(record)
        record["youtube"] = await upload_to_youtube_shorts(page, video_path, caption)
        save_status_record(record)

        record["tiktok"] = "⏳ Đang đăng..."
        save_status_record(record)
        record["tiktok"] = await upload_to_tiktok(page, video_path, caption)
        save_status_record(record)

        record["facebook"] = "⏳ Đang đăng..."
        save_status_record(record)
        record["facebook"] = await upload_to_facebook_reels(page, video_path, caption)
        record["overall_status"] = "Hoàn tất (Đã đăng xong)"
        save_status_record(record)

        await context.close()

# ==========================================
# 3. GIAO DIỆN WEB DASHBOARD THEO DÕI (PORT 8080)
# ==========================================
class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Ẩn log request trên terminal cho gọn

    def do_GET(self):
        records = load_status_list()
        next_str = NEXT_RUN_TIME.strftime("%H:%M:%S - %d/%m/%Y") if NEXT_RUN_TIME else "Đang xử lý..."

        rows_html = ""
        for r in records:
            rows_html += f"""
            <tr>
                <td><strong>#{r.get('id', '-')}</strong><br><small style="color:#888">{r.get('created_at', '-')}</small></td>
                <td>{r.get('title', '-')}<br><small style="color:#60a5fa">{r.get('video_file', '-')}</small></td>
                <td><span class="badge">{r.get('youtube', '-')}</span></td>
                <td><span class="badge">{r.get('facebook', '-')}</span></td>
                <td><span class="badge">{r.get('tiktok', '-')}</span></td>
                <td><strong style="color:#4ade80">{r.get('overall_status', '-')}</strong></td>
            </tr>
            """
        if not rows_html:
            rows_html = '<tr><td colspan="6" style="text-align:center;padding:30px">Chưa có video nào trong danh sách. Hệ thống đang chuẩn bị video đầu tiên...</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="15">
    <title>Bảng Theo Dõi Đăng Video Tự Động (4 Tiếng / Video)</title>
    <style>
        body {{ background: #0f172a; color: #f8fafc; font-family: system-ui, sans-serif; padding: 32px; margin: 0; }}
        .container {{ max-width: 1150px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 20px 28px; border-radius: 14px; margin-bottom: 24px; border: 1px solid #334155; }}
        .timer {{ background: #0284c7; padding: 10px 18px; border-radius: 8px; font-weight: 600; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 14px; overflow: hidden; }}
        th, td {{ padding: 16px 18px; text-align: left; border-bottom: 1px solid #334155; font-size: 15px; }}
        th {{ background: #0f172a; color: #94a3b8; text-transform: uppercase; font-size: 13px; }}
        .badge {{ background: #334155; padding: 6px 12px; border-radius: 6px; font-size: 13px; display: inline-block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h2 style="margin:0 0 6px 0">🚀 Trạm Kiểm Soát Auto-Threads Shorts</h2>
                <span style="color:#94a3b8">Chu kỳ tự động: <strong>{INTERVAL_HOURS} tiếng / 1 video</strong> • Tổng đã xử lý: <strong>{len(records)} video</strong></span>
            </div>
            <div class="timer">⏰ Lần đăng kế tiếp: {next_str}</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Mã / Giờ</th>
                    <th>Nội dung & File Video</th>
                    <th>YouTube Shorts</th>
                    <th>Facebook Reels</th>
                    <th>TikTok</th>
                    <th>Trạng thái tổng</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True

def start_dashboard_server(port=8080):
    server = ReusableHTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"📊 Bảng theo dõi trực tuyến đã mở tại: http://localhost:{port}")
    server.serve_forever()

# ==========================================
# 4. VÒNG LẶP CHÍNH: 4 TIẾNG 1 VIDEO
# ==========================================
async def login_setup():
    """Chạy 1 lần đầu để đăng nhập sẵn tài khoản vào browser_profile/"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR.resolve()),
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await context.new_page()
        await page.goto("https://www.tiktok.com/login")
        print("👉 Hãy đăng nhập TikTok, YouTube Studio và Facebook trên cửa sổ trình duyệt vừa mở.")
        print("👉 Sau khi đăng nhập xong cả 3 trang, hãy đóng cửa sổ trình duyệt lại.")
        await page.wait_for_event("close", timeout=0)
        await context.close()

async def run_4h_pipeline(once: bool = False):
    global NEXT_RUN_TIME
    import auto_threads_video

    # Khởi chạy Web Dashboard ở luồng phụ
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    dashboard_thread = threading.Thread(
        target=start_dashboard_server,
        kwargs={"port": port},
        daemon=True
    )
    dashboard_thread.start()

    video_counter = len(load_status_list()) + 1
    while True:
        now_str = datetime.now().strftime("%H:%M - %d/%m/%Y")
        output_name = f"short_video_{video_counter}_{int(datetime.now().timestamp())}.mp4"
        output_path = Path("published_videos") / output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "id": video_counter,
            "created_at": now_str,
            "title": "Đang quét Threads & tạo kịch bản...",
            "video_file": output_name,
            "youtube": "⏳ Chờ video",
            "facebook": "⏳ Chờ video",
            "tiktok": "⏳ Chờ video",
            "overall_status": "🎬 Đang dựng video..."
        }
        save_status_record(record)

        try:
            # Bước 1: Quét kịch bản mới và dựng video
            story = await get_automated_story(TARGET_THREADS_URLS, api_key=os.environ.get("GEMINI_API_KEY"))
            auto_threads_video.STORY_DATA = story
            first_line = story["cards"][0]["lines"][0]
            text_hook = first_line["text"] if isinstance(first_line, dict) else str(first_line)
            caption = f"{text_hook} #threads #haihuoc #xuhuong #shorts"

            record["title"] = text_hook[:70] + "..."
            save_status_record(record)

            temp_dir = Path("temp_current_build")
            temp_dir.mkdir(parents=True, exist_ok=True)
            segments, wm_path = await prepare_media_assets(temp_dir)
            build_final_video(segments, wm_path, output_file=str(output_path))

            # Bước 2: Tự động đăng lên 3 nền tảng
            record["overall_status"] = "🚀 Đang đăng lên 3 kênh..."
            save_status_record(record)
            await publish_all_platforms(output_path, caption, record)

        except Exception as e:
            record["overall_status"] = f"❌ Lỗi: {str(e)[:40]}"
            save_status_record(record)

        if once:
            print("[✓] Đã hoàn thành 1 chu kỳ thử nghiệm (--once)!")
            break

        video_counter += 1
        NEXT_RUN_TIME = datetime.now() + timedelta(hours=INTERVAL_HOURS)
        print(f"[✓] Đã xong chu kỳ! Chờ {INTERVAL_HOURS} tiếng cho video tiếp theo (lúc {NEXT_RUN_TIME.strftime('%H:%M:%S')})...")
        await asyncio.sleep(INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    import sys
    if "--login" in sys.argv:
        asyncio.run(login_setup())
    elif "--once" in sys.argv:
        asyncio.run(run_4h_pipeline(once=True))
    else:
        asyncio.run(run_4h_pipeline())
