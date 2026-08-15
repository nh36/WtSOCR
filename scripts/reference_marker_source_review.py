#!/usr/bin/env python3
"""Source-image review helpers for exact reference-marker OCR cleanup."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import exact_promotion_batch as batch


VOLUME_ORDER = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
VOLUME_SOURCE_LABELS = {
    "wts_1_34": "WtS_1-34",
    "wts_35_51": "WtS_35-51",
    "wts_8_b": "WtS_8-b",
    "wts_9_m": "WtS_9-m",
}
PREFIX_MARKER_SOURCES = {"I", "T", "\\"}
SOURCE_IMAGE_MARKERS = ("↑²", "↓²", "↑", "↓")
SOURCE_IMAGE_DECISIONS = {
    "",
    "accept_exact",
    "reject_not_marker",
    "reject_unclear_image",
    "reject_stale_context",
    "needs_more_context",
}
REFERENCE_MARKER_REASON = "reviewed_tibetan_exact_reference_marker"
SOURCE_IMAGE_EVIDENCE_TAG = "reference_marker_source_image"
SOURCE_REVIEW_FIELDS = [
    "volume",
    "page",
    "line",
    "token_index",
    "source_token",
    "current_line",
    "source_marker",
    "attached_token",
    "candidate_family",
    "context_excerpt",
    "proposed_to_token",
    "source_pdf",
    "pdf_page",
    "source_crop",
    "crop_confidence",
    "source_image_decision",
    "source_image_marker",
    "review_note",
    "batch_id",
    "reviewed_at",
]


def utc_batch_id(prefix: str = "reference_marker_source_review") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def as_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def relpath(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value)
    return slug.strip("._") or "token"


def diagnostic_source_for_volume(volume: str) -> str:
    return f"release/current/qa/{volume}/tibetan_cleanup_diagnostics/reference_marker_candidates.tsv"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_source_pdf_records(root: Path) -> dict[str, dict[str, str]]:
    path = root / "data" / "source_pdfs.tsv"
    rows = read_tsv(path)
    records: dict[str, dict[str, str]] = {}
    for row in rows:
        label = row.get("label", "")
        if not label:
            continue
        records[label] = row
    return records


def source_pdf_record_for_volume(root: Path, volume: str) -> tuple[str, dict[str, str]]:
    label = VOLUME_SOURCE_LABELS.get(volume, "")
    if not label:
        raise ValueError(f"No source PDF label registered for volume {volume!r}")
    records = load_source_pdf_records(root)
    record = records.get(label)
    if record is None:
        raise ValueError(f"Missing source PDF record {label!r} for volume {volume!r}")
    return label, record


def load_release_page_lines(root: Path, volume: str, page: str) -> list[str]:
    text_path = root / "release" / "current" / "text" / f"{volume}_corrected_full.txt"
    if not text_path.exists():
        raise ValueError(f"Missing release text for {volume}: {text_path}")
    page_number = as_int(page)
    if page_number < 1:
        raise ValueError(f"Invalid page for {volume}: {page!r}")
    pages = text_path.read_text(encoding="utf-8").split("\f")
    if page_number > len(pages):
        raise ValueError(f"Page out of range for {volume}: {page!r}")
    return pages[page_number - 1].split("\n")


def crop_path_for(root: Path, work_dir: Path, row: dict[str, str], batch_id: str) -> str:
    volume = safe_slug(row.get("volume", "volume"))
    page = as_int(row.get("page", "0"))
    line = as_int(row.get("line", "0"))
    token_index = as_int(row.get("token_index", "0"))
    token = safe_slug(row.get("source_token", "token"))[:60]
    path = (
        work_dir
        / "source_crops"
        / f"{safe_slug(batch_id)}_{volume}_p{page:04d}_l{line:03d}_t{token_index:02d}_{token}.png"
    )
    return relpath(root, path)


def source_review_sort_key(row: dict[str, str]) -> tuple[int, int, int, int, int]:
    volume_rank = {volume: index for index, volume in enumerate(VOLUME_ORDER)}
    return (
        -as_int(row.get("score", "")),
        volume_rank.get(row.get("volume", ""), len(volume_rank)),
        as_int(row.get("page", "")),
        as_int(row.get("line", "")),
        as_int(row.get("token_index", "")),
    )


def select_source_review_candidates(
    investigation_rows: list[dict[str, str]],
    *,
    limit: int,
    max_per_volume: int,
) -> list[dict[str, str]]:
    counts: Counter[str] = Counter()
    selected: list[dict[str, str]] = []
    candidates = [
        row
        for row in investigation_rows
        if row.get("decision") == "needs_source_image"
        and row.get("marker_source") in PREFIX_MARKER_SOURCES
        and row.get("source_token", "")
        and row.get("attached_token", "")
        and row.get("token_index", "")
    ]
    for row in sorted(candidates, key=source_review_sort_key):
        volume = row.get("volume", "")
        if max_per_volume and counts[volume] >= max_per_volume:
            continue
        selected.append(row)
        counts[volume] += 1
        if limit and len(selected) >= limit:
            break
    return selected


def review_row_from_investigation(
    root: Path,
    row: dict[str, str],
    *,
    batch_id: str,
    work_dir: Path,
) -> dict[str, str]:
    _label, pdf_record = source_pdf_record_for_volume(root, row.get("volume", ""))
    context_line = row.get("context_line", "")
    return {
        "volume": row.get("volume", ""),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "token_index": row.get("token_index", ""),
        "source_token": row.get("source_token", ""),
        "current_line": context_line,
        "source_marker": row.get("marker_source", ""),
        "attached_token": row.get("attached_token", ""),
        "candidate_family": row.get("candidate_family", ""),
        "context_excerpt": row.get("context_line", "") or row.get("context_excerpt", ""),
        "proposed_to_token": "",
        "source_pdf": pdf_record.get("filename", ""),
        "pdf_page": row.get("page", ""),
        "source_crop": crop_path_for(root, work_dir, row, batch_id),
        "crop_confidence": "not_rendered",
        "source_image_decision": "",
        "source_image_marker": "",
        "review_note": "",
        "batch_id": batch_id,
        "reviewed_at": "",
    }


def build_review_rows(
    root: Path,
    investigation_rows: list[dict[str, str]],
    *,
    batch_id: str,
    work_dir: Path,
    limit: int,
    max_per_volume: int,
    render_crops: bool = False,
    dpi: int = 200,
) -> list[dict[str, str]]:
    selected = select_source_review_candidates(
        investigation_rows,
        limit=limit,
        max_per_volume=max_per_volume,
    )
    rows = [
        review_row_from_investigation(root, row, batch_id=batch_id, work_dir=work_dir)
        for row in selected
    ]
    if render_crops:
        render_review_crops(root, rows, work_dir=work_dir, dpi=dpi)
    return rows


def render_review_crops(root: Path, rows: list[dict[str, str]], *, work_dir: Path, dpi: int) -> None:
    from PIL import Image
    from line_anchor_merge_pilot import crop_image, render_page_png

    page_dir = work_dir / "source_pages"
    page_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        pdf = root / row.get("source_pdf", "")
        if not pdf.exists():
            raise FileNotFoundError(f"Source PDF not found: {pdf}")
        volume = row.get("volume", "")
        page_number = as_int(row.get("pdf_page", ""))
        if page_number < 1:
            raise ValueError(f"Invalid PDF page for review row: {row.get('pdf_page', '')!r}")
        page_png = page_dir / f"{volume}_p{page_number:04d}.png"
        if not page_png.exists():
            render_page_png(pdf, page_number, dpi, page_png)

        release_lines = load_release_page_lines(root, volume, row.get("page", ""))
        line_number = as_int(row.get("line", ""))
        with Image.open(page_png) as image:
            width, height = image.size
        line_count = max(len(release_lines), line_number, 1)
        line_height = max(8, round(height / line_count))
        center_y = round((line_number - 0.5) * height / line_count)
        bbox = (
            0,
            max(0, center_y - line_height),
            width,
            min(height, center_y + line_height),
        )
        crop = root / row.get("source_crop", "")
        crop.parent.mkdir(parents=True, exist_ok=True)
        crop_image(page_png, crop, bbox, pad=max(10, line_height // 2))
        row["crop_confidence"] = "line_band_estimate"


def source_token_marker(row: dict[str, str]) -> str:
    explicit = row.get("source_marker", "")
    if explicit:
        return explicit
    source = row.get("source_token", "")
    return source[:1]


def is_blank_row(row: dict[str, str]) -> bool:
    return not any((value or "").strip() for value in row.values())


def validate_review_rows(root: Path, rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    records: dict[str, dict[str, str]] | None = None
    required = [
        "volume",
        "page",
        "line",
        "token_index",
        "source_token",
        "current_line",
        "source_pdf",
        "pdf_page",
        "batch_id",
    ]
    for index, row in enumerate(rows, start=2):
        if is_blank_row(row):
            continue
        missing = [field for field in required if not row.get(field, "")]
        if missing:
            errors.append(f"row {index} missing required fields: {', '.join(missing)}")
            continue

        decision = row.get("source_image_decision", "")
        if decision not in SOURCE_IMAGE_DECISIONS:
            errors.append(f"row {index} has unknown source_image_decision {decision!r}")

        key = (
            row.get("volume", ""),
            row.get("page", ""),
            row.get("line", ""),
            row.get("token_index", ""),
            row.get("source_token", ""),
        )
        if key in seen:
            errors.append(f"row {index} duplicates review key {key}")
        seen.add(key)

        try:
            current_line = batch.load_release_line(
                root,
                row["volume"],
                row["page"],
                row["line"],
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"row {index} cannot load current release line: {exc}")
            current_line = ""
        if current_line and row.get("current_line", "") != current_line:
            errors.append(
                f"row {index} stale current_line for {row['volume']} {row['page']}:{row['line']}"
            )

        expected_index = as_int(row.get("token_index", ""))
        if expected_index < 1:
            errors.append(f"row {index} has invalid token_index {row.get('token_index', '')!r}")
        elif current_line:
            occurrences = batch.line_occurrences_for_source(row.get("source_token", ""), current_line)
            if occurrences != [expected_index]:
                errors.append(
                    f"row {index} stale or ambiguous source token {row.get('source_token', '')!r}; "
                    f"expected occurrence {expected_index}, found {occurrences}"
                )

        if records is None:
            records = load_source_pdf_records(root)
        label = VOLUME_SOURCE_LABELS.get(row.get("volume", ""), "")
        record = records.get(label, {}) if label else {}
        if not record:
            errors.append(f"row {index} has no registered source PDF for volume {row.get('volume', '')!r}")
        elif row.get("source_pdf", "") != record.get("filename", ""):
            errors.append(
                f"row {index} source_pdf {row.get('source_pdf', '')!r} does not match "
                f"registered {record.get('filename', '')!r}"
            )
        pages = as_int(record.get("pages", ""))
        pdf_page = as_int(row.get("pdf_page", ""))
        if pdf_page < 1 or (pages and pdf_page > pages):
            errors.append(f"row {index} pdf_page {row.get('pdf_page', '')!r} is out of range")

        if decision == "accept_exact":
            marker_source = source_token_marker(row)
            if marker_source not in PREFIX_MARKER_SOURCES:
                errors.append(
                    f"row {index} accepted source marker {marker_source!r} is not an allowed prefix source"
                )
            marker = row.get("source_image_marker", "")
            if marker not in SOURCE_IMAGE_MARKERS:
                errors.append(f"row {index} accepted row has invalid source_image_marker {marker!r}")
            target = row.get("proposed_to_token", "")
            if marker and not target.startswith(f"{marker} "):
                errors.append(
                    f"row {index} proposed_to_token {target!r} does not start with confirmed marker {marker!r}"
                )
            attached = row.get("attached_token", "")
            if marker and attached and target != f"{marker} {attached}":
                errors.append(
                    f"row {index} proposed_to_token {target!r} does not preserve attached token {attached!r}"
                )
            accepted_missing = [
                field
                for field in ("proposed_to_token", "source_crop", "review_note", "reviewed_at")
                if not row.get(field, "")
            ]
            if accepted_missing:
                errors.append(
                    f"row {index} accepted row missing fields: {', '.join(accepted_missing)}"
                )
    return errors


def accepted_review_sort_key(row: dict[str, str]) -> tuple[int, int, int, int]:
    volume_rank = {volume: index for index, volume in enumerate(VOLUME_ORDER)}
    return (
        volume_rank.get(row.get("volume", ""), len(volume_rank)),
        as_int(row.get("page", "")),
        as_int(row.get("line", "")),
        as_int(row.get("token_index", "")),
    )


def select_accepted_reviews(
    rows: list[dict[str, str]],
    *,
    limit: int,
    max_per_volume: int,
) -> list[dict[str, str]]:
    counts: Counter[str] = Counter()
    selected: list[dict[str, str]] = []
    for row in sorted(rows, key=accepted_review_sort_key):
        if row.get("source_image_decision", "") != "accept_exact":
            continue
        volume = row.get("volume", "")
        if max_per_volume and counts[volume] >= max_per_volume:
            continue
        selected.append(row)
        counts[volume] += 1
        if limit and len(selected) >= limit:
            break
    return selected


def packet_row_from_review(row: dict[str, str], batch_id: str) -> dict[str, str]:
    marker = row.get("source_image_marker", "")
    review_batch = row.get("batch_id", "")
    review_note = (
        "Exact page-line-token reference-marker correction from source-image review; "
        "printed marker glyph confirmed; no broad marker, slash, Initial-I/l, or nasal rule."
    )
    if review_batch:
        review_note = f"{review_note} source_review_batch={review_batch}."
    if row.get("review_note", ""):
        review_note = f"{review_note} {row['review_note']}".strip()
    return {
        "volume": row.get("volume", ""),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "token_index": row.get("token_index", ""),
        "from_token": row.get("source_token", ""),
        "to_token": row.get("proposed_to_token", ""),
        "reason": REFERENCE_MARKER_REASON,
        "evidence": f"{SOURCE_IMAGE_EVIDENCE_TAG}:{batch_id}",
        "review_note": review_note,
        "batch_id": batch_id,
        "score": "100",
        "source_diagnostic": diagnostic_source_for_volume(row.get("volume", "")),
        "candidate_family": row.get("candidate_family", ""),
        "direction_basis": f"source_image_marker={marker};source_crop={row.get('source_crop', '')}",
        "context_type": "source_image_review",
        "positive_evidence": "source_image_marker_confirmed;unique_exact_marker_occurrence",
        "negative_evidence": "",
    }


def packet_rows_from_accepted_reviews(
    root: Path,
    rows: list[dict[str, str]],
    *,
    batch_id: str,
    limit: int,
    max_per_volume: int,
) -> list[dict[str, str]]:
    errors = validate_review_rows(root, rows)
    if errors:
        raise ValueError("Invalid source-image review rows:\n" + "\n".join(f"- {error}" for error in errors))
    selected = select_accepted_reviews(rows, limit=limit, max_per_volume=max_per_volume)
    return [packet_row_from_review(row, batch_id) for row in selected]
