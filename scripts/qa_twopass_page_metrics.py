#!/usr/bin/env python3
"""Analyze two OCR passes page-by-page and emit merge guidance.

Input files must use form-feed (\f) as page separators.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

TIB_RE = re.compile(r"[\u0F00-\u0FFF]")


def page_metrics(text: str) -> dict[str, int]:
    lines = text.count("\n") + (1 if text else 0)
    chars = len(text)
    tib = len(TIB_RE.findall(text))
    return {"lines": lines, "chars": chars, "tib": tib}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("pass_a", help="Pass A text file (e.g. psm3 deu+bod)")
    p.add_argument("pass_b", help="Pass B text file (e.g. psm4 deu+bod+Latin)")
    p.add_argument("--csv", required=True, help="Output CSV path")
    p.add_argument("--b-candidates", required=True, help="Output pages where Pass B looks better")
    p.add_argument("--review", required=True, help="Output pages needing manual review")
    p.add_argument("--min-line-ratio", type=float, default=0.85, help="Minimum B/A line ratio to allow B")
    p.add_argument("--min-tib-gain", type=float, default=1.05, help="Minimum B/A Tibetan char multiplier")
    args = p.parse_args()

    a_pages = Path(args.pass_a).read_text(errors="replace").split("\f")
    b_pages = Path(args.pass_b).read_text(errors="replace").split("\f")
    n = min(len(a_pages), len(b_pages))

    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    b_candidates: list[int] = []
    review_pages: list[int] = []

    with Path(args.csv).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "page",
                "a_lines",
                "b_lines",
                "line_ratio_b_over_a",
                "a_chars",
                "b_chars",
                "char_ratio_b_over_a",
                "a_tib",
                "b_tib",
                "tib_ratio_b_over_a",
                "suggestion",
            ]
        )

        for i in range(n):
            am = page_metrics(a_pages[i])
            bm = page_metrics(b_pages[i])
            line_ratio = (bm["lines"] / am["lines"]) if am["lines"] else 1.0
            char_ratio = (bm["chars"] / am["chars"]) if am["chars"] else 1.0
            tib_ratio = (bm["tib"] / am["tib"]) if am["tib"] else (2.0 if bm["tib"] else 1.0)

            # Conservative policy: default to A unless B has more Tibetan and similar layout density.
            suggestion = "use_A"
            if line_ratio >= args.min_line_ratio and tib_ratio >= args.min_tib_gain:
                suggestion = "candidate_use_B"
                b_candidates.append(i + 1)

            # Any large structural divergence should be reviewed.
            if line_ratio < 0.75 or line_ratio > 1.25:
                review_pages.append(i + 1)

            w.writerow(
                [
                    i + 1,
                    am["lines"],
                    bm["lines"],
                    f"{line_ratio:.4f}",
                    am["chars"],
                    bm["chars"],
                    f"{char_ratio:.4f}",
                    am["tib"],
                    bm["tib"],
                    f"{tib_ratio:.4f}",
                    suggestion,
                ]
            )

    Path(args.b_candidates).write_text("\n".join(map(str, b_candidates)) + ("\n" if b_candidates else ""))
    Path(args.review).write_text("\n".join(map(str, review_pages)) + ("\n" if review_pages else ""))

    print(f"pages_compared={n}")
    print(f"candidate_use_B={len(b_candidates)}")
    print(f"manual_review={len(review_pages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
