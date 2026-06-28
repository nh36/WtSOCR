#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(
    r"[A-Za-zĀāĪīŪūṚṛṜṝḶḷḸḹṄṅÑñṬṭḌḍṆṇŚśṢṣḤḥṂṃṀṁŹźÄÖÜäöüßıńŃ$'’.-]+"
)
TIBETAN_SCRIPT_RE = re.compile(r"[\u0F00-\u0FFF]")
SANSKRIT_DIACRITIC_RE = re.compile(r"[āīūṛṝḷḹṅñṭḍṇśṣḥṃṁĀĪŪṚṜḶḸṄÑṬḌṆŚṢḤṂṀ]")
GERMAN_WORD_RE = re.compile(
    r"\b(?:und|oder|der|die|das|dem|den|des|ein|eine|einer|nicht|auch|von|mit|im|zu|als|für|nach|sich|wird|werden)\b",
    re.IGNORECASE,
)
TIBETAN_CUE_RE = re.compile(
    r"[\u0F00-\u0FFF]|"
    r"\b(?:Dagy|sGra|Toh|Tib\.|Wylie|bka'|dge|blo|bzang|bzaṅ|gnas|dngos|dṅos|chos|rgyal|sku|gsung|"
    r"shes|śes|rab|ye|rnam|thar|rje|lha|kha|mkha|gNa|gÑa|khri|bcu|pa'i|la'i|yi|kyi|gi|gis|nas)\b|"
    r"[a-zśźṅñ]'[ai]|(?:kh|tsh|ts|ph|th|dz|rdz|rgy|bzh|gz|mkh|dng|gny|gñ|mng|mṅ)",
    re.IGNORECASE,
)
STRONG_TIBETAN_CUE_RE = re.compile(
    r"[\u0F00-\u0FFF]|"
    r"\b(?:Dagy|sGra|Toh|Tib\.|Wylie|bka'|dge|blo|bzang|bzaṅ|gnas|dngos|dṅos|chos|rgyal|sku|gsung|"
    r"shes|śes|rab|ye|rnam|thar|rje|lha|mkha|gNa|gÑa|khri|bcu|pa'i|la'i|kyi|gis|nas)\b|"
    r"[a-zśźṅñ]'[ai]|(?:rdz|rgy|bzh|mkh|dng|gny|gñ|mng|mṅ)",
    re.IGNORECASE,
)
SANSKRIT_CONTEXT_RE = re.compile(
    r"\b(?:skt\.|sanskrit|mvy|lex\.|abhidharma|prajñ|prajnap|jñāna|jnāna|sūtra|sutra|śāstra|sas?tra|"
    r"dharmakīrti|nāga|bodhisattva|tathāgata|śrāvaka|sravaka)\b",
    re.IGNORECASE,
)
SIGLUM_CONTEXT_RE = re.compile(r"(?:\(|\)|,|;|:|\bms\.|\bmss\.|\bsource\b|\bvol\.|\bp\.|\bfol\.|\bDagy\b|\bToh\b|\bMvy\b|\bLex\.)", re.IGNORECASE)
SIGLUM_TOKEN_RE = re.compile(r"^[A-ZĀŚṢṬḌṆa-zāśṣṭḍṇ]{1,7}\$?[A-ZŚṢṬḌṆa-zāśṣṭḍṇ]{0,4}$")
TIBETAN_SCRIPT_NG_WITNESS_FORMS = {
    "གང": "gaṅ",
    "དང": "daṅ",
    "ཡང": "yaṅ",
    "ལྔ": "lṅa",
    "སྣང": "snaṅ",
    "སྔར": "sṅar",
    "གཙང": "gtsaṅ",
    "ནང": "naṅ",
    "རང": "raṅ",
}


@dataclass(frozen=True)
class SiglumEntry:
    canon: str
    work_title: str
    intro_line_ref: str
    status: str
    variants: tuple[str, ...] = ()


@dataclass
class GroupStats:
    count: int = 0
    volumes: set[str] | None = None
    source_tokens: Counter[str] | None = None
    proposed_targets: Counter[str] | None = None
    refs: list[str] | None = None
    contexts: list[str] | None = None
    evidences: Counter[str] | None = None
    confidences: Counter[str] | None = None
    actions: Counter[str] | None = None

    def __post_init__(self) -> None:
        self.volumes = set()
        self.source_tokens = Counter()
        self.proposed_targets = Counter()
        self.refs = []
        self.contexts = []
        self.evidences = Counter()
        self.confidences = Counter()
        self.actions = Counter()


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text).replace("\f", " ")).strip()


