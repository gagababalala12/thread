import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import os
import shutil
import tempfile
import urllib.request
import threading
from pathlib import Path
from http.server import HTTPServer

import auto_publisher


class TestAutoPublisher(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_status_file = auto_publisher.STATUS_FILE
        self.original_profile_dir = auto_publisher.PROFILE_DIR
        self.test_status_file = Path(self.test_dir) / "test_publish_status.json"
        self.test_profile_dir = Path(self.test_dir) / "test_browser_profile"
        auto_publisher.STATUS_FILE = self.test_status_file
        auto_publisher.PROFILE_DIR = self.test_profile_dir

    def tearDown(self):
        auto_publisher.STATUS_FILE = self.original_status_file
        auto_publisher.PROFILE_DIR = self.original_profile_dir
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

    def test_dashboard_http_server(self):
        # Chuẩn bị dữ liệu mẫu
        record = {
            "id": 42,
            "created_at": "18:00 - 22/10/2026",
            "title": "Kiểm thử Web Dashboard",
            "video_file": "test_video_42.mp4",
            "youtube": "✅ Đã đăng",
            "facebook": "✅ Đã đăng",
            "tiktok": "✅ Đã đăng",
            "overall_status": "Hoàn tất"
        }
        auto_publisher.save_status_record(record)

        # Khởi chạy server trên cổng ngẫu nhiên 18088
        test_port = 18088
        server = auto_publisher.ReusableHTTPServer(("127.0.0.1", test_port), auto_publisher.DashboardHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        try:
            url = f"http://127.0.0.1:{test_port}/"
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                content = response.read().decode("utf-8")
                self.assertIn("Trạm Kiểm Soát Auto-Threads Shorts", content)
                self.assertIn("Kiểm thử Web Dashboard", content)
                self.assertIn("#42", content)
                self.assertIn("test_video_42.mp4", content)
                self.assertIn("YouTube Shorts", content)
                self.assertIn("Facebook Reels", content)
                self.assertIn("TikTok", content)
        finally:
            server.shutdown()
            server.server_close()

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


if __name__ == "__main__":
    unittest.main()
