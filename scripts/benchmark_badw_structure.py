#!/usr/bin/env python3
"""Validate and score source-pinned whole-entry structural annotations offline.

Offsets are half-open Unicode code-point offsets into the packet review text.
Annotations must be exhaustive. Pending packets never contribute accuracy.
Scores compare exact typed spans, nesting and edges, not reviewer node IDs.
Source packets, annotations and predictions belong under ignored work/.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from build_badw_structural_review_packet import VERSION, rows

PARENTS = {
    "headword": {None}, "source_division": {None}, "sense": {None, "sense", "source_division"},
    "definition": {"sense", "source_division"}, "example": {"sense", "source_division"},
    # Language identification can type an alias outside a German definition.
    # A physical source container (or root) does not assert sense ownership.
    "tibetan": {None, "source_division", "sense", "example", "lexical_parallel", "definition"},
    "translation": {"example", "lexical_parallel", "definition"},
    "citation": {None, "example", "sense", "source_division", "definition", "lexical_parallel"},
    "lexical_parallel": {"sense", "source_division"}, "correction": {"tibetan"},
    "cross_reference": {None, "source_division", "sense", "definition", "example", "lexical_parallel"},
    "grammar": {None, "source_division", "sense", "definition"},
    "qualifier": {None, "source_division", "sense", "definition", "example", "lexical_parallel"},
    "sanskrit": {None, "source_division", "sense", "definition", "example", "lexical_parallel"},
}
EDGES = {"citation_of": ("citation", {"example", "sense", "definition", "lexical_parallel"}),
         "shared_citation_of": ("citation", {"example", "definition", "lexical_parallel"}),
         "translation_of": ("translation", {"tibetan"})}
REVIEW_MODES = {"independent_blind_review", "same_agent_source_review", "prediction_exposed_review"}


def identity(row):
    return row["source_kind"], row["identity"]


def index(records):
    result = {}
    for row in records:
        key = identity(row)
        if key in result:
            raise ValueError("duplicate article identity")
        result[key] = row
    return result


def graph(nodes, edges, text):
    by_id = {}
    for node in nodes:
        if node["id"] in by_id or node["kind"] not in PARENTS:
            raise ValueError("duplicate node ID or unsupported kind")
        start, end = node["start"], node["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError("node outside source Unicode span")
        by_id[node["id"]] = node
    keys = {n["id"]: (n["kind"], n["start"], n["end"]) for n in nodes}
    if len(set(keys.values())) != len(keys):
        raise ValueError("duplicate typed source span")
    nested = set()
    for node in nodes:
        parent_id = node.get("parent")
        parent = by_id.get(parent_id)
        if parent_id is not None and parent is None:
            raise ValueError("missing parent")
        if (parent["kind"] if parent else None) not in PARENTS[node["kind"]]:
            raise ValueError("invalid parent kind")
        if parent and not parent["start"] <= node["start"] < node["end"] <= parent["end"]:
            raise ValueError("child outside parent")
        visited, current = set(), node
        while current is not None:
            if current["id"] in visited:
                raise ValueError("cyclic nesting")
            visited.add(current["id"])
            current = by_id.get(current.get("parent"))
        nested.add((keys[node["id"]], keys[parent_id] if parent else None))
    links = set()
    for edge in edges:
        if edge["kind"] not in EDGES or edge["from"] not in by_id or edge["to"] not in by_id:
            raise ValueError("unsupported edge or missing endpoint")
        source, target = by_id[edge["from"]], by_id[edge["to"]]
        source_kind, target_kinds = EDGES[edge["kind"]]
        if source["kind"] != source_kind or target["kind"] not in target_kinds:
            raise ValueError("invalid relationship kinds")
        if edge["kind"] == "citation_of" and source.get("parent") != target["id"]:
            raise ValueError("citation ownership contradicts nesting")
        if edge["kind"] == "shared_citation_of":
            # Shared support is semantic, not physical containment. Require an
            # explicit evidence claim and a common source division/sense; never
            # let this edge relax the ordinary single-owner relationship.
            if not edge.get("evidence"):
                raise ValueError("shared citation requires evidence")
            def ancestors(node):
                result = set()
                while node is not None:
                    if node["kind"] in {"sense", "source_division"}:
                        result.add(node["id"])
                    node = by_id.get(node.get("parent"))
                return result
            if not ancestors(source) & ancestors(target):
                raise ValueError("shared citation crosses source divisions")
        if edge["kind"] == "translation_of" and source.get("parent") != target.get("parent"):
            raise ValueError("translation crosses source owners")
        link = edge["kind"], keys[edge["from"]], keys[edge["to"]]
        if link in links:
            raise ValueError("duplicate relationship")
        links.add(link)
    return set(keys.values()), nested, links


def boundary_diagnostic(nodes, text):
    """Diagnostic only: ignore terminal whitespace, never internal text.

    Report collapsed/empty spans explicitly. This is not an alternative gold
    contract and never changes the exact graph/ownership score.
    """
    keys = []
    empty = 0
    for node in nodes:
        a, b = node["start"], node["end"]
        while a < b and text[a].isspace():
            a += 1
        while a < b and text[b - 1].isspace():
            b -= 1
        if a == b:
            empty += 1
        else:
            keys.append((node["kind"], a, b))
    return set(keys), len(keys) - len(set(keys)), empty


def score(packets, reviews, predictions):
    pinned, gold, predicted = index(packets), index(reviews), index(predictions)
    if set(gold) - set(pinned) or set(predicted) - set(pinned):
        raise ValueError("unpinned article")
    totals, groups, modes = Counter(), defaultdict(Counter), Counter()
    kinds, disagreements = defaultdict(Counter), []
    boundary = Counter()
    for key, packet in sorted(pinned.items()):
        text = packet["review_text"]
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if packet["contract_version"] != VERSION or digest != packet["review_text_sha256"]:
            raise ValueError("stale packet source/version")
        review = gold.get(key, packet)
        if review.get("review_status") == "reviewed_partial":
            for field in ("source", "group", "stratum", "split", "review_text", "review_text_sha256"):
                if review.get(field) != packet[field]:
                    raise ValueError("review changed pinned source or split")
            if (not review.get("reviewer") or not review.get("unresolved") or
                    review.get("review_mode") not in REVIEW_MODES):
                raise ValueError("partial review requires attribution and unresolved claims")
            graph(review["reviewed_nodes"], review["reviewed_edges"], text)
            totals["partial_unscored"] += 1
            continue
        if review.get("review_status") == "pending_independent_review":
            totals["pending"] += 1
            continue
        if (review.get("review_status") != "reviewed_complete" or not review.get("reviewer") or
                review.get("review_mode") not in REVIEW_MODES):
            raise ValueError("complete attributed review required")
        for field in ("source", "group", "stratum", "split", "review_text", "review_text_sha256"):
            if review.get(field) != packet[field]:
                raise ValueError("review changed pinned source or split")
        if key not in predicted or predicted[key].get("review_text_sha256") != digest:
            raise ValueError("missing or stale prediction")
        for field in ("source", "group", "stratum", "split"):
            if predicted[key].get(field) != packet[field]:
                raise ValueError("prediction changed pinned source or split")
        expected = graph(review["reviewed_nodes"], review["reviewed_edges"], text)
        actual = graph(predicted[key]["nodes"], predicted[key]["edges"], text)
        wanted_boundary, gold_collisions, gold_empty = boundary_diagnostic(review["reviewed_nodes"], text)
        found_boundary, predicted_collisions, predicted_empty = boundary_diagnostic(predicted[key]["nodes"], text)
        boundary.update(gold=len(wanted_boundary), predicted=len(found_boundary),
                        correct=len(wanted_boundary & found_boundary),
                        gold_collisions=gold_collisions, predicted_collisions=predicted_collisions,
                        gold_empty=gold_empty, predicted_empty=predicted_empty)
        for kind in sorted(PARENTS):
            wanted = {n for n in expected[0] if n[0] == kind}
            found = {n for n in actual[0] if n[0] == kind}
            if wanted or found:
                kinds[kind].update(gold=len(wanted), predicted=len(found), correct=len(wanted & found))
        if expected != actual:
            differences = {}
            for axis, wanted, found in zip(("nodes", "nesting", "edges"), expected, actual):
                differences[axis] = {"missing": sorted(wanted - found, key=repr),
                                     "extra": sorted(found - wanted, key=repr)}
            disagreements.append({"source_kind": key[0], "identity": key[1],
                                  "review_text_sha256": digest, "differences": differences})
        modes[review["review_mode"]] += 1
        targets = (totals, groups[packet["group"] + ":" + packet["split"]])
        for count in targets:
            count["reviewed"] += 1
            count["whole_entry_exact"] += expected == actual
            for axis, wanted, found in zip(("nodes", "nesting", "edges"), expected, actual):
                count[axis + ":gold"] += len(wanted)
                count[axis + ":predicted"] += len(found)
                count[axis + ":correct"] += len(wanted & found)
    return {"contract_version": "badw-structural-benchmark-v2", "counts": dict(totals),
            "groups": {k: dict(v) for k, v in sorted(groups.items())},
            "kinds": {k: dict(v) for k, v in sorted(kinds.items())},
            "disagreements": disagreements,
            "terminal_whitespace_diagnostic": dict(boundary),
            "review_modes": dict(sorted(modes.items())),
            "limitations": "Empty axes have no measured accuracy; review-mode declarations do not prove independence. Exact entry scores cover packet review text only; PDF packets omit headings. Source divisions are not asserted senses. Partial reviews are unscored."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("packets", "reviews", "predictions"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(score(rows(args.packets), rows(args.reviews), rows(args.predictions)), sort_keys=True))


if __name__ == "__main__":
    main()
