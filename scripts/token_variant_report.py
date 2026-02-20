#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

TIB_RE = re.compile(r"[\u0F00-\u0FFF]")
LATIN_TOKEN_RE = re.compile(r"[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßışŞņŅãÃ]+(?:-[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßışŞņŅãÃ]+)*")
SKT_MARKER_RE = re.compile(r"\b(?:skt|skr|sanskrit|iast)\.?\b", re.IGNORECASE)
BIB_MARKER_RE = re.compile(r"\b(?:ed\.?:|hrsg\.|pp\.|vol\.|no\.|nr\.|ibid\.|trans\.|tr\.)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:1[89]\d{2}|20\d{2})\b")
ROMAN_CUE_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź'’]|(?:kh|tsh|ts|ph|th|dh|bh|dz|rdz)", re.IGNORECASE)
SYMBOL_OR_DIGIT_RE = re.compile(r"[\d€£¬¥¢§¤@#%^&*_=/\\|~]")
IAST_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁźĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂṀŹ]")
GERMAN_RE = re.compile(r"[äöüÄÖÜß]")
TITLE_NAME_RE = re.compile(r"^[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+(?:-[A-ZÄÖÜ][A-Za-zÄÖÜäöüß]+)*$")
GERMAN_STOPWORDS = {
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "und",
    "oder",
    "ein",
    "eine",
    "einer",
    "einem",
    "ich",
    "du",
    "er",
    "sie",
    "wir",
    "ihr",
    "wie",
    "mit",
    "von",
    "für",
    "auf",
    "ist",
    "sind",
    "war",
    "hat",
    "haben",
    "nicht",
    "auch",
    "zu",
    "im",
    "in",
    "am",
    "an",
}

CONFUSABLE_FROM = {
    "$": "ś",
    "ı": "i",
    "I": "l",
    "ş": "ṣ",
    "Ş": "Ṣ",
    "ņ": "ṇ",
    "Ņ": "Ṇ",
    "ã": "ā",
    "Ã": "Ā",
    "ù": "ṅ",
    "ñ": "ṅ",
    "ń": "ṅ",
    "ä": "ā",
    "Ä": "Ā",
    "ü": "ū",
    "Ü": "Ū",
}

CANON_MAP = str.maketrans(
    {
        "ā": "a",
        "Ā": "a",
        "ī": "i",
        "Ī": "i",
        "ū": "u",
        "Ū": "u",
        "ṛ": "r",
        "Ṛ": "r",
        "ṝ": "r",
        "Ṝ": "r",
        "ḷ": "l",
        "Ḷ": "l",
        "ḹ": "l",
        "Ḹ": "l",
        "ṅ": "n",
        "Ṅ": "n",
        "ñ": "n",
        "Ñ": "n",
        "ṭ": "t",
        "Ṭ": "t",
        "ḍ": "d",
        "Ḍ": "d",
        "ṇ": "n",
        "Ṇ": "n",
        "ś": "s",
        "Ś": "s",
        "ṣ": "s",
        "Ṣ": "s",
        "ḥ": "h",
        "Ḥ": "h",
        "ṃ": "m",
        "Ṃ": "m",
        "ṁ": "m",
        "Ṁ": "m",
        "ź": "z",
        "Ź": "z",
        "ä": "a",
        "Ä": "a",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
        "ı": "i",
        "ş": "s",
        "Ş": "s",
        "ņ": "n",
        "Ņ": "n",
        "ã": "a",
        "Ã": "a",
    }
)


