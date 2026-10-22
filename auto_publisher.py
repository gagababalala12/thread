import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from playwright.async_api import async_playwright

# Tự động nạp biến môi trường từ file .env nếu có
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import hàm sản xuất video từ pipeline hiện tại
from auto_threads_video import prepare_media_assets, build_final_video
from threads_scraper_ai import get_automated_story, TARGET_THREADS_URLS

STATUS_FILE = Path("publish_status.json")
PROFILE_DIR = Path("browser_profile")
PUBLISHED_DIR = Path("published_videos")
AUTH_STATE_FILE = Path("auth_state.json")
COOKIES_FILE = Path("cookies.json")
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
# 2. QUẢN LÝ PHIÊN & COOKIE ĐA NỀN TẢNG
# ==========================================
def infer_cookie_domain(cookie_name: str) -> str | None:
    """Tự động suy đoán domain dựa trên tên cookie phiên phổ biến."""
    c_lower = str(cookie_name or "").lower()
    if c_lower in ["sessionid", "sessionid_ss", "sid_tt", "ttwid", "mstoken", "passport_csrf_token", "tt_webid"]:
        return ".tiktok.com"
    if c_lower in ["login_info", "sapisid", "apisid", "ssid", "hsid", "sid", "__secure-3papisid", "__secure-1papisid", "__secure-3psid", "__secure-1psid", "__secure-ynid"]:
        return ".youtube.com"
    if c_lower in ["c_user", "xs", "fr", "datr", "sb", "presence"]:
        return ".facebook.com"
    return None

def normalize_cookie(c: dict, default_domain: str = None) -> dict | None:
    """Chuẩn hóa một cookie dict theo tiêu chuẩn Playwright BrowserContext."""
    if not isinstance(c, dict):
        return None
    name = str(c.get("name", "")).strip()
    value = str(c.get("value", ""))
    if not name:
        return None

    domain = c.get("domain") or default_domain or infer_cookie_domain(name) or ""
    if not domain and c.get("url"):
        try:
            from urllib.parse import urlparse
            domain = urlparse(str(c["url"])).hostname or ""
        except Exception:
            pass

    domain = str(domain).strip().lower()
    if "://" in domain:
        domain = domain.split("://", 1)[1]
    domain = domain.split("/")[0].split(":")[0].strip()
    if not domain:
        return None

    path = str(c.get("path") or "/").strip()
    if not path.startswith("/"):
        path = "/" + path

    same_site_raw = str(c.get("sameSite", "")).lower()
    if same_site_raw in ["strict"]:
        same_site = "Strict"
    elif same_site_raw in ["none", "no_restriction"]:
        same_site = "None"
    else:
        same_site = "Lax"

    secure = bool(c.get("secure", False))
    if same_site == "None":
        secure = True  # Chuẩn RFC: SameSite=None bắt buộc Secure=True

    cookie = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "sameSite": same_site,
        "secure": secure,
        "httpOnly": bool(c.get("httpOnly", False))
    }

    # Xử lý thời hạn expires / expirationDate
    expires = c.get("expires")
    if expires is None:
        expires = c.get("expirationDate")
    if expires is not None:
        try:
            exp_float = float(expires)
            current_time = time.time()
            if exp_float > 0:
                if exp_float <= current_time:
                    # Nếu thời hạn trong quá khứ, tăng lên 1 năm để tránh bị Chromium xóa ngay
                    exp_float = current_time + 365 * 86400
                cookie["expires"] = exp_float
        except (ValueError, TypeError):
            pass

    return cookie

def parse_cookies_input(raw_input, default_domain: str = None) -> list:
    """Phân tích dữ liệu cookies từ nhiều định dạng khác nhau:
    - Danh sách Cookie-Editor JSON / EditThisCookie
    - Playwright storage_state (dict chứa 'cookies')
    - Dict phân nhóm platform {'tiktok': [...], 'youtube': [...]}
    - Dict dạng key-value {cookie_name: cookie_val}
    - Định dạng file Netscape (tab-delimited, hỗ trợ cả #HttpOnly_)
    - Chuỗi Cookie header (k1=v1; k2=v2)
    """
    if raw_input is None:
        return []

    # Nếu truyền vào chuỗi, thử parse JSON trước
    if isinstance(raw_input, str):
        trimmed = raw_input.strip()
        if not trimmed:
            return []
        try:
            parsed_json = json.loads(trimmed)
            return parse_cookies_input(parsed_json, default_domain=default_domain)
        except Exception:
            # Không phải JSON, thử parse Netscape hoặc raw header
            lines = [l.strip() for l in trimmed.splitlines() if l.strip()]
            cookies_found = []
            is_netscape = any("\t" in l for l in lines)
            if is_netscape:
                for line in lines:
                    line = line.strip()
                    http_only = False
                    if line.startswith("#HttpOnly_"):
                        http_only = True
                        line = line[len("#HttpOnly_"):].strip()
                    elif line.startswith("#"):
                        continue
                    tokens = line.split("\t")
                    if len(tokens) >= 7:
                        c_dom = tokens[0].strip()
                        c_path = tokens[2].strip()
                        c_sec = tokens[3].strip().upper() == "TRUE"
                        c_exp = tokens[4].strip()
                        c_name = tokens[5].strip()
                        c_val = tokens[6].strip()
                        cookie_dict = {
                            "name": c_name,
                            "value": c_val,
                            "domain": c_dom,
                            "path": c_path,
                            "secure": c_sec,
                            "httpOnly": http_only
                        }
                        if c_exp.isdigit():
                            cookie_dict["expires"] = float(c_exp)
                        norm = normalize_cookie(cookie_dict, default_domain=default_domain)
                        if norm:
                            cookies_found.append(norm)
                return cookies_found

            # Thử parse header name1=val1; name2=val2
            for part in trimmed.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k:
                        cookie_dom = default_domain or infer_cookie_domain(k) or ".tiktok.com"
                        norm = normalize_cookie({"name": k, "value": v}, default_domain=cookie_dom)
                        if norm:
                            cookies_found.append(norm)
            return cookies_found

    # Nếu là dict
    if isinstance(raw_input, dict):
        if "cookies" in raw_input and isinstance(raw_input["cookies"], list):
            return parse_cookies_input(raw_input["cookies"], default_domain=default_domain)
        # Kiểm tra nếu là dict phân nhóm platform
        is_platform_grouped = any(
            k.lower() in ["tiktok", "youtube", "facebook", "google"] and isinstance(v, list)
            for k, v in raw_input.items()
        )
        if is_platform_grouped:
            all_cookies = []
            for k, v in raw_input.items():
                if isinstance(v, list):
                    platform_domain = None
                    if "tiktok" in k.lower():
                        platform_domain = ".tiktok.com"
                    elif "youtube" in k.lower() or "google" in k.lower():
                        platform_domain = ".youtube.com"
                    elif "facebook" in k.lower():
                        platform_domain = ".facebook.com"
                    all_cookies.extend(parse_cookies_input(v, default_domain=platform_domain or default_domain))
            return all_cookies
        # Dict đại diện cho 1 cookie lẻ
        if "name" in raw_input and "value" in raw_input:
            norm = normalize_cookie(raw_input, default_domain=default_domain)
            return [norm] if norm else []
        # Dict dạng key-value {name: val}
        key_val_cookies = []
        for k, v in raw_input.items():
            if isinstance(v, (str, int, float, bool)):
                cookie_dom = default_domain or infer_cookie_domain(str(k))
                norm = normalize_cookie({"name": str(k), "value": str(v)}, default_domain=cookie_dom)
                if norm:
                    key_val_cookies.append(norm)
        if key_val_cookies:
            return key_val_cookies

    # Nếu là list
    if isinstance(raw_input, list):
        result = []
        for item in raw_input:
            norm = normalize_cookie(item, default_domain=default_domain)
            if norm:
                result.append(norm)
        return result

    return []

def load_saved_cookies(target_file: Path = None) -> list:
    """Nạp tất cả cookie đã lưu từ target_file (nếu chỉ định), hoặc hợp nhất từ auth_state.json và cookies.json."""
    cookies_map = {}

    def ingest(file_path: Path):
        if file_path and file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                parsed = parse_cookies_input(content)
                for c in parsed:
                    key = (c.get("domain", "").lstrip(".").lower(), c.get("path", "/"), c.get("name", ""))
                    cookies_map[key] = c
            except Exception:
                pass

    if target_file is not None:
        ingest(target_file)
    else:
        ingest(AUTH_STATE_FILE)
        ingest(COOKIES_FILE)

    return list(cookies_map.values())

def save_cookies(cookies: list, target_file: Path = None, merge: bool = True) -> int:
    """Lưu danh sách cookie vào file định dạng Playwright storage_state (mặc định auth_state.json)."""
    _YT_VERIFY_CACHE.clear()
    is_default = (target_file is None)
    if target_file is None:
        target_file = AUTH_STATE_FILE

    normalized = parse_cookies_input(cookies)
    if merge and target_file.exists():
        existing = load_saved_cookies(target_file=target_file if not is_default else None)
        cookies_map = {}
        for c in existing:
            key = (c.get("domain", "").lstrip(".").lower(), c.get("path", "/"), c.get("name", ""))
            cookies_map[key] = c
        for c in normalized:
            key = (c.get("domain", "").lstrip(".").lower(), c.get("path", "/"), c.get("name", ""))
            cookies_map[key] = c
        final_list = list(cookies_map.values())
    else:
        final_list = normalized

    payload = {
        "cookies": final_list,
        "origins": []
    }
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _YT_VERIFY_CACHE.clear()
    return len(final_list)

def clear_cookies(platform: str = "all", target_file: Path = None) -> int:
    """Xóa cookie của một nền tảng hoặc toàn bộ khỏi target_file, cookies.json và browser_profile SQLite."""
    _YT_VERIFY_CACHE.clear()
    is_default = (target_file is None)
    if target_file is None:
        target_file = AUTH_STATE_FILE

    domain_filter = []
    if platform == "tiktok":
        domain_filter = ["tiktok.com"]
    elif platform in ["youtube", "google"]:
        domain_filter = ["youtube.com", "google.com"]
    elif platform == "facebook":
        domain_filter = ["facebook.com"]

    if platform == "all":
        payload = {"cookies": [], "origins": []}
        target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if is_default and COOKIES_FILE.exists():
            try:
                COOKIES_FILE.unlink()
            except Exception:
                pass
        remaining_cnt = 0
    else:
        all_cookies = load_saved_cookies(target_file=target_file if not is_default else None)
        remaining = [
            c for c in all_cookies
            if not any(d in c.get("domain", "").lower() for d in domain_filter)
        ]
        payload = {"cookies": remaining, "origins": []}
        target_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        # Giữ cookies.json đồng bộ khi xóa
        if is_default and COOKIES_FILE.exists():
            try:
                COOKIES_FILE.write_text(json.dumps(remaining, indent=2), encoding="utf-8")
            except Exception:
                pass
        remaining_cnt = len(remaining)

    # Dọn dẹp cả trong SQLite browser_profile/Default/Cookies nếu có để tránh cookie cũ lưu phiên hết hạn
    profile_db = PROFILE_DIR / "Default" / "Cookies"
    if profile_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(profile_db))
            cur = conn.cursor()
            if platform == "all":
                cur.execute("DELETE FROM cookies")
            elif domain_filter:
                for df in domain_filter:
                    cur.execute("DELETE FROM cookies WHERE host_key LIKE ?", (f"%{df}%",))
            conn.commit()
            conn.close()
        except Exception:
            pass

    return remaining_cnt

