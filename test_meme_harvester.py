import unittest
from pathlib import Path
from meme_harvester import (
    BGM_QUERIES,
    SFX_QUERIES,
    VIDEO_MEME_QUERIES,
    get_media_duration,
    trim_media_file,
    harvest_all,
)


class TestMemeHarvester(unittest.TestCase):
    def test_queries_structure(self):
        self.assertGreaterEqual(len(BGM_QUERIES), 2)
        for bgm in BGM_QUERIES:
            self.assertIn("name", bgm)
            self.assertIn("query", bgm)

        expected_sfx = ["huh.mp3", "cai_gi_do.mp3", "laugh.mp3", "vine_boom.mp3", "wow.mp3"]
        for sfx_name in expected_sfx:
            self.assertIn(sfx_name, SFX_QUERIES)

        self.assertGreaterEqual(len(VIDEO_MEME_QUERIES), 2)
        for vm in VIDEO_MEME_QUERIES:
            self.assertIn("name", vm)
            self.assertIn("query", vm)

    def test_harvested_bgm_assets_validity(self):
        bgm_dir = Path("assets/bgm")
        self.assertTrue(bgm_dir.exists(), "Thư mục assets/bgm phải tồn tại")
        bgm_files = list(bgm_dir.glob("*.mp3"))
        self.assertGreaterEqual(len(bgm_files), 2, "Cần có ít nhất 2 bài BGM")
        for f in bgm_files:
            dur = get_media_duration(f)
            self.assertGreaterEqual(dur, 30.0, f"BGM {f.name} phải >= 30s (hiện tại: {dur:.2f}s)")
            self.assertLessEqual(dur, 120.0, f"BGM {f.name} phải <= 120s (hiện tại: {dur:.2f}s)")

    def test_harvested_sfx_assets_validity(self):
        from pydub import AudioSegment
        from pydub.silence import detect_nonsilent

        sfx_dir = Path("assets/sfx")
        self.assertTrue(sfx_dir.exists(), "Thư mục assets/sfx phải tồn tại")
        expected_sfx = ["huh.mp3", "cai_gi_do.mp3", "laugh.mp3", "vine_boom.mp3", "wow.mp3"]
        for name in expected_sfx:
            f = sfx_dir / name
            self.assertTrue(f.exists(), f"SFX file {name} phải tồn tại trong assets/sfx/")
            dur = get_media_duration(f)
            self.assertGreater(dur, 0.2, f"SFX {name} thời lượng quá ngắn: {dur:.2f}s")
            self.assertLess(dur, 8.0, f"SFX {name} phải < 8 giây (hiện tại: {dur:.2f}s)")

            # Kiểm tra âm thanh không có khoảng lặng chết > 150ms ở đầu file
            audio = AudioSegment.from_file(str(f))
            ranges = detect_nonsilent(audio, min_silence_len=80, silence_thresh=-40)
            self.assertTrue(bool(ranges), f"SFX {name} không có âm thanh")
            self.assertLessEqual(ranges[0][0], 150, f"SFX {name} có khoảng lặng đầu quá dài: {ranges[0][0]}ms")

    def test_harvested_video_memes_assets_validity(self):
        vm_dir = Path("assets/video_memes")
        self.assertTrue(vm_dir.exists(), "Thư mục assets/video_memes phải tồn tại")
        vm_files = list(vm_dir.glob("*.mp4"))
        self.assertGreaterEqual(len(vm_files), 2, "Cần có ít nhất 2 clip video meme")
        for f in vm_files:
            dur = get_media_duration(f)
            self.assertGreaterEqual(dur, 1.8, f"Video meme {f.name} phải >= 2s (hiện tại: {dur:.2f}s)")
            self.assertLessEqual(dur, 5.2, f"Video meme {f.name} phải <= 5s (hiện tại: {dur:.2f}s)")

    def test_trim_media_audio(self):
        src = Path("assets/sfx/vine_boom.mp3")
        if src.exists():
            out = Path("assets/sfx/_test_trim.mp3")
            try:
                trim_media_file(src, out, start=0.0, duration=1.0, is_video=False)
                dur = get_media_duration(out)
                self.assertAlmostEqual(dur, 1.0, delta=0.2)
            finally:
                if out.exists():
                    out.unlink()

    def test_trim_audio_silence_sfx(self):
        from meme_harvester import trim_audio_silence_sfx
        from pydub import AudioSegment
        from pydub.generators import Sine

        test_file = Path("assets/sfx/_test_silence.mp3")
        try:
            # 1 giây im lặng + 500ms tiếng bíp + 1 giây im lặng
            silence_pre = AudioSegment.silent(duration=1000)
            beep = Sine(440).to_audio_segment(duration=500)
            silence_post = AudioSegment.silent(duration=1000)
            combo = silence_pre + beep + silence_post
            f = combo.export(str(test_file), format="mp3")
            f.close()

            trim_audio_silence_sfx(test_file, max_duration=5.0)
            res = AudioSegment.from_file(str(test_file))
            # Sau khi tỉa khoảng lặng, thời lượng phải quanh 500ms + padding (~600ms)
            self.assertLess(len(res), 800)
        finally:
            if test_file.exists():
                test_file.unlink()


if __name__ == "__main__":
    unittest.main()
