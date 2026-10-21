import json
import os
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from pydantic import ValidationError

from threads_scraper import (
    ThreadCard,
    StorySelection,
    load_history,
    save_history,
    select_and_format_story,
    get_automated_story,
    normalize_vietnamese_text,
    HISTORY_FILE,
)


class TestThreadsScraper(unittest.TestCase):
    def setUp(self):
        # Đảm bảo môi trường sạch cho test history
        self.test_history_file = "test_story_history.json"
        self._orig_history_file = HISTORY_FILE
        # Thay thế file history tạm thời
        import threads_scraper
        threads_scraper.HISTORY_FILE = self.test_history_file
        if Path(self.test_history_file).exists():
            os.remove(self.test_history_file)

    def tearDown(self):
        import threads_scraper
        threads_scraper.HISTORY_FILE = self._orig_history_file
        if Path(self.test_history_file).exists():
            os.remove(self.test_history_file)

    def test_thread_card_schema_valid(self):
        card = ThreadCard(
            card_id=1,
            time_ago="2 giờ",
            likes="15,4K",
            replies="320",
            lines=["Câu 1", "Câu 2", "Câu 3"],
        )
        self.assertEqual(card.card_id, 1)
        self.assertEqual(len(card.lines), 3)

    def test_story_selection_schema_valid(self):
        data = {
            "selected_post_index": 0,
            "humor_score": 9,
            "cards": [
                {
                    "card_id": 1,
                    "time_ago": "1 giờ",
                    "likes": "10K",
                    "replies": "150",
                    "lines": ["Đang đi dạo ngoài công viên.", "Bỗng thấy một chú cún chạy lại gần.", "Nó nhìn tôi đắm đuối."],
                },
                {
                    "card_id": 2,
                    "time_ago": "1 giờ",
                    "likes": "10K",
                    "replies": "150",
                    "lines": ["Tôi tưởng nó thích mình.", "Định giơ tay vuốt ve làm quen.", "Hóa ra nó chỉ muốn cướp cây xúc xích trên tay."],
                },
            ],
        }
        selection = StorySelection(**data)
        self.assertEqual(selection.humor_score, 9)
        self.assertEqual(len(selection.cards), 2)
        self.assertEqual(selection.cards[1].lines[2], "Hóa ra nó chỉ muốn cướp cây xúc xích trên tay.")

    def test_story_selection_invalid_missing_fields(self):
        with self.assertRaises(ValidationError):
            StorySelection(selected_post_index=0)

    def test_save_and_load_history(self):
        self.assertEqual(load_history(), [])
        save_history("Mẩu chuyện 1")
        self.assertEqual(load_history(), ["Mẩu chuyện 1"])
        save_history("Mẩu chuyện 2")
        self.assertEqual(load_history(), ["Mẩu chuyện 1", "Mẩu chuyện 2"])

    def test_history_cap_at_50(self):
        for i in range(60):
            save_history(f"Story #{i}")
        history = load_history()
        self.assertEqual(len(history), 50)
        self.assertEqual(history[0], "Story #10")
        self.assertEqual(history[-1], "Story #59")

    def test_load_history_handles_corrupt_file(self):
        with open(self.test_history_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json content :::")
        self.assertEqual(load_history(), [])

    def test_select_and_format_story_missing_api_key_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                select_and_format_story(raw_posts=["Test post"], api_key=None)
            self.assertIn("Chưa cấu hình GEMINI_API_KEY", str(ctx.exception))

    @patch("threads_scraper.genai.Client")
    def test_select_and_format_story_with_mock_gemini(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_parsed = StorySelection(
            selected_post_index=0,
            humor_score=8,
            cards=[
                ThreadCard(
                    card_id=1,
                    time_ago="2 giờ",
                    likes="12K",
                    replies="200",
                    lines=["Mở bài 1", "Mở bài 2", "Mở bài 3"],
                ),
                ThreadCard(
                    card_id=2,
                    time_ago="2 giờ",
                    likes="12K",
                    replies="200",
                    lines=["Thân bài", "Kết bài", "Cú twist cười nghiêng ngả"],
                ),
            ],
        )

        mock_response = MagicMock()
        mock_response.parsed = mock_parsed
        mock_client.models.generate_content.return_value = mock_response

        result = select_and_format_story(
            raw_posts=["Hôm nay gặp chuyện lạ lắm..."],
            api_key="mock_key",
        )

        self.assertIn("cards", result)
        self.assertEqual(len(result["cards"]), 2)
        self.assertEqual(result["humor_score"], 8)
        # Kiểm tra đã lưu câu mở đầu vào lịch sử
        self.assertIn("Mở bài 1", load_history())

    def test_normalize_vietnamese_text_expands_abbreviations(self):
        sample = "Tôi ko hiểu sao hlv bảo dc vs lại làm j thế"
        normalized = normalize_vietnamese_text(sample)
        self.assertEqual(normalized, "Tôi không hiểu sao huấn luyện viên bảo được với lại làm gì thế")

        # Test case preservation
        upper_sample = "KO DC HLV"
        self.assertEqual(normalize_vietnamese_text(upper_sample), "KHÔNG ĐƯỢC HUẤN LUYỆN VIÊN")

    @patch("threads_scraper.scrape_threads_posts")
    def test_get_automated_story_empty_raises_runtime_error(self, mock_scrape):
        mock_scrape.return_value = []
        import asyncio
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(get_automated_story(["https://example.com"]))
        self.assertIn("Chưa quét được bài từ Threads", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
