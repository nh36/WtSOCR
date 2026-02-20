#!/usr/bin/env python3
"""Pilot geometry-anchored two-pass OCR merge.

Workflow per page:
1. Render page to image.
2. Run Pass A in hOCR mode to get line boxes/text.
3. Re-run Pass B only on candidate line crops (psm 7).
4. Merge line text conservatively when B improves diacritics with sane similarity.

Outputs:
- merged sampled pages in form-feed separated text
- per-page summary CSV
- per-line audit CSV
"""

from __future__ import annotations

import argparse
import csv
import difflib
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

TIB_RE = re.compile(r"[\u0F00-\u0FFF]")
DEV_RE = re.compile(r"[\u0900-\u097F]")
LATIN_RE = re.compile(r"[A-Za-z]")
TIB_STRIP_RE = re.compile(r"[\s\u0F0B\u0F0C\u0F0D\u0F0E\u0F0F\u0F11-\u0F14\u0F20-\u0F29]+")
DIACRITIC_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁźĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂṀŹ]")
# LOC-oriented transliteration cues; avoid Wylie-specific clusters like sh/ny/ng/zh.
TRANSLIT_HINT_RE = re.compile(
    r"\b(?:skt|skr)\.?|[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]|(?:kh|tsh|ts|ch|ph|th|dh|bh|rdz|dz)|[a-z]'[a-z]",
    re.IGNORECASE,
)
BBOX_RE = re.compile(r"\bbbox (\d+) (\d+) (\d+) (\d+)\b")
WS_RE = re.compile(r"\s+")
OCR_CONFUSABLE_I_RE = re.compile(r"\bI(?=[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź])")
OCR_SUSPECT_RE = re.compile(r"[$]|\bI(?=[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź])")
PA_APOSTROPHE_RE = re.compile(r"(?<![A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź])pa[’'](?![A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź])")
ROMAN_TAIL_SUSPECT_RE = re.compile(r"[\u0F20-\u0F33£¥¢§¤@#%^&*_=/\\|~]")
TOKEN_TRANSLIT_RE = re.compile(r"^[a-zA-Z'’āīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄüÜşŞņŅãÃ]+$")
TOKEN_DIACRITIC_OR_SKT_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]")
TOKEN_ANY_LATIN_RE = re.compile(r"^[A-Za-z'’āīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜışŞņŅãÃ-]+$")
SKT_CONTEXT_RE = re.compile(r"\b(?:skt|skr|sanskrit)(?:\.)?(?=\s|$|[:;,\)\]\}])", re.IGNORECASE)
EQUALS_TRANSLIT_HINT_RE = re.compile(r"=\s*[A-Za-z'’äÄāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]{2,}")
HEADWORD_SPLIT_RE = re.compile(r"^\s*(?P<prefix>[\u0F00-\u0FFF\s\u0F0B\u0F0C\u0F0D\u0F0E\u0F0F\u0F11-\u0F14\u0F20-\u0F29]+)(?P<tail>.*)$")
TRANSLIT_CLUSTER_RE = re.compile(r"(?:kh|tsh|ts|ch|ph|th|dh|bh|rdz|dz|'" r"|’)", re.IGNORECASE)
N_TILDE_BEFORE_IE_RE = re.compile(r"ñ(?=[iIeEīĪ])")
N_TILDE_BEFORE_S_FINAL_RE = re.compile(r"ñ(?=[sS](?:\s|$|[,\.;:!\?\)\]\}\"“”„'’/\-་།]))")
N_TILDE_ACUTE_N_BEFORE_S_FINAL_RE = re.compile(r"ñń(?=[sS](?:\s|$|[,\.;:!\?\)\]\}\"“”„'’/\-་།]))")
N_TILDE_SYL_FINAL_RE = re.compile(r"ñ(?=(?:\s|$|[,\.;:!\?\)\]\}\"“”„'’/\-་།]))")
N_ACUTE_N_BEFORE_S_FINAL_RE = re.compile(r"ń(?=[sS](?:\s|$|[,\.;:!\?\)\]\}\"“”„'’/\-་།]))")
N_ACUTE_N_SYL_FINAL_RE = re.compile(r"ń(?=(?:\s|$|[,\.;:!\?\)\]\}\"“”„'’/\-་།]))")
N_TILDE_GRAVE_PAIR_RE = re.compile(r"ñù", re.IGNORECASE)
ROMAN_NOISE_TOKEN_RE = re.compile(r"^[0-9:/%.,;+\-]{2,}$")
ROMAN_NOISE_DIGSYM_RE = re.compile(r"^(?=.*\d)(?=.*[^A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜı0-9])[^\s]+$")
STRAY_SYMBOL_DROP_RE = re.compile(r"[€£¬]")
DIACRITIC_BASE_TABLE = str.maketrans(
    {
        "ä": "a",
        "Ä": "A",
        "ā": "a",
        "Ā": "A",
        "ī": "i",
        "Ī": "I",
        "ū": "u",
        "Ū": "U",
        "ṛ": "r",
        "Ṛ": "R",
        "ṝ": "r",
        "Ṝ": "R",
        "ḷ": "l",
        "Ḷ": "L",
        "ḹ": "l",
        "Ḹ": "L",
        "ṅ": "n",
        "Ṅ": "N",
        "ñ": "n",
        "Ñ": "N",
        "ṭ": "t",
        "Ṭ": "T",
        "ḍ": "d",
        "Ḍ": "D",
        "ṇ": "n",
        "Ṇ": "N",
        "ś": "s",
        "Ś": "S",
        "ź": "z",
        "Ź": "Z",
        "ṣ": "s",
        "Ṣ": "S",
        "ḥ": "h",
        "Ḥ": "H",
        "ṃ": "m",
        "Ṃ": "M",
        "ṁ": "m",
        "Ṁ": "M",
        "ş": "s",
        "Ş": "S",
        "ņ": "n",
        "Ņ": "N",
        "ã": "a",
        "Ã": "A",
    }
)
PUNCT_STRIP_RE = re.compile(r"[`~!@#%^&*_=+\[\]{}\\|;:\"“”„'’<>,./?()-]+")
POST_FIX_WORDS = (
    ("Ita", "lta"),
    ("Itar", "ltar"),
    ("Iha", "lha"),
    ("Idan", "ldan"),
    ("gyl", "gyi"),
)
SANSKRIT_HINT_SUBSTRINGS = (
    "sutra",
    "tantra",
    "karika",
    "vinaya",
    "abhidharma",
    "abhidhana",
    "nidana",
    "bhumika",
    "megha",
    "duta",
    "dharma",
    "prajna",
    "vajra",
    "yoga",
    "mantra",
)
WORD_RE = re.compile(r"[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜışŞņŅãÃ]+(?:-[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜışŞņŅãÃ]+)*")
DIGIT_RUN_RE = re.compile(r"\d{3,}")
REPEATED_DIGIT_RE = re.compile(r"(\d)\1{2,}")
ALNUM_MIXED_RE = re.compile(r"(?=.*[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜı])(?=.*\d)[A-Za-z0-9āīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜı]+")
SUSPECT_SYMBOL_RE = re.compile(r"[£¥¢§¤]")
TIB_SYLLABLE_SPLIT_RE = re.compile(r"[\s\u0F0B\u0F0C\u0F0D\u0F0E\u0F0F\u0F11-\u0F14\u0F20-\u0F29]+")
DEHYPH_LINE_END_RE = re.compile(r"([A-Za-z][A-Za-zäöüÄÖÜāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]*)-$")
BIBLIO_MARKER_RE = re.compile(
    r"\b(?:ed\.?:|hrsg\.|pp\.|vol\.|nr\.|no\.|ibid\.|cf\.|trans\.|tr\.)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:1[89]\d{2}|20\d{2})\b")
