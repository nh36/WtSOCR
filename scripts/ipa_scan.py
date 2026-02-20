#!/usr/bin/env python3
import argparse
import re
import sys


IPA_PATTERN = re.compile(r"[\u0250-\u02AF\u1D00-\u1D7F\u1D80-\u1DBF\u2C60-\u2C7F]")


def scan_file(path: str, max_lines: int) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except OSError as e:
        print(f"[ipa_scan] ERROR: cannot read {path}: {e}", file=sys.stderr)
        return 1

    matches = IPA_PATTERN.findall(text)
    line_hits = []
    for i, line in enumerate(text.splitlines(), start=1):
        if IPA_PATTERN.search(line):
            line_hits.append((i, line))

    print(f"[ipa_scan] {path}")
    print(f"  IPA chars: {len(matches)}")
    print(f"  IPA lines: {len(line_hits)}")
    if line_hits:
        print("  Sample lines:")
        for i, line in line_hits[:max_lines]:
            print(f"    L{i}: {line}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan OCR output for IPA codepoints and print sample lines."
    )
    parser.add_argument("files", nargs="+", help="OCR text files to scan")
    parser.add_argument("--max-lines", type=int, default=5, help="Max sample lines per file")
    args = parser.parse_args()

    rc = 0
    for path in args.files:
        rc |= scan_file(path, args.max_lines)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
