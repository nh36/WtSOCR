#!/usr/bin/env python3
"""Build a bounded source-image review packet for reference-marker rows."""

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
    parser.add_argument("--investigation-packet", type=Path, required=True)
    parser.add_argument("--review-packet", type=Path, required=True)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--root", type=Path, default=repo_root())
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--max-per-volume", type=int, default=15)
    parser.add_argument("--render-crops", action="store_true")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    root = args.root.resolve()
    batch_id = args.batch_id or source_review.utc_batch_id()
    work_dir = args.work_dir or args.review_packet.parent
    rows = source_review.build_review_rows(
        root,
        batch.read_tsv(args.investigation_packet),
        batch_id=batch_id,
        work_dir=work_dir,
        limit=args.limit,
        max_per_volume=args.max_per_volume,
        render_crops=args.render_crops,
        dpi=args.dpi,
    )
    batch.write_tsv(args.review_packet, rows, source_review.SOURCE_REVIEW_FIELDS)
    print(f"source_review_rows={len(rows)}")
    print(f"source_review_packet_path={args.review_packet}")
    print(f"source_review_rendered_crops={1 if args.render_crops else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