TRANSLIT_CHAR_RE = re.compile(r"[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁźäÄöÖüÜıışŞņŅãÃ]")
QUOTE_NORMALIZE_MAP = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "’": "'",
        "‘": "'",
        "‚": "'",
        "‛": "'",
    }
)


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.translate(QUOTE_NORMALIZE_MAP)
    s = s.replace("\u0131", "i")
    s = s.replace("\f", " ")
    return WS_RE.sub(" ", s.replace("\n", " ")).strip()


def is_bibliography_line(s: str) -> bool:
    if not s:
        return False
    if not LATIN_RE.search(s):
        return False
    marker_hits = len(BIBLIO_MARKER_RE.findall(s))
    year_hits = len(YEAR_RE.findall(s))
    comma_hits = s.count(",")
    semicolon_hits = s.count(";")
    return (marker_hits >= 1 and year_hits >= 1) or (year_hits >= 2) or (
        marker_hits >= 1 and (comma_hits + semicolon_hits) >= 2
    )


def line_zones(s: str) -> set[str]:
    zones: set[str] = set()
    if not s:
        return zones
    has_tib = bool(TIB_RE.search(s))
    has_latin = bool(LATIN_RE.search(s))
    if has_tib:
        zones.add("tibetan")
    if is_bibliography_line(s):
        zones.add("bibliography")
    if has_tib and translit_tail_after_tibetan(s):
        zones.add("romanization")
    if SKT_CONTEXT_RE.search(s) or EQUALS_TRANSLIT_HINT_RE.search(s):
        zones.add("sanskrit")
    elif has_latin and "bibliography" not in zones:
        if any(token_looks_sanskritic(tok) for tok in WORD_RE.findall(s)):
            zones.add("sanskrit")
    if has_latin and not ({"romanization", "sanskrit"} & zones):
        zones.add("german_prose")
    return zones


def classify_block_context(lines: list[str], idx: int, window: int = 2) -> dict[str, bool]:
    counts = {
        "tibetan": 0,
        "romanization": 0,
        "sanskrit": 0,
        "bibliography": 0,
        "german_prose": 0,
    }
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    for i in range(start, end):
        for z in line_zones(normalize_text(lines[i])):
            if z in counts:
                counts[z] += 1
    span = max(1, end - start)
    bib = counts["bibliography"] >= 2 or (
        counts["bibliography"] >= 1 and counts["german_prose"] >= 1 and counts["tibetan"] == 0
    )
    return {
        "tibetan_block": counts["tibetan"] >= 1,
        "romanization_block": counts["romanization"] >= 1,
        "sanskrit_block": counts["sanskrit"] >= 1,
        "bibliography_block": bib,
        "german_dominant": counts["german_prose"] >= (span // 2),
    }


def sanskrit_marker_ranges(s: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    end_marks = set(";:,.!?)]}»“”\"")

    for m in SKT_CONTEXT_RE.finditer(s):
        i = m.end()
        while i < len(s) and s[i].isspace():
            i += 1
        j = i
        while j < len(s) and s[j] not in end_marks:
            j += 1
        if i < j:
            ranges.append((i, j))

    i = 0
    while i < len(s):
        if s[i] != "=":
            i += 1
            continue
        j = i + 1
        while j < len(s) and s[j].isspace():
            j += 1
        if j >= len(s):
            break
        k = j
        while k < len(s) and not s[k].isspace() and s[k] not in ",;:.)]}\"“”":
            k += 1
        if j < k:
            ranges.append((j, k))
        i = k

    ranges.sort()
    merged: list[tuple[int, int]] = []
    for st, en in ranges:
        if not merged or st > merged[-1][1]:
            merged.append((st, en))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], en))
    return merged


def in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for st, en in ranges:
        if st <= pos < en:
            return True
    return False


def normalize_romanization_segment(s: str, sanskrit_context: bool) -> str:
    out = s
    out = out.replace("$", "ś")
    out = PA_APOSTROPHE_RE.sub("pa'i", out)
    out = N_TILDE_GRAVE_PAIR_RE.sub("ṅ", out)
    for bad, good in POST_FIX_WORDS:
        out = re.sub(rf"\b{re.escape(bad)}\b", good, out)

    protected = "\uE000"
    out = N_TILDE_BEFORE_IE_RE.sub(protected, out)
    out = N_TILDE_ACUTE_N_BEFORE_S_FINAL_RE.sub("ṅ", out)
    out = N_TILDE_BEFORE_S_FINAL_RE.sub("ṅ", out)
    out = N_TILDE_SYL_FINAL_RE.sub("ṅ", out)
    out = N_ACUTE_N_BEFORE_S_FINAL_RE.sub("ṅ", out)
    out = N_ACUTE_N_SYL_FINAL_RE.sub("ṅ", out)
    out = out.replace(protected, "ñ")

    # Sanskrit-style repairs only for transliteration-looking tokens.
    parts: list[str] = []
    pos = 0
    for m in WORD_RE.finditer(out):
        parts.append(out[pos : m.start()])
        tok = m.group(0)
        use_skt = sanskrit_context or token_has_translit_cues(tok) or token_looks_sanskritic(tok)
        fixed = normalize_translit_token_dieresis(tok, use_skt)
        fixed = normalize_sanskrit_token_chars(fixed, use_skt)
        parts.append(fixed)
        pos = m.end()
    parts.append(out[pos:])
    return "".join(parts)


def normalize_latin_spans(s: str, ctx: dict[str, bool]) -> str:
    ranges = sanskrit_marker_ranges(s)
    out_parts: list[str] = []
    pos = 0
    for m in WORD_RE.finditer(s):
        out_parts.append(s[pos : m.start()])
        tok = m.group(0)
        in_skt_span = in_ranges(m.start(), ranges)
        token_sktish = token_looks_sanskritic(tok)
        use_skt = in_skt_span or (
            token_sktish and (ctx["sanskrit_block"] or not ctx["bibliography_block"])
        )
        fixed = tok
        if use_skt:
            fixed = normalize_translit_token_dieresis(fixed, True)
            fixed = normalize_sanskrit_token_chars(fixed, True)
        out_parts.append(fixed)
        pos = m.end()
    out_parts.append(s[pos:])
    return "".join(out_parts)


