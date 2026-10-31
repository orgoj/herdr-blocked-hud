"""The Herdr plugin manifest and its launcher (bin/herdr-plugin-start)."""

import os
import pathlib
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

FAKE_SETSID = '#!/bin/sh\n[ "$1" = -f ] && shift\nexec "$@"\n'
# Prints what the HUD would see; stdout goes to the launcher's log.
FAKE_PYTHON = '#!/bin/sh\necho "argv=$*"\necho "cwd=$(pwd)"\necho "path=$PATH"\nenv | grep "^HERDR_" || true\n'


class ManifestTests(unittest.TestCase):
    def test_required_metadata_and_release_version(self):
        manifest = tomllib.loads((ROOT / "herdr-plugin.toml").read_text())
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
        for key in ("id", "name", "version", "min_herdr_version", "description"):
            self.assertIsInstance(manifest.get(key), str, key)
        self.assertEqual(manifest["version"], pyproject["project"]["version"])
        self.assertEqual(manifest["platforms"], ["linux"])
        commands = [manifest["startup"][0]["command"], manifest["actions"][0]["command"]]
        self.assertEqual(commands, [["sh", "bin/herdr-plugin-start"]] * 2)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "tmp"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        fakes = self.dir / "fakes"
        fakes.mkdir()
        for name, text in (("setsid", FAKE_SETSID), ("python3", FAKE_PYTHON)):
            (fakes / name).write_text(text)
            (fakes / name).chmod(0o755)
        self.state = self.dir / "state"
        self.state.mkdir()
        self.env = {
            "PATH": f"{fakes}:/usr/bin:/bin",
            "HERDR_BIN_PATH": "/opt/herdr/bin/herdr",
            "HERDR_PLUGIN_STATE_DIR": str(self.state),
            "HERDR_SOCKET_PATH": "/run/herdr/one.sock",
            "HERDR_ENV": "1",
            "HERDR_PANE_ID": "w1:p1",
        }

    def test_starts_the_hud_without_herdr_context_and_logs(self):
        # Run from elsewhere: the launcher finds the plugin root itself.
        result = subprocess.run(
            ["sh", str(ROOT / "bin" / "herdr-plugin-start")],
            cwd=self.dir, env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        log = (self.state / "hud.log").read_text().splitlines()
        self.assertEqual(log[:2], ["argv=-m herdr_blocked_hud", f"cwd={ROOT}"])
        self.assertTrue(log[2].startswith("path=/opt/herdr/bin:"), log[2])
        self.assertEqual(log[3:], [])            # no HERDR_* variable left

    def test_log_is_appended(self):
        for _ in range(2):
            subprocess.run(["sh", str(ROOT / "bin" / "herdr-plugin-start")],
                           env=self.env, check=True)
        self.assertEqual((self.state / "hud.log").read_text().count("argv="), 2)


if __name__ == "__main__":
    unittest.main()
