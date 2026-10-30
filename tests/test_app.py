import signal
import unittest

from herdr_blocked_hud.app import quit_on_sigint


class FakeRoot:
    def __init__(self):
        self.quit_calls = 0

    def quit(self):
        self.quit_calls += 1


class SigintTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(signal.signal, signal.SIGINT, signal.getsignal(signal.SIGINT))

    def test_sigint_stops_main_loop_and_marks_interrupt(self):
        root = FakeRoot()
        interrupted = quit_on_sigint(root)
        self.assertFalse(interrupted.is_set())
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        self.assertEqual(root.quit_calls, 1)
        self.assertTrue(interrupted.is_set())
