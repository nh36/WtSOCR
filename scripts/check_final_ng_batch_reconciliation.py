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
    echoes: list[dict[str, str]] = []
    for volume_dir in (root / "release/current/qa").glob("wts_*"):
        changes_path = volume_dir / f"{volume_dir.name}_changes.tsv"
        if changes_path.exists():
            changes.extend(read_tsv(changes_path))
        diagnostic = volume_dir / "tibetan_cleanup_diagnostics"
        positional.extend(read_tsv(diagnostic / "tibetan_final_ng_consensus_candidates.tsv"))
        echoes.extend(read_tsv(diagnostic / "tibetan_final_ng_same_entry_echo_candidates.tsv"))

    errors: list[str] = []
    for batch in batches:
        pos = [row for row in overrides if row["evidence"] == batch["positional_evidence"]]
        echo = [row for row in overrides if row["evidence"] == batch["echo_evidence"]]
        release_pos = [
            row for row in changes
            if row["reason"] == "reviewed_tibetan_exact_final_ng_consensus"
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
        active_pos = sum(row["tibetan_syllable"] == tibetan for row in positional)
        active_echo = sum(
            row["tibetan_syllable"] == tibetan and row.get("active_queue", "yes") == "yes"
            for row in echoes
        )
        accepted_decisions = sum(
            row["tibetan_syllable"] == tibetan and row["decision"] == "accepted"
            for row in decisions
        )
        expected_pos = int(batch["positional_frozen_count"])
        expected_echo = int(batch["echo_accepted_count"])
        frozen_echo_candidates = int(batch["echo_candidate_frozen_count"])
        checks = {
            "positional overrides": (len(pos), expected_pos),
            "echo overrides": (len(echo), expected_echo),
            "release positional changes": (len(release_pos), expected_pos),
            "release echo changes": (len(release_echo), expected_echo),
            "positional queue delta": (expected_pos - active_pos, expected_pos),
            "echo queue delta": (
                frozen_echo_candidates - active_echo,
                frozen_echo_candidates,
            ),
            "accepted echo decisions": (accepted_decisions, expected_echo),
        }
        for label, (actual, expected) in checks.items():
            if actual != expected:
                errors.append(f"{batch['batch_id']}: {label}={actual}, expected {expected}")
        print(
            f"{batch['batch_id']}: positional={len(pos)} "
            f"{Counter((row['volume'], row['from_token']) for row in pos)}; "
            f"echoes={len(echo)} {Counter((row['volume'], row['from_token']) for row in echo)}; "
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