def normalize_line(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\f", " ")
    return re.sub(r"\s+", " ", s.strip())


def line_category(s: str) -> str:
    has_tib = bool(TIB_RE.search(s))
    has_roman_cues = bool(ROMAN_CUE_RE.search(s))
    bib = bool(BIB_MARKER_RE.search(s) or len(YEAR_RE.findall(s)) >= 2)
    if bib:
        return "names_citations"
    if has_tib and has_roman_cues:
        return "tibetan_translit"
    if SKT_MARKER_RE.search(s):
        return "tibetan_translit"
    return "german_or_other"


def token_category(line: str, tok: str, start: int, end: int, line_cat: str) -> str:
    # Bibliographic context dominates for citation/name cleanup.
    if line_cat == "names_citations":
        return "names_citations"

    window_l = max(0, start - 24)
    window_r = min(len(line), end + 24)
    window = line[window_l:window_r]
    near_tibetan = bool(TIB_RE.search(window))
    tok_has_roman = bool(ROMAN_CUE_RE.search(tok))
    tok_has_iast = bool(IAST_RE.search(tok))
    tok_is_title_name = bool(TITLE_NAME_RE.fullmatch(tok))
    tok_l = tok.lower()
    maybe_translit_shape = bool(re.fullmatch(r"[a-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź'’\-]+", tok_l))
    has_cluster = bool(re.search(r"(kh|tsh|ts|ph|th|dh|bh|dz|rdz|ng|ny)", tok_l))

    # Transliteration bucket: local Tibetan neighborhood plus romanization cues.
    if near_tibetan and tok_l in GERMAN_STOPWORDS:
        return "german_or_other"
    if near_tibetan and (tok_has_roman or tok_has_iast):
        return "tibetan_translit"
    if near_tibetan and maybe_translit_shape and (has_cluster or "'" in tok_l or "’" in tok_l):
        return "tibetan_translit"

    # Name-like tokens outside dictionary transliteration are better treated as citation/name.
    if tok_is_title_name and not GERMAN_RE.search(tok):
        return "names_citations"

    return "german_or_other"


def canon_key(tok: str) -> str:
    t = unicodedata.normalize("NFC", tok)
    t = "".join(CONFUSABLE_FROM.get(ch, ch) for ch in t)
    t = t.translate(CANON_MAP).lower()
    t = t.replace("'", "").replace("’", "").replace("-", "")
    return t


def token_quality_score(tok: str, category: str) -> int:
    score = 0
    if SYMBOL_OR_DIGIT_RE.search(tok):
        score -= 20
    if "ı" in tok:
        score -= 12
    if "$" in tok:
        score -= 15
    if "ù" in tok or "¬" in tok:
        score -= 12
    if category == "tibetan_translit":
        score += 2 * len(re.findall(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]", tok))
        if re.fullmatch(r"[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź'’\-]+", tok):
            score += 6
        if re.search(r"[äöüÄÖÜ]", tok):
            score -= 6
    elif category == "names_citations":
        if re.match(r"^[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?$", tok):
            score += 5
        if re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]", tok):
            score += 1
    else:
        if re.search(r"[äöüÄÖÜß]", tok):
            score += 3
        if re.search(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]", tok):
            score -= 1
    return score


def conservative_pair_allowed(src: str, dst: str, category: str) -> bool:
    # Only allow proposals driven by known OCR confusions.
    if src == dst:
        return False
    if len(src) < 3 or len(dst) < 3:
        return False
    a = src
    b = dst
    # permit case-only differences for names
    if category == "names_citations" and a.lower() == b.lower():
        return True

    def simplify(x: str) -> str:
        return "".join(CONFUSABLE_FROM.get(ch, ch) for ch in x)

    sa = simplify(a)
    sb = simplify(b)
    if sa == sb:
        return True
    if canon_key(a) != canon_key(b):
        return False
    # Keep this strict: reject if there are too many distinct char edits.
    diffs = sum(1 for i, ch in enumerate(sa[: min(len(sa), len(sb))]) if ch != sb[i]) + abs(len(sa) - len(sb))
    return diffs <= 2


def main() -> None:
    ap = argparse.ArgumentParser(description="Find high-confidence OCR variant groups and conservative rewrite candidates.")
    ap.add_argument("inputs", nargs="+", help="Merged text files.")
    ap.add_argument("--outdir", required=True, help="Output directory.")
    ap.add_argument("--min-group-total", type=int, default=5)
    ap.add_argument("--min-winner-share", type=float, default=0.72)
    ap.add_argument("--min-winner-gap", type=float, default=0.20)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    groups: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    examples: dict[tuple[str, str, str], str] = {}

    for p in [Path(x) for x in args.inputs]:
        text = p.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = normalize_line(raw_line)
            if not line:
                continue
            line_cat = line_category(line)
            for m in LATIN_TOKEN_RE.finditer(line):
                tok = m.group(0)
                if len(tok) < 3:
                    continue
                cat = token_category(line, tok, m.start(), m.end(), line_cat)
                key = canon_key(tok)
                if len(key) < 3:
                    continue
                gk = (cat, key)
                groups[gk][tok] += 1
                exk = (cat, key, tok)
                if exk not in examples:
                    examples[exk] = line

    variants_path = outdir / "variant_groups.tsv"
    rewrites_path = outdir / "conservative_rewrite_candidates.tsv"
    review_path = outdir / "manual_review_candidates.tsv"

    with variants_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "category",
                "canon_key",
                "token",
                "count",
                "group_total",
                "share",
                "quality_score",
                "example",
            ]
        )
        for (cat, key), c in sorted(groups.items()):
            total = sum(c.values())
            if total < args.min_group_total or len(c) < 2:
                continue
            for tok, cnt in c.most_common():
                w.writerow(
                    [
                        cat,
                        key,
                        tok,
                        cnt,
                        total,
                        f"{cnt/total:.4f}",
                        token_quality_score(tok, cat),
                        examples.get((cat, key, tok), ""),
                    ]
                )

    with rewrites_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "category",
                "canon_key",
                "from_token",
                "to_token",
                "from_count",
                "to_count",
                "winner_share",
                "winner_gap",
                "confidence",
            ]
        )
        for (cat, key), c in sorted(groups.items()):
            total = sum(c.values())
            if total < args.min_group_total or len(c) < 2:
                continue
            ranked = sorted(
                c.items(),
                key=lambda kv: (kv[1], token_quality_score(kv[0], cat)),
                reverse=True,
            )
            winner, wcnt = ranked[0]
            second_cnt = ranked[1][1] if len(ranked) > 1 else 0
            share = wcnt / total
            gap = (wcnt - second_cnt) / total if total else 0.0
            if share < args.min_winner_share or gap < args.min_winner_gap:
                continue
            for loser, lcnt in ranked[1:]:
                if loser == winner:
                    continue
                if not conservative_pair_allowed(loser, winner, cat):
                    continue
                conf = min(0.99, share + gap / 2.0)
                w.writerow(
                    [
                        cat,
                        key,
                        loser,
                        winner,
                        lcnt,
                        wcnt,
                        f"{share:.4f}",
                        f"{gap:.4f}",
                        f"{conf:.4f}",
                    ]
                )

    with review_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(
            [
                "category",
                "canon_key",
                "candidate_token",
                "suggested_best_token",
                "candidate_count",
                "best_count",
                "group_total",
                "best_share",
                "quality_delta",
                "risk",
                "example",
            ]
        )
        for (cat, key), c in sorted(groups.items()):
            total = sum(c.values())
            if total < args.min_group_total or len(c) < 2:
                continue
            ranked = sorted(
                c.items(),
                key=lambda kv: (kv[1], token_quality_score(kv[0], cat)),
                reverse=True,
            )
            best, bcnt = ranked[0]
            bshare = bcnt / total if total else 0.0
            for cand, ccnt in ranked[1:]:
                if cand == best:
                    continue
                cq = token_quality_score(cand, cat)
                bq = token_quality_score(best, cat)
                qdelta = bq - cq
                conservative = conservative_pair_allowed(cand, best, cat)
                if conservative and bshare >= args.min_winner_share:
                    risk = "low"
                elif conservative:
                    risk = "medium"
                else:
                    risk = "high"
                w.writerow(
                    [
                        cat,
                        key,
                        cand,
                        best,
                        ccnt,
                        bcnt,
                        total,
                        f"{bshare:.4f}",
                        qdelta,
                        risk,
                        examples.get((cat, key, cand), ""),
                    ]
                )

    print(f"variant_groups={variants_path}")
    print(f"rewrite_candidates={rewrites_path}")
    print(f"manual_review={review_path}")


if __name__ == "__main__":
    main()
