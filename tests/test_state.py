import contextlib
import io
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from herdr_blocked_hud.app import clamp
from herdr_blocked_hud.state import HudSettings, load, save, state_path

ROOT = pathlib.Path(__file__).resolve().parent.parent


class StateFileTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "tmp"))
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = self.dir / "sub" / "state.json"

    def load_quietly(self, corner="top-right"):
        with contextlib.redirect_stderr(io.StringIO()):
            return load(self.path, corner)

    def test_round_trip_creates_the_directory_atomically(self):
        save(self.path, HudSettings("top-right", (-40, 12), True))
        self.assertEqual(load(self.path, "top-right"), HudSettings("top-right", (-40, 12), True))
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["state.json"])

    def test_missing_or_malformed_file_gives_defaults(self):
        self.assertEqual(self.load_quietly(), HudSettings("top-right"))
        self.path.parent.mkdir()
        for text in ("{not json", "[1, 2]", '{"offset": "x", "muted": 1, "corner": "top-right"}',
                     '{"offset": [1.5, 2], "corner": "top-right", "muted": true}',
                     '{"offset": [20, 30], "corner": "top-right", "muted": "yes"}',
                     '{"offset": [20, 30], "corner": "top-right"}'):
            self.path.write_text(text)
            self.assertEqual(self.load_quietly(), HudSettings("top-right"), text)

    def test_offset_from_another_corner_is_ignored_but_mute_kept(self):
        save(self.path, HudSettings("bottom-left", (30, -30), True))
        self.assertEqual(load(self.path, "top-right"), HudSettings("top-right", (0, 0), True))

    def test_failed_save_is_reported_not_raised(self):
        self.path.parent.mkdir()
        self.path.mkdir()          # a directory where the file should be
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            save(self.path, HudSettings("top-right"))
        self.assertIn("cannot save state", stderr.getvalue())

    def test_state_path_follows_xdg_state_home(self):
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/x/state"}):
            self.assertEqual(state_path(), pathlib.Path("/x/state/herdr-blocked-hud/state.json"))
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": ""}):
            self.assertEqual(
                state_path(),
                pathlib.Path(os.path.expanduser("~/.local/state/herdr-blocked-hud/state.json")),
            )


class ClampTests(unittest.TestCase):
    def test_window_is_kept_on_the_monitor(self):
        monitor = [(100, 0, 1000, 800)]
        self.assertEqual(clamp(monitor, 500, 300, 320, 100), (500, 300))
        self.assertEqual(clamp(monitor, 2000, -50, 320, 100), (100 + 1000 - 320, 0))
        self.assertEqual(clamp(monitor, 0, 900, 320, 100), (100, 700))

    def test_window_stays_on_the_monitor_holding_its_centre(self):
        # Primary 2560x1440 left, portrait 1080x1920 right of it.
        monitors = [(0, 0, 2560, 1440), (2560, 0, 1080, 1920)]
        self.assertEqual(clamp(monitors, 3000, 1600, 320, 100), (3000, 1600))
        # Overlapping the edge: pulled onto the monitor holding the centre.
        self.assertEqual(clamp(monitors, 2500, 100, 320, 100), (2560, 100))
        self.assertEqual(clamp(monitors, 2300, 100, 320, 100), (2560 - 320, 100))
        # Centre in the gap below the primary: nearer to the taller monitor,
        # or nearer to the primary's bottom edge.
        self.assertEqual(clamp(monitors, 2300, 1700, 320, 100), (2560, 1700))
        self.assertEqual(clamp(monitors, 2000, 1700, 320, 100), (2000, 1440 - 100))

    def test_window_off_every_monitor_goes_to_the_nearest(self):
        monitors = [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]
        self.assertEqual(clamp(monitors, 5000, 50, 320, 100), (3840 - 320, 50))
        self.assertEqual(clamp(monitors, -900, 50, 320, 100), (0, 50))
        self.assertEqual(clamp(monitors[:1], 2500, 50, 320, 100), (1920 - 320, 50))


if __name__ == "__main__":
    unittest.main()
