#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SAMPLE_SIZE = 100
RANDOM_SEED = 20260519
MANIFEST_PATH = Path("data/production_volume_inputs.tsv")
MANIFEST_COLUMNS = [
    "label",
    "display",
    "source_pdf",
    "merged",
    "audit",
    "google_vision",
    "final_name",
    "status",
    "note",
]
SUSPICIOUS_CLASS_ORDER = [
    "residual_real_candidate",
    "manual_review_only",
    "unclear",
    "citation_or_siglum",
    "sanskrit_or_indic",
    "german_or_prose_false_positive",
    "already_corrected_or_stale",
]
SUSPICIOUS_CLASS_PRIORITY = {name: idx for idx, name in enumerate(SUSPICIOUS_CLASS_ORDER)}
TOKEN_EDGE_CHARS = " \t\r\n\f\v.,;:!?()[]{}<>\"“”‘’‚‹›«»"
GERMAN_UMLAUT_CHARS = set("äöüÄÖÜß")
GERMAN_FALSE_POSITIVE_TOKENS = {
    "abkürzungsverzeichnisse",
    "abhängigkeit",
    "anhänger",
    "bewußtsein",
    "erklärung",
    "fülle",
    "gefühle",
    "glück",
    "körper",
    "könig",
    "königs",
    "länge",
    "öffnung",
    "prüfung",
    "rückkehr",
    "rüstung",
    "unglück",
    "übersetzung",
    "überlieferung",
    "verfügung",
    "wörterbuch",
}
SANSKRIT_INDIC_HINTS = (
    "ācāry",
    "acary",
    "āgama",
    "agama",
    "avalok",
    "bodhisatt",
    "dharma",
    "gangä",
    "gangā",
    "jñ",
    "jn",
    "mantra",
    "nāg",
    "näg",
    "praj",
    "pāram",
    "päram",
    "śāstr",
    "śästr",
    "śrāv",
    "śräv",
    "sūtr",
    "sutra",
    "tantra",
    "vajra",
)


@dataclass(frozen=True)
class VolumeSpec:
    label: str
    display: str
    source_pdf: str
    merged: str
    audit: str
    google_vision: str
    final_name: str
    status: str
    note: str

    @property
    def alternate(self) -> str:
        return self.google_vision


def load_volume_manifest(path: Path = MANIFEST_PATH) -> list[VolumeSpec]:
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        missing = [column for column in MANIFEST_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
        volumes: list[VolumeSpec] = []
        for row in reader:
            if not any((value or "").strip() for value in row.values()):
                continue
            values = {column: (row.get(column, "") or "").strip() for column in MANIFEST_COLUMNS}
            volumes.append(VolumeSpec(**values))
    return volumes


def manifest_path_state(path_text: str) -> str:
    if not path_text:
        return "blank"
    return "present" if Path(path_text).exists() else "missing"


def missing_ready_inputs(spec: VolumeSpec) -> list[str]:
    missing: list[str] = []
    for field in ["source_pdf", "merged", "audit", "google_vision"]:
        path_text = getattr(spec, field)
        if not path_text or not Path(path_text).exists():
            missing.append(field)
    return missing


def select_ready_volumes(volumes: list[VolumeSpec]) -> tuple[list[VolumeSpec], list[str]]:
    ready: list[VolumeSpec] = []
    warnings: list[str] = []
    for spec in volumes:
        if spec.status != "ready":
            warnings.append(f"Skipping {spec.display}: status={spec.status} ({spec.note})")
            continue
        missing = missing_ready_inputs(spec)
        if missing:
            warnings.append(f"Skipping {spec.display}: ready row has missing inputs: {', '.join(missing)}")
            continue
        ready.append(spec)
    return ready, warnings


def volume_coverage_rows(volumes: list[VolumeSpec], included: set[str]) -> list[list[object]]:
    rows: list[list[object]] = []
    for spec in volumes:
        rows.append(
            [
                spec.display,
                spec.status,
                "yes" if spec.label in included else "no",
                manifest_path_state(spec.source_pdf),
                manifest_path_state(spec.merged),
                manifest_path_state(spec.audit),
                manifest_path_state(spec.google_vision),
                spec.note,
            ]
        )
    return rows


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_by(rows: list[dict[str, str]], key: str) -> Counter[str]:
    return Counter(row.get(key, "") or "(blank)" for row in rows)


def top_by_page(rows: list[dict[str, str]], limit: int = 20) -> list[tuple[str, int]]:
    return Counter(row.get("page", "") or "(blank)" for row in rows).most_common(limit)


def stratified_sample(
    rows: list[dict[str, str]],
    key: str,
    sample_size: int,
    rng: random.Random,
) -> list[dict[str, str]]:
    if len(rows) <= sample_size:
        result = list(rows)
        rng.shuffle(result)
        return result
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row.get(key, "") or "(blank)"].append(row)
    total = len(rows)
    selected: list[dict[str, str]] = []
    seen: set[int] = set()
    for group_rows in sorted(groups.values(), key=len, reverse=True):
        quota = max(1, round(sample_size * len(group_rows) / total))
        picks = rng.sample(group_rows, min(quota, len(group_rows)))
        for row in picks:
            row_id = id(row)
            if row_id not in seen:
                selected.append(row)
                seen.add(row_id)
    if len(selected) > sample_size:
        selected = rng.sample(selected, sample_size)
    elif len(selected) < sample_size:
        remaining = [row for row in rows if id(row) not in seen]
        selected.extend(rng.sample(remaining, min(sample_size - len(selected), len(remaining))))
    selected.sort(key=lambda r: (safe_int(r.get("page", "")), safe_int(r.get("line", "")), r.get("reason", "")))
    return selected


