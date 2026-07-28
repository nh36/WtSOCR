#!/usr/bin/env python3
"""Build Gate-0 alignment and reviewed-source teaching audits."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRE_TOKENIZER_REF = "014761af93d7a7f9da90437b921f31353ed1bfe5"
POST_TOKENIZER_REF = "1779ff9"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


integrity = load_module(
    "gate0_integrity", ROOT / "scripts/build_tibetan_latin_integrity.py"
)
canonical = load_module(
    "gate0_canonical", ROOT / "scripts/build_tibetan_latin_syllable_concordance.py"
)
signatures = load_module(
    "gate0_signatures",
    ROOT / "scripts/build_tibetan_latin_ocr_signature_evidence.py",
)

SOURCE_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "observed_source", "reviewed_target", "correction_reason",
    "correction_evidence", "evidence_scope", "source_disposition",
    "corrected_tibetan_roles", "corrected_latin_spans",
    "unaffected_source_may_teach", "intentional_variant",
    "target_establishment", "target_teaching_disposition",
    "active_or_superseded",
]
SOURCE_SCOPE_PATH = ROOT / "data/reviewed_correction_source_scopes.tsv"
RECENT_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "observed_source", "reviewed_target", "canonical_target_tier",
    "signature_decision", "signature_condition_match",
    "token_boundary_status", "domain_context", "damage_scope",
    "marker_attached", "prior_identity_decision",
    "target_teaching_disposition", "audit_disposition", "context_excerpt",
]
MIGRATION_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "old_token", "current_token", "migration_class", "context_excerpt",
]
GLYPH_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "captured_token", "adjacent_glyph", "boundary_status",
    "review_disposition", "context_excerpt",
]
CANONICAL_MIGRATION_FIELDS = [
    "tibetan_syllable", "previous_canonical_forms", "previous_tier",
    "current_canonical_forms", "current_tier", "migration_reason",
    "migration_direction", "audit_disposition",
]
FINAL_RECONCILIATION_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_token", "proposed_target", "general_canonical_tier",
    "general_source_alignment_status", "required_signatures",
    "signature_applicability", "prior_identity_decision",
    "final_ng_evidence_class", "effective_disposition", "context_excerpt",
]
FINAL_MIGRATION_FIELDS = [
    "volume", "page", "line", "token_index", "tibetan_syllable",
    "source_token", "target", "comparison_stage", "before_or_after", "migration_class",
    "context_excerpt",
]


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, delimiter="\t", lineterminator="\n", fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(rows)


def ref_diagnostics(ref: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        path = (
            f"release/current/qa/{volume}/tibetan_cleanup_diagnostics/"
            "tibetan_latin_integrity_candidates.tsv"
        )
        text = canonical.git_show(ref, path)
        rows.extend(csv.DictReader(io.StringIO(text), delimiter="\t"))
    return rows


def source_shadow(
    aligned: list[dict[str, str]],
) -> list[dict[str, str]]:
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    historical = canonical.historical_identities()
    scopes = canonical.scope_registry()
    source_scopes = {
        row["reason"]: row for row in integrity.read_tsv(SOURCE_SCOPE_PATH)
    }
    missing = {
        row["reason"] for row in integrity.read_tsv(integrity.OVERRIDES_PATH)
        if row["reason"] not in source_scopes
    }
    if missing:
        raise ValueError(
            "Correction reasons lack persistent source-scope semantics: "
            + ", ".join(sorted(missing))
        )
    rows: list[dict[str, str]] = []
    for override in integrity.read_tsv(integrity.OVERRIDES_PATH):
        key = (
            override["volume"], override["page"], override["line"],
            override["token_index"],
        )
        aligned_row = aligned_by_key.get(key)
        historical_row = historical.get(key, {})
        scope = scopes.get(override["reason"], {})
        source_scope = source_scopes[override["reason"]]
        rows.append({
            "volume": override["volume"], "page": override["page"],
            "line": override["line"], "token_index": override["token_index"],
            "tibetan_syllable": (
                aligned_row or historical_row
            ).get("tibetan_syllable", ""),
            "observed_source": override["from_token"],
            "reviewed_target": override["to_token"],
            "correction_reason": override["reason"],
            "correction_evidence": override.get("evidence", ""),
            "evidence_scope": scope.get("evidence_scope", "other"),
            "source_disposition": source_scope["source_disposition"],
            "corrected_tibetan_roles":
                source_scope["corrected_tibetan_roles"],
            "corrected_latin_spans": source_scope["corrected_latin_spans"],
            "unaffected_source_may_teach":
                source_scope["unaffected_source_may_teach"],
            "intentional_variant": source_scope["intentional_variant"],
            "target_establishment": source_scope["target_establishment"],
            "target_teaching_disposition": scope.get(
                "canonical_teaching_status", "not_teaching_evidence"
            ),
            "active_or_superseded": "active",
        })
    for item in integrity.read_tsv(integrity.SUPERSESSIONS_PATH):
        if item.get("status") != "active":
            continue
        rows.append({
            "volume": item["volume"], "page": item["page"],
            "line": item["line"], "token_index": item["token_index"],
            "tibetan_syllable": item.get("tibetan_syllable", ""),
            "observed_source": item["old_target"],
            "reviewed_target": item["superseding_target"],
            "correction_reason": item["supersession_reason"],
            "correction_evidence": item["evidence"],
            "evidence_scope": "other",
            "source_disposition": "superseded_wrong_target",
            "corrected_tibetan_roles": "multiple",
            "corrected_latin_spans": "full_token",
            "unaffected_source_may_teach": "no",
            "intentional_variant": "no",
            "target_establishment": "superseded",
            "target_teaching_disposition": "not_teaching_evidence",
            "active_or_superseded": "superseded",
        })
    return sorted(rows, key=lambda r: (
        r["volume"], int(r["page"]), int(r["line"]),
        int(r["token_index"]), r["observed_source"],
    ))


def recent_backaudit(
    aligned: list[dict[str, str]], diagnostics: list[dict[str, str]],
    shadow: list[dict[str, str]],
) -> list[dict[str, str]]:
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    diag_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in diagnostics
    }
    canon = {
        r["tibetan_syllable"]: r for r in csv.DictReader(
            io.StringIO(canonical.git_show(
                POST_TOKENIZER_REF,
                "data/tibetan_latin_canonical_syllables.tsv",
            )),
            delimiter="\t",
        )
    }
    registry: dict[str, list[dict[str, str]]] = {}
    for row in integrity.read_tsv(
        ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
    ):
        registry.setdefault(row["operation_signature"], []).append(row)
    echo_decisions = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r["decision"]
        for r in integrity.read_tsv(
            ROOT / "data/reviewed_final_ng_echo_decisions.tsv"
        )
    }
    recent = [
        row for row in shadow
        if row["correction_evidence"]
        in {
            "conditioned_final_ni_to_ng_signature_20260728",
            "canonical_conditioned_final_n_signature_20260728",
        }
    ]
    result: list[dict[str, str]] = []
    for item in recent:
        key = (
            item["volume"], item["page"], item["line"], item["token_index"]
        )
        aligned_row = aligned_by_key.get(key, {})
        diagnostic = diag_by_key.get(key, {})
        signature = (
            "REPLACE ni→ṅ"
            if item["observed_source"].endswith("ni")
            else "SUB n→ṅ"
        )
        synthetic = dict(aligned_row)
        synthetic["latin_token"] = item["observed_source"]
        records = [
            r for r in registry.get(signature, [])
            if r["authorization_status"].startswith("authorized")
        ]
        matches = [
            signatures.signature_applies_to_row(
                record, synthetic, item["reviewed_target"]
            )
            for record in records
        ]
        prior = echo_decisions.get(key, "")
        tier = canon.get(item["tibetan_syllable"], {}).get(
            "canonical_confidence_tier", ""
        )
        passed = (
            aligned_row.get("tibetan_syllable") == item["tibetan_syllable"]
            and diagnostic.get("token_boundary_status") == "token_boundary_secure"
            and diagnostic.get("domain_context")
            == "ordinary_tibetan_lexical_or_compound"
            and diagnostic.get("damage_scope")
            in {"none", "later_gloss_or_commentary"}
            and diagnostic.get("marker_attached") == "no"
            and any(ok for ok, _reason in matches)
            and tier in {
                "canonical_reviewed", "canonical_independent_strong",
                "canonical_feature_composed",
            }
            and prior not in {"deferred", "rejected", "resolved_elsewhere"}
            and item["target_teaching_disposition"]
            != "independent_teaching_evidence"
        )
        result.append({
            "volume": item["volume"], "page": item["page"],
            "line": item["line"], "token_index": item["token_index"],
            "tibetan_syllable": item["tibetan_syllable"],
            "observed_source": item["observed_source"],
            "reviewed_target": item["reviewed_target"],
            "canonical_target_tier": tier,
            "signature_decision": next((
                r["signature_id"] for r in records
                if signatures.signature_applies_to_row(
                    r, synthetic, item["reviewed_target"]
                )[0]
            ), ""),
            "signature_condition_match": "yes" if any(
                ok for ok, _reason in matches
            ) else "no",
            "token_boundary_status": diagnostic.get(
                "token_boundary_status", "identity_unresolved"
            ),
            "domain_context": diagnostic.get("domain_context", ""),
            "damage_scope": diagnostic.get("damage_scope", ""),
            "marker_attached": diagnostic.get("marker_attached", ""),
            "prior_identity_decision": prior or "none",
            "target_teaching_disposition":
                item["target_teaching_disposition"],
            "audit_disposition": "pass" if passed else "manual_audit_required",
            "context_excerpt": aligned_row.get("context_excerpt", ""),
        })
    return result


def tokenizer_migration(
    _current: list[dict[str, str]],
) -> list[dict[str, str]]:
    old = ref_diagnostics(PRE_TOKENIZER_REF)
    current = ref_diagnostics(POST_TOKENIZER_REF)
    old_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r for r in old
    }
    current_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in current
    }
    rows: list[dict[str, str]] = []
    old_only = set(old_by_key) - set(current_by_key)
    current_only = set(current_by_key) - set(old_by_key)
    current_identity_lookup: dict[tuple[str, str, str, str, str], list[tuple[str, ...]]] = {}
    for key in current_only:
        row = current_by_key[key]
        identity = (
            key[0], key[1], key[2], row["tibetan_syllable"],
            row["current_latin_token"],
        )
        current_identity_lookup.setdefault(identity, []).append(key)
    paired_old: set[tuple[str, ...]] = set()
    paired_current: set[tuple[str, ...]] = set()
    for key in sorted(old_only):
        before = old_by_key[key]
        identity = (
            key[0], key[1], key[2], before["tibetan_syllable"],
            before["current_latin_token"],
        )
        candidates = current_identity_lookup.get(identity, [])
        if not candidates:
            continue
        new_key = candidates.pop(0)
        paired_old.add(key)
        paired_current.add(new_key)
        rows.append({
            "volume": key[0], "page": key[1], "line": key[2],
            "token_index": f"{key[3]}→{new_key[3]}",
            "tibetan_syllable": before["tibetan_syllable"],
            "old_token": before["current_latin_token"],
            "current_token": current_by_key[new_key]["current_latin_token"],
            "migration_class": "token_index_changed_only",
            "context_excerpt": current_by_key[new_key]["context_excerpt"],
        })
    for key in sorted(set(old_by_key) | set(current_by_key), key=lambda k: (
        k[0], int(k[1]), int(k[2]), int(k[3] or 0)
    )):
        before, after = old_by_key.get(key), current_by_key.get(key)
        if key in paired_old or key in paired_current:
            continue
        if before and after and (
            before["current_latin_token"] == after["current_latin_token"]
            and before["tibetan_syllable"] == after["tibetan_syllable"]
        ):
            continue
        old_token = before.get("current_latin_token", "") if before else ""
        new_token = after.get("current_latin_token", "") if after else ""
        if before and after:
            if "ı" in new_token and new_token.startswith(old_token):
                category = "dotless_i_token_merged_correctly"
            elif "'" in new_token or "’" in new_token:
                category = "apostrophe_token_extent_repaired"
            elif any(ord(char) > 127 for char in new_token):
                category = "unicode_latin_token_extent_repaired"
            else:
                category = "alignment_change_requires_review"
        elif before:
            category = (
                "former_fragment_or_gloss_alignment_removed"
                if key[3] == "0" or before.get("alignment_confidence")
                in {"gloss_or_prose_noise", "probable_alignment"}
                else "former_alignment_requires_review"
            )
        else:
            category = (
                "newly_visible_unicode_token"
                if any(ord(char) > 127 for char in new_token)
                else "new_alignment_requires_review"
            )
        row = after or before
        rows.append({
            "volume": key[0], "page": key[1], "line": key[2],
            "token_index": key[3],
            "tibetan_syllable": row.get("tibetan_syllable", ""),
            "old_token": old_token, "current_token": new_token,
            "migration_class": category,
            "context_excerpt": row.get("context_excerpt", ""),
        })
    return rows


def unusual_glyphs(aligned: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in aligned:
        adjacent = row["following_character"] or row["preceding_character"]
        if adjacent not in {"ř", "ħ", "ľ"}:
            continue
        rows.append({
            "volume": row["volume"], "page": row["page"],
            "line": row["line"], "token_index": row["token_index"],
            "tibetan_syllable": row["tibetan_syllable"],
            "captured_token": row["latin_token"],
            "adjacent_glyph": adjacent,
            "boundary_status": row["token_boundary_status"],
            "review_disposition": "retain_boundary_unsafe_manual_review",
            "context_excerpt": row["context_excerpt"],
        })
    return rows


def canonical_authority_migration() -> list[dict[str, str]]:
    path = "data/tibetan_latin_canonical_syllables.tsv"
    before = {
        row["tibetan_syllable"]: row for row in csv.DictReader(
            io.StringIO(canonical.git_show(PRE_TOKENIZER_REF, path)),
            delimiter="\t",
        )
    }
    after = {
        row["tibetan_syllable"]: row for row in csv.DictReader(
            io.StringIO(canonical.git_show(POST_TOKENIZER_REF, path)),
            delimiter="\t",
        )
    }
    authoritative = {
        "canonical_reviewed", "canonical_independent_strong",
        "canonical_feature_composed",
    }
    rows = []
    for syllable in sorted(set(before) | set(after)):
        old, new = before.get(syllable, {}), after.get(syllable, {})
        old_authoritative = old.get("canonical_confidence_tier") in authoritative
        new_authoritative = new.get("canonical_confidence_tier") in authoritative
        if old_authoritative != new_authoritative:
            direction = "lost_authority" if old_authoritative else "gained_authority"
            rows.append({
                "tibetan_syllable": syllable,
                "previous_canonical_forms": old.get("canonical_forms", ""),
                "previous_tier": old.get("canonical_confidence_tier", ""),
                "current_canonical_forms": new.get("canonical_forms", ""),
                "current_tier": new.get(
                    "canonical_confidence_tier", "identity_absent"
                ),
                "migration_reason":
                    "tokenizer_boundary_evidence_changed_or_identity_removed",
                "migration_direction": direction,
                "audit_disposition": (
                    "retain_downgrade_pending_positive_evidence"
                    if direction == "lost_authority"
                    else "retain_gain_subject_to_gate0_rebuild"
                ),
            })
    return rows


def final_ng_rows_from_ref(ref: str) -> list[dict[str, str]]:
    rows = []
    for volume in ("wts_1_34", "wts_35_51", "wts_8_b", "wts_9_m"):
        path = (
            f"release/current/qa/{volume}/tibetan_cleanup_diagnostics/"
            "tibetan_final_ng_source_compatible_candidates.tsv"
        )
        text = canonical.git_show(ref, path)
        rows.extend(csv.DictReader(io.StringIO(text), delimiter="\t"))
    return rows


def current_final_ng_rows() -> list[dict[str, str]]:
    rows = []
    for path in sorted(glob.glob(
        str(ROOT / "release/current/qa/*/tibetan_cleanup_diagnostics/"
            "tibetan_final_ng_source_compatible_candidates.tsv")
    )):
        rows.extend(integrity.read_tsv(Path(path)))
    return rows


def final_ng_reconciliation(
    aligned: list[dict[str, str]],
) -> list[dict[str, str]]:
    final_rows = current_final_ng_rows()
    aligned_by_key = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r
        for r in aligned
    }
    canonical_rows = {
        r["tibetan_syllable"]: r for r in integrity.read_tsv(
            ROOT / "data/tibetan_latin_canonical_syllables.tsv"
        )
    }
    outlier_rows = {
        (r["tibetan_syllable"], r["current_source"]): r
        for r in integrity.read_tsv(
            ROOT / "data/tibetan_latin_transcription_outliers.tsv"
        )
    }
    registry: dict[str, list[dict[str, str]]] = {}
    for row in integrity.read_tsv(
        ROOT / "data/tibetan_latin_ocr_signature_registry.tsv"
    ):
        registry.setdefault(row["operation_signature"], []).append(row)
    decisions = {
        (r["volume"], r["page"], r["line"], r["token_index"]): r["decision"]
        for r in integrity.read_tsv(
            ROOT / "data/reviewed_final_ng_echo_decisions.tsv"
        )
    }
    rows = []
    authoritative = {
        "canonical_reviewed", "canonical_independent_strong",
        "canonical_feature_composed",
    }
    for item in final_rows:
        key = (
            item["volume"], item["page"], item["line"], item["token_index"]
        )
        aligned_row = aligned_by_key.get(key, {})
        canon = canonical_rows.get(item["tibetan_syllable"], {})
        target = item.get("proposed_latin_target", "")
        operations = canonical.edit_operations(
            item["source_latin_token"], target
        ) if target else []
        applicability = []
        for operation in operations:
            records = [
                record for record in registry.get(operation["signature"], [])
                if record["authorization_status"].startswith("authorized")
            ]
            results = [
                signatures.signature_applies_to_row(
                    record, aligned_row, target
                ) for record in records
            ]
            applicability.append(
                f"{operation['signature']}:"
                + (
                    "applies" if any(ok for ok, _reason in results)
                    else (results[0][1] if results else "not_authorized")
                )
            )
        prior = decisions.get(key, "")
        outlier = outlier_rows.get(
            (item["tibetan_syllable"], item["source_latin_token"]), {}
        )
        if prior in {"deferred", "rejected", "resolved_elsewhere"}:
            disposition = f"blocked_prior_{prior}"
        elif not target:
            disposition = "no_supported_target"
        elif canon.get("canonical_confidence_tier") not in authoritative:
            disposition = "canonical_target_not_authoritative"
        elif target not in canon.get("canonical_forms", "").split(";"):
            disposition = "final_ng_target_conflicts_with_general_canonical"
        elif outlier.get("source_alignment_status") != "secure_transcription_outlier":
            disposition = "source_alignment_not_secure"
        elif operations and all(value.endswith(":applies") for value in applicability):
            disposition = "ready_existing_authority"
        else:
            disposition = "signature_not_authorized_or_condition_mismatch"
        rows.append({
            "volume": item["volume"], "page": item["page"],
            "line": item["line"], "token_index": item["token_index"],
            "tibetan_syllable": item["tibetan_syllable"],
            "source_token": item["source_latin_token"],
            "proposed_target": target,
            "general_canonical_tier": canon.get(
                "canonical_confidence_tier", "unresolved"
            ),
            "general_source_alignment_status": outlier.get(
                "source_alignment_status", "not_in_general_outlier_queue"
            ),
            "required_signatures": ";".join(
                operation["signature"] for operation in operations
            ),
            "signature_applicability": ";".join(applicability) or "none",
            "prior_identity_decision": prior or "none",
            "final_ng_evidence_class": item["source_compatible_category"],
            "effective_disposition": disposition,
            "context_excerpt": item["context_excerpt"],
        })
    return rows


def final_ng_queue_migration() -> list[dict[str, str]]:
    baseline = final_ng_rows_from_ref(PRE_TOKENIZER_REF)
    pre_gate0 = final_ng_rows_from_ref(
        "247f44fd697cfe4727dbe38f158a3a2fd855fcad"
    )
    current = current_final_ng_rows()
    def key(row):
        return (
            row["volume"], row["page"], row["line"], row["token_index"],
            row["tibetan_syllable"], row["source_latin_token"],
        )
    rows = []
    for stage, before, after in (
        ("baseline_530_to_pre_gate0_555", baseline, pre_gate0),
        ("pre_gate0_555_to_current", pre_gate0, current),
    ):
        before_by_key, after_by_key = (
            {key(r): r for r in before}, {key(r): r for r in after}
        )
        for identity in sorted(
            set(before_by_key) ^ set(after_by_key),
            key=lambda k: (
                k[0], int(k[1]), int(k[2]), int(k[3] or 0), k[4], k[5]
            ),
        ):
            item = after_by_key.get(identity) or before_by_key[identity]
            gained = identity in after_by_key
            token = identity[-1]
            if gained and ("ı" in token or "'" in token or "’" in token):
                category = "newly_visible_complete_token"
            elif gained:
                category = "new_or_reclassified_candidate"
            else:
                category = "resolved_or_no_longer_candidate"
            rows.append({
                "volume": identity[0], "page": identity[1],
                "line": identity[2], "token_index": identity[3],
                "tibetan_syllable": identity[4], "source_token": token,
                "target": item.get("proposed_latin_target", ""),
                "comparison_stage": stage,
                "before_or_after": "after" if gained else "before",
                "migration_class": category,
                "context_excerpt": item.get("context_excerpt", ""),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    aligned = integrity.collect_all_aligned(ROOT / "release/current")
    diagnostics = integrity.build_diagnostics(ROOT / "release/current")
    shadow = source_shadow(aligned)
    recent = recent_backaudit(aligned, diagnostics, shadow)
    migration = tokenizer_migration(diagnostics)
    glyphs = unusual_glyphs(aligned)
    canonical_migration = canonical_authority_migration()
    final_reconciliation = final_ng_reconciliation(aligned)
    final_migration = final_ng_queue_migration()
    write(
        args.data_root / "tibetan_latin_reviewed_source_dispositions.tsv",
        shadow, SOURCE_FIELDS,
    )
    write(
        args.data_root / "final_ng_vs_general_signature_reconciliation.tsv",
        final_reconciliation, FINAL_RECONCILIATION_FIELDS,
    )
    write(
        args.data_root / "final_ng_source_compatible_queue_migration.tsv",
        final_migration, FINAL_MIGRATION_FIELDS,
    )
    write(
        args.data_root / "tibetan_latin_recent_signature_correction_backaudit.tsv",
        recent, RECENT_FIELDS,
    )
    write(
        args.data_root / "tibetan_latin_tokenizer_alignment_migration.tsv",
        migration, MIGRATION_FIELDS,
    )
    write(
        args.data_root / "tibetan_latin_unusual_boundary_glyph_audit.tsv",
        glyphs, GLYPH_FIELDS,
    )
    write(
        args.data_root / "tibetan_latin_canonical_authority_migration.tsv",
        canonical_migration, CANONICAL_MIGRATION_FIELDS,
    )
    print(
        f"source_dispositions={len(shadow)} recent={len(recent)} "
        f"recent_pass={sum(r['audit_disposition'] == 'pass' for r in recent)} "
        f"migration={len(migration)} unusual_glyphs={len(glyphs)} "
        f"canonical_losses={len(canonical_migration)}"
        f" final_reconciliation={len(final_reconciliation)} "
        f"final_queue_migration={len(final_migration)}"
    )


if __name__ == "__main__":
    main()
