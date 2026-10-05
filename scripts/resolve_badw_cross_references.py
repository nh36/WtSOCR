"""Bounded canonical linking of existing source cross-reference records.

URL capture (the older ``resolution_status``) is not entry resolution. This
adds a separate, replayable ``canonical_resolution`` annotation without
altering literal observations. Only actual supplied entry records can be
targets. There is deliberately no nearest-lemma, arrow-direction, Unicode
normalization, stem expansion, or morphological inference.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict
from pathlib import Path

METHOD_VERSION = "badw-cross-reference-exact-v1"


class EntryIndex:
    def __init__(self, entries):
        self.urls = defaultdict(set)
        self.labels = defaultdict(set)
        self.identities = defaultdict(set)
        self.records = {}
        for entry in entries:
            if entry.get("record_type") != "entry":
                continue
            identifier = entry["id"]
            if identifier in self.records and self.records[identifier] != entry:
                raise ValueError(f"conflicting entry record: {identifier}")
            self.records[identifier] = entry
            url = entry.get("stable_url")
            if url:
                self.urls[url].add(identifier)
            label = entry.get("headword", {}).get("loc")
            if label:
                self.labels[label].add(identifier)
                self.identities[(label, str(entry.get("homonym") or ""))].add(identifier)
        encoded = json.dumps(sorted(self.records.values(), key=lambda r: r["id"]),
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.sha256 = hashlib.sha256(encoded.encode()).hexdigest()

    def resolve(self, occurrence, *, reviewed_target=None):
        """Return a copy annotated with exact-index resolution.

        PDF targets require a source-bound review of the exact printed target
        extent. ``reviewed_target`` is not an unreviewed text normalizer. The
        literal, review and source spans remain attached to the annotation.
        A URL with no entry never falls back to an attractive nearby lemma.
        """
        if occurrence.get("record_type") != "cross_reference":
            raise ValueError("expected existing cross_reference record")
        if not occurrence.get("source_spans"):
            raise ValueError("cross-reference lacks exact source provenance")
        if "canonical_resolution" in occurrence:
            raise ValueError("already annotated; replay from the source record")
        url = occurrence.get("target_url")
        review = None
        if url:
            candidates = self.urls.get(url, set())
            method = "exact_explicit_url"
        elif reviewed_target is not None:
            review = copy.deepcopy(reviewed_target)
            if (review.get("occurrence_id") != occurrence.get("id") or
                    review.get("source_spans") != occurrence["source_spans"] or
                    review.get("literal") != occurrence.get("target_label") or
                    not isinstance(review.get("lemma"), str) or
                    not isinstance(review.get("review"), dict) or
                    not all(review["review"].get(k) for k in ("reviewer", "reviewed_at", "evidence"))):
                raise ValueError("printed target review is not bound to this occurrence")
            candidates = (self.identities.get((review["lemma"], str(review["homonym"])), set())
                          if review.get("homonym") is not None else
                          self.labels.get(review["lemma"], set()))
            method = "reviewed_exact_printed_target"
        else:
            candidates = set()
            method = "no_reviewed_target"
        ids = sorted(candidates)
        annotation = dict(method_version=METHOD_VERSION, method=method,
                          entry_index_sha256=self.sha256, candidate_entry_ids=ids,
                          status="resolved" if len(ids)==1 else "ambiguous" if ids else "unresolved")
        if len(ids)==1:
            annotation["target_entry_id"] = ids[0]
        if review is not None:
            annotation["target_review"] = review
        result = copy.deepcopy(occurrence)
        result["canonical_resolution"] = annotation
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True,
                        help="explicit bounded source-reference JSONL, not a corpus assignment job")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.entries.open(encoding="utf-8") as stream:
        index = EntryIndex(json.loads(line) for line in stream if line.strip())
    with args.references.open(encoding="utf-8") as stream:
        records = [index.resolve(json.loads(line)) for line in stream if line.strip()]
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":"))+"\n" for r in records),
                           encoding="utf-8")


if __name__ == "__main__":
    main()
