#!/usr/bin/env python3
"""Build the current OCR status page and correction-family ledger.

This script intentionally reads only tracked repository artifacts.  It does
not inspect ignored ``work/`` outputs and it does not change correction
behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release" / "current"
QA_ROOT = RELEASE / "qa"
STATUS_PATH = ROOT / "docs" / "STATUS.md"
FAMILIES_PATH = ROOT / "data" / "correction_families.tsv"

VOLUME_ORDER = ["wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"]
TSV_COLUMNS = [
    "family_id",
    "category",
    "from_pattern_or_token",
    "to_pattern_or_token",
    "scope",
    "status",
    "volumes_applied",
    "reason_codes",
    "implementation_location",
    "evidence_doc",
    "applied_count_current_release",
    "residual_count_current_release",
    "negative_controls",
    "notes",
]
ALLOWED_STATUSES = {
    "applied",
    "partially_applied",
    "deferred",
    "unsafe_broad_rule",
    "false_positive_or_noise",
    "needs_source_check",
    "promote_candidate",
    "diagnostic_only",
    "historical_only",
}
HISTORICAL_NOTE = (
    "> Historical audit record. This file is not the current to-do list. "
    "See `docs/STATUS.md` for the current operational status."
)
REQUIRED_QA_FILES = [
    "{volume}_summary.json",
    "{volume}_changes.tsv",
    "bucket_report.summary.md",
    "bucket_report.artifact_tokens.tsv",
]


@dataclass
class ReleaseStats:
    manifest_generated_utc: str
    manifest_source_commit: str
    manifest_volumes: list[str]
    volumes: dict[str, dict[str, int | str]]
    reason_counts: Counter[str]
    pair_counts: Counter[tuple[str, str]]
    pair_volumes: dict[tuple[str, str], set[str]]
    residual_tokens: Counter[str]
    residual_buckets: Counter[str]


def as_int(value: str | int | None) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    value = str(value).strip().strip("`")
    if not value:
        return 0
    return int(value.replace(",", ""))


def parse_manifest() -> tuple[str, str, list[str]]:
    manifest = RELEASE / "manifest.md"
    text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
    generated = "unknown"
    source_commit = "unknown"
    manifest_volumes: list[str] = []
    m = re.search(r"Generated UTC:\s*`([^`]+)`", text)
    if m:
        generated = m.group(1)
    m = re.search(r"Source/code commit observed while building this bundle:\s*`([^`]+)`", text)
    if m:
        source_commit = m.group(1)
    in_source_outputs = False
    for line in text.splitlines():
        if line == "## Source Outputs":
            in_source_outputs = True
            continue
        if in_source_outputs and line.startswith("## "):
            break
        m = re.match(r"\| `([^`]+)` \| `", line)
        if m and m.group(1).startswith("wts_"):
            manifest_volumes.append(m.group(1))
    if not manifest_volumes:
        text_dir = RELEASE / "text"
        manifest_volumes = sorted(
            path.name.removesuffix("_corrected_full.txt")
            for path in text_dir.glob("*_corrected_full.txt")
        )
    return generated, source_commit, manifest_volumes


def parse_bucket_summary(path: Path) -> dict[str, int]:
    out = {
        "bucket_unresolved_pairs": 0,
        "bucket_promote_rows": 0,
        "bucket_hold_rows": 0,
    }
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8")
    patterns = {
        "bucket_unresolved_pairs": r"unresolved confusable pairs:\s*`?([0-9,]+)`?",
        "bucket_promote_rows": r"promote candidates \(conservative\):\s*`?([0-9,]+)`?",
        "bucket_hold_rows": r"hold candidates:\s*`?([0-9,]+)`?",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = as_int(m.group(1))
    return out


def iter_tsv(path: Path) -> Iterable[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        yield from csv.DictReader(fh, delimiter="\t")


def tsv_row_count(path: Path) -> int:
    return sum(1 for _ in iter_tsv(path))


def diagnostic_variant_family_count(path: Path, family: str, source_token: str) -> int:
    total_count = 0
    for row in iter_tsv(path):
        if (row.get("candidate_family") or "").strip() != family:
            continue
        source_tokens = (row.get("source_tokens") or "").strip()
        if source_tokens == source_token or source_tokens.startswith(f"{source_token} "):
            total_count += as_int(row.get("occurrence_count"))
    return total_count


def dngos_exact_orthography_count(path: Path) -> int:
    return sum(
        1
        for row in iter_tsv(path)
        if (row.get("candidate_family") or "").strip() == "dngos_family"
        and (row.get("token") or "").strip() == "dnos"
        and (row.get("proposed_target") or "").strip() == "dṅos"
    )


def dngos_google_witness_count(path: Path, reason: str | None = None) -> int:
    count = 0
    for row in iter_tsv(path):
        if (row.get("candidate_family") or "").strip() != "dngos_family":
            continue
        if (row.get("base_token") or "").strip() != "dnos":
            continue
        if (row.get("proposed_target") or "").strip() != "dṅos":
            continue
        if reason is not None and (row.get("reason") or "").strip() != reason:
            continue
        count += 1
    return count


def read_release_stats() -> ReleaseStats:
    generated, source_commit, manifest_volumes = parse_manifest()
    volumes: dict[str, dict[str, int | str]] = {}
    reason_counts: Counter[str] = Counter()
    pair_counts: Counter[tuple[str, str]] = Counter()
    pair_volumes: dict[tuple[str, str], set[str]] = defaultdict(set)
    residual_tokens: Counter[str] = Counter()
    residual_buckets: Counter[str] = Counter()

    for volume in VOLUME_ORDER:
        vol_dir = QA_ROOT / volume
        summary_path = vol_dir / f"{volume}_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        bucket_counts = parse_bucket_summary(vol_dir / "bucket_report.summary.md")
        change_rows = 0
        changes_path = vol_dir / f"{volume}_changes.tsv"
        for row in iter_tsv(changes_path):
            if str(row.get("applied", "1")).strip() in {"0", "false", "False"}:
                continue
            change_rows += 1
            reason = (row.get("reason") or "").strip()
            if reason:
                reason_counts[reason] += 1
            from_token = (row.get("from_token") or "").strip()
            to_token = (row.get("to_token") or "").strip()
            if from_token or to_token:
                pair = (from_token, to_token)
                pair_counts[pair] += 1
                pair_volumes[pair].add(volume)

        artifact_path = vol_dir / "bucket_report.artifact_tokens.tsv"
        for row in iter_tsv(artifact_path):
            token = (row.get("token") or "").strip()
            bucket = (row.get("bucket") or "").split(":", 1)[-1]
            count = as_int(row.get("count"))
            if token:
                residual_tokens[token] += count
            if bucket:
                residual_buckets[bucket] += count

        diagnostic_dir = vol_dir / "tibetan_cleanup_diagnostics"
        diagnostic_counts = {
            "initial_i_exact_residual_candidates": tsv_row_count(
                diagnostic_dir / "tibetan_initial_i_residual_candidates.tsv"
            ),
            "script_ng_witness_candidates": tsv_row_count(
                diagnostic_dir / "tibetan_script_ng_witness_candidates.tsv"
            ),
            "reference_marker_candidates": tsv_row_count(diagnostic_dir / "reference_marker_candidates.tsv"),
            "sanskrit_low_confidence_candidates": tsv_row_count(
                diagnostic_dir / "residual_sanskrit_low_confidence_candidates.tsv"
            ),
            "sigla_variant_candidates": tsv_row_count(diagnostic_dir / "sigla_variant_candidates.tsv"),
            "dngos_family_dnos_candidates": diagnostic_variant_family_count(
                diagnostic_dir / "tibetan_variant_families.tsv",
                "dngos_family",
                "dnos",
            ),
            "dngos_family_exact_orthography_candidates": dngos_exact_orthography_count(
                diagnostic_dir / "tibetan_orthography_damage_candidates.tsv"
            ),
            "dngos_family_google_witness_candidates": dngos_google_witness_count(
                diagnostic_dir / "tibetan_google_candidate_readings.tsv"
            ),
            "dngos_family_blocked_wrong_nasal_witness": dngos_google_witness_count(
                diagnostic_dir / "tibetan_google_candidate_readings.tsv",
                "blocked_alternate_witness_wrong_nasal_dnos",
            ),
        }
        diagnostic_counts["dngos_family_context_diagnostic_candidates"] = (
            diagnostic_counts["dngos_family_google_witness_candidates"]
            - diagnostic_counts["dngos_family_blocked_wrong_nasal_witness"]
        )

        volumes[volume] = {
            "entries": as_int(summary.get("entries_detected")),
            "non_empty_lines": as_int(summary.get("non_empty_lines")),
            "validator_issues": as_int(summary.get("validator_issues")),
            "google_adoptions": as_int(summary.get("alternate_witness_adoptions")),
            "google_unresolved": as_int(summary.get("alternate_witness_unresolved")),
            "applied_changes": change_rows or as_int(summary.get("tier_a_applied")),
            "reviewed_tibetan_exact_changes": as_int(summary.get("reviewed_tibetan_exact_changes")),
            "sanskrit_changes": as_int(summary.get("sanskrit_changes")),
            "sanskrit_review_suggestions": as_int(summary.get("sanskrit_review_suggestions")),
            **bucket_counts,
            **diagnostic_counts,
        }

    return ReleaseStats(
        manifest_generated_utc=generated,
        manifest_source_commit=source_commit,
        manifest_volumes=manifest_volumes,
        volumes=volumes,
        reason_counts=reason_counts,
        pair_counts=pair_counts,
        pair_volumes=pair_volumes,
        residual_tokens=residual_tokens,
        residual_buckets=residual_buckets,
    )


def total(stats: ReleaseStats, key: str) -> int:
    return sum(as_int(v.get(key)) for v in stats.volumes.values())


def pair_count(stats: ReleaseStats, source: str, target: str) -> int:
    return stats.pair_counts[(source, target)]


def pair_volume_text(stats: ReleaseStats, source: str, target: str, default: str = "all") -> str:
    volumes = sorted(stats.pair_volumes.get((source, target), set()), key=VOLUME_ORDER.index)
    return ";".join(volumes) if volumes else default


def reason_sum(stats: ReleaseStats, *prefixes_or_codes: str) -> int:
    count = 0
    for reason, value in stats.reason_counts.items():
        for prefix in prefixes_or_codes:
            if reason == prefix or reason.startswith(prefix):
                count += value
                break
    return count


def residual_token(stats: ReleaseStats, *tokens: str) -> int:
    return sum(stats.residual_tokens[t] for t in tokens)


def residual_chars(stats: ReleaseStats, chars: str) -> int:
    wanted = set(chars)
    return sum(count for token, count in stats.residual_tokens.items() if wanted.intersection(token))


def residual_bucket(stats: ReleaseStats, *buckets: str) -> int:
    return sum(stats.residual_buckets[b] for b in buckets)


def row(
    family_id: str,
    category: str,
    from_pattern_or_token: str,
    to_pattern_or_token: str,
    scope: str,
    status: str,
    volumes_applied: str,
    reason_codes: str,
    implementation_location: str,
    evidence_doc: str,
    applied_count: int | str,
    residual_count: int | str,
    negative_controls: str,
    notes: str,
) -> dict[str, str]:
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"unsupported status {status!r} for {family_id}")
    return {
        "family_id": family_id,
        "category": category,
        "from_pattern_or_token": from_pattern_or_token,
        "to_pattern_or_token": to_pattern_or_token,
        "scope": scope,
        "status": status,
        "volumes_applied": volumes_applied,
        "reason_codes": reason_codes,
        "implementation_location": implementation_location,
        "evidence_doc": evidence_doc,
        "applied_count_current_release": str(applied_count),
        "residual_count_current_release": str(residual_count),
        "negative_controls": negative_controls,
        "notes": notes,
    }


def build_family_rows(stats: ReleaseStats) -> list[dict[str, str]]:
    all_reviewed_exact = reason_sum(stats, "reviewed_tibetan_exact_")
    all_sanskrit = reason_sum(stats, "sanskrit_")
    dollar_residual = residual_chars(stats, "$")
    initial_i_residual = residual_bucket(stats, "initial_confusable_I")
    dotless_residual = residual_chars(stats, "ı")
    final_ng_residual = residual_chars(stats, "ñńň")
    initial_i_exact_residual = total(stats, "initial_i_exact_residual_candidates")
    script_ng_witness_residual = total(stats, "script_ng_witness_candidates")
    reference_marker_residual = total(stats, "reference_marker_candidates")
    sanskrit_low_confidence_residual = total(stats, "sanskrit_low_confidence_candidates")
    dngos_exact_residual = total(stats, "dngos_family_exact_orthography_candidates")
    dngos_google_witness_residual = total(stats, "dngos_family_google_witness_candidates")
    dngos_blocked_wrong_nasal = total(stats, "dngos_family_blocked_wrong_nasal_witness")
    dngos_context_diagnostic = total(stats, "dngos_family_context_diagnostic_candidates")
    initial_i_exact_note = (
        "Exact Initial-I/l residual diagnostics are exhausted in all four volumes; this is not the broader initial_confusable_I artifact bucket."
        if initial_i_exact_residual == 0
        else f"Current exact Initial-I/l residual diagnostics contain {initial_i_exact_residual} candidate row(s); this is not the broader initial_confusable_I artifact bucket."
    )

    rows = [
        row(
            "google_vision_alternate_witness_policy",
            "google_witness",
            "Google Vision token witness",
            "safe token-level adoptions only",
            "policy",
            "applied",
            "all",
            "alternate_witness_adoptions",
            "scripts/postprocess_entry_map.py;release/current/qa/*/*_alternate_witness_adoptions.tsv",
            "docs/STATUS.md;release/current/qa",
            total(stats, "google_adoptions"),
            total(stats, "google_unresolved"),
            "no raw line replacement;no loosened adoption gates",
            "Base OCR remains authoritative; Google Vision is an alternate witness only.",
        ),
        row(
            "dotless_i_to_i_translit_and_names",
            "dotless_i",
            "ı",
            "i",
            "guarded_token_context",
            "applied",
            "all",
            "confusable_dotless_i_to_i_translit_shape;confusable_dotless_i_to_i_lexicon;confusable_dotless_i_to_i_safe_char_map;confusable_dotless_i_to_i_citation_name;confusable_dotless_i_to_i_allowlist;confusable_dotless_i_to_i_context;confusable_dotless_i_to_i_headword;confusable_dotless_i_to_i_entry_memory",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "confusable_dotless_i_to_i_"),
            dotless_residual,
            "Tibetan transliteration context required where applicable",
            "Guarded dotless-i repairs are active; residual dotless-i artifacts remain review evidence, not proof of a global rule.",
        ),
        row(
            "german_prose_dotless_i",
            "dotless_i",
            "ı",
            "i",
            "german_prose_context",
            "applied",
            "all",
            "german_dotless_i_safe_map;confusable_dotless_i_to_i_german_core",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "german_dotless_i_safe_map", "confusable_dotless_i_to_i_german_core"),
            dotless_residual,
            "Tibetan/Sanskrit transliteration tokens",
            "German prose dotless-i repairs are separate from transliteration repairs.",
        ),
        row(
            "guarded_dollar_to_sacute",
            "dollar_to_sacute",
            "$",
            "ś",
            "exact_or_context_guarded",
            "partially_applied",
            "all",
            "confusable_dollar_to_sacute_shape_safe;confusable_dollar_to_sacute_lexicon;confusable_dollar_to_sacute_name_anchor;orphan_safe_dollar_to_sacute;citation_isv_dollar_abbrev_map",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "release/current/qa;docs/tibetan_sigla_registry_cleanup_2026-06-27.md",
            reason_sum(stats, "confusable_dollar_to_sacute_", "orphan_safe_dollar_to_sacute", "citation_isv_dollar_abbrev_map"),
            dollar_residual,
            "generic $ token;currency/noise;unreviewed sigla",
            "Exact/guarded $ to ś repairs are active, but the broad character rule is forbidden and residual $ buckets remain.",
        ),
        row(
            "final_ng_mark_variants",
            "final_ng",
            "ñ/ń/ň",
            "ṅ",
            "exact_token_or_witness_guarded",
            "partially_applied",
            "all",
            "confusable_nya_coda_safe;confusable_nya_coda_safe_strong_context;reviewed_tibetan_exact_final_ng;reviewed_tibetan_exact_script_ng_witness;reviewed_tibetan_exact_residual_ng;reviewed_tibetan_exact_residual_spacing_ng",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_script_ng_witness_sweep_2026-06-28.md;release/current/qa",
            reason_sum(stats, "confusable_nya_coda_safe", "reviewed_tibetan_exact_final_ng", "reviewed_tibetan_exact_script_ng_witness", "reviewed_tibetan_exact_residual_ng", "reviewed_tibetan_exact_residual_spacing_ng"),
            final_ng_residual,
            "broad ń->ṅ;broad n->ṅ",
            "Many exact final-ṅ repairs are applied; remaining nasal-looking tokens still require context or Tibetan-script witness support.",
        ),
        row(
            "final_ng_deferred_source_review",
            "final_ng",
            "source-sensitive final-ng candidates",
            "source-checked Tibetan forms",
            "source_review_queue",
            "deferred",
            "none",
            "none",
            "none",
            "docs/tibetan_initial_i_ng_cleanup_2026-06-28.md;release/current/qa/*/tibetan_cleanup_diagnostics",
            0,
            final_ng_residual,
            "broad ń->ṅ;broad n->ṅ;abbreviation/noisy contexts",
            "Deferred final-ng source-review rows remain separate from the script-ng witness diagnostic queue.",
        ),
        row(
            "final_ng_script_witness_diagnostic_queue",
            "final_ng",
            "script-ng witness diagnostic candidates",
            "source-checked Tibetan-script evidence",
            "diagnostic_queue",
            "diagnostic_only",
            "none",
            "none",
            "none",
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_script_ng_witness_candidates.tsv",
            0,
            script_ng_witness_residual,
            "broad ń->ṅ;broad n->ṅ;broad T/I/\\->↑ marker rule;unverified witness-only contexts",
            "Current script-ng witness diagnostic rows are separate from the final-ng deferred source-review residual; marker-attached rows remain in this queue after reference-marker separation.",
        ),
        row(
            "reference_marker_diagnostics",
            "reference_marker",
            "T/I/slash/backslash/actual arrows near Tibetan transliteration context",
            "↑/↓ reference markers",
            "page_line_token;diagnostic_queue",
            "partially_applied",
            "reviewed_tibetan_exact_reference_marker",
            "data/reviewed_tibetan_exact_overrides.tsv;scripts/postprocess_entry_map.py",
            "exact reviewed rows only; no broad marker rule",
            "release/current/qa/*/*_changes.tsv;release/current/qa/*/tibetan_cleanup_diagnostics/reference_marker_candidates.tsv",
            reason_sum(stats, "reviewed_tibetan_exact_reference_marker"),
            reference_marker_residual,
            "broad T->↑/↓;broad I->↑/↓;broad /->↑/↓;broad \\->↑/↓;broad n->ṅ",
            "Reviewed reference-marker rows are exact page-line-token corrections with confirmed direction; remaining rows are diagnostic only.",
        ),
        row(
            "dngos_exact_dnos_to_dngos",
            "final_ng",
            "dnos",
            "dṅos",
            "page_line_token",
            "partially_applied",
            pair_volume_text(stats, "dnos", "dṅos"),
            "reviewed_tibetan_exact_dngos;blocked_alternate_witness_wrong_nasal_dnos",
            "data/reviewed_tibetan_exact_overrides.tsv;scripts/postprocess_entry_map.py",
            "release/current/qa/*/*_changes.tsv;release/current/qa/*/tibetan_cleanup_diagnostics",
            reason_sum(stats, "reviewed_tibetan_exact_dngos"),
            dngos_exact_residual + dngos_google_witness_residual,
            "broad dnos->dṅos;broad nasal rule;dnos->dños witness",
            (
                "Reviewed exact dnos->dṅos rows are applied by page/line/token; "
                f"exact orthography diagnostic residual rows={dngos_exact_residual}; "
                f"remaining witness diagnostics={dngos_google_witness_residual} "
                f"({dngos_blocked_wrong_nasal} blocked dnos->dños, "
                f"{dngos_context_diagnostic} context diagnostics). "
                "No broad dnos->dṅos rule exists."
            ),
        ),
        row(
            "final_ng_yang",
            "final_ng",
            "yañ",
            "yaṅ",
            "exact_token",
            "applied",
            pair_volume_text(stats, "yañ", "yaṅ"),
            "explicit_user_allowlist;reviewed_tibetan_exact_yang",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_initial_i_ng_cleanup_2026-06-28.md",
            pair_count(stats, "yañ", "yaṅ") + reason_sum(stats, "reviewed_tibetan_exact_yang"),
            residual_token(stats, "yañ"),
            "yani unless separately reviewed;German prose",
            "Applied where token/context gates permit.",
        ),
        row(
            "final_ng_dang",
            "final_ng",
            "dañ",
            "daṅ",
            "exact_token",
            "applied",
            pair_volume_text(stats, "dañ", "daṅ"),
            "explicit_user_allowlist;tibetan_dang_phrase_override;tibetan_dang_witness_rewrite",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_dan_dang_phrase_batch_2026-06-25.md;docs/tibetan_initial_i_ng_cleanup_2026-06-28.md",
            pair_count(stats, "dañ", "daṅ") + reason_sum(stats, "tibetan_dang_phrase_override", "tibetan_dang_witness_rewrite"),
            residual_token(stats, "dañ"),
            "German dan;unreviewed n->ṅ",
            "Exact daṅ-family repairs are applied; this is not a broad n-to-ṅ rule.",
        ),
        row(
            "final_ng_nang",
            "final_ng",
            "nañ",
            "naṅ",
            "exact_token",
            "applied",
            pair_volume_text(stats, "nañ", "naṅ"),
            "explicit_user_allowlist",
            "scripts/postprocess_entry_map.py",
            "docs/tibetan_initial_i_ng_cleanup_2026-06-28.md",
            pair_count(stats, "nañ", "naṅ"),
            residual_token(stats, "nañ"),
            "German/non-Tibetan contexts",
            "Exact token correction only.",
        ),
        row(
            "initial_I_Ita_lta",
            "I_to_l",
            "Ita",
            "lta",
            "exact_token",
            "applied",
            "all",
            "explicit_case_sensitive_allowlist",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            pair_count(stats, "Ita", "lta"),
            residual_token(stats, "Ita"),
            "Inhalt;Indien;Ich;Ingwer",
            "Explicit case-sensitive allowlist token, not a generic I-to-l rule.",
        ),
        row(
            "initial_I_Iha_lha",
            "I_to_l",
            "Iha",
            "lha",
            "exact_token",
            "applied",
            "all",
            "explicit_case_sensitive_allowlist",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            pair_count(stats, "Iha", "lha"),
            residual_token(stats, "Iha"),
            "Inhalt;Indien;Ich;Ingwer",
            "Explicit case-sensitive allowlist token.",
        ),
        row(
            "initial_I_Ihan_lhan",
            "I_to_l",
            "Ihan",
            "lhan",
            "exact_token",
            "applied",
            "all",
            "explicit_case_sensitive_allowlist",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            pair_count(stats, "Ihan", "lhan"),
            residual_token(stats, "Ihan"),
            "Inhalt;Indien;Ich;Ingwer",
            "Explicit case-sensitive allowlist token.",
        ),
        row(
            "initial_I_Iho_lho",
            "I_to_l",
            "Iho",
            "lho",
            "exact_token",
            "applied",
            "all",
            "explicit_case_sensitive_allowlist",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            pair_count(stats, "Iho", "lho"),
            residual_token(stats, "Iho"),
            "Inhalt;Indien;Ich;Ingwer",
            "Explicit case-sensitive allowlist token.",
        ),
        row(
            "initial_I_Itos_ltos",
            "I_to_l",
            "Itos",
            "ltos",
            "exact_token",
            "applied",
            "all",
            "explicit_case_sensitive_allowlist",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            pair_count(stats, "Itos", "ltos"),
            residual_token(stats, "Itos"),
            "Inhalt;Indien;Ich;Ingwer",
            "Explicit case-sensitive allowlist token.",
        ),
        row(
            "initial_I_exact_residual_diagnostic",
            "I_to_l",
            "reviewed Initial-I/l residual diagnostic",
            "no remaining exact candidate rows",
            "diagnostic_queue",
            "diagnostic_only",
            "none",
            "none",
            "none",
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_initial_i_residual_candidates.tsv",
            0,
            initial_i_exact_residual,
            "initial_confusable_I artifact bucket;German/prose controls",
            initial_i_exact_note,
        ),
        row(
            "initial_I_context_gated_ldan_family",
            "I_to_l",
            "Idan and related marked-context initial-I tokens",
            "ldan and related l-forms",
            "lexicon_or_marked_context",
            "partially_applied",
            "all",
            "confusable_initial_I_to_l_marked_context;confusable_initial_I_to_l_lexicon;confusable_initial_I_to_l_strong_context;confusable_initial_I_to_l_headword;reviewed_tibetan_exact_initial_i_l_family;confusable_hyphenated_I_to_l_translit",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "release/current/qa;docs/tibetan_initial_i_ng_cleanup_2026-06-28.md",
            reason_sum(stats, "confusable_initial_I_to_l_", "reviewed_tibetan_exact_initial_i_l_family", "confusable_hyphenated_I_to_l_translit"),
            initial_i_residual,
            "Inhalt;Indien;Ich;Ingwer;International",
            f"{initial_i_exact_note} Reviewed rows such as Ina->lṅa, Itar->ltar, Ipags->lpags, Ius->lus, and Ikog->lkog are applied; the broader initial_confusable_I diagnostic bucket remains.",
        ),
        row(
            "initial_I_Itar_ltar",
            "I_to_l",
            "Itar",
            "ltar",
            "mixed",
            "partially_applied",
            pair_volume_text(stats, "Itar", "ltar", "wts_8_b"),
            "reviewed_tibetan_exact;initial_I_context_rules",
            "data/reviewed_tibetan_exact_overrides.tsv;release/current/qa",
            "docs/tibetan_initial_i_ng_cleanup_2026-06-28.md",
            pair_count(stats, "Itar", "ltar"),
            residual_token(stats, "Itar"),
            "Inhalt;Indien;Ich;Ingwer",
            "Reviewed exact Itar->ltar rows are applied, but residual Itar remains; no global unconstrained Itar->ltar rule exists.",
        ),
        row(
            "sanskrit_normalisations",
            "sanskrit",
            "damaged Sanskrit title/name/term tokens",
            "reviewed Sanskrit forms",
            "exact_token_context_gate",
            "partially_applied",
            "all",
            "sanskrit_high_freq_allowlist;sanskrit_promoted_context_gate;sanskrit_char_normalize;sanskrit_singleton_context_gate;sanskrit_jn_cluster_contextual;sanskrit_jn_cluster_context_gate;sanskrit_family_canonicalize;sanskrit_promoted_context_allowlist",
            "scripts/postprocess_entry_map.py;data/sanskrit_promote_overrides.tsv",
            "docs/sanskrit_large_batch_cleanup_2026-05-28.md;release/current/qa",
            all_sanskrit,
            total(stats, "sanskrit_review_suggestions"),
            "German prose;Tibetan transliteration;unreviewed broad jn->jñ or ä->ā",
            "Sanskrit cleanups are exact/context-gated; remaining Sanskrit review suggestions need source/context checking.",
        ),
        row(
            "sanskrit_source_check_queue",
            "sanskrit",
            "Sanskrit review suggestions",
            "source-checked Sanskrit forms",
            "source_review_queue",
            "needs_source_check",
            "none",
            "none",
            "release/current/qa/*/*_sanskrit_report.tsv",
            "release/current/qa",
            0,
            total(stats, "sanskrit_review_suggestions"),
            "German prose;Tibetan transliteration;unreviewed broad jn->jñ or ä->ā",
            "Residual Sanskrit suggestions are a source-check queue, not applied correction evidence.",
        ),
        row(
            "residual_sanskrit_low_confidence_diagnostic",
            "sanskrit",
            "low-confidence Sanskrit-like residual diagnostics",
            "sampled/promoted formal review rows",
            "diagnostic_queue",
            "diagnostic_only",
            "none",
            "none",
            "none",
            "release/current/qa/*/tibetan_cleanup_diagnostics/residual_sanskrit_low_confidence_candidates.tsv",
            0,
            sanskrit_low_confidence_residual,
            "German prose;Tibetan transliteration;bibliographic names",
            "Exploratory diagnostic only; keep separate from the formal Sanskrit source-check queue.",
        ),
        row(
            "sigla_bu_sz",
            "sigla",
            "Bu-Sz / Bu-$z variants",
            "Bu-śz",
            "row_gated",
            "applied",
            "wts_8_b;wts_9_m",
            "reviewed_siglum_exact_registry_canonicalization",
            "data/reviewed_tibetan_exact_overrides.tsv;scripts/postprocess_entry_map.py",
            "docs/tibetan_sigla_registry_cleanup_2026-06-27.md",
            reason_sum(stats, "reviewed_siglum_exact_registry_canonicalization"),
            residual_token(stats, "Bu-Sz", "Bu-$z"),
            "generic $->ś",
            "Reviewed siglum canonicalization only.",
        ),
        row(
            "sigla_li_lish",
            "sigla",
            "Lis / Li$",
            "Liś",
            "row_or_registry_gated",
            "applied",
            "all",
            "citation_siglum_confusable_map;reviewed_siglum_exact_registry_canonicalization",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_sigla_registry_cleanup_2026-06-27.md",
            pair_count(stats, "Lis", "Liś") + pair_count(stats, "Li$", "Liś"),
            residual_token(stats, "Lis", "Li$"),
            "plain German/Sanskrit tokens",
            "Liś siglum normalization is treated as siglum policy, not generic dollar repair.",
        ),
        row(
            "sigla_lsdz_k_lshdz_k",
            "sigla",
            "Lsdz-K / L$dz-K",
            "Lśdz-K",
            "row_or_registry_gated",
            "applied",
            "wts_8_b;wts_9_m",
            "reviewed_siglum_exact_registry_canonicalization",
            "data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_sigla_registry_cleanup_2026-06-27.md",
            pair_count(stats, "Lsdz-K", "Lśdz-K") + pair_count(stats, "L$dz-K", "Lśdz-K"),
            residual_token(stats, "Lsdz-K", "L$dz-K"),
            "generic $->ś",
            "Reviewed siglum family only.",
        ),
        row(
            "sigla_gs_h_gsh_h",
            "sigla",
            "Gs-H / G$-H",
            "Gś-H",
            "row_or_registry_gated",
            "applied",
            "wts_8_b;wts_9_m",
            "reviewed_siglum_exact_registry_canonicalization",
            "data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_sigla_registry_cleanup_2026-06-27.md",
            pair_count(stats, "Gs-H", "Gś-H") + pair_count(stats, "G$-H", "Gś-H"),
            residual_token(stats, "Gs-H", "G$-H"),
            "generic $->ś",
            "Reviewed siglum canonicalization only.",
        ),
        row(
            "sigla_other_reviewed_exact",
            "sigla",
            "reviewed siglum variants",
            "reviewed canonical sigla",
            "row_or_registry_gated",
            "applied",
            "all",
            "reviewed_siglum_exact_tar;reviewed_siglum_exact_visht",
            "data/reviewed_tibetan_exact_overrides.tsv;scripts/postprocess_entry_map.py",
            "docs/tibetan_sigla_registry_cleanup_2026-06-27.md;release/current/qa",
            reason_sum(stats, "reviewed_siglum_exact_tar", "reviewed_siglum_exact_visht"),
            "unknown",
            "generic $->ś;unreviewed bibliography abbreviations",
            "Covers reviewed siglum exact rows outside the named registry families.",
        ),
        row(
            "reviewed_page_line_tibetan_exact_overrides",
            "tibetan_exact",
            "reviewed page-line-token source forms",
            "reviewed target forms",
            "page_line_token",
            "applied",
            "all",
            "reviewed_tibetan_exact_*",
            "data/reviewed_tibetan_exact_overrides.tsv",
            "docs/tibetan_initial_i_ng_cleanup_2026-06-28.md;docs/tibetan_script_ng_witness_sweep_2026-06-28.md;release/current/qa",
            all_reviewed_exact,
            "unknown",
            "unreviewed rows;global character rules",
            "Reviewed exact overrides are deliberately row/family scoped.",
        ),
        row(
            "structural_german_quote_hyphen_wrap",
            "german_prose",
            "line-wrap and quote/hyphen OCR damage",
            "normal German prose",
            "structural_context",
            "applied",
            "all",
            "structural_german_quote_hyphen_wrap_direct;citation_english_spacing_loss_map;explicit_rastrapala_split_prev;explicit_rastrapala_split_curr",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "structural_german_quote_hyphen_wrap_direct", "citation_english_spacing_loss_map", "explicit_rastrapala_split_prev", "explicit_rastrapala_split_curr"),
            "unknown",
            "Tibetan/Sanskrit tokens",
            "Represented here so status checks know these current-release correction reasons are intentional.",
        ),
        row(
            "citation_name_author_normalisations",
            "citation",
            "citation/name OCR variants",
            "canonical citation/name forms",
            "citation_context",
            "applied",
            "all",
            "citation_author_lexicon;citation_confusable_safe_map;citation_name_safe_map;citation_caps_name_normalize;citation_token_exact_safe_map;citation_phrase_safe_map;citation_name_and_sigla;citation_roman_l_to_I",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "citation_author_lexicon", "citation_confusable_safe_map", "citation_name_safe_map", "citation_caps_name_normalize", "citation_token_exact_safe_map", "citation_phrase_safe_map", "citation_roman_l_to_I"),
            "unknown",
            "non-citation prose;Tibetan lexical tokens",
            "Citation/name normalization is separate from Tibetan or Sanskrit lexical cleanup.",
        ),
        row(
            "german_numeric_function_word_confusion",
            "german_prose",
            "German numeric/function-word OCR variants",
            "German prose forms",
            "german_prose_context",
            "applied",
            "all",
            "german_numeric_function_word_confusion",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "german_numeric_function_word_confusion"),
            "unknown",
            "Tibetan/Sanskrit transliteration tokens",
            "Current-release correction family outside the OCR-script cleanup queues.",
        ),
        row(
            "tibetan_phrase_spacing_and_allowlists",
            "tibetan_phrase",
            "known Tibetan phrase/token spacing variants",
            "reviewed Tibetan phrase forms",
            "phrase_or_context_gate",
            "applied",
            "all",
            "tibetan_translit_phrase_allowlist;tibetan_translit_ting_nge_dzin_phrase;tibetan_dang_phrase_override;tibetan_dang_witness_rewrite;reviewed_tibetan_exact_di_lta_spacing;reviewed_tibetan_exact_di_lta_bu_spacing;explicit_gans_ri;explicit_user_allowlist_in_tu",
            "scripts/postprocess_entry_map.py;data/reviewed_tibetan_exact_overrides.tsv",
            "docs/residual_error_family_research_2026-06-24.md;docs/tibetan_dan_dang_phrase_batch_2026-06-25.md",
            reason_sum(stats, "tibetan_translit_phrase_allowlist", "tibetan_translit_ting_nge_dzin_phrase", "tibetan_dang_phrase_override", "tibetan_dang_witness_rewrite", "reviewed_tibetan_exact_di_lta_spacing", "reviewed_tibetan_exact_di_lta_bu_spacing", "explicit_gans_ri", "explicit_user_allowlist_in_tu"),
            "unknown",
            "unreviewed spacing changes",
            "Phrase-level Tibetan repairs are not broad whitespace rules.",
        ),
        row(
            "contextual_confusable_headword_memory",
            "contextual_confusable",
            "headword/context-memory confusable tokens",
            "contextually supported forms",
            "headword_or_entry_context",
            "applied",
            "all",
            "confusable_to_headword",
            "scripts/postprocess_entry_map.py",
            "release/current/qa",
            reason_sum(stats, "confusable_to_headword"),
            "unknown",
            "unanchored token replacements",
            "Context-memory repairs are represented separately from broad character families.",
        ),
        row(
            "residual_bucket_promote_candidates",
            "residual_queue",
            "bucket promote candidates",
            "candidate exact/context promotions",
            "review_queue",
            "promote_candidate",
            "none",
            "none",
            "release/current/qa/*/bucket_report.summary.md",
            "release/current/qa",
            0,
            total(stats, "bucket_promote_rows"),
            "unreviewed token-level buckets",
            "Promote candidates are residual review targets only until accepted into code or override TSVs.",
        ),
        row(
            "dated_cleanup_reports",
            "documentation",
            "dated cleanup reports",
            "historical audit records",
            "documentation_only",
            "historical_only",
            "none",
            "none",
            "none",
            "docs/*_2026-*.md",
            0,
            0,
            "current operational status",
            "Dated cleanup reports are historical records. `docs/STATUS.md` is the current operational status.",
        ),
        row(
            "generic_dollar_to_sacute",
            "dollar_to_sacute",
            "$",
            "ś",
            "generic",
            "unsafe_broad_rule",
            "none",
            "none",
            "none",
            "docs/STATUS.md",
            0,
            dollar_residual,
            "all unreviewed $ tokens",
            "Forbidden broad rule; only exact/guarded or siglum-reviewed rows may change.",
        ),
        row(
            "generic_I_to_l",
            "I_to_l",
            "I",
            "l",
            "generic",
            "unsafe_broad_rule",
            "none",
            "none",
            "none",
            "docs/STATUS.md",
            0,
            initial_i_residual,
            "Inhalt;Indien;Ich;Ingwer;International",
            "Forbidden broad rule. Current initial-I cleanup is explicit-token, lexicon/context, or reviewed exact only.",
        ),
        row(
            "validator_only_suggestions",
            "validator",
            "validator/canonicalisation suggestions",
            "not correction evidence",
            "reporting_only",
            "false_positive_or_noise",
            "none",
            "none",
            "release/current/qa/*/*_validator_issues.tsv",
            "docs/STATUS.md;release/current/qa",
            0,
            total(stats, "validator_issues"),
            "German/prose false positives;valid Tibetan transliteration;sigla",
            "Validator-only rows are diagnostics. They are not OCR-witness evidence by themselves.",
        ),
    ]
    return rows


def write_tsv(rows: list[dict[str, str]]) -> str:
    lines: list[str] = []
    lines.append("\t".join(TSV_COLUMNS))
    for item in rows:
        lines.append("\t".join(item.get(col, "") for col in TSV_COLUMNS))
    return "\n".join(lines) + "\n"


def markdown_table(headers: list[str], rows: Iterable[Iterable[str | int]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row_values in rows:
        out.append("| " + " | ".join(str(v) for v in row_values) + " |")
    return "\n".join(out)


def per_volume_count_text(stats: ReleaseStats, key: str) -> str:
    return ", ".join(f"{volume}: {stats.volumes[volume][key]}" for volume in VOLUME_ORDER)


def remaining_work_rows(stats: ReleaseStats) -> list[list[str | int]]:
    dollar_residual = residual_chars(stats, "$")
    initial_i_residual = residual_bucket(stats, "initial_confusable_I")
    initial_i_exact_residual = total(stats, "initial_i_exact_residual_candidates")
    final_ng_residual = residual_chars(stats, "ñńň")
    reference_marker_residual = total(stats, "reference_marker_candidates")
    dngos_blocked_wrong_nasal = total(stats, "dngos_family_blocked_wrong_nasal_witness")
    dngos_context_diagnostic = total(stats, "dngos_family_context_diagnostic_candidates")
    return [
        [
            "Exact Initial-I/l residual diagnostic",
            initial_i_exact_residual,
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_initial_i_residual_candidates.tsv",
            "exhausted diagnostic" if initial_i_exact_residual == 0 else "diagnostic residual",
            "No action unless a later release artifact repopulates it."
            if initial_i_exact_residual == 0
            else "Review only in a dedicated Initial-I pass; do not apply broad I -> l.",
            "Separate from broader initial_confusable_I warnings."
            if initial_i_exact_residual == 0
            else "Exposed by current release diagnostics; not processed in the dngos_family pass.",
        ],
        [
            "initial_confusable_I artifact bucket",
            initial_i_residual,
            "release/current/qa/*/bucket_report.artifact_tokens.tsv",
            "warning/diagnostic",
            "Review sampled token families only; do not apply broad I -> l.",
            "May include controls, bibliographic/prose tokens, and unreviewed cases.",
        ],
        [
            "Reviewed exact Initial-I/l rows",
            reason_sum(stats, "reviewed_tibetan_exact_initial_i_l_family"),
            "release/current/qa/*/*_changes.tsv",
            "already applied",
            "No current residual queue for the exact diagnostic.",
            "Includes Ina -> lṅa, Itar -> ltar, Ipags -> lpags, Ius -> lus, and Ikog -> lkog; no global Itar -> ltar.",
        ],
        [
            "dngos_family exact orthography residual",
            total(stats, "dngos_family_exact_orthography_candidates"),
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_orthography_damage_candidates.tsv",
            "exhausted exact queue",
            "No action unless a later release artifact repopulates it.",
            "This release promoted reviewed exact dnos -> dṅos rows; no broad rule.",
        ],
        [
            "dngos_family Google-witness diagnostic residual",
            total(stats, "dngos_family_google_witness_candidates"),
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_google_candidate_readings.tsv",
            "diagnostic only; broad rule forbidden",
            "Review only if promoted to exact page/line/token rows; keep dnos -> dños blocked.",
            f"{dngos_blocked_wrong_nasal} blocked dnos -> dños pairs; {dngos_context_diagnostic} context diagnostics.",
        ],
        [
            "Guarded $ -> ś residuals",
            dollar_residual,
            "release/current/qa/*/bucket_report.artifact_tokens.tsv",
            "partially applied; broad rule forbidden",
            "Review exact/context candidates only.",
            "Siglum policy is a separate queue.",
        ],
        [
            "Siglum policy diagnostics",
            total(stats, "sigla_variant_candidates"),
            "release/current/qa/*/tibetan_cleanup_diagnostics/sigla_variant_candidates.tsv",
            "exploratory diagnostic",
            "Review separately from Tibetan lexical corrections.",
            "Named sigla normalisations are already applied separately.",
        ],
        [
            "Final-ng deferred source review",
            final_ng_residual,
            "release/current/qa/*/bucket_report.artifact_tokens.tsv",
            "deferred source review",
            "Check source/context before promotion.",
            "Separate from script-ng witness diagnostics.",
        ],
        [
            "Script-ng witness diagnostic queue",
            total(stats, "script_ng_witness_candidates"),
            "release/current/qa/*/tibetan_cleanup_diagnostics/tibetan_script_ng_witness_candidates.tsv",
            "diagnostic only",
            "Review witness rows; separate reference markers first, then promote only exact accepted cases.",
            f'{per_volume_count_text(stats, "script_ng_witness_candidates")}; marker-attached rows remain part of this queue.',
        ],
        [
            "Reference-marker OCR diagnostics",
            reference_marker_residual,
            "release/current/qa/*/tibetan_cleanup_diagnostics/reference_marker_candidates.tsv",
            "partially applied; broad rules forbidden",
            "Promote only reviewed page/line/token rows with confirmed ↑/↓ direction; do not apply broad T/I/slash/backslash -> ↑/↓.",
            f'{per_volume_count_text(stats, "reference_marker_candidates")}; actual ↑/↓ rows are controls, not correction evidence.',
        ],
        [
            "Formal Sanskrit source-check queue",
            total(stats, "sanskrit_review_suggestions"),
            "release/current/qa/*/*_summary.json and Sanskrit report TSVs",
            "needs source check",
            "Review source/context suggestions.",
            "Do not collapse with low-confidence residual diagnostics.",
        ],
        [
            "Residual Sanskrit low-confidence diagnostic",
            total(stats, "sanskrit_low_confidence_candidates"),
            "release/current/qa/*/tibetan_cleanup_diagnostics/residual_sanskrit_low_confidence_candidates.tsv",
            "exploratory diagnostic",
            "Sample before promoting into a formal queue.",
            "Not applied correction evidence.",
        ],
        [
            "Validator-only diagnostics",
            total(stats, "validator_issues"),
            "release/current/qa/*/*_validator_issues.tsv",
            "false-positive/noise diagnostic",
            "Treat as diagnostics unless independently confirmed.",
            "Not OCR-witness evidence by themselves.",
        ],
        [
            "Bucket promote candidates",
            total(stats, "bucket_promote_rows"),
            "release/current/qa/*/bucket_report.summary.md",
            "promote candidate",
            "Promote only after explicit review.",
            "Current residual queue, not applied behavior.",
        ],
    ]


def build_status_markdown(stats: ReleaseStats, family_rows: list[dict[str, str]]) -> str:
    volume_rows = []
    for volume in VOLUME_ORDER:
        data = stats.volumes[volume]
        volume_rows.append(
            [
                volume,
                data["entries"],
                data["non_empty_lines"],
                data["validator_issues"],
                data["google_adoptions"],
                data["google_unresolved"],
                data["applied_changes"],
                data["reviewed_tibetan_exact_changes"],
                data["sanskrit_changes"],
                data["sanskrit_review_suggestions"],
                data["bucket_unresolved_pairs"],
                data["bucket_promote_rows"],
                data["bucket_hold_rows"],
            ]
        )

    family_table_rows = []
    for item in family_rows:
        family_table_rows.append(
            [
                item["family_id"],
                item["status"],
                item["scope"],
                item["volumes_applied"],
                item["implementation_location"],
                item["evidence_doc"],
                item["notes"],
            ]
        )

    remaining_table = markdown_table(
        [
            "Queue / family",
            "Current count",
            "Where counted",
            "Status",
            "Next action",
            "Notes",
        ],
        remaining_work_rows(stats),
    )
    initial_i_exact_residual = total(stats, "initial_i_exact_residual_candidates")
    script_ng_witness_residual = total(stats, "script_ng_witness_candidates")
    reference_marker_residual = total(stats, "reference_marker_candidates")
    initial_i_exact_sentence = (
        "The exact Initial-I/l residual diagnostic is exhausted: `tibetan_initial_i_residual_candidates.tsv` has no candidate rows after the header for all four volumes."
        if initial_i_exact_residual == 0
        else f"The exact Initial-I/l residual diagnostic currently has {initial_i_exact_residual} candidate row(s); keep these for a dedicated Initial-I pass, separate from dngos_family release changes."
    )

    return f"""# WtS OCR Current Status

