#!/usr/bin/env python3
"""Utilities for exact OCR cleanup promotion batches."""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path


OVERRIDE_FIELDS = [
    "volume",
    "page",
    "line",
    "token_index",
    "from_token",
    "to_token",
    "reason",
    "evidence",
    "review_note",
]

PACKET_METADATA_FIELDS = [
    "batch_id",
    "score",
    "source_diagnostic",
    "candidate_family",
    "direction_basis",
    "context_type",
    "positive_evidence",
    "negative_evidence",
]

PACKET_FIELDS = [*OVERRIDE_FIELDS, *PACKET_METADATA_FIELDS]

MANIFEST_FIELDS = [
    "batch_id",
    "family_id",
    "status",
    "source_release_revision",
    "source_diagnostic",
    "selection_rule",
    "min_score",
    "row_limit",
    "max_per_volume",
    "selected_count",
    "applied_count",
    "affected_volumes",
    "notes",
]

TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+)*"
)
TRAILING_SUFFIXES = ("ı", "'", "’")


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_tsv_with_fields(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        fields = list(reader.fieldnames or [])
        return fields, list(reader)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def append_tsv_row(path: Path, row: dict[str, str], fields: list[str]) -> None:
    existing_fields: list[str] = []
    if path.exists():
        existing_fields, _rows = read_tsv_with_fields(path)
        if existing_fields != fields:
            raise ValueError(f"{path} has unexpected fields: {existing_fields}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        if not existing_fields:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def override_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("volume", ""),
        row.get("page", ""),
        row.get("line", ""),
        row.get("token_index", ""),
        row.get("from_token", ""),
    )


def override_value(row: dict[str, str]) -> tuple[str, str]:
    return (row.get("to_token", ""), row.get("reason", ""))


def load_existing_override_map(path: Path) -> dict[tuple[str, str, str, str, str], tuple[str, str]]:
    if not path.exists():
        return {}
    fields, rows = read_tsv_with_fields(path)
    missing = [field for field in OVERRIDE_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"{path} missing required fields: {', '.join(missing)}")
    existing: dict[tuple[str, str, str, str, str], tuple[str, str]] = {}
    for row in rows:
        key = override_key(row)
        value = override_value(row)
        previous = existing.get(key)
        if previous is not None and previous != value:
            raise ValueError(f"Conflicting duplicate override already exists for {key}")
        existing[key] = value
    return existing


def ensure_required_fields(rows: list[dict[str, str]], fields: list[str], label: str) -> None:
    for index, row in enumerate(rows, start=2):
        missing = [field for field in fields if not row.get(field, "")]
        if missing:
            raise ValueError(f"{label} row {index} missing required fields: {', '.join(missing)}")


def extract_tokens(line: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in TOKEN_RE.finditer(line)]


def match_options(line: str, token: str, start: int, end: int) -> list[tuple[str, int, int]]:
    options: list[tuple[str, int, int]] = []

    def prefix_has_left_boundary(prefix_start: int) -> bool:
        if prefix_start <= 0:
            return True
        previous = line[prefix_start - 1]
        return not (previous.isalpha() or previous.isdigit() or previous in {"'", "’", "-", "_"})

    if start > 0 and line[start - 1] in {"/", "\\"} and prefix_has_left_boundary(start - 1):
        prefix_start = start - 1
        prefix = line[prefix_start]
        for suffix in ("", *TRAILING_SUFFIXES):
            if suffix and line[end : end + len(suffix)] != suffix:
                continue
            options.append((f"{prefix}{token}{suffix}", prefix_start, end + len(suffix)))

    whitespace_start = start
    while whitespace_start > 0 and line[whitespace_start - 1].isspace():
        whitespace_start -= 1
    if whitespace_start < start and whitespace_start > 0:
        prefix_start = whitespace_start - 1
        if line[prefix_start] in {"/", "\\"} and prefix_has_left_boundary(prefix_start):
            prefix = line[prefix_start:start]
            for suffix in ("", *TRAILING_SUFFIXES):
                if suffix and line[end : end + len(suffix)] != suffix:
                    continue
                options.append((f"{prefix}{token}{suffix}", prefix_start, end + len(suffix)))

    for suffix in ("", *TRAILING_SUFFIXES):
        if suffix and line[end : end + len(suffix)] != suffix:
            continue
        options.append((f"{token}{suffix}", start, end + len(suffix)))

    return options


def line_occurrences_for_source(source_token: str, line: str) -> list[int]:
    occurrences: list[int] = []
    for index, (token, start, end) in enumerate(extract_tokens(line), start=1):
        if any(candidate == source_token for candidate, _start, _end in match_options(line, token, start, end)):
            occurrences.append(index)
    return occurrences


def load_release_line(root: Path, volume: str, page: str, line: str) -> str:
    path = root / "release" / "current" / "text" / f"{volume}_corrected_full.txt"
    if not path.exists():
        raise ValueError(f"Missing release text for {volume}: {path}")
    try:
        page_index = int(page)
        line_index = int(line)
    except ValueError as exc:
        raise ValueError(f"Invalid page/line for {volume} {page}:{line}") from exc
    pages = path.read_text(encoding="utf-8").split("\f")
    if page_index < 1 or page_index > len(pages):
        raise ValueError(f"Page out of range for {volume} {page}:{line}")
    lines = pages[page_index - 1].split("\n")
    if line_index < 1 or line_index > len(lines):
        raise ValueError(f"Line out of range for {volume} {page}:{line}")
    return lines[line_index - 1]


def validate_packet_rows(
    root: Path,
    rows: list[dict[str, str]],
    *,
    override_path: Path | None = None,
    expected_reason: str = "",
    min_score: int = 0,
) -> None:
    ensure_required_fields(rows, OVERRIDE_FIELDS, "packet")
    existing = load_existing_override_map(override_path) if override_path else {}
    seen: dict[tuple[str, str, str, str, str], tuple[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        if expected_reason and row.get("reason") != expected_reason:
            raise ValueError(f"packet row {index} has unexpected reason {row.get('reason')!r}")
        score = row.get("score", "")
        if score:
            try:
                score_value = int(score)
            except ValueError as exc:
                raise ValueError(f"packet row {index} has non-integer score {score!r}") from exc
            if score_value < min_score:
                raise ValueError(f"packet row {index} score {score_value} below minimum {min_score}")
        key = override_key(row)
        value = override_value(row)
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(f"packet row {index} duplicates key {key}")
        seen[key] = value
        existing_value = existing.get(key)
        if existing_value is not None:
            if existing_value != value:
                raise ValueError(f"packet row {index} conflicts with existing override {key}")
            continue
        line = load_release_line(root, row["volume"], row["page"], row["line"])
        occurrences = line_occurrences_for_source(row["from_token"], line)
        expected_index = int(row["token_index"])
        if occurrences != [expected_index]:
            raise ValueError(
                "packet row "
                f"{index} is stale or ambiguous for {row['volume']} {row['page']}:{row['line']} "
                f"token {row['from_token']!r}; expected occurrence {expected_index}, found {occurrences}"
            )


def append_override_rows(path: Path, rows: list[dict[str, str]]) -> int:
    if not rows:
        return 0
    fields = OVERRIDE_FIELDS
    if path.exists():
        existing_fields, existing_rows = read_tsv_with_fields(path)
        missing = [field for field in OVERRIDE_FIELDS if field not in existing_fields]
        if missing:
            raise ValueError(f"{path} missing required fields: {', '.join(missing)}")
        fields = existing_fields
    else:
        existing_rows = []
    existing = load_existing_override_map(path)
    added = 0
    output_rows = list(existing_rows)
    for row in rows:
        key = override_key(row)
        value = override_value(row)
        existing_value = existing.get(key)
        if existing_value is not None:
            if existing_value != value:
                raise ValueError(f"Conflicting exact override for {key}")
            continue
        output_rows.append({field: row.get(field, "") for field in fields})
        existing[key] = value
        added += 1
    write_tsv(path, output_rows, fields)
    return added


def write_packet(path: Path, rows: list[dict[str, str]]) -> None:
    write_tsv(path, rows, PACKET_FIELDS)


def load_packet(path: Path) -> list[dict[str, str]]:
    fields, rows = read_tsv_with_fields(path)
    missing = [field for field in OVERRIDE_FIELDS if field not in fields]
    if missing:
        raise ValueError(f"{path} missing required fields: {', '.join(missing)}")
    return rows


def append_manifest_row(path: Path, row: dict[str, str]) -> None:
    append_tsv_row(path, row, MANIFEST_FIELDS)


def affected_volumes(rows: list[dict[str, str]], volume_order: tuple[str, ...] = ()) -> list[str]:
    volumes = {row.get("volume", "") for row in rows if row.get("volume", "")}
    if volume_order:
        rank = {volume: index for index, volume in enumerate(volume_order)}
        return sorted(volumes, key=lambda volume: (rank.get(volume, len(rank)), volume))
    return sorted(volumes)


def git_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()
