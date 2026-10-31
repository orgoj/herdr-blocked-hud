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
        self.assertEqual(loaded.done.after_seconds, 5)
        self.assertTrue(loaded.done.sound_enabled)
        self.assertEqual(loaded.done.modes, {})
        self.assertEqual(loaded.done.default_mode, "transient")

    def test_example_file_equals_defaults(self):
        self.assertEqual(config.load(EXAMPLE), Config())

    def test_values_override_defaults(self):
        loaded = config.load(self.write(
            'poll_interval = 2\ncorner = "bottom-left"\nwm_class = ""\n'
            '[done]\nafter_seconds = 120\nsound_enabled = false\n'
            'default_mode = "sticky"\n[done.modes]\nDONE = "hide"\n'
        ))
        self.assertEqual(loaded.poll_interval, 2)
        self.assertEqual(loaded.corner, "bottom-left")
        self.assertEqual(loaded.wm_class, "")
        self.assertEqual(loaded.done.after_seconds, 120)
        self.assertFalse(loaded.done.sound_enabled)
        self.assertEqual(loaded.done.default_mode, "sticky")
        self.assertEqual(loaded.done.modes, {"DONE": "hide"})

    def test_modes_keep_the_file_order(self):
        loaded = config.load(self.write(
            '[done.modes]\nNEEDS_USER = "sticky"\nWAITING = "sticky"\nDONE = "transient"\n'
        ))
        self.assertEqual(list(loaded.done.modes), ["NEEDS_USER", "WAITING", "DONE"])

    def test_mode_table_sets_the_sound(self):
        loaded = config.load(self.write(
            '[done.modes]\nDONE = "transient"\n'
            'NEEDS_USER = { mode = "sticky", sound = "blocked" }\n'
            'WAITING = { mode = "sticky", sound = "done" }\n'
            'INFO = { mode = "hide" }\n'
        ))
        done = loaded.done
        self.assertEqual(done.mode_of, {
            "DONE": "transient", "NEEDS_USER": "sticky", "WAITING": "sticky", "INFO": "hide",
        })
        self.assertEqual(done.sound_of, {
            "DONE": "done", "NEEDS_USER": "blocked", "WAITING": "done", "INFO": "done",
        })

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
            "[done]\nstatus_regex = '('\n": "invalid regex",
            "[done]\nstatus_regex = 'STATUS:'\n": "needs a group",
            "[done]\nignore_regexes = []\n": "unknown key done.ignore_regexes",
            '[done]\ndefault_mode = "keep"\n': "mode 'keep' is not one of",
            '[done]\nno_status_mode = "sticky "\n': "is not one of",
            '[done.modes]\nDONE = "gone"\n': "is not one of",
            "[done.modes]\nDONE = 1\n": "modes values must be strings or tables",
            '[done.modes]\nX = { mode = "sticky", sound = "loud" }\n': "sound 'loud' is not one of",
            '[done.modes]\nX = { sound = "blocked" }\n': "modes.X: missing mode",
            '[done.modes]\nX = { mode = "sticky", volume = 1 }\n': "modes.X: unknown key volume",
            '[done.modes]\nX = { mode = "keep" }\n': "mode 'keep' is not one of",
            "[done]\nmodes = 1\n": "done.modes has the wrong type",
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