Generated by `python3 scripts/build_status.py` from checked-in release artifacts.

## Current Release

- Current release path: `release/current`
- Current release generated date: `{stats.manifest_generated_utc}`
- Current release commit / observed source commit: `{stats.manifest_source_commit}`
- Volumes included: `{', '.join(VOLUME_ORDER)}`
- Policy: base OCR authoritative; Google Vision alternate witness only.

## How To Read This Repository

- `release/current` is the current deployable OCR text snapshot.
- `release/current/manifest.md` is a release/file inventory, not the project to-do list.
- `release/current/qa` is current evidence for the deployed snapshot.
- Dated cleanup reports in `docs/` are historical audit records. They may contain statements that were true when written but are now superseded.
- Historical reports preserve old counts and old decisions. They should not be used for current counts. Use `docs/STATUS.md`, `data/correction_families.tsv`, and `release/current/qa` for current status.
- `docs/STATUS.md` is the current human operational overview.
- `data/correction_families.tsv` is the small machine-readable correction-family status table.
- Code and override TSVs are the implementation source for applied behavior.

## Volume Status

{markdown_table([
        "Volume",
        "Entries",
        "Non-empty lines",
        "Validator issues",
        "Google adoptions",
        "Google unresolved",
        "Applied changes",
        "Reviewed Tibetan exact changes",
        "Sanskrit changes",
        "Sanskrit review suggestions",
        "Bucket unresolved pairs",
        "Promote rows",
        "Hold rows",
    ], volume_rows)}

