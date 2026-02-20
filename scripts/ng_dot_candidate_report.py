#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

TIB_RE = re.compile(r"[\u0F00-\u0FFF]")
TIB_SPAN_RE = re.compile(r"[\u0F00-\u0FFF]+(?:[\u0F00-\u0FFF་།༔\s]*[\u0F00-\u0FFF]+)?")
LATIN_TOKEN_RE = re.compile(
    r"[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßı'’]+(?:-[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßı'’]+)*"
)
ROMAN_CUE_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź'’]|(?:kh|tsh|ts|ph|th|dh|bh|dz|rdz)", re.IGNORECASE)
TOKEN_VALID_RE = re.compile(r"^[a-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź'’\-]+$")
NVAR_RE = re.compile(r"[nñṅ]")
PROTECTED_NY = {"sñan", "ñan", "ñon", "gñan"}


@dataclass
class TokenStats:
    count: int = 0
    tib_nga_lines: int = 0
    tib_nya_lines: int = 0
    n_before_ie_count: int = 0
    n_not_before_ie_count: int = 0
    example: str = ""


def normalize_line(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("\f", " ")
    return re.sub(r"\s+", " ", s.strip())


def is_tibetan_translit_line(line: str) -> bool:
    return bool(TIB_RE.search(line) and ROMAN_CUE_RE.search(line))


def iter_translit_windows(line: str):
    # Focus on romanization immediately after Tibetan script spans.
    # This avoids German prose/citation zones on the same physical line.
    for m in TIB_SPAN_RE.finditer(line):
        start = m.end()
        rest = line[start : start + 120]
        if not rest:
            continue
        # Stop at likely prose/citation boundaries.
        cut = len(rest)
        for delim in ['"', "“", "”", ";", "(", ")", "[", "]"]:
            i = rest.find(delim)
            if i != -1:
                cut = min(cut, i)
        window = rest[:cut].strip()
        if window:
            yield window


def has_n_variant_context(tok: str) -> bool:
    return bool(NVAR_RE.search(tok.lower()))


def canon_key(tok: str) -> str:
    # Collapse n/ñ/ṅ so variants land in one group.
    t = unicodedata.normalize("NFC", tok).lower()
    t = t.replace("ñ", "n").replace("ṅ", "n")
    t = t.replace("’", "'")
    return t


def n_pos_counts(tok: str) -> tuple[int, int]:
    t = tok.lower().replace("’", "'")
    b_ie = 0
    not_ie = 0
    for i, ch in enumerate(t):
        if ch not in {"n", "ñ", "ṅ"}:
            continue
        nxt = t[i + 1] if i + 1 < len(t) else ""
        if nxt in {"i", "e", "ī", "ē"}:
            b_ie += 1
        else:
            not_ie += 1
    return b_ie, not_ie


def token_weighted_score(tok: str, st: TokenStats) -> float:
    t = tok.lower()
    score = float(st.count)
    has_nga = "ṅ" in t
    has_nya = "ñ" in t
    has_plain_n = "n" in t

    # Tibetan-line evidence rewards expected characters.
    if has_nga:
        score += 0.75 * st.tib_nga_lines
    if has_nya:
        score += 0.75 * st.tib_nya_lines
    if has_plain_n:
        score -= 0.20 * (st.tib_nga_lines + st.tib_nya_lines)

    # User-approved heuristic: ñ before i/e; otherwise prefer dotted n.
    if has_nya:
        score += 0.6 * st.n_before_ie_count
        score -= 0.6 * st.n_not_before_ie_count
    if has_nga:
        score += 0.6 * st.n_not_before_ie_count
        score -= 0.3 * st.n_before_ie_count
    if has_plain_n:
        score -= 0.25 * st.n_not_before_ie_count

    return score


def risk_label(src: str, dst: str, src_st: TokenStats, dst_st: TokenStats) -> str:
    src_has_plain = "n" in src.lower()
    dst_has_diac = ("ṅ" in dst.lower()) or ("ñ" in dst.lower())
    evidence = src_st.tib_nga_lines + src_st.tib_nya_lines + dst_st.tib_nga_lines + dst_st.tib_nya_lines
    if dst_has_diac and src_has_plain and evidence >= 5:
        return "medium"
    if dst_has_diac and evidence >= 8:
        return "low"
    return "review"


def main() -> None:
    ap = argparse.ArgumentParser(description="Build safe-review candidates for n/ñ/ṅ normalization in Tibetan transliteration.")
    ap.add_argument("inputs", nargs="+", help="Input merged OCR text files")
    ap.add_argument("--out", required=True, help="Output TSV path")
    ap.add_argument("--min-group-total", type=int, default=3)
    ap.add_argument("--mode", choices=["general", "n_to_dot_only"], default="general")
    ap.add_argument("--min-nga-evidence", type=int, default=3)
    args = ap.parse_args()

    groups: dict[str, Counter[str]] = defaultdict(Counter)
    stats: dict[tuple[str, str], TokenStats] = defaultdict(TokenStats)

    for p in [Path(x) for x in args.inputs]:
        text = p.read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            line = normalize_line(raw)
            if not line or not is_tibetan_translit_line(line):
                continue
            line_has_nga = "ང" in line
            line_has_nya = "ཉ" in line
            for window in iter_translit_windows(line):
                for m in LATIN_TOKEN_RE.finditer(window):
                    tok = m.group(0)
                    tok_l = tok.lower().replace("’", "'")
                    if len(tok_l) < 3 or not TOKEN_VALID_RE.fullmatch(tok_l):
                        continue
                    if tok_l in PROTECTED_NY:
                        continue
                    if not has_n_variant_context(tok_l):
                        continue
                    key = canon_key(tok_l)
                    if len(key) < 3:
                        continue
                    groups[key][tok_l] += 1
                    st = stats[(key, tok_l)]
                    st.count += 1
                    if line_has_nga:
                        st.tib_nga_lines += 1
                    if line_has_nya:
                        st.tib_nya_lines += 1
                    b_ie, not_ie = n_pos_counts(tok_l)
                    st.n_before_ie_count += b_ie
                    st.n_not_before_ie_count += not_ie
                    if not st.example:
                        st.example = line

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "canon_key",
                "from_token",
                "to_token",
                "from_count",
                "to_count",
                "group_total",
                "from_weighted_score",
                "to_weighted_score",
                "from_tib_nga_lines",
                "from_tib_nya_lines",
                "from_n_before_ie_count",
                "from_n_not_before_ie_count",
                "risk",
                "from_example",
                "to_example",
            ]
        )
        for key, c in sorted(groups.items()):
            total = sum(c.values())
            if total < args.min_group_total or len(c) < 2:
                continue
            if args.mode == "general":
                ranked = sorted(
                    c.keys(),
                    key=lambda tok: (token_weighted_score(tok, stats[(key, tok)]), stats[(key, tok)].count),
                    reverse=True,
                )
                best = ranked[0]
                best_st = stats[(key, best)]
                for cand in ranked[1:]:
                    cand_st = stats[(key, cand)]
                    if token_weighted_score(best, best_st) <= token_weighted_score(cand, cand_st):
                        continue
                    w.writerow(
                        [
                            key,
                            cand,
                            best,
                            cand_st.count,
                            best_st.count,
                            total,
                            f"{token_weighted_score(cand, cand_st):.2f}",
                            f"{token_weighted_score(best, best_st):.2f}",
                            cand_st.tib_nga_lines,
                            cand_st.tib_nya_lines,
                            cand_st.n_before_ie_count,
                            cand_st.n_not_before_ie_count,
                            risk_label(cand, best, cand_st, best_st),
                            cand_st.example,
                            best_st.example,
                        ]
                    )
            else:
                dotted = [t for t in c if "ṅ" in t and "ñ" not in t]
                plain = [t for t in c if "n" in t and "ṅ" not in t and "ñ" not in t]
                if not dotted or not plain:
                    continue
                target = max(
                    dotted,
                    key=lambda tok: (token_weighted_score(tok, stats[(key, tok)]), stats[(key, tok)].count),
                )
                target_st = stats[(key, target)]
                if target_st.tib_nga_lines < args.min_nga_evidence:
                    continue
                for cand in plain:
                    cand_st = stats[(key, cand)]
                    if cand in PROTECTED_NY or target in PROTECTED_NY:
                        continue
                    if cand_st.count < 2 and target_st.count < 2:
                        continue
                    if cand_st.n_before_ie_count > cand_st.n_not_before_ie_count:
                        continue
                    w.writerow(
                        [
                            key,
                            cand,
                            target,
                            cand_st.count,
                            target_st.count,
                            total,
                            f"{token_weighted_score(cand, cand_st):.2f}",
                            f"{token_weighted_score(target, target_st):.2f}",
                            cand_st.tib_nga_lines,
                            cand_st.tib_nya_lines,
                            cand_st.n_before_ie_count,
                            cand_st.n_not_before_ie_count,
                            risk_label(cand, target, cand_st, target_st),
                            cand_st.example,
                            target_st.example,
                        ]
                    )

    print(out)


if __name__ == "__main__":
    main()