_YT_VERIFY_CACHE = {}

def verify_youtube_session_online(cookies: list = None, timeout: float = 4.0) -> tuple[bool | None, str]:
    """Kiểm tra trực tuyến với studio.youtube.com xem session cookie có thực sự hợp lệ không.
    Trả về (True, '...') nếu phiên hợp lệ;
    Trả về (False, '...') nếu bị chuyển hướng sang trang đăng nhập Google;
    Trả về (None, '...') nếu có lỗi mạng hoặc timeout.
    """
    if cookies is None:
        cookies = load_saved_cookies()

    yt_cookies = [c for c in cookies if isinstance(c, dict) and any(d in c.get("domain", "").lower() for d in ["youtube.com", "google.com"])]
    cookie_hdr = "; ".join([f"{c['name']}={c['value']}" for c in yt_cookies if c.get("name") and c.get("value")])
    if not cookie_hdr:
        return False, "Chưa có cookie YouTube"

    cache_key = hash(cookie_hdr)
    now = time.time()
    if cache_key in _YT_VERIFY_CACHE:
        cached_time, cached_res, cached_msg = _YT_VERIFY_CACHE[cache_key]
        if now - cached_time < 60:
            return cached_res, cached_msg

    import urllib.request
    import urllib.error

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request("https://studio.youtube.com", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie_hdr
    })
    try:
        resp = opener.open(req, timeout=timeout)
        res = (True, "Đã xác thực Studio trực tiếp")
    except urllib.error.HTTPError as e:
        loc = str(e.headers.get("Location") or "").lower()
        if any(kw in loc for kw in ["accounts.google.com", "servicelogin", "signin", "/login"]):
            res = (False, "Cookie YouTube hết hạn hoặc chưa đăng nhập")
        elif "studio.youtube.com" in loc:
            res = (True, "Đã xác thực Studio")
        else:
            res = (False, f"Chuyển hướng ({e.code})")
    except Exception as e:
        res = (None, f"Không kiểm tra được kết nối ({e})")

    _YT_VERIFY_CACHE[cache_key] = (now, res[0], res[1])
    return res

def check_auth_status(cookies: list = None, verify_live: bool = False) -> dict:
    """Kiểm tra trạng thái xác thực của cả 3 nền tảng: YouTube, TikTok, Facebook."""
    if cookies is not None:
        combined = list(cookies)
    else:
        saved = load_saved_cookies()
        profile_db = PROFILE_DIR / "Default" / "Cookies"
        extra_cookies = []
        if profile_db.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(profile_db))
                cur = conn.cursor()
                cur.execute("SELECT host_key, name FROM cookies")
                for h, n in cur.fetchall():
                    extra_cookies.append({"domain": h, "name": n})
                conn.close()
            except Exception:
                pass
        combined = list(saved) + extra_cookies

    # 1. TikTok
    tt_cookies = [c for c in combined if "tiktok.com" in c.get("domain", "").lower()]
    tt_names = {c.get("name") for c in tt_cookies}
    tt_auth = any(k in tt_names for k in ["sessionid", "sessionid_ss", "sid_tt"])
    if tt_auth:
        tt_details = f"Đã đăng nhập ({len(tt_cookies)} cookies, sessionid hợp lệ)"
    elif tt_cookies:
        tt_details = f"Chưa đăng nhập ({len(tt_cookies)} cookies, thiếu sessionid)"
    else:
        tt_details = "Chưa có cookie"

    # 2. YouTube
    yt_cookies = [c for c in combined if any(d in c.get("domain", "").lower() for d in ["youtube.com", "google.com"])]
    yt_names = {c.get("name") for c in yt_cookies}
    yt_auth_keys = [k for k in ["LOGIN_INFO", "SID", "SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID", "__Secure-3PSID"] if k in yt_names]
    has_auth_key = len(yt_auth_keys) > 0

    if not yt_cookies:
        yt_auth = False
        yt_details = "Chưa có cookie"
    elif not has_auth_key:
        yt_auth = False
        yt_details = f"Chưa đăng nhập ({len(yt_cookies)} cookies, thiếu LOGIN_INFO / SID)"
    else:
        if verify_live:
            is_valid, msg = verify_youtube_session_online(yt_cookies)
            if is_valid is True:
                yt_auth = True
                yt_details = f"Đã đăng nhập ({len(yt_cookies)} cookies, {msg})"
            elif is_valid is False:
                yt_auth = False
                yt_details = f"Phiên hết hạn ({msg})"
            else:
                yt_auth = True
                yt_details = f"Đã có cookie xác thực ({len(yt_cookies)} cookies, {msg})"
        else:
            cookie_hdr = "; ".join([f"{c['name']}={c.get('value','')}" for c in yt_cookies if c.get("name") and c.get("value")])
            cache_key = hash(cookie_hdr)
            cached = _YT_VERIFY_CACHE.get(cache_key)
            if cached and (time.time() - cached[0] < 60):
                if cached[1] is False:
                    yt_auth = False
                    yt_details = f"Phiên hết hạn ({cached[2]})"
                else:
                    yt_auth = True
                    yt_details = f"Đã đăng nhập ({len(yt_cookies)} cookies, {cached[2]})"
            else:
                yt_auth = True
                yt_details = f"Đã đăng nhập ({len(yt_cookies)} cookies, có xác thực Studio)"

    # 3. Facebook
    fb_cookies = [c for c in combined if "facebook.com" in c.get("domain", "").lower()]
    fb_names = {c.get("name") for c in fb_cookies}
    fb_auth = "c_user" in fb_names
    c_user_val = next((c.get("value") for c in combined if c.get("name") == "c_user"), None)
    if fb_auth:
        uid_str = f"UID: {c_user_val}" if c_user_val else "c_user hợp lệ"
        fb_details = f"Đã đăng nhập ({uid_str}, {len(fb_cookies)} cookies)"
    elif fb_cookies:
        fb_details = f"Chưa đăng nhập ({len(fb_cookies)} cookies, thiếu c_user)"
    else:
        fb_details = "Chưa có cookie"

    all_auth = tt_auth and yt_auth and fb_auth
    ready_count = sum([1 if tt_auth else 0, 1 if yt_auth else 0, 1 if fb_auth else 0])

    return {
        "all_authenticated": all_auth,
        "ready_count": ready_count,
        "total_platforms": 3,
        "platforms": {
            "youtube": {
                "name": "YouTube Studio",
                "authenticated": yt_auth,
                "details": yt_details,
                "count": len(yt_cookies),
                "url": "https://studio.youtube.com"
            },
            "tiktok": {
                "name": "TikTok Studio",
                "authenticated": tt_auth,
                "details": tt_details,
                "count": len(tt_cookies),
                "url": "https://www.tiktok.com/tiktokstudio/upload" if tt_auth else "https://www.tiktok.com/login"
            },
            "facebook": {
                "name": "Facebook Reels",
                "authenticated": fb_auth,
                "details": fb_details,
                "count": len(fb_cookies),
                "url": "https://www.facebook.com/reels/create" if fb_auth else "https://www.facebook.com/login"
            }
        }
    }

