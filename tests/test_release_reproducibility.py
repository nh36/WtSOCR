import copy
import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import materialize_release_inputs as materialize  # noqa: E402
import package_release_inputs as package  # noqa: E402
import reproduce_current_release as reproduce  # noqa: E402


class ReleaseReproducibilityTests(unittest.TestCase):
    def make_sources(self, root: Path) -> None:
        for label in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
            volume = root / label
            volume.mkdir(parents=True)
            (volume / f"{label}_corrected_full.txt").write_text(
                f"{label} text\n", encoding="utf-8"
            )
            (volume / f"{label}_changes.tsv").write_text(
                "page\tline\n", encoding="utf-8"
            )
            diagnostics = root / f"tibetan_cleanup_diagnostics_{label}"
            diagnostics.mkdir()
            (diagnostics / "summary.md").write_text(
                f"# {label}\n", encoding="utf-8"
            )

    def build_fixture(self, root: Path):
        source = root / "sources"
        self.make_sources(source)
        files = package.collect_required_files(source)
        first = root / "first.zip"
        second = root / "second.zip"
        package.write_deterministic_zip(files, first)
        package.write_deterministic_zip(files, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        lock = package.build_lock(
            release_id="fixture",
            archive_path=first,
            asset_base_url="https://example.invalid/assets",
            files=files,
            recipe_revision="a" * 40,
            production_revision="b" * 40,
            production_workspace="fixture-workspace",
            build_timestamp="2026-07-29T16:22:11Z",
        )
        return files, first, lock

    def test_deterministic_archive_materializes_exact_locked_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            files, archive, lock = self.build_fixture(root)
            output = root / "materialized"
            materialize.verify_archive(archive, lock["archive"])
            materialize.materialize(lock, archive, output)
            self.assertEqual(
                {
                    path.relative_to(output).as_posix()
                    for path in output.rglob("*")
                    if path.is_file()
                },
                {logical for logical, _source in files},
            )

    def test_archive_checksum_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _files, archive, lock = self.build_fixture(root)
            archive.write_bytes(archive.read_bytes() + b"damage")
            with self.assertRaisesRegex(ValueError, "size mismatch"):
                materialize.verify_archive(archive, lock["archive"])

    def test_unexpected_archive_member_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _files, archive, lock = self.build_fixture(root)
            with zipfile.ZipFile(archive, "a") as handle:
                handle.writestr("wtsocr-release-inputs/extra.txt", b"extra")
            changed = copy.deepcopy(lock)
            changed["archive"]["bytes"] = archive.stat().st_size
            changed["archive"]["sha256"] = hashlib.sha256(
                archive.read_bytes()
            ).hexdigest()
            with self.assertRaisesRegex(ValueError, "archive member mismatch"):
                materialize.materialize(changed, archive, root / "output")

    def test_tree_comparison_reports_missing_extra_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            expected = root / "expected"
            actual = root / "actual"
            expected.mkdir()
            actual.mkdir()
            (expected / "same").write_text("same", encoding="utf-8")
            (actual / "same").write_text("same", encoding="utf-8")
            (expected / "changed").write_text("old", encoding="utf-8")
            (actual / "changed").write_text("new", encoding="utf-8")
            (expected / "missing").write_text("x", encoding="utf-8")
            (actual / "extra").write_text("x", encoding="utf-8")
            count, differences = reproduce.compare_trees(expected, actual)
            self.assertEqual(count, 3)
            self.assertEqual(
                differences,
                ["missing:missing", "unexpected:extra", "content:changed"],
            )


if __name__ == "__main__":
    unittest.main()