def split_line_spans(s: str) -> list[tuple[str, str]]:
    prefix, tail = split_tibetan_prefix_tail(s)
    if not prefix:
        return [("latin", s)]
    if not tail:
        return [("tibetan_script", prefix)]
    lead = translit_lead_tokens(tail)
    lead_consumed = len("".join(lead))
    if lead_consumed <= 0:
        return [("tibetan_script", prefix), ("latin", tail)]
    roman = tail[:lead_consumed]
    rest = tail[lead_consumed:]
    spans: list[tuple[str, str]] = [("tibetan_script", prefix), ("romanization", roman)]
    if rest:
        spans.append(("latin", rest))
    return spans


def post_cleanup_contextual(lines: list[str], idx: int, s: str) -> str:
    out = normalize_text(s)
    ctx = classify_block_context(lines, idx)
    has_explicit_confusable = ("$" in out) or PA_APOSTROPHE_RE.search(out) or any(
        re.search(rf"\b{re.escape(bad)}\b", out) for bad, _ in POST_FIX_WORDS
    )
    if not (LATIN_RE.search(out) or has_explicit_confusable):
        return out

    out = STRAY_SYMBOL_DROP_RE.sub("", out)
    spans = split_line_spans(out)
    rebuilt: list[str] = []
    for zone, text in spans:
        if zone == "tibetan_script":
            rebuilt.append(text)
            continue
        if zone == "romanization":
            rebuilt.append(normalize_romanization_segment(text, ctx["sanskrit_block"]))
            continue
        rebuilt.append(normalize_latin_spans(text, ctx))

    out = "".join(rebuilt)
    if split_tibetan_prefix_tail(out)[0]:
        out = drop_roman_tail_noise_after_tibetan(out)
        out = enforce_ng_from_tibetan_prefix(out)
    return normalize_text(out)


def normalize_ocr_confusables(s: str) -> str:
    # Common OCR confusions in romanized Tibetan lines.
    s = s.replace("$", "ś")
    s = OCR_CONFUSABLE_I_RE.sub("l", s)
    s = PA_APOSTROPHE_RE.sub("pa'i", s)
    return s


def base_equivalent_for_merge(s: str) -> str:
    # Compare lines with diacritics and punctuation stripped to detect near-identical OCR variants.
    out = normalize_ocr_confusables(s).translate(DIACRITIC_BASE_TABLE)
    out = PUNCT_STRIP_RE.sub(" ", out)
    return normalize_text(out).casefold()


def tibetan_anchor_for_merge(s: str) -> str:
    chunks = TIB_RE.findall(s)
    if not chunks:
        return ""
    return TIB_STRIP_RE.sub("", "".join(chunks))


def translit_tail_after_tibetan(s: str) -> str:
    m = re.search(r"[\u0F00-\u0FFF][\u0F00-\u0FFF\s\u0F0B\u0F0C\u0F0D\u0F0E\u0F0F\u0F11-\u0F14\u0F20-\u0F29]*", s)
    if not m:
        return ""
    tail = normalize_text(s[m.end() :])
    return tail


def split_tibetan_prefix_tail(s: str) -> tuple[str, str]:
    m = HEADWORD_SPLIT_RE.match(s)
    if not m:
        return "", ""
    prefix = m.group("prefix")
    tail = normalize_text(m.group("tail"))
    if not TIB_RE.search(prefix):
        return "", ""
    return prefix, tail


def roman_tail_quality_score(s: str) -> tuple[int, int, int]:
    tail = translit_tail_after_tibetan(s)
    if not tail:
        return (0, 0, 0)
    letters = len(re.findall(r"[A-Za-zāīūṛṝḷḹṅñṭḍṇśṣḥṃṁź]", tail))
    suspects = len(ROMAN_TAIL_SUSPECT_RE.findall(tail))
    diacritics = len(DIACRITIC_RE.findall(tail))
    return (letters, -suspects, diacritics)


def roman_tail_noise_score(s: str) -> int:
    tail = translit_tail_after_tibetan(s)
    if not tail:
        return 0
    # Conservative: count obvious OCR junk in romanization tails only.
    return len(re.findall(r"[0-9:/%$£¥¢§¤@#^&*_=/\\|~]", tail))


def normalize_translit_token_dieresis(token: str, sanskrit_context: bool) -> str:
    # Conservative: transliteration-looking tokens in Sanskritic context.
    if not sanskrit_context:
        return token
    if not TOKEN_ANY_LATIN_RE.match(token):
        return token
    if all(ch not in token for ch in ("ä", "Ä", "ü", "Ü")):
        return token
    return (
        token.replace("ä", "ā")
        .replace("Ä", "Ā")
        .replace("ü", "ū")
        .replace("Ü", "Ū")
    )


SANSKRIT_CEDILLA_CHAR_MAP = {
    "ş": "ṣ",
    "Ş": "Ṣ",
    "ņ": "ṇ",
    "Ņ": "Ṇ",
    "ã": "ā",
    "Ã": "Ā",
}
SANSKRIT_CEDILLA_MAP = str.maketrans(SANSKRIT_CEDILLA_CHAR_MAP)


def normalize_sanskrit_token_chars(token: str, sanskrit_context: bool) -> str:
    if not sanskrit_context:
        return token
    return token.translate(SANSKRIT_CEDILLA_MAP)


def token_to_ascii_base(token: str) -> str:
    t = normalize_text(token).translate(DIACRITIC_BASE_TABLE).lower()
    t = t.replace("ä", "a").replace("ö", "o").replace("ü", "u")
    t = t.replace("-", "")
    return t


def token_looks_sanskritic(token: str) -> bool:
    if not token:
        return False
    if not TOKEN_ANY_LATIN_RE.match(token):
        return False
    if DIACRITIC_RE.search(token):
        return True
    if re.search(r"[şŞņŅãÃ]", token):
        return True
    base = token_to_ascii_base(token)
    if not base:
        return False
    if any(h in base for h in SANSKRIT_HINT_SUBSTRINGS):
        return True
    if re.search(r"(bh|dh|gh|kh|ph|th|sh|tsh|dz|rdz)", base):
        return True
    return False


def normalize_sanskrit_umlauts_in_text(s: str) -> str:
    # Convert token-by-token and hyphen-segment-by-segment to avoid spilling into German compounds.
    parts: list[str] = []
    pos = 0
    for m in WORD_RE.finditer(s):
        parts.append(s[pos : m.start()])
        token = m.group(0)
        if "-" not in token:
            sanskritic = token_looks_sanskritic(token)
            fixed = normalize_translit_token_dieresis(token, sanskritic)
            fixed = normalize_sanskrit_token_chars(fixed, sanskritic)
            parts.append(fixed)
        else:
            seg_parts: list[str] = []
            for seg in re.split(r"(-)", token):
                if seg == "-" or not seg:
                    seg_parts.append(seg)
                    continue
                sanskritic = token_looks_sanskritic(seg)
                fixed = normalize_translit_token_dieresis(seg, sanskritic)
                fixed = normalize_sanskrit_token_chars(fixed, sanskritic)
                seg_parts.append(fixed)
            parts.append("".join(seg_parts))
        pos = m.end()
    parts.append(s[pos:])
    return "".join(parts)


