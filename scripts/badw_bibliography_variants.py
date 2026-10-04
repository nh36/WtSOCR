"""Reviewed publication relations preserve editions without merging authorities.

Evidence names an exact online/print occurrence and its literal wording. A
candidate relation is never an accepted citation edge or edition certificate.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


def publication_relations(path: Path | None, authorities: list[dict], rows: list[dict],
                          printed: list[dict]) -> list[dict]:
    if path is None:
        return []
    kinds = {a["id"]: a["kind"] for a in authorities}
    evidence = {r["occurrence_id"]: (r["source_sha256"], r["text"], r["id"]) for r in rows}
    evidence.update({r["id"]: (r["candidate"]["pdf_sha256"], r["verified_transcription"], r["authority_id"]) for r in printed})
    results, seen = [], set()
    with path.open(encoding="utf-8", newline="") as stream:
        for review in csv.DictReader(stream, delimiter="\t"):
            source, target = review["source_id"], review["target_id"]
            relation, status = review["relation_type"], review["status"]
            key = source, target, relation
            if key in seen or source == target or any(kinds.get(i) != "publication" for i in (source, target)):
                raise ValueError("duplicate or invalid publication relation endpoints")
            seen.add(key)
            if relation not in {"different_edition", "reprint_of", "possible_same_work"} or status not in {"candidate", "reviewed"}:
                raise ValueError("unsupported publication relation")
            if relation == "possible_same_work" and status != "candidate":
                raise ValueError("possible same work is only a candidate")
            observation = evidence.get(review["evidence_occurrence_id"])
            quote = review["evidence_quote"]
            if (not observation or observation[0] != review["evidence_sha256"] or observation[2] not in {source, target} or
                    not quote.strip() or quote not in observation[1] or not review["evidence_note"].strip()):
                raise ValueError("stale or missing publication relation evidence")
            identity = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:32]
            results.append({**review, "id": "publication-relation-" + identity,
                            "limitations": "Not a citation edition/locator verification; original source readings retained"})
    return sorted(results, key=lambda r: r["id"])
