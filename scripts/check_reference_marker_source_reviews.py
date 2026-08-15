#!/usr/bin/env python3
"""Validate tracked source-image reference-marker review rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import exact_promotion_batch as batch
import reference_marker_source_review as source_review


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("data/reference_marker_source_image_reviews.tsv"))
    parser.add_argument("--root", type=Path, default=repo_root())
    args = parser.parse_args()

    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    if not ledger.exists():
        print(f"Missing source-image review ledger: {ledger}", file=sys.stderr)
        return 1
    fields, rows = batch.read_tsv_with_fields(ledger)
    if fields != source_review.SOURCE_REVIEW_FIELDS:
        print(f"{ledger} has unexpected fields:", file=sys.stderr)
        print("\t".join(fields), file=sys.stderr)
        return 1
    errors = source_review.validate_review_rows(root, rows)
    if errors:
        print("Reference-marker source-image review validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Reference-marker source-image reviews are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
