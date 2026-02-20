#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

SAMPLE_PER_VOLUME = 20

N_DOT_RE = re.compile(
    r"\b("
    r"gan|gaṅ|dan|daṅ|dban|dbaṅ|bzan|bzaṅ|rkan|rkaṅ|snan|snaṅ|glan|glaṅ|tshan|tshaṅ"
    r"|[a-zA-Z'’\-]*ñ[a-zA-Z'’\-]*"
    r")\b"
)
SANSKRIT_CUE_RE = re.compile(
    r"\b(skt\.|abhidharma|vinaya|sutra|sūtra|tantra|kārik|prajñ|mahā|dharma|bodhisattva)\b",
    re.IGNORECASE,
)
SANSKRIT_DIAC_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂṀŹź]")
SANSKRIT_TOKEN_CUE_RE = re.compile(
    r"\b([a-z]{3,}(?:sutra|sūtra|tantra|kārika|kārikā|dharma|yāna|pāramitā))\b",
    re.IGNORECASE,
)
UMLAUT_RE = re.compile(r"[äöüÄÖÜ]")
DIGIT_GARBAGE_RE = re.compile(r"(\d{3,}|[0-9][%/:)\(]{1,}|[%/:)\(]{2,}[0-9])")
TOKEN_RE = re.compile(r"\S+")
TIBETAN_RE = re.compile(r"[\u0F00-\u0FFF]")
ROMANIZATION_CUE_RE = re.compile(
    r"\b(?:[bdgmkprstnlyh]?[rly]?[kgcjtdnpbmszh'’][aeiouāīūṛṝḷḹṅñṭḍṇśṣḥṃṁ]{1,}|"
    r"daṅ|gaṅ|dbaṅ|mñam|phyin|tshig|chos|rtog|bdag|gnam|mtsho|theg|dge|’dun|'dun)\b",
    re.IGNORECASE,
)
# Typical bibliography/citation signals; these should be excluded from digit-garbage OCR flags.
CITATION_LINE_RE = re.compile(
    r"\b(?:ed\.|pp\.|vol\.|no\.|nr\.|cf\.|see|vgl\.|hrsg\.|isbn|"
    r"[12][0-9]{3}|[A-Z][A-Za-z]{1,6}\s*\d+[ab]?\d*)\b",
    re.IGNORECASE,
)
PAREN_RE = re.compile(r"\([^)]{0,120}\)")
REF_FRAGMENT_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z]{0,8}\d*[a-z]?|[A-Z]{1,5})\s+\d+[a-z]?(?:,\d+|[ab]\d+)?\b"
)
GARBAGE_TOKEN_RE = re.compile(r"^(?:\d{3,}|(?=.*\d)[0-9%/:)\(]{3,}|[7/%:]{3,})$")


def stratified_pages(total_pages: int, count: int) -> list[int]:
    if total_pages <= 0:
        return []
    if count >= total_pages:
        return list(range(1, total_pages + 1))
    pages = []
    for i in range(count):
        pos = 1 + round(i * (total_pages - 1) / (count - 1))
        pages.append(pos)
    # Preserve order while removing duplicates.
    out = []
    seen = set()
    for p in pages:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def parse_abs_offset(name: str) -> int | None:
    m = re.search(r"_(\d+)-(\d+)_", name)
    if not m:
        return None
    return int(m.group(1)) - 1


def write_selected_pages(
    text: str, pages: list[int], out_txt: Path, volume_label: str, abs_offset: int | None
) -> None:
    chunks = text.split("\f")
    with out_txt.open("w", encoding="utf-8") as f:
        for p in pages:
            if p < 1 or p > len(chunks):
                continue
            abs_page = (abs_offset + p) if abs_offset is not None else p
            f.write(f"===== {volume_label} page_rel={p} page_abs={abs_page} =====\n")
            f.write(chunks[p - 1].rstrip() + "\n\n")


def token_garbage_ratio(tok: str) -> float:
    if not tok:
        return 0.0
    bad = sum(1 for c in tok if c.isdigit() or c in "%/:)()[]{}")
    return bad / len(tok)


def strip_citation_like_spans(s: str) -> str:
    """Remove common citation fragments so digit-garbage checks focus on entry text."""
    out = PAREN_RE.sub(" ", s)
    out = REF_FRAGMENT_RE.sub(" ", out)
    return out


