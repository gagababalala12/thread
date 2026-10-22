import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import threading
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
        mock_page.goto = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.keyboard.type = AsyncMock()

        mock_input = MagicMock()
        mock_input.set_input_files = AsyncMock()

        mock_caption = MagicMock()
        mock_caption.count = AsyncMock(return_value=1)
        mock_caption.click = AsyncMock()

        mock_btn = MagicMock()
        mock_btn.click = AsyncMock()

        def locator_side_effect(selector):
            loc = MagicMock()
            if 'input[type="file"]' in selector:
                return mock_input
            elif 'contenteditable' in selector:
                loc.first = mock_caption
                return loc
            elif 'button' in selector:
                loc.last = mock_btn
                return loc
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


if __name__ == "__main__":
    unittest.main()

