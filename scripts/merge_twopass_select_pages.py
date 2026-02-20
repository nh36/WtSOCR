#!/usr/bin/env python3
"""Merge two OCR pass outputs by page using explicit Pass B page list."""

from __future__ import annotations

import argparse
from pathlib import Path


def read_pages(path: str) -> list[str]:
    return Path(path).read_text(errors="replace").split("\f")


def read_page_set(path: str) -> set[int]:
    s: set[int] = set()
    p = Path(path)
    if not p.exists():
        return s
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        s.add(int(line))
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pass_a")
    ap.add_argument("pass_b")
    ap.add_argument("b_pages", help="File containing 1-based page numbers to take from Pass B")
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    a = read_pages(args.pass_a)
    b = read_pages(args.pass_b)
    n = min(len(a), len(b))
    b_pages = read_page_set(args.b_pages)

    merged: list[str] = []
    log_lines: list[str] = []

    for i in range(1, n + 1):
        src = "B" if i in b_pages else "A"
        merged.append(b[i - 1] if src == "B" else a[i - 1])
        log_lines.append(f"{i},{src}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\f".join(merged))
    Path(args.log).write_text("\n".join(log_lines) + "\n")

    print(f"pages={n}")
    print(f"from_B={sum(1 for i in range(1, n + 1) if i in b_pages)}")
    print(f"from_A={n - sum(1 for i in range(1, n + 1) if i in b_pages)}")
    print(f"out={args.out}")
    print(f"log={args.log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
