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
    r"\b(vgl|Lex|unter|s\.|cf)\.|\b(v|V)\.\s|[=~]",
    re.IGNORECASE,
)
BAD_CONTEXT_RE = re.compile(
    r"\b(?:Skt|Sanskrit|Indien|International|Inhalt|Ich|Ingwer)\b"
)


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
    direction_basis: str
    replacement_target: str
    candidate_family: str
    context_excerpt: str
    decision: str
    defer_reason: str
    decision_notes: str


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


def lookup_variants(token: str) -> list[str]:
    variants = {normalize_key(token)}
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
            variants.add(normalize_key(f"{token[: -len(src)]}{dst}"))
    return sorted(variants)


def phrase_lookup_variants(tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    variants = lookup_variants(tokens[0])
    for token in tokens[1:]:
        token_variants = lookup_variants(token)
        variants = [f"{prefix} {suffix}" for prefix in variants for suffix in token_variants]
    return sorted(set(variants))


def release_volumes(root: Path) -> Iterable[str]:
    for volume in VOLUME_ORDER:
        if (root / "release" / "current" / "text" / f"{volume}_corrected_full.txt").exists():
            yield volume


def load_line_zones(
    root: Path,
) -> tuple[dict[tuple[str, str, str], dict[str, str]], dict[tuple[str, str], Lemma], dict[str, list[Lemma]], list[Lemma]]:
    by_line: dict[tuple[str, str, str], dict[str, str]] = {}
    lemma_by_entry: dict[tuple[str, str], Lemma] = {}
    lemma_index: dict[str, list[Lemma]] = defaultdict(list)
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
            lemma_index[key].append(lemma)
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
        if any(candidate == source_token for candidate, _start, _end in candidates):
            occurrences.append(index)
    if len(occurrences) == 1:
        return occurrences[0], "unique"
    if not occurrences:
        return None, "not_found"
    return None, "ambiguous"


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
    tokens: list[str], lemma_index: dict[str, list[Lemma]]
) -> tuple[str, str, Lemma | None, str]:
    ambiguous_candidate = ""
    for length in range(min(6, len(tokens)), 0, -1):
        phrase_tokens = tokens[:length]
        phrase = " ".join(phrase_tokens)
        matched: dict[int, Lemma] = {}
        for key in phrase_lookup_variants(phrase_tokens):
            for lemma in lemma_index.get(key, []):
                matched[lemma.ordinal] = lemma
        if len(matched) == 1:
            lemma = next(iter(matched.values()))
            return phrase, lemma.headword_transliteration, lemma, "unique_match"
        if len(matched) > 1:
            ambiguous_candidate = phrase
    if ambiguous_candidate:
        return ambiguous_candidate, "", None, "ambiguous_match"
    return " ".join(tokens[: min(6, len(tokens))]), "", None, "no_match"


def context_is_reference_like(row: dict[str, str]) -> bool:
    context = row.get("context_excerpt", "")
    if row.get("near_vgl") == "1" or REFERENCE_CONTEXT_RE.search(context):
        return True
    if row.get("near_headword") == "1" and row.get("near_transliteration") == "1":
        return True
    if row.get("candidate_family", "").startswith("ocr_prefix_") and row.get("confidence") == "high":
        return True
    return False


def looks_like_ldan_not_marker(source_token: str, attached_token: str, context: str) -> bool:
    if not source_token.startswith("I"):
        return False
    if normalize_key(attached_token).startswith("dan"):
        return True
    return bool(re.search(r"[A-Za-zÀ-ÿĀ-ž]-Idan\b", context))


def looks_like_slash_punctuation(row: dict[str, str], split_kind: str) -> bool:
    if row.get("source_token") != "/" and not row.get("source_token", "").startswith("/"):
        return False
    context = row.get("context_excerpt", "")
    if split_kind == "standalone":
        return True
    if not context_is_reference_like(row):
        return True
    return context.count("/") >= 2 and not row.get("near_vgl") == "1"


def first_replacement_token(source_attached: str, referenced_lemma: str) -> str:
    if not referenced_lemma:
        return source_attached
    first = referenced_lemma.split()[0]
    return first or source_attached


