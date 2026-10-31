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
            ["×", "↻", "Blocked", "▶ blocked row", "Done · NEEDS_USER", "▶ row a", "×",
             "Done", "▶ row b", "×"],
        )
        widgets = [widget for _, widget in self.labels()]
        self.assertLess(widgets[1].winfo_x(), widgets[0].winfo_x())   # ↻ before ×
        self.before = ([], [])
        self.press(widgets[5], 1, release_at=(-5, 2))     # released outside: nothing
        self.press(widgets[6], 1)       # × of row a
        self.press(widgets[8], 3)       # right click on row b
        self.press(widgets[5], 1)       # left click on row a focuses it
        self.press(widgets[3], 3)       # right click on a blocked row does nothing
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
