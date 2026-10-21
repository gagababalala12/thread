import unittest
from pathlib import Path
from threads_video_builder import (
    build_threads_html,
    build_watermark_html,
    CONFIG,
    clip_subclip,
    clip_set_start,
    clip_set_duration,
    clip_set_position,
    crop_to_9_16,
)
from moviepy import ColorClip


class TestThreadsVideoBuilder(unittest.TestCase):
    def test_build_threads_html(self):
        html = build_threads_html(
            username="test_user",
            avatar_url="https://example.com/avatar.png",
            time_ago="2 giờ",
            lines=["Dòng 1", "Dòng 2"],
            likes="10K",
            replies="500",
        )
        self.assertIn("test_user", html)
        self.assertIn("Dòng 1", html)
        self.assertIn("Dòng 2", html)
        self.assertIn("10K", html)
        self.assertIn("500", html)
        self.assertIn('id="card"', html)

    def test_build_watermark_html(self):
        html = build_watermark_html("Watermark Test")
        self.assertIn("Watermark Test", html)
        self.assertIn('id="wm"', html)

    def test_moviepy_helper_methods(self):
        clip = ColorClip(size=(400, 300), color=(100, 100, 100), duration=5)
        c_sub = clip_subclip(clip, 1, 3)
        self.assertEqual(c_sub.duration, 2)

        c_start = clip_set_start(clip, 2.5)
        self.assertEqual(c_start.start, 2.5)

        c_dur = clip_set_duration(clip, 3)
        self.assertEqual(c_dur.duration, 3)

        c_pos = clip_set_position(clip, ("center", "center"))
        self.assertIsNotNone(c_pos)

    def test_crop_to_9_16(self):
        clip = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=2)
        cropped = crop_to_9_16(clip, target_w=1080, target_h=1920)
        self.assertEqual(cropped.size, (1080, 1920))


    def test_threads_card_size_and_font(self):
        html = build_threads_html(
            username="test_user",
            avatar_url="https://example.com/avatar.png",
            time_ago="2 giờ",
            lines=["Dòng 1", "Dòng 2"],
            likes="10K",
            replies="500",
        )
        self.assertIn("width: 960px;", html)
        self.assertIn("font-size: 40px;", html)
        self.assertIn("font-weight: 500;", html)

    def test_progressive_reveal_mask_opacity(self):
        lines = ["Câu mở đầu số 1", "Câu phát triển số 2", "Câu twist chốt hạ số 3"]
        # Step 1: visible_count = 1
        html_s1 = build_threads_html(
            username="u", avatar_url="a", time_ago="1h",
            lines=lines, likes="10K", replies="200", visible_count=1
        )
        self.assertIn('<p style="opacity: 1;">Câu mở đầu số 1</p>', html_s1)
        self.assertIn('<p style="opacity: 0;">Câu phát triển số 2</p>', html_s1)
        self.assertIn('<p style="opacity: 0;">Câu twist chốt hạ số 3</p>', html_s1)
        self.assertIn('class="actions" style="opacity: 0;"', html_s1)

        # Step 2: visible_count = 2
        html_s2 = build_threads_html(
            username="u", avatar_url="a", time_ago="1h",
            lines=lines, likes="10K", replies="200", visible_count=2
        )
        self.assertIn('<p style="opacity: 1;">Câu mở đầu số 1</p>', html_s2)
        self.assertIn('<p style="opacity: 1;">Câu phát triển số 2</p>', html_s2)
        self.assertIn('<p style="opacity: 0;">Câu twist chốt hạ số 3</p>', html_s2)
        self.assertIn('class="actions" style="opacity: 0;"', html_s2)

        # Step 3: visible_count = 3 (final line of card)
        html_s3 = build_threads_html(
            username="u", avatar_url="a", time_ago="1h",
            lines=lines, likes="10K", replies="200", visible_count=3
        )
        self.assertIn('<p style="opacity: 1;">Câu mở đầu số 1</p>', html_s3)
        self.assertIn('<p style="opacity: 1;">Câu phát triển số 2</p>', html_s3)
        self.assertIn('<p style="opacity: 1;">Câu twist chốt hạ số 3</p>', html_s3)
        self.assertIn('class="actions" style="opacity: 1;"', html_s3)

    def test_sample_stories_pool_and_vietnamese_quality(self):
        from threads_video_builder import SAMPLE_STORIES
        import re

        # Yêu cầu 1: Phải có ít nhất 5 câu chuyện cười học đường/gia đình
        self.assertGreaterEqual(len(SAMPLE_STORIES), 5)

        for story in SAMPLE_STORIES:
            self.assertIn("cards", story)
            self.assertEqual(len(story["cards"]), 2, "Mỗi câu chuyện phải có đúng 2 card")
            for card in story["cards"]:
                self.assertEqual(len(card["lines"]), 3, "Mỗi card phải có đúng 3 câu")
                for line in card["lines"]:
                    # Kiểm tra không có từ viết tắt cấm
                    lower_line = line.lower()
                    for forbidden in [r"\bko\b", r"\bdc\b", r"\bhlv\b", r"\bvs\b"]:
                        self.assertIsNone(
                            re.search(forbidden, lower_line),
                            f"Phát hiện từ viết tắt '{forbidden}' trong câu: {line}"
                        )
                    # Kiểm tra tiếng Việt có dấu
                    has_accent = any(c in "áàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ" for c in lower_line)
                    self.assertTrue(has_accent, f"Câu không có dấu tiếng Việt: {line}")


    def test_real_assets_present_and_valid(self):
        from pydub import AudioSegment
        from moviepy import VideoFileClip

        bg_path = Path("assets/background.mp4")
        pop_path = Path("assets/pop.mp3")
        final_sfx_path = Path("assets/final_sfx.mp3")

        self.assertTrue(bg_path.exists(), "assets/background.mp4 phải tồn tại")
        self.assertGreater(bg_path.stat().st_size, 5_000_000, "assets/background.mp4 phải là video thật (> 5MB)")

        with VideoFileClip(str(bg_path)) as v:
            self.assertEqual(v.size, [1080, 1920], "Video nền phải đúng độ phân giải 9:16 (1080x1920)")
            self.assertGreaterEqual(v.duration, 60, "Video nền phải có độ dài ít nhất 1 phút")

        self.assertTrue(pop_path.exists(), "assets/pop.mp3 phải tồn tại")
        self.assertGreater(pop_path.stat().st_size, 2000, "assets/pop.mp3 phải là âm thanh Bubble Pop thật (> 2KB)")
        pop_audio = AudioSegment.from_file(str(pop_path))
        self.assertGreater(len(pop_audio), 150, "assets/pop.mp3 thời lượng phải > 150ms")

        self.assertTrue(final_sfx_path.exists(), "assets/final_sfx.mp3 phải tồn tại")
        self.assertGreater(final_sfx_path.stat().st_size, 10000, "assets/final_sfx.mp3 phải là âm thanh meme thật (> 10KB)")
        sfx_audio = AudioSegment.from_file(str(final_sfx_path))
        self.assertGreater(len(sfx_audio), 800, "assets/final_sfx.mp3 thời lượng phải > 800ms")

    def test_card_height_invariance_across_reveal_steps(self):
        import asyncio
        from playwright.async_api import async_playwright
        from threads_video_builder import SAMPLE_STORIES

        async def verify_heights():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1080, "height": 1920})
                for story in SAMPLE_STORIES[:2]:
                    for card in story["cards"]:
                        heights = []
                        lines = card["lines"]
                        for v_count in range(1, len(lines) + 1):
                            html = build_threads_html(
                                "user", "avatar", card["time_ago"],
                                lines, card["likes"], card["replies"],
                                visible_count=v_count
                            )
                            await page.set_content(html)
                            box = await page.locator("#card").bounding_box()
                            heights.append(box["height"])
                        self.assertEqual(
                            len(set(heights)), 1,
                            f"Chiều cao card bị thay đổi giữa các bước (gây giật khung): {heights}"
                        )
                await browser.close()

        asyncio.run(verify_heights())


if __name__ == "__main__":
    unittest.main()
