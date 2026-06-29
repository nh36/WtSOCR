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
    "historical_only",
}
HISTORICAL_NOTE = (
    "> Historical audit record. This file is not the current to-do list. "
    "See `docs/STATUS.md` for the current operational status."
)


@dataclass
class ReleaseStats:
    manifest_generated_utc: str
    manifest_source_commit: str
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


def parse_manifest() -> tuple[str, str]:
    manifest = RELEASE / "manifest.md"
    text = manifest.read_text(encoding="utf-8") if manifest.exists() else ""
    generated = "unknown"
    source_commit = "unknown"
    m = re.search(r"Generated UTC:\s*`([^`]+)`", text)
    if m:
        generated = m.group(1)
    m = re.search(r"Source/code commit observed while building this bundle:\s*`([^`]+)`", text)
    if m:
        source_commit = m.group(1)
    return generated, source_commit


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


def read_release_stats() -> ReleaseStats:
    generated, source_commit = parse_manifest()
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
        }

    return ReleaseStats(
        manifest_generated_utc=generated,
        manifest_source_commit=source_commit,
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
            "Some initial-I forms are corrected by lexicon, marked, strong-context, or reviewed exact gates; residual initial_confusable_I buckets remain.",
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
            "At least one exact reviewed row is applied, but large residual bucket counts mean broad/global Itar to ltar is not proven.",
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
            "German prose;Tibetan/Wylie;unreviewed broad jn->jñ or ä->ā",
            "Sanskrit cleanups are exact/context-gated; remaining Sanskrit review suggestions need source/context checking.",
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
            "German/prose false positives;valid Tibetan/Wylie;sigla",
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
- Some initial-`I` forms are corrected by lexicon, marked-context, strong-context, or reviewed exact gates.
- At least one exact reviewed `Itar -> ltar` row has been applied.
- Large residual `initial_confusable_I` bucket counts remain in current bucket reports, so broad/global `Itar -> ltar` is not proven as fully applied.
- Generic `I -> l` remains forbidden.

## Current Open Questions

- Which high-frequency residual `initial_confusable_I` tokens are safe for promotion?
- Which residual `$` tokens are true `ś` errors versus warnings/noise?
- Which validator issues are real OCR errors versus German/prose false positives?
- Which Sanskrit review suggestions still need source checking?

## Next Recommended Work

Do not start new OCR cleanup until this status pass is committed and reviewed.
The next cleanup pass should use this file and `data/correction_families.tsv` as
the starting point, then focus on one residual audit at a time with corrected-text
diffs, QA counts, and source/context evidence.
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


def warning_messages(stats: ReleaseStats, rows: list[dict[str, str]]) -> list[str]:
    warnings: list[str] = []
    represented, prefixes = represented_reason_codes(rows)
    missing = sorted(
        reason for reason in stats.reason_counts if not reason_code_represented(reason, represented, prefixes)
    )
    if missing:
        warnings.append(
            "reason codes in release/current changes not represented in data/correction_families.tsv: "
            + ", ".join(missing)
        )

    family_ids = {item["family_id"] for item in rows}
    if len(family_ids) != len(rows):
        warnings.append("duplicate family_id values found in data/correction_families.tsv")

    status_text = build_status_markdown(stats, rows)
    for item in rows:
        family_id = item["family_id"]
        if family_id not in status_text:
            warnings.append(f"family {family_id} is not represented in docs/STATUS.md")
        residual = item.get("residual_count_current_release", "")
        try:
            residual_int = int(residual)
        except ValueError:
            residual_int = 0
        if item["status"] == "applied" and residual_int >= 25 and item["scope"] in {"exact_token", "row_gated", "row_or_registry_gated"}:
            warnings.append(
                f"{family_id} is marked applied but has high residual count {residual_int}; "
                "consider partially_applied if that residual is the same family"
            )
    return warnings


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
    warnings = warning_messages(stats, family_rows)

    if args.check:
        failed = False
        expected = {
            STATUS_PATH: status_text,
            FAMILIES_PATH: tsv_text,
        }
        for path, generated in expected.items():
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != generated:
                print(f"{path.relative_to(ROOT)} is not up to date", file=sys.stderr)
                failed = True
        for message in warnings:
            print(f"warning: {message}", file=sys.stderr)
        return 1 if failed else 0

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
