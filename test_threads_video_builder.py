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


if __name__ == "__main__":
    unittest.main()
