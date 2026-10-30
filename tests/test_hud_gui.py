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


if __name__ == "__main__":
    unittest.main()
