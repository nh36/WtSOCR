#!/usr/bin/env python3
"""Import accepted source-image reference-marker reviews into an exact packet."""

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
    parser.add_argument("--write-packet", type=Path, required=True)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--root", type=Path, default=repo_root())
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--max-per-volume", type=int, default=20)
    args = parser.parse_args()

    root = args.root.resolve()
    ledger = args.ledger if args.ledger.is_absolute() else root / args.ledger
    fields, rows = batch.read_tsv_with_fields(ledger)
    if fields != source_review.SOURCE_REVIEW_FIELDS:
        print(f"{ledger} has unexpected fields", file=sys.stderr)
        return 1
    batch_id = args.batch_id or source_review.utc_batch_id("reference_marker_source_apply")
    packet_rows = source_review.packet_rows_from_accepted_reviews(
        root,
        rows,
        batch_id=batch_id,
        limit=args.limit,
        max_per_volume=args.max_per_volume,
    )
    batch.validate_packet_rows(
        root,
        packet_rows,
        override_path=root / "data" / "reviewed_tibetan_exact_overrides.tsv",
        expected_reason=source_review.REFERENCE_MARKER_REASON,
        min_score=100,
    )
    batch.write_packet(args.write_packet, packet_rows)
    print(f"source_review_accepted_rows={len(packet_rows)}")
    print(f"packet_path={args.write_packet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