def collect_candidates(
    text: str, pages: list[int], volume_label: str, abs_offset: int | None
) -> tuple[list[list[str]], list[list[str]], list[list[str]], list[list[str]]]:
    chunks = text.split("\f")
    n_dot_rows: list[list[str]] = []
    sanskrit_rows: list[list[str]] = []
    garbage_rows: list[list[str]] = []
    garbage_high_rows: list[list[str]] = []
    for p in pages:
        if p < 1 or p > len(chunks):
            continue
        abs_page = (abs_offset + p) if abs_offset is not None else p
        page = chunks[p - 1]
        for ln, line in enumerate(page.splitlines(), start=1):
            s = line.strip()
            if not s:
                continue
            if N_DOT_RE.search(s):
                n_dot_rows.append([volume_label, str(p), str(abs_page), str(ln), s, "n_dot_focus"])
            lc = s.lower()
            if UMLAUT_RE.search(s) and (
                SANSKRIT_CUE_RE.search(lc)
                or SANSKRIT_DIAC_RE.search(s)
                or SANSKRIT_TOKEN_CUE_RE.search(lc)
            ):
                sanskrit_rows.append(
                    [volume_label, str(p), str(abs_page), str(ln), s, "sanskrit_umlaut_candidate"]
                )
            s_clean = strip_citation_like_spans(s)
            has_tibetan = bool(TIBETAN_RE.search(s))
            has_romanish = bool(ROMANIZATION_CUE_RE.search(s_clean))
            looks_citation = bool(CITATION_LINE_RE.search(s)) and not has_tibetan
            context_ok = (has_tibetan or has_romanish) and not looks_citation

            high_risk = False
            for tok in TOKEN_RE.findall(s_clean):
                if GARBAGE_TOKEN_RE.match(tok):
                    high_risk = True
                    break
            if (DIGIT_GARBAGE_RE.search(s_clean) or high_risk) and context_ok:
                garbage_rows.append(
                    [volume_label, str(p), str(abs_page), str(ln), s, "digit_pattern_romanization_context"]
                )
                if high_risk and has_romanish:
                    garbage_high_rows.append(
                        [volume_label, str(p), str(abs_page), str(ln), s, "digit_pattern_high_risk_romanization"]
                    )
                continue
            for tok in TOKEN_RE.findall(s_clean):
                if len(tok) >= 4 and token_garbage_ratio(tok) >= 0.5:
                    if not context_ok:
                        break
                    garbage_rows.append(
                        [
                            volume_label,
                            str(p),
                            str(abs_page),
                            str(ln),
                            s,
                            f"symbol_ratio_romanization_context:{tok}",
                        ]
                    )
                    if high_risk and has_romanish:
                        garbage_high_rows.append(
                            [
                                volume_label,
                                str(p),
                                str(abs_page),
                                str(ln),
                                s,
                                f"symbol_ratio_high_risk_romanization:{tok}",
                            ]
                        )
                    break
    return n_dot_rows, sanskrit_rows, garbage_rows, garbage_high_rows


def write_tsv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["volume", "page_rel", "page_abs", "line_no", "line_text", "reason"])
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a 40-page QA packet for v6 outputs.")
    ap.add_argument("--vol1", required=True, help="Volume 1 merged text file (form-feed separated pages)")
    ap.add_argument("--vol2", required=True, help="Volume 2 merged text file (form-feed separated pages)")
    ap.add_argument("--outdir", required=True, help="Output folder for packet")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    all_meta_rows: list[list[str]] = []
    all_n_dot: list[list[str]] = []
    all_sanskrit: list[list[str]] = []
    all_garbage: list[list[str]] = []
    all_garbage_high: list[list[str]] = []

    inputs = [("v1", Path(args.vol1)), ("v2", Path(args.vol2))]
    for label, p in inputs:
        text = p.read_text(encoding="utf-8", errors="replace")
        total_pages = text.count("\f") + 1
        pages = stratified_pages(total_pages, SAMPLE_PER_VOLUME)
        abs_offset = parse_abs_offset(p.name)
        for pr in pages:
            abs_page = (abs_offset + pr) if abs_offset is not None else pr
            all_meta_rows.append([label, str(pr), str(abs_page), p.name])

        write_selected_pages(
            text, pages, outdir / f"{label}_selected_20pages.txt", label, abs_offset
        )
        n_dot_rows, sanskrit_rows, garbage_rows, garbage_high_rows = collect_candidates(
            text, pages, label, abs_offset
        )
        all_n_dot.extend(n_dot_rows)
        all_sanskrit.extend(sanskrit_rows)
        all_garbage.extend(garbage_rows)
        all_garbage_high.extend(garbage_high_rows)

    with (outdir / "selected_pages.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["volume", "page_rel", "page_abs", "source_file"])
        w.writerows(all_meta_rows)

    write_tsv(outdir / "n_dot_candidates.tsv", all_n_dot)
    write_tsv(outdir / "sanskrit_umlaut_candidates.tsv", all_sanskrit)
    write_tsv(outdir / "digit_symbol_garbage_candidates.tsv", all_garbage)
    write_tsv(outdir / "digit_symbol_garbage_highrisk.tsv", all_garbage_high)
    write_tsv(outdir / "digit_symbol_romanization_highrisk.tsv", all_garbage_high)

    print(f"outdir={outdir}")
    print(f"selected_pages={len(all_meta_rows)}")
    print(f"n_dot_candidates={len(all_n_dot)}")
    print(f"sanskrit_umlaut_candidates={len(all_sanskrit)}")
    print(f"digit_symbol_candidates={len(all_garbage)}")
    print(f"digit_symbol_highrisk={len(all_garbage_high)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
