import pathlib
import shutil
import tempfile
import unittest

from herdr_blocked_hud import config
from herdr_blocked_hud.app import place
from herdr_blocked_hud.config import Config, ConfigError

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "contrib" / "config.toml"


class LoadTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "tmp"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def write(self, text):
        path = self.dir / "config.toml"
        path.write_text(text)
        return path

    def test_missing_file_gives_defaults(self):
        loaded = config.load(self.dir / "absent.toml")
        self.assertEqual(loaded, Config())
        self.assertEqual(loaded.done.after_seconds, 60)
        self.assertTrue(loaded.done.sound_enabled)
        self.assertEqual(loaded.done.ignore_regexes, [])

    def test_example_file_equals_defaults(self):
        self.assertEqual(config.load(EXAMPLE), Config())

    def test_values_override_defaults(self):
        loaded = config.load(self.write(
            'poll_interval = 2\ncorner = "bottom-left"\nwm_class = ""\n'
            '[done]\nafter_seconds = 120\nsound_enabled = false\n'
            "ignore_regexes = ['STATUS:\\s*DONE']\n"
        ))
        self.assertEqual(loaded.poll_interval, 2)
        self.assertEqual(loaded.corner, "bottom-left")
        self.assertEqual(loaded.wm_class, "")
        self.assertEqual(loaded.done.after_seconds, 120)
        self.assertFalse(loaded.done.sound_enabled)
        self.assertEqual(len(loaded.done.ignore), 1)

    def test_errors(self):
        cases = {
            "colour = 1\n": "unknown key colour",
            "[done]\nafter = 1\n": "unknown key done.after",
            'width = "wide"\n': "width has the wrong type",
            "margin_x = true\n": "margin_x has the wrong type",
            'corner = "middle"\n': "corner must be one of",
            "poll_interval = 0\n": "poll_interval must be positive",
            "width = 0\n": "width must be positive",
            "margin_x = -1\n": "margin_x must not be negative",
            "margin_y = -5\n": "margin_y must not be negative",
            "[done]\nafter_seconds = 0\n": "after_seconds must be positive",
            "[done]\nafter_seconds = -10\n": "after_seconds must be positive",
            "[done]\nignore_regexes = ['(']\n": "invalid regex",
            "[done]\nignore_regexes = [1]\n": "list of strings",
            "done = 1\n": "must be a table",
            "width = \n": "config.toml",
        }
        for text, message in cases.items():
            with self.subTest(text=text), self.assertRaisesRegex(ConfigError, message):
                config.load(self.write(text))


class PlaceTests(unittest.TestCase):
    def test_corners_on_primary_monitor(self):
        monitor = (100, 0, 2560, 1440)
        self.assertEqual(place(monitor, Config(), 92), (100 + 2560 - 320 - 24, 36))
        self.assertEqual(
            place(monitor, Config(corner="bottom-left"), 92), (124, 1440 - 92 - 36)
        )


if __name__ == "__main__":
    unittest.main()