def launch_windows_browser(url: str) -> bool:
    """Mở URL trên trình duyệt mặc định của Windows host từ môi trường WSL2/Linux."""
    # 1. Thử wslview nếu có
    if shutil.which("wslview"):
        try:
            subprocess.Popen(["wslview", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass

    # 2. Thử cmd.exe /c start "" "<url>"
    for cmd in ["cmd.exe", "/mnt/c/Windows/system32/cmd.exe"]:
        if shutil.which(cmd) or os.path.exists(cmd):
            try:
                subprocess.Popen([cmd, "/c", "start", "", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass

    # 3. Thử powershell.exe Start-Process
    for ps in ["powershell.exe", "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"]:
        if shutil.which(ps) or os.path.exists(ps):
            try:
                subprocess.Popen([ps, "-NoProfile", "-Command", f"Start-Process '{url}'"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass

    # 4. Fallback explorer.exe
    for exp in ["explorer.exe", "/mnt/c/Windows/explorer.exe"]:
        if shutil.which(exp) or os.path.exists(exp):
            try:
                subprocess.Popen([exp, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass

    return False

def deploy_windows_desktop_helper(port: int = 8080) -> str | None:
    """Tự động tạo file AutoPublisher_Login.bat trên Windows Desktop nếu tìm thấy thư mục Desktop."""
    bat_content = f"""@echo off
chcp 65001 >nul
title Auto-Publisher - Tro Ly Dang Nhap Trinh Duyet Windows

echo ======================================================================
echo   🚀 TRỢ LÝ ĐĂNG NHẬP TRÌNH DUYỆT WINDOWS CHO AUTO-PUBLISHER
echo ======================================================================
echo.
echo Đang mở trình duyệt Windows để bạn đăng nhập TikTok, YouTube, Facebook...
echo.

start "" "https://www.tiktok.com/login"
start "" "https://studio.youtube.com"
start "" "https://www.facebook.com"
start "" "http://localhost:{port}#accounts"

echo [✓] Đã mở các tab đăng nhập và trang Web Dashboard!
echo.
echo ======================================================================
echo 👉 HƯỚNG DẪN 4 BƯỚC ĐỂ LƯU PHIÊN:
echo 1. Đăng nhập tài khoản trên các tab trình duyệt vừa mở.
echo 2. Cài tiện ích 'Cookie-Editor' trên Cốc Cốc, Chrome, hoặc Edge.
echo 3. Trên mỗi trang đã đăng nhập, bấm Cookie-Editor -^> Export as JSON.
echo 4. Chuyển sang tab Dashboard (http://localhost:{port}#accounts):
echo    Dán mã JSON vừa copy vào khung và bấm nút 'Lưu Cookie'.
echo ======================================================================
echo.
pause
"""
    users_dir = Path("/mnt/c/Users")
    if users_dir.exists():
        for user_folder in users_dir.iterdir():
            if user_folder.is_dir() and user_folder.name not in ["Public", "Default", "Default User", "All Users"]:
                desktop = user_folder / "Desktop"
                if desktop.exists() and desktop.is_dir():
                    target = desktop / "AutoPublisher_Login.bat"
                    try:
                        target.write_text(bat_content, encoding="utf-8")
                        return str(target)
                    except Exception:
                        pass
    return None

async def safe_add_cookies(context, cookies: list) -> int:
    """Nạp cookies vào context một cách an toàn, tránh để 1 cookie lỗi làm hủy bỏ toàn bộ phiên."""
    if not cookies:
        return 0
    try:
        await context.add_cookies(cookies)
        return len(cookies)
    except Exception as batch_err:
        print(f"[!] Cảnh báo nạp cookie mảng ({batch_err}), tự động nạp từng cookie...")
        success = 0
        for c in cookies:
            try:
                await context.add_cookies([c])
                success += 1
            except Exception:
                pass
        print(f"[✓] Đã nạp an toàn {success}/{len(cookies)} cookies vào context.")
        return success

async def dismiss_tiktok_modals(page):
    """Đóng các pop-up, modal hướng dẫn hoặc overlay của TikTok Studio nếu xuất hiện."""
    try:
        res = page.keyboard.press("Escape")
        if asyncio.iscoroutine(res):
            await res
    except Exception:
        pass

    modal_selectors = [
        'button:has-text("Đã hiểu")',
        'button:has-text("Got it")',
        'button:has-text("Bỏ qua")',
        'button:has-text("Skip")',
        'button:has-text("Đóng")',
        'button:has-text("Close")',
        'button[aria-label="Close"]',
        'button[aria-label="Đóng"]',
        '.TUXModal-close',
        '.common-modal-close',
        '[data-tid="modal-close-btn"]',
    ]
    for sel in modal_selectors:
        try:
            btns = page.locator(sel)
            cnt = btns.count()
            if asyncio.iscoroutine(cnt):
                cnt = await cnt
            if isinstance(cnt, int) and cnt > 0:
                for i in range(min(cnt, 3)):
                    btn = btns.nth(i) if hasattr(btns, "nth") else btns
                    vis = btn.is_visible() if hasattr(btn, "is_visible") else True
                    if asyncio.iscoroutine(vis):
                        vis = await vis
                    if vis:
                        cl = btn.click(force=True, timeout=1000)
                        if asyncio.iscoroutine(cl):
                            await cl
                        await asyncio.sleep(0.3)
        except Exception:
            pass

    try:
        overlays = page.locator('.TUXModal-overlay, .modal-mask, .common-modal-mask')
        if hasattr(overlays, "evaluate_all"):
            rem = overlays.evaluate_all('els => els.forEach(el => el.remove())')
            if asyncio.iscoroutine(rem):
                await rem
    except Exception:
        pass

async def dismiss_youtube_modals(page):
    """Đóng các pop-up, modal hướng dẫn, điều khoản hoặc tạo kênh của YouTube Studio nếu xuất hiện."""
    try:
        res = page.keyboard.press("Escape")
        if asyncio.iscoroutine(res):
            await res
    except Exception:
        pass

    # 1. Hộp thoại tạo kênh mới nếu tài khoản chưa có kênh
    try:
        chan_dlg = page.locator('ytcp-channel-creation-dialog')
        cnt = chan_dlg.count()
        if asyncio.iscoroutine(cnt):
            cnt = await cnt
        if isinstance(cnt, int) and cnt > 0:
            create_chan_btn = chan_dlg.locator('ytcp-button:has-text("Tạo kênh"), ytcp-button:has-text("Create channel"), #create-channel-button').first
            c_cnt = create_chan_btn.count()
            if asyncio.iscoroutine(c_cnt):
                c_cnt = await c_cnt
            if isinstance(c_cnt, int) and c_cnt > 0:
                print("[YouTube] Phát hiện hộp thoại tạo kênh, đang tự động bấm xác nhận...")
                cl = create_chan_btn.click(force=True, timeout=3000)
                if asyncio.iscoroutine(cl):
                    await cl
                await asyncio.sleep(2)
    except Exception:
        pass

    # 2. Các pop-up chào mừng, tour, hướng dẫn hoặc điều khoản
    modal_selectors = [
        'ytcp-dialog #dismiss-button',
        'ytcp-dialog ytcp-button:has-text("Đóng")',
        'ytcp-dialog ytcp-button:has-text("Close")',
        'ytcp-dialog ytcp-button:has-text("Tôi hiểu")',
        'ytcp-dialog ytcp-button:has-text("Got it")',
        'ytcp-dialog ytcp-button:has-text("Bỏ qua")',
        'ytcp-dialog ytcp-button:has-text("Dismiss")',
        'ytcp-dialog ytcp-button:has-text("Tiếp tục")',
        'ytcp-dialog ytcp-button:has-text("Continue")',
        'tp-yt-paper-dialog #dismiss-button',
        'tp-yt-paper-dialog ytcp-button:has-text("Đóng")',
        'tp-yt-paper-dialog ytcp-button:has-text("Close")',
        'ytcp-feature-discovery-callout #dismiss-button',
    ]
    for sel in modal_selectors:
        try:
            btns = page.locator(sel)
            cnt = btns.count()
            if asyncio.iscoroutine(cnt):
                cnt = await cnt
            if isinstance(cnt, int) and cnt > 0:
                for i in range(min(cnt, 2)):
                    btn = btns.nth(i) if hasattr(btns, "nth") else btns
                    vis = btn.is_visible() if hasattr(btn, "is_visible") else True
                    if asyncio.iscoroutine(vis):
                        vis = await vis
                    if vis:
                        cl = btn.click(force=True, timeout=1000)
                        if asyncio.iscoroutine(cl):
                            await cl
                        await asyncio.sleep(0.3)
        except Exception:
            pass

    # 3. Gỡ bỏ overlay backdrop nếu còn che màn hình
    try:
        backdrops = page.locator('tp-yt-iron-overlay-backdrop.opened, ytcp-dialog-backdrop')
        if hasattr(backdrops, "evaluate_all"):
            rem = backdrops.evaluate_all('els => els.forEach(el => el.remove())')
            if asyncio.iscoroutine(rem):
                await rem
    except Exception:
        pass

# ==========================================
# 2.5. TỐI ƯU TIÊU ĐỀ & HASHTAG CHO REELS / SHORTS / TIKTOK
# ==========================================
VIRAL_HASHTAGS = "#shorts #reels #tiktok #haihuoc #xuhuong #chuyenvuithoret #drama #giaitri #cuoivolua #trending #viral #fyp"

def _clean_story_lines(story: dict) -> list:
    """Trích xuất danh sách các câu thoại sạch từ story."""
    lines = []
    if not isinstance(story, dict):
        return lines
    for card in story.get("cards", []):
        raw_lines = card.get("lines", []) if isinstance(card, dict) else getattr(card, "lines", [])
        for l in raw_lines:
            txt = l.get("text", "") if isinstance(l, dict) else getattr(l, "text", str(l))
            if txt and str(txt).strip():
                lines.append(str(txt).strip())

    if not lines:
        for fallback_k in ["content", "text", "body", "description", "script"]:
            val = story.get(fallback_k)
            if val and isinstance(val, str):
                lines = [s.strip() for s in val.splitlines() if s.strip()]
                break
    return lines

def _generate_offline_caption(story: dict) -> dict:
    """Tạo tiêu đề và caption dự phòng chất lượng cao khi không có kết nối Gemini API."""
    if not isinstance(story, dict):
        story = {}
    import re
    raw_title = str(story.get("title", "") or "").strip()
    if "#" in raw_title:
        raw_title = re.sub(r'#\S+', '', raw_title).strip()
        raw_title = re.sub(r'\s+', ' ', raw_title).strip()

    lines = _clean_story_lines(story)
    first_line = lines[0] if lines else ""
    full_text = " ".join(lines)
    text_lower = full_text.lower()

    is_generic_title = (
        not raw_title
        or raw_title in ["Kịch bản viral", "Story", "Kịch bản mẫu", "Kịch bản hài hước"]
        or raw_title.lower().startswith("hôm nay tôi quyết định")
        or raw_title.lower().startswith("hôm nay em ")
        or raw_title.lower().startswith("hôm nay mình ")
    )
    if not is_generic_title:
        title = raw_title
    else:
        if any(w in text_lower for w in ["người tốt", "nhường ghế", "xe buýt"]):
            title = "Cái kết đắng khi thử làm người tốt"
        elif any(w in text_lower for w in ["salon", "kiểu tóc", "cắt tóc", "thợ tóc"]):
            title = "Bài học nhớ đời khi đi đổi kiểu tóc"
        elif any(w in text_lower for w in ["giảm cân", "chạy bộ", "huấn luyện viên", "khóa học"]):
            title = "Cú lừa ngoạn mục từ khóa học giảm cân"
        elif any(w in text_lower for w in ["tarot", "bói", "thầy bói"]):
            title = "Cái kết hài hước khi đi xem bói Tarot"
        elif any(w in text_lower for w in ["tập gym", "thể hình", "tập thể dục"]):
            title = "Bài học nhớ đời khi đi tập thể hình"
        elif any(w in text_lower for w in ["phỏng vấn", "xin việc", "nhân sự", "cv"]):
            title = "Pha phỏng vấn xin việc bất ổn nhất năm"
        elif any(w in text_lower for w in ["cầu hôn", "nhà hàng sang trọng", "người yêu"]):
            title = "Màn cầu hôn bất ổn không nhịn được cười"
        elif any(w in text_lower for w in ["rửa bát", "bài văn", "người hùng", "tiểu minh"]):
            title = "Cú twist khó đỡ trong bài văn tả bố"
        elif any(w in text_lower for w in ["nỏ thần", "an dương vương", "lịch sử"]):
            title = "Ai đã lấy cắp nỏ thần của An Dương Vương"
        elif any(w in text_lower for w in ["điểm mười", "kiểm tra toán", "thưởng nóng"]):
            title = "Cái kết của bài kiểm tra Toán điểm mười"
        elif any(w in text_lower for w in ["chó cảnh", "mua chó", "thú cưng", "nuôi chó", "tiếng sủa"]):
            title = "Cái kết bất ngờ khi mua chó cảnh"
        elif any(w in text_lower for w in ["mèo", "nuôi mèo", "mèo hoang", "hoàng thượng"]):
            title = "Pha nuôi mèo bất ổn nhất hệ mặt trời"
        elif first_line.lower().startswith("hôm nay tôi quyết định "):
            core = first_line[len("hôm nay tôi quyết định "):].strip().rstrip(".")
            title = f"Cái kết bất ngờ khi {core}"
        elif first_line:
            title = f"Cú twist khó đỡ: {first_line[:35]}..."
        else:
            title = "Mẩu chuyện cười ngắn siêu hài hước"

    if "#" in title:
        title = re.sub(r'#\S+', '', title).strip()
        title = re.sub(r'\s+', ' ', title).strip()
    if len(title) > 60:
        truncated = title[:57].rstrip()
        if " " in truncated:
            title = truncated.rsplit(" ", 1)[0] + "..."
        else:
            title = truncated + "..."

    if first_line:
        hook = f"{first_line} Xem đến cuối để thấy cú twist cười bể bụng 🤣"
    else:
        hook = "Cú twist cười ra nước mắt, xem đến cuối không nhịn được cười! 🤣"

    hashtags = VIRAL_HASHTAGS
    full_caption = f"{title} 🤣\n\n{hook}\n\n{hashtags}"
    yt_title = f"{title[:85].strip()} #Shorts"
    tiktok_caption = f"{title} | {hook} {hashtags}"
    fb_caption = f"{title}\n\n{hook}\n\n{hashtags}"

    return {
        "title": title,
        "hook": hook,
        "hashtags": hashtags,
        "caption": full_caption,
        "youtube_title": yt_title,
        "tiktok_caption": tiktok_caption,
        "facebook_caption": fb_caption,
    }

def generate_reel_caption(story: dict, api_key: str | None = None) -> dict:
    """Tạo tiêu đề viral rõ ràng (dưới 60 ký tự, không chứa hashtag) và caption phong phú kèm hashtag cho Reels/Shorts/TikTok.
    Ưu tiên gọi Gemini AI để sáng tạo tiêu đề & hook giật tít, tự động fallback sang bộ tạo tiêu đề offline nếu không có API key.
    """
    if not isinstance(story, dict):
        return _generate_offline_caption(story)

    resolved_api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not resolved_api_key or resolved_api_key == "invalid_dummy_key":
        return _generate_offline_caption(story)

    lines = _clean_story_lines(story)
    raw_title = str(story.get("title", "") or "").strip()
    story_summary = "\n".join(lines) if lines else raw_title

    if not story_summary:
        return _generate_offline_caption(story)

    try:
        from google import genai
        from google.genai import types
        from pydantic import BaseModel, Field

        class ReelMeta(BaseModel):
            title: str = Field(description="Tiêu đề video ngắn hấp dẫn, tò mò, hài hước, dưới 60 ký tự, tiếng Việt đầy đủ dấu, không chứa hashtag")
            hook: str = Field(description="1-2 câu hook mở đầu dẫn dắt người xem vào video")

        client = genai.Client(api_key=resolved_api_key, http_options=types.HttpOptions(timeout=25000))
        prompt = f"""Bạn là chuyên gia sáng tạo nội dung mạng xã hội triệu view (Facebook Reels, TikTok, YouTube Shorts).
Hãy viết tiêu đề và câu hook viral cho mẩu chuyện cười sau:
\"\"\"{story_summary}\"\"\"

Yêu cầu:
1. title: Tiêu đề cực kỳ cuốn hút, giật tít hài hước hoặc tò mò (ví dụ: "Bí quyết nhịn cười khi...", "Cái kết đắng khi thử làm người tốt...", "Bài học nhớ đời khi đi đổi kiểu tóc...", "Khóa học giảm cân bất ổn nhất năm"), TUYỆT ĐỐI dưới 60 ký tự, tiếng Việt chuẩn có dấu UTF-8, KHÔNG chứa hashtag trong title.
2. hook: 1-2 câu mở đầu kích thích người xem xem đến hết video."""

        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        resp = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReelMeta,
                temperature=0.7,
            )
        )

        meta_data = None
        if hasattr(resp, "parsed") and resp.parsed is not None:
            if isinstance(resp.parsed, ReelMeta):
                meta_data = resp.parsed.model_dump()
            elif isinstance(resp.parsed, dict):
                meta_data = resp.parsed
        if not meta_data and getattr(resp, "text", None):
            meta_data = json.loads(resp.text)

        if meta_data and meta_data.get("title"):
            import re
            title = str(meta_data["title"]).strip()
            title = re.sub(r'#\S+', '', title).strip()
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 60:
                truncated = title[:57].rstrip()
                if " " in truncated:
                    title = truncated.rsplit(" ", 1)[0] + "..."
                else:
                    title = truncated + "..."
            hook = str(meta_data.get("hook", "")).strip() or (lines[0] if lines else "")
            hashtags = VIRAL_HASHTAGS
            full_caption = f"{title} 🤣\n\n{hook}\n\n{hashtags}"
            yt_title = f"{title[:85].strip()} #Shorts"
            return {
                "title": title,
                "hook": hook,
                "hashtags": hashtags,
                "caption": full_caption,
                "youtube_title": yt_title,
                "tiktok_caption": f"{title} | {hook} {hashtags}",
                "facebook_caption": f"{title}\n\n{hook}\n\n{hashtags}",
            }
    except Exception as e:
        print(f"[!] Gọi Gemini tối ưu tiêu đề gặp lỗi ({e}), chuyển sang bộ tạo tiêu đề offline...")

    return _generate_offline_caption(story)

# ==========================================
# 3. TỰ ĐỘNG ĐĂNG BÀI ĐA NỀN TẢNG (PLAYWRIGHT)
# ==========================================
async def upload_to_tiktok(page, video_path: Path, caption: str) -> str:
    try:
        print("[TikTok] Đang truy cập TikTok Studio Upload...")
        await page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(6)

        # Kiểm tra xem có bị chuyển về trang login không
        if "login" in page.url.lower():
            return "❌ Lỗi (Cookie hết hạn hoặc chưa đăng nhập)"

        # Tìm thẻ input[type="file"] (trên page hoặc iframe)
        file_input = page.locator('input[type="file"]').first
        try:
            await file_input.wait_for(timeout=15000)
        except Exception:
            for frame in page.frames:
                f_input = frame.locator('input[type="file"]').first
                cnt = f_input.count()
                if asyncio.iscoroutine(cnt):
                    cnt = await cnt
                if cnt > 0:
                    file_input = f_input
                    break

        await file_input.set_input_files(str(video_path.resolve()))
        print("[TikTok] Đã nạp file video, đang chờ xử lý...")
        await asyncio.sleep(12)

        # Điền caption
        await dismiss_tiktok_modals(page)
        caption_box = page.locator('div[contenteditable="true"], textarea').first
        cap_count = caption_box.count()
        if asyncio.iscoroutine(cap_count):
            cap_count = await cap_count
        if cap_count > 0:
            try:
                cl = caption_box.click(force=True, timeout=5000)
                if asyncio.iscoroutine(cl):
                    await cl
            except Exception:
                try:
                    foc = caption_box.evaluate('el => el.focus()')
                    if asyncio.iscoroutine(foc):
                        await foc
                except Exception:
                    pass
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await page.keyboard.type(caption, delay=20)
            print("[TikTok] Đã nhập caption thành công.")

        await asyncio.sleep(3)
        # Chờ nút Đăng (Post) sẵn sàng
        post_btn = page.locator('button:has-text("Đăng"), button:has-text("Post")').last
        post_ready = False
        for i in range(25):
            await dismiss_tiktok_modals(page)
            p_cnt = post_btn.count()
            if asyncio.iscoroutine(p_cnt):
                p_cnt = await p_cnt
            if p_cnt > 0:
                try:
                    en = post_btn.is_enabled()
                    if asyncio.iscoroutine(en):
                        en = await en
                except Exception:
                    en = True
                if en:
                    post_ready = True
                    break
            await asyncio.sleep(2)
            if (i + 1) % 5 == 0:
                print(f"[TikTok] Đang đợi upload hoàn tất và nút Đăng sẵn sàng... ({(i + 1) * 2}s)")

        p_cnt_final = post_btn.count()
        if asyncio.iscoroutine(p_cnt_final):
            p_cnt_final = await p_cnt_final

        if post_ready or p_cnt_final > 0:
            try:
                cl = post_btn.click(force=True, timeout=5000)
                if asyncio.iscoroutine(cl):
                    await cl
            except Exception:
                try:
                    eval_cl = post_btn.evaluate('el => el.click()')
                    if asyncio.iscoroutine(eval_cl):
                        await eval_cl
                except Exception:
                    pass
            print("[TikTok] Đã bấm nút Đăng video!")
            await asyncio.sleep(8)
            await dismiss_tiktok_modals(page)
            return "✅ Đã đăng"
        else:
            return "❌ Lỗi (Không tìm thấy nút Đăng)"
    except Exception as e:
        print(f"[!] Lỗi đăng TikTok: {e}")
        return f"❌ Lỗi ({str(e)[:30]}...)"

async def upload_to_youtube_shorts(page, video_path: Path, title: str) -> str:
    try:
        # 1. Kiểm tra nhanh cookie YouTube trong phiên trình duyệt
        try:
            if hasattr(page, "context") and hasattr(page.context, "cookies"):
                c_fn = page.context.cookies()
                ctx_cookies = await c_fn if asyncio.iscoroutine(c_fn) else c_fn
                if isinstance(ctx_cookies, list):
                    yt_c = [c for c in ctx_cookies if isinstance(c, dict) and any(d in c.get("domain", "").lower() for d in ["youtube.com", "google.com"])]
                    has_auth = any(c.get("name") in ["LOGIN_INFO", "SID", "SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID", "__Secure-3PSID"] for c in yt_c)
                    if not yt_c or not has_auth:
                        print("[!] Không tìm thấy cookie xác thực YouTube trong phiên trình duyệt.")
                        return "⏭️ Bỏ qua (Chưa có cookie YouTube)"
        except Exception:
            pass

        print("[YouTube] Đang truy cập YouTube Studio...")
        await page.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # 2. Kiểm tra nếu bị chuyển hướng sang trang đăng nhập Google hoặc Studio yêu cầu đăng nhập
        try:
            url_str = page.url() if callable(getattr(page, "url", None)) else str(getattr(page, "url", "") or "")
            url_lower = url_str.lower()
            if any(kw in url_lower for kw in ["accounts.google.com", "servicelogin", "service_login", "signin", "/login"]):
                print(f"[!] YouTube Studio chuyển hướng đến trang đăng nhập ({url_str}). Cookie YouTube đã hết hạn hoặc chưa đăng nhập.")
                return "❌ Lỗi (Cookie YouTube hết hạn hoặc chưa đăng nhập)"
        except Exception:
            pass

        # 3. Đóng các pop-up, modal tạo kênh, tour hoặc điều khoản nếu có
        await dismiss_youtube_modals(page)

        # 4. Bấm nút Tạo (Create) -> Tải video lên với selector kiên cố và force click fallback
        create_btn = page.locator('#create-icon, ytcp-button#create-icon, ytcp-button:has-text("Tạo"), ytcp-button:has-text("Create"), ytcp-button[aria-label*="Tạo"], ytcp-button[aria-label*="Create"], #upload-icon, #upload-button, ytcp-button#upload-button').first
        try:
            c_cnt = create_btn.count()
            if asyncio.iscoroutine(c_cnt):
                c_cnt = await c_cnt
            if isinstance(c_cnt, int) and c_cnt > 0:
                try:
                    cl = create_btn.click(force=True, timeout=10000)
                    if asyncio.iscoroutine(cl):
                        await cl
                except Exception:
                    eval_cl = create_btn.evaluate("el => el.click()")
                    if asyncio.iscoroutine(eval_cl):
                        await eval_cl
            else:
                cl = create_btn.click(force=True, timeout=10000)
                if asyncio.iscoroutine(cl):
                    await cl
        except Exception as e:
            # Nếu không tìm thấy nút Tạo, kiểm tra xem có đang ở trang login không
            url_str = page.url() if callable(getattr(page, "url", None)) else str(getattr(page, "url", "") or "")
            if any(kw in url_str.lower() for kw in ["accounts.google.com", "signin"]):
                return "❌ Lỗi (Cookie YouTube hết hạn hoặc chưa đăng nhập)"
            raise e

        await asyncio.sleep(2)

        # 5. Bấm mục "Tải video lên" trong dropdown menu nếu modal upload chưa mở
        upload_modal = page.locator('ytcp-uploads-dialog, #dialog[aria-label*="Tải video"], #dialog[aria-label*="Upload"]')
        is_modal_open = False
        try:
            m_cnt = upload_modal.count()
            if asyncio.iscoroutine(m_cnt):
                m_cnt = await m_cnt
            if isinstance(m_cnt, int) and m_cnt > 0:
                is_modal_open = True
        except Exception:
            pass

        if not is_modal_open:
            upload_item = page.locator('tp-yt-paper-item:has-text("Tải video lên"), tp-yt-paper-item:has-text("Upload videos"), tp-yt-paper-item:has-text("Upload video"), #text-item-0').first
            try:
                u_cnt = upload_item.count()
                if asyncio.iscoroutine(u_cnt):
                    u_cnt = await u_cnt
                if isinstance(u_cnt, int) and u_cnt > 0:
                    try:
                        cl = upload_item.click(force=True, timeout=8000)
                        if asyncio.iscoroutine(cl):
                            await cl
                    except Exception:
                        eval_cl = upload_item.evaluate("el => el.click()")
                        if asyncio.iscoroutine(eval_cl):
                            await eval_cl
                else:
                    cl = upload_item.click(force=True, timeout=8000)
                    if asyncio.iscoroutine(cl):
                        await cl
            except Exception:
                pass
            await asyncio.sleep(2)

        # 6. Chọn file video tải lên
        file_input = page.locator('input[type="file"]').first
        try:
            if hasattr(page, "wait_for_selector"):
                w = page.wait_for_selector('input[type="file"]', timeout=15000)
                if asyncio.iscoroutine(w):
                    await w
        except Exception:
            pass

        set_files = file_input.set_input_files(str(video_path.resolve()))
        if asyncio.iscoroutine(set_files):
            await set_files
        await asyncio.sleep(10)

        # 7. Điền tiêu đề kèm #Shorts (chuẩn hóa độ dài <= 95 ký tự)
        clean_yt_title = str(title or "").strip()
        if "#shorts" not in clean_yt_title.lower():
            clean_yt_title = f"{clean_yt_title[:85].strip()} #Shorts"
        else:
            clean_yt_title = clean_yt_title[:95].strip()

        title_box = page.locator('#title-textarea #textbox, #textbox[aria-label*="tiêu đề"], #textbox[aria-label*="title"], ytcp-social-suggestions-textbox #textbox, #textbox').first
        try:
            t_cnt = title_box.count()
            if asyncio.iscoroutine(t_cnt):
                t_cnt = await t_cnt
            if not isinstance(t_cnt, int) or t_cnt > 0:
                try:
                    cl = title_box.click(force=True)
                    if asyncio.iscoroutine(cl):
                        await cl
                except Exception:
                    pass
                p1 = page.keyboard.press("Control+A")
                if asyncio.iscoroutine(p1):
                    await p1
                p2 = page.keyboard.press("Backspace")
                if asyncio.iscoroutine(p2):
                    await p2
                tp = page.keyboard.type(clean_yt_title, delay=20)
                if asyncio.iscoroutine(tp):
                    await tp
        except Exception:
            pass

        # 8. Chọn "Không, nội dung này không dành cho trẻ em"
        not_for_kids = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"], tp-yt-paper-radio-button:has-text("Không, nội dung này không dành cho trẻ em"), tp-yt-paper-radio-button:has-text("No, it\'s not made for kids")').first
        try:
            k_cnt = not_for_kids.count()
            if asyncio.iscoroutine(k_cnt):
                k_cnt = await k_cnt
            if not isinstance(k_cnt, int) or k_cnt > 0:
                if hasattr(not_for_kids, "scroll_into_view_if_needed"):
                    s = not_for_kids.scroll_into_view_if_needed()
                    if asyncio.iscoroutine(s):
                        await s
                cl = not_for_kids.click(force=True)
                if asyncio.iscoroutine(cl):
                    await cl
        except Exception:
            pass

        # 9. Nhấn Tiếp (Next) cho đến khi sang bước Công khai (tối đa 4 lần)
        public_radio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"], tp-yt-paper-radio-button:has-text("Công khai"), tp-yt-paper-radio-button:has-text("Public")').first
        for _ in range(4):
            pub_cnt = public_radio.count()
            if asyncio.iscoroutine(pub_cnt):
                pub_cnt = await pub_cnt
            if isinstance(pub_cnt, int) and pub_cnt > 0:
                pub_vis = public_radio.is_visible()
                if asyncio.iscoroutine(pub_vis):
                    pub_vis = await pub_vis
                if pub_vis:
                    break

            next_btn = page.locator('#next-button, ytcp-button#next-button, ytcp-button:has-text("Tiếp"), ytcp-button:has-text("Next")').first
            n_cnt = next_btn.count()
            if asyncio.iscoroutine(n_cnt):
                n_cnt = await n_cnt
            if not isinstance(n_cnt, int) or n_cnt > 0:
                try:
                    cl = next_btn.click(force=True)
                    if asyncio.iscoroutine(cl):
                        await cl
                except Exception:
                    pass
                await asyncio.sleep(2)

        # 10. Chọn Công khai (Public) và nhấn Xuất bản
        try:
            cl = public_radio.click(force=True)
            if asyncio.iscoroutine(cl):
                await cl
        except Exception:
            pass
        await asyncio.sleep(2)

        done_btn = page.locator('#done-button, ytcp-button#done-button, ytcp-button:has-text("Xuất bản"), ytcp-button:has-text("Publish"), ytcp-button:has-text("Lưu"), ytcp-button:has-text("Save")').first
        d_cnt = done_btn.count()
        if asyncio.iscoroutine(d_cnt):
            d_cnt = await d_cnt
        if not isinstance(d_cnt, int) or d_cnt > 0:
            try:
                cl = done_btn.click(force=True)
                if asyncio.iscoroutine(cl):
                    await cl
            except Exception:
                pass
            await asyncio.sleep(8)
        return "✅ Đã đăng"
    except Exception as e:
        err_str = str(e)
        print(f"[!] Lỗi đăng YouTube: {err_str}")
        if "Timeout" in err_str:
            return "❌ Lỗi (Timeout chờ giao diện Studio)"
        return f"❌ Lỗi ({err_str[:25]}...)"

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

async def publish_all_platforms(
    video_path: Path,
    caption: str,
    record: dict,
    dry_run: bool = False,
    yt_title: str = None,
    tiktok_caption: str = None,
    fb_caption: str = None,
):
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
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )

        # Nạp cookies từ auth_state.json hoặc cookies.json nếu có
        saved_cookies = load_saved_cookies()
        if saved_cookies:
            await safe_add_cookies(context, saved_cookies)

        page = await context.new_page()

        # Kiểm tra trạng thái xác thực từng kênh để chỉ đăng các kênh đã có cookie
        auth_status = check_auth_status()
        yt_ready = auth_status["platforms"]["youtube"]["authenticated"]
        tt_ready = auth_status["platforms"]["tiktok"]["authenticated"]
        fb_ready = auth_status["platforms"]["facebook"]["authenticated"]

        # 1. YouTube Shorts
        if yt_ready:
            # Kiểm tra nhanh endpoint studio.youtube.com để tránh tốn thời gian timeout trình duyệt nếu cookie đã hết hạn
            ctx_cookies = await context.cookies()
            check_cookies = saved_cookies if saved_cookies else ctx_cookies
            is_valid, verify_msg = verify_youtube_session_online(check_cookies)
            if is_valid is False:
                print(f"[YouTube] Phiên đăng nhập không hợp lệ ({verify_msg}).")
                record["youtube"] = "❌ Lỗi (Cookie YouTube hết hạn hoặc chưa đăng nhập)"
                save_status_record(record)
            else:
                record["youtube"] = "⏳ Đang đăng..."
                save_status_record(record)
                upload_yt_title = yt_title or record.get("title") or caption
                record["youtube"] = await upload_to_youtube_shorts(page, video_path, upload_yt_title)
                save_status_record(record)
        else:
            record["youtube"] = "⏭️ Bỏ qua (Chưa có cookie)"
            save_status_record(record)

        # 2. TikTok Studio
        if tt_ready:
            record["tiktok"] = "⏳ Đang đăng..."
            save_status_record(record)
            upload_tt_caption = tiktok_caption or caption
            record["tiktok"] = await upload_to_tiktok(page, video_path, upload_tt_caption)
            save_status_record(record)
        else:
            record["tiktok"] = "⏭️ Bỏ qua (Chưa có cookie)"
            save_status_record(record)

        # 3. Facebook Reels
        if fb_ready:
            record["facebook"] = "⏳ Đang đăng..."
            save_status_record(record)
            upload_fb_caption = fb_caption or caption
            record["facebook"] = await upload_to_facebook_reels(page, video_path, upload_fb_caption)
            save_status_record(record)
        else:
            record["facebook"] = "⏭️ Bỏ qua (Chưa có cookie)"
            save_status_record(record)

        # Xác định trạng thái tổng kết
        posted = [name for name, val in [("YouTube", record["youtube"]), ("TikTok", record["tiktok"]), ("Facebook", record["facebook"])] if "Đã đăng" in val]
        if posted:
            record["overall_status"] = f"Hoàn tất (Đã đăng {', '.join(posted)})"
        else:
            record["overall_status"] = "Hoàn tất (Chưa nạp cookie kênh nào)"
        save_status_record(record)

        # Lưu lại cookies cập nhật mới nhất
        try:
            current_cookies = await context.cookies()
            if current_cookies:
                save_cookies(current_cookies)
        except Exception:
            pass

        await context.close()

# ==========================================
# 4. GIAO DIỆN WEB DASHBOARD (PORT 8080)
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
    elif "Bỏ qua" in status:
        bg, color = "#1e293b", "#94a3b8"
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
        # 1. API: Trạng thái xác thực tài khoản
        if self.path.startswith("/api/auth-status"):
            verify_live = ("verify=1" in self.path)
            auth_info = check_auth_status(verify_live=verify_live)
            res_body = json.dumps({"success": True, "auth": auth_info}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(res_body)))
            self.end_headers()
            self.wfile.write(res_body)
            return

        # 2. API: Tải về auth_state.json
        if self.path == "/api/export-cookies":
            cookies = load_saved_cookies()
            export_payload = json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Disposition", 'attachment; filename="auth_state.json"')
            self.send_header("Content-Length", str(len(export_payload)))
            self.end_headers()
            self.wfile.write(export_payload)
            return

        # 3. API: Tải về script trợ lý Windows (.bat / .ps1)
        if self.path == "/login-helper.bat":
            port = int(os.environ.get("DASHBOARD_PORT", 8080))
            bat_str = f"""@echo off
chcp 65001 >nul
title Auto-Publisher - Tro Ly Dang Nhap Trinh Duyet Windows

echo ======================================================================
echo   🚀 TRỢ LÝ ĐĂNG NHẬP TRÌNH DUYỆT WINDOWS CHO AUTO-PUBLISHER
echo ======================================================================
echo.
echo Đang mở trình duyệt Windows để bạn đăng nhập TikTok, YouTube, Facebook...
echo.

start "" "https://www.tiktok.com/login"
start "" "https://studio.youtube.com"
start "" "https://www.facebook.com"
start "" "http://localhost:{port}#accounts"

echo [✓] Đã mở các tab đăng nhập và trang Web Dashboard!
echo.
pause
"""
            body_bytes = bat_str.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-bat")
            self.send_header("Content-Disposition", 'attachment; filename="login_helper_windows.bat"')
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        if self.path == "/login-helper.ps1":
            port = int(os.environ.get("DASHBOARD_PORT", 8080))
            ps_str = f"""# Tro Ly Dang Nhap Trinh Duyet Windows (PowerShell)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host "Dang mo trinh duyet TikTok, YouTube, Facebook va Dashboard..."
Start-Process "https://www.tiktok.com/login"
Start-Process "https://studio.youtube.com"
Start-Process "https://www.facebook.com"
Start-Process "http://localhost:{port}#accounts"
Write-Host "`n[OK] Da mo cac tab dang nhap!"
"""
            body_bytes = ps_str.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="login_helper_windows.ps1"')
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        # 4. Phục vụ video trực tiếp qua endpoint /videos/<filename>
        if self.path.startswith("/videos/"):
            video_name = self.path[len("/videos/"):].split("?")[0]
            clean_name = Path(video_name).name
            video_file = (PUBLISHED_DIR / clean_name).resolve()
            if not video_file.exists():
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

        # 5. Trang chủ Dashboard
        records = load_status_list()
        total_exported = len(records)
        total_published = sum(1 for r in records if "Đã đăng" in str(r.get("overall_status", "")))

        auth_info = check_auth_status()
        auth_badge = "✅ 3/3 Sẵn sàng" if auth_info["all_authenticated"] else f"⚠️ {auth_info['ready_count']}/3 Sẵn sàng"
        auth_badge_color = "#34d399" if auth_info["all_authenticated"] else "#fde047"
        auth_badge_bg = "#065f46" if auth_info["all_authenticated"] else "#854d0e"

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

        # Render Platform cards HTML
        platforms = auth_info["platforms"]
        yt = platforms["youtube"]
        tt = platforms["tiktok"]
        fb = platforms["facebook"]

        def make_platform_card(p_id, p_data, icon):
            is_ok = p_data["authenticated"]
            bg_col = "#065f46" if is_ok else "#854d0e"
            text_col = "#34d399" if is_ok else "#fde047"
            status_text = "✅ Đã đăng nhập" if is_ok else "⚠️ Chưa đăng nhập"
            return f"""
            <div class="stat-card platform-card" id="card-{p_id}">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                    <span style="font-size:18px;font-weight:700">{icon} {p_data['name']}</span>
                    <span class="badge" style="background:{bg_col};color:{text_col}">{status_text}</span>
                </div>
                <div class="sub" style="font-size:13px;color:#cbd5e1;margin-bottom:12px">{p_data['details']}</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    <a href="{p_data['url']}" target="_blank" class="btn-watch" style="text-decoration:none;font-size:12px;padding:6px 12px;background:#334155;color:#e2e8f0">Mở trang đăng nhập ↗</a>
                    <button class="btn-watch" style="background:#475569;font-size:12px;padding:6px 10px" onclick="quickSelectPlatform('{p_id}')">Dán Cookie</button>
                </div>
            </div>
            """

        cards_html = (
            make_platform_card("youtube", yt, "🔴") +
            make_platform_card("tiktok", tt, "🎵") +
            make_platform_card("facebook", fb, "🔵")
        )

        html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta id="meta-refresh" http-equiv="refresh" content="10">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bảng Theo Dõi Đăng Video Tự Động (4 Tiếng / Video)</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ background: #0f172a; color: #f8fafc; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 28px 20px; margin: 0; }}
        .container {{ max-width: 1250px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; background: #1e293b; padding: 22px 28px; border-radius: 16px; margin-bottom: 20px; border: 1px solid #334155; }}
        .header-title h2 {{ margin: 0 0 6px 0; font-size: 24px; color: #ffffff; }}
        .header-title span {{ color: #94a3b8; font-size: 14px; }}
        
        .nav-tabs {{ display: flex; gap: 12px; margin-bottom: 20px; }}
        .tab-btn {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 10px 20px; border-radius: 10px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 14px; }}
        .tab-btn:hover {{ background: #334155; color: #f8fafc; }}
        .tab-btn.active {{ background: #0284c7; color: #ffffff; border-color: #38bdf8; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.3); }}

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
        .btn-action {{ background: #3b82f6; color: white; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px; display: inline-flex; align-items: center; gap: 6px; }}
        .btn-action:hover {{ background: #2563eb; }}
        .btn-danger {{ background: #dc2626; color: white; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px; }}
        .btn-danger:hover {{ background: #b91c1c; }}
        
        /* Modal Player */
        .modal {{ display: none; position: fixed; z-index: 999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); align-items: center; justify-content: center; }}
        .modal.active {{ display: flex; }}
        .modal-content {{ background: #1e293b; border-radius: 16px; border: 1px solid #475569; padding: 20px; max-width: 480px; width: 90%; text-align: center; position: relative; }}
        .modal-title {{ font-size: 16px; font-weight: 600; margin-bottom: 14px; color: #f8fafc; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }}
        .modal-close {{ position: absolute; right: 14px; top: 12px; background: none; border: none; font-size: 24px; color: #94a3b8; cursor: pointer; }}
        .modal-close:hover {{ color: #ffffff; }}
        video {{ width: 100%; max-height: 70vh; border-radius: 10px; background: #000; }}

        .form-group {{ margin-bottom: 16px; }}
        label {{ display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: #cbd5e1; }}
        select, textarea {{ width: 100%; background: #0b1120; border: 1px solid #334155; border-radius: 8px; color: #f8fafc; padding: 10px 14px; font-size: 14px; font-family: inherit; }}
        textarea {{ min-height: 120px; resize: vertical; }}
        .alert {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; display: none; font-size: 14px; }}
        .alert.success {{ background: #065f46; color: #34d399; border: 1px solid #059669; display: block; }}
        .alert.error {{ background: #991b1b; color: #f87171; border: 1px solid #dc2626; display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title">
                <h2>🚀 Trạm Kiểm Soát Auto-Threads Shorts</h2>
                <span>Chu kỳ tự động: <strong>{INTERVAL_HOURS} tiếng / 1 video</strong> • Tự động refresh tiến độ mỗi 10 giây</span>
            </div>
            <div style="display:flex;gap:12px;align-items:center">
                <div style="background:{auth_badge_bg};color:{auth_badge_color};padding:8px 16px;border-radius:10px;font-weight:700;font-size:13px;border:1px solid {auth_badge_color}" id="nav-auth-pill">
                    Tài khoản: {auth_badge}
                </div>
                <div style="background:#0284c7;padding:12px 20px;border-radius:10px;text-align:right">
                    <div style="font-size:12px;color:#bae6fd;text-transform:uppercase;font-weight:600">Đăng video tiếp theo</div>
                    <div style="font-size:18px;font-weight:700;color:#ffffff" id="timer-text">{next_str}</div>
                </div>
            </div>
        </div>

        <div class="nav-tabs">
            <button class="tab-btn active" id="btn-tab-pipeline" onclick="switchTab('pipeline')">🎬 Lịch Sử & Tiến Độ Video</button>
            <button class="tab-btn" id="btn-tab-accounts" onclick="switchTab('accounts')">🔐 Đăng Nhập & Quản Lý Tài Khoản</button>
        </div>

        <!-- TAB 1: PIPELINE TIẾN ĐỘ VIDEO -->
        <div id="tab-pipeline">
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

        <!-- TAB 2: QUẢN LÝ ĐĂNG NHẬP & COOKIES -->
        <div id="tab-accounts" style="display:none">
            <div class="stats-grid" style="margin-bottom:20px" id="platform-cards-container">
                {cards_html}
            </div>

            <div class="stat-card" style="margin-bottom:24px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px">
                    <h3 style="margin:0;font-size:18px">📥 Nạp Cookie Phiên Đăng Nhập (Cookie-Editor / JSON / Netscape / auth_state.json)</h3>
                    <button class="btn-action" style="background:#8b5cf6" onclick="openAllPlatformTabs()">🚀 Mở Cả 3 Trang Đăng Nhập Trên Trình Duyệt</button>
                </div>
                <div id="cookie-alert" class="alert"></div>

                <div class="form-group">
                    <label for="platform-select">Nền tảng đích:</label>
                    <select id="platform-select">
                        <option value="all">Tự động nhận diện nền tảng (Khuyên dùng)</option>
                        <option value="tiktok">TikTok (.tiktok.com)</option>
                        <option value="youtube">YouTube Studio (.youtube.com)</option>
                        <option value="facebook">Facebook (.facebook.com)</option>
                    </select>
                </div>

                <div class="form-group">
                    <label for="cookie-input">Mã Cookie JSON (Copy từ tiện ích Cookie-Editor hoặc file auth_state.json):</label>
                    <textarea id="cookie-input" placeholder="Dán mã JSON cookie từ extension Cookie-Editor hoặc file auth_state.json vào đây..."></textarea>
                </div>

                <div style="margin-bottom:18px;padding:12px 16px;background:#0b1120;border:1px dashed #38bdf8;border-radius:10px;display:flex;align-items:center;gap:14px;flex-wrap:wrap">
                    <span style="font-size:13px;color:#93c5fd;font-weight:600">📁 Hoặc nạp file trực tiếp từ máy tính:</span>
                    <input type="file" id="cookie-file-input" accept=".json,.txt" onchange="handleFileSelect(event)" style="font-size:13px;color:#cbd5e1;cursor:pointer">
                </div>

                <div style="display:flex;gap:10px;flex-wrap:wrap">
                    <button class="btn-action" onclick="submitCookies()">💾 Lưu & Nạp Cookie</button>
                    <button class="btn-action" style="background:#475569" onclick="refreshAuthStatus()">🔄 Kiểm Tra Trạng Thái</button>
                    <button class="btn-action" style="background:#0284c7" onclick="window.location.href='/api/export-cookies'">📥 Tải auth_state.json</button>
                    <button class="btn-action" style="background:#059669" onclick="window.location.href='/login-helper.bat'">💻 Tải Script Windows (.bat)</button>
                    <button class="btn-danger" onclick="clearPlatformCookies()">🗑️ Xóa Cookie</button>
                </div>
            </div>

            <div class="stat-card" style="background:#1e1b4b;border:1px solid #6366f1;border-radius:14px;padding:18px 22px;margin-bottom:18px">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                    <span style="font-size:20px">🔴</span>
                    <h3 style="margin:0;font-size:16px;color:#c7d2fe">Hướng Dẫn Nạp Cookie Cho Tab "YouTube" Đang Mở Trên Trình Duyệt:</h3>
                </div>
                <p style="font-size:13px;color:#e0e7ff;margin:0 0 10px 0;line-height:1.6">
                    Trình duyệt của bạn đang có sẵn tab <strong>YouTube</strong> (đã đăng nhập). Hãy xuất cookie sang đây chỉ với 3 thao tác:
                </p>
                <ol style="margin:0;padding-left:22px;color:#cbd5e1;line-height:1.8;font-size:13px">
                    <li>Chuyển sang tab <strong>YouTube</strong> đang mở trên trình duyệt.</li>
                    <li>Bấm biểu tượng tiện ích <strong>Cookie-Editor</strong> trên góc trình duyệt &rarr; chọn <strong>Export</strong> &rarr; chọn <strong>Export as JSON</strong>.</li>
                    <li>Quay lại tab này &rarr; chọn nền tảng <strong>YouTube Studio (.youtube.com)</strong> &rarr; dán vào ô trên &rarr; bấm <strong>💾 Lưu & Nạp Cookie</strong>.</li>
                </ol>
                <div style="margin-top:10px;font-size:12px;color:#94a3b8">
                    <em>💡 Yêu cầu: Cookie xuất ra cần chứa <code>LOGIN_INFO</code> và <code>SID</code> từ tài khoản Google/YouTube đã đăng nhập để YouTube Studio cấp quyền tải lên.</em>
                </div>
            </div>

            <div class="stat-card" style="background:#131c2e;border-color:#1e3a8a">
                <h3 style="margin-top:0;font-size:16px;color:#93c5fd">💡 Hướng Dẫn Chung 4 Bước Lấy Cookie Trên Windows (Cốc Cốc, Chrome, Edge):</h3>
                <ol style="margin:0;padding-left:22px;color:#cbd5e1;line-height:1.7;font-size:14px">
                    <li>Cài tiện ích <strong><a href="https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm" target="_blank" style="color:#60a5fa">Cookie-Editor</a></strong> trên trình duyệt của bạn (hoàn toàn miễn phí, an toàn).</li>
                    <li>Bấm nút tím <strong>"🚀 Mở Cả 3 Trang Đăng Nhập"</strong> ở trên và đăng nhập tài khoản của bạn bình thường.</li>
                    <li>Bấm biểu tượng <strong>Cookie-Editor</strong> trên thanh công cụ trình duyệt &rarr; chọn <strong>Export</strong> &rarr; chọn <strong>Export as JSON</strong>.</li>
                    <li>Dán nội dung JSON vào khung phía trên và bấm <strong>"Lưu & Nạp Cookie"</strong>. Hệ thống sẽ lập tức cập nhật trạng thái xanh!</li>
                </ol>
            </div>
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
            if (!el) return;
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

        // Tự động reload chỉ khi ở tab pipeline
        let autoReloadTimer = null;
        function schedulePipelineRefresh() {{
            if (autoReloadTimer) clearTimeout(autoReloadTimer);
            autoReloadTimer = setTimeout(() => {{
                if (window.location.hash !== "#accounts" && window.location.hash !== "#login") {{
                    window.location.reload();
                }} else {{
                    refreshAuthStatus();
                    schedulePipelineRefresh();
                }}
            }}, 10000);
        }}
        schedulePipelineRefresh();

        function switchTab(name) {{
            const pipe = document.getElementById("tab-pipeline");
            const acc = document.getElementById("tab-accounts");
            const bPipe = document.getElementById("btn-tab-pipeline");
            const bAcc = document.getElementById("btn-tab-accounts");

            if (name === "accounts") {{
                pipe.style.display = "none";
                acc.style.display = "block";
                bPipe.classList.remove("active");
                bAcc.classList.add("active");
                window.location.hash = "#accounts";
                refreshAuthStatus();
            }} else {{
                pipe.style.display = "block";
                acc.style.display = "none";
                bPipe.classList.add("active");
                bAcc.classList.remove("active");
                window.location.hash = "#pipeline";
            }}
        }}

        if (window.location.hash === "#accounts" || window.location.hash === "#login") {{
            switchTab("accounts");
        }}

        function quickSelectPlatform(platform) {{
            const sel = document.getElementById("platform-select");
            if (sel) sel.value = platform;
            const area = document.getElementById("cookie-input");
            if (area) {{
                area.focus();
                area.scrollIntoView({{ behavior: "smooth" }});
            }}
        }}

        function openAllPlatformTabs() {{
            window.open("https://www.tiktok.com/login", "_blank");
            window.open("https://studio.youtube.com", "_blank");
            window.open("https://www.facebook.com", "_blank");
            try {{
                fetch("/api/open-browser", {{ method: "POST" }});
            }} catch(e) {{}}
        }}

        function handleFileSelect(event) {{
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {{
                document.getElementById("cookie-input").value = e.target.result;
                showAlert("Đã đọc nội dung file '" + file.name + "'. Hãy bấm 'Lưu & Nạp Cookie'!", true);
            }};
            reader.readAsText(file);
        }}

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

        // Quản lý Cookies API AJAX
        function showAlert(msg, isSuccess) {{
            const el = document.getElementById("cookie-alert");
            el.className = isSuccess ? "alert success" : "alert error";
            el.innerText = msg;
            el.style.display = "block";
            setTimeout(() => {{
                el.style.display = "none";
            }}, 8000);
        }}

        async function submitCookies() {{
            const raw = document.getElementById("cookie-input").value;
            const platform = document.getElementById("platform-select").value;
            if (!raw || !raw.trim()) {{
                showAlert("Vui lòng dán nội dung cookie vào khung trước khi bấm lưu!", false);
                return;
            }}
            try {{
                const resp = await fetch("/api/save-cookies", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ cookies: raw, platform: platform }})
                }});
                const data = await resp.json();
                if (data.success) {{
                    showAlert(data.message || "Đã lưu cookie thành công!", true);
                    document.getElementById("cookie-input").value = "";
                    refreshAuthStatus();
                }} else {{
                    showAlert(data.message || "Lỗi lưu cookie", false);
                }}
            }} catch (err) {{
                showAlert("Lỗi kết nối máy chủ: " + err, false);
            }}
        }}

        async function clearPlatformCookies() {{
            const platform = document.getElementById("platform-select").value;
            if (!confirm("Bạn có chắc muốn xóa cookie " + (platform === "all" ? "tất cả nền tảng" : platform) + "?")) return;
            try {{
                const resp = await fetch("/api/clear-cookies", {{
                    method: "POST",
                    headers: {{ "Content-Type": "application/json" }},
                    body: JSON.stringify({{ platform: platform }})
                }});
                const data = await resp.json();
                if (data.success) {{
                    showAlert(data.message, true);
                    refreshAuthStatus();
                }}
            }} catch (err) {{
                showAlert("Lỗi: " + err, false);
            }}
        }}

        async function refreshAuthStatus() {{
            try {{
                const resp = await fetch("/api/auth-status?verify=1");
                const data = await resp.json();
                if (data.success && data.auth) {{
                    const auth = data.auth;
                    const pill = document.getElementById("nav-auth-pill");
                    if (pill) {{
                        pill.innerText = auth.all_authenticated ? "Tài khoản: ✅ 3/3 Sẵn sàng" : "Tài khoản: ⚠️ " + auth.ready_count + "/3 Sẵn sàng";
                        pill.style.background = auth.all_authenticated ? "#065f46" : "#854d0e";
                        pill.style.color = auth.all_authenticated ? "#34d399" : "#fde047";
                        pill.style.borderColor = auth.all_authenticated ? "#34d399" : "#fde047";
                    }}
                    for (const [k, p] of Object.entries(auth.platforms)) {{
                        const card = document.getElementById("card-" + k);
                        if (card) {{
                            const badge = card.querySelector(".badge");
                            const sub = card.querySelector(".sub");
                            if (badge) {{
                                badge.innerText = p.authenticated ? "✅ Đã đăng nhập" : "⚠️ Chưa đăng nhập";
                                badge.style.background = p.authenticated ? "#065f46" : "#854d0e";
                                badge.style.color = p.authenticated ? "#34d399" : "#fde047";
                            }}
                            if (sub) {{
                                sub.innerText = p.details;
                            }}
                        }}
                    }}
                }}
            }} catch (e) {{
                console.error("Lỗi lấy trạng thái:", e);
            }}
        }}
    </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        if self.path == "/api/open-browser":
            port = int(os.environ.get("DASHBOARD_PORT", 8080))
            st = check_auth_status()
            opened = []
            for k, p in st["platforms"].items():
                if not p["authenticated"] and p.get("url"):
                    if launch_windows_browser(p["url"]):
                        opened.append(p["name"])
            launch_windows_browser(f"http://localhost:{port}#accounts")
            res_body = json.dumps({
                "success": True,
                "message": f"Đã mở các trang: {', '.join(opened) if opened else 'Dashboard'}"
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(res_body)))
            self.end_headers()
            self.wfile.write(res_body)
            return

        if self.path == "/api/save-cookies":
            try:
                data = json.loads(body) if body else {}
                raw_cookies = data.get("cookies", "")
                platform = data.get("platform", "all")
                default_domain = None
                if platform == "tiktok":
                    default_domain = ".tiktok.com"
                elif platform in ["youtube", "google"]:
                    default_domain = ".youtube.com"
                elif platform == "facebook":
                    default_domain = ".facebook.com"

                parsed = parse_cookies_input(raw_cookies, default_domain=default_domain)
                if not parsed:
                    res_body = json.dumps({
                        "success": False,
                        "message": "Không tìm thấy cookie hợp lệ nào trong nội dung nhập vào. Hãy kiểm tra lại mã JSON."
                    }, ensure_ascii=False).encode("utf-8")
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(res_body)))
                    self.end_headers()
                    self.wfile.write(res_body)
                    return

                total_saved = save_cookies(parsed, merge=True)
                auth_info = check_auth_status(verify_live=True)
                res_body = json.dumps({
                    "success": True,
                    "count": len(parsed),
                    "total_saved": total_saved,
                    "message": f"Đã nạp thành công {len(parsed)} cookie!",
                    "auth": auth_info
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return
            except Exception as e:
                res_body = json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return

        if self.path == "/api/clear-cookies":
            try:
                data = json.loads(body) if body else {}
                platform = data.get("platform", "all")
                clear_cookies(platform=platform)
                auth_info = check_auth_status()
                res_body = json.dumps({
                    "success": True,
                    "message": f"Đã xóa cookie ({platform}) thành công!",
                    "auth": auth_info
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return
            except Exception as e:
                res_body = json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(res_body)))
                self.end_headers()
                self.wfile.write(res_body)
                return

        self.send_error(404, "Endpoint Not Found")

from socketserver import ThreadingMixIn

class ReusableHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_dashboard_server(port=8080):
    try:
        server = ReusableHTTPServer(("0.0.0.0", port), DashboardHandler)
        print(f"📊 Bảng theo dõi trực tuyến đã mở tại: http://localhost:{port}")
        server.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"ℹ️ Cổng {port} đang được sử dụng (Web Dashboard có thể đã đang chạy).")
        else:
            raise

# ==========================================
# 5. ĐĂNG NHẬP THIẾT LẬP PHIÊN (--login)
# ==========================================
async def login_setup():
    """Hệ thống đăng nhập và thiết lập phiên tài khoản đa nền tảng 100% ổn định:
    1. Kiểm tra trạng thái hiện tại của YouTube Studio, TikTok Studio, Facebook.
    2. Tự động khởi chạy Web Dashboard (cổng 8080 hoặc DASHBOARD_PORT).
    3. Cố gắng mở trình duyệt trên Windows (Cốc Cốc, Chrome, Edge) tới trang Quản lý Tài khoản & Cookie.
    4. Cung cấp hướng dẫn trực quan để nạp cookie qua Cookie-Editor hoặc file auth_state.json.
    5. Tự động nhận diện khi tất cả tài khoản đã sẵn sàng và lưu vào auth_state.json.
    """
    import sys
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("DASHBOARD_PORT", 8080))

    # Khởi chạy Web Dashboard ở luồng nền nếu chưa chạy
    dashboard_thread = threading.Thread(
        target=start_dashboard_server,
        kwargs={"port": port},
        daemon=True
    )
    dashboard_thread.start()
    await asyncio.sleep(0.5)

    dash_url = f"http://localhost:{port}#accounts"
    launch_windows_browser(dash_url)

    # Thử triển khai shortcut lên màn hình Desktop Windows nếu phát hiện thấy
    desktop_shortcut = deploy_windows_desktop_helper(port=port)

    status = check_auth_status()
    # Mở các tab nền tảng chưa đăng nhập trên trình duyệt Windows
    for k, p in status["platforms"].items():
        if not p["authenticated"] and p.get("url"):
            launch_windows_browser(p["url"])

    print("\n" + "=" * 70)
    print("🔐 HỆ THỐNG ĐĂNG NHẬP & QUẢN LÝ PHIÊN (WSL2 / WINDOWS / LINUX)")
    print("=" * 70)
    print("📊 Trạng thái xác thực hiện tại:")
    for k, p in status["platforms"].items():
        icon = "✅" if p["authenticated"] else "⚠️"
        print(f"   [{p['name']:<15}] : {icon} {p['details']}")
    print("-" * 70)

    if status["all_authenticated"]:
        print("\n🎉 Tất cả 3 nền tảng đã sẵn sàng xuất bản video tự động!")
        print(f"👉 Bạn có thể xem và chỉnh sửa phiên bất cứ lúc nào tại: {dash_url}")
        print("Nhấn phím [ENTER] để kết thúc: ", end="", flush=True)
        if sys.stdin and sys.stdin.isatty():
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, sys.stdin.readline)
            except Exception:
                pass
        return

    print("🌐 Đã mở Web Dashboard Quản lý Tài khoản tại:")
    print(f"   👉 {dash_url}\n")
    if desktop_shortcut:
        print(f"🖥️ Đã tạo lối tắt mở trình duyệt trên Windows Desktop: {desktop_shortcut}")
    print("👉 3 CÁCH NẠP PHIÊN ĐĂNG NHẬP DỄ DÀNG:")
    print(f"   1. [Khuyên dùng]: Mở {dash_url} trên Cốc Cốc / Chrome / Edge,")
    print("      dùng tiện ích 'Cookie-Editor' -> Export JSON -> dán vào Dashboard và bấm 'Lưu Cookie'.")
    print("   2. [Windows Desktop Helper]: Bấm đúp vào file 'AutoPublisher_Login.bat' trên màn hình Windows Desktop.")
    print("   3. [File thả trực tiếp]: Copy file 'auth_state.json' hoặc 'cookies.json' vào thư mục dự án.")
    print("=" * 70)
    print("⏳ Hệ thống đang theo dõi và tự động phát hiện khi bạn lưu cookie...")
    print("👉 Nhấn [ENTER] tại terminal này bất kỳ lúc nào để kiểm tra trạng thái và kết thúc: ", end="", flush=True)

    # Đợi người dùng nạp cookie hoặc bấm Enter
    async def poll_auth():
        while True:
            await asyncio.sleep(2)
            st = check_auth_status()
            if st["all_authenticated"]:
                return st

    async def wait_user_input():
        if not sys.stdin or not sys.stdin.isatty():
            while True:
                await asyncio.sleep(3600)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, sys.stdin.readline)

    input_task = asyncio.create_task(wait_user_input())
    poll_task = asyncio.create_task(poll_auth())

    done, pending = await asyncio.wait([input_task, poll_task], return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    final_status = check_auth_status()
    print("\n" + "=" * 70)
    print("📊 KẾT QUẢ KIỂM TRA PHIÊN ĐĂNG NHẬP:")
    for k, p in final_status["platforms"].items():
        icon = "✅" if p["authenticated"] else "⚠️"
        print(f"   [{p['name']:<15}] : {icon} {p['details']}")
    print("=" * 70)

    if final_status["all_authenticated"]:
        print("🎉 [✓] Hoàn tất! Cả 3 nền tảng đã sẵn sàng cho pipeline tự động đăng bài.")
    else:
        print(f"ℹ️ Dùng lệnh '.venv/bin/python auto_publisher.py --login' hoặc '--server-only' để mở lại Dashboard nạp thêm cookie bất cứ lúc nào.")

# ==========================================
# 6. VÒNG LẶP CHÍNH: 4 TIẾNG 1 VIDEO
# ==========================================
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

        # Tạo tiêu đề rõ ràng phù hợp với reel và hashtag phong phú
        reel_meta = generate_reel_caption(story, api_key=api_key)
        clean_title = reel_meta["title"]
        caption = reel_meta["caption"]
        yt_title = reel_meta["youtube_title"]
        tt_caption = reel_meta.get("tiktok_caption", caption)
        fb_caption = reel_meta.get("facebook_caption", caption)

        record["title"] = clean_title
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
        await publish_all_platforms(
            output_path,
            caption,
            record,
            dry_run=dry_run,
            yt_title=yt_title,
            tiktok_caption=tt_caption,
            fb_caption=fb_caption,
        )

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
    elif "--check-login" in sys.argv or "--status" in sys.argv:
        st = check_auth_status()
        print("\n" + "=" * 60)
        print("📊 TRẠNG THÁI ĐĂNG NHẬP CÁC NỀN TẢNG:")
        print("=" * 60)
        for k, p in st["platforms"].items():
            icon = "✅" if p["authenticated"] else "⚠️"
            print(f"  [{p['name']:<15}] : {icon} {p['details']}")
        print("=" * 60)
        if st["all_authenticated"]:
            print("🎉 Cả 3 nền tảng đã sẵn sàng đăng bài tự động!\n")
            sys.exit(0)
        else:
            print(f"⚠️ Còn {3 - st['ready_count']} nền tảng chưa đăng nhập. Dùng --login để thiết lập.\n")
            sys.exit(1)
    elif "--server-only" in sys.argv or "--dashboard-only" in sys.argv:
        port = int(os.environ.get("DASHBOARD_PORT", 8080))
        start_dashboard_server(port=port)
    elif once or dry_run:
        asyncio.run(run_4h_pipeline(once=once, dry_run=dry_run))
    else:
        asyncio.run(run_4h_pipeline())
