#!/usr/bin/env python3
"""Rebuild the source-backed quotation-role review packet from frozen ledgers."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/badw_forensic_structure"
OUT = DATA / "quotation_role_investigation.jsonl"
FAMILY = "form_substitution_with_quoted_definition_role_missing"


def read_jsonl(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    dispositions = [r for r in read_jsonl(DATA / "reference_dispositions.jsonl")
                    if r.get("reason") == FAMILY]
    current = {}
    with gzip.open(DATA / "reference_after.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            current[(row["identity"], row["source_span"]["start"],
                     row["source_span"]["end"])] = row
    output = []
    for disposition in dispositions:
        key = (disposition["identity"], disposition["source_span"]["start"],
               disposition["source_span"]["end"])
        row = current[key]
        if row["text_sha256"] != disposition["text_sha256"]:
            raise SystemExit(f"source hash mismatch for {key}")
        output.append({
            "packet_role": "current_unresolved_candidate",
            "selection": "all current citations in the explicit substitution/quoted-definition family",
            "disposition": disposition,
            "source_kind": row["source_kind"], "identity": row["identity"],
            "source_span": row["source_span"], "literal": row["literal"],
            "text_sha256": row["text_sha256"], "source": row["source"],
            "context": row["context"], "containing_components": row.get("containing_components"),
            "punctuation_enclosures": row.get("punctuation_enclosures"),
            "layout_lines": row.get("layout_lines"), "dom": row.get("dom"),
            "review_status": "not_yet_facsimile_verified_in_this_investigation",
        })
    # Preserve the previously facsimile-verified controls, explicitly labelled
    # as historical positives rather than new sample members.
    for row in read_jsonl(DATA / "quotation_positive_review.jsonl"):
        output.append({"packet_role": "previously_reviewed_positive_control", **row})
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                                  for row in output), encoding="utf-8")
    print(f"wrote {len(output)} rows ({len(dispositions)} unresolved candidates, "
          f"{len(output)-len(dispositions)} historical positive controls): {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
