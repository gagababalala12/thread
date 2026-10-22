import asyncio
import json
import os
import shutil
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
PUBLISHED_DIR = Path("published_videos")
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

async def publish_all_platforms(video_path: Path, caption: str, record: dict, dry_run: bool = False):
    if dry_run:
        print(f"[Dry-Run] Bắt đầu giả lập đăng bài: {video_path.name}")
        record["youtube"] = "⏳ Đang đăng..."
        save_status_record(record)
        await asyncio.sleep(0.5)
        record["youtube"] = "✅ Đã đăng"
        save_status_record(record)

        record["tiktok"] = "⏳ Đang đăng..."
        save_status_record(record)
        await asyncio.sleep(0.5)
        record["tiktok"] = "✅ Đã đăng"
        save_status_record(record)

        record["facebook"] = "⏳ Đang đăng..."
        save_status_record(record)
        await asyncio.sleep(0.5)
        record["facebook"] = "✅ Đã đăng"
        record["overall_status"] = "Hoàn tất (Đã đăng xong)"
        save_status_record(record)
        print(f"[✓] [Dry-Run] Đã giả lập đăng bài thành công lên 3 nền tảng cho {video_path.name}")
        return

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR.resolve()),
            headless=True,
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
def render_badge(status_text: str) -> str:
    """Trả về HTML badge với màu sắc tương ứng theo trạng thái."""
    status = str(status_text or "")
    if "Đã đăng" in status or "Hoàn tất" in status:
        bg, color = "#065f46", "#34d399"
    elif "Đang" in status or "Chờ" in status:
        bg, color = "#854d0e", "#fde047"
    elif "Lỗi" in status:
        bg, color = "#991b1b", "#f87171"
    else:
        bg, color = "#334155", "#cbd5e1"
    return f'<span class="badge" style="background:{bg};color:{color}">{status}</span>'

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Ẩn log request trên terminal cho gọn

    def do_HEAD(self):
        if self.path.startswith("/videos/"):
            video_name = self.path[len("/videos/"):].split("?")[0]
            clean_name = Path(video_name).name
            video_file = (PUBLISHED_DIR / clean_name).resolve()
            if not video_file.exists():
                video_file = Path(clean_name).resolve()
            if video_file.exists() and video_file.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(video_file.stat().st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return
            else:
                self.send_error(404, "Video Not Found")
                return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        # 1. Phục vụ video trực tiếp qua endpoint /videos/<filename>
        if self.path.startswith("/videos/"):
            video_name = self.path[len("/videos/"):].split("?")[0]
            # Sanitize tên file để tránh directory traversal
            clean_name = Path(video_name).name
            video_file = (PUBLISHED_DIR / clean_name).resolve()
            if not video_file.exists():
                # Thử tìm ở thư mục gốc (cho các file mẫu như output_short.mp4)
                video_file = Path(clean_name).resolve()

            if video_file.exists() and video_file.is_file():
                try:
                    file_size = video_file.stat().st_size
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(file_size))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    with open(video_file, "rb") as f:
                        shutil.copyfileobj(f, self.wfile)
                    return
                except (BrokenPipeError, ConnectionResetError):
                    return
            else:
                self.send_error(404, "Video Not Found")
                return

        # 2. Trang chủ Dashboard
        records = load_status_list()
        total_exported = len(records)
        total_published = sum(1 for r in records if "Đã đăng" in str(r.get("overall_status", "")))

        next_str = NEXT_RUN_TIME.strftime("%H:%M:%S - %d/%m/%Y") if NEXT_RUN_TIME else "Đang khởi tạo chu kỳ..."
        next_iso = NEXT_RUN_TIME.isoformat() if NEXT_RUN_TIME else ""

        rows_html = ""
        for r in records:
            vfile = r.get('video_file', '-')
            has_video = (PUBLISHED_DIR / Path(vfile).name).exists() or Path(vfile).exists()
            clean_title = str(r.get("title", "Video")).replace("'", "").replace('"', "&quot;")
            if has_video:
                action_btn = f'<button class="btn-watch" onclick="openPlayer(\'/videos/{vfile}\', \'{clean_title}\')">▶ Xem video</button>'
            else:
                action_btn = '<span style="color:#64748b;font-size:13px">⏳ Chưa có file</span>'

            rows_html += f"""
            <tr>
                <td><strong>#{r.get('id', '-')}</strong></td>
                <td><small style="color:#94a3b8">{r.get('created_at', '-')}</small></td>
                <td><div class="story-title" title="{r.get('title', '-')}">{r.get('title', '-')}</div><small style="color:#60a5fa">{vfile}</small></td>
                <td>{render_badge(r.get('youtube', '-'))}</td>
                <td>{render_badge(r.get('facebook', '-'))}</td>
                <td>{render_badge(r.get('tiktok', '-'))}</td>
                <td>{render_badge(r.get('overall_status', '-'))}</td>
                <td style="text-align:center">{action_btn}</td>
            </tr>
            """
        if not rows_html:
            rows_html = '<tr><td colspan="8" style="text-align:center;padding:36px;color:#94a3b8">Chưa có video nào trong danh sách. Hệ thống đang chuẩn bị sản xuất video đầu tiên...</td></tr>'

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bảng Theo Dõi Đăng Video Tự Động (4 Tiếng / Video)</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ background: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 28px 20px; margin: 0; }}
        .container {{ max-width: 1250px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 22px 28px; border-radius: 16px; margin-bottom: 24px; border: 1px solid #334155; }}
        .header-title h2 {{ margin: 0 0 6px 0; font-size: 24px; color: #ffffff; }}
        .header-title span {{ color: #94a3b8; font-size: 14px; }}
        
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .stat-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 14px; padding: 18px 22px; }}
        .stat-card .label {{ color: #94a3b8; font-size: 13px; text-transform: uppercase; font-weight: 600; margin-bottom: 6px; }}
        .stat-card .value {{ font-size: 26px; font-weight: 700; color: #38bdf8; }}
        .stat-card .sub {{ font-size: 13px; color: #64748b; margin-top: 4px; }}

        .table-wrap {{ background: #1e293b; border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th, td {{ padding: 16px 18px; border-bottom: 1px solid #334155; font-size: 14px; vertical-align: middle; }}
        th {{ background: #0b1120; color: #94a3b8; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; font-weight: 600; }}
        tr:hover {{ background: #243247; }}
        
        .badge {{ padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; display: inline-block; white-space: nowrap; }}
        .story-title {{ max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; color: #f1f5f9; }}
        .btn-watch {{ background: #0284c7; color: #ffffff; border: none; padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; gap: 6px; }}
        .btn-watch:hover {{ background: #0369a1; }}
        
        /* Modal Player */
        .modal {{ display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); align-items: center; justify-content: center; }}
        .modal.active {{ display: flex; }}
        .modal-content {{ background: #1e293b; border-radius: 16px; border: 1px solid #475569; padding: 20px; max-width: 480px; width: 90%; text-align: center; position: relative; }}
        .modal-title {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: #f8fafc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }}
        .modal-close {{ position: absolute; right: 14px; top: 12px; background: none; border: none; font-size: 24px; color: #94a3b8; cursor: pointer; }}
        .modal-close:hover {{ color: #ffffff; }}
        video {{ width: 100%; max-height: 70vh; border-radius: 10px; background: #000; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title">
                <h2>🚀 Trạm Kiểm Soát Auto-Threads Shorts</h2>
                <span>Chu kỳ tự động: <strong>{INTERVAL_HOURS} tiếng / 1 video</strong> • Tự động refresh mỗi 10 giây</span>
            </div>
            <div style="background:#0284c7;padding:12px 20px;border-radius:10px;text-align:right">
                <div style="font-size:12px;color:#bae6fd;text-transform:uppercase;font-weight:600">Đăng video tiếp theo</div>
                <div style="font-size:18px;font-weight:700;color:#ffffff" id="timer-text">{next_str}</div>
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Tổng video đã xuất</div>
                <div class="value">{total_exported} <span style="font-size:16px;font-weight:400;color:#94a3b8">video</span></div>
                <div class="sub">Tất cả video đã dựng hoàn chỉnh</div>
            </div>
            <div class="stat-card">
                <div class="label">Đã đăng thành công</div>
                <div class="value" style="color:#4ade80">{total_published} <span style="font-size:16px;font-weight:400;color:#94a3b8">video</span></div>
                <div class="sub">Hoàn tất đăng lên 3 nền tảng</div>
            </div>
            <div class="stat-card">
                <div class="label">Đồng hồ đếm ngược</div>
                <div class="value" id="countdown-val" style="color:#facc15">--:--:--</div>
                <div class="sub">Thời gian còn lại đến chu kỳ sau</div>
            </div>
        </div>

        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th style="width:70px">Mã</th>
                        <th style="width:130px">Thời gian</th>
                        <th>Nội dung & File Video</th>
                        <th>YouTube Shorts</th>
                        <th>Facebook Reels</th>
                        <th>TikTok</th>
                        <th>Trạng thái tổng</th>
                        <th style="text-align:center;width:120px">Xem video</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
    </div>

    <!-- Video Modal Player -->
    <div id="videoModal" class="modal">
        <div class="modal-content">
            <button class="modal-close" onclick="closePlayer()">&times;</button>
            <div id="modalTitle" class="modal-title">Xem video</div>
            <video id="playerVideo" controls autoplay playsinline></video>
        </div>
    </div>

    <script>
        const nextTimeIso = "{next_iso}";
        function updateCountdown() {{
            if (!nextTimeIso) return;
            const target = new Date(nextTimeIso).getTime();
            const now = new Date().getTime();
            const diff = target - now;
            const el = document.getElementById("countdown-val");
            if (diff <= 0) {{
                el.innerText = "Đang tiến hành...";
                return;
            }}
            const h = Math.floor(diff / (1000 * 60 * 60));
            const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const s = Math.floor((diff % (1000 * 60)) / 1000);
            el.innerText = String(h).padStart(2, '0') + ":" + String(m).padStart(2, '0') + ":" + String(s).padStart(2, '0');
        }}
        setInterval(updateCountdown, 1000);
        updateCountdown();

        function openPlayer(videoUrl, title) {{
            const modal = document.getElementById("videoModal");
            const video = document.getElementById("playerVideo");
            document.getElementById("modalTitle").innerText = title || "Xem Video Shorts";
            video.src = videoUrl;
            modal.classList.add("active");
            video.play();
        }}
        function closePlayer() {{
            const modal = document.getElementById("videoModal");
            const video = document.getElementById("playerVideo");
            video.pause();
            video.src = "";
            modal.classList.remove("active");
        }}
        window.onclick = function(e) {{
            const modal = document.getElementById("videoModal");
            if (e.target === modal) closePlayer();
        }}
    </script>
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

async def run_single_cycle(video_counter: int, dry_run: bool = False) -> dict:
    """Thực hiện đúng 1 chu kỳ: quét kịch bản, dựng video, và đăng bài (hoặc giả lập nếu dry_run)."""
    import auto_threads_video

    now_str = datetime.now().strftime("%H:%M - %d/%m/%Y")
    output_name = f"short_video_{video_counter}_{int(datetime.now().timestamp())}.mp4"
    output_path = PUBLISHED_DIR / output_name
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)

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
        print(f"[+] [Chu kỳ #{video_counter}] Bắt đầu quét kịch bản Threads / AI...")
        api_key = os.environ.get("GEMINI_API_KEY")
        story = None
        try:
            story = await get_automated_story(TARGET_THREADS_URLS, api_key=api_key)
        except Exception as e:
            print(f"[!] Không cào được Threads ({e}). Chuyển sang gọi trực tiếp Gemini sáng tác...")
            if api_key:
                try:
                    from threads_scraper import select_and_format_story
                    story = select_and_format_story([], api_key=api_key)
                except Exception as e2:
                    print(f"[!] Gọi Gemini gặp lỗi: {e2}")

        if not story:
            print("[+] Kích hoạt kịch bản hài hước học đường/gia đình chuẩn từ kho fallback...")
            story = auto_threads_video.SAMPLE_STORIES[(video_counter - 1) % len(auto_threads_video.SAMPLE_STORIES)]

        auto_threads_video.STORY_DATA = story
        first_line = story["cards"][0]["lines"][0]
        text_hook = first_line["text"] if isinstance(first_line, dict) else str(first_line)
        caption = f"{text_hook} #shorts #threads #haihuoc #xuhuong"

        record["title"] = text_hook[:70] + "..."
        save_status_record(record)

        temp_dir = Path("temp_current_build")
        temp_dir.mkdir(parents=True, exist_ok=True)
        print(f"[+] [Chu kỳ #{video_counter}] Đang chuẩn bị media và chụp DOM...")
        segments, wm_path = await prepare_media_assets(temp_dir)
        print(f"[+] [Chu kỳ #{video_counter}] Đang tổng hợp video với BGM và Meme...")
        build_final_video(segments, wm_path, output_file=str(output_path))
        print(f"[✓] [Chu kỳ #{video_counter}] Đã tạo video thành công tại: {output_path}")

        # Bước 2: Đăng tải (hoặc giả lập đăng nếu dry_run)
        record["overall_status"] = "🚀 Đang đăng lên 3 kênh..."
        save_status_record(record)
        await publish_all_platforms(output_path, caption, record, dry_run=dry_run)

    except Exception as e:
        print(f"[!] [Chu kỳ #{video_counter}] Lỗi xảy ra: {e}")
        record["overall_status"] = f"❌ Lỗi: {str(e)[:40]}"
        save_status_record(record)

    return record

async def run_4h_pipeline(once: bool = False, dry_run: bool = False):
    global NEXT_RUN_TIME

    # Khởi chạy Web Dashboard ở luồng phụ
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    dashboard_thread = threading.Thread(
        target=start_dashboard_server,
        kwargs={"port": port},
        daemon=True
    )
    dashboard_thread.start()

    # Khởi tạo thời gian đăng tiếp theo ngay khi bắt đầu
    NEXT_RUN_TIME = datetime.now() + timedelta(hours=INTERVAL_HOURS)

    video_counter = len(load_status_list()) + 1
    while True:
        await run_single_cycle(video_counter, dry_run=dry_run)

        if once:
            print(f"[✓] Đã hoàn thành 1 chu kỳ kiểm thử {'(Dry-Run) ' if dry_run else ''}(--once)!")
            print(f"📊 Bảng theo dõi Web Dashboard vẫn đang phục vụ tại: http://localhost:{port}")
            break

        video_counter += 1
        NEXT_RUN_TIME = datetime.now() + timedelta(hours=INTERVAL_HOURS)
        print(f"[✓] Đã xong chu kỳ! Chờ {INTERVAL_HOURS} tiếng cho video tiếp theo (lúc {NEXT_RUN_TIME.strftime('%H:%M:%S')})...")
        await asyncio.sleep(INTERVAL_HOURS * 3600)

if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    once = "--once" in sys.argv

    if "--login" in sys.argv:
        asyncio.run(login_setup())
    elif "--server-only" in sys.argv or "--dashboard-only" in sys.argv:
        port = int(os.environ.get("DASHBOARD_PORT", 8080))
        start_dashboard_server(port=port)
    elif once or dry_run:
        asyncio.run(run_4h_pipeline(once=once, dry_run=dry_run))
    else:
        asyncio.run(run_4h_pipeline())