def safe_int(value: str | None) -> int:
    try:
        return int(value or "0")
    except ValueError:
        return 0


def truncate(value: str, limit: int = 110) -> str:
    value = (value or "").replace("\n", " ").replace("\r", " ")
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def md_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(md_escape(cell) for cell in row) + " |")
    return out


def reason_table(counter: Counter[str]) -> list[list[object]]:
    return [[reason, count] for reason, count in counter.most_common()]


def normalize_report_token(token: str) -> str:
    return (token or "").strip(TOKEN_EDGE_CHARS)


def corrected_token_counter(text: str) -> Counter[str]:
    tokens: Counter[str] = Counter()
    for piece in re.split(r"\s+", text or ""):
        token = normalize_report_token(piece)
        if token:
            tokens[token] += 1
    return tokens


def applied_from_token_counter(changes: list[dict[str, str]], adoptions: list[dict[str, str]]) -> Counter[str]:
    tokens: Counter[str] = Counter()
    for row in changes:
        if row.get("applied", "1") == "0":
            continue
        token = normalize_report_token(row.get("from_token", ""))
        if token:
            tokens[token] += 1
    for row in adoptions:
        token = normalize_report_token(row.get("base_token", ""))
        if token:
            tokens[token] += 1
    return tokens


def looks_like_sanskrit_or_indic(token: str, reason: str, excerpt: str) -> bool:
    token_l = normalize_report_token(token).lower()
    context_l = f"{reason} {excerpt}".lower()
    if "sanskrit" in context_l or "indic" in context_l or "skt" in context_l:
        return True
    return any(hint in token_l or hint in context_l for hint in SANSKRIT_INDIC_HINTS)


def looks_like_german_or_prose(token: str, reason: str, excerpt: str) -> bool:
    token_l = normalize_report_token(token).lower()
    reason_l = (reason or "").lower()
    if "german" in reason_l:
        return True
    if token_l in GERMAN_FALSE_POSITIVE_TOKENS:
        return True
    return any(char in token for char in GERMAN_UMLAUT_CHARS)


def looks_like_citation_or_siglum(token: str, reason: str, excerpt: str) -> bool:
    token_s = normalize_report_token(token)
    reason_l = (reason or "").lower()
    excerpt_l = (excerpt or "").lower()
    if "citation" in reason_l or "siglum" in reason_l:
        return True
    if "$" in token_s and any(char.isupper() for char in token_s):
        return True
    if re.fullmatch(r"[A-Z][A-Za-z$Śś-]{1,12}(?:-[A-Z])?", token_s):
        return any(cue in excerpt_l for cue in ["lex.", "sigl", "mahāvy", "mahavy", "t.", "p.", "liś", "viś"])
    return False


