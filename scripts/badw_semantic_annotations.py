#!/usr/bin/env python3
"""Validate a small scholarly overlay against frozen source review packets.

No extraction, normalization, entity resolution or database promotion occurs.
Packet offsets are half-open Unicode code-point offsets, not OCR token indices.
Source binding verifies cached bytes and the frozen extraction view; it does not
certify the extraction itself or turn same-agent review into independent gold.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from build_badw_structural_review_packet import VERSION as PACKET_VERSION, rows

VERSION = "badw-semantic-annotation-v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RELATIONS = {
    "citation_of": ({"citation"}, {"example", "definition", "sense", "lexical_parallel"}),
    "translation_of": ({"translation"}, {"tibetan", "sanskrit"}),
    "gloss_of": ({"translation"}, {"tibetan", "sanskrit"}),
}


def relationship_claim(claim, ranges):
    """Validate exact endpoints, including shared/discontinuous support.

    Evidence ranges may contain endpoints; they do not assert ownership.
    Endpoints are source-view spans, never nearest-node or canonical identities.
    """
    _keys(claim, ("relation", "from", "to", "basis"))
    if claim["relation"] not in RELATIONS or claim["basis"] not in (
            "explicit_dom", "lex_item_punctuation", "reviewed_parallel_text"):
        raise ValueError("unsupported relationship or evidence basis")
    if not isinstance(claim["to"], list) or not claim["to"]:
        raise ValueError("relationship requires target endpoints")
    allowed_from, allowed_to = RELATIONS[claim["relation"]]
    seen = set()
    for endpoint, allowed in [(claim["from"], allowed_from)] + [(t, allowed_to) for t in claim["to"]]:
        _keys(endpoint, ("kind", "start", "end"))
        a, b = endpoint["start"], endpoint["end"]
        if endpoint["kind"] not in allowed or type(a) is not int or type(b) is not int or not any(
                r["start"] <= a < b <= r["end"] for r in ranges):
            raise ValueError("invalid or unbound relationship endpoint")
        key = (endpoint["kind"], a, b)
        if key in seen:
            raise ValueError("duplicate relationship endpoint")
        seen.add(key)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def binding(packet):
    """Bind the entire source view, including physical anchors, not review labels."""
    keys = ("contract_version", "identity", "source_kind", "source", "review_text",
            "review_text_sha256")
    return {"view_version": packet["contract_version"],
            "view_sha256": digest(canonical({key: packet[key] for key in keys})),
            "text_sha256": packet["review_text_sha256"]}


def physical_selectors(packet, ranges):
    """Return source-view anchors; PDF style/run envelopes are not glyph-exact."""
    if packet["source_kind"] == "html":
        return [{"kind": "html_visible_text", "source_sha256":
                 packet["source"]["source_object"]["sha256"],
                 "ranges": [[r["start"], r["end"]] for r in ranges]}]
    result = []
    offset = 0
    for index, line in enumerate(packet["source"]["visual_lines"]):
        for r in ranges:
            start, end = max(r["start"], offset), min(r["end"], offset + len(line["text"]))
            if start < end:
                result.append({"kind": "pdf_visual_line", "visual_line_index": index,
                    "page_id": line["page_id"], "line_start": start-offset,
                    "line_end": end-offset, "run_start": line["run_start"],
                    "run_end_exclusive": line["run_end_exclusive"],
                    "style_envelopes": [s for s in line["style_spans"]
                                        if s["start"] < end-offset and s["end"] > start-offset]})
        offset += len(line["text"]) + 1
    return result


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("missing or unsupported contract fields")


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _object(root, relative, expected, verified):
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise ValueError("invalid object hash")
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("object path escapes source root")
    key = (path, expected)
    if key not in verified:
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("cached object hash mismatch")
        verified.add(key)


def _packet(packet, cache, canonical_root, verified):
    if packet["contract_version"] != PACKET_VERSION:
        raise ValueError("unsupported source view version")
    text = packet["review_text"]
    if digest(text) != packet["review_text_sha256"]:
        raise ValueError("source view text hash mismatch")
    source = packet["source"]
    if packet["source_kind"] == "html":
        if source["article_source_text"] != text:
            raise ValueError("HTML view text differs from source text")
        obj = source["source_object"]
        _object(cache, obj["object_path"], obj["sha256"], verified)
    elif packet["source_kind"] == "pdf":
        if not source["source_objects"] or canonical_root is None:
            raise ValueError("PDF source requires canonical objects and root")
        if "\n".join(line["text"] for line in source["visual_lines"]) != text:
            raise ValueError("PDF visual lines differ from source view text")
        page_ids = {obj["page_id"] for obj in source["source_objects"]}
        if any(line["page_id"] not in page_ids for line in source["visual_lines"]):
            raise ValueError("visual line has no source page")
        for obj in source["source_objects"]:
            sha = obj["pdf_sha256"]
            _object(cache, f"objects/sha256/{sha[:2]}/{sha}", sha, verified)
            _object(canonical_root, obj["canonical_object"], obj["canonical_object_sha256"], verified)
    else:
        raise ValueError("unsupported source kind")


def validate(packets, annotations, *, cache, canonical_root=None):
    """Fail closed. Preserve candidates and superseded claims in the output."""
    source = {}
    for packet in packets:
        if packet["identity"] in source:
            raise ValueError("duplicate packet identity")
        source[packet["identity"]] = packet
    records, verified, checked = {}, set(), set()
    required = ("contract_version", "annotation_id", "identity", "binding", "ranges",
                "physical_selectors", "kind", "claim", "status", "review", "supersedes")
    for row in annotations:
        _keys(row, required)
        if row["contract_version"] != VERSION:
            raise ValueError("unsupported annotation version")
        annotation_id = row["annotation_id"]
        if not _string(annotation_id) or annotation_id in records:
            raise ValueError("invalid or duplicate annotation ID")
        packet = source.get(row["identity"])
        if packet is None:
            raise ValueError("unknown source identity")
        if packet["identity"] not in checked:
            _packet(packet, cache, canonical_root, verified)
            checked.add(packet["identity"])
        if row["binding"] != binding(packet):
            raise ValueError("stale source view binding")
        ranges = row["ranges"]
        if not isinstance(ranges, list) or not ranges:
            raise ValueError("annotation requires source ranges")
        previous = -1
        for r in ranges:
            _keys(r, ("start", "end", "literal"))
            start, end = r["start"], r["end"]
            if type(start) is not int or type(end) is not int or not (0 <= start < end <= len(packet["review_text"])) or start < previous:
                raise ValueError("invalid, unordered or overlapping source ranges")
            if r["literal"] != packet["review_text"][start:end]:
                raise ValueError("literal does not match source range")
            previous = end
        if row["physical_selectors"] != physical_selectors(packet, ranges):
            raise ValueError("physical selectors differ from frozen source view")
        claim = row["claim"]
        if row["kind"] == "language_span":
            _keys(claim, ("language",))
            if claim["language"] not in ("sa", "bo", "de"):
                raise ValueError("unsupported pilot language")
        elif row["kind"] == "form_mention":
            _keys(claim, ("base_form", "base_language", "context_language", "relation"))
            if not _string(claim["base_form"]) or claim["base_language"] != "sa" or claim["context_language"] != "de" or claim["relation"] != "inflected_name_mention":
                raise ValueError("unsupported pilot form mention")
        elif row["kind"] == "relationship":
            relationship_claim(claim, ranges)
        else:
            raise ValueError("unsupported annotation kind")
        if row["status"] not in ("candidate", "accepted", "rejected"):
            raise ValueError("invalid annotation status")
        review = row["review"]
        _keys(review, ("reviewer", "reviewed_at", "mode", "method_version", "evidence"))
        if any(not _string(v) for v in review.values()):
            raise ValueError("review fields must be nonempty strings")
        if review["mode"] not in ("same_agent_source_review", "prediction_exposed_review", "independent_source_review"):
            raise ValueError("unsupported review mode")
        if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None:
            raise ValueError("review timestamp requires timezone")
        if not isinstance(row["supersedes"], list) or any(not _string(v) for v in row["supersedes"]) or len(set(row["supersedes"])) != len(row["supersedes"]):
            raise ValueError("invalid supersession list")
        records[annotation_id] = row
    # An explicit replacement can change ranges/type, but not witness identity.
    retired = set()
    for key, row in records.items():
        for old in row["supersedes"]:
            if old not in records or records[old]["identity"] != row["identity"]:
                raise ValueError("supersession requires an existing same-witness claim")
            if row["status"] != "accepted" or old in retired:
                raise ValueError("supersession requires one accepted replacement")
            retired.add(old)
    def visit(key, active, done):
        if key in active:
            raise ValueError("supersession cycle")
        if key not in done:
            for old in records[key]["supersedes"]:
                visit(old, active | {key}, done)
            done.add(key)
    done = set()
    for key in records:
        visit(key, set(), done)
    output = [{**records[key], "effective_status": "superseded" if key in retired else records[key]["status"]}
              for key in sorted(records)]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = (Path.cwd() / "work").resolve()
    if not output.is_relative_to(work):
        parser.error("validated source-bound output belongs under ignored work/")
    result = validate(rows(args.packets), rows(args.annotations), cache=args.cache,
                      canonical_root=args.canonical_root)
    encoded = "".join(canonical(row) + "\n" for row in result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(canonical({"contract_version": VERSION, "annotations": len(result),
                     "sha256": digest(encoded), "status_counts":
                     {s: sum(r["effective_status"] == s for r in result)
                      for s in ("accepted", "candidate", "rejected", "superseded")}}))


def apply_validated_annotations(packet, prediction, annotations):
    """Project an offline-validated overlay, without changing observations.

    Call validate() with the source cache before calling this function. Physical
    containment is not citation ownership. Accepted relationships bind exact
    extracted endpoints separately from containment; inactive and base-form
    claims remain explicit. Neither typography nor a base-form annotation is a
    language rule. Discontinuous ranges remain separate source spans.
    """
    from copy import deepcopy
    from benchmark_badw_structure import PARENTS, graph

    if prediction["identity"] != packet["identity"]:
        raise ValueError("annotation projection witness mismatch")
    result = deepcopy(prediction)
    selected = sorted((r for r in annotations if r["identity"] == packet["identity"]),
                      key=lambda r: r["annotation_id"])
    text = packet["review_text"]
    for row in selected:
        if row["binding"] != binding(packet) or row["physical_selectors"] != physical_selectors(packet, row["ranges"]):
            raise ValueError("annotation projection source binding mismatch")
        if "effective_status" not in row:
            raise ValueError("annotation must be validated before projection")
        for span in row["ranges"]:
            if not 0 <= span["start"] < span["end"] <= len(text) or text[span["start"]:span["end"]] != span["literal"]:
                raise ValueError("annotation projection literal mismatch")
        if row["effective_status"] != "accepted" or row["kind"] != "language_span":
            continue
        kind = {"bo": "tibetan", "sa": "sanskrit"}.get(row["claim"]["language"])
        # German language does not imply definition or translation function.
        if kind is None:
            continue
        for span in row["ranges"]:
            a, b = span["start"], span["end"]
            existing = next((n for n in result["nodes"] if
                             (n["kind"], n["start"], n["end"]) == (kind, a, b)), None)
            if existing is None:
                possible = sorted((n for n in result["nodes"] if
                    n["kind"] in PARENTS[kind] and n["start"] <= a < b <= n["end"]),
                    key=lambda n: (n["end"]-n["start"],
                                   n["kind"] == "source_division", n["id"]))
                existing = dict(id=f"annotation:{row['annotation_id']}:{a}:{b}",
                    kind=kind, start=a, end=b,
                    parent=possible[0]["id"] if possible else None,
                    association_status="source_containment_only")
                result["nodes"].append(existing)
            ids = existing.setdefault("semantic_annotation_ids", [])
            if row["annotation_id"] not in ids:
                ids.append(row["annotation_id"])
                ids.sort()
    result["semantic_annotations"] = selected
    # Semantic ownership is not physical containment. Keep these reviewed
    # assertions separate from the extraction benchmark's containment edges.
    # Fail closed if extraction no longer exposes an exact reviewed endpoint.
    relationships = []
    for row in selected:
        if row["kind"] != "relationship" or row["effective_status"] != "accepted":
            continue
        claim = row["claim"]
        relationship_claim(claim, row["ranges"])
        def resolve(endpoint):
            matches = [n for n in result["nodes"] if all(n[k] == endpoint[k] for k in ("kind", "start", "end"))]
            if len(matches) != 1:
                raise ValueError("reviewed relationship endpoint absent or ambiguous")
            return {**endpoint, "node_id": matches[0]["id"]}
        relationships.append({"annotation_id": row["annotation_id"],
            "relation": claim["relation"], "from": resolve(claim["from"]),
            "to": [resolve(t) for t in claim["to"]], "basis": claim["basis"],
            "binding": row["binding"], "physical_selectors": row["physical_selectors"],
            "review": row["review"]})
    result["semantic_relationships"] = relationships
    graph(result["nodes"], result["edges"], text)
    return result


if __name__ == "__main__":
    main()
