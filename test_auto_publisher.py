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

        self.test_status_file = Path(self.test_dir) / "test_publish_status.json"
        self.test_profile_dir = Path(self.test_dir) / "test_browser_profile"
        self.test_published_dir = Path(self.test_dir) / "test_published_videos"
        self.test_published_dir.mkdir(parents=True, exist_ok=True)

        auto_publisher.STATUS_FILE = self.test_status_file
        auto_publisher.PROFILE_DIR = self.test_profile_dir
        auto_publisher.PUBLISHED_DIR = self.test_published_dir

    def tearDown(self):
        auto_publisher.STATUS_FILE = self.original_status_file
        auto_publisher.PROFILE_DIR = self.original_profile_dir
        auto_publisher.PUBLISHED_DIR = self.original_published_dir
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


if __name__ == "__main__":
    unittest.main()