def stripped_token(token: str) -> str:
    return unicodedata.normalize("NFC", token).strip(" \t\r\n.,;:()[]{}<>\"“”")


def siglum_key(token: str) -> str:
    folded = stripped_token(token)
    folded = folded.replace("$", "s")
    folded = folded.replace("Ś", "s").replace("ś", "s")
    folded = folded.replace("Ṣ", "s").replace("ṣ", "s")
    folded = folded.replace("Ṭ", "t").replace("ṭ", "t")
    folded = folded.replace("Ḍ", "d").replace("ḍ", "d")
    folded = folded.replace("Ā", "a").replace("ā", "a")
    return folded.lower()


def has_siglum_shape(token: str) -> bool:
    clean = stripped_token(token)
    if not clean:
        return False
    if "$" in clean:
        return True
    letters = [ch for ch in clean if ch.isalpha()]
    if not letters:
        return False
    has_internal_upper = any(ch.isupper() for ch in clean[1:])
    has_siglum_diacritic = any(ch in clean for ch in "ĀŚṢṬḌṆāśṣṭḍṇ")
    has_digit_or_hyphen = any(ch.isdigit() for ch in clean) or "-" in clean
    return clean.isupper() or has_internal_upper or has_siglum_diacritic or has_digit_or_hyphen


def looks_like_unregistered_siglum(token: str, context: str) -> bool:
    clean = stripped_token(token)
    if not clean or not SIGLUM_TOKEN_RE.fullmatch(clean):
        return False
    if "$" in clean:
        return True
    if not SIGLUM_CONTEXT_RE.search(context):
        return False
    return has_siglum_shape(clean)


def registered_siglum_context_ok(clean: str, context: str, entries: list[SiglumEntry]) -> bool:
    registered_forms: set[str] = set()
    registered_keys: set[str] = set()
    for entry in entries:
        registered_forms.add(entry.canon)
        registered_forms.update(entry.variants)
        registered_keys.add(siglum_key(entry.canon))
        registered_keys.update(siglum_key(variant) for variant in entry.variants)
    if clean in registered_forms:
        return True
    if "$" in clean:
        return True
    if siglum_key(clean) in registered_keys and SIGLUM_CONTEXT_RE.search(context):
        return True
    if not has_siglum_shape(clean):
        return False
    return bool(SIGLUM_CONTEXT_RE.search(context))


def load_sigla_registry(path: Path) -> dict[str, list[SiglumEntry]]:
    registry: dict[str, list[SiglumEntry]] = defaultdict(list)
    if not path.exists():
        return registry
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            canon = row.get("canon", "").strip()
            variants = [canon]
            variants.extend(v.strip() for v in row.get("allowed_variants", "").split("|") if v.strip())
            entry = SiglumEntry(
                canon=canon,
                work_title=row.get("work_title", "").strip(),
                intro_line_ref=row.get("intro_line_ref", "").strip(),
                status=row.get("status", "").strip(),
                variants=tuple(variants),
            )
            if not entry.canon:
                continue
            for variant in variants:
                registry[siglum_key(variant)].append(entry)
    return registry


def classify_siglum_token(token: str, context: str, registry: dict[str, list[SiglumEntry]]) -> dict[str, str] | None:
    clean = stripped_token(token)
    if not clean:
        return None
    key = siglum_key(clean)
    entries = registry.get(key, [])
    if entries and not registered_siglum_context_ok(clean, context, entries):
        return None
    if not entries and not looks_like_unregistered_siglum(clean, context):
        return None
    if entries:
        entry = entries[0]
        canonical = entry.canon
        work_title = entry.work_title
        intro_line_ref = entry.intro_line_ref
        status = entry.status
    else:
        canonical = clean.replace("$", "ś")
        work_title = ""
        intro_line_ref = ""
        status = "unknown"
    if clean == canonical:
        action = "already_canonical_siglum"
    else:
        action = "siglum_policy_review"
    return {
        "canon": canonical,
        "work_title": work_title,
        "intro_line_ref": intro_line_ref,
        "status": status,
        "suggested_action": action,
    }


def is_german_prose(line: str) -> bool:
    german_hits = len(GERMAN_WORD_RE.findall(line))
    if german_hits < 2:
        return False
    if STRONG_TIBETAN_CUE_RE.search(line) or SANSKRIT_CONTEXT_RE.search(line):
        return False
    return True


def is_tibetan_context(line: str) -> bool:
    line = norm_text(line)
    if not line:
        return False
    if is_german_prose(line):
        return False
    return bool(TIBETAN_CUE_RE.search(line))


