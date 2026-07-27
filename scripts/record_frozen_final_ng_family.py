#!/usr/bin/env python3
"""Record one manually reviewed family from an immutable final-ṅ manifest."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_DATE = date.today().isoformat()
REVIEW_DATE_COMPACT = REVIEW_DATE.replace("-", "")


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def append(path: Path, rows: list[list[str]]) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter="\t", lineterminator="\n").writerows(rows)


def key(row: dict[str, str]) -> str:
    return f"{row['volume']}:{row['page']}:{row['line']}:{row['token_index']}"


def validate_echo_decisions(
    echoes: list[dict[str, str]],
    *,
    accepted: set[str],
    deferred: set[str],
    rejected: set[str],
    resolved: set[str],
) -> dict[str, str]:
    frozen = {key(row) for row in echoes}
    categories = {
        "accepted": accepted,
        "deferred": deferred,
        "rejected": rejected,
        "resolved_elsewhere": resolved,
    }
    supplied = set().union(*categories.values())
    unknown = supplied - frozen
    if unknown:
        raise ValueError(f"echo keys are not frozen for this family: {sorted(unknown)}")
    duplicates = {
        row_key
        for row_key in supplied
        if sum(row_key in values for values in categories.values()) > 1
    }
    if duplicates:
        raise ValueError(
            f"echo keys have multiple decisions: {sorted(duplicates)}"
        )
    missing = frozen - supplied
    if missing:
        raise ValueError(
            f"frozen echoes lack explicit decisions: {sorted(missing)}"
        )
    return {
        row_key: decision
        for decision, values in categories.items()
        for row_key in values
    }


def decision_audit_metadata(decision: str) -> tuple[str, str]:
    metadata = {
        "accepted": (
            "Entry structure independently establishes the same Tibetan lemma.",
            "none",
        ),
        "deferred": (
            "Current evidence does not independently establish exact same-lemma identity.",
            "independent_lemma_identity_not_established",
        ),
        "rejected": (
            "Manual review establishes that the candidate is not an exact repetition "
            "of this Tibetan lemma.",
            "different_lemma_or_non_echo",
        ),
        "resolved_elsewhere": (
            "This frozen echo identity is already handled by another reviewed exact "
            "decision.",
            "already_resolved_exact_identity",
        ),
    }
    return metadata[decision]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--syllable", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--accept-echo", action="append", default=[])
    parser.add_argument("--defer-echo", action="append", default=[])
    parser.add_argument("--reject-echo", action="append", default=[])
    parser.add_argument("--resolved-echo", action="append", default=[])
    args = parser.parse_args()

    rows = [
        row for row in read(args.manifest)
        if row["tibetan_syllable"] == args.syllable
    ]
    positional = [row for row in rows if row["candidate_status"] == "positional"]
    withheld = [
        row for row in rows if row["candidate_status"] == "withheld_damage"
    ]
    echoes = [row for row in rows if row["candidate_status"] == "echo"]
    accepted = set(args.accept_echo)
    deferred = set(args.defer_echo)
    rejected = set(args.reject_echo)
    resolved = set(args.resolved_echo)
    try:
        echo_decisions = validate_echo_decisions(
            echoes,
            accepted=accepted,
            deferred=deferred,
            rejected=rejected,
            resolved=resolved,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    positional_evidence = f"{args.batch}_consensus_batch_{REVIEW_DATE_COMPACT}"
    echo_evidence = f"{args.batch}_same_entry_echo_batch_{REVIEW_DATE_COMPACT}"
    positional_reason = (
        "reviewed_tibetan_exact_final_ng_source_compatible"
        if "source_compatible" in args.manifest.name
        else "reviewed_tibetan_exact_final_ng_consensus"
    )
    override_rows = [
        [
            row["volume"], row["page"], row["line"], row["token_index"],
            row["source_token"], row["target"],
            positional_reason,
            positional_evidence,
            f"Frozen exact Tibetan {args.syllable} alignment; exact-row only.",
        ]
        for row in positional
    ]
    decision_rows: list[list[str]] = []
    counts = {"accepted": 0, "deferred": 0, "rejected": 0, "resolved_elsewhere": 0}
    for row in echoes:
        row_key = key(row)
        decision = echo_decisions[row_key]
        counts[decision] += 1
        rationale, reconsideration_reason = decision_audit_metadata(decision)
        decision_rows.append([
            row["volume"], row["page"], row["line"], row["token_index"],
            args.syllable, row["source_token"], row["target"], decision,
            row["alignment_category"],
            "same_line_entry_structure_after_positional_alignment",
            rationale, echo_evidence, REVIEW_DATE, reconsideration_reason,
        ])
        if decision == "accepted":
            override_rows.append([
                row["volume"], row["page"], row["line"], row["token_index"],
                row["source_token"], row["target"],
                "reviewed_tibetan_exact_final_ng_echo", echo_evidence, rationale,
            ])

    append(ROOT / "data/reviewed_tibetan_exact_overrides.tsv", override_rows)
    append(ROOT / "data/reviewed_final_ng_echo_decisions.tsv", decision_rows)
    append(ROOT / "data/final_ng_batch_reconciliation.tsv", [[
        f"{args.batch}_{REVIEW_DATE_COMPACT}", positional[0]["frozen_prepass_sha"],
        args.syllable, positional_evidence, str(len(positional)),
        str(len(positional)), echo_evidence, str(len(echoes)),
        str(counts["accepted"]), str(counts["deferred"]),
        str(counts["rejected"]), str(counts["resolved_elsewhere"]), "0",
        str(len(positional)),
        str(counts["accepted"] + counts["resolved_elsewhere"]),
        str(len(echoes)), str(len(positional) + counts["accepted"]),
        str(len(withheld)),
    ]])
    print(
        f"{args.syllable}: positional={len(positional)} "
        f"withheld_damage={len(withheld)} "
        f"echoes={counts} overrides={len(positional) + counts['accepted']}"
    )


if __name__ == "__main__":
    main()
