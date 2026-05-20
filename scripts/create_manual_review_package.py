#!/usr/bin/env python3
"""Create a manual review package from a production QA output directory."""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


VOLUMES = [
    ("WtS 1-34", "wts_1_34", "WtS_1-34_release_candidate.txt"),
    ("WtS 35-51", "wts_35_51", "WtS_35-51_release_candidate.txt"),
    ("WtS 8-b", "wts_8_b", "WtS_8-b_release_candidate.txt"),
    ("WtS 9-m", "wts_9_m", "WtS_9-m_release_candidate.txt"),
]

PACKAGE_FILES = [
    "production_release_candidate_report.md",
    "residual_real_suspicious_tokens.tsv",
    "manual_review_only_suspicious_tokens.tsv",
    "sample_changes_for_manual_review.tsv",
    "sample_review_queue_for_manual_review.tsv",
    "sample_google_adoptions_for_manual_review.tsv",
    "pages_with_many_changes.tsv",
    "suspicious_token_classification_summary.tsv",
]


@dataclass(frozen=True)
class Volume:
    label: str
    slug: str
    final_name: str


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def copy_required(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def load_page_text(corrected_full: Path) -> list[str]:
    return corrected_full.read_text(encoding="utf-8").split("\f")


def rows_by_volume_page(rows: list[dict[str, str]], page_field: str = "page") -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        volume = row.get("volume", "")
        page = row.get(page_field, "")
        if volume and page:
            grouped[(volume, page)].append(row)
    return grouped


def format_row(row: dict[str, str], fields: list[str]) -> str:
    parts = []
    for field in fields:
        value = row.get(field, "")
        if value:
            parts.append(f"{field}={value}")
    return "; ".join(parts) if parts else "(no details)"


def make_dense_page_excerpts(input_dir: Path, output_dir: Path) -> None:
    page_rows = read_tsv(input_dir / "pages_with_many_changes.tsv")
    manual_rows = read_tsv(input_dir / "manual_review_only_suspicious_tokens.tsv")
    residual_rows = read_tsv(input_dir / "residual_real_suspicious_tokens.tsv")

    manual_by_page = rows_by_volume_page(manual_rows, "sample_page")
    residual_by_page = rows_by_volume_page(residual_rows, "sample_page")

    for label, slug, _final_name in VOLUMES:
        volume = Volume(label, slug, _final_name)
        top_pages = [row for row in page_rows if row.get("volume") == volume.label][:10]
        review_rows = read_tsv(input_dir / volume.slug / f"{volume.slug}_review_queue.tsv")
        review_by_page = rows_by_volume_page(
            [{**row, "volume": volume.label} for row in review_rows],
            "page",
        )
        pages = load_page_text(input_dir / volume.slug / f"{volume.slug}_corrected_full.txt")
        output_path = output_dir / f"{volume.label.replace(' ', '_')}_dense_page_review_excerpt.txt"
        with output_path.open("w", encoding="utf-8", newline="\n") as out:
            out.write(f"{volume.label} dense-page review excerpts\n")
            out.write("=" * (len(volume.label) + 27) + "\n\n")
            for row in top_pages:
                page = row.get("page", "")
                out.write(f"Page {page}\n")
                out.write("-" * (len(page) + 5) + "\n")
                out.write(
                    "Counts: "
                    f"changes={row.get('changes', '')}; "
                    f"review_queue={row.get('review_queue', '')}; "
                    f"validator_issues={row.get('validator_issues', '')}; "
                    f"alternate_unresolved={row.get('alternate_unresolved', '')}; "
                    f"total_attention_rows={row.get('total_attention_rows', '')}\n\n"
                )

                out.write("Review queue rows for this page:\n")
                page_review_rows = review_by_page.get((volume.label, page), [])
                if page_review_rows:
                    for review in page_review_rows:
                        out.write(
                            "- "
                            + format_row(
                                review,
                                ["line", "reason", "from_token", "to_token", "zone", "tier", "line_excerpt"],
                            )
                            + "\n"
                        )
                else:
                    out.write("- none\n")
                out.write("\n")

                out.write("Manual-review-only suspicious rows sampled on this page:\n")
                page_manual_rows = manual_by_page.get((volume.label, page), [])
                if page_manual_rows:
                    for manual in page_manual_rows:
                        out.write(
                            "- "
                            + format_row(
                                manual,
                                ["token", "reason_or_issue", "suggestion", "count", "sample_line", "sample_excerpt"],
                            )
                            + "\n"
                        )
                else:
                    out.write("- none\n")
                out.write("\n")

                out.write("Residual-real candidate rows sampled on this page:\n")
                page_residual_rows = residual_by_page.get((volume.label, page), [])
                if page_residual_rows:
                    for residual in page_residual_rows:
                        out.write(
                            "- "
                            + format_row(
                                residual,
                                ["token", "reason_or_issue", "suggestion", "count", "sample_line", "sample_excerpt"],
                            )
                            + "\n"
                        )
                else:
                    out.write("- none\n")
                out.write("\n")

                out.write("Corrected text excerpt:\n")
                try:
                    page_index = int(page) - 1
                except ValueError:
                    page_index = -1
                if 0 <= page_index < len(pages):
                    for line_no, line in enumerate(pages[page_index].splitlines(), start=1):
                        out.write(f"{line_no:04d}: {line}\n")
                else:
                    out.write("(page text unavailable)\n")
                out.write("\n\n")


def aggregate_classification_summary(input_dir: Path) -> list[tuple[str, int, int]]:
    rows = read_tsv(input_dir / "suspicious_token_classification_summary.tsv")
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        classification = row.get("classification", "")
        if not classification:
            continue
        totals[classification][0] += int(row.get("rows") or 0)
        totals[classification][1] += int(row.get("occurrences") or 0)
    return sorted((key, value[0], value[1]) for key, value in totals.items())


def write_readme(input_dir: Path, output_dir: Path) -> None:
    checksums = (input_dir / "final" / "SHA256SUMS.txt").read_text(encoding="utf-8").strip()
    residual_rows = read_tsv(input_dir / "residual_real_suspicious_tokens.tsv")
    classifications = aggregate_classification_summary(input_dir)
    files = sorted(path.name for path in output_dir.iterdir() if path.is_file())

    readme = output_dir / "README.md"
    with readme.open("w", encoding="utf-8", newline="\n") as out:
        out.write("# WtS OCR Manual Review Package\n\n")
        out.write(
            "This package contains the current release-candidate OCR text and QA "
            "artifacts for manual scholarly review. It was generated from:\n\n"
        )
        out.write(f"`{input_dir}`\n\n")
        out.write(
            "The text files are copied from the `final/` release-candidate outputs. "
            "No OCR rules are applied during packaging, and corrected text is not modified.\n\n"
        )

        out.write("## Checksums\n\n")
        out.write("```text\n")
        out.write(checksums + "\n")
        out.write("```\n\n")

        out.write("## Files\n\n")
        for name in files:
            out.write(f"- `{name}`\n")
        out.write("\n")

        out.write("## QA Classification Summary\n\n")
        out.write("| Classification | Rows | Occurrences |\n")
        out.write("| --- | ---: | ---: |\n")
        for classification, rows, occurrences in classifications:
            out.write(f"| `{classification}` | {rows} | {occurrences} |\n")
        out.write("\n")

        out.write("## Residual Candidate Decisions\n\n")
        out.write(
            "The readiness review found no residual candidate that justified an "
            "automatic exact OCR fix before release. Review these rows first:\n\n"
        )
        for row in residual_rows:
            out.write(
                "- "
                f"{row.get('volume', '')} page {row.get('sample_page', '')}, "
                f"line {row.get('sample_line', '')}: `{row.get('token', '')}` "
                f"-> `{row.get('suggestion', '')}`; "
                f"{row.get('sample_excerpt', '')}\n"
            )
        out.write("\n")

        out.write("## Remaining Known Issues\n\n")
        out.write(
            "- Manual-review-only transliteration candidates remain for initial `I`/`l`, "
            "`ñ`/`ṅ`/`n`, and lowercase `$`/`ś` contexts outside exact reviewed allowlists.\n"
        )
        out.write(
            "- Citation/siglum and Sanskrit/Indic edge cases should be reviewed with source context.\n"
        )
        out.write(
            "- German/prose validator rows are separated as QA noise and should not drive OCR rules.\n\n"
        )

        out.write("## Suggested Manual Review Order\n\n")
        out.write("1. `residual_real_suspicious_tokens.tsv`\n")
        out.write("2. `manual_review_only_suspicious_tokens.tsv`\n")
        out.write("3. Dense-page excerpt files, one per volume\n")
        out.write("4. `sample_google_adoptions_for_manual_review.tsv`\n")
        out.write("5. `sample_changes_for_manual_review.tsv`\n")


def create_package(input_dir: Path, output_dir: Path, readiness_note: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for _label, _slug, final_name in VOLUMES:
        copy_required(input_dir / "final" / final_name, output_dir / final_name)
    copy_required(input_dir / "final" / "SHA256SUMS.txt", output_dir / "SHA256SUMS.txt")

    for name in PACKAGE_FILES:
        copy_required(input_dir / name, output_dir / name)
    copy_required(readiness_note, output_dir / "README_RELEASE_CANDIDATE.md")

    make_dense_page_excerpts(input_dir, output_dir)
    write_readme(input_dir, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("work/production_release_candidate_clean_qa_20260520T055946Z"),
        help="Production QA output directory to package.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("work/manual_review_package_20260520"),
        help="Manual review package directory to create.",
    )
    parser.add_argument(
        "--readiness-note",
        type=Path,
        default=Path("docs/release_candidate_readiness_2026-05-20.md"),
        help="Readiness note to copy as README_RELEASE_CANDIDATE.md.",
    )
    args = parser.parse_args()
    create_package(args.input_dir, args.output_dir, args.readiness_note)
    print(f"Created manual review package: {args.output_dir}")


if __name__ == "__main__":
    main()
