#!/usr/bin/env python3
"""Promote exact reference-marker candidates using empirical lemma order.

This is an exact-row reviewer, not an OCR rule. Direction is determined by
comparing the current entry's observed lemma ordinal with the referenced
lemma's observed ordinal in the current release.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import exact_promotion_batch as batch


VOLUME_ORDER = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
MARKER_SOURCES = {"I", "T", "/", "\\"}
REFERENCE_MARKER_REASON = "reviewed_tibetan_exact_reference_marker"
EVIDENCE_TAG = "reference_marker_lemma_order_20260701"
REVIEW_NOTE = (
    "Exact page-line-token reference-marker correction from lemma-order "
    "promotion; direction from current/referenced lemma ordinal; no broad "
    "marker, slash, Initial-I/l, or nasal rule."
)
TEXT_INVESTIGATION_REVIEW_NOTE = (
    "Exact page-line-token reference-marker correction from bounded text "
    "investigation; accepted proof is lemma-order, sibling-marker, or "
    "same-family-reviewed evidence; no broad marker, slash, Initial-I/l, "
    "or nasal rule."
)
INVESTIGATION_PREFIX_MARKERS = {"I", "T", "\\"}
INVESTIGATION_PROMOTE_PROOF_TYPES = {
    "lemma_order",
    "sibling_marker",
    "same_family_reviewed",
}
INVESTIGATION_REFERENCE_CONTEXTS = {
    "reference_cue",
    "near_actual_marker_control",
    "headword_transliteration_context",
    "reference_list_context",
}

TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňıß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňıß$]+)*"
)
EXACT_OVERRIDE_TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňß$]+)*"
)
TRAILING_SUFFIXES = ("ı", "'", "’")
REFERENCE_CONTEXT_RE = re.compile(
    r"\b(vgl|Lex|unter|cf)\.|\bs\.\s*v\.|\b(v|V)\.\s|[=~]",
    re.IGNORECASE,
)
STRONG_SLASH_CONTEXT_RE = re.compile(
    r"\b(vgl|Lex|unter|cf)\.|\bs\.\s*v\.",
    re.IGNORECASE,
)
METRIC_CONTEXT_RE = re.compile(r"\((?:metr|poet)\.\)|\b(?:Vers|Strophe|Metrum)\b", re.IGNORECASE)
GRAMMATICAL_LABEL_CONTEXT_RE = re.compile(
    r"\b(?:imp|imper|imperat|imperativ)\.\s+[\\/IT]?[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]",
    re.IGNORECASE,
)
BAD_CONTEXT_RE = re.compile(
    r"\b(?:Skt|Sanskrit|Indien|International|Inhalt|Ich|Ingwer)\b"
)
FINAL_PARTICLES = {
    "kyi",
    "gyi",
    "gi",
    "gis",
    "yis",
    "la",
    "las",
    "na",
    "nas",
    "ni",
    "dan",
    "daṅ",
    "pa",
    "ba",
    "po",
    "mo",
}
HARD_NEGATIVE_REASONS = {
    "possible_ldan_not_marker",
    "slash_punctuation_context",
    "ordinary_example_context",
    "false_positive_control",
    "no_referenced_lemma_match",
    "ambiguous_crosses_current",
    "ambiguous_replacement_target",
    "unknown_current_lemma",
    "same_lemma",
    "exact_source_token_not_found",
    "exact_source_token_ambiguous",
    "superscript_marker_unclear",
}


@dataclass(frozen=True)
class Lemma:
    ordinal: int
    volume: str
    page: str
    line: str
    entry_id: str
    headword_tibetan: str
    headword_transliteration: str
    normalized_key: str
    source: str

    @property
    def ref(self) -> str:
        return f"{self.volume} {self.page}:{self.line}"


@dataclass(frozen=True)
class LemmaAlias:
    lemma: Lemma
    alias: str
    basis: str


@dataclass(frozen=True)
class LookupResult:
    candidate: str
    lookup_key: str
    alias_matched: str
    alias_basis: str
    lemma: Lemma | None
    status: str
    matches: tuple[LemmaAlias, ...] = ()


@dataclass(frozen=True)
class CandidateDecision:
    volume: str
    page: str
    line: str
    diagnostic_token_index: str
    token_index: str
    source_token: str
    marker_source: str
    marker_target: str
    attached_token: str
    current_lemma: str
    current_lemma_ordinal: str
    current_lemma_ref: str
    referenced_lemma_candidate: str
    referenced_lemma: str
    referenced_lemma_ordinal: str
    referenced_lemma_ref: str
    referenced_lemma_match_count: str
    referenced_lemma_ordinal_min: str
    referenced_lemma_ordinal_max: str
    matched_lemma_ordinals: str
    direction_resolution: str
    lemma_lookup_status: str
    referenced_lemma_lookup_key: str
    referenced_lemma_alias_matched: str
    lemma_alias_basis: str
    exact_occurrence_status: str
    context_type: str
    direction_basis: str
    replacement_target: str
    candidate_family: str
    similar_to_promoted_family: str
    context_excerpt: str
    near_vgl: str
    near_headword: str
    near_transliteration: str
    near_tibetan_script: str
    decision: str
    defer_reason: str
    decision_notes: str
    score: str
    positive_evidence: str
    negative_evidence: str
    tier: str


@dataclass(frozen=True)
class ReviewedReferencePattern:
    marker_source: str
    attached_key: str
    target_marker: str
    target_token: str
    volume: str
    page: str
    line: str
    from_token: str
    to_token: str


NEAR_MISS_FIELDS = [
    "volume",
    "page",
    "line",
    "token_index",
    "source_token",
    "attached_token",
    "current_lemma",
    "current_lemma_ordinal",
    "referenced_lemma_candidate",
    "matched_lemma_ordinals",
    "direction_resolution",
    "candidate_family",
    "context_excerpt",
    "score",
    "defer_reason",
    "decision_notes",
    "suggested_target",
]

INVESTIGATION_FIELDS = [
    "batch_id",
    "volume",
    "page",
    "line",
    "token_index",
    "source_token",
    "reviewed_to_token",
    "decision",
    "proof_type",
    "proof_note",
    "current_lemma",
    "current_lemma_ordinal",
    "current_lemma_ref",
    "referenced_lemma_candidate",
    "referenced_lemma",
    "referenced_lemma_ordinal",
    "referenced_lemma_ref",
    "matched_lemma_ordinals",
    "direction_basis",
    "context_type",
    "defer_reason",
    "candidate_family",
    "marker_source",
    "attached_token",
    "score",
    "positive_evidence",
    "negative_evidence",
    "source_diagnostic",
    "context_before_2",
    "context_before_1",
    "context_line",
    "context_after_1",
    "context_after_2",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def as_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_key(value: str) -> str:
    text = unicodedata.normalize("NFC", value)
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = text.replace("ı", "i")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \t\r\n,.;:()[]{}\"")
    return text.lower()


def add_variant(variants: dict[str, str], value: str, basis: str) -> None:
    key = normalize_key(value)
    if key and key not in variants:
        variants[key] = basis


def lemma_aliases(value: str) -> dict[str, str]:
    variants: dict[str, str] = {}
    text = unicodedata.normalize("NFC", value)
    add_variant(variants, text, "normalized")
    add_variant(variants, text.replace("’", "'").replace("‘", "'"), "apostrophe_normalized")
    add_variant(variants, text.replace("ı", "i"), "dotless_i_folded")

    truncated = re.split(r"\s*[(,;]\s*", text, maxsplit=1)[0]
    if truncated and truncated != text:
        add_variant(variants, truncated, "annotation_truncated")

    base_values = list(variants)
    for key in base_values:
        if "-" in key:
            add_variant(variants, key.replace("-", " "), "hyphen_to_space")
        if " " in key:
            add_variant(variants, key.replace(" ", "-"), "space_to_hyphen")

    return variants


def add_lemma_aliases(lemma_index: dict[str, list[LemmaAlias]], lemma: Lemma) -> None:
    for alias, basis in lemma_aliases(lemma.headword_transliteration).items():
        lemma_index[alias].append(LemmaAlias(lemma=lemma, alias=alias, basis=basis))


def lookup_variants(token: str) -> dict[str, str]:
    variants: dict[str, str] = {}
    add_variant(variants, token, "normalized")
    replacements = [
        ("ans", "aṅs"),
        ("an", "aṅ"),
        ("on", "oṅ"),
        ("en", "eṅ"),
        ("in", "iṅ"),
        ("un", "uṅ"),
    ]
    for src, dst in replacements:
        if token.endswith(src):
            add_variant(variants, f"{token[: -len(src)]}{dst}", f"final_{src}_to_{dst}_lookup")
    return variants


def phrase_lookup_variants(tokens: list[str], *, cutoff_basis: str = "") -> dict[str, str]:
    if not tokens:
        return {}
    variants = lookup_variants(tokens[0])
    for token in tokens[1:]:
        token_variants = lookup_variants(token)
        combined: dict[str, str] = {}
        for prefix, prefix_basis in variants.items():
            for suffix, suffix_basis in token_variants.items():
                basis = "+".join(part for part in (prefix_basis, suffix_basis) if part)
                combined[f"{prefix} {suffix}"] = basis or "normalized"
        variants = combined

    expanded: dict[str, str] = {}
    for phrase, basis in variants.items():
        add_variant(expanded, phrase, basis)
        if "-" in phrase:
            add_variant(expanded, phrase.replace("-", " "), f"{basis}+hyphen_to_space")
        if " " in phrase:
            add_variant(expanded, phrase.replace(" ", "-"), f"{basis}+space_to_hyphen")
    if cutoff_basis:
        expanded = {key: f"{basis}+{cutoff_basis}" for key, basis in expanded.items()}
    return expanded


def release_volumes(root: Path) -> Iterable[str]:
    for volume in VOLUME_ORDER:
        if (root / "release" / "current" / "text" / f"{volume}_corrected_full.txt").exists():
            yield volume


def load_line_zones(
    root: Path,
) -> tuple[
    dict[tuple[str, str, str], dict[str, str]],
    dict[tuple[str, str], Lemma],
    dict[str, list[LemmaAlias]],
    list[Lemma],
]:
    by_line: dict[tuple[str, str, str], dict[str, str]] = {}
    lemma_by_entry: dict[tuple[str, str], Lemma] = {}
    lemma_index: dict[str, list[LemmaAlias]] = defaultdict(list)
    lemmas: list[Lemma] = []
    ordinal = 0

    for volume in release_volumes(root):
        path = root / "release" / "current" / "qa" / volume / f"{volume}_line_zones.tsv"
        for row in read_tsv(path):
            by_line[(volume, row["page"], row["line"])] = row
            entry_id = row.get("entry_id", "")
            if (
                row.get("zone") != "headword_line"
                or not entry_id
                or entry_id == "0"
                or not row.get("headword_latin", "").strip()
                or (volume, entry_id) in lemma_by_entry
            ):
                continue
            key = normalize_key(row["headword_latin"])
            if not key:
                continue
            ordinal += 1
            lemma = Lemma(
                ordinal=ordinal,
                volume=volume,
                page=row["page"],
                line=row["line"],
                entry_id=entry_id,
                headword_tibetan=row.get("headword_tibetan", ""),
                headword_transliteration=row.get("headword_latin", ""),
                normalized_key=key,
                source="line_zones.headword_line",
            )
            lemma_by_entry[(volume, entry_id)] = lemma
            add_lemma_aliases(lemma_index, lemma)
            lemmas.append(lemma)

    return by_line, lemma_by_entry, lemma_index, lemmas


def load_release_lines(root: Path) -> dict[tuple[str, str, str], str]:
    lines: dict[tuple[str, str, str], str] = {}
    for volume in release_volumes(root):
        path = root / "release" / "current" / "text" / f"{volume}_corrected_full.txt"
        pages = path.read_text(encoding="utf-8").split("\f")
        for page_index, page in enumerate(pages, start=1):
            for line_index, line in enumerate(page.split("\n"), start=1):
                lines[(volume, str(page_index), str(line_index))] = line
    return lines


def load_reference_marker_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for volume in release_volumes(root):
        path = (
            root
            / "release"
            / "current"
            / "qa"
            / volume
            / "tibetan_cleanup_diagnostics"
            / "reference_marker_candidates.tsv"
        )
        if path.exists():
            rows.extend(read_tsv(path))
    return rows


def current_lemma_for(
    row: dict[str, str],
    line_zones: dict[tuple[str, str, str], dict[str, str]],
    lemma_by_entry: dict[tuple[str, str], Lemma],
) -> Lemma | None:
    zone = line_zones.get((row["volume"], row["page"], row["line"]))
    if not zone:
        return None
    entry_id = zone.get("entry_id", "")
    if not entry_id or entry_id == "0":
        return None
    return lemma_by_entry.get((row["volume"], entry_id))


def split_marker(row: dict[str, str]) -> tuple[str, str, str]:
    source_token = row.get("source_token", "")
    suspected = row.get("suspected_marker_source", "")
    if source_token in {"↑", "↓", "↑²", "↓²"}:
        return source_token, "", "actual_marker"
    if suspected in MARKER_SOURCES and source_token.startswith(suspected) and len(source_token) > len(suspected):
        return suspected, source_token[len(suspected) :], "attached"
    if source_token and source_token[0] in MARKER_SOURCES and len(source_token) > 1:
        return source_token[0], source_token[1:], "attached"
    if source_token in MARKER_SOURCES:
        return source_token, row.get("attached_token", ""), "standalone"
    return suspected, row.get("attached_token", ""), "unknown"


def extract_exact_override_tokens(line: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in EXACT_OVERRIDE_TOKEN_RE.finditer(line)]


def exact_override_match_options(
    line: str, token: str, start: int, end: int
) -> list[tuple[str, int, int]]:
    options: list[tuple[str, int, int]] = []

    def prefix_has_left_boundary(prefix_start: int) -> bool:
        if prefix_start <= 0:
            return True
        previous = line[prefix_start - 1]
        return not (previous.isalpha() or previous.isdigit() or previous in {"'", "’", "-", "_"})

    if start > 0 and line[start - 1] in {"/", "\\"} and prefix_has_left_boundary(start - 1):
        prefix_start = start - 1
        prefix = line[prefix_start]
        for suffix in ("", *TRAILING_SUFFIXES):
            if suffix and line[end : end + len(suffix)] != suffix:
                continue
            options.append((f"{prefix}{token}{suffix}", prefix_start, end + len(suffix)))

    whitespace_start = start
    while whitespace_start > 0 and line[whitespace_start - 1].isspace():
        whitespace_start -= 1
    if whitespace_start < start and whitespace_start > 0:
        prefix_start = whitespace_start - 1
        if line[prefix_start] in {"/", "\\"} and prefix_has_left_boundary(prefix_start):
            prefix = line[prefix_start:start]
            for suffix in ("", *TRAILING_SUFFIXES):
                if suffix and line[end : end + len(suffix)] != suffix:
                    continue
                options.append((f"{prefix}{token}{suffix}", prefix_start, end + len(suffix)))

    for suffix in ("", *TRAILING_SUFFIXES):
        if suffix and line[end : end + len(suffix)] != suffix:
            continue
        options.append((f"{token}{suffix}", start, end + len(suffix)))

    return options


def line_occurrence_for_source(source_token: str, line: str) -> tuple[int | None, str]:
    occurrences: list[int] = []

    for index, (token, start, end) in enumerate(extract_exact_override_tokens(line), start=1):
        candidates = exact_override_match_options(line, token, start, end)
        if any(candidate == source_token for candidate, _start, _end in candidates):
            occurrences.append(index)
    if len(occurrences) == 1:
        return occurrences[0], "unique"
    if not occurrences:
        return None, "not_found"
    return None, "ambiguous"


def exact_source_for_marker_occurrence(
    source_token: str, marker_source: str, attached_token: str, line: str, split_kind: str
) -> tuple[str, str]:
    if split_kind != "standalone" or marker_source not in {"/", "\\"} or not attached_token:
        return source_token, "candidate"

    attached_key = normalize_key(attached_token)
    matches: set[str] = set()
    for token, start, end in extract_exact_override_tokens(line):
        if normalize_key(token) != attached_key:
            continue
        for candidate, _candidate_start, _candidate_end in exact_override_match_options(
            line, token, start, end
        ):
            if candidate.startswith(f"{marker_source} ") and normalize_key(
                candidate.split(maxsplit=1)[1]
            ) == attached_key:
                matches.add(candidate)
    if len(matches) == 1:
        return next(iter(matches)), "unique"
    if not matches:
        return source_token, "not_found"
    return source_token, "ambiguous"


def transliteration_tokens_after_source(
    source_token: str, attached_token: str, line: str, split_kind: str
) -> list[str]:
    if split_kind == "attached":
        position = line.find(source_token)
        tail = line[position + len(source_token) :] if position >= 0 else ""
        return [attached_token] + [m.group(0) for m in TOKEN_RE.finditer(tail[:80])][:5]

    position = line.find(source_token)
    if position < 0:
        return [attached_token] if attached_token else []
    tail = line[position + len(source_token) :]
    tokens = [m.group(0) for m in TOKEN_RE.finditer(tail[:80])][:6]
    if attached_token and (not tokens or normalize_key(tokens[0]) != normalize_key(attached_token)):
        tokens.insert(0, attached_token)
    return tokens[:6]


def lookup_longest_unique(
    tokens: list[str], lemma_index: dict[str, list[LemmaAlias]]
) -> LookupResult:
    for length in range(min(6, len(tokens)), 0, -1):
        phrase_tokens = tokens[:length]
        phrase = " ".join(phrase_tokens)
        cutoff_basis = ""
        if length < len(tokens) and normalize_key(tokens[length]) in FINAL_PARTICLES:
            cutoff_basis = f"final_particle_cutoff:{tokens[length]}"
        matched: dict[int, tuple[str, str, LemmaAlias]] = {}
        for key, variant_basis in phrase_lookup_variants(phrase_tokens, cutoff_basis=cutoff_basis).items():
            for alias in lemma_index.get(key, []):
                matched.setdefault(alias.lemma.ordinal, (key, variant_basis, alias))
        if not matched:
            continue

        ordered = [value for _ordinal, value in sorted(matched.items())]
        key, variant_basis, alias = ordered[0]
        matches = tuple(value[2] for value in ordered)
        if len(ordered) == 1:
            return LookupResult(
                candidate=phrase,
                lookup_key=key,
                alias_matched=alias.alias,
                alias_basis=f"{variant_basis}|{alias.basis}",
                lemma=alias.lemma,
                status="unique_match",
                matches=matches,
            )
        return LookupResult(
            candidate=phrase,
            lookup_key=key,
            alias_matched=alias.alias,
            alias_basis=f"{variant_basis}|{alias.basis}",
            lemma=None,
            status="ambiguous_match",
            matches=matches,
        )
    return LookupResult(
        candidate=" ".join(tokens[: min(6, len(tokens))]),
        lookup_key="",
        alias_matched="",
        alias_basis="",
        lemma=None,
        status="no_match",
        matches=(),
    )


def context_type(row: dict[str, str], split_kind: str) -> str:
    context = row.get("context_excerpt", "")
    if BAD_CONTEXT_RE.search(context):
        return "control_context"
    if GRAMMATICAL_LABEL_CONTEXT_RE.search(context):
        return "ordinary_example_context"
    if REFERENCE_CONTEXT_RE.search(context):
        return "reference_cue"
    if "↑" in context or "↓" in context:
        return "near_actual_marker_control"
    if row.get("near_headword") == "1" and row.get("near_transliteration") == "1":
        return "headword_transliteration_context"
    if ";" in context and row.get("near_transliteration") == "1":
        return "reference_list_context"
    if row.get("candidate_family", "").startswith("ocr_prefix_") and row.get("confidence") == "high":
        return "attached_high_confidence_context"
    if split_kind == "standalone" and row.get("source_token") == "/":
        return "slash_standalone_uncued_context"
    return "ordinary_context"


def context_is_reference_like(row: dict[str, str], kind: str = "") -> bool:
    if kind in {
        "reference_cue",
        "near_actual_marker_control",
        "headword_transliteration_context",
        "reference_list_context",
    }:
        return True
    context = row.get("context_excerpt", "")
    if REFERENCE_CONTEXT_RE.search(context):
        return True
    if row.get("near_headword") == "1" and row.get("near_transliteration") == "1":
        return True
    return False


def slash_context_is_promotable(row: dict[str, str], kind: str) -> bool:
    """Slash requires a stronger cue than attached I/T/backslash candidates."""
    context = row.get("context_excerpt", "")
    if METRIC_CONTEXT_RE.search(context):
        return False
    if GRAMMATICAL_LABEL_CONTEXT_RE.search(context):
        return False
    if kind == "near_actual_marker_control":
        return True
    if STRONG_SLASH_CONTEXT_RE.search(context) or "=" in context:
        return True
    return False


def repeated_slash_separator_context(context: str) -> bool:
    if STRONG_SLASH_CONTEXT_RE.search(context) or "=" in context or "↑" in context or "↓" in context:
        return False
    if context.count("/") < 2:
        return False
    return bool(
        re.search(
            r"\b[A-Za-zÀ-ÖØ-öø-ÿĀ-ž'’.-]+\s*/\s+"
            r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž'’.-]+\s*/\s+"
            r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž'’.-]+",
            context,
        )
    )


def looks_like_ldan_not_marker(source_token: str, attached_token: str, context: str) -> bool:
    if not source_token.startswith("I"):
        return False
    if normalize_key(attached_token).startswith("dan"):
        return True
    return bool(re.search(r"[A-Za-zÀ-ÿĀ-ž]-Idan\b", context))


def looks_like_slash_punctuation(row: dict[str, str], split_kind: str, kind: str) -> bool:
    if row.get("source_token") != "/" and not row.get("source_token", "").startswith("/"):
        return False
    context = row.get("context_excerpt", "")
    if METRIC_CONTEXT_RE.search(context) or GRAMMATICAL_LABEL_CONTEXT_RE.search(context):
        return True
    if repeated_slash_separator_context(context):
        return True
    if split_kind == "standalone" and not slash_context_is_promotable(row, kind):
        return True
    return False


def score_decision(
    *,
    lookup_status: str,
    current_known: bool,
    direction_known: bool,
    reference_like: bool,
    exact_unique: bool,
    split_kind: str,
    marker_source: str,
    hard_negative: str,
    similar_to_promoted_family: str,
) -> tuple[int, str, str]:
    score = 0
    positive: list[str] = []
    negative: list[str] = []
    if lookup_status == "unique_match":
        score += 50
        positive.append("unique_referenced_lemma_match")
    if lookup_status in {"ambiguous_same_direction_up", "ambiguous_same_direction_down"}:
        score += 45
        positive.append("ambiguous_referenced_lemma_same_direction")
    if current_known:
        score += 30
        positive.append("known_current_lemma")
    if direction_known:
        score += 30
        positive.append("clear_lemma_order_direction")
    if reference_like:
        score += 20
        positive.append("reference_like_context")
    if exact_unique:
        score += 15
        positive.append("unique_exact_marker_occurrence")
    if split_kind == "attached" and marker_source in {"I", "T", "\\"}:
        score += 15
        positive.append("attached_marker_prefix_with_transliteration")
    if marker_source == "/" and reference_like and exact_unique:
        score += 10
        positive.append("slash_with_reference_context_and_unique_occurrence")
    if similar_to_promoted_family:
        score += 10
        positive.append(similar_to_promoted_family)

    if hard_negative:
        penalty = {
            "possible_ldan_not_marker": 50,
            "slash_punctuation_context": 40,
            "false_positive_control": 40,
            "ambiguous_crosses_current": 30,
            "ambiguous_replacement_target": 30,
            "unknown_current_lemma": 30,
            "exact_source_token_not_found": 30,
            "exact_source_token_ambiguous": 30,
            "superscript_marker_unclear": 20,
        }.get(hard_negative, 20)
        score -= penalty
        negative.append(hard_negative)
    return score, ";".join(positive), ";".join(negative)


def first_replacement_token(source_attached: str, referenced_lemma: str) -> str:
    if not referenced_lemma:
        return source_attached
    first = referenced_lemma.split()[0]
    return first or source_attached


def reference_source_parts(source: str) -> tuple[str, str]:
    if source.startswith("/ "):
        return "/", source.split(maxsplit=1)[1].split()[0]
    if source.startswith("\\ "):
        return "\\", source.split(maxsplit=1)[1].split()[0]
    if source and source[0] in MARKER_SOURCES:
        attached = source[1:].split()[0] if len(source) > 1 else ""
        return source[0], attached
    return "", ""


def load_promoted_reference_marker_patterns(root: Path) -> set[tuple[str, str]]:
    path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
    if not path.exists():
        return set()
    patterns: set[tuple[str, str]] = set()
    for row in read_tsv(path):
        if row.get("reason") != REFERENCE_MARKER_REASON:
            continue
        marker_source, attached = reference_source_parts(row.get("from_token", ""))
        if marker_source and attached:
            patterns.add((marker_source, normalize_key(attached)))
    return patterns


def load_reviewed_reference_marker_details(root: Path) -> list[ReviewedReferencePattern]:
    path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
    if not path.exists():
        return []
    patterns: list[ReviewedReferencePattern] = []
    for row in read_tsv(path):
        if row.get("reason") != REFERENCE_MARKER_REASON:
            continue
        marker_source, attached = reference_source_parts(row.get("from_token", ""))
        target = row.get("to_token", "")
        target_marker = target[:1] if target[:1] in {"↑", "↓"} else ""
        if not marker_source or not attached or not target_marker:
            continue
        target_parts = target.split(maxsplit=1)
        target_token = target_parts[1].split()[0] if len(target_parts) > 1 else attached
        patterns.append(
            ReviewedReferencePattern(
                marker_source=marker_source,
                attached_key=normalize_key(attached),
                target_marker=target_marker,
                target_token=target_token,
                volume=row.get("volume", ""),
                page=row.get("page", ""),
                line=row.get("line", ""),
                from_token=row.get("from_token", ""),
                to_token=target,
            )
        )
    return patterns


def promoted_family_similarity(
    marker_source: str, attached_token: str, patterns: set[tuple[str, str]]
) -> str:
    if (marker_source, normalize_key(attached_token)) in patterns:
        return "same_marker_attached_token_as_reviewed_row"
    return ""


def decide_candidate(
    row: dict[str, str],
    line_zones: dict[tuple[str, str, str], dict[str, str]],
    lemma_by_entry: dict[tuple[str, str], Lemma],
    lemma_index: dict[str, list[LemmaAlias]],
    release_lines: dict[tuple[str, str, str], str],
    promoted_patterns: set[tuple[str, str]] | None = None,
) -> CandidateDecision:
    promoted_patterns = promoted_patterns or set()
    volume = row["volume"]
    page = row["page"]
    line_no = row["line"]
    line = release_lines.get((volume, page, line_no), "")
    source_token = row.get("source_token", "")
    marker_source, attached_token, split_kind = split_marker(row)
    context = row.get("context_excerpt", "")
    kind = context_type(row, split_kind)
    base = {
        "volume": volume,
        "page": page,
        "line": line_no,
        "diagnostic_token_index": row.get("token_index", ""),
        "token_index": "",
        "source_token": source_token,
        "marker_source": marker_source,
        "marker_target": "",
        "attached_token": attached_token,
        "current_lemma": "",
        "current_lemma_ordinal": "",
        "current_lemma_ref": "",
        "referenced_lemma_candidate": "",
        "referenced_lemma": "",
        "referenced_lemma_ordinal": "",
        "referenced_lemma_ref": "",
        "referenced_lemma_match_count": "",
        "referenced_lemma_ordinal_min": "",
        "referenced_lemma_ordinal_max": "",
        "matched_lemma_ordinals": "",
        "direction_resolution": "",
        "lemma_lookup_status": "",
        "referenced_lemma_lookup_key": "",
        "referenced_lemma_alias_matched": "",
        "lemma_alias_basis": "",
        "exact_occurrence_status": "",
        "context_type": kind,
        "direction_basis": "",
        "replacement_target": "",
        "candidate_family": row.get("candidate_family", ""),
        "similar_to_promoted_family": "",
        "context_excerpt": context,
        "near_vgl": row.get("near_vgl", ""),
        "near_headword": row.get("near_headword", ""),
        "near_transliteration": row.get("near_transliteration", ""),
        "near_tibetan_script": row.get("near_tibetan_script", ""),
        "decision": "defer",
        "defer_reason": "",
        "decision_notes": "",
        "score": "0",
        "positive_evidence": "",
        "negative_evidence": "",
        "tier": "",
    }

    def finish(**updates: str) -> CandidateDecision:
        values = {**base, **updates}
        return CandidateDecision(**values)

    def finish_with_score(**updates: str) -> CandidateDecision:
        values = {**base, **updates}
        if (
            values.get("decision") == "promote"
            and marker_source == "/"
            and not slash_context_is_promotable(row, values.get("context_type", kind))
        ):
            values["decision"] = "defer"
            values["defer_reason"] = "slash_punctuation_context"
            values["decision_notes"] = "Slash lacks a strong reference cue; kept diagnostic-only."
        score, positive, negative = score_decision(
            lookup_status=values.get("lemma_lookup_status", ""),
            current_known=bool(values.get("current_lemma_ordinal")),
            direction_known=bool(values.get("marker_target")),
            reference_like=context_is_reference_like(row, values.get("context_type", kind)),
            exact_unique=values.get("exact_occurrence_status") == "unique",
            split_kind=split_kind,
            marker_source=marker_source,
            hard_negative=values.get("defer_reason", "")
            if values.get("defer_reason", "") in HARD_NEGATIVE_REASONS
            else "",
            similar_to_promoted_family=values.get("similar_to_promoted_family", ""),
        )
        if values.get("decision") == "promote" and score >= 100:
            values["tier"] = "A"
        elif values.get("decision") == "promote":
            values["decision"] = "defer"
            values["defer_reason"] = "tier_a_score_below_threshold"
            values["decision_notes"] = "Evidence did not reach Tier A threshold."
        values["score"] = str(score)
        values["positive_evidence"] = positive
        values["negative_evidence"] = negative
        return CandidateDecision(**values)

    if source_token in {"↑", "↓"}:
        return finish(
            decision="false_positive",
            defer_reason="already_normalized",
            marker_target=source_token,
            decision_notes="Actual marker already present; diagnostic control only.",
        )
    if source_token in {"↑²", "↓²"} or "²" in source_token:
        return finish(
            defer_reason="superscript_marker_unclear",
            decision_notes="Lemma order does not choose superscript marker numbers.",
        )
    if marker_source not in MARKER_SOURCES or split_kind == "unknown":
        return finish_with_score(defer_reason="false_positive_control", decision_notes="No promotable marker source.")
    if BAD_CONTEXT_RE.search(context):
        return finish_with_score(defer_reason="false_positive_control", decision_notes="Control/prose context.")
    if looks_like_ldan_not_marker(source_token, attached_token, context):
        return finish_with_score(
            defer_reason="possible_ldan_not_marker",
            decision_notes="I appears to belong to ldan-like compound damage, not a reference marker.",
        )

    exact_source_token, exact_source_status = exact_source_for_marker_occurrence(
        source_token, marker_source, attached_token, line, split_kind
    )
    if split_kind == "standalone" and marker_source in {"/", "\\"} and exact_source_status != "unique":
        return finish_with_score(
            source_token=exact_source_token,
            exact_occurrence_status=exact_source_status,
            defer_reason=f"exact_source_token_{exact_source_status}",
            decision_notes="Could not locate a unique marker plus right-hand token occurrence.",
        )
    tokens = transliteration_tokens_after_source(exact_source_token, attached_token, line, split_kind)
    token_index, token_status = line_occurrence_for_source(exact_source_token, line)
    if token_index is None:
        return finish_with_score(
            source_token=exact_source_token,
            exact_occurrence_status=token_status,
            defer_reason=f"exact_source_token_{token_status}",
            decision_notes="Could not identify a unique exact token occurrence in the release line.",
        )

    current = current_lemma_for(row, line_zones, lemma_by_entry)
    if current is None:
        return finish_with_score(
            token_index=str(token_index),
            source_token=exact_source_token,
            exact_occurrence_status=token_status,
            defer_reason="unknown_current_lemma",
            decision_notes="Line-zone metadata does not identify the current lemma.",
        )

    if not tokens:
        return finish_with_score(
            token_index=str(token_index),
            source_token=exact_source_token,
            exact_occurrence_status=token_status,
            current_lemma=current.headword_transliteration,
            current_lemma_ordinal=str(current.ordinal),
            current_lemma_ref=current.ref,
            defer_reason="no_referenced_lemma_match",
            decision_notes="No Tibetan transliteration candidate found to the right of the marker.",
        )

    lookup = lookup_longest_unique(tokens, lemma_index)
    referenced = lookup.lemma
    match_ordinals = sorted({alias.lemma.ordinal for alias in lookup.matches})
    match_lemmas = [alias.lemma for alias in lookup.matches]
    match_fields = {
        "referenced_lemma_match_count": str(len(match_ordinals)) if match_ordinals else "0",
        "referenced_lemma_ordinal_min": str(match_ordinals[0]) if match_ordinals else "",
        "referenced_lemma_ordinal_max": str(match_ordinals[-1]) if match_ordinals else "",
        "matched_lemma_ordinals": ";".join(str(ordinal) for ordinal in match_ordinals),
    }
    similar_to_promoted = promoted_family_similarity(
        marker_source, attached_token or (tokens[0] if tokens else ""), promoted_patterns
    )
    common = {
        "token_index": str(token_index),
        "source_token": exact_source_token,
        "exact_occurrence_status": token_status,
        "current_lemma": current.headword_transliteration,
        "current_lemma_ordinal": str(current.ordinal),
        "current_lemma_ref": current.ref,
        "referenced_lemma_candidate": lookup.candidate,
        "referenced_lemma": referenced.headword_transliteration if referenced else "",
        "lemma_lookup_status": lookup.status,
        "referenced_lemma_lookup_key": lookup.lookup_key,
        "referenced_lemma_alias_matched": lookup.alias_matched,
        "lemma_alias_basis": lookup.alias_basis,
        "similar_to_promoted_family": similar_to_promoted,
        **match_fields,
    }
    if not match_ordinals:
        return finish_with_score(
            **common,
            defer_reason="no_referenced_lemma_match",
            decision_notes="Referenced lemma lookup did not yield a unique match.",
        )

    if current.ordinal in match_ordinals:
        return finish_with_score(
            **common,
            defer_reason="same_lemma",
            decision_notes="One possible referenced lemma resolves to the current lemma.",
        )
    all_before = all(ordinal < current.ordinal for ordinal in match_ordinals)
    all_after = all(ordinal > current.ordinal for ordinal in match_ordinals)
    if not (all_before or all_after):
        ambiguous_common = {
            **common,
            "lemma_lookup_status": "ambiguous_crosses_current",
            "direction_resolution": "ambiguous_crosses_current",
        }
        return finish_with_score(
            **ambiguous_common,
            defer_reason="ambiguous_crosses_current",
            decision_notes="Possible referenced lemmas occur on both sides of the current lemma.",
        )
    if looks_like_slash_punctuation(row, split_kind, kind):
        return finish_with_score(
            **common,
            defer_reason="slash_punctuation_context",
            decision_notes="Slash context is not strong enough for exact marker promotion.",
        )
    if not context_is_reference_like(row, kind):
        return finish_with_score(
            **common,
            defer_reason="ordinary_example_context",
            decision_notes="Lemma match exists, but context is not clearly reference-like.",
        )

    marker_target = "↑" if all_before else "↓"
    direction_resolution = "unique_up" if marker_target == "↑" else "unique_down"
    if len(match_ordinals) > 1:
        direction_resolution = (
            "ambiguous_same_direction_up" if marker_target == "↑" else "ambiguous_same_direction_down"
        )
    replacement_tokens = {
        first_replacement_token(attached_token, lemma.headword_transliteration) for lemma in match_lemmas
    }
    if len(replacement_tokens) != 1:
        replacement_common = {
            **common,
            "lemma_lookup_status": direction_resolution if len(match_ordinals) > 1 else lookup.status,
            "direction_resolution": direction_resolution,
        }
        return finish_with_score(
            **replacement_common,
            defer_reason="ambiguous_replacement_target",
            decision_notes=(
                "Lemma-order direction is clear, but possible referenced lemmas require "
                "different local replacement tokens."
            ),
        )
    replacement_first_token = next(iter(replacement_tokens))
    display_referenced = referenced or match_lemmas[0]
    common.update(
        {
            "referenced_lemma": (
                display_referenced.headword_transliteration
                if len(match_ordinals) == 1
                else "<ambiguous: same direction>"
            ),
            "referenced_lemma_ordinal": (
                str(display_referenced.ordinal)
                if len(match_ordinals) == 1
                else f"{match_ordinals[0]}-{match_ordinals[-1]}"
            ),
            "referenced_lemma_ref": (
                display_referenced.ref
                if len(match_ordinals) == 1
                else "; ".join(lemma.ref for lemma in match_lemmas[:5])
            ),
            "lemma_lookup_status": direction_resolution if len(match_ordinals) > 1 else lookup.status,
            "direction_resolution": direction_resolution,
        }
    )
    ordinal_side = (
        str(match_ordinals[0]) if len(match_ordinals) == 1 else f"{match_ordinals[0]}-{match_ordinals[-1]}"
    )
    return finish_with_score(
        **common,
        marker_target=marker_target,
        replacement_target=f"{marker_target} {replacement_first_token}",
        direction_basis=f"{ordinal_side} {'<' if marker_target == '↑' else '>'} {current.ordinal}",
        decision="promote",
        decision_notes=(
            "Tier A: referenced lemma evidence and known current lemma; marker "
            "direction chosen from empirical lemma order."
        ),
    )


def decision_to_row(decision: CandidateDecision) -> dict[str, str]:
    return decision.__dict__.copy()


def override_row_from_decision(decision: CandidateDecision, batch_id: str = "") -> dict[str, str]:
    evidence = EVIDENCE_TAG if not batch_id else f"{EVIDENCE_TAG}:{batch_id}"
    return {
        "volume": decision.volume,
        "page": decision.page,
        "line": decision.line,
        "token_index": decision.token_index,
        "from_token": decision.source_token,
        "to_token": decision.replacement_target,
        "reason": REFERENCE_MARKER_REASON,
        "evidence": evidence,
        "review_note": REVIEW_NOTE,
    }


def diagnostic_source_for(decision: CandidateDecision) -> str:
    return (
        f"release/current/qa/{decision.volume}/"
        "tibetan_cleanup_diagnostics/reference_marker_candidates.tsv"
    )


def packet_row_from_decision(decision: CandidateDecision, batch_id: str) -> dict[str, str]:
    row = override_row_from_decision(decision, batch_id=batch_id)
    row.update(
        {
            "batch_id": batch_id,
            "score": decision.score,
            "source_diagnostic": diagnostic_source_for(decision),
            "candidate_family": decision.candidate_family,
            "direction_basis": decision.direction_basis,
            "context_type": decision.context_type,
            "positive_evidence": decision.positive_evidence,
            "negative_evidence": decision.negative_evidence,
        }
    )
    return row


def parse_ordinals(value: str) -> list[int]:
    ordinals: list[int] = []
    for part in re.split(r"[;,\s]+", value.strip()):
        if not part:
            continue
        try:
            ordinals.append(int(part))
        except ValueError:
            continue
    return ordinals


def clean_investigation_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\t", " ")).strip()


def investigation_context_window(
    release_lines: dict[tuple[str, str, str], str],
    decision: CandidateDecision,
) -> dict[str, str]:
    line_no = as_int(decision.line, default=-1)

    def line_at(offset: int) -> str:
        if line_no < 1 or line_no + offset < 1:
            return ""
        return release_lines.get(
            (decision.volume, decision.page, str(line_no + offset)),
            "",
        )

    return {
        "context_before_2": line_at(-2),
        "context_before_1": line_at(-1),
        "context_line": line_at(0),
        "context_after_1": line_at(1),
        "context_after_2": line_at(2),
    }


def investigation_context_is_reference_like(decision: CandidateDecision) -> bool:
    if decision.context_type in INVESTIGATION_REFERENCE_CONTEXTS:
        return True
    if REFERENCE_CONTEXT_RE.search(decision.context_excerpt):
        return True
    return False


def exact_source_is_unique(decision: CandidateDecision) -> bool:
    return decision.exact_occurrence_status in {"unique", "candidate"} and bool(decision.token_index)


def candidate_target_token(decision: CandidateDecision) -> str:
    return first_replacement_token(
        decision.attached_token,
        decision.referenced_lemma or decision.referenced_lemma_candidate,
    )


def lemma_order_text_proof(decision: CandidateDecision) -> tuple[str, str, str] | None:
    if as_int(decision.referenced_lemma_match_count) != 1 or not decision.referenced_lemma:
        return None
    current = as_int(decision.current_lemma_ordinal)
    ordinals = parse_ordinals(decision.matched_lemma_ordinals)
    if current <= 0 or not ordinals or current in ordinals:
        return None
    all_before = all(ordinal < current for ordinal in ordinals)
    all_after = all(ordinal > current for ordinal in ordinals)
    if not (all_before or all_after):
        return None
    target_token = candidate_target_token(decision)
    if not target_token:
        return None
    marker_target = "↑" if all_before else "↓"
    ordinal_side = (
        str(ordinals[0])
        if len(ordinals) == 1
        else f"{min(ordinals)}-{max(ordinals)}"
    )
    direction_basis = f"{ordinal_side} {'<' if all_before else '>'} {current}"
    proof_note = (
        "text proof: referenced lemma ordinal(s) are all "
        f"{'before' if all_before else 'after'} current lemma; context is reference-like"
    )
    return f"{marker_target} {target_token}", direction_basis, proof_note


def sibling_marker_text_proof(
    decision: CandidateDecision,
    context_line: str,
) -> tuple[str, str, str] | None:
    if decision.marker_source not in INVESTIGATION_PREFIX_MARKERS:
        return None
    if not context_line or not re.search(r"[;,]", context_line):
        return None
    if not (
        decision.context_type in {"near_actual_marker_control", "reference_list_context", "reference_cue"}
        or REFERENCE_CONTEXT_RE.search(context_line)
    ):
        return None
    directions = set(re.findall(r"[↑↓]", context_line))
    if len(directions) != 1:
        return None
    target_token = candidate_target_token(decision)
    if not target_token:
        return None
    marker_target = next(iter(directions))
    direction_basis = f"sibling_marker_line_direction={marker_target}"
    proof_note = (
        "text proof: same local list contains an actual marker and all visible "
        f"sibling markers point {marker_target}"
    )
    return f"{marker_target} {target_token}", direction_basis, proof_note


def same_family_reviewed_text_proof(
    decision: CandidateDecision,
    reviewed_patterns: list[ReviewedReferencePattern],
) -> tuple[str, str, str] | None:
    if decision.marker_source not in INVESTIGATION_PREFIX_MARKERS:
        return None
    if not investigation_context_is_reference_like(decision):
        return None
    attached_key = normalize_key(decision.attached_token)
    if not attached_key:
        return None
    page = as_int(decision.page, default=-1)
    line = as_int(decision.line, default=-1)
    for pattern in reviewed_patterns:
        if pattern.marker_source != decision.marker_source:
            continue
        if pattern.attached_key != attached_key:
            continue
        if pattern.volume != decision.volume or as_int(pattern.page, default=-2) != page:
            continue
        if line < 1 or abs(as_int(pattern.line, default=-100000) - line) > 6:
            continue
        target_token = candidate_target_token(decision)
        if not target_token:
            continue
        direction_basis = (
            f"reviewed_family={pattern.volume} {pattern.page}:{pattern.line} "
            f"{pattern.from_token}->{pattern.to_token}"
        )
        proof_note = (
            "text proof: same marker plus attached token already reviewed in the "
            "same local entry/list window"
        )
        return f"{pattern.target_marker} {target_token}", direction_basis, proof_note
    return None


def source_image_needed(decision: CandidateDecision, context_line: str) -> bool:
    if decision.marker_source not in INVESTIGATION_PREFIX_MARKERS:
        return False
    if not exact_source_is_unique(decision):
        return False
    if decision.defer_reason in {
        "same_lemma",
        "ambiguous_crosses_current",
        "possible_ldan_not_marker",
        "false_positive_control",
        "ordinary_example_context",
        "slash_punctuation_context",
    }:
        return False
    if investigation_context_is_reference_like(decision):
        return True
    return bool(re.search(r"[↑↓]", context_line) and re.search(r"[;,]", context_line))


def investigation_reject_note(decision: CandidateDecision) -> str:
    ordinals = parse_ordinals(decision.matched_lemma_ordinals)
    current = as_int(decision.current_lemma_ordinal)
    if decision.marker_source == "/":
        return "slash row excluded from this reference-marker investigation"
    if decision.marker_source not in INVESTIGATION_PREFIX_MARKERS:
        return "not an investigated prefix marker source"
    if not exact_source_is_unique(decision):
        return "exact source occurrence is not uniquely located in corrected text"
    if decision.defer_reason == "possible_ldan_not_marker" or looks_like_ldan_not_marker(
        decision.source_token,
        decision.attached_token,
        decision.context_excerpt,
    ):
        return "likely Initial-I/l or ldan-like OCR damage, not a reference marker"
    if current > 0 and current in ordinals:
        return "referenced lemma resolves to the current lemma"
    if ordinals and current > 0 and not (
        all(ordinal < current for ordinal in ordinals)
        or all(ordinal > current for ordinal in ordinals)
    ):
        return "possible referenced lemmas cross the current lemma, so direction is unproved"
    if decision.defer_reason == "no_referenced_lemma_match":
        return "no referenced lemma can be proven from corrected text"
    if decision.context_type in {"ordinary_context", "ordinary_example_context", "control_context"}:
        return "ordinary prose/example context, not a reference-list context"
    if not investigation_context_is_reference_like(decision):
        return "local text context does not prove reference-marker usage"
    if decision.defer_reason:
        return f"unresolved diagnostic defer reason: {decision.defer_reason}"
    return "no concrete text proof found"


def base_investigation_row(
    decision: CandidateDecision,
    release_lines: dict[tuple[str, str, str], str],
    batch_id: str,
) -> dict[str, str]:
    row = {
        "batch_id": batch_id,
        "volume": decision.volume,
        "page": decision.page,
        "line": decision.line,
        "token_index": decision.token_index,
        "source_token": decision.source_token,
        "reviewed_to_token": "",
        "decision": "",
        "proof_type": "",
        "proof_note": "",
        "current_lemma": decision.current_lemma,
        "current_lemma_ordinal": decision.current_lemma_ordinal,
        "current_lemma_ref": decision.current_lemma_ref,
        "referenced_lemma_candidate": decision.referenced_lemma_candidate,
        "referenced_lemma": decision.referenced_lemma,
        "referenced_lemma_ordinal": decision.referenced_lemma_ordinal
        or decision.referenced_lemma_ordinal_min,
        "referenced_lemma_ref": decision.referenced_lemma_ref,
        "matched_lemma_ordinals": decision.matched_lemma_ordinals,
        "direction_basis": decision.direction_basis,
        "context_type": decision.context_type,
        "defer_reason": decision.defer_reason,
        "candidate_family": decision.candidate_family,
        "marker_source": decision.marker_source,
        "attached_token": decision.attached_token,
        "score": decision.score,
        "positive_evidence": decision.positive_evidence,
        "negative_evidence": decision.negative_evidence,
        "source_diagnostic": diagnostic_source_for(decision),
    }
    row.update(investigation_context_window(release_lines, decision))
    return {field: clean_investigation_text(row.get(field, "")) for field in INVESTIGATION_FIELDS}


def investigate_decision(
    decision: CandidateDecision,
    release_lines: dict[tuple[str, str, str], str],
    reviewed_patterns: list[ReviewedReferencePattern],
    batch_id: str,
) -> dict[str, str]:
    row = base_investigation_row(decision, release_lines, batch_id)
    context_line = row.get("context_line", "")
    if decision.marker_source == "/" or decision.marker_source not in INVESTIGATION_PREFIX_MARKERS:
        row.update(decision="reject_not_marker", proof_note=investigation_reject_note(decision))
        return row
    if not exact_source_is_unique(decision):
        row.update(decision="reject_not_marker", proof_note=investigation_reject_note(decision))
        return row
    if investigation_reject_note(decision).startswith(
        ("likely Initial-I", "referenced lemma resolves", "possible referenced lemmas cross")
    ):
        row.update(decision="reject_not_marker", proof_note=investigation_reject_note(decision))
        return row

    if investigation_context_is_reference_like(decision):
        proof = lemma_order_text_proof(decision)
        if proof:
            reviewed_to_token, direction_basis, proof_note = proof
            row.update(
                decision="promote_exact",
                proof_type="lemma_order",
                reviewed_to_token=reviewed_to_token,
                direction_basis=direction_basis,
                proof_note=proof_note,
            )
            return row

    proof = sibling_marker_text_proof(decision, context_line)
    if proof:
        reviewed_to_token, direction_basis, proof_note = proof
        row.update(
            decision="promote_exact",
            proof_type="sibling_marker",
            reviewed_to_token=reviewed_to_token,
            direction_basis=direction_basis,
            proof_note=proof_note,
        )
        return row

    proof = same_family_reviewed_text_proof(decision, reviewed_patterns)
    if proof:
        reviewed_to_token, direction_basis, proof_note = proof
        row.update(
            decision="promote_exact",
            proof_type="same_family_reviewed",
            reviewed_to_token=reviewed_to_token,
            direction_basis=direction_basis,
            proof_note=proof_note,
        )
        return row

    if source_image_needed(decision, context_line):
        row.update(
            decision="needs_source_image",
            proof_note="text strongly suggests a marker, but corrected text cannot prove target glyph",
        )
        return row

    row.update(decision="reject_not_marker", proof_note=investigation_reject_note(decision))
    return row


def investigation_sort_key(decision: CandidateDecision) -> tuple[int, int, int, int, int]:
    volume_rank = {volume: index for index, volume in enumerate(VOLUME_ORDER)}
    return (
        -as_int(decision.score),
        volume_rank.get(decision.volume, len(volume_rank)),
        as_int(decision.page),
        as_int(decision.line),
        as_int(decision.token_index),
    )


def select_investigation_candidates(
    deferred: list[CandidateDecision],
    *,
    limit: int,
    min_score: int,
) -> list[CandidateDecision]:
    candidates = [
        row
        for row in deferred
        if row.marker_source in INVESTIGATION_PREFIX_MARKERS
        and as_int(row.score) >= min_score
        and row.source_token
        and row.attached_token
    ]
    selected = sorted(candidates, key=investigation_sort_key)
    return selected[:limit] if limit else selected


def investigation_packet_row(row: dict[str, str], batch_id: str) -> dict[str, str]:
    if row.get("decision") != "promote_exact":
        raise ValueError("investigation row is not marked promote_exact")
    proof_type = row.get("proof_type", "")
    if proof_type not in INVESTIGATION_PROMOTE_PROOF_TYPES:
        raise ValueError(
            "investigation promote_exact row lacks an accepted concrete proof type: "
            f"{proof_type!r}"
        )
    if not row.get("reviewed_to_token", ""):
        raise ValueError("investigation promote_exact row lacks reviewed_to_token")
    if row.get("marker_source") == "/":
        raise ValueError("slash rows are excluded from reference-marker investigation import")
    evidence = f"{EVIDENCE_TAG}:{batch_id}:{proof_type}"
    return {
        "volume": row.get("volume", ""),
        "page": row.get("page", ""),
        "line": row.get("line", ""),
        "token_index": row.get("token_index", ""),
        "from_token": row.get("source_token", ""),
        "to_token": row.get("reviewed_to_token", ""),
        "reason": REFERENCE_MARKER_REASON,
        "evidence": evidence,
        "review_note": f"{TEXT_INVESTIGATION_REVIEW_NOTE} {row.get('proof_note', '')}".strip(),
        "batch_id": batch_id,
        "score": row.get("score", ""),
        "source_diagnostic": row.get("source_diagnostic", ""),
        "candidate_family": row.get("candidate_family", ""),
        "direction_basis": row.get("direction_basis", ""),
        "context_type": row.get("context_type", ""),
        "positive_evidence": row.get("positive_evidence", ""),
        "negative_evidence": row.get("negative_evidence", ""),
    }


def packet_rows_from_investigation(
    rows: list[dict[str, str]],
    batch_id: str,
) -> list[dict[str, str]]:
    packet_rows: list[dict[str, str]] = []
    for row in rows:
        if row.get("decision") != "promote_exact":
            continue
        packet_rows.append(investigation_packet_row(row, batch_id))
    return packet_rows


def promotable_sort_key(decision: CandidateDecision) -> tuple[int, int, int, int, int]:
    volume_rank = {volume: index for index, volume in enumerate(VOLUME_ORDER)}
    return (
        -as_int(decision.score),
        volume_rank.get(decision.volume, len(volume_rank)),
        as_int(decision.page),
        as_int(decision.line),
        as_int(decision.token_index),
    )


def select_promotable(
    decisions: list[CandidateDecision],
    *,
    tier: str,
    limit: int,
    min_score: int,
    max_per_volume: int,
) -> list[CandidateDecision]:
    counts: Counter[str] = Counter()
    selected: list[CandidateDecision] = []
    promotable = [
        row
        for row in decisions
        if row.decision == "promote" and row.tier == tier and as_int(row.score) >= min_score
    ]
    for row in sorted(promotable, key=promotable_sort_key):
        if max_per_volume and counts[row.volume] >= max_per_volume:
            continue
        selected.append(row)
        counts[row.volume] += 1
        if limit and len(selected) >= limit:
            break
    return selected


def append_overrides(path: Path, decisions: list[CandidateDecision]) -> int:
    return batch.append_override_rows(
        path, [override_row_from_decision(decision) for decision in decisions]
    )


def write_deferred_profile(out_dir: Path, deferred: list[CandidateDecision]) -> None:
    fields = [
        "defer_reason",
        "marker_source",
        "candidate_family",
        "attached_token",
        "context_type",
        "lemma_lookup_status",
        "near_vgl",
        "near_headword",
        "near_transliteration",
        "near_tibetan_script",
        "count",
    ]
    counts: Counter[tuple[str, ...]] = Counter(
        (
            row.defer_reason,
            row.marker_source,
            row.candidate_family,
            row.attached_token,
            row.context_type,
            row.lemma_lookup_status,
            row.near_vgl,
            row.near_headword,
            row.near_transliteration,
            row.near_tibetan_script,
        )
        for row in deferred
    )
    rows = [
        {**dict(zip(fields[:-1], key)), "count": str(count)}
        for key, count in counts.most_common()
    ]
    write_tsv(out_dir / "deferred_profile.tsv", rows, fields)


def reference_marker_profile_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    source = row.get("from_token", "")
    target = row.get("to_token", "")
    marker_source = source[0] if source else ""
    if source.startswith("/ "):
        source_pattern = "standalone_slash"
    elif source.startswith("\\ "):
        source_pattern = "standalone_backslash"
    elif marker_source in MARKER_SOURCES:
        source_pattern = f"attached_{marker_source}"
    else:
        source_pattern = "other"
    if target.startswith("↑²"):
        target_pattern = "upward_superscript"
    elif target.startswith("↓²"):
        target_pattern = "downward_superscript"
    elif target.startswith("↑"):
        target_pattern = "upward"
    elif target.startswith("↓"):
        target_pattern = "downward"
    else:
        target_pattern = "other"
    return (
        marker_source,
        source_pattern,
        target[:1],
        target_pattern,
        row.get("reason", ""),
    )


def write_reviewed_reference_marker_profile(root: Path, out_dir: Path) -> None:
    path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
    fields = [
        "marker_source",
        "source_token_pattern",
        "direction",
        "replacement_target_pattern",
        "reason",
        "count",
        "sample_refs",
    ]
    if not path.exists():
        write_tsv(out_dir / "reviewed_reference_marker_feature_profile.tsv", [], fields)
        return

    grouped: dict[tuple[str, str, str, str, str], list[str]] = defaultdict(list)
    for row in read_tsv(path):
        if row.get("reason") != REFERENCE_MARKER_REASON:
            continue
        key = reference_marker_profile_key(row)
        grouped[key].append(
            f"{row.get('volume')} {row.get('page')}:{row.get('line')}:{row.get('token_index')}"
        )
    rows = []
    for key, refs in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        rows.append(
            {
                "marker_source": key[0],
                "source_token_pattern": key[1],
                "direction": key[2],
                "replacement_target_pattern": key[3],
                "reason": key[4],
                "count": str(len(refs)),
                "sample_refs": "; ".join(refs[:8]),
            }
        )
    write_tsv(out_dir / "reviewed_reference_marker_feature_profile.tsv", rows, fields)


def page_band(page: str) -> str:
    try:
        page_number = int(page)
    except ValueError:
        return "unknown"
    start = (page_number // 50) * 50
    return f"{start:04d}-{start + 49:04d}"


def attached_or_referenced_token(source: str, target: str) -> str:
    marker_source, attached = reference_source_parts(source)
    if attached:
        return attached
    parts = target.split(maxsplit=1)
    return parts[1].split()[0] if len(parts) > 1 and parts[1].split() else ""


def promoted_family_row_key(row: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    source = row.get("from_token", "")
    target = row.get("to_token", "")
    marker_source, _attached = reference_source_parts(source)
    if source.startswith("/ "):
        candidate_family = "standalone_slash"
    elif source.startswith("\\ "):
        candidate_family = "standalone_backslash"
    elif marker_source in {"I", "T"}:
        candidate_family = f"attached_{marker_source}"
    else:
        candidate_family = "other"
    direction = target[:1] if target[:1] in {"↑", "↓"} else ""
    return (
        marker_source,
        attached_or_referenced_token(source, target),
        target.split(maxsplit=1)[1].split()[0] if len(target.split(maxsplit=1)) > 1 else target,
        page_band(row.get("page", "")),
        direction,
        candidate_family,
    )


def write_promoted_family_profile(root: Path, out_dir: Path) -> None:
    path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
    fields = [
        "source_prefix",
        "attached_or_referenced_token",
        "target_token",
        "volume_page_band",
        "direction",
        "candidate_family",
        "count",
        "sample_refs",
    ]
    if not path.exists():
        write_tsv(out_dir / "promoted_family_profile.tsv", [], fields)
        return

    grouped: dict[tuple[str, str, str, str, str, str], list[str]] = defaultdict(list)
    for row in read_tsv(path):
        if row.get("reason") != REFERENCE_MARKER_REASON:
            continue
        grouped[promoted_family_row_key(row)].append(
            f"{row.get('volume')} {row.get('page')}:{row.get('line')}:{row.get('token_index')}"
        )

    rows = []
    for key, refs in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        rows.append(
            {
                "source_prefix": key[0],
                "attached_or_referenced_token": key[1],
                "target_token": key[2],
                "volume_page_band": key[3],
                "direction": key[4],
                "candidate_family": key[5],
                "count": str(len(refs)),
                "sample_refs": "; ".join(refs[:8]),
            }
        )
    write_tsv(out_dir / "promoted_family_profile.tsv", rows, fields)


def suggested_target_for(decision: CandidateDecision) -> str:
    if decision.replacement_target:
        return decision.replacement_target
    marker = decision.marker_target
    if marker in {"↑", "↓"} and decision.attached_token:
        return f"{marker} {decision.attached_token}"
    if decision.direction_resolution == "ambiguous_same_direction_up" and decision.attached_token:
        return f"↑ {decision.attached_token}"
    if decision.direction_resolution == "ambiguous_same_direction_down" and decision.attached_token:
        return f"↓ {decision.attached_token}"
    return ""


def near_miss_rows(deferred: list[CandidateDecision], limit: int) -> list[dict[str, str]]:
    if limit <= 0:
        return []

    hard_excludes = {
        "false_positive_control",
        "possible_ldan_not_marker",
        "slash_punctuation_context",
        "ordinary_example_context",
        "superscript_marker_unclear",
    }

    def as_int(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    candidates = [
        row
        for row in deferred
        if row.current_lemma_ordinal
        and row.referenced_lemma_candidate
        and row.exact_occurrence_status == "unique"
        and as_int(row.referenced_lemma_match_count) > 0
        and row.defer_reason not in hard_excludes
    ]
    candidates.sort(
        key=lambda row: (
            row.direction_resolution in {"ambiguous_same_direction_up", "ambiguous_same_direction_down"},
            as_int(row.score),
            as_int(row.referenced_lemma_match_count),
        ),
        reverse=True,
    )
    rows = []
    for decision in candidates[:limit]:
        row = decision_to_row(decision)
        row["suggested_target"] = suggested_target_for(decision)
        rows.append({field: row.get(field, "") for field in NEAR_MISS_FIELDS})
    return rows


def write_near_miss_rows(
    out_dir: Path, deferred: list[CandidateDecision], limit: int
) -> list[dict[str, str]]:
    rows = near_miss_rows(deferred, limit)
    write_tsv(out_dir / "near_miss_rows.tsv", rows, NEAR_MISS_FIELDS)
    return rows


def write_audit(
    out_dir: Path,
    root: Path,
    lemmas: list[Lemma],
    promotable: list[CandidateDecision],
    deferred: list[CandidateDecision],
    false_positive: list[CandidateDecision],
    *,
    applied: int,
    limit: int,
    near_miss_limit: int,
) -> None:
    lemma_fields = [
        "lemma_ordinal",
        "volume",
        "page",
        "line",
        "headword_tibetan",
        "headword_transliteration",
        "normalized_headword_key",
        "source",
    ]
    write_tsv(
        out_dir / "lemma_order.tsv",
        [
            {
                "lemma_ordinal": str(lemma.ordinal),
                "volume": lemma.volume,
                "page": lemma.page,
                "line": lemma.line,
                "headword_tibetan": lemma.headword_tibetan,
                "headword_transliteration": lemma.headword_transliteration,
                "normalized_headword_key": lemma.normalized_key,
                "source": lemma.source,
            }
            for lemma in lemmas
        ],
        lemma_fields,
    )

    decision_fields = list(CandidateDecision.__dataclass_fields__)
    write_tsv(
        out_dir / "tier_a_promotable_rows.tsv",
        [decision_to_row(row) for row in promotable],
        decision_fields,
    )
    write_tsv(
        out_dir / "deferred_rows.tsv",
        [decision_to_row(row) for row in deferred],
        decision_fields,
    )
    write_tsv(
        out_dir / "false_positive_rows.tsv",
        [decision_to_row(row) for row in false_positive],
        decision_fields,
    )
    write_deferred_profile(out_dir, deferred)
    write_reviewed_reference_marker_profile(root, out_dir)
    write_promoted_family_profile(root, out_dir)
    near_misses = write_near_miss_rows(out_dir, deferred, near_miss_limit)

    marker_counts = Counter(row.marker_source for row in promotable)
    direction_counts = Counter(row.marker_target for row in promotable)
    defer_counts = Counter(row.defer_reason for row in deferred)
    defer_profile_counts: Counter[tuple[str, str, str, str]] = Counter(
        (
            row.defer_reason,
            row.marker_source,
            row.context_type,
            row.lemma_lookup_status,
        )
        for row in deferred
    )
    summary = [
        "# Reference Marker Lemma-Order Promotion Summary",
        "",
        f"- Lemmas indexed: {len(lemmas)}",
        f"- Tier A promotable rows written: {len(promotable)}",
        f"- Apply limit: {limit}",
        f"- Exact rows applied: {applied}",
        f"- Deferred rows: {len(deferred)}",
        f"- False-positive/control rows: {len(false_positive)}",
        f"- Near-miss rows written: {len(near_misses)}",
        "",
        "## Promotable Marker Sources",
        "",
    ]
    for source, count in sorted(marker_counts.items()):
        summary.append(f"- `{source}`: {count}")
    summary.extend(["", "## Promotable Directions", ""])
    for target, count in sorted(direction_counts.items()):
        summary.append(f"- `{target}`: {count}")
    summary.extend(["", "## Top Defer Reasons", ""])
    for reason, count in defer_counts.most_common(12):
        summary.append(f"- `{reason}`: {count}")
    summary.extend(["", "## Top Deferred Profiles", ""])
    for (reason, source, kind, lookup), count in defer_profile_counts.most_common(12):
        summary.append(
            f"- `{reason}` / source `{source}` / `{kind}` / lookup `{lookup}`: {count}"
        )
    (out_dir / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    batch_id = args.batch_id or f"reference_marker_{timestamp}"
    out_dir = Path(args.work_dir) if args.work_dir else root / "work" / f"reference_marker_promotion_{timestamp}"

    line_zones, lemma_by_entry, lemma_index, lemmas = load_line_zones(root)
    release_lines = load_release_lines(root)
    rows = load_reference_marker_rows(root)
    promoted_patterns = load_promoted_reference_marker_patterns(root)
    reviewed_patterns = load_reviewed_reference_marker_details(root)
    decisions = [
        decide_candidate(
            row,
            line_zones,
            lemma_by_entry,
            lemma_index,
            release_lines,
            promoted_patterns=promoted_patterns,
        )
        for row in rows
    ]
    promotable_all = sorted(
        [
            row
            for row in decisions
            if row.decision == "promote"
            and row.tier == args.tier
            and as_int(row.score) >= args.min_score
        ],
        key=promotable_sort_key,
    )
    selected = select_promotable(
        decisions,
        tier=args.tier,
        limit=args.limit,
        min_score=args.min_score,
        max_per_volume=args.max_per_volume,
    )
    deferred = [row for row in decisions if row.decision == "defer"]
    false_positive = [row for row in decisions if row.decision == "false_positive"]
    packet_rows = [packet_row_from_decision(decision, batch_id) for decision in selected]
    packet_min_score = args.min_score

    investigation_rows: list[dict[str, str]] = []
    investigation_packet_rows: list[dict[str, str]] = []
    if args.write_investigation_packet:
        investigation_candidates = select_investigation_candidates(
            deferred,
            limit=args.investigation_limit,
            min_score=args.investigation_min_score,
        )
        investigation_rows = [
            investigate_decision(decision, release_lines, reviewed_patterns, batch_id)
            for decision in investigation_candidates
        ]
        investigation_packet_rows = packet_rows_from_investigation(investigation_rows, batch_id)
        write_tsv(
            Path(args.write_investigation_packet),
            investigation_rows,
            INVESTIGATION_FIELDS,
        )
        if args.include_investigation_promotions and not packet_rows:
            packet_rows = investigation_packet_rows
            packet_min_score = min(args.min_score, args.investigation_min_score)

    applied = 0
    applied_from_packet = ""
    override_path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
    if args.write_packet:
        packet_path = Path(args.write_packet)
        batch.validate_packet_rows(
            root,
            packet_rows,
            override_path=override_path,
            expected_reason=REFERENCE_MARKER_REASON,
            min_score=packet_min_score,
        )
        batch.write_packet(packet_path, packet_rows)
    if args.apply:
        rows_to_apply = packet_rows
        if args.apply_packet:
            packet_path = Path(args.apply_packet)
            rows_to_apply = batch.load_packet(packet_path)
            applied_from_packet = str(packet_path)
            if rows_to_apply and rows_to_apply[0].get("batch_id"):
                batch_id = rows_to_apply[0]["batch_id"]
        apply_min_score = args.min_score
        if any(
            row.get("evidence", "").split(":")[-1] in INVESTIGATION_PROMOTE_PROOF_TYPES
            for row in rows_to_apply
        ):
            apply_min_score = min(args.min_score, args.investigation_min_score)
        batch.validate_packet_rows(
            root,
            rows_to_apply,
            override_path=override_path,
            expected_reason=REFERENCE_MARKER_REASON,
            min_score=apply_min_score,
        )
        applied = batch.append_override_rows(override_path, rows_to_apply)

    write_audit(
        out_dir,
        root,
        lemmas,
        selected,
        deferred,
        false_positive,
        applied=applied,
        limit=args.limit,
        near_miss_limit=args.show_near_misses,
    )

    print(f"audit_dir={out_dir}")
    print(f"batch_id={batch_id}")
    print(f"lemmas_indexed={len(lemmas)}")
    print(f"tier_a_total={len(promotable_all)}")
    print(f"tier_a_selected={len(selected)}")
    print(f"deferred={len(deferred)}")
    print(f"false_positive={len(false_positive)}")
    if args.write_packet:
        print(f"packet_path={Path(args.write_packet)}")
    if args.write_investigation_packet:
        investigation_counts = Counter(row.get("decision", "") for row in investigation_rows)
        proof_counts = Counter(row.get("proof_type", "") for row in investigation_rows if row.get("proof_type", ""))
        print(f"investigation_packet_path={Path(args.write_investigation_packet)}")
        print(f"investigation_rows={len(investigation_rows)}")
        print(f"investigation_promote_exact={investigation_counts.get('promote_exact', 0)}")
        print(f"investigation_reject_not_marker={investigation_counts.get('reject_not_marker', 0)}")
        print(f"investigation_needs_source_image={investigation_counts.get('needs_source_image', 0)}")
        for proof_type, count in sorted(proof_counts.items()):
            print(f"investigation_proof_{proof_type}={count}")
    if applied_from_packet:
        print(f"applied_from_packet={applied_from_packet}")
    print(f"applied={applied}")
    for source, count in sorted(Counter(row.marker_source for row in selected).items()):
        print(f"selected_source_{source}={count}")
    for target, count in sorted(Counter(row.marker_target for row in selected).items()):
        print(f"selected_target_{target}={count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Promote exact reference-marker rows using empirical lemma order."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--tier", default="A", choices=["A"])
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--min-score", type=int, default=100)
    parser.add_argument(
        "--max-per-volume",
        type=int,
        default=0,
        help="Maximum selected rows per volume; 0 means no per-volume cap.",
    )
    parser.add_argument("--batch-id", default="")
    parser.add_argument(
        "--write-packet",
        default="",
        help="Write selected exact override rows and review metadata to this TSV.",
    )
    parser.add_argument(
        "--apply-packet",
        default="",
        help="Apply exact override rows from a previously emitted packet TSV.",
    )
    parser.add_argument(
        "--write-investigation-packet",
        default="",
        help=(
            "Write bounded deferred-row investigation results to this TSV; "
            "promote_exact rows require a concrete text proof."
        ),
    )
    parser.add_argument(
        "--investigation-limit",
        type=int,
        default=25,
        help="Maximum deferred prefix rows to investigate; 0 means no limit.",
    )
    parser.add_argument(
        "--investigation-min-score",
        type=int,
        default=70,
        help="Minimum score for bounded deferred prefix investigation.",
    )
    parser.add_argument(
        "--include-investigation-promotions",
        action="store_true",
        help=(
            "When no Tier A rows are selected, write promote_exact investigation "
            "rows to --write-packet."
        ),
    )
    parser.add_argument(
        "--direction-from-lemma-order",
        action="store_true",
        help="Direction comes from empirical lemma order; accepted for explicit CLI clarity.",
    )
    parser.add_argument("--root", default="")
    parser.add_argument("--work-dir", default="")
    parser.add_argument(
        "--profile-deferred",
        action="store_true",
        help="Accepted for explicit CLI clarity; deferred profiles are always written.",
    )
    parser.add_argument(
        "--show-near-misses",
        type=int,
        default=0,
        help="Write up to N high-scoring deferred near misses to near_miss_rows.tsv.",
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