def looks_manual_review_only(token: str, reason: str, suggestion: str) -> bool:
    token_s = normalize_report_token(token)
    reason_l = (reason or "").lower()
    if not suggestion or normalize_report_token(suggestion) == token_s:
        return False
    if "review" in reason_l:
        return True
    if "confusable" in reason_l:
        return True
    if "$" in token_s or "ñ" in token_s or "ṅ" in token_s:
        return True
    return bool(re.match(r"I[a-z]", token_s))


def classify_suspicious_token(
    row: dict[str, str],
    corrected_tokens: Counter[str],
    applied_from_tokens: Counter[str],
) -> tuple[str, str]:
    token = normalize_report_token(row.get("token", ""))
    reason = row.get("reason_or_issue", "")
    suggestion = normalize_report_token(row.get("suggestion", ""))
    excerpt = row.get("sample_excerpt", "")
    exact_count = corrected_tokens[token]
    applied_count = applied_from_tokens[token]
    if not token:
        return "unclear", "blank token in source QA row"
    if applied_count and not exact_count:
        return (
            "already_corrected_or_stale",
            f"appears as applied from_token {applied_count} time(s) and not as an exact corrected-text token",
        )
    if not exact_count:
        return "already_corrected_or_stale", "not found as an exact token in corrected text"
    if looks_like_sanskrit_or_indic(token, reason, excerpt):
        return "sanskrit_or_indic", "Sanskrit/Indic lexical or context cue"
    if looks_like_german_or_prose(token, reason, excerpt):
        return "german_or_prose_false_positive", "German/prose token flagged by transliteration validator"
    if looks_like_citation_or_siglum(token, reason, excerpt):
        return "citation_or_siglum", "citation/siglum-shaped token or context"
    if applied_count:
        return "already_corrected_or_stale", f"also appears as applied from_token {applied_count} time(s)"
    if looks_manual_review_only(token, reason, suggestion):
        return "manual_review_only", "possible OCR issue, but context-sensitive or unsafe for automatic correction"
    if suggestion and suggestion != token:
        return "residual_real_candidate", "appears in corrected text with a validator suggestion"
    return "unclear", "no safe automatic classification evidence"


def sort_suspicious_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (
            SUSPICIOUS_CLASS_PRIORITY.get(row.get("classification", "unclear"), 99),
            -safe_int(row.get("count", "")),
            row.get("volume", ""),
            row.get("token", ""),
            row.get("source", ""),
        ),
    )


def suspicious_summary_rows(rows: list[dict[str, str]], volume: str = "") -> list[dict[str, str]]:
    row_counts: Counter[str] = Counter()
    occurrence_counts: Counter[str] = Counter()
    for row in rows:
        classification = row.get("classification", "unclear") or "unclear"
        row_counts[classification] += 1
        occurrence_counts[classification] += safe_int(row.get("count", ""))
    return [
        {
            "volume": volume,
            "classification": classification,
            "rows": str(row_counts[classification]),
            "occurrences": str(occurrence_counts[classification]),
        }
        for classification in SUSPICIOUS_CLASS_ORDER
        if row_counts[classification]
    ]


def sample_change_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "reason": row.get("reason", ""),
        "from_token": row.get("from_token", ""),
        "to_token": row.get("to_token", ""),
        "line_excerpt": row.get("line_excerpt", ""),
        "zone": row.get("zone", ""),
        "tier": row.get("tier", ""),
        "alignment_method": row.get("alignment_method", ""),
        "alternate_page": row.get("alternate_page", ""),
    }


def sample_adoption_row(volume: str, source_file: Path, row: dict[str, str]) -> dict[str, str]:
    return {
        "volume": volume,
        "source_file": str(source_file),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "reason": row.get("reason", ""),
        "from_token": row.get("base_token", ""),
        "to_token": row.get("alternate_token", ""),
        "line_excerpt": row.get("base_line", ""),
        "zone": "",
        "tier": "",
        "alignment_method": row.get("alignment_method", ""),
        "alternate_page": row.get("alternate_page", ""),
    }