def is_sanskrit_context(line: str) -> bool:
    line = norm_text(line)
    if SANSKRIT_CONTEXT_RE.search(line):
        return True
    return bool(SANSKRIT_DIACRITIC_RE.search(line) and not is_tibetan_context(line))


def latin_n_source_for_ng_target(target: str) -> str:
    return target.replace("ṅ", "n").replace("Ṅ", "N")


def candidate_target_for_ng_witness_token(token: str, target: str) -> str | None:
    source = latin_n_source_for_ng_target(target)
    if token == source:
        return target
    for prefix in ("T", "\\", "I"):
        if token.startswith(prefix) and token[len(prefix) :] == source:
            return f"{prefix}{target}"
    return None


def classify_tibetan_script_ng_token(token: str, context: str) -> dict[str, str] | None:
    clean = stripped_token(token)
    if not clean or is_german_prose(context):
        return None
    if not TIBETAN_SCRIPT_RE.search(context):
        return None
    for tibetan_witness, target in TIBETAN_SCRIPT_NG_WITNESS_FORMS.items():
        if tibetan_witness not in context:
            continue
        proposed = candidate_target_for_ng_witness_token(clean, target)
        if proposed and proposed != clean:
            return {
                "candidate_family": "tibetan_script_ng_witness",
                "proposed_target": proposed,
                "tibetan_witness": tibetan_witness,
                "evidence": "tibetan_script_witness",
                "confidence": "high",
                "suggested_action": "exact_promotion_candidate",
                "score": "98",
                "score_explanation": (
                    "Latin n conflicts with same-line Tibetan-script ང witness; "
                    "review exact rows rather than applying a broad n->ṅ rule."
                ),
            }
    return None


def ref(volume: str, page: str | int, line: str | int) -> str:
    return f"{volume}:{page}:{line}"


def classify_tibetan_token(token: str, context: str) -> dict[str, str] | None:
    token = stripped_token(token)
    if not token or is_german_prose(context):
        return None
    context_is_tibetan = is_tibetan_context(context)
    if token == "dnos":
        return {
            "candidate_family": "dngos_family",
            "proposed_target": "dṅos",
            "evidence": "language_knowledge",
            "confidence": "high" if context_is_tibetan else "medium",
            "suggested_action": "exact_promotion_candidate" if context_is_tibetan else "review",
            "score": "95" if context_is_tibetan else "70",
            "score_explanation": "Exact Tibetan lexical repair; Google dños target is rejected.",
        }
    if token == "gNa-khri":
        return {
            "candidate_family": "gña_khri_family",
            "proposed_target": "gÑa-khri",
            "evidence": "language_knowledge",
            "confidence": "high" if context_is_tibetan else "medium",
            "suggested_action": "exact_promotion_candidate" if context_is_tibetan else "review",
            "score": "90" if context_is_tibetan else "65",
            "score_explanation": "Exact Tibetan proper-name style repair; not a broad n/ñ rule.",
        }
    if token == "la'añń":
        return {
            "candidate_family": "stacked_nasal_damage",
            "proposed_target": "",
            "evidence": "unknown",
            "confidence": "low",
            "suggested_action": "source_review",
            "score": "15",
            "score_explanation": "Both observed and la'aṅń-like forms remain malformed; source review needed.",
        }
    if "ń" in token or "Ń" in token:
        return {
            "candidate_family": "loc_nasal_damage",
            "proposed_target": token.replace("ń", "ṅ").replace("Ń", "Ṅ"),
            "evidence": "orthography_scan",
            "confidence": "medium" if context_is_tibetan else "low",
            "suggested_action": "review",
            "score": "55" if context_is_tibetan else "25",
            "score_explanation": "LOC-style acute-n appears in a Tibetan transliteration context.",
        }
    if "$" in token and context_is_tibetan:
        return {
            "candidate_family": "dollar_ś",
            "proposed_target": token.replace("$", "ś"),
            "evidence": "orthography_scan",
            "confidence": "medium",
            "suggested_action": "review",
            "score": "50",
            "score_explanation": "Dollar sign may represent ś in transliteration; sigla are handled separately.",
        }
    if "ı" in token:
        return {
            "candidate_family": "dotless_i",
            "proposed_target": token.replace("ı", "i"),
            "evidence": "orthography_scan",
            "confidence": "medium" if context_is_tibetan else "low",
            "suggested_action": "review",
            "score": "45" if context_is_tibetan else "20",
            "score_explanation": "Dotless i is likely OCR damage in transliteration.",
        }
    return None


