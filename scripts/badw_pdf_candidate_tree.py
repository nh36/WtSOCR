"""Lossless ordered database projection of the nested PDF candidate contract.

An ownership edge means parser disposition, not a reviewed semantic fact.
Unsegmented divisions and ownerless citations remain named as such. Original
candidate JSON and source anchors are retained, including literal apparatus.
"""
from __future__ import annotations

from build_badw_pdf_nested_candidates import COLLECTIONS

VERSION = "badw-pdf-candidate-tree-v1"
KINDS = dict(zip(COLLECTIONS, ("definition", "tibetan_example", "belegstelle",
             "lexicographic_parallel", "variant_gloss", "translation", "citation",
             "correction_apparatus", "quoted_non_example")))


def project(nested: dict, lexical: dict) -> tuple[list[dict], list[dict]]:
    if nested["article_id"] != lexical["article_id"]:
        raise ValueError("candidate tree article identity mismatch")
    nodes = [{"id": "root", "parent": None, "ordinal": 0, "kind": "article_witness",
              "payload": {k: v for k, v in nested.items()
                          if k not in ("divisions", "unassigned_source_candidates")}}]
    edges: list[dict] = []
    seen: set[tuple[str, int]] = set()

    def member(owner: str, collection: str, index: int, record: dict) -> None:
        key = (collection, index)
        if key in seen or lexical[collection][index] != record:
            raise ValueError("duplicate or changed candidate tree component")
        seen.add(key)
        edges.append({"node": owner, "kind": KINDS[collection], "ordinal": index})

    for d, division in enumerate(nested["divisions"]):
        division_id = f"division:{d}"
        nodes.append({"id": division_id, "parent": "root", "ordinal": d,
                      "kind": division["kind"],
                      "payload": {k: v for k, v in division.items() if k != "items"}})
        for i, item in enumerate(division["items"]):
            node_id = f"division:{d}:item:{i}"
            nodes.append({"id": node_id, "parent": division_id, "ordinal": i,
                          "kind": item["kind"], "payload": item})
            for collection, index in item["references"].items():
                if index is not None:
                    member(node_id, collection, index, item["components"][collection])
            for index, record in zip(item.get("correction_indices", []),
                                     item.get("corrections", []), strict=True):
                member(node_id, "correction_apparatus", index, record)
    for i, item in enumerate(nested["unassigned_source_candidates"]):
        node_id = f"unassigned:{i}"
        nodes.append({"id": node_id, "parent": "root",
                      "ordinal": len(nested["divisions"]) + i,
                      "kind": "unassigned_source_candidate", "payload": item})
        member(node_id, item["collection"], item["index"], item["record"])
    expected = {(collection, i) for collection in COLLECTIONS
                for i in range(len(lexical[collection]))}
    if seen != expected:
        raise ValueError("candidate tree component conservation failed")
    return nodes, edges