def collect_suspicious_tokens(
    volume: str,
    validator_path: Path,
    validator_rows: list[dict[str, str]],
    review_path: Path,
    review_rows: list[dict[str, str]],
    corrected_text: str,
    changes: list[dict[str, str]],
    adoptions: list[dict[str, str]],
    limit: int | None = None,
) -> list[dict[str, str]]:
    buckets: dict[tuple[str, str, str], dict[str, str]] = {}
    counts: Counter[tuple[str, str, str]] = Counter()
    corrected_tokens = corrected_token_counter(corrected_text)
    applied_from_tokens = applied_from_token_counter(changes, adoptions)

    def add(source: str, token: str, reason: str, suggestion: str, row: dict[str, str], source_file: Path) -> None:
        token = token.strip()
        if not token:
            return
        key = (source, token, reason or "(blank)")
        counts[key] += 1
        buckets.setdefault(
            key,
            {
                "volume": volume,
                "source": source,
                "source_file": str(source_file),
                "token": token,
                "reason_or_issue": reason,
                "suggestion": suggestion,
                "sample_page": row.get("page", ""),
                "sample_line": row.get("line", ""),
                "sample_excerpt": row.get("line_excerpt", ""),
            },
        )

    for row in validator_rows:
        add("validator", row.get("token", ""), row.get("issue", ""), row.get("suggestion", ""), row, validator_path)
    for row in review_rows:
        add("review_queue_from", row.get("from_token", ""), row.get("reason", ""), row.get("to_token", ""), row, review_path)
        add("review_queue_to", row.get("to_token", ""), row.get("reason", ""), row.get("from_token", ""), row, review_path)

    out: list[dict[str, str]] = []
    for key, count in counts.items():
        item = dict(buckets[key])
        item["count"] = str(count)
        token = normalize_report_token(item["token"])
        classification, evidence = classify_suspicious_token(item, corrected_tokens, applied_from_tokens)
        item["classification"] = classification
        item["evidence"] = evidence
        item["corrected_text_exact_count"] = str(corrected_tokens[token])
        item["applied_change_count"] = str(applied_from_tokens[token])
        out.append(item)
    out = sort_suspicious_rows(out)
    return out if limit is None else out[:limit]


def page_attention_rows(
    volume: str,
    changes: list[dict[str, str]],
    reviews: list[dict[str, str]],
    validators: list[dict[str, str]],
    unresolved: list[dict[str, str]],
    limit: int = 50,
) -> list[dict[str, str]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for name, rows in [
        ("changes", changes),
        ("review_queue", reviews),
        ("validator_issues", validators),
        ("alternate_unresolved", unresolved),
    ]:
        for row in rows:
            page = row.get("page", "") or "(blank)"
            counts[page][name] += 1
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-(kv[1]["changes"] + kv[1]["review_queue"] + kv[1]["validator_issues"] + kv[1]["alternate_unresolved"]), safe_int(kv[0])),
    )
    out: list[dict[str, str]] = []
    for page, c in ranked[:limit]:
        total = c["changes"] + c["review_queue"] + c["validator_issues"] + c["alternate_unresolved"]
        out.append(
            {
                "volume": volume,
                "page": page,
                "changes": str(c["changes"]),
                "review_queue": str(c["review_queue"]),
                "validator_issues": str(c["validator_issues"]),
                "alternate_unresolved": str(c["alternate_unresolved"]),
                "total_attention_rows": str(total),
            }
        )
    return out


def markdown_sample_rows(rows: list[dict[str, str]]) -> list[list[object]]:
    return [
        [
            row.get("page", ""),
            row.get("line", ""),
            truncate(row.get("reason", ""), 45),
            truncate(row.get("from_token", ""), 35),
            truncate(row.get("to_token", ""), 35),
            truncate(row.get("alignment_method", ""), 30),
            truncate(row.get("line_excerpt", ""), 90),
        ]
        for row in rows
    ]