def classify_google_row(row: dict[str, str], volume: str, registry: dict[str, list[SiglumEntry]]) -> dict[str, str] | None:
    base = stripped_token(row.get("base_token", ""))
    alt = stripped_token(row.get("alternate_token", ""))
    if not base or not alt or base == alt:
        return None
    base_line = norm_text(row.get("base_line", ""))
    alternate_line = norm_text(row.get("alternate_line", ""))
    context = base_line or alternate_line
    page = row.get("page", "")
    line = row.get("line", "")
    token_index = row.get("token_index", "")

    siglum = classify_siglum_token(base, context, registry) or classify_siglum_token(alt, context, registry)
    if siglum:
        return {
            "volume": volume,
            "page": page,
            "line": line,
            "token_index": token_index,
            "base_token": base,
            "alternate_token": alt,
            "proposed_target": siglum["canon"],
            "reason": row.get("reason", ""),
            "base_key": row.get("base_key", ""),
            "alternate_key": row.get("alternate_key", ""),
            "candidate_family": "citation_or_siglum",
            "context_excerpt": context,
            "alternate_line": alternate_line,
            "evidence": "sigla_registry" if siglum.get("work_title") else "siglum_shape",
            "confidence": "policy",
            "suggested_action": siglum["suggested_action"],
            "score": "5",
            "score_explanation": f"Bibliographic siglum candidate for {siglum['canon']}; do not treat as Sanskrit/Tibetan OCR evidence.",
            "alignment_method": row.get("alignment_method", ""),
            "alignment_attribution": row.get("alignment_attribution", ""),
            "resynchronization_attribution": row.get("resynchronization_attribution", ""),
        }

    if "wrong_nasal_dnos" in row.get("reason", "") or (base == "dnos" and alt == "dños"):
        return {
            "volume": volume,
            "page": page,
            "line": line,
            "token_index": token_index,
            "base_token": base,
            "alternate_token": alt,
            "proposed_target": "dṅos",
            "reason": row.get("reason", ""),
            "base_key": row.get("base_key", ""),
            "alternate_key": row.get("alternate_key", ""),
            "candidate_family": "dngos_family",
            "context_excerpt": context,
            "alternate_line": alternate_line,
            "evidence": "google_blocked_wrong_target_plus_language_knowledge",
            "confidence": "high" if is_tibetan_context(context) else "medium",
            "suggested_action": "exact_promotion_candidate" if is_tibetan_context(context) else "review",
            "score": "98",
            "score_explanation": "Google exposed the suspicious token but the dños alternate is rejected; Tibetan target is dṅos.",
            "alignment_method": row.get("alignment_method", ""),
            "alignment_attribution": row.get("alignment_attribution", ""),
            "resynchronization_attribution": row.get("resynchronization_attribution", ""),
        }

    token_class = classify_tibetan_token(base, context)
    if token_class:
        return {
            "volume": volume,
            "page": page,
            "line": line,
            "token_index": token_index,
            "base_token": base,
            "alternate_token": alt,
            "proposed_target": token_class["proposed_target"],
            "reason": row.get("reason", ""),
            "base_key": row.get("base_key", ""),
            "alternate_key": row.get("alternate_key", ""),
            "candidate_family": token_class["candidate_family"],
            "context_excerpt": context,
            "alternate_line": alternate_line,
            "evidence": "google_unresolved_plus_" + token_class["evidence"],
            "confidence": token_class["confidence"],
            "suggested_action": token_class["suggested_action"],
            "score": token_class["score"],
            "score_explanation": token_class["score_explanation"],
            "alignment_method": row.get("alignment_method", ""),
            "alignment_attribution": row.get("alignment_attribution", ""),
            "resynchronization_attribution": row.get("resynchronization_attribution", ""),
        }

    if is_tibetan_context(context) and any(ch in alt for ch in "ṅñśźÑŚŹ"):
        return {
            "volume": volume,
            "page": page,
            "line": line,
            "token_index": token_index,
            "base_token": base,
            "alternate_token": alt,
            "proposed_target": alt,
            "reason": row.get("reason", ""),
            "base_key": row.get("base_key", ""),
            "alternate_key": row.get("alternate_key", ""),
            "candidate_family": "google_tibetan_diacritic_disagreement",
            "context_excerpt": context,
            "alternate_line": alternate_line,
            "evidence": "google_unresolved_tibetan_context",
            "confidence": "medium",
            "suggested_action": "review",
            "score": "45",
            "score_explanation": "Google has a Tibetan-looking diacritic alternate, but this needs manual validation.",
            "alignment_method": row.get("alignment_method", ""),
            "alignment_attribution": row.get("alignment_attribution", ""),
            "resynchronization_attribution": row.get("resynchronization_attribution", ""),
        }
    return None


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, delimiter="\t", fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def iter_corrected_lines(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    for page_idx, page_text in enumerate(text.split("\f"), start=1):
        for line_idx, line in enumerate(page_text.splitlines(), start=1):
            yield page_idx, line_idx, norm_text(line)


def find_one(run_dir: Path, suffix: str) -> Path | None:
    found = sorted(run_dir.glob(f"*{suffix}"))
    return found[0] if found else None


def volume_label(run_dir: Path) -> str:
    corrected = find_one(run_dir, "_corrected_full.txt")
    if corrected:
        return corrected.name.removesuffix("_corrected_full.txt")
    return run_dir.name


def build_orthography_candidates(run_dir: Path, volume: str, registry: dict[str, list[SiglumEntry]]) -> list[dict[str, str]]:
    corrected = find_one(run_dir, "_corrected_full.txt")
    if not corrected:
        return []
    rows: list[dict[str, str]] = []
    for page, line_no, line in iter_corrected_lines(corrected):
        if not line or is_german_prose(line):
            continue
        for match in TOKEN_RE.finditer(line):
            tok = stripped_token(match.group(0))
            if not tok:
                continue
            if classify_siglum_token(tok, line, registry):
                continue
            token_class = classify_tibetan_token(tok, line)
            if not token_class:
                continue
            rows.append(
                {
                    "volume": volume,
                    "page": str(page),
                    "line": str(line_no),
                    "token": tok,
                    "candidate_family": token_class["candidate_family"],
                    "proposed_target": token_class["proposed_target"],
                    "context_excerpt": line,
                    "evidence": token_class["evidence"],
                    "confidence": token_class["confidence"],
                    "suggested_action": token_class["suggested_action"],
                    "score": token_class["score"],
                    "score_explanation": token_class["score_explanation"],
                }
            )
    return rows


def build_script_ng_witness_candidates(run_dir: Path, volume: str) -> list[dict[str, str]]:
    corrected = find_one(run_dir, "_corrected_full.txt")
    if not corrected:
        return []
    rows: list[dict[str, str]] = []
    for page, line_no, line in iter_corrected_lines(corrected):
        if not line:
            continue
        for token_index, match in enumerate(TOKEN_RE.finditer(line), start=1):
            tok = stripped_token(match.group(0))
            token_class = classify_tibetan_script_ng_token(tok, line)
            if not token_class:
                continue
            rows.append(
                {
                    "source_queue": "corrected_text_scan",
                    "volume": volume,
                    "page": str(page),
                    "line": str(line_no),
                    "token_index": str(token_index),
                    "source_token": tok,
                    "proposed_target": token_class["proposed_target"],
                    "tibetan_witness": token_class["tibetan_witness"],
                    "candidate_family": token_class["candidate_family"],
                    "context_excerpt": line,
                    "evidence": token_class["evidence"],
                    "confidence": token_class["confidence"],
                    "suggested_action": token_class["suggested_action"],
                    "score": token_class["score"],
                    "score_explanation": token_class["score_explanation"],
                }
            )
    return rows


def build_sigla_candidates(run_dir: Path, volume: str, registry: dict[str, list[SiglumEntry]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    corrected = find_one(run_dir, "_corrected_full.txt")
    if corrected:
        for page, line_no, line in iter_corrected_lines(corrected):
            if not line:
                continue
            for match in TOKEN_RE.finditer(line):
                tok = stripped_token(match.group(0))
                info = classify_siglum_token(tok, line, registry)
                if not info or info["suggested_action"] == "already_canonical_siglum":
                    continue
                rows.append(
                    {
                        "source_queue": "corrected_text_scan",
                        "volume": volume,
                        "page": str(page),
                        "line": str(line_no),
                        "token_index": "",
                        "source_token": tok,
                        "proposed_canon": info["canon"],
                        "work_title": info["work_title"],
                        "intro_line_ref": info["intro_line_ref"],
                        "status": info["status"],
                        "context_excerpt": line,
                        "suggested_action": info["suggested_action"],
                    }
                )
    for queue_name, suffix in [
        ("alternate_witness_unresolved", "_alternate_witness_unresolved.tsv"),
        ("alternate_witness_adoptions", "_alternate_witness_adoptions.tsv"),
    ]:
        path = find_one(run_dir, suffix)
        for row in read_tsv(path) if path else []:
            context = norm_text(row.get("base_line", "") or row.get("alternate_line", ""))
            for token_field in ["base_token", "alternate_token"]:
                tok = stripped_token(row.get(token_field, ""))
                info = classify_siglum_token(tok, context, registry)
                if not info or info["suggested_action"] == "already_canonical_siglum":
                    continue
                rows.append(
                    {
                        "source_queue": queue_name,
                        "volume": volume,
                        "page": row.get("page", ""),
                        "line": row.get("line", ""),
                        "token_index": row.get("token_index", ""),
                        "source_token": tok,
                        "proposed_canon": info["canon"],
                        "work_title": info["work_title"],
                        "intro_line_ref": info["intro_line_ref"],
                        "status": info["status"],
                        "context_excerpt": context,
                        "suggested_action": info["suggested_action"],
                    }
                )
    return rows


def build_google_candidates(run_dir: Path, volume: str, registry: dict[str, list[SiglumEntry]]) -> list[dict[str, str]]:
    path = find_one(run_dir, "_alternate_witness_unresolved.tsv")
    rows: list[dict[str, str]] = []
    for row in read_tsv(path) if path else []:
        candidate = classify_google_row(row, volume, registry)
        if candidate:
            rows.append(candidate)
    return rows


def build_adoption_patterns(run_dir: Path, volume: str) -> list[dict[str, str]]:
    path = find_one(run_dir, "_alternate_witness_adoptions.tsv")
    patterns: dict[tuple[str, str, str], GroupStats] = defaultdict(GroupStats)
    for row in read_tsv(path) if path else []:
        reason = row.get("reason", "")
        base = stripped_token(row.get("base_token", ""))
        alt = stripped_token(row.get("alternate_token", ""))
        key = (reason, base, alt)
        st = patterns[key]
        st.count += 1
        st.volumes.add(volume)
        st.refs.append(ref(volume, row.get("page", ""), row.get("line", "")))
        context = norm_text(row.get("base_line", ""))
        if context:
            st.contexts.append(context)
    out: list[dict[str, str]] = []
    for (reason, base, alt), st in sorted(patterns.items(), key=lambda item: item[1].count, reverse=True):
        out.append(
            {
                "reason": reason,
                "base_token": base,
                "alternate_token": alt,
                "count": str(st.count),
                "volume_count": str(len(st.volumes)),
                "sample_refs": "; ".join(st.refs[:5]),
                "sample_contexts": " || ".join(dict.fromkeys(st.contexts[:3])),
            }
        )
    return out


def build_sanskrit_low_confidence(run_dir: Path, volume: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    review = find_one(run_dir, "_review_queue.tsv")
    for row in read_tsv(review) if review else []:
        context = norm_text(row.get("line_excerpt", ""))
        from_token = stripped_token(row.get("from_token", ""))
        to_token = stripped_token(row.get("to_token", ""))
        if not from_token:
            continue
        if is_sanskrit_context(context) or "sanskrit" in row.get("reason", "").lower() or SANSKRIT_DIACRITIC_RE.search(from_token + to_token):
            rows.append(
                {
                    "source_queue": "review_queue",
                    "volume": volume,
                    "page": row.get("page", ""),
                    "line": row.get("line", ""),
                    "from_token": from_token,
                    "proposed_target": to_token,
                    "reason": row.get("reason", ""),
                    "applied": row.get("applied", ""),
                    "context_excerpt": context,
                    "confidence": "review",
                    "suggested_action": "review",
                }
            )
    corrected = find_one(run_dir, "_corrected_full.txt")
    if corrected:
        for page, line_no, line in iter_corrected_lines(corrected):
            if not is_sanskrit_context(line):
                continue
            for match in TOKEN_RE.finditer(line):
                tok = stripped_token(match.group(0))
                if not tok:
                    continue
                if any(marker in tok for marker in ["ä", "Ä", "$", "ı"]) or re.search(r"jn[āaīiuueo]", tok, re.IGNORECASE):
                    rows.append(
                        {
                            "source_queue": "corrected_text_scan",
                            "volume": volume,
                            "page": str(page),
                            "line": str(line_no),
                            "from_token": tok,
                            "proposed_target": "",
                            "reason": "residual_sanskrit_like_damage",
                            "applied": "",
                            "context_excerpt": line,
                            "confidence": "low",
                            "suggested_action": "review",
                        }
                    )
    return rows


def family_key_from_row(row: dict[str, str]) -> str:
    family = row.get("candidate_family") or row.get("reason") or "unknown"
    token = row.get("base_token") or row.get("token") or row.get("source_token") or row.get("from_token") or ""
    target = row.get("proposed_target") or row.get("proposed_canon") or ""
    folded = siglum_key(token)
    return f"{family}:{folded}:{siglum_key(target)}"


def build_variant_families(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    groups: dict[str, GroupStats] = defaultdict(GroupStats)
    family_names: dict[str, str] = {}
    for row in rows:
        key = family_key_from_row(row)
        family_names[key] = row.get("candidate_family") or row.get("reason") or "unknown"
        st = groups[key]
        st.count += 1
        st.volumes.add(row.get("volume", ""))
        source_token = row.get("base_token") or row.get("token") or row.get("source_token") or row.get("from_token") or ""
        target = row.get("proposed_target") or row.get("proposed_canon") or ""
        if source_token:
            st.source_tokens[source_token] += 1
        if target:
            st.proposed_targets[target] += 1
        if row.get("page") and row.get("line"):
            st.refs.append(ref(row.get("volume", ""), row.get("page", ""), row.get("line", "")))
        context = row.get("context_excerpt", "")
        if context:
            st.contexts.append(context)
        if row.get("evidence"):
            st.evidences[row["evidence"]] += 1
        if row.get("confidence"):
            st.confidences[row["confidence"]] += 1
        if row.get("suggested_action"):
            st.actions[row["suggested_action"]] += 1
    out: list[dict[str, str]] = []
    for key, st in sorted(groups.items(), key=lambda item: (-item[1].count, item[0])):
        out.append(
            {
                "family_key": key,
                "candidate_family": family_names[key],
                "source_tokens": ", ".join(f"{tok} ({n})" for tok, n in st.source_tokens.most_common(8)),
                "proposed_targets": ", ".join(f"{tok} ({n})" for tok, n in st.proposed_targets.most_common(5)),
                "occurrence_count": str(st.count),
                "volume_count": str(len([v for v in st.volumes if v])),
                "sample_refs": "; ".join(st.refs[:5]),
                "sample_contexts": " || ".join(dict.fromkeys(st.contexts[:3])),
                "evidence_summary": ", ".join(f"{k}:{v}" for k, v in st.evidences.most_common()),
                "confidence_summary": ", ".join(f"{k}:{v}" for k, v in st.confidences.most_common()),
                "suggested_action": st.actions.most_common(1)[0][0] if st.actions else "review",
            }
        )
    return out


def write_summary(out_dir: Path, counts: dict[str, int], family_rows: list[dict[str, str]], adoption_rows: list[dict[str, str]]) -> None:
    top_families = family_rows[:20]
    top_adoptions = adoption_rows[:15]
    lines = [
        "# Tibetan Cleanup Exploratory Diagnostics",
        "",
        "This is a diagnostics-only packet. It does not add OCR correction heuristics, does not loosen Google Vision adoption gates, and does not modify corrected text.",
        "",
        "## Row Counts",
        "",
    ]
    for name, count in counts.items():
        lines.append(f"- `{name}`: {count}")
    lines.extend(["", "## Top Candidate Families", ""])
    if top_families:
        lines.append("| Family | Sources | Targets | Count | Action |")
        lines.append("|---|---|---|---:|---|")
        for row in top_families:
            lines.append(
                f"| {row['candidate_family']} | {row['source_tokens']} | {row['proposed_targets']} | {row['occurrence_count']} | {row['suggested_action']} |"
            )
    else:
        lines.append("No candidate families were emitted.")
    lines.extend(["", "## Top Google Adoption Patterns", ""])
    if top_adoptions:
        lines.append("| Reason | Base | Alternate | Count |")
        lines.append("|---|---|---|---:|")
        for row in top_adoptions:
            lines.append(f"| {row['reason']} | {row['base_token']} | {row['alternate_token']} | {row['count']} |")
    else:
        lines.append("No alternate-witness adoption rows were available.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `tibetan_google_candidate_readings.tsv` contains unresolved Google-witness disagreements that may deserve manual review.",
            "- `tibetan_orthography_damage_candidates.tsv` scans the current corrected text directly for Tibetan-looking damage patterns.",
            "- `tibetan_script_ng_witness_candidates.tsv` scans corrected text for exact Latin `n`/`ṅ` disagreements backed by a same-line Tibetan-script `ང` witness. It is diagnostic only; it is not a broad `n -> ṅ` rule.",
            "- `sigla_variant_candidates.tsv` separates bibliography/siglum policy cases from Tibetan and Sanskrit normalisation.",
            "- `residual_sanskrit_low_confidence_candidates.tsv` is a small exploratory queue for Sanskrit-like residue outside the previous Sanskrit watch list.",
            "- Promotion should happen only in a later audited batch, using exact tokens and context gates.",
        ]
    )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build exploratory Tibetan/Sanskrit/sigla cleanup diagnostics from postprocess QA outputs.")
    parser.add_argument("--run-dir", action="append", required=True, help="Postprocess volume directory, e.g. work/.../wts_9_m")
    parser.add_argument("--out-dir", required=True, help="Output diagnostics directory")
    parser.add_argument("--sigla-registry", default="data/sigla_registry.tsv")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = load_sigla_registry(Path(args.sigla_registry))

    google_rows: list[dict[str, str]] = []
    orthography_rows: list[dict[str, str]] = []
    script_ng_rows: list[dict[str, str]] = []
    sigla_rows: list[dict[str, str]] = []
    sanskrit_rows: list[dict[str, str]] = []
    adoption_rows: list[dict[str, str]] = []

    for run in [Path(p) for p in args.run_dir]:
        volume = volume_label(run)
        google_rows.extend(build_google_candidates(run, volume, registry))
        orthography_rows.extend(build_orthography_candidates(run, volume, registry))
        script_ng_rows.extend(build_script_ng_witness_candidates(run, volume))
        sigla_rows.extend(build_sigla_candidates(run, volume, registry))
        sanskrit_rows.extend(build_sanskrit_low_confidence(run, volume))
        adoption_rows.extend(build_adoption_patterns(run, volume))

    google_fields = [
        "volume",
        "page",
        "line",
        "token_index",
        "base_token",
        "alternate_token",
        "proposed_target",
        "reason",
        "base_key",
        "alternate_key",
        "candidate_family",
        "context_excerpt",
        "alternate_line",
        "evidence",
        "confidence",
        "suggested_action",
        "score",
        "score_explanation",
        "alignment_method",
        "alignment_attribution",
        "resynchronization_attribution",
    ]
    orthography_fields = [
        "volume",
        "page",
        "line",
        "token",
        "candidate_family",
        "proposed_target",
        "context_excerpt",
        "evidence",
        "confidence",
        "suggested_action",
        "score",
        "score_explanation",
    ]
    script_ng_fields = [
        "source_queue",
        "volume",
        "page",
        "line",
        "token_index",
        "source_token",
        "proposed_target",
        "tibetan_witness",
        "candidate_family",
        "context_excerpt",
        "evidence",
        "confidence",
        "suggested_action",
        "score",
        "score_explanation",
    ]
    sigla_fields = [
        "source_queue",
        "volume",
        "page",
        "line",
        "token_index",
        "source_token",
        "proposed_canon",
        "work_title",
        "intro_line_ref",
        "status",
        "context_excerpt",
        "suggested_action",
    ]
    sanskrit_fields = [
        "source_queue",
        "volume",
        "page",
        "line",
        "from_token",
        "proposed_target",
        "reason",
        "applied",
        "context_excerpt",
        "confidence",
        "suggested_action",
    ]
    family_fields = [
        "family_key",
        "candidate_family",
        "source_tokens",
        "proposed_targets",
        "occurrence_count",
        "volume_count",
        "sample_refs",
        "sample_contexts",
        "evidence_summary",
        "confidence_summary",
        "suggested_action",
    ]
    adoption_fields = [
        "reason",
        "base_token",
        "alternate_token",
        "count",
        "volume_count",
        "sample_refs",
        "sample_contexts",
    ]

    family_rows = build_variant_families(google_rows + orthography_rows + script_ng_rows + sigla_rows)
    write_tsv(out_dir / "tibetan_google_candidate_readings.tsv", google_rows, google_fields)
    write_tsv(out_dir / "tibetan_orthography_damage_candidates.tsv", orthography_rows, orthography_fields)
    write_tsv(out_dir / "tibetan_script_ng_witness_candidates.tsv", script_ng_rows, script_ng_fields)
    write_tsv(out_dir / "sigla_variant_candidates.tsv", sigla_rows, sigla_fields)
    write_tsv(out_dir / "residual_sanskrit_low_confidence_candidates.tsv", sanskrit_rows, sanskrit_fields)
    write_tsv(out_dir / "tibetan_variant_families.tsv", family_rows, family_fields)
    write_tsv(out_dir / "tibetan_google_adoption_patterns.tsv", adoption_rows, adoption_fields)

    write_summary(
        out_dir,
        {
            "tibetan_google_candidate_readings.tsv": len(google_rows),
            "tibetan_orthography_damage_candidates.tsv": len(orthography_rows),
            "tibetan_script_ng_witness_candidates.tsv": len(script_ng_rows),
            "sigla_variant_candidates.tsv": len(sigla_rows),
            "residual_sanskrit_low_confidence_candidates.tsv": len(sanskrit_rows),
            "tibetan_variant_families.tsv": len(family_rows),
            "tibetan_google_adoption_patterns.tsv": len(adoption_rows),
        },
        family_rows,
        adoption_rows,
    )


if __name__ == "__main__":
    main()
