import unittest

from herdr_blocked_hud import x11
from herdr_blocked_hud.source import Session
from herdr_blocked_hud.x11 import Process

SESSIONS = [
    Session("default", "/c/herdr.sock", True),
    Session("work", "/c/sessions/work/herdr.sock", False),
]

# client 5992 -> wezterm-gui 5893 -> session leader 5264 -> init
PARENTS = {5992: 5893, 5893: 5264, 5264: 1, 7001: 7000, 7000: 1}


class ClientTests(unittest.TestCase):
    def test_ui_client_argv(self):
        self.assertTrue(x11.is_ui_client(("herdr",)))
        self.assertTrue(x11.is_ui_client(("/usr/bin/herdr", "--session", "work")))
        self.assertFalse(x11.is_ui_client(("/home/u/.local/bin/herdr", "server")))
        self.assertFalse(x11.is_ui_client(("herdr", "agent", "focus", "w1:p1")))
        self.assertFalse(x11.is_ui_client(("wezterm-gui", "--class", "herdr")))
        self.assertFalse(x11.is_ui_client(()))

    def test_client_session(self):
        def session(argv, env=None):
            return x11.client_session(Process(1, argv, env or {}), SESSIONS)

        self.assertEqual(session(("herdr",)), "default")
        self.assertEqual(session(("herdr", "--session", "work")), "work")
        self.assertEqual(session(("herdr", "--session=work")), "work")
        self.assertEqual(session(("herdr",), {"HERDR_SESSION": "work"}), "work")
        self.assertEqual(
            session(("herdr",), {"HERDR_SOCKET_PATH": "/c/sessions/work/herdr.sock"}), "work"
        )
        self.assertIsNone(session(("herdr", "--session", "gone")))
        self.assertIsNone(session(("herdr",), {"HERDR_SOCKET_PATH": "/elsewhere.sock"}))

    def test_ancestors_stop_at_init_and_loops(self):
        self.assertEqual(x11.ancestors(5992, PARENTS.get), [5992, 5893, 5264])
        self.assertEqual(x11.ancestors(1, {1: 2, 2: 1}.get), [1, 2])

    def test_viewed_sessions(self):
        clients = {"default": [5992], "work": [7001]}
        self.assertEqual(x11.viewed_sessions(5893, clients, PARENTS.get), {"default"})
        self.assertEqual(x11.viewed_sessions(7000, clients, PARENTS.get), {"work"})
        self.assertEqual(x11.viewed_sessions(4242, clients, PARENTS.get), set())
        self.assertEqual(x11.viewed_sessions(None, clients, PARENTS.get), set())


WMCTRL = """\
0x04400003  0 5900   google-chrome.Google-chrome  host herdr - GitHub - Google Chrome
0x04200003  0 5893   herdr.herdr           host ▶ herdr_dev - herdr
0x06800003  0 229557 org.wezfurlong.wezterm.org.wezfurlong.wezterm  host shell
0x07100003  2 7000   herdr.herdr           host herdr work
0x01200008 -1 5456   lxqt-panel.lxqt-panel  host lxqt-panel
"""


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.windows = x11.parse_window_list(WMCTRL)

    def test_parse_window_list(self):
        self.assertEqual(len(self.windows), 5)
        self.assertEqual(self.windows[1], x11.Window("0x04200003", 5893, "herdr.herdr"))

    def test_host_window_by_process_tree(self):
        window = x11.host_window([5992], self.windows, None, PARENTS.get)
        self.assertEqual(window.wid, "0x04200003")
        window = x11.host_window([7001], self.windows, None, PARENTS.get)
        self.assertEqual(window.wid, "0x07100003")

    def test_first_client_with_a_window_wins(self):
        window = x11.host_window([4000, 7001, 5992], self.windows, None, PARENTS.get)
        self.assertEqual(window.wid, "0x07100003")

    def test_wm_class_fallback_is_exact_and_never_by_title(self):
        # Client under a mux server: no window in its parent chain.
        parents = {8000: 8837, 8837: 1}
        window = x11.host_window([8000], self.windows, "herdr.herdr", parents.get)
        self.assertEqual(window.wid, "0x04200003")
        self.assertIsNone(x11.host_window([8000], self.windows, "herdr", parents.get))
        self.assertIsNone(x11.host_window([8000], self.windows, None, parents.get))
        self.assertIsNone(x11.host_window([], self.windows, None, parents.get))


class MonitorTests(unittest.TestCase):
    def test_primary_monitor(self):
        listing = (
            "Monitors: 2\n"
            " 0: +*DP-0 2560/698x1440/393+0+0  DP-0\n"
            " 1: +HDMI-0 1080/477x1920/268+2560+0  HDMI-0\n"
        )
        self.assertEqual(x11.parse_primary_monitor(listing), (0, 0, 2560, 1440))

    def test_first_monitor_without_primary(self):
        listing = "Monitors: 1\n 0: +HDMI-0 1920/477x1080/268+100+0  HDMI-0\n"
        self.assertEqual(x11.parse_primary_monitor(listing), (100, 0, 1920, 1080))


if __name__ == "__main__":
    unittest.main()
