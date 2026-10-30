import signal
import unittest

from herdr_blocked_hud.app import quit_on_sigint


class FakeRoot:
    """Tk stand-in: idle callbacks run only once the main loop runs."""

    def __init__(self):
        self.idle = []
        self.quit_calls = 0

    def after_idle(self, callback):
        self.idle.append(callback)

    def quit(self):
        self.quit_calls += 1

    def mainloop(self):
        for callback in self.idle:
            callback()


class SigintTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(signal.signal, signal.SIGINT, signal.getsignal(signal.SIGINT))

    def test_sigint_before_mainloop_still_stops_it(self):
        root = FakeRoot()
        interrupted = quit_on_sigint(root)
        self.assertFalse(interrupted.is_set())
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        self.assertTrue(interrupted.is_set())
        # Entering mainloop resets Tk's quit flag; the quit must come after.
        self.assertEqual(root.quit_calls, 0)
        root.mainloop()
        self.assertEqual(root.quit_calls, 1)
