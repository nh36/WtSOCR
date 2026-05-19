#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SAMPLE_SIZE = 100
RANDOM_SEED = 20260519


@dataclass(frozen=True)
class VolumeSpec:
    label: str
    display: str
    merged: str
    audit: str
    alternate: str
    final_name: str


VOLUMES = (
    VolumeSpec(
        label="wts_1_34",
        display="WtS 1-34",
        merged="work/line_anchor_full_20260225T165417Z_locked/WtS_1-34/WtS 1-34_lineanchored_merged_sample.txt",
        audit="work/line_anchor_full_20260225T165417Z_locked/WtS_1-34/WtS 1-34_lineanchored_audit.csv",
        alternate="pdfs/WtS 1-34.vision.txt",
        final_name="WtS_1-34_release_candidate.txt",
    ),
    VolumeSpec(
        label="wts_35_51",
        display="WtS 35-51",
        merged="work/line_anchor_full_20260225T165417Z_locked/WtS_35-51/WtS 35-51_lineanchored_merged_sample.txt",
        audit="work/line_anchor_full_20260225T165417Z_locked/WtS_35-51/WtS 35-51_lineanchored_audit.csv",
        alternate="pdfs/WtS 35-51.vision.txt",
        final_name="WtS_35-51_release_candidate.txt",
    ),
)


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
    limit: int = 50,
) -> list[dict[str, str]]:
    buckets: dict[tuple[str, str, str], dict[str, str]] = {}
    counts: Counter[tuple[str, str, str]] = Counter()

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
    for key, count in counts.most_common(limit):
        item = dict(buckets[key])
        item["count"] = str(count)
        out.append(item)
    return out


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


def run(output_dir: Path, sample_size: int, seed: int) -> None:
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
        f"Sample seed: `{seed}`",
        "",
    ]
    checksums: list[tuple[str, str]] = []

    for spec in VOLUMES:
        volume_dir = output_dir / spec.label
        corrected = volume_dir / f"{spec.label}_corrected_full.txt"
        final_text = final_dir / spec.final_name
        if not corrected.exists():
            raise FileNotFoundError(f"missing corrected text: {corrected}")
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
        suspicious = collect_suspicious_tokens(spec.display, validator_path, validators, review_path, reviews)
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
                f"- Base merged: `{spec.merged}`",
                f"- Audit CSV: `{spec.audit}`",
                f"- Google alternate witness: `{spec.alternate}`",
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
        report.extend(["", "### Top 50 Suspicious Tokens From Validator/Review Queues", ""])
        report.extend(
            md_table(
                ["source", "token", "reason_or_issue", "count", "suggestion", "sample_page", "sample_line", "sample_excerpt"],
                [
                    [
                        row["source"],
                        truncate(row["token"], 30),
                        truncate(row["reason_or_issue"], 45),
                        row["count"],
                        truncate(row["suggestion"], 30),
                        row["sample_page"],
                        row["sample_line"],
                        truncate(row["sample_excerpt"], 80),
                    ]
                    for row in suspicious
                ],
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
    write_tsv(
        output_dir / "top_suspicious_tokens.tsv",
        all_suspicious,
        [
            "volume",
            "source",
            "source_file",
            "token",
            "reason_or_issue",
            "count",
            "suggestion",
            "sample_page",
            "sample_line",
            "sample_excerpt",
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
            f"- `{output_dir / 'pages_with_many_changes.tsv'}`",
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
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    run(args.output_dir, args.sample_size, args.seed)


if __name__ == "__main__":
    main()
