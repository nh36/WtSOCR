#!/usr/bin/env python3
"""Validate reviewed final-ṅ batch arithmetic against release artifacts."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def validate(root: Path = ROOT) -> list[str]:
    batches = read_tsv(root / "data/final_ng_batch_reconciliation.tsv")
    overrides = read_tsv(root / "data/reviewed_tibetan_exact_overrides.tsv")
    decisions = read_tsv(root / "data/reviewed_final_ng_echo_decisions.tsv")
    changes: list[dict[str, str]] = []
    positional: list[dict[str, str]] = []
    source_compatible_positional: list[dict[str, str]] = []
    echoes: list[dict[str, str]] = []
    frozen_rows: list[dict[str, str]] = []
    for manifest in (root / "data").glob(
        "final_ng_*prepass_manifest_*.tsv"
    ):
        frozen_rows.extend(read_tsv(manifest))
    for volume_dir in (root / "release/current/qa").glob("wts_*"):
        changes_path = volume_dir / f"{volume_dir.name}_changes.tsv"
        if changes_path.exists():
            changes.extend(read_tsv(changes_path))
        diagnostic = volume_dir / "tibetan_cleanup_diagnostics"
        positional.extend(read_tsv(diagnostic / "tibetan_final_ng_consensus_candidates.tsv"))
        source_path = (
            diagnostic / "tibetan_final_ng_source_compatible_candidates.tsv"
        )
        if source_path.exists():
            source_compatible_positional.extend(read_tsv(source_path))
        echoes.extend(read_tsv(diagnostic / "tibetan_final_ng_same_entry_echo_candidates.tsv"))

    errors: list[str] = []
    for batch in batches:
        pos = [row for row in overrides if row["evidence"] == batch["positional_evidence"]]
        echo = [row for row in overrides if row["evidence"] == batch["echo_evidence"]]
        release_pos = [
            row for row in changes
            if row["reason"] in {
                "reviewed_tibetan_exact_final_ng_consensus",
                "reviewed_tibetan_exact_final_ng_source_compatible",
            }
            and row["to_token"] in {item["to_token"] for item in pos}
            and (row["page"], row["line"], row["from_token"])
            in {(item["page"], item["line"], item["from_token"]) for item in pos}
        ]
        release_echo = [
            row for row in changes
            if row["reason"] == "reviewed_tibetan_exact_final_ng_echo"
            and (row["page"], row["line"], row["from_token"])
            in {(item["page"], item["line"], item["from_token"]) for item in echo}
        ]
        tibetan = batch["tibetan_syllable"]
        frozen_echo_keys = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["source_token"],
            )
            for row in frozen_rows
            if row["frozen_prepass_sha"] == batch["frozen_prepass_sha"]
            and row["tibetan_syllable"] == tibetan
            and row["candidate_status"] == "echo"
        }
        current_frozen_echoes = [
            row for row in echoes
            if (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["additional_source_token"],
            ) in frozen_echo_keys
        ]
        if not frozen_echo_keys:
            current_frozen_echoes = [
                row for row in echoes if row["tibetan_syllable"] == tibetan
            ]
        frozen_pos_keys = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["source_token"], row["target"],
            )
            for row in frozen_rows
            if row["frozen_prepass_sha"] == batch["frozen_prepass_sha"]
            and row["tibetan_syllable"] == tibetan
            and row["candidate_status"] == "positional"
        }
        current_pos_keys = {
            (
                row["volume"], row["page"], row["line"], row["token_index"],
                row["tibetan_syllable"], row["source_latin_token"],
                row["proposed_latin_target"],
            )
            for row in positional + source_compatible_positional
        }
        active_pos = len(frozen_pos_keys & current_pos_keys)
        active_echo = sum(
            row.get("active_queue", "yes") == "yes"
            for row in current_frozen_echoes
        )
        decision_counts = Counter(
            row["decision"]
            for row in decisions
            if row["tibetan_syllable"] == tibetan
            and row["reviewing_batch"] == batch["echo_evidence"]
        )
        frozen_pos = int(batch["frozen_positional_count"])
        frozen_echo = int(batch["frozen_echo_candidate_count"])
        current_echo_total = len(current_frozen_echoes)
        computed = {
            "actual_positional_overrides": len(pos),
            "echo_decisions_accepted": decision_counts["accepted"],
            "echo_decisions_deferred": decision_counts["deferred"],
            "echo_decisions_rejected": decision_counts["rejected"],
            "echo_decisions_resolved_elsewhere": decision_counts["resolved_elsewhere"],
            "echo_candidates_not_yet_reviewed": active_echo,
            "positional_queue_delta": frozen_pos - active_pos,
            "total_echo_diagnostic_delta": frozen_echo - current_echo_total,
            "active_echo_queue_delta": frozen_echo - active_echo,
            "total_overrides_added": len(pos) + len(echo),
        }
        checks = {
            field: (actual, int(batch[field])) for field, actual in computed.items()
        }
        checks.update(
            {
                "frozen positional arithmetic": (len(pos), frozen_pos),
                "echo override/decision arithmetic": (
                    len(echo),
                    decision_counts["accepted"],
                ),
                "all frozen echoes reviewed": (
                    sum(decision_counts.values()) + active_echo,
                    frozen_echo,
                ),
                "release positional changes": (len(release_pos), len(pos)),
                "release echo changes": (len(release_echo), len(echo)),
            }
        )
        for label, (actual, expected) in checks.items():
            if actual != expected:
                errors.append(f"{batch['batch_id']}: {label}={actual}, expected {expected}")
        print(
            f"{batch['batch_id']}: positional={len(pos)} "
            f"{Counter((row['volume'], row['from_token']) for row in pos)}; "
            f"echoes={len(echo)} {Counter((row['volume'], row['from_token']) for row in echo)}; "
            f"decisions={dict(decision_counts)}; active={active_echo}; "
            f"total={len(pos) + len(echo)}"
        )
    return errors


def main() -> None:
    errors = validate()
    if errors:
        raise SystemExit("\n".join(errors))
    print("Final-ng batch reconciliation passed.")


if __name__ == "__main__":
    main()
