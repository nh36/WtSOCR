#!/usr/bin/env python3
from __future__ import annotations

import ast
import fnmatch
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "docs/STATUS.md",
    "data/correction_families.tsv",
    "release/current/manifest.md",
)

REPORT_PATTERNS = (
    "docs/*audit*.md",
    "docs/*cleanup*.md",
    "docs/*triage*.md",
    "docs/*readiness*.md",
    "docs/*refresh*.md",
    "docs/*diagnostic*.md",
)

LEDGER_PATTERNS = (
    "data/*ledger*.tsv",
    "data/*status*.tsv",
    "data/*todo*.tsv",
    "docs/*ledger*.md",
    "docs/*todo*.md",
)

ALLOWED_REPORT_FILES = {
    "docs/STATUS.md",
    "docs/current_release_workflow.md",
    "docs/branch_audit_current_release_refresh_2026-06-29.md",
}

ALLOWED_LEDGER_FILES = {
    "data/correction_families.tsv",
}

ALLOWED_NON_STDLIB_IMPORTS = {
    "pytest",
}

PROJECT_LOCAL_IMPORTS = {
    "conftest",
    "scripts",
    "tests",
}

NARRATIVE_REPORT_ERROR = (
    "Do not add new narrative audit/report files by default. "
    "Update data/correction_families.tsv and docs/STATUS.md instead, "
    "or explicitly allowlist the file with a justification."
)

IMPORT_ERROR = (
    "New non-stdlib import detected. Avoid adding dependencies unless necessary "
    "and documented."
)


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    source: str

    @property
    def is_added_like(self) -> bool:
        return self.status in {"A", "C", "R", "??"}


def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def find_merge_base() -> tuple[str | None, str | None]:
    for ref in ("main", "origin/main", "refs/remotes/origin/main"):
        result = run_git(["merge-base", "HEAD", ref])
        base = result.stdout.strip()
        if result.returncode == 0 and base:
            return base, ref
    return None, None


def parse_name_status(output: str, source: str) -> list[FileChange]:
    changes: list[FileChange] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        code = status[:1]
        if code in {"R", "C"} and len(parts) >= 3:
            path = parts[2]
        elif len(parts) >= 2:
            path = parts[1]
        else:
            continue
        changes.append(FileChange(code, path, source))
    return changes


def parse_porcelain_status(output: str) -> list[FileChange]:
    changes: list[FileChange] = []
    for line in output.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if status == "??":
            code = "??"
        elif "A" in status:
            code = "A"
        elif "R" in status:
            code = "R"
        elif "C" in status:
            code = "C"
        else:
            code = "M"
        changes.append(FileChange(code, path, "working tree"))
    return changes


def collect_changes() -> tuple[list[FileChange], list[str]]:
    changes: dict[str, FileChange] = {}
    notes: list[str] = []
    used_branch_diff = False

    base, ref = find_merge_base()
    if base:
        result = run_git(["diff", "--name-status", f"{base}...HEAD"])
        if result.returncode == 0:
            notes.append(f"Compared branch changes against merge base with {ref}.")
            for change in parse_name_status(result.stdout, f"{ref} merge-base"):
                changes[change.path] = change
            used_branch_diff = True
        else:
            notes.append("Could not read branch diff; falling back to tracked files.")
    else:
        notes.append("Could not find merge base with main; falling back to tracked files.")

    if not used_branch_diff:
        result = run_git(["ls-files"])
        if result.returncode == 0:
            for path in result.stdout.splitlines():
                changes.setdefault(path, FileChange("M", path, "tracked fallback"))

    status_result = run_git(["status", "--porcelain"])
    if status_result.returncode == 0:
        for change in parse_porcelain_status(status_result.stdout):
            previous = changes.get(change.path)
            if previous is None or (change.is_added_like and not previous.is_added_like):
                changes[change.path] = change

    return sorted(changes.values(), key=lambda item: item.path), notes


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_required_files(errors: list[str]) -> None:
    for path in REQUIRED_FILES:
        if not (ROOT / path).exists():
            errors.append(f"Required source-of-truth file is missing: {path}")


def check_new_report_files(changes: list[FileChange], errors: list[str]) -> None:
    for change in changes:
        if not change.is_added_like:
            continue
        if (
            matches_any(change.path, REPORT_PATTERNS)
            and change.path not in ALLOWED_REPORT_FILES
        ):
            errors.append(f"{change.path}: {NARRATIVE_REPORT_ERROR}")


def check_new_ledgers(changes: list[FileChange], errors: list[str]) -> None:
    for change in changes:
        if not change.is_added_like:
            continue
        if (
            matches_any(change.path, LEDGER_PATTERNS)
            and change.path not in ALLOWED_LEDGER_FILES
        ):
            errors.append(
                f"{change.path}: Do not add competing status or to-do ledgers by "
                "default. Update data/correction_families.tsv and docs/STATUS.md "
                "instead, or explicitly allowlist the file with a justification."
            )


def changed_python_files(changes: list[FileChange]) -> list[Path]:
    paths: list[Path] = []
    for change in changes:
        if not change.path.endswith(".py"):
            continue
        if not (change.path.startswith("scripts/") or change.path.startswith("tests/")):
            continue
        path = ROOT / change.path
        if path.exists():
            paths.append(path)
    return paths


def stdlib_modules() -> set[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return set(names) | {"__future__"}
    return {
        "__future__",
        "argparse",
        "ast",
        "collections",
        "csv",
        "dataclasses",
        "datetime",
        "difflib",
        "fnmatch",
        "glob",
        "hashlib",
        "importlib",
        "json",
        "os",
        "pathlib",
        "re",
        "shutil",
        "subprocess",
        "sys",
        "tempfile",
        "typing",
        "unicodedata",
        "unittest",
        "xml",
        "zipfile",
    }


def local_module_names() -> set[str]:
    names = set(PROJECT_LOCAL_IMPORTS)
    for folder in ("scripts", "tests"):
        root = ROOT / folder
        if root.exists():
            names.update(path.stem for path in root.glob("*.py"))
    return names


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


def check_imports(changes: list[FileChange], errors: list[str]) -> None:
    allowed = stdlib_modules() | ALLOWED_NON_STDLIB_IMPORTS | local_module_names()
    for path in changed_python_files(changes):
        try:
            roots = imported_roots(path)
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(ROOT)}: could not parse Python: {exc}")
            continue
        for root in sorted(roots - allowed):
            errors.append(f"{path.relative_to(ROOT)} imports {root}: {IMPORT_ERROR}")


def main() -> int:
    changes, notes = collect_changes()
    errors: list[str] = []

    check_required_files(errors)
    check_new_report_files(changes, errors)
    check_new_ledgers(changes, errors)
    check_imports(changes, errors)

    for note in notes:
        print(note)

    if errors:
        print("Repository hygiene checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Repository hygiene checks passed.")
    print("Reminder: run `python3 scripts/build_status.py --check` before reporting success.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
