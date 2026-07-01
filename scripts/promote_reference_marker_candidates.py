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
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


VOLUME_ORDER = ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m")
MARKER_SOURCES = {"I", "T", "/", "\\"}
REFERENCE_MARKER_REASON = "reviewed_tibetan_exact_reference_marker"
EVIDENCE_TAG = "reference_marker_lemma_order_20260701"
REVIEW_NOTE = (
    "Exact page-line-token reference-marker correction from lemma-order "
    "promotion; direction from current/referenced lemma ordinal; no broad "
    "marker, slash, Initial-I/l, or nasal rule."
)

TOKEN_RE = re.compile(
    r"[0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňıß$]+"
    r"(?:['’.$-][0-9A-Za-zÀ-ÖØ-öø-ÿĀāĪīŪūṄṅÑñŚśŹźḌḍṬṭṢṣḤḥṚṛḶḷČčŽžŠšŃńǸǹŇňıß$]+)*"
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
    "ambiguous_referenced_lemma",
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
    lemma_lookup_status: str
    referenced_lemma_lookup_key: str
    referenced_lemma_alias_matched: str
    lemma_alias_basis: str
    exact_occurrence_status: str
    context_type: str
    direction_basis: str
    replacement_target: str
    candidate_family: str
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


def line_occurrence_for_source(source_token: str, line: str) -> tuple[int | None, str]:
    matches = list(TOKEN_RE.finditer(line))
    occurrences: list[int] = []

    def prefix_has_left_boundary(prefix_start: int) -> bool:
        if prefix_start <= 0:
            return True
        previous = line[prefix_start - 1]
        return not (previous.isalpha() or previous.isdigit() or previous in {"'", "’", "-", "_"})

    def append_standalone_marker_options(
        candidates: list[tuple[str, int, int]],
        token_start: int,
    ) -> None:
        whitespace_start = token_start
        while whitespace_start > 0 and line[whitespace_start - 1].isspace():
            whitespace_start -= 1
        if whitespace_start == token_start or whitespace_start <= 0:
            return
        prefix_start = whitespace_start - 1
        if line[prefix_start] not in {"/", "\\"} or not prefix_has_left_boundary(prefix_start):
            return
        for _candidate, _candidate_start, candidate_end in list(candidates):
            candidates.append((line[prefix_start:candidate_end], prefix_start, candidate_end))

    for index, match in enumerate(matches, start=1):
        token = match.group(0)
        start = match.start()
        end = match.end()
        candidates = [(token, start, end)]
        for suffix in TRAILING_SUFFIXES:
            if line[end : end + len(suffix)] == suffix:
                candidates.append((f"{token}{suffix}", start, end + len(suffix)))
        if start > 0 and line[start - 1] in {"/", "\\"} and prefix_has_left_boundary(start - 1):
            for candidate, candidate_start, candidate_end in list(candidates):
                candidates.append((f"{line[start - 1]}{candidate}", candidate_start - 1, candidate_end))
        append_standalone_marker_options(candidates, start)
        if any(candidate == source_token for candidate, _start, _end in candidates):
            occurrences.append(index)
    if len(occurrences) == 1:
        return occurrences[0], "unique"
    if not occurrences:
        return None, "not_found"
    return None, "ambiguous"


def exact_source_for_marker_occurrence(
    source_token: str, marker_source: str, attached_token: str, line: str, split_kind: str
) -> str:
    if split_kind != "standalone" or marker_source not in {"/", "\\"} or not attached_token:
        return source_token

    attached_key = normalize_key(attached_token)
    matches: list[str] = []
    for match in TOKEN_RE.finditer(line):
        if normalize_key(match.group(0)) != attached_key:
            continue
        whitespace_start = match.start()
        while whitespace_start > 0 and line[whitespace_start - 1].isspace():
            whitespace_start -= 1
        if whitespace_start == match.start() or whitespace_start <= 0:
            continue
        prefix_start = whitespace_start - 1
        if line[prefix_start] == marker_source:
            matches.append(line[prefix_start : match.end()])
    unique = sorted(set(matches))
    return unique[0] if len(unique) == 1 else source_token


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
    ambiguous: LookupResult | None = None
    unique_matches: list[tuple[int, str, str, str, LemmaAlias]] = []
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
        if len(matched) == 1:
            key, variant_basis, alias = next(iter(matched.values()))
            unique_matches.append((length, phrase, key, variant_basis, alias))
        if len(matched) > 1:
            key, variant_basis, alias = next(iter(matched.values()))
            ambiguous = LookupResult(
                candidate=phrase,
                lookup_key=key,
                alias_matched=alias.alias,
                alias_basis=f"{variant_basis}|{alias.basis}",
                lemma=None,
                status="ambiguous_match",
            )

    if unique_matches:
        chosen = unique_matches[0]
        chosen_alias = chosen[4]
        for _length, phrase, key, variant_basis, alias in unique_matches[1:]:
            if alias.lemma.ordinal != chosen_alias.lemma.ordinal:
                return LookupResult(
                    candidate=chosen[1],
                    lookup_key=chosen[2],
                    alias_matched=chosen_alias.alias,
                    alias_basis=f"{chosen[3]}|{chosen_alias.basis}; conflicts_with:{phrase}",
                    lemma=None,
                    status="ambiguous_match",
                )
        return LookupResult(
            candidate=chosen[1],
            lookup_key=chosen[2],
            alias_matched=chosen_alias.alias,
            alias_basis=f"{chosen[3]}|{chosen_alias.basis}",
            lemma=chosen_alias.lemma,
            status="unique_match",
        )

    if ambiguous is not None:
        return ambiguous
    return LookupResult(
        candidate=" ".join(tokens[: min(6, len(tokens))]),
        lookup_key="",
        alias_matched="",
        alias_basis="",
        lemma=None,
        status="no_match",
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
    if row.get("source_token") == "/" and context.count("/") >= 2:
        return "slash_running_example_context"
    if split_kind == "standalone" and row.get("source_token") == "/":
        return "slash_standalone_uncued_context"
    return "ordinary_context"


def context_is_reference_like(row: dict[str, str], kind: str = "") -> bool:
    if kind in {
        "reference_cue",
        "near_actual_marker_control",
        "headword_transliteration_context",
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
    if context.count("/") >= 2:
        return False
    if kind == "near_actual_marker_control":
        return True
    if kind != "reference_cue":
        return False
    return bool(STRONG_SLASH_CONTEXT_RE.search(context))


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
    if context.count("/") >= 2:
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
) -> tuple[int, str, str]:
    score = 0
    positive: list[str] = []
    negative: list[str] = []
    if lookup_status == "unique_match":
        score += 50
        positive.append("unique_referenced_lemma_match")
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

    if hard_negative:
        penalty = {
            "possible_ldan_not_marker": 50,
            "slash_punctuation_context": 40,
            "false_positive_control": 40,
            "ambiguous_referenced_lemma": 30,
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


def decide_candidate(
    row: dict[str, str],
    line_zones: dict[tuple[str, str, str], dict[str, str]],
    lemma_by_entry: dict[tuple[str, str], Lemma],
    lemma_index: dict[str, list[LemmaAlias]],
    release_lines: dict[tuple[str, str, str], str],
) -> CandidateDecision:
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
        "lemma_lookup_status": "",
        "referenced_lemma_lookup_key": "",
        "referenced_lemma_alias_matched": "",
        "lemma_alias_basis": "",
        "exact_occurrence_status": "",
        "context_type": kind,
        "direction_basis": "",
        "replacement_target": "",
        "candidate_family": row.get("candidate_family", ""),
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

    tokens = transliteration_tokens_after_source(source_token, attached_token, line, split_kind)
    exact_source_token = exact_source_for_marker_occurrence(
        source_token, marker_source, attached_token or (tokens[0] if tokens else ""), line, split_kind
    )
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
    }
    if referenced is None:
        reason = (
            "ambiguous_referenced_lemma"
            if lookup.status == "ambiguous_match"
            else "no_referenced_lemma_match"
        )
        return finish_with_score(
            **common,
            defer_reason=reason,
            decision_notes="Referenced lemma lookup did not yield a unique match.",
        )
    common.update(
        {
            "referenced_lemma_ordinal": str(referenced.ordinal),
            "referenced_lemma_ref": referenced.ref,
        }
    )
    if referenced.ordinal == current.ordinal:
        return finish_with_score(
            **common,
            defer_reason="same_lemma",
            decision_notes="Referenced lemma resolves to the current lemma.",
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

    marker_target = "↑" if referenced.ordinal < current.ordinal else "↓"
    replacement_first_token = first_replacement_token(attached_token, referenced.headword_transliteration)
    return finish_with_score(
        **common,
        marker_target=marker_target,
        replacement_target=f"{marker_target} {replacement_first_token}",
        direction_basis=f"{referenced.ordinal} {'<' if referenced.ordinal < current.ordinal else '>'} {current.ordinal}",
        decision="promote",
        decision_notes=(
            "Tier A: unique referenced lemma and known current lemma; marker "
            "direction chosen from empirical lemma order."
        ),
    )


def decision_to_row(decision: CandidateDecision) -> dict[str, str]:
    return decision.__dict__.copy()


def load_existing_overrides(path: Path) -> tuple[list[dict[str, str]], set[tuple[str, str, str, str, str]]]:
    rows = read_tsv(path)
    keys = {
        (
            row["volume"],
            row["page"],
            row["line"],
            row["token_index"],
            row["from_token"],
        )
        for row in rows
    }
    return rows, keys


def append_overrides(path: Path, decisions: list[CandidateDecision]) -> int:
    rows, existing = load_existing_overrides(path)
    added = 0
    for decision in decisions:
        key = (
            decision.volume,
            decision.page,
            decision.line,
            decision.token_index,
            decision.source_token,
        )
        if key in existing:
            continue
        rows.append(
            {
                "volume": decision.volume,
                "page": decision.page,
                "line": decision.line,
                "token_index": decision.token_index,
                "from_token": decision.source_token,
                "to_token": decision.replacement_target,
                "reason": REFERENCE_MARKER_REASON,
                "evidence": EVIDENCE_TAG,
                "review_note": REVIEW_NOTE,
            }
        )
        existing.add(key)
        added += 1
    fields = [
        "volume",
        "page",
        "line",
        "token_index",
        "from_token",
        "to_token",
        "reason",
        "evidence",
        "review_note",
    ]
    write_tsv(path, rows, fields)
    return added


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
    out_dir = Path(args.work_dir) if args.work_dir else root / "work" / f"reference_marker_promotion_{timestamp}"

    line_zones, lemma_by_entry, lemma_index, lemmas = load_line_zones(root)
    release_lines = load_release_lines(root)
    rows = load_reference_marker_rows(root)
    decisions = [
        decide_candidate(row, line_zones, lemma_by_entry, lemma_index, release_lines)
        for row in rows
    ]
    promotable_all = [row for row in decisions if row.decision == "promote"]
    selected = promotable_all[: args.limit] if args.limit else promotable_all
    deferred = [row for row in decisions if row.decision == "defer"]
    false_positive = [row for row in decisions if row.decision == "false_positive"]

    applied = 0
    if args.apply:
        override_path = root / "data" / "reviewed_tibetan_exact_overrides.tsv"
        applied = append_overrides(override_path, selected)

    write_audit(out_dir, root, lemmas, selected, deferred, false_positive, applied=applied, limit=args.limit)

    print(f"audit_dir={out_dir}")
    print(f"lemmas_indexed={len(lemmas)}")
    print(f"tier_a_total={len(promotable_all)}")
    print(f"tier_a_selected={len(selected)}")
    print(f"deferred={len(deferred)}")
    print(f"false_positive={len(false_positive)}")
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
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
