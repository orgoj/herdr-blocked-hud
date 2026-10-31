"""Tk tests; they create windows, so they run only under a virtual display:
xvfb-run -a env HUD_GUI_TESTS=1 python3 tests/run
"""

import os
import unittest

from herdr_blocked_hud.config import Config
from herdr_blocked_hud.logic import Row, Section, View
from herdr_blocked_hud.source import Agent


def agent(terminal):
    return Agent("default", f"w1:{terminal}", terminal, "w1", "w1:t1", "api", "main", "claude",
                 "done", False, 1)


@unittest.skipUnless(os.environ.get("HUD_GUI_TESTS") == "1", "needs xvfb-run, see docstring")
class HudGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk

        from herdr_blocked_hud.app import Hud

        self.root = tk.Tk()
        self.addCleanup(self.destroy)
        self.clicked, self.dismissed = [], []
        self.hud = Hud(self.root, on_click=self.clicked.append, config=Config(),
                       on_dismiss=self.dismissed.append)

    def destroy(self):
        import tkinter as tk

        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def labels(self):
        """(text, widget) of every label in the HUD, rows included."""
        found = []
        for child in self.hud.frame.winfo_children():
            for widget in (child, *child.winfo_children()):
                if widget.winfo_class() == "Label":
                    found.append((widget.cget("text"), widget))
        return found

    def press(self, widget, button, release_at=(2, 2)):
        widget.event_generate(f"<ButtonPress-{button}>", x=2, y=2)
        self.root.update()
        # Acting on press would let the release fall through to the window below.
        self.assertEqual((self.clicked, self.dismissed), self.before)
        x, y = release_at
        widget.event_generate(f"<ButtonRelease-{button}>", x=x, y=y)
        self.root.update()
        self.before = (list(self.clicked), list(self.dismissed))

    def test_done_rows_dismiss_by_close_button_and_right_click(self):
        a, b, c = agent("a"), agent("b"), agent("c")
        self.hud.render(View(
            blocked=(Row(c, "blocked row"),),
            done=(Section("Done · NEEDS_USER", (Row(a, "row a"),)),
                  Section("Done", (Row(b, "row b"),))),
        ))
        # Hud starts withdrawn; unmapped widgets get no generated events.
        self.root.deiconify()
        self.root.update()
        texts = [text for text, _ in self.labels()]
        # Top line: quit and restart packed from the right, then the first header.
        self.assertEqual(
            texts,
            ["×", "↻", "♪", "Blocked", "▶ blocked row", "Done · NEEDS_USER", "▶ row a", "×",
             "Done", "▶ row b", "×"],
        )
        widgets = [widget for _, widget in self.labels()]
        self.assertLess(widgets[1].winfo_x(), widgets[0].winfo_x())   # ↻ before ×
        self.before = ([], [])
        self.press(widgets[6], 1, release_at=(-5, 2))     # released outside: nothing
        self.press(widgets[7], 1)       # × of row a
        self.press(widgets[9], 3)       # right click on row b
        self.press(widgets[6], 1)       # left click on row a focuses it
        self.press(widgets[4], 3)       # right click on a blocked row does nothing
        self.assertEqual(self.dismissed, [a, b])
        self.assertEqual(self.clicked, [a])
        self.assertIsNone(self.hud.exit_action)

    def test_control_buttons_end_the_main_loop(self):
        self.hud.render(View(error="refused"))
        self.root.deiconify()
        self.root.update()
        quit_button, restart_button = [w for _, w in self.labels()][:2]
        self.before = ([], [])
        self.press(restart_button, 1, release_at=(-5, 2))
        self.assertIsNone(self.hud.exit_action)
        self.press(restart_button, 1)
        self.assertEqual(self.hud.exit_action, "restart")
        self.press(quit_button, 1)
        self.assertEqual(self.hud.exit_action, "quit")

    def test_mute_button_silences_sounds_but_keeps_the_hud(self):
        from unittest import mock

        beeping = View(blocked=(Row(agent("a"), "row a"),), beep_blocked=True)
        played = []
        with mock.patch("herdr_blocked_hud.app.play", played.append):
            self.hud.show(beeping)
            self.root.update()
            self.assertEqual(len(played), 1)
            mute = dict(self.labels())["♪"]
            self.before = ([], [])
            self.press(mute, 1)
            self.assertTrue(self.hud.muted)
            self.assertIn("overstrike", str(mute.cget("font")))
            # A new beep while muted: the HUD shows, nothing plays.
            self.hud.show(View(blocked=(Row(agent("b"), "row b"),), beep_blocked=True))
            self.root.update()
            self.assertEqual(len(played), 1)
            self.assertEqual(self.root.state(), "normal")
            # The state survives the re-render; unmuting plays again.
            mute = dict(self.labels())["♪"]
            self.assertIn("overstrike", str(mute.cget("font")))
            self.press(mute, 1)
            self.assertFalse(self.hud.muted)
            self.assertNotIn("overstrike", str(mute.cget("font")))
            self.hud.show(View(blocked=(Row(agent("c"), "row c"),), beep_blocked=True))
            self.assertEqual(len(played), 2)

    def test_mute_covers_the_demo_sounds(self):
        from unittest import mock

        from herdr_blocked_hud.app import start_demo

        scheduled = []
        with mock.patch.object(self.root, "after", lambda ms, f, *a: scheduled.append((f, a))):
            hud = start_demo(self.root, Config())
        sounds = [(f, a) for f, a in scheduled if f == hud.play]
        self.assertEqual(len(sounds), 2)
        played = []
        hud.muted = True
        with mock.patch("herdr_blocked_hud.app.play", played.append):
            for f, a in sounds:
                f(*a)
            self.assertEqual(played, [])
            hud.muted = False
            sounds[0][0](*sounds[0][1])
            self.assertEqual(len(played), 1)

    def test_tray_click_toggles_the_hud_until_the_next_sound_event(self):
        a = agent("a")
        self.hud.show(View())
        self.root.update()
        self.assertFalse(self.hud.mapped)
        # Shown on a click even with nothing listed.
        self.hud.tray_event(("activate",))
        self.root.update()
        self.assertEqual(self.root.state(), "normal")
        self.assertIn("Nothing waiting", [text for text, _ in self.labels()])
        self.hud.tray_event(("activate",))
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        # Hidden by a click: a refresh with rows but no sound keeps it hidden...
        self.hud.show(View(blocked=(Row(a, "row a"),)))
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        # ...a new sound event shows it again.
        self.hud.show(View(blocked=(Row(a, "row a"), Row(agent("b"), "row b")),
                           beep_blocked=True))
        self.root.update()
        self.assertEqual(self.root.state(), "normal")
        self.assertIsNone(self.hud.forced)

    def test_tray_events_drain_and_menu_acts_like_the_buttons(self):
        self.hud.tray_events.put(("activate",))
        self.hud.start_draining()
        self.root.update()
        self.assertEqual(self.root.state(), "normal")
        menu = self.hud.menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
        self.assertEqual(labels, ["Mute", "Restart", "Quit"])
        menu.invoke(0)
        self.assertTrue(self.hud.muted)
        self.assertTrue(self.hud.menu_mute.get())
        self.assertIn("overstrike", str(self.hud.mute_button.cget("font")))
        menu.invoke(0)
        self.assertFalse(self.hud.muted)
        menu.invoke(1)
        self.assertEqual(self.hud.exit_action, "restart")
        menu.invoke(2)
        self.assertEqual(self.hud.exit_action, "quit")

    def test_hud_reports_its_state_to_the_tray(self):
        import queue
        import tkinter as tk

        from herdr_blocked_hud.app import Hud
        from herdr_blocked_hud.tray import TrayState

        class FakeTray:
            events = queue.Queue()
            states = []

            def set_state(self, state):
                self.states.append(state)

        root = tk.Tk()
        self.addCleanup(root.destroy)
        fake = FakeTray()
        hud = Hud(root, on_click=lambda a: None, config=Config(), tray=fake)
        hud.show(View(blocked=(Row(agent("a"), "a"),),
                      done=(Section("Done", (Row(agent("b"), "b"), Row(agent("c"), "c"))),)))
        hud.toggle_mute()
        self.assertEqual(fake.states[-2:], [TrayState(1, 2, False), TrayState(1, 2, True)])

    def test_position_and_mute_survive_a_restart(self):
        import pathlib
        import shutil
        import tempfile
        import tkinter as tk

        from herdr_blocked_hud.app import Hud, start_demo

        root_dir = pathlib.Path(__file__).resolve().parent.parent / "tmp"
        root_dir.mkdir(exist_ok=True)
        directory = pathlib.Path(tempfile.mkdtemp(dir=root_dir))
        self.addCleanup(shutil.rmtree, directory)
        state_file = directory / "state.json"
        view = View(blocked=(Row(agent("a"), "row a"),))

        def run():
            root = tk.Tk()

            def destroy():
                try:
                    root.destroy()
                except tk.TclError:
                    pass

            self.addCleanup(destroy)
            hud = Hud(root, on_click=lambda a: None, config=Config(), state_file=state_file)
            hud.monitor = (0, 0, 1000, 800)
            hud.render(view)
            root.deiconify()
            root.update()
            return root, hud

        root, hud = run()
        header = hud.top.winfo_children()[-1]          # "Blocked", packed last
        header.event_generate("<ButtonPress-1>", x=2, y=2, rootx=700, rooty=40)
        header.event_generate("<B1-Motion>", x=2, y=2, rootx=600, rooty=140)
        header.event_generate("<ButtonRelease-1>", x=2, y=2, rootx=600, rooty=140)
        root.update()
        hud.toggle_mute()
        root.update_idletasks()
        moved = (root.winfo_x(), root.winfo_y())
        self.assertEqual(moved, (556, 136))
        root.destroy()

        root, hud = run()
        root.update_idletasks()
        self.assertEqual((root.winfo_x(), root.winfo_y()), moved)
        self.assertTrue(hud.muted)
        root.destroy()

        # The demo neither reads nor writes the state file.
        before = state_file.read_bytes()
        demo = start_demo(self.root, Config())
        self.assertIsNone(demo.state_file)
        self.assertFalse(demo.muted)
        demo.toggle_mute()
        self.assertEqual(state_file.read_bytes(), before)

    def drag(self, widget, start, end):
        """Left-button drag from root coordinates `start` to `end` over `widget`."""
        widget.event_generate("<ButtonPress-1>", x=2, y=2, rootx=start[0], rooty=start[1])
        widget.event_generate("<B1-Motion>", x=2, y=2, rootx=end[0], rooty=end[1])
        widget.event_generate("<ButtonRelease-1>", x=2, y=2, rootx=end[0], rooty=end[1])
        self.root.update()

    def position(self):
        self.root.update_idletasks()
        return self.root.winfo_x(), self.root.winfo_y()

    def test_drag_moves_the_hud_and_keeps_the_position(self):
        a = agent("a")
        self.hud.monitor = (0, 0, 1000, 800)
        self.hud.render(View(blocked=(Row(a, "row a"),)))
        self.root.deiconify()
        self.root.update()
        self.assertTrue(self.root.overrideredirect())
        # Default corner: top-right, margins 24/36, width 320.
        self.assertEqual(self.position(), (1000 - 320 - 24, 36))
        texts = dict(self.labels())
        self.before = ([], [])
        # A drag from the header moves the window.
        self.drag(texts["Blocked"], (700, 40), (600, 140))
        self.assertEqual(self.position(), (556, 136))
        # A drag starting on a row moves it too, without focusing the agent.
        self.drag(texts["▶ row a"], (600, 160), (590, 170))
        self.assertEqual(self.position(), (546, 146))
        # A short jitter is still a click, and the window stays put.
        self.drag(texts["▶ row a"], (600, 160), (602, 161))
        self.assertEqual(self.position(), (546, 146))
        self.assertEqual(self.clicked, [a])
        # A refresh with another height keeps the dragged position.
        self.hud.render(View(blocked=(Row(a, "row a"), Row(agent("b"), "row b"))))
        self.root.update()
        self.assertEqual(self.position(), (546, 146))

    def test_dragged_bottom_corner_keeps_its_bottom_edge(self):
        import dataclasses

        self.hud.config = dataclasses.replace(Config(), corner="bottom-left")
        self.hud.monitor = (0, 0, 1000, 800)
        self.hud.render(View(blocked=(Row(agent("a"), "row a"),)))
        self.root.deiconify()
        self.root.update()
        self.drag(dict(self.labels())["Blocked"], (100, 700), (150, 650))
        x, y = self.position()
        bottom = y + self.root.winfo_height()
        self.hud.render(View(blocked=(Row(agent("a"), "row a"), Row(agent("b"), "row b"))))
        self.root.update()
        x2, y2 = self.position()
        self.assertEqual((x2, y2 + self.root.winfo_height()), (x, bottom))
        self.assertLess(y2, y)


if __name__ == "__main__":
    unittest.main()