## Correction Family Status

{markdown_table([
        "Family",
        "Status",
        "Scope",
        "Volumes",
        "Implementation",
        "Evidence",
        "Current residual note",
    ], family_table_rows)}

The initial-`I` family is intentionally mixed:

- `Ita`, `Iha`, `Ihan`, `Iho`, and `Itos` are applied by explicit case-sensitive rules.
- Some initial-`I` forms are corrected by lexicon, marked-context, strong-context, headword, hyphenated, or reviewed exact gates.
- {initial_i_exact_sentence}
- The broader `initial_confusable_I` artifact bucket is not the same thing. It is a warning/diagnostic bucket and may include controls, bibliographic/prose tokens, and unreviewed cases.
- Reviewed exact Initial-I/l rows have been applied, including forms such as `Ina -> lṅa`, `Itar -> ltar`, `Ipags -> lpags`, `Ius -> lus`, and `Ikog -> lkog`.
- No generic `I -> l` rule exists, and no global unconstrained `Itar -> ltar` rule exists.

The final-ng rows also use two separate counts. `final_ng_deferred_source_review` counts the current 3-row residual source-review signal from artifact reports. `final_ng_script_witness_diagnostic_queue` counts the current {script_ng_witness_residual}-row script-ng witness diagnostic queue ({per_volume_count_text(stats, "script_ng_witness_candidates")}). Marker-attached rows stay in this queue after the reference marker is separated; they are not discarded as false final-ng candidates. The witness queue is diagnostic only until reviewed exact rows are accepted.

