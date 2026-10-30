import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

from herdr_blocked_hud.app import quit_on_sigint

ROOT = pathlib.Path(__file__).resolve().parent.parent


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


# Holds the lock, restarts itself once; the new process must get the lock.
RESTARTER = """
import os, sys
from herdr_blocked_hud import app
lock = app.acquire_single_instance()
if os.environ.get("RESTARTED"):
    print("second run, lock", "free" if lock else "held", sys.argv[1:])
else:
    os.environ["RESTARTED"] = "1"
    app.restart()
"""


class RestartTests(unittest.TestCase):
    def test_restart_runs_the_same_command_and_frees_the_lock(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        runtime = tempfile.mkdtemp(dir=ROOT / "tmp")
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        env = {k: v for k, v in os.environ.items() if k != "RESTARTED"}
        env.update(XDG_RUNTIME_DIR=runtime, PYTHONPATH=str(ROOT))
        result = subprocess.run(
            [sys.executable, "-c", RESTARTER, "--demo"],
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "second run, lock free ['--demo']\n")