def token_has_translit_cues(token: str) -> bool:
    if not token:
        return False
    if DIACRITIC_RE.search(token):
        return True
    if TRANSLIT_CLUSTER_RE.search(token):
        return True
    return False


def translit_lead_tokens(tail: str) -> list[str]:
    # Leading token run after Tibetan headword that still looks like transliteration.
    parts = re.split(r"(\s+)", tail)
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.isspace():
            out.append(part)
            continue
        if TOKEN_TRANSLIT_RE.match(part):
            out.append(part)
            continue
        break
    return out


def is_roman_noise_token(tok: str) -> bool:
    if not tok:
        return False
    if TOKEN_TRANSLIT_RE.match(tok):
        return False
    char_count = len(tok)
    if char_count:
        letter_count = len(TRANSLIT_CHAR_RE.findall(tok))
        non_letter_ratio = (char_count - letter_count) / char_count
        if char_count >= 3 and non_letter_ratio > 0.40:
            return True
    if ROMAN_NOISE_TOKEN_RE.match(tok):
        return True
    if REPEATED_DIGIT_RE.search(tok):
        return True
    if ROMAN_NOISE_DIGSYM_RE.match(tok):
        return True
    if SUSPECT_SYMBOL_RE.search(tok) and not LATIN_RE.search(tok):
        return True
    return False


def drop_roman_tail_noise_after_tibetan(line: str) -> str:
    # Remove obvious digit/symbol artefacts from the transliteration slot immediately
    # after Tibetan script, while preserving valid transliteration tokens.
    prefix, tail = split_tibetan_prefix_tail(line)
    if not prefix or not tail:
        return line
    parts = re.split(r"(\s+)", tail)
    out_parts: list[str] = []
    for idx, part in enumerate(parts):
        if not part:
            continue
        if part.isspace():
            out_parts.append(part)
            continue
        if TOKEN_TRANSLIT_RE.match(part):
            out_parts.append(part)
            continue
        if is_roman_noise_token(part):
            continue
        out_parts.append(part)
        out_parts.extend(parts[idx + 1 :])
        break
    if not out_parts:
        out_tail = tail
    else:
        out_tail = "".join(out_parts).strip()
    joiner = "" if prefix.endswith(" ") or not out_tail else " "
    return f"{prefix}{joiner}{out_tail}".rstrip()


def normalize_dieresis_in_skt_spans(s: str) -> str:
    # Apply Sanskrit-only char repair inside spans explicitly marked as Sanskrit.
    marks = list(SKT_CONTEXT_RE.finditer(s))
    if not marks:
        return s
    chars = list(s)
    end_marks = set(";:,.!?)]}»“”\"")
    for m in marks:
        i = m.end()
        # Skip immediate whitespace after marker.
        while i < len(chars) and chars[i].isspace():
            i += 1
        while i < len(chars):
            ch = chars[i]
            if ch in end_marks:
                break
            if ch == "ä":
                chars[i] = "ā"
            elif ch == "Ä":
                chars[i] = "Ā"
            elif ch == "ü":
                chars[i] = "ū"
            elif ch == "Ü":
                chars[i] = "Ū"
            elif ch in SANSKRIT_CEDILLA_CHAR_MAP:
                chars[i] = SANSKRIT_CEDILLA_CHAR_MAP[ch]
            i += 1
    return "".join(chars)


def normalize_dieresis_after_equals_translit(s: str) -> str:
    # In dictionary equivalence patterns ("... = ..."), the immediate RHS is usually transliteration.
    # Normalize ä/Ä there only within the leading transliteration-like token run.
    if "=" not in s:
        return s
    if not (TIB_RE.search(s) or SKT_CONTEXT_RE.search(s) or re.search(r"\bLex\.", s)):
        return s
    chars = list(s)
    i = 0
    n = len(chars)
    while i < n:
        if chars[i] != "=":
            i += 1
            continue
        j = i + 1
        while j < n and chars[j].isspace():
            j += 1
        if j >= n:
            break
        k = j
        while k < n and not chars[k].isspace() and chars[k] not in ",;:.)]}\"“”":
            k += 1
        token = "".join(chars[j:k])
        converted = normalize_translit_token_dieresis(token, bool(token))
        converted = normalize_sanskrit_token_chars(converted, bool(token))
        if converted != token and TOKEN_TRANSLIT_RE.match(token):
            chars[j:k] = list(converted)
        i = k
    return "".join(chars)


def tibetan_syllables(prefix: str) -> list[str]:
    return [x for x in TIB_SYLLABLE_SPLIT_RE.split(prefix) if x]


def enforce_ng_from_tibetan_prefix(line: str) -> str:
    # Align early romanization tokens with Tibetan headword syllables and restore dotted n
    # where the source Tibetan syllable contains NGA (U+0F44).
    prefix, tail = split_tibetan_prefix_tail(line)
    if not prefix or not tail:
        return line
    syls = tibetan_syllables(prefix)
    if not syls:
        return line
    lead = translit_lead_tokens(tail)
    lead_consumed = len("".join(lead))
    if lead_consumed <= 0:
        return line
    lead_text = tail[:lead_consumed]
    tokens = re.split(r"(\s+)", lead_text)
    roman_idx = 0
    out_parts: list[str] = []
    for tok in tokens:
        if not tok or tok.isspace():
            out_parts.append(tok)
            continue
        fixed = tok
        if roman_idx < len(syls) and "ང" in syls[roman_idx]:
            # Project transliteration uses dotted n, not digraph ng.
            fixed = re.sub(r"n(?=s?$)", "ṅ", fixed)
            fixed = re.sub(r"ng(?=s?$)", "ṅ", fixed)
        out_parts.append(fixed)
        roman_idx += 1
    fixed_lead = "".join(out_parts)
    fixed_tail = fixed_lead + tail[lead_consumed:]
    return line[: len(line) - len(tail)] + fixed_tail


def dehyphenate_wrapped_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        cur = lines[i]
        if i + 1 >= len(lines):
            out.append(cur)
            i += 1
            continue
        nxt = lines[i + 1]
        if not cur or not nxt:
            out.append(cur)
            i += 1
            continue
        # Do not touch transliteration-heavy lines.
        if line_is_translit_heavy(cur) or line_is_translit_heavy(nxt):
            out.append(cur)
            i += 1
            continue
        m = DEHYPH_LINE_END_RE.search(cur.rstrip())
        if m and re.match(r"^[a-zäöü]", nxt.lstrip()):
            merged = DEHYPH_LINE_END_RE.sub(r"\1", cur.rstrip()) + nxt.lstrip()
            out.append(merged)
            i += 2
            continue
        out.append(cur)
        i += 1
    return out


