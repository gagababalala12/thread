import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import threading
import time
from pathlib import Path
from http.server import HTTPServer

import auto_publisher


class TestAutoPublisher(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_status_file = auto_publisher.STATUS_FILE
        self.original_profile_dir = auto_publisher.PROFILE_DIR
        self.original_published_dir = auto_publisher.PUBLISHED_DIR
        self.original_auth_state_file = auto_publisher.AUTH_STATE_FILE
        self.original_cookies_file = auto_publisher.COOKIES_FILE

        self.test_status_file = Path(self.test_dir) / "test_publish_status.json"
        self.test_profile_dir = Path(self.test_dir) / "test_browser_profile"
        self.test_published_dir = Path(self.test_dir) / "test_published_videos"
        self.test_published_dir.mkdir(parents=True, exist_ok=True)
        self.test_auth_state_file = Path(self.test_dir) / "test_auth_state.json"
        self.test_cookies_file = Path(self.test_dir) / "test_cookies.json"

        auto_publisher.STATUS_FILE = self.test_status_file
        auto_publisher.PROFILE_DIR = self.test_profile_dir
        auto_publisher.PUBLISHED_DIR = self.test_published_dir
        auto_publisher.AUTH_STATE_FILE = self.test_auth_state_file
        auto_publisher.COOKIES_FILE = self.test_cookies_file

    def tearDown(self):
        auto_publisher.STATUS_FILE = self.original_status_file
        auto_publisher.PROFILE_DIR = self.original_profile_dir
        auto_publisher.PUBLISHED_DIR = self.original_published_dir
        auto_publisher.AUTH_STATE_FILE = self.original_auth_state_file
        auto_publisher.COOKIES_FILE = self.original_cookies_file
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_status_list_empty_and_corrupt(self):
        # Khi file chưa tồn tại
        self.assertEqual(auto_publisher.load_status_list(), [])

        # Khi file bị hỏng
        self.test_status_file.write_text("{corrupt json", encoding="utf-8")
        self.assertEqual(auto_publisher.load_status_list(), [])

    def test_save_and_update_status_record(self):
        # Thêm record mới
        record1 = {
            "id": 1,
            "created_at": "10:00 - 22/10/2026",
            "title": "Chuyện Tiểu Minh",
            "video_file": "short_1.mp4",
            "youtube": "⏳ Chờ video",
            "facebook": "⏳ Chờ video",
            "tiktok": "⏳ Chờ video",
            "overall_status": "🎬 Đang dựng video..."
        }
        auto_publisher.save_status_record(record1)
        data = auto_publisher.load_status_list()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], 1)

        # Cập nhật record đã tồn tại
        record1_updated = dict(record1)
        record1_updated["youtube"] = "✅ Đã đăng"
        record1_updated["overall_status"] = "Hoàn tất (Đã đăng xong)"
        auto_publisher.save_status_record(record1_updated)

        data = auto_publisher.load_status_list()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["youtube"], "✅ Đã đăng")
        self.assertEqual(data[0]["overall_status"], "Hoàn tất (Đã đăng xong)")

        # Thêm record 2 (phải chèn lên đầu danh sách)
        record2 = {
            "id": 2,
            "created_at": "14:00 - 22/10/2026",
            "title": "Chuyện Con Vẹt",
            "video_file": "short_2.mp4",
            "youtube": "⏳ Đang đăng...",
            "facebook": "⏳ Đang đăng...",
            "tiktok": "⏳ Đang đăng...",
            "overall_status": "🚀 Đang đăng lên 3 kênh..."
        }
        auto_publisher.save_status_record(record2)
        data = auto_publisher.load_status_list()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], 2)
        self.assertEqual(data[1]["id"], 1)

    def test_render_badge(self):
        badge_ok = auto_publisher.render_badge("✅ Đã đăng")
        self.assertIn("#065f46", badge_ok)
        self.assertIn("✅ Đã đăng", badge_ok)

        badge_waiting = auto_publisher.render_badge("⏳ Đang xử lý")
        self.assertIn("#854d0e", badge_waiting)

        badge_err = auto_publisher.render_badge("❌ Lỗi (403)")
        self.assertIn("#991b1b", badge_err)

    def test_dashboard_http_server_and_video_stream(self):
        # Tạo file video mẫu giả lập trong published_videos
        dummy_video_path = self.test_published_dir / "test_video_42.mp4"
        dummy_video_bytes = b"\x00\x00\x00 ftypmp42\x00\x00\x00\x00mp42mp41"
        dummy_video_path.write_bytes(dummy_video_bytes)

        # Chuẩn bị dữ liệu mẫu
        record = {
            "id": 42,
            "created_at": "18:00 - 22/10/2026",
            "title": "Kiểm thử Web Dashboard & Stream Video",
            "video_file": "test_video_42.mp4",
            "youtube": "✅ Đã đăng",
            "facebook": "✅ Đã đăng",
            "tiktok": "✅ Đã đăng",
            "overall_status": "Hoàn tất (Đã đăng xong)"
        }
        auto_publisher.save_status_record(record)

        # Khởi chạy server trên cổng ngẫu nhiên 18090
        test_port = 18090
        server = auto_publisher.ReusableHTTPServer(("127.0.0.1", test_port), auto_publisher.DashboardHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            # 1. Kiểm tra trang chủ Dashboard
            url = f"http://127.0.0.1:{test_port}/"
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                content = response.read().decode("utf-8")
                self.assertIn("Trạm Kiểm Soát Auto-Threads Shorts", content)
                self.assertIn("Kiểm thử Web Dashboard & Stream Video", content)
                self.assertIn("#42", content)
                self.assertIn("test_video_42.mp4", content)
                self.assertIn("content=\"10\"", content)  # Refresh mỗi 10 giây
                self.assertIn("Tổng video đã xuất", content)
                self.assertIn("Đã đăng thành công", content)
                self.assertIn("countdown-val", content)
                self.assertIn("▶ Xem video", content)

            # 2. Kiểm tra endpoint streaming video /videos/<filename>
            video_url = f"http://127.0.0.1:{test_port}/videos/test_video_42.mp4"
            with urllib.request.urlopen(video_url, timeout=5) as v_response:
                self.assertEqual(v_response.status, 200)
                self.assertEqual(v_response.headers.get("Content-Type"), "video/mp4")
                self.assertEqual(v_response.headers.get("Accept-Ranges"), "bytes")
                received_bytes = v_response.read()
                self.assertEqual(received_bytes, dummy_video_bytes)

            # 3. Kiểm tra file không tồn tại trả về 404
            missing_url = f"http://127.0.0.1:{test_port}/videos/not_found.mp4"
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(missing_url, timeout=5)
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()

    async def test_publish_all_platforms_dry_run(self):
        record = {
            "id": 99,
            "created_at": "20:00 - 22/10/2026",
            "title": "Dry run test",
            "video_file": "test_dry.mp4",
            "youtube": "⏳ Chờ video",
            "facebook": "⏳ Chờ video",
            "tiktok": "⏳ Chờ video",
            "overall_status": "🎬 Đang dựng video..."
        }
        auto_publisher.save_status_record(record)

        video_path = Path("/tmp/fake_short.mp4")
        caption = "Caption #shorts #threads #haihuoc #xuhuong"

        # Thực thi publish_all_platforms ở chế độ dry_run=True
        await auto_publisher.publish_all_platforms(video_path, caption, record, dry_run=True)

        data = auto_publisher.load_status_list()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["youtube"], "✅ Đã đăng")
        self.assertEqual(data[0]["tiktok"], "✅ Đã đăng")
        self.assertEqual(data[0]["facebook"], "✅ Đã đăng")
        self.assertIn("Hoàn tất", data[0]["overall_status"])

    async def test_upload_to_tiktok_success(self):
        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/tiktokstudio/upload"
        mock_page.frames = []
        mock_page.goto = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        mock_input = MagicMock()
        mock_input.set_input_files = AsyncMock()
        mock_input.wait_for = AsyncMock()
        mock_input.first = mock_input

        mock_caption = MagicMock()
        mock_caption.count = AsyncMock(return_value=1)
        mock_caption.click = AsyncMock()
        mock_caption.first = mock_caption

        mock_btn = MagicMock()
        mock_btn.click = AsyncMock()
        mock_btn.is_enabled = AsyncMock(return_value=True)
        mock_btn.count = AsyncMock(return_value=1)
        mock_btn.last = mock_btn

        def locator_side_effect(selector):
            if 'input[type="file"]' in selector:
                return mock_input
            elif "contenteditable" in selector or "textarea" in selector:
                return mock_caption
            elif "button" in selector:
                return mock_btn
            loc = MagicMock()
            loc.first = loc
            loc.last = loc
            loc.count = AsyncMock(return_value=1)
            loc.is_enabled = AsyncMock(return_value=True)
            return loc

        mock_page.locator.side_effect = locator_side_effect

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_tiktok(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Caption test #tiktok"
            )
            self.assertEqual(result, "✅ Đã đăng")

    async def test_upload_to_youtube_shorts_success(self):
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        mock_first = MagicMock()
        mock_first.click = AsyncMock()
        mock_first.count = AsyncMock(return_value=1)
        mock_first.set_input_files = AsyncMock()

        mock_loc = MagicMock()
        mock_loc.first = mock_first
        mock_loc.click = AsyncMock()
        mock_loc.set_input_files = AsyncMock()
        mock_page.locator.return_value = mock_loc

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_youtube_shorts(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Tiêu đề Shorts Hài Hước"
            )
            self.assertEqual(result, "✅ Đã đăng")

    async def test_upload_to_facebook_reels_success(self):
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        mock_item = MagicMock()
        mock_item.click = AsyncMock()
        mock_item.count = AsyncMock(return_value=1)
        mock_item.set_input_files = AsyncMock()

        mock_loc = MagicMock()
        mock_loc.first = mock_item
        mock_loc.last = mock_item
        mock_page.locator.return_value = mock_loc

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_facebook_reels(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Mô tả Facebook Reels"
            )
            self.assertEqual(result, "✅ Đã đăng")

    async def test_upload_error_handling(self):
        mock_page = MagicMock()
        mock_page.goto = AsyncMock(side_effect=RuntimeError("Mất kết nối mạng"))

        result_tiktok = await auto_publisher.upload_to_tiktok(mock_page, Path("/tmp/v.mp4"), "test")
        self.assertIn("❌ Lỗi", result_tiktok)

        result_yt = await auto_publisher.upload_to_youtube_shorts(mock_page, Path("/tmp/v.mp4"), "test")
        self.assertIn("❌ Lỗi", result_yt)

        result_fb = await auto_publisher.upload_to_facebook_reels(mock_page, Path("/tmp/v.mp4"), "test")
        self.assertIn("❌ Lỗi", result_fb)

    def test_normalize_cookie(self):
        # Cookie-Editor format với sameSite: no_restriction và expirationDate
        raw_cookie = {
            "name": "sessionid",
            "value": "secret_tt_val",
            "domain": ".tiktok.com",
            "path": "/",
            "sameSite": "no_restriction",
            "expirationDate": 1899999999,
            "hostOnly": False,
            "httpOnly": True,
            "secure": False
        }
        normalized = auto_publisher.normalize_cookie(raw_cookie)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["name"], "sessionid")
        self.assertEqual(normalized["value"], "secret_tt_val")
        self.assertEqual(normalized["domain"], ".tiktok.com")
        self.assertEqual(normalized["sameSite"], "None")
        self.assertTrue(normalized["secure"])  # SameSite=None bắt buộc secure=True
        self.assertTrue(normalized["httpOnly"])
        self.assertEqual(normalized["expires"], 1899999999.0)

        # Invalid cookie (thiếu name hoặc domain)
        self.assertIsNone(auto_publisher.normalize_cookie({}))
        self.assertIsNone(auto_publisher.normalize_cookie({"name": "test"}))

    def test_parse_cookies_input_formats(self):
        # 1. Cookie-Editor JSON array
        json_str = json.dumps([
            {"name": "LOGIN_INFO", "value": "yt_val", "domain": ".youtube.com", "path": "/"}
        ])
        parsed = auto_publisher.parse_cookies_input(json_str)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "LOGIN_INFO")

        # 2. Playwright storage_state format
        storage_state = {
            "cookies": [
                {"name": "c_user", "value": "100012345", "domain": ".facebook.com", "path": "/"}
            ],
            "origins": []
        }
        parsed = auto_publisher.parse_cookies_input(storage_state)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "c_user")

        # 3. Dict platform
        platform_dict = {
            "tiktok": [{"name": "sessionid", "value": "tt_123"}],
            "facebook": [{"name": "xs", "value": "fb_456"}]
        }
        parsed = auto_publisher.parse_cookies_input(platform_dict)
        self.assertEqual(len(parsed), 2)
        domains = {c["domain"] for c in parsed}
        self.assertIn(".tiktok.com", domains)
        self.assertIn(".facebook.com", domains)

        # 4. Netscape format
        netscape_str = ".tiktok.com\tTRUE\t/\tTRUE\t1999999999\tsid_tt\tsecret_sid\n"
        parsed = auto_publisher.parse_cookies_input(netscape_str)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "sid_tt")
        self.assertEqual(parsed[0]["value"], "secret_sid")

        # 5. Raw header string
        header_str = "cookie1=val1; cookie2=val2"
        parsed = auto_publisher.parse_cookies_input(header_str, default_domain=".tiktok.com")
        self.assertEqual(len(parsed), 2)
        names = {c["name"] for c in parsed}
        self.assertEqual(names, {"cookie1", "cookie2"})

    def test_save_load_and_merge_cookies(self):
        c1 = [{"name": "sessionid", "value": "tt_val_1", "domain": ".tiktok.com", "path": "/"}]
        auto_publisher.save_cookies(c1, target_file=self.test_auth_state_file)

        loaded = auto_publisher.load_saved_cookies()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["value"], "tt_val_1")

        # Merge cookie mới từ YouTube
        c2 = [{"name": "LOGIN_INFO", "value": "yt_val_1", "domain": ".youtube.com", "path": "/"}]
        auto_publisher.save_cookies(c2, target_file=self.test_auth_state_file, merge=True)

        loaded = auto_publisher.load_saved_cookies()
        self.assertEqual(len(loaded), 2)
        names = {c["name"] for c in loaded}
        self.assertEqual(names, {"sessionid", "LOGIN_INFO"})

        # Cập nhật giá trị sessionid cũ
        c1_updated = [{"name": "sessionid", "value": "tt_val_NEW", "domain": ".tiktok.com", "path": "/"}]
        auto_publisher.save_cookies(c1_updated, target_file=self.test_auth_state_file, merge=True)

        loaded = auto_publisher.load_saved_cookies()
        self.assertEqual(len(loaded), 2)
        tt_c = next(c for c in loaded if c["name"] == "sessionid")
        self.assertEqual(tt_c["value"], "tt_val_NEW")

    def test_clear_cookies(self):
        cookies = [
            {"name": "sessionid", "value": "1", "domain": ".tiktok.com", "path": "/"},
            {"name": "LOGIN_INFO", "value": "2", "domain": ".youtube.com", "path": "/"},
            {"name": "c_user", "value": "3", "domain": ".facebook.com", "path": "/"}
        ]
        auto_publisher.save_cookies(cookies, target_file=self.test_auth_state_file)
        self.assertEqual(len(auto_publisher.load_saved_cookies()), 3)

        # Xóa TikTok
        auto_publisher.clear_cookies("tiktok", target_file=self.test_auth_state_file)
        remaining = auto_publisher.load_saved_cookies()
        self.assertEqual(len(remaining), 2)
        self.assertNotIn("sessionid", [c["name"] for c in remaining])

        # Xóa tất cả
        auto_publisher.clear_cookies("all", target_file=self.test_auth_state_file)
        self.assertEqual(len(auto_publisher.load_saved_cookies()), 0)

    def test_check_auth_status(self):
        # Trạng thái ban đầu: chưa có gì
        st = auto_publisher.check_auth_status([])
        self.assertFalse(st["all_authenticated"])
        self.assertEqual(st["ready_count"], 0)
        self.assertFalse(st["platforms"]["tiktok"]["authenticated"])
        self.assertFalse(st["platforms"]["youtube"]["authenticated"])
        self.assertFalse(st["platforms"]["facebook"]["authenticated"])

        # Nạp lần lượt từng nền tảng
        c_tt = [{"name": "sessionid", "value": "xyz", "domain": ".tiktok.com", "path": "/"}]
        st_tt = auto_publisher.check_auth_status(c_tt)
        self.assertTrue(st_tt["platforms"]["tiktok"]["authenticated"])
        self.assertEqual(st_tt["ready_count"], 1)

        c_yt = c_tt + [{"name": "LOGIN_INFO", "value": "abc", "domain": ".youtube.com", "path": "/"}]
        st_yt = auto_publisher.check_auth_status(c_yt)
        self.assertTrue(st_yt["platforms"]["youtube"]["authenticated"])
        self.assertEqual(st_yt["ready_count"], 2)

        c_fb = c_yt + [
            {"name": "c_user", "value": "615709999", "domain": ".facebook.com", "path": "/"},
            {"name": "xs", "value": "token", "domain": ".facebook.com", "path": "/"}
        ]
        st_all = auto_publisher.check_auth_status(c_fb)
        self.assertTrue(st_all["all_authenticated"])
        self.assertEqual(st_all["ready_count"], 3)
        self.assertIn("615709999", st_all["platforms"]["facebook"]["details"])

    def test_dashboard_api_endpoints(self):
        test_port = 18091
        server = auto_publisher.ReusableHTTPServer(("127.0.0.1", test_port), auto_publisher.DashboardHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            # 1. GET /api/auth-status
            status_url = f"http://127.0.0.1:{test_port}/api/auth-status"
            with urllib.request.urlopen(status_url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertIn("platforms", data.get("auth", {}))

            # 2. POST /api/save-cookies (hợp lệ)
            save_url = f"http://127.0.0.1:{test_port}/api/save-cookies"
            payload = json.dumps({
                "platform": "tiktok",
                "cookies": json.dumps([{"name": "sessionid", "value": "api_tt_val", "domain": ".tiktok.com", "path": "/"}])
            }).encode("utf-8")
            req = urllib.request.Request(save_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertEqual(data.get("count"), 1)

            # 3. GET /api/export-cookies
            export_url = f"http://127.0.0.1:{test_port}/api/export-cookies"
            with urllib.request.urlopen(export_url, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                exported_data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("cookies", exported_data)
                self.assertEqual(len(exported_data["cookies"]), 1)

            # 4. POST /api/save-cookies (body rỗng -> 400)
            req_empty = urllib.request.Request(save_url, data=b"{}", headers={"Content-Type": "application/json"})
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_empty, timeout=5)
            self.assertEqual(ctx.exception.code, 400)

            # 5. POST /api/clear-cookies
            clear_url = f"http://127.0.0.1:{test_port}/api/clear-cookies"
            clear_payload = json.dumps({"platform": "all"}).encode("utf-8")
            req_clear = urllib.request.Request(clear_url, data=clear_payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req_clear, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))

        finally:
            server.shutdown()
            server.server_close()

    def test_launch_windows_browser(self):
        with patch("shutil.which", return_value="/mnt/c/Windows/explorer.exe"), \
             patch("subprocess.Popen") as mock_popen:
            result = auto_publisher.launch_windows_browser("http://localhost:8080#accounts")
            self.assertTrue(result)
            mock_popen.assert_called_once()

    def test_parse_cookies_netscape_httponly(self):
        """Kiểm tra parse định dạng Netscape có tiền tố #HttpOnly_ cho cookie phiên."""
        netscape_text = (
            "# Netscape HTTP Cookie File\n"
            "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t1999999999\tsessionid\tsecret_tt_val\n"
            "#HttpOnly_.facebook.com\tTRUE\t/\tTRUE\t1999999999\txs\tsecret_fb_token\n"
            "# Regular comment\n"
            ".facebook.com\tTRUE\t/\tTRUE\t1999999999\tc_user\t100099999\n"
        )
        parsed = auto_publisher.parse_cookies_input(netscape_text)
        self.assertEqual(len(parsed), 3)
        tt_c = next(c for c in parsed if c["name"] == "sessionid")
        self.assertEqual(tt_c["value"], "secret_tt_val")
        self.assertTrue(tt_c["httpOnly"])
        self.assertEqual(tt_c["domain"], ".tiktok.com")

        fb_xs = next(c for c in parsed if c["name"] == "xs")
        self.assertTrue(fb_xs["httpOnly"])

    def test_parse_cookies_key_value_dict(self):
        """Kiểm tra parse dict dạng key-value đơn giản {name: value}."""
        raw_dict = {
            "sessionid": "val_123",
            "ttwid": "val_456"
        }
        parsed = auto_publisher.parse_cookies_input(raw_dict)
        self.assertEqual(len(parsed), 2)
        domains = {c["domain"] for c in parsed}
        self.assertIn(".tiktok.com", domains)

    def test_parse_cookies_domain_inference(self):
        """Kiểm tra tự động nhận diện domain cho chuỗi header khi không truyền default_domain."""
        fb_header = "c_user=1000999; xs=fb_secret_token"
        parsed = auto_publisher.parse_cookies_input(fb_header)
        self.assertEqual(len(parsed), 2)
        for c in parsed:
            self.assertEqual(c["domain"], ".facebook.com")

        yt_header = "LOGIN_INFO=yt_token; SID=yt_sid"
        parsed_yt = auto_publisher.parse_cookies_input(yt_header)
        self.assertEqual(len(parsed_yt), 2)
        for c in parsed_yt:
            self.assertEqual(c["domain"], ".youtube.com")

    def test_save_cookies_custom_target_file(self):
        """Kiểm tra lưu cookie vào file chỉ định không bị ảnh hưởng bởi file mặc định."""
        custom_file = Path(self.test_dir) / "custom_auth.json"
        c1 = [{"name": "custom_1", "value": "val1", "domain": ".tiktok.com", "path": "/"}]
        auto_publisher.save_cookies(c1, target_file=custom_file)

        c2 = [{"name": "custom_2", "value": "val2", "domain": ".tiktok.com", "path": "/"}]
        auto_publisher.save_cookies(c2, target_file=custom_file, merge=True)

        data = json.loads(custom_file.read_text())["cookies"]
        self.assertEqual(len(data), 2)
        names = {c["name"] for c in data}
        self.assertEqual(names, {"custom_1", "custom_2"})

    def test_clear_cookies_sync_cookies_file(self):
        """Kiểm tra clear_cookies xóa và đồng bộ cả khi cookies.json đang tồn tại."""
        self.test_cookies_file.write_text(json.dumps([
            {"name": "sessionid", "value": "tt_1", "domain": ".tiktok.com", "path": "/"},
            {"name": "c_user", "value": "fb_1", "domain": ".facebook.com", "path": "/"}
        ]), encoding="utf-8")
        self.test_auth_state_file.write_text(json.dumps({
            "cookies": [{"name": "sessionid", "value": "tt_1", "domain": ".tiktok.com", "path": "/"}],
            "origins": []
        }), encoding="utf-8")

        # Xóa tiktok
        auto_publisher.clear_cookies("tiktok")
        loaded = auto_publisher.load_saved_cookies()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "c_user")

    async def test_safe_add_cookies_batch_fallback(self):
        """Kiểm tra safe_add_cookies tự động fallback nạp từng cookie nếu nạp batch thất bại."""
        mock_context = MagicMock()
        async def mock_add_cookies(cookies_list):
            if len(cookies_list) > 1:
                raise Exception("Batch failed due to invalid cookie")
            if cookies_list[0].get("name") == "invalid":
                raise Exception("Malformed cookie")
            return None

        mock_context.add_cookies = AsyncMock(side_effect=mock_add_cookies)

        cookies = [
            {"name": "good1", "value": "v1", "domain": ".tiktok.com", "path": "/"},
            {"name": "invalid", "value": "bad", "domain": ".tiktok.com", "path": "/"},
            {"name": "good2", "value": "v2", "domain": ".tiktok.com", "path": "/"}
        ]
        success_count = await auto_publisher.safe_add_cookies(mock_context, cookies)
        self.assertEqual(success_count, 2)

    async def test_login_setup_execution(self):
        """Kiểm tra login_setup chạy trơn tru không phát sinh TypeError hay Exception."""
        # Giả lập trạng thái đã đăng nhập để login_setup thoát ngay
        with patch("auto_publisher.check_auth_status", return_value={
            "all_authenticated": True,
            "ready_count": 3,
            "platforms": {
                "youtube": {"name": "YouTube", "authenticated": True, "details": "OK"},
                "tiktok": {"name": "TikTok", "authenticated": True, "details": "OK"},
                "facebook": {"name": "Facebook", "authenticated": True, "details": "OK"}
            }
        }), patch("auto_publisher.launch_windows_browser", return_value=True), \
           patch("auto_publisher.start_dashboard_server"), \
           patch("sys.stdin.isatty", return_value=False):
            await auto_publisher.login_setup()

    def test_dashboard_download_and_open_endpoints(self):
        """Kiểm tra các endpoint tải script helper và mở browser trên Dashboard."""
        test_port = 18092
        server = auto_publisher.ReusableHTTPServer(("127.0.0.1", test_port), auto_publisher.DashboardHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            # 1. GET /login-helper.bat
            with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/login-helper.bat", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                bat_code = resp.read().decode("utf-8")
                self.assertIn("TRỢ LÝ ĐĂNG NHẬP", bat_code)
                self.assertIn("tiktok.com", bat_code)

            # 2. GET /login-helper.ps1
            with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/login-helper.ps1", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                ps_code = resp.read().decode("utf-8")
                self.assertIn("Start-Process", ps_code)

            # 3. POST /api/open-browser
            with patch("auto_publisher.launch_windows_browser", return_value=True):
                req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/open-browser", data=b"{}", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    data = json.loads(resp.read().decode("utf-8"))
                    self.assertTrue(data.get("success"))

        finally:
            server.shutdown()
            server.server_close()

    def test_deploy_windows_desktop_helper(self):
        """Kiểm tra tự động tạo file AutoPublisher_Login.bat trên desktop giả lập."""
        fake_users = Path(self.test_dir) / "Users"
        fake_desktop = fake_users / "TestUser" / "Desktop"
        fake_desktop.mkdir(parents=True, exist_ok=True)

        with patch("pathlib.Path.exists", autospec=True) as mock_exists, \
             patch("pathlib.Path.iterdir", autospec=True) as mock_iterdir:
            def fake_exists_func(p):
                p_str = str(p)
                if p_str == "/mnt/c/Users" or "Desktop" in p_str:
                    return True
                return False

            def fake_iterdir_func(p):
                if str(p) == "/mnt/c/Users":
                    fake_folder = MagicMock()
                    fake_folder.is_dir.return_value = True
                    fake_folder.name = "TestUser"
                    fake_folder.__truediv__.return_value = fake_desktop
                    return [fake_folder]
                return []

            mock_exists.side_effect = fake_exists_func
            mock_iterdir.side_effect = fake_iterdir_func
            res = auto_publisher.deploy_windows_desktop_helper(port=8080)
            self.assertIsNotNone(res)
            self.assertIn("AutoPublisher_Login.bat", res)

    def test_generate_reel_caption_offline_fallback(self):
        """Kiểm tra bộ tạo tiêu đề & hashtag ngoại tuyến khi không có Gemini."""
        story = {
            "title": "Tiểu Minh và bài văn tả người hùng",
            "cards": [
                {"lines": [{"text": "Trong giờ tập làm văn, cô giáo yêu cầu cả lớp viết về một người hùng."}]},
                {"lines": [{"text": "Tiểu Minh ngây thơ đáp: Em tả lại cảnh bố em đi rửa bát đấy ạ!"}]}
            ]
        }
        res = auto_publisher.generate_reel_caption(story, api_key="invalid_dummy_key")
        self.assertIn("title", res)
        self.assertIn("hook", res)
        self.assertIn("hashtags", res)
        self.assertIn("youtube_title", res)
        self.assertIn("tiktok_caption", res)
        self.assertIn("caption", res)

        # Tiêu đề rõ ràng, dưới 60 ký tự, không chứa hashtag
        self.assertLessEqual(len(res["title"]), 60)
        self.assertNotIn("#", res["title"])
        self.assertEqual(res["title"], "Tiểu Minh và bài văn tả người hùng")

        # YouTube Shorts title có chứa #Shorts
        self.assertIn("#Shorts", res["youtube_title"])

        # Hashtags phong phú
        for tag in ["#shorts", "#reels", "#tiktok", "#haihuoc", "#xuhuong", "#chuyenvuithoret"]:
            self.assertIn(tag, res["hashtags"])
            self.assertIn(tag, res["caption"])

    def test_generate_reel_caption_theme_inference(self):
        """Kiểm tra tự động suy đoán tiêu đề giật tít theo chủ đề câu chuyện."""
        # Chủ đề làm người tốt / xe buýt
        story_good_guy = {
            "title": "Kịch bản viral",
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định thử một lần làm người tốt bụng nhường ghế trên xe buýt."}]}
            ]
        }
        res_gg = auto_publisher.generate_reel_caption(story_good_guy, api_key="invalid_dummy_key")
        self.assertEqual(res_gg["title"], "Cái kết đắng khi thử làm người tốt")
        self.assertNotIn("#", res_gg["title"])

        # Chủ đề salon / cắt tóc
        story_salon = {
            "title": "",
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định ra tiệm salon lớn nhất phố để đổi một kiểu tóc thật ngầu."}]}
            ]
        }
        res_salon = auto_publisher.generate_reel_caption(story_salon, api_key="invalid_dummy_key")
        self.assertEqual(res_salon["title"], "Bài học nhớ đời khi đi đổi kiểu tóc")

        # Chủ đề khóa học giảm cân
        story_diet = {
            "title": None,
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định tham gia một khóa học trực tuyến về phương pháp giảm cân khoa học."}]}
            ]
        }
        res_diet = auto_publisher.generate_reel_caption(story_diet, api_key="invalid_dummy_key")
        self.assertEqual(res_diet["title"], "Cú lừa ngoạn mục từ khóa học giảm cân")

    def test_generate_reel_caption_with_gemini_mock(self):
        """Kiểm tra tích hợp Gemini AI tạo tiêu đề & hook triệu view."""
        story = {
            "title": "Kịch bản viral",
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định đi bơi giữa mùa đông lạnh giá."}]},
                {"lines": [{"text": "Vừa chạm chân xuống nước thì phát hiện hồ bơi đã cạn sạch từ tuần trước."}]}
            ]
        }
        mock_response = MagicMock()
        mock_response.parsed = {
            "title": "Pha bơi lội bất ổn nhất mùa đông",
            "hook": "Trời lạnh âm mười độ mà vẫn đam mê bơi lội và cái kết vỡ mộng!"
        }
        mock_response.text = json.dumps(mock_response.parsed)

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_client

            res = auto_publisher.generate_reel_caption(story, api_key="test_api_key_123")
            self.assertEqual(res["title"], "Pha bơi lội bất ổn nhất mùa đông")
            self.assertIn("Trời lạnh âm mười độ", res["hook"])
            self.assertIn("#Shorts", res["youtube_title"])
            self.assertIn("#chuyenvuithoret", res["hashtags"])

    async def test_upload_to_youtube_shorts_login_redirect_detection(self):
        """Kiểm tra upload_to_youtube_shorts phát hiện chuyển hướng trang login và trả về thông báo lỗi rõ ràng."""
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()
        mock_page.url = "https://accounts.google.com/v3/signin/identifier?continue=https://studio.youtube.com"

        mock_context = MagicMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "LOGIN_INFO", "domain": ".youtube.com", "value": "xyz"}
        ])
        mock_page.context = mock_context

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_youtube_shorts(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Tiêu đề Shorts"
            )
            self.assertIn("Cookie YouTube hết hạn hoặc chưa đăng nhập", result)

    async def test_upload_to_youtube_shorts_no_cookies_skip(self):
        """Kiểm tra upload_to_youtube_shorts bỏ qua khi phiên trình duyệt không có cookie YouTube nào."""
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()

        mock_context = MagicMock()
        # Không có cookie youtube.com hoặc google.com nào
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "sessionid", "domain": ".tiktok.com", "value": "123"}
        ])
        mock_page.context = mock_context

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_youtube_shorts(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Tiêu đề Shorts"
            )
            self.assertIn("Chưa có cookie YouTube", result)

    async def test_dismiss_youtube_modals(self):
        """Kiểm tra dismiss_youtube_modals xử lý các pop-up và hộp thoại tạo kênh."""
        mock_page = MagicMock()
        mock_page.keyboard.press = AsyncMock()

        mock_button = MagicMock()
        mock_button.count = AsyncMock(return_value=1)
        mock_button.is_visible = AsyncMock(return_value=True)
        mock_button.click = AsyncMock()
        mock_button.nth = MagicMock(return_value=mock_button)

        mock_dlg = MagicMock()
        mock_dlg.count = AsyncMock(return_value=1)
        mock_dlg.locator = MagicMock(return_value=mock_button)

        def mock_locator(selector):
            if "channel-creation" in selector:
                return mock_dlg
            return mock_button

        mock_page.locator = MagicMock(side_effect=mock_locator)

        with patch("asyncio.sleep", AsyncMock()):
            await auto_publisher.dismiss_youtube_modals(mock_page)
            self.assertTrue(mock_page.keyboard.press.called)

    def test_generate_reel_caption_none_and_edge_cases(self):
        """Kiểm tra generate_reel_caption xử lý an toàn khi story là None, rỗng hoặc tiêu đề chứa hashtag."""
        # 1. story là None
        res_none = auto_publisher.generate_reel_caption(None, api_key="invalid_dummy_key")
        self.assertIn("title", res_none)
        self.assertLessEqual(len(res_none["title"]), 60)
        self.assertNotIn("#", res_none["title"])
        self.assertIn("#Shorts", res_none["youtube_title"])

        # 2. story rỗng {}
        res_empty = auto_publisher.generate_reel_caption({}, api_key="invalid_dummy_key")
        self.assertIn("title", res_empty)
        self.assertLessEqual(len(res_empty["title"]), 60)

        # 3. story có tiêu đề chứa sẵn hashtag và dài
        story_tags = {
            "title": "Chuyện tiệm cắt tóc siêu bất ổn #shorts #reels #viral #haihuoc",
            "cards": []
        }
        res_tags = auto_publisher.generate_reel_caption(story_tags, api_key="invalid_dummy_key")
        self.assertNotIn("#", res_tags["title"])
        self.assertIn("Chuyện tiệm cắt tóc", res_tags["title"])
        self.assertLessEqual(len(res_tags["title"]), 60)

        # 4. story không có cards nhưng có content/text fallback
        story_content = {
            "title": "",
            "content": "Hôm nay tôi quyết định tham gia một khóa học giảm cân cấp tốc."
        }
        res_content = auto_publisher.generate_reel_caption(story_content, api_key="invalid_dummy_key")
        self.assertEqual(res_content["title"], "Cú lừa ngoạn mục từ khóa học giảm cân")

    async def test_upload_to_youtube_shorts_empty_context_cookies_skip(self):
        """Kiểm tra upload_to_youtube_shorts bỏ qua ngay khi danh sách context.cookies hoàn toàn rỗng."""
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()

        mock_context = MagicMock()
        mock_context.cookies = AsyncMock(return_value=[])
        mock_page.context = mock_context

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_youtube_shorts(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Tiêu đề Shorts"
            )
            self.assertIn("Chưa có cookie YouTube", result)
            self.assertFalse(mock_page.goto.called)

    async def test_upload_to_youtube_shorts_generic_only_cookies_skip(self):
        """Kiểm tra upload_to_youtube_shorts bỏ qua khi chỉ có cookie generic (PREF, YSC) mà không có auth key."""
        mock_page = MagicMock()
        mock_page.goto = AsyncMock()

        mock_context = MagicMock()
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "PREF", "domain": ".youtube.com", "value": "f1=50000000"},
            {"name": "VISITOR_INFO1_LIVE", "domain": ".youtube.com", "value": "abc"}
        ])
        mock_page.context = mock_context

        with patch("asyncio.sleep", AsyncMock()):
            result = await auto_publisher.upload_to_youtube_shorts(
                mock_page,
                Path("/tmp/fake_video.mp4"),
                "Tiêu đề Shorts"
            )
            self.assertIn("Chưa có cookie YouTube", result)
            self.assertFalse(mock_page.goto.called)

    def test_verify_youtube_session_online_logic(self):
        """Kiểm tra logic verify_youtube_session_online với mock redirect HTTP và cache."""
        auto_publisher._YT_VERIFY_CACHE.clear()

        # Khi không có cookie
        valid, msg = auto_publisher.verify_youtube_session_online([])
        self.assertFalse(valid)
        self.assertIn("Chưa có cookie", msg)

        # Mock chuyển hướng tới Google sign-in
        mock_err = urllib.error.HTTPError(
            url="https://studio.youtube.com",
            code=302,
            msg="Found",
            hdrs={"Location": "https://accounts.google.com/ServiceLogin?service=youtube"},
            fp=None
        )
        fake_cookies = [{"name": "LOGIN_INFO", "domain": ".youtube.com", "value": "fake_login"}]
        with patch("urllib.request.build_opener") as mock_opener:
            mock_inst = MagicMock()
            mock_inst.open.side_effect = mock_err
            mock_opener.return_value = mock_inst

            valid, msg = auto_publisher.verify_youtube_session_online(fake_cookies)
            self.assertFalse(valid)
            self.assertIn("Cookie YouTube hết hạn hoặc chưa đăng nhập", msg)

            # Lần gọi tiếp theo lấy từ cache (không gọi urllib)
            mock_inst.open.reset_mock()
            valid_c, msg_c = auto_publisher.verify_youtube_session_online(fake_cookies)
            self.assertFalse(valid_c)
            self.assertFalse(mock_inst.open.called)

    def test_clear_cookies_cleans_profile_sqlite(self):
        """Kiểm tra clear_cookies xóa triệt để cả trong SQLite browser_profile/Default/Cookies."""
        import sqlite3
        profile_db_dir = self.test_profile_dir / "Default"
        profile_db_dir.mkdir(parents=True, exist_ok=True)
        db_path = profile_db_dir / "Cookies"

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("CREATE TABLE cookies (host_key TEXT, name TEXT)")
        cur.execute("INSERT INTO cookies VALUES ('.youtube.com', 'LOGIN_INFO')")
        cur.execute("INSERT INTO cookies VALUES ('.tiktok.com', 'sessionid')")
        conn.commit()
        conn.close()

        # Xóa cookie youtube
        auto_publisher.clear_cookies(platform="youtube")

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT host_key, name FROM cookies")
        rows = cur.fetchall()
        conn.close()

        # Chỉ còn cookie tiktok, youtube đã bị xóa
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], ".tiktok.com")

    def test_clean_word_truncation_no_split_words(self):
        """Kiểm tra cắt tiêu đề > 60 ký tự theo ranh giới từ, không xé đôi từ."""
        long_story = {
            "title": "Hôm nay tôi quyết định tham gia một chuyến du lịch thám hiểm rừng sâu vô cùng kỳ lạ và bất ngờ",
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định tham gia một chuyến du lịch thám hiểm rừng sâu vô cùng kỳ lạ."}]}
            ]
        }
        res = auto_publisher.generate_reel_caption(long_story, api_key="invalid_dummy_key")
        title = res["title"]
        self.assertLessEqual(len(title), 60)
        self.assertNotIn("#", title)
        if title.endswith("..."):
            # Từ trước dấu ... phải là từ nguyên vẹn
            stem = title[:-3].strip()
            self.assertFalse(stem.endswith(" t"))  # Không cắt dở chữ cái
            self.assertTrue(len(stem.split()[-1]) >= 2)

    def test_generate_offline_caption_handles_sentence_raw_title(self):
        """Kiểm tra _generate_offline_caption xử lý tiêu đề raw bắt đầu bằng 'Hôm nay tôi quyết định'."""
        story = {
            "title": "Hôm nay tôi quyết định đi mua một chú chó cảnh thật đắt tiền",
            "cards": [
                {"lines": [{"text": "Hôm nay tôi quyết định đi mua một chú chó cảnh thật đắt tiền."}]},
                {"lines": [{"text": "Về đến nhà nó sủa tiếng meo làm cả nhà ngơ ngác."}]}
            ]
        }
        res = auto_publisher.generate_reel_caption(story, api_key="invalid_dummy_key")
        self.assertLessEqual(len(res["title"]), 60)
        self.assertNotIn("#", res["title"])
        self.assertNotIn("...", res["title"])
        # Heuristic chó cảnh hoặc biến đổi 'Cái kết...'
        self.assertTrue(
            "chó" in res["title"].lower() or "cái kết" in res["title"].lower()
        )

    def test_verify_cache_cleared_on_save_and_clear(self):
        """Kiểm tra _YT_VERIFY_CACHE được xóa sạch khi lưu hoặc xóa cookie."""
        auto_publisher._YT_VERIFY_CACHE[12345] = (time.time(), True, "dummy")
        self.assertIn(12345, auto_publisher._YT_VERIFY_CACHE)

        auto_publisher.save_cookies([{"name": "LOGIN_INFO", "value": "123", "domain": ".youtube.com"}])
        self.assertEqual(len(auto_publisher._YT_VERIFY_CACHE), 0)

        auto_publisher._YT_VERIFY_CACHE[99999] = (time.time(), False, "expired")
        self.assertIn(99999, auto_publisher._YT_VERIFY_CACHE)

        auto_publisher.clear_cookies("youtube")
        self.assertEqual(len(auto_publisher._YT_VERIFY_CACHE), 0)

    def test_render_platform_cell_shows_retry_button_on_error(self):
        """Kiểm tra render_platform_cell hiển thị nút Đăng lại khi có lỗi và có file video."""
        test_video = self.test_published_dir / "test_retry.mp4"
        test_video.write_bytes(b"dummy")

        record = {
            "id": 99,
            "video_file": "test_retry.mp4",
            "youtube": "❌ Lỗi (Cookie hết hạn)",
            "tiktok": "✅ Đã đăng",
            "facebook": "⏭️ Bỏ qua (Chưa có cookie)"
        }

        # YouTube có lỗi -> Phải có nút Đăng lại
        yt_cell = auto_publisher.render_platform_cell(record, "youtube")
        self.assertIn("btn-retry", yt_cell)
        self.assertIn("retryPublish(99, 'youtube')", yt_cell)
        self.assertIn("🔄 Đăng lại", yt_cell)

        # TikTok đã đăng -> Không hiển thị nút Đăng lại
        tt_cell = auto_publisher.render_platform_cell(record, "tiktok")
        self.assertNotIn("btn-retry", tt_cell)

        # Facebook bị bỏ qua -> Phải có nút Đăng lại
        fb_cell = auto_publisher.render_platform_cell(record, "facebook")
        self.assertIn("btn-retry", fb_cell)
        self.assertIn("retryPublish(99, 'facebook')", fb_cell)

        # Nếu file video không tồn tại -> Không hiển thị nút Đăng lại
        record_no_file = {
            "id": 100,
            "video_file": "non_existent.mp4",
            "youtube": "❌ Lỗi (Cookie hết hạn)"
        }
        no_file_cell = auto_publisher.render_platform_cell(record_no_file, "youtube")
        self.assertNotIn("btn-retry", no_file_cell)

    async def test_retry_publish_single_dry_run(self):
        """Kiểm tra hàm retry_publish_single ở chế độ dry-run cập nhật trạng thái chuẩn xác."""
        test_video = self.test_published_dir / "short_video_99.mp4"
        test_video.write_bytes(b"dummy_mp4")

        rec = {
            "id": 99,
            "created_at": "12:00 - 26/10/2026",
            "title": "Bài kiểm tra retry publish",
            "video_file": "short_video_99.mp4",
            "youtube": "❌ Lỗi cũ",
            "tiktok": "✅ Đã đăng",
            "facebook": "⏭️ Bỏ qua cũ",
            "overall_status": "Hoàn tất"
        }
        auto_publisher.save_status_record(rec)

        res = await auto_publisher.retry_publish_single(99, "youtube", dry_run=True)
        self.assertTrue(res["success"])

        updated = auto_publisher.load_status_list()
        target = next((item for item in updated if item["id"] == 99), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["youtube"], "✅ Đã đăng")

    def test_api_retry_publish_endpoint(self):
        """Kiểm tra gọi endpoint /api/retry-publish qua HTTP."""
        test_port = 18099
        server = auto_publisher.ReusableHTTPServer(("127.0.0.1", test_port), auto_publisher.DashboardHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            # Tạo record giả
            rec = {
                "id": 88,
                "created_at": "12:00 - 26/10/2026",
                "title": "Video test retry API",
                "video_file": "short_88.mp4",
                "youtube": "❌ Lỗi",
                "tiktok": "❌ Lỗi",
                "facebook": "❌ Lỗi",
                "overall_status": "Lỗi"
            }
            auto_publisher.save_status_record(rec)

            # Gọi POST /api/retry-publish
            req_data = json.dumps({"id": 88, "platform": "youtube"}).encode("utf-8")
            req = urllib.request.Request(
                f"http://127.0.0.1:{test_port}/api/retry-publish",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("success"))
                self.assertIn("video #88", data.get("message"))

            # Kiểm tra trạng thái đã chuyển thành "⏳ Đang đăng lại..."
            status_list = auto_publisher.load_status_list()
            target = next((item for item in status_list if item["id"] == 88), None)
            self.assertEqual(target["youtube"], "⏳ Đang đăng lại...")

        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()