Reference-marker cleanup is exact/page-line-token only. `reference_marker_candidates.tsv` currently has {reference_marker_residual} row(s) ({per_volume_count_text(stats, "reference_marker_candidates")}) covering actual arrows and likely `T`, `I`, `/`, and `\\` marker OCR substitutes near Tibetan transliteration contexts. No broad marker normalisation rule exists; exact changes require confirmed `↑` or `↓` direction from context, source, or entry order.

Sanskrit has two queues. `sanskrit_source_check_queue` is the formal source-check queue with {total(stats, "sanskrit_review_suggestions")} suggestions. `residual_sanskrit_low_confidence_diagnostic` is an exploratory diagnostic with {total(stats, "sanskrit_low_confidence_candidates")} rows. Do not collapse them.

Generic `$ -> ś` remains forbidden. Exact/context-gated `$ -> ś` rows are only partially applied, and sigla normalisations are separate from generic `$ -> ś`. Validator-only rows are diagnostics, not correction evidence.

## Current Remaining Work

{remaining_table}

## Next Recommended Work

The next cleanup pass should not be a broad OCR pass. Work one residual queue at a time.

Recommended order:

1. Review reference-marker OCR diagnostics and promote only exact page/line/token rows with confirmed `↑` or `↓` direction; keep broad marker rules forbidden.
2. Review residual `$ -> ś` candidates, keeping the generic `$ -> ś` rule forbidden.
3. Review siglum policy candidates separately from Tibetan lexical corrections.
4. Review the script-ng witness diagnostic queue after marker separation.
5. Review formal Sanskrit source-check suggestions.
6. Treat residual Sanskrit low-confidence candidates as exploratory only unless sampled and promoted into a formal queue.
7. Treat validator-only rows as diagnostics, not correction evidence.
8. Revisit remaining `dngos_family` Google-witness diagnostics only as a separate exact-row pass if evidence warrants it; keep broad `dnos -> dṅos` and `dnos -> dños` blocked.
"""


def represented_reason_codes(rows: list[dict[str, str]]) -> tuple[set[str], list[str]]:
    exact: set[str] = set()
    prefixes: list[str] = []
    for item in rows:
        raw = item.get("reason_codes", "")
        for part in raw.split(";"):
            part = part.strip()
            if not part or part == "none" or part == "alternate_witness_adoptions":
                continue
            if part.endswith("*"):
                prefixes.append(part[:-1])
            else:
                exact.add(part)
    return exact, prefixes


def reason_code_represented(reason: str, exact: set[str], prefixes: list[str]) -> bool:
    return reason in exact or any(reason.startswith(prefix) for prefix in prefixes)


def dirty_release_status_paths() -> list[str]:
    try:
        result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                "release/current",
                "docs/STATUS.md",
                "data/correction_families.tsv",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError:
        return ["git status could not be executed"]
    if result.returncode != 0:
        return [result.stderr.strip() or "git status failed"]
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def validation_messages(
    stats: ReleaseStats,
    rows: list[dict[str, str]],
    status_text: str,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    represented, prefixes = represented_reason_codes(rows)
    missing = sorted(
        reason for reason in stats.reason_counts if not reason_code_represented(reason, represented, prefixes)
    )
    if missing:
        failures.append(
            "reason codes in release/current changes not represented in data/correction_families.tsv: "
            + ", ".join(missing)
        )

    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for item in rows:
        family_id = item["family_id"]
        if family_id in seen_ids:
            duplicate_ids.add(family_id)
        seen_ids.add(family_id)
        if item["status"] not in ALLOWED_STATUSES:
            failures.append(f"{family_id} has unsupported status {item['status']}")
    if duplicate_ids:
        failures.append("duplicate family_id values found: " + ", ".join(sorted(duplicate_ids)))

    manifest_set = set(stats.manifest_volumes)
    status_set = set(VOLUME_ORDER)
    extra_manifest = sorted(manifest_set - status_set)
    missing_manifest = [volume for volume in VOLUME_ORDER if volume not in manifest_set]
    if extra_manifest:
        failures.append(
            "volumes in release/current/manifest.md are missing from the Volume Status table: "
            + ", ".join(extra_manifest)
        )
    if missing_manifest:
        failures.append(
            "volumes in the Volume Status table are missing from release/current/manifest.md: "
            + ", ".join(missing_manifest)
        )

    for volume in VOLUME_ORDER:
        text_path = RELEASE / "text" / f"{volume}_corrected_full.txt"
        if not text_path.is_file():
            failures.append(f"{volume} is missing release text {text_path.relative_to(ROOT)}")
        qa_dir = QA_ROOT / volume
        for template in REQUIRED_QA_FILES:
            qa_path = qa_dir / template.format(volume=volume)
            if not qa_path.is_file():
                failures.append(f"{volume} is missing required QA file {qa_path.relative_to(ROOT)}")

    for item in rows:
        family_id = item["family_id"]
        if family_id not in status_text:
            failures.append(f"family {family_id} is not represented in docs/STATUS.md")
        applied = item.get("applied_count_current_release", "")
        residual = item.get("residual_count_current_release", "")
        try:
            applied_int = int(applied)
        except ValueError:
            applied_int = 0
        try:
            residual_int = int(residual)
        except ValueError:
            residual_int = 0
        if item["status"] == "unsafe_broad_rule" and applied_int != 0:
            failures.append(f"{family_id} is an unsafe broad rule but has applied count {applied_int}")
        if item["status"] == "applied" and residual_int > 0 and item["scope"] == "exact_token":
            explanation = " ".join(
                [
                    item.get("negative_controls", ""),
                    item.get("notes", ""),
                ]
            )
            if not re.search(r"false positive|noise", explanation, flags=re.IGNORECASE):
                failures.append(
                    f"{family_id} is marked applied for an exact-token family but has residual count {residual_int}"
                )
        if item["status"] == "partially_applied" and residual_int >= 1000:
            warnings.append(
                f"{family_id} remains partially applied with large residual count {residual_int}; review recommended"
            )
    return failures, warnings


def add_historical_notes() -> None:
    targets = [
        ROOT / "docs" / "current_release_refresh_2026-06-27.md",
        ROOT / "docs" / "current_release_refresh_2026-06-28.md",
        ROOT / "docs" / "four_volume_cleanup_strategy_2026-06-25.md",
        ROOT / "docs" / "release_readiness_after_wts_8b_9m_2026-06-13.md",
        ROOT / "docs" / "tibetan_cleanup_residual_triage_2026-06-21.md",
        ROOT / "docs" / "tibetan_initial_i_ng_cleanup_2026-06-28.md",
        ROOT / "docs" / "tibetan_script_ng_witness_sweep_2026-06-28.md",
        ROOT / "docs" / "tibetan_sigla_registry_cleanup_2026-06-27.md",
    ]
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if HISTORICAL_NOTE in text:
            continue
        path.write_text(HISTORICAL_NOTE + "\n\n" + text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify generated files are up to date")
    args = parser.parse_args()

    stats = read_release_stats()
    family_rows = build_family_rows(stats)
    tsv_text = write_tsv(family_rows)
    status_text = build_status_markdown(stats, family_rows)
    failures, warnings = validation_messages(stats, family_rows, status_text)

    if args.check:
        failed = False
        dirty_paths = dirty_release_status_paths()
        if dirty_paths:
            print(
                "release/status inputs are dirty; commit or discard them before release check:",
                file=sys.stderr,
            )
            for path in dirty_paths:
                print(f"  {path}", file=sys.stderr)
            failed = True
        expected = {
            STATUS_PATH: status_text,
            FAMILIES_PATH: tsv_text,
        }
        for path, generated in expected.items():
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != generated:
                print(f"{path.relative_to(ROOT)} is not up to date", file=sys.stderr)
                failed = True
        for message in failures:
            print(f"error: {message}", file=sys.stderr)
            failed = True
        for message in warnings:
            print(f"warning: {message}", file=sys.stderr)
        return 1 if failed else 0

    if failures:
        for message in failures:
            print(f"error: {message}", file=sys.stderr)
        return 1
    STATUS_PATH.write_text(status_text, encoding="utf-8")
    FAMILIES_PATH.write_text(tsv_text, encoding="utf-8")
    add_historical_notes()
    for message in warnings:
        print(f"warning: {message}", file=sys.stderr)
    print(f"wrote {STATUS_PATH.relative_to(ROOT)}")
    print(f"wrote {FAMILIES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
