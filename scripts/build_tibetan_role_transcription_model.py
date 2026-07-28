#!/usr/bin/env python3
"""Build corpus-internal Tibetan-role transcription evidence.

This module parses Tibetan orthographic roles without consulting Latin text,
then mines role contrasts only from non-circular canonical evidence.  It is
deliberately not a Tibetan transliterator.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import hashlib
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


integrity = load_module(
    "role_model_integrity", ROOT / "scripts/build_tibetan_latin_integrity.py"
)
canonical_builder = load_module(
    "role_model_canonical",
    ROOT / "scripts/build_tibetan_latin_syllable_concordance.py",
)

SOURCE_SCOPE_PATH = ROOT / "data/reviewed_correction_source_scopes.tsv"
SOURCE_SHADOW_PATH = ROOT / "data/tibetan_latin_reviewed_source_dispositions.tsv"
CANONICAL_PATH = ROOT / "data/tibetan_latin_canonical_syllables.tsv"
CONCORDANCE_PATH = ROOT / "data/tibetan_latin_syllable_concordance.tsv"
DECISIONS_PATH = ROOT / "data/reviewed_tibetan_feature_mapping_decisions.tsv"

PREFIXES = set("གདབམའ")
SUPERSCRIPTS = set("རལས")
SUBJOINED_MEDIALS = set("ཡརལཝ")
SUFFIXES = set("གངདནབམའརལས")
POST_SUFFIXES = {"ད", "ས"}
VOWELS = {"ི": "i", "ུ": "u", "ེ": "e", "ོ": "o"}
ROLE_ORDER = (
    "prefix", "superscript", "root_consonant", "subjoined_consonants",
    "vowel", "suffix_coda", "post_suffix",
)

PARSE_FIELDS = [
    "tibetan_syllable", "prefix", "superscript", "root_consonant",
    "subjoined_consonants", "vowel", "suffix_coda", "post_suffix",
    "orthographic_stack", "ambiguous_root_candidates",
    "role_parse_status", "role_parse_confidence", "rationale",
]
FEATURE_EVIDENCE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "latin_source", "latin_target", "tibetan_role", "tibetan_feature",
    "latin_realization", "structural_unit", "evidence_provenance",
    "source_or_target", "independence_class", "feature_teaching_status",
    "domain", "alignment", "confidence",
]
MAPPING_FIELDS = [
    "rule_id", "tibetan_role", "tibetan_feature", "structural_context",
    "proposed_latin_realization", "strong_canonical_syllables",
    "independent_feature_evidence_identities", "reviewed_explicit_support",
    "unaffected_reviewed_source_support", "minimal_pair_support",
    "alternate_witness_support", "supporting_volumes", "counterexamples",
    "competing_realizations", "domain_breakdown", "confidence",
    "recommendation",
]
BACKTEST_FIELDS = [
    "tibetan_syllable", "hidden_canonical_target", "canonical_tier",
    "role_parse_status", "prediction", "component_rule_ids",
    "leave_one_out_status", "reconstruction_status", "missing_roles",
]
COMPOSITION_FIELDS = [
    "tibetan_syllable", "observed_forms", "current_canonical_tier",
    "role_parse_status", "composition_status", "feature_composed_target",
    "component_rule_ids", "supporting_evidence_ids",
    "leave_one_out_status", "domain_compatibility", "correction_authority",
    "blocker",
]
DOMAIN_FIELDS = [
    "rule_id", "ordinary_lexical_support", "proper_name_support",
    "sanskrit_foreign_support", "unclear_support", "conflicts",
    "proper_name_compatible", "rationale",
]
GRAPH_FIELDS = [
    "from_node", "edge_type", "to_node", "evidence_identity",
    "teaching_allowed",
]


def read(path: Path) -> list[dict[str, str]]:
    return integrity.read_tsv(path)


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    integrity.write_tsv(path, rows, fields)


def base_consonant(char: str) -> str:
    code = ord(char)
    if 0x0F90 <= code <= 0x0FBC:
        candidate = chr(code - 0x50)
        return candidate if "\u0f40" <= candidate <= "\u0f6c" else ""
    return char if "\u0f40" <= char <= "\u0f6c" else ""


def _suffix_split(bases: list[str], onset_end: int) -> tuple[list[str], str, str]:
    trailing = bases[onset_end:]
    if not trailing:
        return [], "", ""
    if (
        len(trailing) >= 2 and trailing[-1] in POST_SUFFIXES
        and trailing[-2] in SUFFIXES
    ):
        return trailing[:-2], trailing[-2], trailing[-1]
    if trailing[-1] in SUFFIXES:
        return trailing[:-1], trailing[-1], ""
    return trailing, "", ""


def parse_tibetan_syllable(syllable: str) -> dict[str, str]:
    """Conservatively recover orthographic roles from Tibetan Unicode alone."""
    chars = [
        c for c in unicodedata.normalize("NFC", syllable)
        if c not in "་།༔ " and not unicodedata.category(c).startswith("M")
    ]
    # Tibetan vowel/subjoined signs are combining marks, so collect them from
    # the unfiltered input before interpreting consonant structure.
    original = list(unicodedata.normalize("NFC", syllable))
    vowel_signs = [c for c in original if c in VOWELS]
    subjoined_positions = [
        (index, base_consonant(c)) for index, c in enumerate(original)
        if 0x0F90 <= ord(c) <= 0x0FBC and base_consonant(c)
    ]
    base_positions = [
        (index, c) for index, c in enumerate(original)
        if "\u0f40" <= c <= "\u0f6c"
    ]
    result = {
        "tibetan_syllable": syllable, "prefix": "", "superscript": "",
        "root_consonant": "", "subjoined_consonants": "",
        "vowel": (
            VOWELS[vowel_signs[0]] if len(vowel_signs) == 1
            else "a" if not vowel_signs else ""
        ),
        "suffix_coda": "", "post_suffix": "", "orthographic_stack": "",
        "ambiguous_root_candidates": "", "role_parse_status": "unparsed",
        "role_parse_confidence": "none", "rationale": "",
    }
    if not base_positions or len(vowel_signs) > 1:
        result["rationale"] = "No base consonant or multiple vowel signs."
        return result

    bases = [c for _, c in base_positions]
    if subjoined_positions:
        first_sub_index, first_sub = subjoined_positions[0]
        preceding = [item for item in base_positions if item[0] < first_sub_index]
        following = [item for item in base_positions if item[0] > first_sub_index]
        if not preceding:
            result["rationale"] = "Subjoined stack lacks a visible base."
            return result
        stack_base = preceding[-1][1]
        if stack_base in SUPERSCRIPTS and first_sub not in SUBJOINED_MEDIALS:
            root = first_sub
            superscript = stack_base
            subjoined = "".join(c for _, c in subjoined_positions[1:])
            onset_bases = preceding[:-1]
        else:
            root = stack_base
            superscript = ""
            subjoined = "".join(c for _, c in subjoined_positions)
            onset_bases = preceding[:-1]
        prefix = onset_bases[-1][1] if len(onset_bases) == 1 \
            and onset_bases[-1][1] in PREFIXES else ""
        unresolved_onset = onset_bases[:-1] if prefix else onset_bases
        trailing_bases = [c for _, c in following]
        leftovers, suffix, post = _suffix_split(trailing_bases, 0)
        result.update({
            "prefix": prefix, "superscript": superscript,
            "root_consonant": root, "subjoined_consonants": subjoined,
            "suffix_coda": suffix, "post_suffix": post,
            "orthographic_stack": superscript + root + subjoined,
        })
        if unresolved_onset or leftovers:
            result["role_parse_status"] = "partially_resolved"
            result["role_parse_confidence"] = "medium"
            result["ambiguous_root_candidates"] = ";".join(
                dict.fromkeys(
                    [c for _, c in unresolved_onset] + leftovers
                )
            )
            result["rationale"] = "Stack resolved; extra consonants remain ambiguous."
        else:
            result["role_parse_status"] = "fully_resolved"
            result["role_parse_confidence"] = "high"
            result["rationale"] = "Unicode stack and trailing suffix roles resolve uniquely."
        return result

    candidates: list[dict[str, str]] = []
    for root_index, root in enumerate(bases):
        before, after = bases[:root_index], bases[root_index + 1:]
        if len(before) > 1 or (before and before[0] not in PREFIXES):
            continue
        leftovers, suffix, post = _suffix_split(after, 0)
        if leftovers:
            continue
        candidates.append({
            "prefix": before[0] if before else "", "root_consonant": root,
            "suffix_coda": suffix, "post_suffix": post,
        })
    # Prefer a prefix interpretation when it is the only candidate supported
    # by a recognized prefix and a valid suffix sequence.
    unique = {
        (c["prefix"], c["root_consonant"], c["suffix_coda"], c["post_suffix"]):
        c for c in candidates
    }
    candidates = list(unique.values())
    if len(candidates) == 1:
        chosen = candidates[0]
        result.update(chosen)
        result["orthographic_stack"] = chosen["root_consonant"]
        result["role_parse_status"] = "fully_resolved"
        result["role_parse_confidence"] = "high"
        result["rationale"] = "One prefix/root/suffix parse is structurally possible."
    elif candidates:
        result["ambiguous_root_candidates"] = ";".join(
            dict.fromkeys(c["root_consonant"] for c in candidates)
        )
        result["role_parse_status"] = "ambiguous_root"
        result["role_parse_confidence"] = "low"
        result["rationale"] = "Multiple Tibetan-only root parses remain possible."
    else:
        result["role_parse_status"] = "unusual_stack"
        result["role_parse_confidence"] = "none"
        result["rationale"] = "Consonant sequence does not match conservative role patterns."
    return result


def identity(row: dict[str, str]) -> str:
    return ":".join(
        row.get(field, "") for field in ("volume", "page", "line", "token_index")
    )


def changed_spans(source: str, target: str) -> list[dict[str, str]]:
    return canonical_builder.edit_operations(source, target)


def feature_teaching_evidence(
    parses: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diag = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in integrity.build_diagnostics(ROOT / "release/current")
    }
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    source_scopes = {r["reason"]: r for r in read(SOURCE_SCOPE_PATH)}
    evidence: list[dict[str, str]] = []
    for override in read(integrity.OVERRIDES_PATH):
        key = tuple(override[f] for f in ("volume", "page", "line", "token_index"))
        row = aligned_by_key.get(key)
        check = diag.get(key, {})
        if not row:
            continue
        parse = parses.get(row["tibetan_syllable"], {})
        scope = source_scopes[override["reason"]]
        operations = changed_spans(override["from_token"], override["to_token"])
        common = {
            "volume": override["volume"], "page": override["page"],
            "line": override["line"], "token_index": override["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "latin_source": override["from_token"],
            "latin_target": override["to_token"],
            "evidence_provenance": override["reason"],
            "domain": check.get("domain_context", ""),
            "alignment": check.get("alignment_confidence", ""),
        }
        if scope["source_disposition"] in {
            "full_source_noncanonical", "superseded_wrong_target",
            "unknown_source_disposition",
        }:
            evidence.append({
                **common, "tibetan_role": "", "tibetan_feature": "",
                "latin_realization": "", "structural_unit": "full_token",
                "source_or_target": "source", "independence_class": "reviewed",
                "feature_teaching_status": "not_feature_evidence",
                "confidence": "high",
            })
            continue
        if scope["corrected_tibetan_roles"] == "suffix_coda" \
                and override["to_token"].endswith("ṅ"):
            if parse.get("suffix_coda") != "ང":
                evidence.append({
                    **common, "tibetan_role": "suffix_coda",
                    "tibetan_feature": "", "latin_realization": "",
                    "structural_unit": "token_final",
                    "source_or_target": "target",
                    "independence_class": "reviewed",
                    "feature_teaching_status": "role_unresolved",
                    "confidence": "none",
                })
                continue
            evidence.append({
                **common, "tibetan_role": "suffix_coda",
                "tibetan_feature": parse.get("suffix_coda", ""),
                "latin_realization": "ṅ", "structural_unit": "token_final",
                "source_or_target": "target", "independence_class": "reviewed",
                "feature_teaching_status": "reviewed_explicit_feature_evidence",
                "confidence": "high",
            })
            if scope["unaffected_source_may_teach"] == "yes":
                evidence.append({
                    **common, "tibetan_role": "pre_coda_structural_unit",
                    "tibetan_feature": row["tibetan_syllable"][:-1],
                    "latin_realization": override["from_token"][:-1],
                    "structural_unit": "pre_coda_stem",
                    "source_or_target": "source",
                    "independence_class": "historical_source",
                    "feature_teaching_status":
                        "unaffected_feature_from_reviewed_source",
                    "confidence": "medium",
                })
            continue
        if scope["corrected_tibetan_roles"] == "root_consonant" \
                and parse.get("root_consonant") == "ཞ" \
                and "ź" in override["to_token"]:
            evidence.append({
                **common, "tibetan_role": "root_consonant",
                "tibetan_feature": "ཞ", "latin_realization": "ź",
                "structural_unit": "root", "source_or_target": "target",
                "independence_class": "reviewed",
                "feature_teaching_status": "reviewed_explicit_feature_evidence",
                "confidence": "high",
            })
        if scope["unaffected_source_may_teach"] == "yes" and operations:
            unchanged = override["from_token"]
            for op in sorted(
                operations, key=lambda item: int(item["source_position"]),
                reverse=True,
            ):
                start = int(op["source_position"])
                unchanged = unchanged[:start] + "□" + unchanged[
                    start + len(op["source_span"]):
                ]
            evidence.append({
                **common, "tibetan_role": "unsegmented_structural_unit",
                "tibetan_feature": row["tibetan_syllable"],
                "latin_realization": unchanged,
                "structural_unit": "unaffected_span_support",
                "source_or_target": "source",
                "independence_class": "historical_source",
                "feature_teaching_status":
                    "unaffected_feature_from_reviewed_source",
                "confidence": "medium",
            })
    return evidence


def canonical_forms() -> list[dict[str, str]]:
    return [
        row for row in read(CANONICAL_PATH)
        if row["canonical_confidence_tier"] in {
            "canonical_reviewed", "canonical_independent_strong"
        } and row["canonical_forms"] and ";" not in row["canonical_forms"]
    ]


def contrastive_candidates(
    canonical: list[dict[str, str]],
    parses: dict[str, dict[str, str]],
    feature_evidence: list[dict[str, str]],
) -> list[dict[str, str]]:
    items = [
        (row, parses[row["tibetan_syllable"]])
        for row in canonical
        if parses[row["tibetan_syllable"]]["role_parse_status"]
        == "fully_resolved"
    ]
    support: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    pairs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    volumes: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    competing: dict[tuple[str, str], set[str]] = defaultdict(set)
    for index, (left, lp) in enumerate(items):
        left_roles = tuple(lp[r] for r in ROLE_ORDER)
        for right, rp in items[index + 1:]:
            right_roles = tuple(rp[r] for r in ROLE_ORDER)
            differing = [
                role for role, a, b in zip(ROLE_ORDER, left_roles, right_roles)
                if a != b
            ]
            if len(differing) != 1:
                continue
            operations = canonical_builder.edit_operations(
                left["canonical_forms"], right["canonical_forms"]
            )
            if len(operations) != 1:
                continue
            op = operations[0]
            role = differing[0]
            left_real, right_real = op["source_span"], op["target_span"]
            for row, parse, realization in (
                (left, lp, left_real), (right, rp, right_real)
            ):
                feature = parse[role]
                key = (role, feature, realization)
                support[key].add(row["tibetan_syllable"])
                pairs[key].add(
                    f"{left['tibetan_syllable']}:{left['canonical_forms']}↔"
                    f"{right['tibetan_syllable']}:{right['canonical_forms']}"
                )
                volumes[key].update(
                    v for v in row["supporting_volumes"].split(";") if v
                )
                competing[(role, feature)].add(realization)

    explicit = {
        (r["tibetan_role"], r["tibetan_feature"], r["latin_realization"])
        for r in feature_evidence
        if r["feature_teaching_status"] == "reviewed_explicit_feature_evidence"
    }
    decisions = {
        (r["tibetan_role"], r["tibetan_feature"], r["latin_realization"]): r
        for r in read(DECISIONS_PATH) if r["decision"] == "A"
    }
    keys = set(support) | explicit | set(decisions)
    rows: list[dict[str, str]] = []
    def automatic_rule_id(key: tuple[str, str, str]) -> str:
        digest = hashlib.sha1(
            "\u241f".join(key).encode("utf-8")
        ).hexdigest()[:12].upper()
        return f"CORPUS_{digest}"

    for role, feature, realization in sorted(keys):
        key = (role, feature, realization)
        alternatives = competing.get((role, feature), set()) - {realization}
        reviewed_count = sum(
            r["tibetan_role"] == role and r["tibetan_feature"] == feature
            and r["latin_realization"] == realization
            and r["feature_teaching_status"]
            == "reviewed_explicit_feature_evidence"
            for r in feature_evidence
        )
        if key in decisions:
            confidence, recommendation = "reviewed", "feature_reviewed"
            rule_id = decisions[key]["rule_id"]
        elif len(support[key]) >= 3 and len(pairs[key]) >= 2 and not alternatives:
            confidence, recommendation = (
                "high", "feature_independent_strong_candidate",
            )
            rule_id = automatic_rule_id(key)
        elif support[key]:
            confidence, recommendation = "provisional", "feature_provisional"
            rule_id = automatic_rule_id(key)
        else:
            confidence, recommendation = "reviewed", "feature_reviewed"
            rule_id = decisions.get(key, {}).get("rule_id", "REVIEWED")
        rows.append({
            "rule_id": rule_id, "tibetan_role": role,
            "tibetan_feature": feature, "structural_context": "contrastive",
            "proposed_latin_realization": realization,
            "strong_canonical_syllables": ";".join(sorted(support[key])),
            "independent_feature_evidence_identities": "",
            "reviewed_explicit_support": str(reviewed_count),
            "unaffected_reviewed_source_support": str(sum(
                r["tibetan_role"] == role and r["tibetan_feature"] == feature
                and r["latin_realization"] == realization
                and r["feature_teaching_status"]
                == "unaffected_feature_from_reviewed_source"
                for r in feature_evidence
            )),
            "minimal_pair_support": " || ".join(sorted(pairs[key])),
            "alternate_witness_support": "0",
            "supporting_volumes": ";".join(sorted(volumes[key])),
            "counterexamples": "",
            "competing_realizations": ";".join(sorted(alternatives)),
            "domain_breakdown": "ordinary_tibetan_lexical_or_compound",
            "confidence": confidence, "recommendation": recommendation,
        })
    return rows


def authoritative_rules(
    candidates: list[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    decisions = {
        row["rule_id"]: row for row in read(DECISIONS_PATH)
        if row["decision"] == "A"
    }
    result = {}
    for row in candidates:
        decision = decisions.get(row["rule_id"])
        if not decision:
            continue
        result[(row["tibetan_role"], row["tibetan_feature"])] = {
            **row, **decision,
        }
    return result


def compose(
    parse: dict[str, str],
    rules: dict[tuple[str, str], dict[str, str]],
    *,
    excluded_syllable: str = "",
    candidates: list[dict[str, str]] | None = None,
) -> tuple[str, list[str], list[str]]:
    spans: list[str] = []
    rule_ids: list[str] = []
    missing: list[str] = []
    if parse["role_parse_status"] != "fully_resolved":
        return "", [], ["orthographic_role_unresolved"]
    # The corpus writes an explicit separator for the resolved ག + ཡ onset
    # (for example g.yo).  Independent role rules for g and y cannot silently
    # erase that cluster-conditioned punctuation.
    if parse["prefix"] == "ག" and parse["root_consonant"] == "ཡ":
        return "", [], ["cluster:ག+ཡ:conditioned_separator_unresolved"]
    for role in ROLE_ORDER:
        feature = parse[role]
        if not feature:
            continue
        rule = rules.get((role, feature))
        if not rule:
            missing.append(f"{role}:{feature}")
            continue
        if excluded_syllable and candidates:
            supports = set(
                rule.get("strong_canonical_syllables", "").split(";")
            ) - {"", excluded_syllable}
            if rule.get("recommendation") != "feature_reviewed" and not supports:
                missing.append(f"{role}:{feature}:leave_one_out")
                continue
        spans.append(rule["latin_realization"])
        rule_ids.append(rule["rule_id"])
    return "".join(spans) if not missing else "", rule_ids, missing


def build() -> tuple[list[dict[str, str]], ...]:
    canonical = canonical_forms()
    syllables = {
        row["tibetan_syllable"] for row in read(CONCORDANCE_PATH)
    } | {row["tibetan_syllable"] for row in canonical}
    parse_rows = [parse_tibetan_syllable(s) for s in sorted(syllables)]
    parses = {row["tibetan_syllable"]: row for row in parse_rows}
    feature_evidence = feature_teaching_evidence(parses)
    candidates = contrastive_candidates(canonical, parses, feature_evidence)
    rules = authoritative_rules(candidates)

    backtest: list[dict[str, str]] = []
    canonical_by_syllable = {r["tibetan_syllable"]: r for r in canonical}
    for row in canonical:
        parse = parses[row["tibetan_syllable"]]
        prediction, rule_ids, missing = compose(
            parse, rules, excluded_syllable=row["tibetan_syllable"],
            candidates=candidates,
        )
        if prediction == row["canonical_forms"]:
            status = "exact_reconstruction"
        elif prediction:
            status = "wrong_reconstruction"
        elif missing:
            status = "partial_reconstruction"
        else:
            status = "ambiguous"
        backtest.append({
            "tibetan_syllable": row["tibetan_syllable"],
            "hidden_canonical_target": row["canonical_forms"],
            "canonical_tier": row["canonical_confidence_tier"],
            "role_parse_status": parse["role_parse_status"],
            "prediction": prediction,
            "component_rule_ids": ";".join(rule_ids),
            "leave_one_out_status": "passed" if prediction else "insufficient",
            "reconstruction_status": status,
            "missing_roles": ";".join(missing),
        })

    concordance_by_syllable: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read(CONCORDANCE_PATH):
        concordance_by_syllable[row["tibetan_syllable"]].append(row)
    composition: list[dict[str, str]] = []
    for syllable, forms in sorted(concordance_by_syllable.items()):
        existing = canonical_by_syllable.get(syllable)
        current_tier = (
            existing["canonical_confidence_tier"] if existing else next(
                (r["canonical_confidence_tier"] for r in read(CANONICAL_PATH)
                 if r["tibetan_syllable"] == syllable), "unresolved"
            )
        )
        prediction, rule_ids, missing = compose(
            parses[syllable], rules, excluded_syllable=syllable,
            candidates=candidates,
        )
        if prediction:
            status, authority, blocker = (
                "feature_complete_unique", "yes", "",
            )
        elif parses[syllable]["role_parse_status"] != "fully_resolved":
            status, authority, blocker = (
                "role_parse_unresolved", "no",
                parses[syllable]["role_parse_status"],
            )
        else:
            status, authority, blocker = (
                "feature_partial", "no", ";".join(missing),
            )
        composition.append({
            "tibetan_syllable": syllable,
            "observed_forms": ";".join(r["latin_form"] for r in forms),
            "current_canonical_tier": current_tier,
            "role_parse_status": parses[syllable]["role_parse_status"],
            "composition_status": status,
            "feature_composed_target": prediction,
            "component_rule_ids": ";".join(rule_ids),
            "supporting_evidence_ids": ";".join(rule_ids),
            "leave_one_out_status": "passed" if prediction else "insufficient",
            "domain_compatibility": "ordinary_only",
            "correction_authority": authority,
            "blocker": blocker,
        })

    domain: list[dict[str, str]] = []
    canonical_targets = {
        row["tibetan_syllable"]: row["canonical_forms"]
        for row in canonical
    }
    teaching = read(
        ROOT / "data/tibetan_latin_canonical_teaching_evidence.tsv"
    )
    for rule in rules.values():
        domain_support: dict[str, set[str]] = defaultdict(set)
        for item in teaching:
            syllable = item["tibetan_syllable"]
            if item["latin_form"] != canonical_targets.get(syllable):
                continue
            parse = parses.get(syllable, {})
            role, feature = rule["tibetan_role"], rule["tibetan_feature"]
            if parse.get(role) != feature:
                continue
            realization = rule["latin_realization"]
            form = item["latin_form"]
            if role in {"suffix_coda", "post_suffix"}:
                matches = form.endswith(realization)
            elif role == "prefix":
                matches = form.startswith(realization)
            else:
                matches = realization in form
            if matches:
                domain_support[item["domain_context"]].add(syllable)
        proper_count = len(domain_support["tibetan_proper_name"])
        ordinary_count = len(
            domain_support["ordinary_tibetan_lexical_or_compound"]
        )
        domain.append({
            "rule_id": rule["rule_id"],
            "ordinary_lexical_support": str(ordinary_count),
            "proper_name_support": str(proper_count),
            "sanskrit_foreign_support": str(len(
                domain_support["sanskrit_or_indic_transcription"]
            )),
            "unclear_support": str(len(domain_support["unclear"])),
            "conflicts": "",
            "proper_name_compatible": "yes" if proper_count >= 3 else "no",
            "rationale": (
                "Proper-name compatibility requires the reviewed/strong exact "
                "canonical realization in at least three independent proper-name "
                "syllables; ordinary lexical authority is never inherited alone."
            ),
        })

    graph: list[dict[str, str]] = []
    for row in feature_evidence:
        graph.append({
            "from_node": "identity:" + identity(row),
            "edge_type": row["feature_teaching_status"],
            "to_node": (
                f"feature:{row['tibetan_role']}:{row['tibetan_feature']}:"
                f"{row['latin_realization']}"
            ),
            "evidence_identity": identity(row),
            "teaching_allowed": (
                "yes" if row["feature_teaching_status"] in {
                    "independent_full_form_feature_evidence",
                    "reviewed_explicit_feature_evidence",
                    "unaffected_feature_from_reviewed_source",
                } else "no"
            ),
        })
    for row in composition:
        if row["correction_authority"] != "yes":
            continue
        for rule_id in row["component_rule_ids"].split(";"):
            graph.append({
                "from_node": "feature_rule:" + rule_id,
                "edge_type": "composes",
                "to_node": "canonical_feature_composed:" + row["tibetan_syllable"],
                "evidence_identity": row["tibetan_syllable"],
                "teaching_allowed": "no",
            })
    validate_no_cycles(graph)
    return (
        parse_rows, feature_evidence, candidates, backtest, composition,
        domain, graph,
    )


def validate_no_cycles(graph: list[dict[str, str]]) -> None:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph:
        if edge["teaching_allowed"] == "yes":
            adjacency[edge["from_node"]].add(edge["to_node"])
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError(f"Transcription evidence cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in list(adjacency):
        visit(node)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    outputs = build()
    for name, rows, fields in [
        ("tibetan_orthographic_parse.tsv", outputs[0], PARSE_FIELDS),
        ("tibetan_latin_feature_teaching_evidence.tsv", outputs[1],
         FEATURE_EVIDENCE_FIELDS),
        ("tibetan_latin_role_mapping_candidates.tsv", outputs[2],
         MAPPING_FIELDS),
        ("tibetan_latin_feature_composition_backtest.tsv", outputs[3],
         BACKTEST_FIELDS),
        ("tibetan_latin_feature_composition_queue.tsv", outputs[4],
         COMPOSITION_FIELDS),
        ("tibetan_latin_domain_compatibility.tsv", outputs[5], DOMAIN_FIELDS),
        ("tibetan_transcription_evidence_graph.tsv", outputs[6], GRAPH_FIELDS),
    ]:
        write(args.data_root / name, rows, fields)
    counts = Counter(r["role_parse_status"] for r in outputs[0])
    backtest = Counter(r["reconstruction_status"] for r in outputs[3])
    composition = Counter(r["composition_status"] for r in outputs[4])
    print(
        f"parses={dict(counts)} feature_evidence={len(outputs[1])} "
        f"mapping_candidates={len(outputs[2])} backtest={dict(backtest)} "
        f"composition={dict(composition)}"
    )


if __name__ == "__main__":
    main()
