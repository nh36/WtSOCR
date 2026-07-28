#!/usr/bin/env python3
"""Build exact-Tibetan-syllable Latin concordance and canonical evidence."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_PATH = ROOT / "scripts/build_tibetan_latin_integrity.py"
SPEC = importlib.util.spec_from_file_location("tibetan_latin_integrity", INTEGRITY_PATH)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)

BASELINE = "6322c7255cfba2fcfaf678cec656e65496ed5f12"
SCOPE_PATH = ROOT / "data/reviewed_correction_evidence_scopes.tsv"
CONCORDANCE_FIELDS = [
    "tibetan_syllable", "latin_form", "current_clean_occurrences",
    "historical_baseline_occurrences", "distinct_volumes",
    "distinct_entry_clusters", "reviewed_exact_occurrences",
    "explicit_user_reviewed_occurrences", "google_adopted_occurrences",
    "other_postprocess_occurrences", "superseded_occurrences",
    "damaged_occurrences", "marker_attached_occurrences", "domain_breakdown",
    "alignment_breakdown", "gateway_breakdown", "boundary_breakdown",
    "correction_evidence_scope",
    "known_feature_violation_breakdown",
    "provenance_breakdown", "canonical_teaching_breakdown",
    "independent_teaching_occurrences", "independent_teaching_volumes",
    "independent_teaching_clusters",
    "sample_contexts",
]
CANONICAL_FIELDS = [
    "tibetan_syllable", "canonical_forms", "canonical_status",
    "canonical_confidence_tier",
    "evidence_class", "full_target_reviewed", "supporting_forms",
    "supporting_volumes", "competing_forms", "competing_support",
    "independent_teaching_occurrences", "derived_occurrences",
    "historical_occurrences", "domain_breakdown", "feature_coverage",
    "rationale",
]
TEACHING_FIELDS = [
    "tibetan_syllable", "latin_form", "volume", "page", "line",
    "token_index", "provenance_class", "canonical_teaching_status",
    "correction_evidence_scope", "domain_context", "alignment_confidence",
    "context_excerpt",
]
FEATURE_FIELDS = [
    "tibetan_role", "tibetan_feature", "candidate_latin_realization",
    "independent_canonical_syllables", "supporting_volumes",
    "reviewed_support", "historical_support", "counterexamples",
    "counterexample_domains", "likely_ocr_confusions", "recommendation",
]
OUTLIER_FIELDS = [
    "tibetan_syllable", "current_source", "canonical_forms",
    "outlier_category", "edit_script", "edit_signatures",
    "canonical_evidence", "canonical_confidence_tier", "occurrence_count",
    "domain_breakdown", "damage_or_marker", "sample_contexts",
]
CONFUSION_FIELDS = [
    "operation_signature", "operation_type", "tibetan_role_context",
    "independent_tibetan_syllables", "occurrences", "domains",
    "canonical_evidence_classes", "reviewed_correction_support",
    "counterexamples", "collision_examples", "authorization_status",
]
RECENT_AUDIT_FIELDS = [
    "tibetan_syllable", "source_variants", "target", "corrected_count",
    "canonical_rationale", "historical_target_present",
    "explicit_feature_support", "remainder_support",
    "derived_or_circular", "disposition",
]


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def historical_identities(ref: str = BASELINE) -> dict[tuple[str, ...], dict[str, str]]:
    identities: dict[tuple[str, ...], dict[str, str]] = {}
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        text = git_show(ref, f"release/current/qa/{volume}/{volume}_line_zones.tsv")
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            line = row.get("line_text", "")
            syllables, tail, tail_start = integrity.consensus.tibetan_syllables_and_tail(line)
            latin = integrity.consensus.latin_headword_tokens(tail, len(syllables))
            if syllables and len(latin) >= len(syllables):
                for syllable, (token, start) in zip(syllables, latin):
                    absolute = tail_start + start
                    token_index = next((
                        i for i, match in enumerate(
                            integrity.consensus.POSTPROCESS_TOKEN_RE.finditer(line),
                            start=1,
                        ) if match.start() == absolute
                    ), 0)
                    identities[
                        (volume, row["page"], row["line"], str(token_index))
                    ] = {
                        "tibetan_syllable": syllable, "latin_form": token,
                        "context_excerpt": line,
                    }
    return identities


def scope_registry() -> dict[str, dict[str, str]]:
    return {row["reason"]: row for row in integrity.read_tsv(SCOPE_PATH)}


def correction_scope(row: dict[str, str]) -> tuple[str, str]:
    scope = scope_registry().get(row.get("reason", ""))
    if scope:
        return scope["evidence_scope"], scope["canonical_teaching_status"]
    return "other", "not_teaching_evidence"


def baseline_ledgers(ref: str = BASELINE) -> tuple[dict[tuple[str, ...], dict[str, str]], set[tuple[str, ...]], set[tuple[str, ...]]]:
    reviewed: dict[tuple[str, ...], dict[str, str]] = {}
    google: set[tuple[str, ...]] = set()
    changed: set[tuple[str, ...]] = set()
    text = git_show(ref, "data/reviewed_tibetan_exact_overrides.tsv")
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        reviewed[(
            row["volume"], row["page"], row["line"], row["token_index"],
            row["to_token"],
        )] = row
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        prefix = f"release/current/qa/{volume}/{volume}"
        for row in csv.DictReader(
            io.StringIO(git_show(ref, f"{prefix}_alternate_witness_adoptions.tsv")),
            delimiter="\t",
        ):
            google.add((
                volume, row.get("page", ""), row.get("line", ""),
                row.get("token_index", ""), row.get("alternate_token", ""),
            ))
        for row in csv.DictReader(
            io.StringIO(git_show(ref, f"{prefix}_changes.tsv")), delimiter="\t"
        ):
            changed.add((
                volume, row.get("page", ""), row.get("line", ""),
                row.get("to_token", ""),
            ))
    return reviewed, google, changed


def provenance_for(
    row: dict[str, str],
    historical: dict[tuple[str, ...], dict[str, str]],
    historical_ledgers: tuple[set[tuple[str, ...]], set[tuple[str, ...]], set[tuple[str, ...]]],
    override: dict[str, str] | None,
    superseded_targets: set[tuple[str, ...]],
    superseding_full_targets: set[tuple[str, ...]],
) -> tuple[str, str, str]:
    identity = (row["volume"], row["page"], row["line"], row["token_index"])
    full = identity + (row["latin_token"],)
    if full in superseded_targets:
        return "superseded", "superseded", "other"
    if full in superseding_full_targets:
        return (
            "current_reviewed_full_target",
            "reviewed_full_target_teaching_evidence",
            "full_token_explicit_review",
        )
    historical_row = historical.get(identity)
    reviewed, google, changed = historical_ledgers
    if (
        historical_row
        and historical_row["tibetan_syllable"] == row["tibetan_syllable"]
        and historical_row["latin_form"] == row["latin_token"]
    ):
        if full in reviewed:
            evidence_scope, teaching = correction_scope(reviewed[full])
            return "historical_reviewed_exact", teaching, evidence_scope
        if full in google:
            return "historical_google_adopted", "alternate_witness_only", "other"
        if (row["volume"], row["page"], row["line"], row["latin_token"]) in changed:
            return (
                "historical_other_postprocess",
                "supporting_but_derived",
                "other",
            )
        return (
            "historical_pre_campaign_unattributed",
            "independent_teaching_evidence",
            "full_token_independent_canonical",
        )
    if override:
        evidence_scope, teaching = correction_scope(override)
        if teaching == "reviewed_full_target_teaching_evidence":
            return "current_reviewed_full_target", teaching, evidence_scope
        if evidence_scope.startswith("feature_only"):
            return "current_reviewed_feature_only", teaching, evidence_scope
        if teaching == "supporting_but_derived":
            return "current_derived_from_canonical", teaching, evidence_scope
        return "current_other_postprocess", teaching, evidence_scope
    return "unknown", "not_teaching_evidence", "other"


def domain_is_teaching_safe(domain: str) -> bool:
    return domain == "ordinary_tibetan_lexical_or_compound"


def edit_operations(source: str, target: str) -> list[dict[str, str]]:
    source = unicodedata.normalize("NFC", source)
    target = unicodedata.normalize("NFC", target)
    matcher = SequenceMatcher(a=source, b=target, autojunk=False)
    operations: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old, new = source[i1:i2], target[j1:j2]
        if tag == "replace" and len(old) == len(new) and len(old) > 1:
            for offset, (old_char, new_char) in enumerate(zip(old, new)):
                operations.extend(edit_operations(old_char, new_char))
                operations[-1]["source_position"] = str(i1 + offset)
                operations[-1]["target_position"] = str(j1 + offset)
            continue
        if tag == "replace" and len(old) == len(new) == 1:
            old_base = "".join(
                c for c in unicodedata.normalize("NFD", old).lower()
                if not unicodedata.combining(c)
            )
            new_base = "".join(
                c for c in unicodedata.normalize("NFD", new).lower()
                if not unicodedata.combining(c)
            )
            if old_base == new_base:
                kind = "single_diacritic_or_case_confusion"
            elif old in "'’./\\" or new in "'’./\\":
                kind = "punctuation_confusion"
            else:
                kind = "single_character_substitution"
            signature = f"SUB {old}→{new}"
        elif tag == "delete":
            kind, signature = "single_character_deletion" if len(old) == 1 else "edit_unclassified", f"DEL {old}"
        elif tag == "insert":
            kind, signature = "single_character_insertion" if len(new) == 1 else "edit_unclassified", f"INS {new}"
        else:
            kind, signature = "edit_unclassified", f"REPLACE {old}→{new}"
        operations.append({
            "operation_type": kind, "signature": signature,
            "source_span": old, "target_span": new,
            "source_position": str(i1), "target_position": str(j1),
        })
    return operations


def edit_category(operations: list[dict[str, str]]) -> str:
    if not operations:
        return "canonical_match"
    if len(operations) == 1:
        return operations[0]["operation_type"]
    if all(op["operation_type"] != "edit_unclassified" for op in operations):
        return "multiple_recognised_edits"
    return "edit_unclassified"


def build() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diagnostics = integrity.build_diagnostics(ROOT / "release/current")
    diag_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in diagnostics
    }
    overrides = integrity.read_tsv(integrity.OVERRIDES_PATH)
    override_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in overrides
    }
    supersessions = integrity.read_tsv(integrity.SUPERSESSIONS_PATH)
    superseded = {
        (
            r["volume"], r["page"], r["line"], r["token_index"],
            r["old_target"],
        ) for r in supersessions
        if r["status"] == "active"
    }
    superseding_full_targets = {
        (
            r["volume"], r["page"], r["line"], r["token_index"],
            r["superseding_target"],
        ) for r in supersessions
        if r["status"] == "active"
        and "explicit_user" in r.get("evidence", "")
    }
    historical = historical_identities()
    historical_ledger_sets = baseline_ledgers()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in aligned:
        grouped[(row["tibetan_syllable"], row["latin_token"])].append(row)
    concordance: list[dict[str, str]] = []
    teaching_rows: list[dict[str, str]] = []
    for (syllable, form), rows in sorted(grouped.items()):
        diags = [
            diag_by_key[(r["volume"], r["page"], r["line"], r["token_index"])]
            for r in rows
        ]
        reviewed = []
        provenance = Counter()
        teaching = Counter()
        scopes = Counter()
        for r, d in zip(rows, diags):
            key = (r["volume"], r["page"], r["line"], r["token_index"])
            override = override_by_key.get(key)
            if override:
                reviewed.append(override)
            provenance_class, teaching_status, evidence_scope = provenance_for(
                r, historical, historical_ledger_sets, override, superseded,
                superseding_full_targets,
            )
            if not domain_is_teaching_safe(d["domain_context"]):
                teaching_status = "foreign_domain"
            if d["alignment_confidence"] not in {
                "secure_positional_alignment", "secure_reviewed_alignment",
            } or d["damage_scope"] not in {"none", "later_gloss_or_commentary"} \
                    or d["marker_attached"] == "yes" \
                    or d["token_boundary_status"] != "token_boundary_secure":
                teaching_status = "not_teaching_evidence"
            provenance[provenance_class] += 1
            teaching[teaching_status] += 1
            scopes[evidence_scope] += 1
            teaching_rows.append({
                "tibetan_syllable": syllable, "latin_form": form,
                "volume": r["volume"], "page": r["page"], "line": r["line"],
                "token_index": r["token_index"],
                "provenance_class": provenance_class,
                "canonical_teaching_status": teaching_status,
                "correction_evidence_scope": evidence_scope,
                "domain_context": d["domain_context"],
                "alignment_confidence": d["alignment_confidence"],
                "context_excerpt": r["context_excerpt"],
            })
        clean = [
            d for d in diags if d["alignment_confidence"] in {
                "secure_positional_alignment", "secure_reviewed_alignment"
            } and d["damage_scope"] in {"none", "later_gloss_or_commentary"}
            and d["marker_attached"] == "no"
            and d["token_boundary_status"] == "token_boundary_secure"
        ]
        domains = Counter(d["domain_context"] for d in diags)
        alignments = Counter(d["alignment_confidence"] for d in diags)
        gateways = Counter(d["transcription_gateway_status"] for d in diags)
        boundaries = Counter(d["token_boundary_status"] for d in diags)
        raw_checks = [
            integrity.token_integrity(
                r["tibetan_syllable"], r["latin_token"], use_canonical=False
            ) for r in rows
        ]
        concordance.append({
            "tibetan_syllable": syllable, "latin_form": form,
            "current_clean_occurrences": str(len(clean)),
            "historical_baseline_occurrences": str(sum(
                historical.get(
                    (r["volume"], r["page"], r["line"], r["token_index"]), {}
                ).get("tibetan_syllable") == syllable
                and historical.get(
                    (r["volume"], r["page"], r["line"], r["token_index"]), {}
                ).get("latin_form") == form
                for r in rows
            )),
            "distinct_volumes": ";".join(sorted({r["volume"] for r in clean})),
            "distinct_entry_clusters": str(len({
                (r["volume"], r["page"]) for r in clean
            })),
            "reviewed_exact_occurrences": str(len(reviewed)),
            "explicit_user_reviewed_occurrences": str(sum(
                "explicit_user_review" in r.get("evidence", "") for r in reviewed
            )),
            "google_adopted_occurrences": str(
                provenance["historical_google_adopted"]
            ),
            "other_postprocess_occurrences": str(
                provenance["historical_other_postprocess"]
                + provenance["current_other_postprocess"]
            ),
            "superseded_occurrences": str(
                provenance["superseded"]
            ),
            "damaged_occurrences": str(sum(
                d["damage_scope"] not in {"none", "later_gloss_or_commentary"}
                for d in diags
            )),
            "marker_attached_occurrences": str(sum(
                d["marker_attached"] == "yes" for d in diags
            )),
            "domain_breakdown": ";".join(f"{k}:{v}" for k, v in sorted(domains.items())),
            "alignment_breakdown": ";".join(f"{k}:{v}" for k, v in sorted(alignments.items())),
            "gateway_breakdown": ";".join(f"{k}:{v}" for k, v in sorted(gateways.items())),
            "boundary_breakdown": ";".join(
                f"{k}:{v}" for k, v in sorted(boundaries.items())
            ),
            "known_feature_violation_breakdown": ";".join(
                f"{k}:{v}" for k, v in sorted(Counter(
                    c["known_feature_violation"] for c in raw_checks
                ).items())
            ),
            "correction_evidence_scope": ";".join(
                f"{k}:{v}" for k, v in sorted(scopes.items())
            ),
            "provenance_breakdown": ";".join(
                f"{k}:{v}" for k, v in sorted(provenance.items())
            ),
            "canonical_teaching_breakdown": ";".join(
                f"{k}:{v}" for k, v in sorted(teaching.items())
            ),
            "independent_teaching_occurrences": str(
                teaching["independent_teaching_evidence"]
            ),
            "independent_teaching_volumes": ";".join(sorted({
                r["volume"] for r, t in zip(rows, teaching_rows[-len(rows):])
                if t["canonical_teaching_status"]
                == "independent_teaching_evidence"
            })),
            "independent_teaching_clusters": str(len({
                (r["volume"], r["page"])
                for r, t in zip(rows, teaching_rows[-len(rows):])
                if t["canonical_teaching_status"]
                == "independent_teaching_evidence"
            })),
            "sample_contexts": " || ".join(r["context_excerpt"] for r in rows[:3]),
        })

    by_syllable: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in concordance:
        by_syllable[row["tibetan_syllable"]].append(row)
    canonical: list[dict[str, str]] = []
    for syllable, forms in sorted(by_syllable.items()):
        eligible = [r for r in forms if int(r["superseded_occurrences"]) == 0]
        explicit = [
            r for r in eligible
            if "reviewed_full_target_teaching_evidence:"
            in r["canonical_teaching_breakdown"]
            and "full_token_explicit_review:" in r["correction_evidence_scope"]
        ]
        strong = [
            r for r in eligible
            if int(r["independent_teaching_occurrences"]) >= 3
            and len([v for v in r["independent_teaching_volumes"].split(";") if v]) >= 2
            and int(r["independent_teaching_clusters"]) >= 2
            and "yes:" not in r["known_feature_violation_breakdown"]
        ]
        moderate = [
            r for r in eligible
            if int(r["independent_teaching_occurrences"]) >= 2
            and int(r["independent_teaching_clusters"]) >= 2
            and "yes:" not in r["known_feature_violation_breakdown"]
        ]
        credible = [
            r for r in eligible
            if "yes:" not in r["known_feature_violation_breakdown"]
            and (
                int(r["independent_teaching_occurrences"]) >= 2
                or "reviewed_full_target_teaching_evidence:"
                in r["canonical_teaching_breakdown"]
            )
        ]
        if len(explicit) == 1:
            chosen, status, tier, evidence = (
                explicit, "canonical", "canonical_reviewed",
                "explicit_user_reviewed",
            )
        elif len(explicit) > 1:
            chosen, status, tier, evidence = (
                explicit, "ambiguous", "ambiguous",
                "conflicting_explicit_review",
            )
        elif len(strong) == 1 and len(credible) == 1:
            chosen, status, tier, evidence = (
                strong, "canonical", "canonical_independent_strong",
                "independent_multi_context_canonical",
            )
        elif len(credible) > 1:
            chosen, status, tier, evidence = (
                credible, "ambiguous", "ambiguous",
                "credible_competing_forms",
            )
        elif len(moderate) == 1:
            chosen, status, tier, evidence = (
                moderate, "provisional", "canonical_independent_moderate",
                "independent_moderate_evidence",
            )
        elif any(int(r["historical_baseline_occurrences"]) for r in eligible):
            chosen, status, tier, evidence = (
                [], "provisional", "provisional",
                "historically_supported_candidate",
            )
        else:
            chosen, status, tier, evidence = (
                [], "unresolved", "unresolved", "no_full_target_evidence"
            )
        competing = [r for r in eligible if r not in chosen]
        canonical.append({
            "tibetan_syllable": syllable,
            "canonical_forms": ";".join(r["latin_form"] for r in chosen),
            "canonical_status": status, "evidence_class": evidence,
            "canonical_confidence_tier": tier,
            "full_target_reviewed": "yes" if explicit else "no",
            "supporting_forms": ";".join(
                f"{r['latin_form']}:{r['current_clean_occurrences']}" for r in eligible
            ),
            "supporting_volumes": ";".join(sorted({
                v for r in chosen for v in r["distinct_volumes"].split(";") if v
            })),
            "competing_forms": ";".join(r["latin_form"] for r in competing),
            "competing_support": ";".join(
                f"{r['latin_form']}:independent={r['independent_teaching_occurrences']},"
                f"derived={int(r['current_clean_occurrences']) - int(r['independent_teaching_occurrences'])},"
                f"historical={r['historical_baseline_occurrences']},"
                f"domains={r['domain_breakdown']}"
                for r in competing
            ),
            "independent_teaching_occurrences": str(sum(
                int(r["independent_teaching_occurrences"]) for r in chosen
            )),
            "derived_occurrences": str(sum(
                int(r["current_clean_occurrences"])
                - int(r["independent_teaching_occurrences"]) for r in chosen
            )),
            "historical_occurrences": str(sum(
                int(r["historical_baseline_occurrences"]) for r in chosen
            )),
            "domain_breakdown": " || ".join(
                r["domain_breakdown"] for r in chosen
            ),
            "feature_coverage": "exact_canonical_route" if chosen else "unresolved",
            "rationale": (
                "Canonical selection uses exact non-circular teaching identities, "
                "domain-safe multi-volume/entry support, and quantitative "
                "competitor thresholds; corrected current frequency never votes."
            ),
        })

    canon_map = {
        r["tibetan_syllable"]: r for r in canonical
        if r["canonical_confidence_tier"] in {
            "canonical_reviewed", "canonical_independent_strong"
        } and r["canonical_forms"]
    }
    outliers: list[dict[str, str]] = []
    confusion_groups: dict[str, set[str]] = defaultdict(set)
    confusion_occurrences: Counter[str] = Counter()
    confusion_domains: dict[str, Counter[str]] = defaultdict(Counter)
    confusion_evidence: dict[str, set[str]] = defaultdict(set)
    confusion_types: dict[str, str] = {}
    for row in concordance:
        canon = canon_map.get(row["tibetan_syllable"])
        if not canon or row["latin_form"] in canon["canonical_forms"].split(";"):
            continue
        targets = canon["canonical_forms"].split(";")
        if len(targets) != 1:
            continue
        target = targets[0]
        source = row["latin_form"]
        operations = edit_operations(source, target)
        category = edit_category(operations)
        if (
            len(operations) == 1
            and source[:-1] == target[:-1]
            and source[-1:] in "nñńňh" and target.endswith("ṅ")
        ):
            category = "final_nasal_only_variant"
        outliers.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "current_source": source, "canonical_forms": target,
            "outlier_category": category,
            "edit_script": json.dumps(operations, ensure_ascii=False),
            "edit_signatures": ";".join(
                op["signature"] for op in operations
            ),
            "canonical_evidence": canon["evidence_class"],
            "canonical_confidence_tier": canon["canonical_confidence_tier"],
            "occurrence_count": row["current_clean_occurrences"],
            "domain_breakdown": row["domain_breakdown"],
            "damage_or_marker": (
                f"damage:{row['damaged_occurrences']};marker:{row['marker_attached_occurrences']}"
            ),
            "sample_contexts": row["sample_contexts"],
        })
        for operation in operations:
            signature = operation["signature"]
            confusion_groups[signature].add(row["tibetan_syllable"])
            confusion_occurrences[signature] += int(row["current_clean_occurrences"])
            confusion_domains[signature].update(
                {part.split(":", 1)[0]: int(part.rsplit(":", 1)[1])
                 for part in row["domain_breakdown"].split(";") if ":" in part}
            )
            confusion_evidence[signature].add(canon["canonical_confidence_tier"])
            confusion_types[signature] = operation["operation_type"]

    # Reviewed feature repairs are backtest evidence for an operation even
    # after the current release no longer contains their source form.
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    for override in overrides:
        evidence_scope, _teaching = correction_scope(override)
        if evidence_scope not in {
            "feature_only_root", "feature_only_final_nasal",
            "composed_repair",
        }:
            continue
        key = (
            override["volume"], override["page"], override["line"],
            override["token_index"],
        )
        aligned_row = aligned_by_key.get(key)
        if not aligned_row:
            continue
        for operation in edit_operations(
            override["from_token"], override["to_token"]
        ):
            signature = operation["signature"]
            confusion_groups[signature].add(aligned_row["tibetan_syllable"])
            confusion_occurrences[signature] += 1
            confusion_domains[signature]["ordinary_tibetan_lexical_or_compound"] += 1
            confusion_evidence[signature].add("reviewed_feature_repair")
            confusion_types[signature] = operation["operation_type"]

    decision_path = ROOT / "data/reviewed_tibetan_ocr_signature_decisions.tsv"
    signature_decisions = {
        row["signature"]: row for row in integrity.read_tsv(decision_path)
    } if decision_path.exists() else {}
    confusions = [{
        "operation_signature": signature,
        "operation_type": confusion_types[signature],
        "tibetan_role_context": signature_decisions.get(
            signature, {}
        ).get("tibetan_role", "unresolved")
        + (
            ":" + signature_decisions.get(signature, {}).get(
                "tibetan_feature", ""
            )
            if signature_decisions.get(signature, {}).get(
                "tibetan_feature", ""
            ) else ""
        ),
        "independent_tibetan_syllables": str(len(confusion_groups[signature])),
        "occurrences": str(confusion_occurrences[signature]),
        "domains": ";".join(
            f"{k}:{v}" for k, v in sorted(confusion_domains[signature].items())
        ),
        "canonical_evidence_classes": ";".join(
            sorted(confusion_evidence[signature])
        ),
        "reviewed_correction_support": signature_decisions.get(
            signature, {}
        ).get("evidence_summary", ""),
        "counterexamples": "",
        "collision_examples": "unrelated Latin Z/z excluded by Tibetan identity",
        "authorization_status": {
            "A": "authorized_exact_tibetan_conditioned",
            "D": "candidate_review", "R": "rejected",
        }.get(signature_decisions.get(signature, {}).get("decision", ""),
              "diagnostic_only"),
    } for signature in sorted(confusion_groups)]

    registry = integrity.load_registry()
    feature_candidates: list[dict[str, str]] = []
    for rule in registry:
        feature = rule["tibetan_feature"]
        realization = rule["expected_latin_feature"]
        supports: list[dict[str, str]] = []
        counters: list[dict[str, str]] = []
        for canon in canonical:
            if canon["canonical_confidence_tier"] not in {
                "canonical_reviewed", "canonical_independent_strong"
            }:
                continue
            roles = integrity.tibetan_roles(canon["tibetan_syllable"])
            role_key = (
                "suffix_coda"
                if rule["feature_type"] == "suffix_coda"
                else "root_consonant"
            )
            if roles.get(role_key) != feature:
                continue
            forms = canon["canonical_forms"].split(";")
            matches = (
                [form for form in forms if form.endswith(realization)]
                if role_key == "suffix_coda"
                else [form for form in forms if realization in form]
            )
            (supports if matches else counters).append(canon)
        feature_candidates.append({
            "tibetan_role": rule["feature_type"],
            "tibetan_feature": feature,
            "candidate_latin_realization": realization,
            "independent_canonical_syllables": str(len(supports)),
            "supporting_volumes": ";".join(sorted({
                volume for item in supports
                for volume in item["supporting_volumes"].split(";") if volume
            })),
            "reviewed_support": ";".join(
                item["tibetan_syllable"] for item in supports
                if item["canonical_confidence_tier"] == "canonical_reviewed"
            ),
            "historical_support": str(sum(
                int(item["historical_occurrences"]) for item in supports
            )),
            "counterexamples": str(len(counters)),
            "counterexample_domains": " || ".join(
                item["domain_breakdown"] for item in counters[:10]
            ),
            "likely_ocr_confusions":
                rule["known_ocr_confusable_alternatives"],
            "recommendation": (
                "promote" if rule["review_status"] in {"reviewed", "high_confidence"}
                and not counters
                else "ambiguous" if counters
                else "diagnostic_only"
            ),
        })
    root_ng_realizations: dict[str, list[dict[str, str]]] = defaultdict(list)
    for canon in canonical:
        if canon["canonical_confidence_tier"] not in {
            "canonical_reviewed", "canonical_independent_strong"
        }:
            continue
        if integrity.tibetan_roles(canon["tibetan_syllable"]).get(
            "root_consonant"
        ) != "ང":
            continue
        for form in canon["canonical_forms"].split(";"):
            if form:
                root_ng_realizations[form[0]].append(canon)
    for realization, supports in sorted(root_ng_realizations.items()):
        feature_candidates.append({
            "tibetan_role": "root_consonant",
            "tibetan_feature": "ང",
            "candidate_latin_realization": realization,
            "independent_canonical_syllables": str(len(supports)),
            "supporting_volumes": ";".join(sorted({
                volume for item in supports
                for volume in item["supporting_volumes"].split(";") if volume
            })),
            "reviewed_support": "",
            "historical_support": str(sum(
                int(item["historical_occurrences"]) for item in supports
            )),
            "counterexamples": "",
            "counterexample_domains": "",
            "likely_ocr_confusions": "",
            "recommendation": "diagnostic_only",
        })

    recent: list[dict[str, str]] = []
    for syllable, sources, target in [
        ("བཞི", "bZi;bzi", "bźi"),
        ("གཞི", "gZi;gzi", "gźi"),
        ("གཞུང", "gZuṅ", "gźuṅ"),
        ("བཞག", "bZag;bzag", "bźag"),
    ]:
        matching = [
            row for row in overrides
            if row["evidence"].startswith("tibetan_root_zha_integrity_")
            and row["to_token"] == target
        ]
        historical_target = any(
            item["tibetan_syllable"] == syllable
            and item["latin_form"] == target
            for item in historical.values()
        )
        recent.append({
            "tibetan_syllable": syllable, "source_variants": sources,
            "target": target, "corrected_count": str(len(matching)),
            "canonical_rationale": (
                "Reviewed root ཞ→ź plus independently attested/reviewed "
                "unchanged remainder of the exact syllable target."
            ),
            "historical_target_present": "yes" if historical_target else "no",
            "explicit_feature_support": "reviewed root_consonant ཞ→ź",
            "remainder_support": (
                "explicit_user_reviewed_full_target"
                if syllable == "གཞུང"
                else "historical exact full-form concordance"
            ),
            "derived_or_circular": "no",
            "disposition": "preserve",
        })
    return (
        concordance, canonical, feature_candidates, outliers, confusions,
        teaching_rows, recent,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    outputs = build()
    for name, rows, fields in [
        ("tibetan_latin_syllable_concordance.tsv", outputs[0], CONCORDANCE_FIELDS),
        ("tibetan_latin_canonical_syllables.tsv", outputs[1], CANONICAL_FIELDS),
        ("tibetan_latin_feature_rule_candidates.tsv", outputs[2], FEATURE_FIELDS),
        ("tibetan_latin_transcription_outliers.tsv", outputs[3], OUTLIER_FIELDS),
        ("tibetan_latin_ocr_confusion_signatures.tsv", outputs[4], CONFUSION_FIELDS),
        ("tibetan_latin_canonical_teaching_evidence.tsv", outputs[5], TEACHING_FIELDS),
        ("tibetan_latin_recent_root_zha_correction_audit.tsv", outputs[6], RECENT_AUDIT_FIELDS),
    ]:
        integrity.write_tsv(args.data_root / name, rows, fields)
    print(
        f"concordance_forms={len(outputs[0])} syllables={len(outputs[1])} "
        f"canonical_reviewed={sum(r['canonical_confidence_tier'] == 'canonical_reviewed' for r in outputs[1])} "
        f"canonical_strong={sum(r['canonical_confidence_tier'] == 'canonical_independent_strong' for r in outputs[1])} "
        f"provisional={sum(r['canonical_confidence_tier'] in {'canonical_independent_moderate', 'provisional'} for r in outputs[1])} "
        f"ambiguous={sum(r['canonical_status'] == 'ambiguous' for r in outputs[1])} "
        f"outliers={len(outputs[3])}"
    )


if __name__ == "__main__":
    main()
