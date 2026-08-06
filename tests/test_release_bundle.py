import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_current_release_bundle.py"
SPEC = importlib.util.spec_from_file_location("release_bundle_test_module", SCRIPT)
assert SPEC and SPEC.loader
release_bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_bundle
SPEC.loader.exec_module(release_bundle)


class ReleaseBundleTests(unittest.TestCase):
    def test_missing_required_source_does_not_clean_existing_release(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "release" / "current"
            output.mkdir(parents=True)
            sentinel = output / "sentinel.txt"
            sentinel.write_text("preserve\n", encoding="utf-8")

            with mock.patch.object(release_bundle, "repo_root", return_value=root):
                with self.assertRaisesRegex(
                    FileNotFoundError, "source directory not found"
                ):
                    release_bundle.main(["--output-dir", "release/current"])

            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve\n")


if __name__ == "__main__":
    unittest.main()