def decide_candidate(
    row: dict[str, str],
    line_zones: dict[tuple[str, str, str], dict[str, str]],
    lemma_by_entry: dict[tuple[str, str], Lemma],
    lemma_index: dict[str, list[Lemma]],
    release_lines: dict[tuple[str, str, str], str],
) -> CandidateDecision:
    volume = row["volume"]
    page = row["page"]
    line_no = row["line"]
    line = release_lines.get((volume, page, line_no), "")
    source_token = row.get("source_token", "")
    marker_source, attached_token, split_kind = split_marker(row)
    context = row.get("context_excerpt", "")
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
        "direction_basis": "",
        "replacement_target": "",
        "candidate_family": row.get("candidate_family", ""),
        "context_excerpt": context,
        "decision": "defer",
        "defer_reason": "",
        "decision_notes": "",
    }

    def finish(**updates: str) -> CandidateDecision:
        values = {**base, **updates}
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
        return finish(defer_reason="false_positive_control", decision_notes="No promotable marker source.")
    if BAD_CONTEXT_RE.search(context):
        return finish(defer_reason="false_positive_control", decision_notes="Control/prose context.")
    if looks_like_ldan_not_marker(source_token, attached_token, context):
        return finish(
            defer_reason="possible_ldan_not_marker",
            decision_notes="I appears to belong to ldan-like compound damage, not a reference marker.",
        )
    if looks_like_slash_punctuation(row, split_kind):
        return finish(
            defer_reason="slash_punctuation_context",
            decision_notes="Slash context is not strong enough for exact marker promotion.",
        )

    token_index, token_status = line_occurrence_for_source(source_token, line)
    if token_index is None:
        return finish(
            defer_reason=f"exact_source_token_{token_status}",
            decision_notes="Could not identify a unique exact token occurrence in the release line.",
        )

    current = current_lemma_for(row, line_zones, lemma_by_entry)
    if current is None:
        return finish(
            token_index=str(token_index),
            defer_reason="unknown_current_lemma",
            decision_notes="Line-zone metadata does not identify the current lemma.",
        )

    tokens = transliteration_tokens_after_source(source_token, attached_token, line, split_kind)
    if not tokens:
        return finish(
            token_index=str(token_index),
            current_lemma=current.headword_transliteration,
            current_lemma_ordinal=str(current.ordinal),
            current_lemma_ref=current.ref,
            defer_reason="no_referenced_lemma_match",
            decision_notes="No Tibetan transliteration candidate found to the right of the marker.",
        )

    phrase, referenced_text, referenced, lookup_status = lookup_longest_unique(tokens, lemma_index)
    common = {
        "token_index": str(token_index),
        "current_lemma": current.headword_transliteration,
        "current_lemma_ordinal": str(current.ordinal),
        "current_lemma_ref": current.ref,
        "referenced_lemma_candidate": phrase,
        "referenced_lemma": referenced_text,
        "lemma_lookup_status": lookup_status,
    }
    if referenced is None:
        reason = (
            "ambiguous_referenced_lemma"
            if lookup_status == "ambiguous_match"
            else "no_referenced_lemma_match"
        )
        return finish(
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
        return finish(
            **common,
            defer_reason="same_lemma",
            decision_notes="Referenced lemma resolves to the current lemma.",
        )
    if not context_is_reference_like(row):
        return finish(
            **common,
            defer_reason="ordinary_example_context",
            decision_notes="Lemma match exists, but context is not clearly reference-like.",
        )

    marker_target = "↑" if referenced.ordinal < current.ordinal else "↓"
    replacement_first_token = first_replacement_token(attached_token, referenced.headword_transliteration)
    return finish(
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


def write_audit(
    out_dir: Path,
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

    decision_fields = [
        "volume",
        "page",
        "line",
        "diagnostic_token_index",
        "token_index",
        "source_token",
        "marker_source",
        "marker_target",
        "attached_token",
        "current_lemma",
        "current_lemma_ordinal",
        "current_lemma_ref",
        "referenced_lemma_candidate",
        "referenced_lemma",
        "referenced_lemma_ordinal",
        "referenced_lemma_ref",
        "lemma_lookup_status",
        "direction_basis",
        "replacement_target",
        "candidate_family",
        "context_excerpt",
        "decision_notes",
    ]
    write_tsv(
        out_dir / "tier_a_promotable_rows.tsv",
        [decision_to_row(row) for row in promotable],
        decision_fields,
    )
    deferred_fields = decision_fields + ["defer_reason"]
    write_tsv(
        out_dir / "deferred_rows.tsv",
        [decision_to_row(row) for row in deferred],
        deferred_fields,
    )
    write_tsv(
        out_dir / "false_positive_rows.tsv",
        [decision_to_row(row) for row in false_positive],
        deferred_fields,
    )

    marker_counts = Counter(row.marker_source for row in promotable)
    direction_counts = Counter(row.marker_target for row in promotable)
    defer_counts = Counter(row.defer_reason for row in deferred)
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

    write_audit(out_dir, lemmas, selected, deferred, false_positive, applied=applied, limit=args.limit)

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
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
