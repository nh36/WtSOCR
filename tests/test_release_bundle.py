import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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
    def test_reproducible_timestamp_precedence(self) -> None:
        with mock.patch.dict(
            "os.environ", {"SOURCE_DATE_EPOCH": "1785342131"}, clear=False
        ):
            expected = datetime.fromtimestamp(
                1785342131, timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.assertEqual(release_bundle.resolve_build_timestamp(None), expected)
            self.assertEqual(
                release_bundle.resolve_build_timestamp("2026-07-29T16:22:11Z"),
                "2026-07-29T16:22:11Z",
            )

    def test_invalid_source_date_epoch_fails_closed(self) -> None:
        with mock.patch.dict(
            "os.environ", {"SOURCE_DATE_EPOCH": "not-an-integer"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                release_bundle.resolve_build_timestamp(None)

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