def markdown_suspicious_rows(rows: list[dict[str, str]], limit: int = 50) -> list[list[object]]:
    return [
        [
            row.get("classification", ""),
            row.get("source", ""),
            truncate(row.get("token", ""), 30),
            truncate(row.get("reason_or_issue", ""), 45),
            row.get("count", ""),
            truncate(row.get("suggestion", ""), 30),
            truncate(row.get("evidence", ""), 80),
            row.get("sample_page", ""),
            row.get("sample_line", ""),
            truncate(row.get("sample_excerpt", ""), 80),
        ]
        for row in rows[:limit]
    ]


def run(output_dir: Path, sample_size: int, seed: int, manifest_path: Path = MANIFEST_PATH) -> None:
    volumes = load_volume_manifest(manifest_path)
    ready_volumes, warnings = select_ready_volumes(volumes)
    if not ready_volumes:
        raise ValueError(f"No ready production volumes found in {manifest_path}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    rng = random.Random(seed)
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    all_change_samples: list[dict[str, str]] = []
    all_review_samples: list[dict[str, str]] = []
    all_adoption_samples: list[dict[str, str]] = []
    all_suspicious: list[dict[str, str]] = []
    all_pages_attention: list[dict[str, str]] = []
    report: list[str] = [
        "# Production Release-Candidate OCR QA Report",
        "",
        f"Output directory: `{output_dir}`",
        f"Volume manifest: `{manifest_path}`",
        f"Sample seed: `{seed}`",
        "",
        "## Volume Coverage",
        "",
    ]
    report.extend(
        md_table(
            [
                "volume",
                "status",
                "included",
                "source_pdf",
                "merged",
                "audit",
                "google_vision",
                "note",
            ],
            volume_coverage_rows(volumes, {spec.label for spec in ready_volumes}),
        )
    )
    report.append("")
    checksums: list[tuple[str, str]] = []

    for spec in ready_volumes:
        volume_dir = output_dir / spec.label
        corrected = volume_dir / f"{spec.label}_corrected_full.txt"
        final_text = final_dir / spec.final_name
        if not corrected.exists():
            raise FileNotFoundError(f"missing corrected text: {corrected}")
        corrected_text = corrected.read_text(encoding="utf-8", errors="replace")
        shutil.copy2(corrected, final_text)
        checksum = sha256_file(final_text)
        checksums.append((checksum, final_text.name))

        summary_path = volume_dir / f"{spec.label}_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8", errors="replace"))
        changes_path = volume_dir / f"{spec.label}_changes.tsv"
        review_path = volume_dir / f"{spec.label}_review_queue.tsv"
        validator_path = volume_dir / f"{spec.label}_validator_issues.tsv"
        adoptions_path = volume_dir / f"{spec.label}_alternate_witness_adoptions.tsv"
        unresolved_path = volume_dir / f"{spec.label}_alternate_witness_unresolved.tsv"
        changes = read_tsv(changes_path)
        reviews = read_tsv(review_path)
        validators = read_tsv(validator_path)
        adoptions = read_tsv(adoptions_path)
        unresolved = read_tsv(unresolved_path)

        change_samples = [
            sample_change_row(spec.display, changes_path, row)
            for row in stratified_sample(changes, "reason", sample_size, rng)
        ]
        review_samples = [
            sample_change_row(spec.display, review_path, row)
            for row in stratified_sample(reviews, "reason", sample_size, rng)
        ]
        adoption_samples = [
            sample_adoption_row(spec.display, adoptions_path, row)
            for row in stratified_sample(adoptions, "reason", sample_size, rng)
        ]
        suspicious = collect_suspicious_tokens(
            spec.display,
            validator_path,
            validators,
            review_path,
            reviews,
            corrected_text,
            changes,
            adoptions,
        )
        attention = page_attention_rows(spec.display, changes, reviews, validators, unresolved)
        all_change_samples.extend(change_samples)
        all_review_samples.extend(review_samples)
        all_adoption_samples.extend(adoption_samples)
        all_suspicious.extend(suspicious)
        all_pages_attention.extend(attention)

        report.extend(
            [
                f"## {spec.display}",
                "",
                "### Inputs",
                "",
                f"- Source PDF: `{spec.source_pdf}`",
                f"- Base merged: `{spec.merged}`",
                f"- Audit CSV: `{spec.audit}`",
                f"- Google alternate witness: `{spec.google_vision}`",
                "",
                "### Output Summary",
                "",
            ]
        )
        report.extend(
            md_table(
                ["metric", "value"],
                [
                    ["corrected_full", str(corrected)],
                    ["release_candidate", str(final_text)],
                    ["sha256", checksum],
                    ["pages", summary.get("pages", "")],
                    ["total_lines_seen", summary.get("total_lines_seen", "")],
                    ["non_empty_lines", summary.get("non_empty_lines", "")],
                    ["entries_detected", summary.get("entries_detected", "")],
                    ["alternate_witness_adoptions", len(adoptions)],
                    ["alternate_witness_unresolved", len(unresolved)],
                ],
            )
        )
        report.extend(["", "### Postprocess Changes By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(changes, "reason"))))
        report.extend(["", "### Review Queue By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(reviews, "reason"))))
        report.extend(["", "### Google Alternate-Witness Adoptions By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(adoptions, "reason"))))
        report.extend(["", "### Google Alternate-Witness Adoptions By Alignment Method", ""])
        report.extend(md_table(["alignment_method", "count"], reason_table(count_by(adoptions, "alignment_method"))))
        report.extend(["", "### Unresolved Alternate-Witness Rows By Reason", ""])
        report.extend(md_table(["reason", "count"], reason_table(count_by(unresolved, "reason"))))
        report.extend(["", "### Suspicious Token Classification", ""])
        report.extend(
            md_table(
                ["classification", "rows", "occurrences"],
                [
                    [row["classification"], row["rows"], row["occurrences"]]
                    for row in suspicious_summary_rows(suspicious)
                ],
            )
        )
        focused_suspicious = [
            row
            for row in suspicious
            if row.get("classification") in {"residual_real_candidate", "manual_review_only", "unclear"}
        ]
        german_suspicious = [row for row in suspicious if row.get("classification") == "german_or_prose_false_positive"]
        stale_suspicious = [row for row in suspicious if row.get("classification") == "already_corrected_or_stale"]
        report.extend(["", "### Top Residual Or Manual-Review Suspicious Tokens", ""])
        report.extend(
            md_table(
                [
                    "classification",
                    "source",
                    "token",
                    "reason_or_issue",
                    "count",
                    "suggestion",
                    "evidence",
                    "sample_page",
                    "sample_line",
                    "sample_excerpt",
                ],
                markdown_suspicious_rows(focused_suspicious),
            )
        )
        report.extend(["", "### Top German/Prose Validator False Positives", ""])
        report.extend(
            md_table(
                ["classification", "source", "token", "reason_or_issue", "count", "suggestion", "evidence", "sample_page", "sample_line", "sample_excerpt"],
                markdown_suspicious_rows(german_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Stale Or Already-Corrected Suspicious Tokens", ""])
        report.extend(
            md_table(
                ["classification", "source", "token", "reason_or_issue", "count", "suggestion", "evidence", "sample_page", "sample_line", "sample_excerpt"],
                markdown_suspicious_rows(stale_suspicious, limit=20),
            )
        )
        report.extend(["", "### Top Pages By Number Of Changes", ""])
        report.extend(md_table(["page", "changes"], top_by_page(changes)))
        report.extend(["", "### Top Pages By Unresolved Alternate-Witness Rows", ""])
        report.extend(md_table(["page", "unresolved_rows"], top_by_page(unresolved)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(change_samples))} Changes", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(change_samples)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(review_samples))} Review-Queue Items", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(review_samples)))
        report.extend(["", f"### Random Sample Of {min(sample_size, len(adoption_samples))} Google Adoptions", ""])
        report.extend(md_table(["page", "line", "reason", "from", "to", "alignment", "excerpt"], markdown_sample_rows(adoption_samples)))
        report.extend(
            [
                "",
                "### Short Risk Assessment",
                "",
                f"- Highest validator issue: `{count_by(validators, 'issue').most_common(1)[0][0] if validators else 'none'}`.",
                f"- Highest review-queue reason: `{count_by(reviews, 'reason').most_common(1)[0][0] if reviews else 'none'}`.",
                f"- Highest unresolved alternate-witness reason: `{count_by(unresolved, 'reason').most_common(1)[0][0] if unresolved else 'none'}`.",
                "- Google witness adoptions remain token-gated; raw Google line replacement is not used.",
                "",
            ]
        )

    checksum_path = final_dir / "SHA256SUMS.txt"
    checksum_path.write_text(
        "".join(f"{checksum}  {name}\n" for checksum, name in checksums),
        encoding="utf-8",
    )

    manual_fields = [
        "volume",
        "source_file",
        "page",
        "line",
        "reason",
        "from_token",
        "to_token",
        "line_excerpt",
        "zone",
        "tier",
        "alignment_method",
        "alternate_page",
    ]
    write_tsv(output_dir / "sample_changes_for_manual_review.tsv", all_change_samples, manual_fields)
    write_tsv(output_dir / "sample_review_queue_for_manual_review.tsv", all_review_samples, manual_fields)
    write_tsv(output_dir / "sample_google_adoptions_for_manual_review.tsv", all_adoption_samples, manual_fields)
    suspicious_fields = [
        "volume",
        "source",
        "source_file",
        "token",
        "reason_or_issue",
        "count",
        "suggestion",
        "classification",
        "evidence",
        "sample_page",
        "sample_line",
        "sample_excerpt",
        "corrected_text_exact_count",
        "applied_change_count",
    ]
    write_tsv(
        output_dir / "top_suspicious_tokens.tsv",
        all_suspicious,
        suspicious_fields,
    )
    write_tsv(
        output_dir / "residual_real_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "residual_real_candidate"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "stale_or_already_corrected_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "already_corrected_or_stale"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "german_false_positive_validator_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "german_or_prose_false_positive"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "manual_review_only_suspicious_tokens.tsv",
        [row for row in all_suspicious if row.get("classification") == "manual_review_only"],
        suspicious_fields,
    )
    write_tsv(
        output_dir / "suspicious_token_classification_summary.tsv",
        [
            row
            for volume in sorted({row.get("volume", "") for row in all_suspicious})
            for row in suspicious_summary_rows(
                [item for item in all_suspicious if item.get("volume", "") == volume],
                volume,
            )
        ],
        [
            "volume",
            "classification",
            "rows",
            "occurrences",
        ],
    )
    write_tsv(
        output_dir / "pages_with_many_changes.tsv",
        all_pages_attention,
        [
            "volume",
            "page",
            "changes",
            "review_queue",
            "validator_issues",
            "alternate_unresolved",
            "total_attention_rows",
        ],
    )

    report.extend(
        [
            "## Manual Review Package",
            "",
            f"- `{output_dir / 'sample_changes_for_manual_review.tsv'}`",
            f"- `{output_dir / 'sample_review_queue_for_manual_review.tsv'}`",
            f"- `{output_dir / 'sample_google_adoptions_for_manual_review.tsv'}`",
            f"- `{output_dir / 'top_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'residual_real_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'manual_review_only_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'stale_or_already_corrected_suspicious_tokens.tsv'}`",
            f"- `{output_dir / 'german_false_positive_validator_tokens.tsv'}`",
            f"- `{output_dir / 'suspicious_token_classification_summary.tsv'}`",
            f"- `{output_dir / 'pages_with_many_changes.tsv'}`",
            "",
            "Warning: stale/already-corrected suspicious-token artifacts and German/prose false positives should not drive new OCR correction rules.",
            "",
            "## Cross-Volume Top Risk Categories",
            "",
            "1. Remaining transliteration-shape validator issues need manual/rule review before release.",
            "2. German umlaut tokens in transliteration-like contexts remain a high-volume validator bucket.",
            "3. Confusable-character validator issues remain concentrated in OCR-sensitive romanization tokens.",
            "4. Review-queue suggestions are still manual-only and should be sampled before promotion.",
            "5. Unresolved Google alternate-witness rows are useful diagnostics, but not a release success metric.",
            "",
        ]
    )
    (output_dir / "production_release_candidate_report.md").write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate production OCR QA report from postprocess outputs.")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    run(args.output_dir, args.sample_size, args.seed, args.manifest)


if __name__ == "__main__":
    main()