def line_is_translit_heavy(s: str) -> bool:
    if TIB_RE.search(s):
        return True
    tokens = [t for t in WORD_RE.findall(s) if t]
    if not tokens:
        return False
    translitish = sum(1 for t in tokens if token_has_translit_cues(t))
    return translitish >= max(2, len(tokens) // 2)


def collect_anomalies(page: int, line_no: int, text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    zones = ",".join(sorted(line_zones(text)))
    for tok in WORD_RE.findall(text):
        if any(ch in tok for ch in ("ä", "Ä", "ü", "Ü")) and token_looks_sanskritic(tok):
            rows.append(
                {
                    "page": page,
                    "line": line_no,
                    "type": "sanskrit_umlaut_candidate",
                    "token": tok,
                    "context": text,
                    "zones": zones,
                }
            )
    for tok in re.findall(r"\S+", text):
        if DIGIT_RUN_RE.search(tok):
            rows.append({"page": page, "line": line_no, "type": "digit_run", "token": tok, "context": text, "zones": zones})
        if REPEATED_DIGIT_RE.search(tok):
            rows.append({"page": page, "line": line_no, "type": "repeated_digit", "token": tok, "context": text, "zones": zones})
        if ALNUM_MIXED_RE.match(tok):
            rows.append({"page": page, "line": line_no, "type": "alnum_mixed", "token": tok, "context": text, "zones": zones})
        if SUSPECT_SYMBOL_RE.search(tok):
            rows.append({"page": page, "line": line_no, "type": "suspect_symbol", "token": tok, "context": text, "zones": zones})
        if "ù" in tok or "Ù" in tok:
            rows.append({"page": page, "line": line_no, "type": "u_grave_marker", "token": tok, "context": text, "zones": zones})
    return rows


def maybe_splice_tibetan_prefix_with_b_tail(a_text: str, b_text: str, min_similarity_tibetan_anchor: float) -> str:
    # If B drops Tibetan script but has a cleaner romanization tail, keep Tibetan prefix from A.
    if not a_text or not b_text:
        return ""
    if TIB_RE.search(b_text):
        return ""
    prefix, a_tail = split_tibetan_prefix_tail(a_text)
    if not prefix or not a_tail:
        return ""
    b_tail = normalize_text(b_text)
    if not b_tail or not LATIN_RE.search(b_tail):
        return ""
    if a_tail:
        length_ratio = len(b_tail) / len(a_tail)
        if length_ratio < 0.55 or length_ratio > 1.8:
            return ""
    sim = difflib.SequenceMatcher(None, base_equivalent_for_merge(a_tail), base_equivalent_for_merge(b_tail)).ratio()
    if sim < min_similarity_tibetan_anchor:
        return ""
    a_sus = len(ROMAN_TAIL_SUSPECT_RE.findall(a_tail))
    b_sus = len(ROMAN_TAIL_SUSPECT_RE.findall(b_tail))
    a_d = len(DIACRITIC_RE.findall(a_tail))
    b_d = len(DIACRITIC_RE.findall(b_tail))
    if not ((a_sus > b_sus) or (b_d > a_d)):
        return ""
    joiner = "" if prefix.endswith(" ") or not b_tail else " "
    return f"{prefix}{joiner}{b_tail}".rstrip()


def post_cleanup_translit_line(s: str) -> str:
    out = normalize_text(s)
    zones = line_zones(out)
    # Restrict to lines that likely need normalization.
    has_explicit_confusable = ("$" in out) or PA_APOSTROPHE_RE.search(out) or any(
        re.search(rf"\b{re.escape(bad)}\b", out) for bad, _ in POST_FIX_WORDS
    )
    if not (
        {"romanization", "sanskrit"} & zones
        or has_explicit_confusable
    ):
        return out
    out = STRAY_SYMBOL_DROP_RE.sub("", out)
    if "romanization" in zones or has_explicit_confusable:
        out = out.replace("$", "ś")
        out = PA_APOSTROPHE_RE.sub("pa'i", out)
        out = N_TILDE_GRAVE_PAIR_RE.sub("ṅ", out)
        for bad, good in POST_FIX_WORDS:
            out = re.sub(rf"\b{re.escape(bad)}\b", good, out)
        # Romanization filter:
        # - ñ before i/e is palatal and should stay ñ.
        # - ñ before final -s is usually OCR's stand-in for dotted n + suffix.
        # - syllable-final ñ is usually OCR's stand-in for dotted n; normalize to ṅ.
        # - OCR acute-n noise (ń) in final position is also normalized to ṅ.
        protected = "\uE000"
        out = N_TILDE_BEFORE_IE_RE.sub(protected, out)
        out = N_TILDE_ACUTE_N_BEFORE_S_FINAL_RE.sub("ṅ", out)
        out = N_TILDE_BEFORE_S_FINAL_RE.sub("ṅ", out)
        out = N_TILDE_SYL_FINAL_RE.sub("ṅ", out)
        out = N_ACUTE_N_BEFORE_S_FINAL_RE.sub("ṅ", out)
        out = N_ACUTE_N_SYL_FINAL_RE.sub("ṅ", out)
        out = out.replace(protected, "ñ")
    if "sanskrit" in zones:
        out = normalize_dieresis_in_skt_spans(out)
        out = normalize_dieresis_after_equals_translit(out)
        out = normalize_sanskrit_umlauts_in_text(out)
    if "romanization" in zones and TIB_RE.search(out):
        sanskrit_context = bool("sanskrit" in zones or TOKEN_DIACRITIC_OR_SKT_RE.search(out))
        tail = translit_tail_after_tibetan(out)
        if tail:
            lead = translit_lead_tokens(tail)
            has_lead_cues = any(token_has_translit_cues(p) for p in lead if p and not p.isspace())
            use_macron_norm = sanskrit_context or has_lead_cues
            if use_macron_norm:
                pieces: list[str] = []
                lead_consumed = len("".join(lead))
                for part in re.split(r"(\s+)", tail[:lead_consumed]):
                    if part and not part.isspace():
                        fixed = normalize_translit_token_dieresis(part, True)
                        fixed = normalize_sanskrit_token_chars(fixed, True)
                        pieces.append(fixed)
                    else:
                        pieces.append(part)
                out = out[: len(out) - len(tail)] + "".join(pieces) + tail[lead_consumed:]
        out = drop_roman_tail_noise_after_tibetan(out)
        out = enforce_ng_from_tibetan_prefix(out)
    return normalize_text(out)


def parse_pages_arg(pages: str) -> list[int]:
    out: set[int] = set()
    for part in pages.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start = int(a)
            end = int(b)
            if end < start:
                start, end = end, start
            out.update(range(start, end + 1))
        else:
            out.add(int(part))
    return sorted(out)


def evenly_spaced_pages(start: int, end: int, n: int) -> list[int]:
    if n <= 0:
        return []
    if n == 1:
        return [start]
    span = end - start
    if span <= 0:
        return [start]
    picks = []
    for i in range(n):
        pos = start + round((span * i) / (n - 1))
        picks.append(pos)
    return sorted(set(picks))


def get_pdf_pages(pdf: Path) -> int:
    proc = subprocess.run(["pdfinfo", str(pdf)], text=True, errors="replace", capture_output=True, check=True)
    m = re.search(r"^Pages:\s+(\d+)", proc.stdout, re.MULTILINE)
    if not m:
        raise RuntimeError(f"Could not read page count from pdfinfo for {pdf}")
    return int(m.group(1))


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, errors="replace", capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(cmd)
            + "\nSTDOUT:\n"
            + proc.stdout[-3000:]
            + "\nSTDERR:\n"
            + proc.stderr[-3000:]
        )


def run_tesseract_stdout_txt(image: Path, lang: str, psm: int, dpi: int, timeout_sec: float) -> str:
    cmd = [
        "tesseract",
        str(image),
        "stdout",
        "-l",
        lang,
        "--psm",
        str(psm),
        "--dpi",
        str(dpi),
        "-c",
        "preserve_interword_spaces=1",
    ]
    try:
        proc = subprocess.run(cmd, text=True, errors="replace", capture_output=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        # Treat single-crop OCR failures as empty candidates so one bad line image
        # does not abort long full-volume runs.
        return ""
    return proc.stdout.replace("\f", "").strip()


def choose_best_b_text(a_text: str, b_candidates: list[tuple[str, str]]) -> tuple[str, str]:
    a_norm = normalize_text(a_text)
    a_has_tib = bool(TIB_RE.search(a_norm))
    best = ""
    best_source = ""
    best_key = (-1, -1, -9999, -1, -1, -1.0, -10.0, -1)
    for source, bt in b_candidates:
        b_norm = normalize_text(bt)
        b_d = len(DIACRITIC_RE.findall(b_norm))
        sim = difflib.SequenceMatcher(None, a_norm, b_norm).ratio() if a_norm and b_norm else 0.0
        script_ok = int(not DEV_RE.search(b_norm) and ((not a_has_tib) or bool(TIB_RE.search(b_norm))))
        b_letters, b_neg_suspects, b_tail_d = roman_tail_quality_score(b_norm)
        if a_norm:
            len_ratio = len(b_norm) / len(a_norm) if len(a_norm) else 0.0
            len_closeness = -abs(len_ratio - 1.0)
        else:
            len_closeness = -1.0
        # For Tibetan-headword lines, prioritize cleaner romanization tails.
        if a_has_tib:
            key = (script_ok, b_letters, b_neg_suspects, b_tail_d, b_d, sim, len_closeness, len(b_norm))
        else:
            # Otherwise: prefer script-safe outputs, then richer diacritics and alignment.
            key = (script_ok, -1, -9999, -1, b_d, sim, len_closeness, len(b_norm))
        if key > best_key:
            best = bt
            best_source = source
            best_key = key
    return best, best_source


def make_crop_variants(raw_crop: Path, variants: list[str]) -> list[tuple[str, Path]]:
    from PIL import Image, ImageOps

    out: list[tuple[str, Path]] = []
    with Image.open(raw_crop) as img:
        for name in variants:
            if name == "raw":
                out.append((name, raw_crop))
                continue
            if name == "auto":
                v = ImageOps.autocontrast(ImageOps.grayscale(img))
            elif name == "bw180":
                g = ImageOps.autocontrast(ImageOps.grayscale(img))
                v = g.point(lambda p: 255 if p > 180 else 0, mode="1").convert("L")
            elif name == "up2x_auto":
                w, h = img.size
                up = img.resize((max(1, w * 2), max(1, h * 2)))
                v = ImageOps.autocontrast(ImageOps.grayscale(up))
            else:
                raise RuntimeError(f"Unknown crop variant: {name}")
            dst = raw_crop.with_name(f"{raw_crop.stem}_{name}.png")
            v.save(dst)
            out.append((name, dst))
    return out


def render_page_png(pdf: Path, page: int, dpi: int, out_png: Path) -> None:
    prefix = out_png.with_suffix("")
    run_cmd(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(dpi),
            "-png",
            str(pdf),
            str(prefix),
        ]
    )
    generated = out_png.parent / f"{prefix.name}-{page:04d}.png"
    if not generated.exists():
        raise RuntimeError(f"Expected rendered page image not found: {generated}")
    generated.rename(out_png)


def tesseract_hocr(image: Path, lang: str, psm: int, dpi: int, out_hocr: Path) -> None:
    base = out_hocr.with_suffix("")
    run_cmd(
        [
            "tesseract",
            str(image),
            str(base),
            "-l",
            lang,
            "--psm",
            str(psm),
            "--dpi",
            str(dpi),
            "hocr",
        ]
    )
    generated = out_hocr.parent / f"{base.name}.hocr"
    if not generated.exists():
        raise RuntimeError(f"Expected hOCR output not found: {generated}")
    if generated != out_hocr:
        generated.rename(out_hocr)


def iter_text(node: ET.Element) -> Iterable[str]:
    if node.text:
        yield node.text
    for child in node:
        yield from iter_text(child)
        if child.tail:
            yield child.tail


def parse_hocr_lines(hocr_path: Path) -> list[dict[str, object]]:
    xml_text = hocr_path.read_text(errors="replace")
    # hOCR occasionally includes invalid control chars; strip XML-illegal chars.
    xml_text = "".join(
        ch
        for ch in xml_text
        if ch in ("\t", "\n", "\r") or ord(ch) >= 0x20
    )
    root = ET.fromstring(xml_text)
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    out: list[dict[str, object]] = []
    for line in root.findall(".//x:span[@class='ocr_line']", ns):
        title = line.attrib.get("title", "")
        m = BBOX_RE.search(title)
        if not m:
            continue
        x0, y0, x1, y1 = map(int, m.groups())
        text = normalize_text("".join(iter_text(line)))
        out.append({"bbox": (x0, y0, x1, y1), "text": text})
    return out


def line_is_candidate(text: str) -> bool:
    if not LATIN_RE.search(text):
        return False
    # Target transliteration regions: mixed Tibetan+Latin or Latin with Sanskrit-like diacritics.
    if TIB_RE.search(text):
        return True
    if DIACRITIC_RE.search(text):
        return True
    if TRANSLIT_HINT_RE.search(text):
        return True
    return False


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def crop_image(src: Path, dst: Path, bbox: tuple[int, int, int, int], pad: int) -> None:
    x0, y0, x1, y1 = bbox
    from PIL import Image

    with Image.open(src) as img:
        w, h = img.size
        cx0 = clamp(x0 - pad, 0, w)
        cy0 = clamp(y0 - pad, 0, h)
        cx1 = clamp(x1 + pad, 0, w)
        cy1 = clamp(y1 + pad, 0, h)
        if cx1 <= cx0 or cy1 <= cy0:
            raise RuntimeError(f"Invalid crop box: {(x0, y0, x1, y1)}")
        img.crop((cx0, cy0, cx1, cy1)).save(dst)


def should_replace(
    a_text: str,
    b_text: str,
    min_similarity: float,
    min_similarity_diacritic_only: float,
    min_similarity_tibetan_anchor: float,
) -> tuple[bool, str, float, int, int]:
    a = normalize_text(a_text)
    b = normalize_text(b_text)
    if not b:
        return False, "empty_b", 0.0, 0, 0
    if DEV_RE.search(b):
        return False, "unexpected_devanagari", 0.0, 0, 0
    if TIB_RE.search(a) and not TIB_RE.search(b):
        return False, "lost_tibetan_script", 0.0, 0, 0
    a_d = len(DIACRITIC_RE.findall(a))
    b_d = len(DIACRITIC_RE.findall(b))
    if a:
        length_ratio = len(b) / len(a)
        if length_ratio < 0.5 or length_ratio > 1.8:
            return False, "length_ratio_out_of_range", 0.0, a_d, b_d
    similarity = difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0
    if b_d > a_d:
        if similarity < min_similarity:
            if similarity < min_similarity_diacritic_only:
                if similarity < min_similarity_tibetan_anchor:
                    return False, "similarity_too_low", similarity, a_d, b_d
                if tibetan_anchor_for_merge(a) and tibetan_anchor_for_merge(a) == tibetan_anchor_for_merge(b):
                    return True, "replace_tibetan_anchor", similarity, a_d, b_d
                return False, "similarity_too_low", similarity, a_d, b_d
            if base_equivalent_for_merge(a) == base_equivalent_for_merge(b):
                return True, "replace_diacritic_only", similarity, a_d, b_d
            if tibetan_anchor_for_merge(a) and tibetan_anchor_for_merge(a) == tibetan_anchor_for_merge(b):
                return True, "replace_tibetan_anchor", similarity, a_d, b_d
            return False, "similarity_too_low", similarity, a_d, b_d
        return True, "replace", similarity, a_d, b_d

    # Accept high-confidence OCR-confusable improvements even without diacritic gain.
    if similarity >= max(min_similarity, 0.92):
        a_norm_conf = normalize_ocr_confusables(a)
        b_norm_conf = normalize_ocr_confusables(b)
        a_sus = len(OCR_SUSPECT_RE.findall(a))
        b_sus = len(OCR_SUSPECT_RE.findall(b))
        if a_sus > b_sus and a_norm_conf == b_norm_conf:
            return True, "replace_confusable_gain", similarity, a_d, b_d

    if b_d <= a_d:
        # Allow Tibetan-headword anchored cleanup even without diacritic gain if B clearly improves
        # romanization tail quality and keeps the same Tibetan anchor.
        a_anchor = tibetan_anchor_for_merge(a)
        b_anchor = tibetan_anchor_for_merge(b)
        if (
            a_anchor
            and b_anchor
            and a_anchor == b_anchor
            and similarity >= min_similarity_tibetan_anchor
        ):
            a_q = roman_tail_quality_score(a)
            b_q = roman_tail_quality_score(b)
            a_noise = roman_tail_noise_score(a)
            b_noise = roman_tail_noise_score(b)
            if b_q > a_q and (
                (b_q[1] - a_q[1] >= 1 or b_q[2] > a_q[2])
                or (
                    a_noise >= 2
                    and b_noise < a_noise
                    and (b_q[0] - a_q[0]) >= 2
                    and b_q[1] >= a_q[1]
                )
            ):
                return True, "replace_headword_tail_cleanup", similarity, a_d, b_d
        if similarity >= min_similarity_diacritic_only and base_equivalent_for_merge(a) == base_equivalent_for_merge(b):
            if DIACRITIC_RE.search(a) or DIACRITIC_RE.search(b):
                return True, "replace_diacritic_only", similarity, a_d, b_d
        return False, "no_diacritic_gain", similarity, a_d, b_d
    if similarity < min_similarity:
        return False, "similarity_too_low", similarity, a_d, b_d
    return True, "replace", similarity, a_d, b_d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Input PDF path")
    ap.add_argument("--outdir", required=True, help="Output directory for pilot run")
    ap.add_argument("--pages", default="", help="Explicit pages, e.g. 1,5,10-20")
    ap.add_argument("--sample-count", type=int, default=0, help="Evenly spaced pages if --pages omitted")
    ap.add_argument(
        "--all-pages",
        action="store_true",
        help="Process every page in the selected start/end range.",
    )
    ap.add_argument("--start-page", type=int, default=1, help="Sample range start")
    ap.add_argument("--end-page", type=int, default=0, help="Sample range end (default: end of PDF)")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang-a", default="deu+bod")
    ap.add_argument("--lang-b", default="deu+bod+san+script/Latin")
    ap.add_argument("--psm-a", type=int, default=3)
    ap.add_argument("--psm-b-lines", default="7,6", help="Comma-separated list of B line PSMs")
    ap.add_argument(
        "--psm-b-lines-tib",
        default="7,13,6",
        help="Comma-separated B line PSMs for lines containing Tibetan script.",
    )
    ap.add_argument(
        "--crop-variants",
        default="raw,auto,bw180,up2x_auto",
        help="Comma-separated crop preprocess variants: raw,auto,bw180,up2x_auto",
    )
    ap.add_argument("--min-similarity", type=float, default=0.85)
    ap.add_argument(
        "--min-similarity-diacritic-only",
        type=float,
        default=0.78,
        help="Lower threshold for base-equivalent lines that differ mostly in diacritics/confusables.",
    )
    ap.add_argument(
        "--min-similarity-tibetan-anchor",
        type=float,
        default=0.73,
        help="Lower threshold when Tibetan-script anchor matches after tsheg/shad/digit normalization.",
    )
    ap.add_argument("--line-timeout-sec", type=float, default=20.0, help="Per-line tesseract timeout in seconds")
    ap.add_argument(
        "--candidate-mode",
        choices=["heuristic", "all_latin"],
        default="heuristic",
        help="Line candidate selection: heuristic translit detector, or all lines containing Latin letters.",
    )
    ap.add_argument(
        "--page-separator",
        choices=["formfeed", "marker"],
        default="formfeed",
        help="Output page delimiter in merged text.",
    )
    ap.add_argument(
        "--dehyphenate-wrap",
        action="store_true",
        help="Dehyphenate likely German/English line-wrap hyphens (skips transliteration-heavy lines).",
    )
    ap.add_argument(
        "--anomaly-report",
        action="store_true",
        help="Write anomaly CSV (digit runs, symbols, and Sanskrit-umlaut candidates).",
    )
    args = ap.parse_args()

    pdf = Path(args.pdf)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    pages_dir = outdir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    total_pages = get_pdf_pages(pdf)
    end_page = args.end_page if args.end_page > 0 else total_pages
    end_page = min(end_page, total_pages)
    start_page = max(1, args.start_page)
    if end_page < start_page:
        raise SystemExit("Invalid range: end-page < start-page")

    if args.pages:
        pages = [p for p in parse_pages_arg(args.pages) if start_page <= p <= end_page]
    elif args.all_pages:
        pages = list(range(start_page, end_page + 1))
    elif args.sample_count > 0:
        pages = evenly_spaced_pages(start_page, end_page, args.sample_count)
    else:
        raise SystemExit("Provide --pages, --sample-count, or --all-pages")
    if not pages:
        raise SystemExit("No pages selected")
    psm_b_values = [int(x.strip()) for x in args.psm_b_lines.split(",") if x.strip()]
    if not psm_b_values:
        raise SystemExit("No valid --psm-b-lines values")
    psm_b_values_tib = [int(x.strip()) for x in args.psm_b_lines_tib.split(",") if x.strip()]
    if not psm_b_values_tib:
        psm_b_values_tib = psm_b_values
    crop_variants = [x.strip() for x in args.crop_variants.split(",") if x.strip()]
    if not crop_variants:
        raise SystemExit("No valid --crop-variants values")

    merged_pages: list[str] = []
    summary_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    anomaly_rows: list[dict[str, object]] = []

    for page in pages:
        page_tag = f"p{page:04d}"
        png = pages_dir / f"{page_tag}.png"
        hocr = pages_dir / f"{page_tag}_A.hocr"
        render_page_png(pdf, page, args.dpi, png)
        tesseract_hocr(png, args.lang_a, args.psm_a, args.dpi, hocr)
        lines = parse_hocr_lines(hocr)

        page_total = len(lines)
        page_candidates = 0
        page_replaced = 0
        raw_final_lines: list[str] = []
        page_audit_meta: list[dict[str, object]] = []

        for idx, line in enumerate(lines, start=1):
            a_text = str(line["text"])
            bbox = line["bbox"]
            use_b = False
            b_text = ""
            reason = "non_candidate"
            similarity = 0.0
            a_d = len(DIACRITIC_RE.findall(a_text))
            b_d = 0

            is_candidate = line_is_candidate(a_text) if args.candidate_mode == "heuristic" else bool(LATIN_RE.search(a_text))
            if is_candidate:
                page_candidates += 1
                crop_path = pages_dir / f"{page_tag}_l{idx:04d}.png"
                crop_image(png, crop_path, bbox, pad=4)
                variant_paths = make_crop_variants(crop_path, crop_variants)
                b_candidates: list[tuple[str, str]] = []
                psm_values_this_line = psm_b_values_tib if TIB_RE.search(a_text) else psm_b_values
                for var_name, var_path in variant_paths:
                    for psm_b in psm_values_this_line:
                        source = f"{var_name}_psm{psm_b}"
                        bt = run_tesseract_stdout_txt(var_path, args.lang_b, psm_b, args.dpi, args.line_timeout_sec)
                        b_candidates.append((source, bt))
                b_text, b_source = choose_best_b_text(a_text, b_candidates)
                use_b, reason, similarity, a_d, b_d = should_replace(
                    a_text,
                    b_text,
                    args.min_similarity,
                    args.min_similarity_diacritic_only,
                    args.min_similarity_tibetan_anchor,
                )
                if not use_b and reason == "lost_tibetan_script":
                    spliced = maybe_splice_tibetan_prefix_with_b_tail(a_text, b_text, args.min_similarity_tibetan_anchor)
                    if spliced:
                        use_b = True
                        reason = "replace_splice_tibetan_prefix_b_tail"
                        b_text = spliced
                        b_source = f"{b_source}+splice" if b_source else "splice"
                        b_d = len(DIACRITIC_RE.findall(b_text))
            else:
                b_source = ""

            final_text = b_text if use_b else a_text
            if use_b:
                page_replaced += 1
            raw_final_lines.append(final_text)
            page_audit_meta.append(
                {
                    "page": page,
                    "line": idx,
                    "candidate": int(is_candidate),
                    "replaced": int(use_b),
                    "reason": reason,
                    "similarity": f"{similarity:.4f}",
                    "a_diacritics": a_d,
                    "b_diacritics": b_d,
                    "a_text": a_text,
                    "b_text": b_text,
                    "b_source": b_source,
                }
            )

        merged_lines = [post_cleanup_contextual(raw_final_lines, i, text) for i, text in enumerate(raw_final_lines)]
        if args.anomaly_report:
            for i, final_text in enumerate(merged_lines, start=1):
                anomaly_rows.extend(collect_anomalies(page, i, final_text))

        for meta, final_text in zip(page_audit_meta, merged_lines):
            row = dict(meta)
            row["final_text"] = final_text
            audit_rows.append(row)

        if args.dehyphenate_wrap:
            merged_lines = dehyphenate_wrapped_lines(merged_lines)
        merged_page_text = "\n".join(merged_lines)
        merged_pages.append(merged_page_text)
        summary_rows.append(
            {
                "page": page,
                "lines_total": page_total,
                "lines_candidate": page_candidates,
                "lines_replaced": page_replaced,
                "replace_rate_candidates": f"{(page_replaced / page_candidates):.4f}" if page_candidates else "0.0000",
            }
        )
        print(
            f"page={page} lines={page_total} candidates={page_candidates} replaced={page_replaced}",
            file=sys.stderr,
        )

    stem = pdf.stem
    merged_out = outdir / f"{stem}_lineanchored_merged_sample.txt"
    summary_out = outdir / f"{stem}_lineanchored_summary.csv"
    audit_out = outdir / f"{stem}_lineanchored_audit.csv"
    pages_out = outdir / f"{stem}_sampled_pages.txt"
    anomaly_out = outdir / f"{stem}_lineanchored_anomalies.csv"

    page_sep = "\f" if args.page_separator == "formfeed" else "\n\n<<<PAGE_BREAK>>>\n\n"
    merged_out.write_text(page_sep.join(merged_pages))
    pages_out.write_text("\n".join(str(p) for p in pages) + "\n")

    with summary_out.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "page",
                "lines_total",
                "lines_candidate",
                "lines_replaced",
                "replace_rate_candidates",
            ],
        )
        w.writeheader()
        w.writerows(summary_rows)

    with audit_out.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "page",
                "line",
                "candidate",
                "replaced",
                "reason",
                "similarity",
                "a_diacritics",
                "b_diacritics",
                "a_text",
                "b_text",
                "b_source",
                "final_text",
            ],
        )
        w.writeheader()
        w.writerows(audit_rows)

    if args.anomaly_report:
        with anomaly_out.open("w", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "page",
                    "line",
                    "type",
                    "token",
                    "context",
                    "zones",
                ],
            )
            w.writeheader()
            w.writerows(anomaly_rows)

    total_lines = sum(int(r["lines_total"]) for r in summary_rows)
    total_candidates = sum(int(r["lines_candidate"]) for r in summary_rows)
    total_replaced = sum(int(r["lines_replaced"]) for r in summary_rows)
    print(f"pdf={pdf}")
    print(f"pages={len(pages)}")
    print(f"lines_total={total_lines}")
    print(f"lines_candidate={total_candidates}")
    print(f"lines_replaced={total_replaced}")
    print(f"replace_rate_candidates={(total_replaced / total_candidates):.4f}" if total_candidates else "replace_rate_candidates=0.0000")
    print(f"merged_sample={merged_out}")
    print(f"summary_csv={summary_out}")
    print(f"audit_csv={audit_out}")
    if args.anomaly_report:
        print(f"anomaly_csv={anomaly_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
