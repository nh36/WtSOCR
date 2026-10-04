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


if __name__ == "__main__":
    main()
