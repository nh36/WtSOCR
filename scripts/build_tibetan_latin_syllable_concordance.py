#!/usr/bin/env python3
"""Build exact-Tibetan-syllable Latin concordance and canonical evidence."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_PATH = ROOT / "scripts/build_tibetan_latin_integrity.py"
SPEC = importlib.util.spec_from_file_location("tibetan_latin_integrity", INTEGRITY_PATH)
assert SPEC and SPEC.loader
integrity = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = integrity
SPEC.loader.exec_module(integrity)

BASELINE = "6322c7255cfba2fcfaf678cec656e65496ed5f12"
CONCORDANCE_FIELDS = [
    "tibetan_syllable", "latin_form", "current_clean_occurrences",
    "historical_baseline_occurrences", "distinct_volumes",
    "distinct_entry_clusters", "reviewed_exact_occurrences",
    "explicit_user_reviewed_occurrences", "google_adopted_occurrences",
    "other_postprocess_occurrences", "superseded_occurrences",
    "damaged_occurrences", "marker_attached_occurrences", "domain_breakdown",
    "alignment_breakdown", "gateway_breakdown", "correction_evidence_scope",
    "known_feature_violation_breakdown",
    "sample_contexts",
]
CANONICAL_FIELDS = [
    "tibetan_syllable", "canonical_forms", "canonical_status",
    "evidence_class", "full_target_reviewed", "supporting_forms",
    "supporting_volumes", "competing_forms", "feature_coverage",
    "rationale",
]
FEATURE_FIELDS = [
    "tibetan_role", "tibetan_feature", "candidate_latin_realization",
    "independent_canonical_syllables", "supporting_volumes",
    "reviewed_support", "historical_support", "counterexamples",
    "counterexample_domains", "likely_ocr_confusions", "recommendation",
]
OUTLIER_FIELDS = [
    "tibetan_syllable", "current_source", "canonical_forms",
    "outlier_category", "canonical_evidence", "occurrence_count",
    "domain_breakdown", "damage_or_marker", "sample_contexts",
]
CONFUSION_FIELDS = [
    "source_form", "canonical_form", "difference_class",
    "independent_tibetan_syllables", "occurrences", "domains",
    "authorization_status",
]


def git_show(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True,
        capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def historical_counts(ref: str = BASELINE) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        text = git_show(ref, f"release/current/qa/{volume}/{volume}_line_zones.tsv")
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            line = row.get("line_text", "")
            syllables, tail, _ = integrity.consensus.tibetan_syllables_and_tail(line)
            latin = integrity.consensus.latin_headword_tokens(tail, len(syllables))
            if syllables and len(latin) >= len(syllables):
                for syllable, (token, _start) in zip(syllables, latin):
                    counts[(syllable, token)] += 1
    return counts


def correction_scope(row: dict[str, str]) -> str:
    reason = row.get("reason", "")
    evidence = row.get("evidence", "")
    if "manual_multi_error" in reason or "explicit_user_review" in evidence:
        return "full_token_canonical_transcription"
    if "final_ng" in reason or "final_nasal" in reason:
        return "final_nasal_only"
    if "marker" in reason or "apostrophe" in reason:
        return "punctuation_or_marker_only"
    return "other_reviewed_feature"


def build() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
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
        (r["tibetan_syllable"], r["old_target"]) for r in supersessions
        if r["status"] == "active"
    }
    historical = historical_counts()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in aligned:
        grouped[(row["tibetan_syllable"], row["latin_token"])].append(row)
    concordance: list[dict[str, str]] = []
    for (syllable, form), rows in sorted(grouped.items()):
        diags = [
            diag_by_key[(r["volume"], r["page"], r["line"], r["token_index"])]
            for r in rows
        ]
        reviewed = [
            override_by_key[(r["volume"], r["page"], r["line"], r["token_index"])]
            for r in rows
            if (r["volume"], r["page"], r["line"], r["token_index"])
            in override_by_key
        ]
        clean = [
            d for d in diags if d["alignment_confidence"] in {
                "secure_positional_alignment", "secure_reviewed_alignment"
            } and d["damage_scope"] in {"none", "later_gloss_or_commentary"}
            and d["marker_attached"] == "no"
        ]
        domains = Counter(d["domain_context"] for d in diags)
        alignments = Counter(d["alignment_confidence"] for d in diags)
        gateways = Counter(d["transcription_gateway_status"] for d in diags)
        raw_checks = [
            integrity.token_integrity(
                r["tibetan_syllable"], r["latin_token"], use_canonical=False
            ) for r in rows
        ]
        concordance.append({
            "tibetan_syllable": syllable, "latin_form": form,
            "current_clean_occurrences": str(len(clean)),
            "historical_baseline_occurrences": str(historical[(syllable, form)]),
            "distinct_volumes": ";".join(sorted({r["volume"] for r in clean})),
            "distinct_entry_clusters": str(len({
                (r["volume"], r["page"]) for r in clean
            })),
            "reviewed_exact_occurrences": str(len(reviewed)),
            "explicit_user_reviewed_occurrences": str(sum(
                "explicit_user_review" in r.get("evidence", "") for r in reviewed
            )),
            "google_adopted_occurrences": "0",
            "other_postprocess_occurrences": "0",
            "superseded_occurrences": str(
                len(rows) if (syllable, form) in superseded else 0
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
            "known_feature_violation_breakdown": ";".join(
                f"{k}:{v}" for k, v in sorted(Counter(
                    c["known_feature_violation"] for c in raw_checks
                ).items())
            ),
            "correction_evidence_scope": ";".join(sorted({
                correction_scope(r) for r in reviewed
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
            if int(r["explicit_user_reviewed_occurrences"]) > 0
            and "full_token_canonical_transcription" in r["correction_evidence_scope"]
        ]
        multi = [
            r for r in eligible
            if int(r["current_clean_occurrences"]) >= 3
            and len(r["distinct_volumes"].split(";")) >= 2
            and "yes:" not in r["known_feature_violation_breakdown"]
        ]
        if len(explicit) == 1:
            chosen, status, evidence = explicit, "canonical", "explicit_user_reviewed"
        elif len(explicit) > 1:
            chosen, status, evidence = explicit, "ambiguous", "conflicting_explicit_review"
        elif len(multi) == 1:
            chosen, status, evidence = multi, "canonical", "independent_multi_context_canonical"
        elif len(multi) > 1:
            chosen, status, evidence = multi, "ambiguous", "credible_competing_forms"
        elif any(int(r["historical_baseline_occurrences"]) for r in eligible):
            chosen, status, evidence = [], "unresolved", "historically_supported_candidate"
        else:
            chosen, status, evidence = [], "unresolved", "no_full_target_evidence"
        canonical.append({
            "tibetan_syllable": syllable,
            "canonical_forms": ";".join(r["latin_form"] for r in chosen),
            "canonical_status": status, "evidence_class": evidence,
            "full_target_reviewed": "yes" if explicit else "no",
            "supporting_forms": ";".join(
                f"{r['latin_form']}:{r['current_clean_occurrences']}" for r in eligible
            ),
            "supporting_volumes": ";".join(sorted({
                v for r in chosen for v in r["distinct_volumes"].split(";") if v
            })),
            "competing_forms": ";".join(
                r["latin_form"] for r in eligible if r not in chosen
            ),
            "feature_coverage": "exact_canonical_route" if chosen else "unresolved",
            "rationale": (
                "Canonical selection requires full-target review or one uniquely "
                "supported multi-volume form; frequency alone is insufficient."
            ),
        })

    canon_map = {
        r["tibetan_syllable"]: r for r in canonical
        if r["canonical_status"] == "canonical" and r["canonical_forms"]
    }
    outliers: list[dict[str, str]] = []
    confusion_groups: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    confusion_occurrences: Counter[tuple[str, str, str]] = Counter()
    confusion_domains: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in concordance:
        canon = canon_map.get(row["tibetan_syllable"])
        if not canon or row["latin_form"] in canon["canonical_forms"].split(";"):
            continue
        targets = canon["canonical_forms"].split(";")
        if len(targets) != 1:
            continue
        target = targets[0]
        source = row["latin_form"]
        if source[:-1] == target[:-1] and source[-1:] in "nñńňh" and target.endswith("ṅ"):
            category = "final_nasal_only_variant"
        elif len(source) == len(target) and sum(a != b for a, b in zip(source, target)) == 1:
            category = "single_diacritic_confusion"
        else:
            category = "canonical_target_known_but_edit_unclassified"
        outliers.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "current_source": source, "canonical_forms": target,
            "outlier_category": category,
            "canonical_evidence": canon["evidence_class"],
            "occurrence_count": row["current_clean_occurrences"],
            "domain_breakdown": row["domain_breakdown"],
            "damage_or_marker": (
                f"damage:{row['damaged_occurrences']};marker:{row['marker_attached_occurrences']}"
            ),
            "sample_contexts": row["sample_contexts"],
        })
        key = (source, target, category)
        confusion_groups[key].add(row["tibetan_syllable"])
        confusion_occurrences[key] += int(row["current_clean_occurrences"])
        confusion_domains[key].add(row["domain_breakdown"])

    confusions = [{
        "source_form": key[0], "canonical_form": key[1],
        "difference_class": key[2],
        "independent_tibetan_syllables": str(len(confusion_groups[key])),
        "occurrences": str(confusion_occurrences[key]),
        "domains": " || ".join(sorted(confusion_domains[key])),
        "authorization_status": (
            "diagnostic_only" if len(confusion_groups[key]) < 2
            else "high_confidence_candidate_requires_review"
        ),
    } for key in sorted(confusion_groups)]

    feature_candidates = [{
        "tibetan_role": "root_consonant",
        "tibetan_feature": feature,
        "candidate_latin_realization": realization,
        "independent_canonical_syllables": str(count),
        "supporting_volumes": "",
        "reviewed_support": "registry_seed",
        "historical_support": "",
        "counterexamples": "",
        "counterexample_domains": "",
        "likely_ocr_confusions": alternatives,
        "recommendation": recommendation,
    } for feature, realization, count, alternatives, recommendation in [
        ("ཞ", "ź", 3, "Z;z", "promote"),
        ("ཉ", "ñ", 0, "n", "diagnostic_only"),
        ("ཤ", "ś", 0, "S;s;$", "ambiguous"),
        ("ང", "", 0, "", "diagnostic_only"),
    ]]
    return concordance, canonical, feature_candidates, outliers, confusions


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
        ("tibetan_latin_ocr_confusion_candidates.tsv", outputs[4], CONFUSION_FIELDS),
    ]:
        integrity.write_tsv(args.data_root / name, rows, fields)
    print(
        f"concordance_forms={len(outputs[0])} syllables={len(outputs[1])} "
        f"canonical={sum(r['canonical_status'] == 'canonical' for r in outputs[1])} "
        f"ambiguous={sum(r['canonical_status'] == 'ambiguous' for r in outputs[1])} "
        f"outliers={len(outputs[3])}"
    )


if __name__ == "__main__":
    main()
