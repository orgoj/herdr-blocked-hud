import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

PYPROJECT = '[project]\nname = "herdr-blocked-hud"\nversion = "0.1.4"\n'
README = (
    "uv tool install git+https://github.com/orgoj/herdr-blocked-hud@v0.1.4\n"
    "herdr-blocked-hud --demo\n"
)
MANIFEST = 'id = "orgoj.blocked-hud"\nversion = "0.1.4"\nmin_herdr_version = "0.7.5"\n'


class BumpVersionTests(unittest.TestCase):
    """Run a copy of bin/bump-version against a fake checkout in tmp/."""

    def setUp(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.dir = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "tmp"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        (self.dir / "bin").mkdir()
        shutil.copy(ROOT / "bin" / "bump-version", self.dir / "bin")
        self.write(PYPROJECT, README)

    def write(self, pyproject, readme, manifest=MANIFEST):
        (self.dir / "pyproject.toml").write_text(pyproject)
        (self.dir / "README.md").write_text(readme)
        (self.dir / "herdr-plugin.toml").write_text(manifest)

    def files(self):
        return tuple(
            (self.dir / name).read_text()
            for name in ("pyproject.toml", "README.md", "herdr-plugin.toml")
        )

    def bump(self, *args):
        return subprocess.run(
            [sys.executable, str(self.dir / "bin" / "bump-version"), *args],
            capture_output=True, text=True,
        )

    def assert_rejected(self, *args, message):
        before = self.files()
        result = self.bump(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertEqual(self.files(), before)

    def test_updates_pyproject_and_readme_tag(self):
        result = self.bump("0.2.0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "0.1.4 -> 0.2.0\n")
        pyproject, readme, manifest = self.files()
        self.assertEqual(pyproject, PYPROJECT.replace("0.1.4", "0.2.0"))
        self.assertEqual(readme, README.replace("@v0.1.4", "@v0.2.0"))
        self.assertEqual(manifest, MANIFEST.replace('"0.1.4"', '"0.2.0"'))

    def test_numeric_not_lexical_comparison(self):
        self.write(PYPROJECT.replace("0.1.4", "0.9.0"), README.replace("0.1.4", "0.9.0"))
        self.assertEqual(self.bump("0.10.0").returncode, 0)
        self.assertIn('version = "0.10.0"', self.files()[0])

    def test_rejects_malformed_versions(self):
        for bad in ["0.2", "v0.2.0", "0.2.0-rc1", "01.2.0", "0.2.0 ", ""]:
            with self.subTest(bad=bad):
                self.assert_rejected(bad, message="malformed version")

    def test_rejects_same_or_older_version(self):
        for old in ["0.1.4", "0.1.3", "0.0.9"]:
            with self.subTest(old=old):
                self.assert_rejected(old, message="is not newer than 0.1.4")

    def test_rejects_missing_argument(self):
        self.assert_rejected(message="usage")

    def test_readme_without_tag_changes_nothing(self):
        self.write(PYPROJECT, "no install line\n")
        self.assert_rejected("0.2.0", message="expected one version in")

    def test_manifest_without_version_changes_nothing(self):
        self.write(PYPROJECT, README, 'id = "x"\n')
        self.assert_rejected("0.2.0", message="expected one version in")


if __name__ == "__main__":
    unittest.main()
