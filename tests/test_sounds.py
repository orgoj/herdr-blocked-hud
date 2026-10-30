import io
import pathlib
import shutil
import tempfile
import unittest
import wave

from herdr_blocked_hud import sounds

ROOT = pathlib.Path(__file__).resolve().parent.parent


class SoundTests(unittest.TestCase):
    def test_render_gives_distinct_valid_wav(self):
        rendered = {}
        for kind in ("blocked", "done"):
            data = sounds.render(kind)
            with wave.open(io.BytesIO(data)) as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertEqual(wav.getframerate(), sounds.RATE)
                seconds = wav.getnframes() / wav.getframerate()
            self.assertGreater(seconds, 0.3)
            self.assertLess(seconds, 1.0)
            rendered[kind] = data
        self.assertNotEqual(rendered["blocked"], rendered["done"])

    def test_builtin_path_writes_once(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        directory = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "tmp"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        cache = directory / "cache"
        path = pathlib.Path(sounds.builtin_path("done", cache))
        self.assertEqual(path.read_bytes(), sounds.render("done"))
        path.write_bytes(b"kept")
        self.assertEqual(sounds.builtin_path("done", cache), str(path))
        self.assertEqual(path.read_bytes(), b"kept")
        self.assertEqual([p.name for p in cache.iterdir()], [path.name])
