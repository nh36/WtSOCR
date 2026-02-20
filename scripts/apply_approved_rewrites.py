#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

LATIN_TOKEN_RE = re.compile(r"[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßışŞņŅãÃ]+(?:-[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßışŞņŅãÃ]+)*")
APOSTROPHES = {"'", "’"}
NEXT_SYLLABLE_SKIP = re.compile(r"^[\s/\-–—~\.,;:!?\"“”()\[\]{}]*([A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßışŞņŅãÃ]+)")
GAN_BLOCK_HINTS = ("türk.-mong.", "turk.-mong.", "qayan")
GAN_BLOCK_PATTERNS = (
    re.compile(r"\bna\s+gan\s+s[āa]n\b", re.IGNORECASE),
    re.compile(r"\bca\s+gan\s+\(skt\.", re.IGNORECASE),
)


def load_rewrites(path: Path) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    rewrites: dict[str, str] = {}
    conflicts: list[tuple[str, str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        required = {"from_token", "to_token"}
        if not required.issubset(set(r.fieldnames or [])):
            raise SystemExit(f"{path}: missing required columns {sorted(required)}")
        for row in r:
            src = (row.get("from_token") or "").strip()
            dst = (row.get("to_token") or "").strip()
            if not src or not dst or src == dst:
                continue
            prev = rewrites.get(src)
            if prev is not None and prev != dst:
                conflicts.append((src, prev, dst))
                continue
            rewrites[src] = dst
    return rewrites, conflicts


def apply_text(text: str, rewrites: dict[str, str]) -> tuple[str, Counter[tuple[str, str]]]:
    counts: Counter[tuple[str, str]] = Counter()

    def get_line_bounds(full: str, start: int, end: int) -> tuple[int, int]:
        line_start = full.rfind("\n", 0, start) + 1
        line_end = full.find("\n", end)
        if line_end < 0:
            line_end = len(full)
        return line_start, line_end

    def should_skip_rewrite(tok: str, dst: str, full: str, start: int, end: int) -> bool:
        # Conservative guardrails for known risky pair: gan -> gaṅ.
        if tok != "gan" or dst != "gaṅ":
            return False

        line_start, line_end = get_line_bounds(full, start, end)
        line_text = full[line_start:line_end]
        line_lc = line_text.lower()

        # If Tibetan source line has གན, keep Latin "gan" rather than forcing "gaṅ".
        if "གན" in line_text:
            return True
        if any(h in line_lc for h in GAN_BLOCK_HINTS):
            return True
        if any(p.search(line_text) for p in GAN_BLOCK_PATTERNS):
            return True
        # Very conservative: in skt-reference lines without Tibetan script,
        # "gan" at line-wrap boundaries is ambiguous; leave unchanged.
        if "skt." in line_lc and not re.search(r"[\u0F00-\u0FFF]", line_text):
            return True

        prev_char = full[start - 1] if start > 0 else ""
        next_char = full[end] if end < len(full) else ""
        if prev_char in APOSTROPHES or next_char in APOSTROPHES:
            return True

        tail = full[end : end + 48]
        m = NEXT_SYLLABLE_SKIP.match(tail)
        if m:
            nxt = m.group(1).lower()
            if nxt in {"di", "de", "ti"}:
                return True
        return False

    def repl(m: re.Match[str]) -> str:
        tok = m.group(0)
        dst = rewrites.get(tok)
        if not dst:
            return tok
        if should_skip_rewrite(tok, dst, text, m.start(), m.end()):
            return tok
        counts[(tok, dst)] += 1
        return dst

    out = LATIN_TOKEN_RE.sub(repl, text)
    return out, counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply only explicit approved token rewrite pairs to OCR text.")
    ap.add_argument("--approved", required=True, help="TSV with at least from_token and to_token columns.")
    ap.add_argument("--inputs", nargs="+", required=True, help="Input text files.")
    ap.add_argument("--outdir", required=True, help="Output directory.")
    args = ap.parse_args()

    approved_path = Path(args.approved)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rewrites, conflicts = load_rewrites(approved_path)
    if conflicts:
        conflict_path = outdir / "rewrite_conflicts.tsv"
        with conflict_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["from_token", "to_token_a", "to_token_b"])
            w.writerows(conflicts)
        raise SystemExit(f"Conflicting approved rewrites found. See: {conflict_path}")

    summary_path = outdir / "apply_summary.tsv"
    with summary_path.open("w", encoding="utf-8", newline="") as sf:
        sw = csv.writer(sf, delimiter="\t")
        sw.writerow(["input_file", "output_file", "replacements", "distinct_pairs"])

        global_counts: Counter[tuple[str, str]] = Counter()
        for ip in [Path(x) for x in args.inputs]:
            text = ip.read_text(encoding="utf-8", errors="replace")
            out_text, counts = apply_text(text, rewrites)
            op = outdir / ip.name
            op.write_text(out_text, encoding="utf-8")
            rep = sum(counts.values())
            sw.writerow([str(ip), str(op), rep, len(counts)])
            global_counts.update(counts)

    detail_path = outdir / "apply_replacements_detail.tsv"
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["from_token", "to_token", "count"])
        for (src, dst), c in global_counts.most_common():
            w.writerow([src, dst, c])

    print(f"approved_pairs={len(rewrites)}")
    print(f"summary={summary_path}")
    print(f"details={detail_path}")


if __name__ == "__main__":
    main()
