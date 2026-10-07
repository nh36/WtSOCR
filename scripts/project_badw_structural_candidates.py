#!/usr/bin/env python3
"""Source-pinned candidate adapters and citation-ownership inventory, offline.

This is not a gold annotator or an ownership resolver. Unrepresented components
and unresolved associations remain explicit. Outputs contain source text and
must live under ignored work/. The original review packet is never rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from benchmark_badw_structure import graph
from build_badw_structural_review_packet import rows

VERSION = "badw-structural-candidate-projection-v6"


def enrich(nodes, text, *, article=None, structure=None):
    """Source structure only: never add citation/translation ownership edges.

    Tagged HTML supplies language evidence. PDF italic runs alone do not.
    Original source records accompany the projection for exhaustive audit.
    """
    unresolved = []

    def add(kind, a, b, evidence, allowed=None):
        if not 0 <= a < b <= len(text):
            raise ValueError("structural component outside pinned source")
        existing = next((n for n in nodes if (n["kind"], n["start"], n["end"]) == (kind, a, b)), None)
        if existing:
            return existing
        from benchmark_badw_structure import PARENTS
        possible = [n for n in nodes if n["kind"] in PARENTS[kind]
                    and n["start"] <= a < b <= n["end"]
                    and (allowed is None or n["kind"] in allowed)]
        possible.sort(key=lambda n: (n["end"] - n["start"],
                                    n["kind"] == "source_division", n["id"]))
        parent = possible[0]["id"] if possible else None
        if parent is None and None not in PARENTS[kind]:
            unresolved.append({"kind": kind, "start": a, "end": b,
                               "reason": "no source container", "evidence": evidence})
            return None
        node = dict(id=f"n{len(nodes)}", kind=kind, start=a, end=b, parent=parent,
                    source_evidence=evidence, association_status="source_containment_only")
        nodes.append(node)
        return node

    def bounds(field):
        loc = field["locator"]
        a, b = loc["visible_text_start"], loc["visible_text_end"]
        if a is None or b is None or text[a:b] != field["source_text"]:
            raise ValueError("HTML structural field differs from pinned source")
        return a, b

    if article is not None:
        if article["article_source_text"] != text:
            raise ValueError("HTML structural text differs from packet")
        for block in article.get("lexical_blocks", []):
            bounds(block)
            for clause in block.get("clauses", []):
                a, b = clause["start"], clause["end"]
                if text[a:b] != clause["source_text"]:
                    raise ValueError("Lex. clause differs from source")
                add("lexical_parallel", a, b, "explicit HTML Lex. block / delimiter clause")
                # A DOM language field can start before the clause's trimmed
                # boundary. Use the parser's exact source intersection, not a
                # widened clause or a guessed semantic owner. Keep the original
                # DOM locator alongside this derived span for audit.
                for name, kind in (("tibetan_segments", "tibetan"), ("sanskrit", "sanskrit")):
                    for field in clause.get("tagged_fields", {}).get(name, []):
                        if "parent_source_locator" not in field:
                            continue
                        x, y = bounds(field)
                        loc = field["parent_source_locator"]
                        p, q = loc["visible_text_start"], loc["visible_text_end"]
                        if not (0 <= p <= x < y <= q <= len(text) and a <= x < y <= b):
                            raise ValueError("HTML clause intersection outside source field")
                        node = add(kind, x, y, "explicit HTML language tag / source clause intersection")
                        if node is not None:
                            node["parent_source_locator"] = loc
                for quote in clause["german_quotation_candidates"]:
                    add("translation", quote["start"], quote["end"], "source German quotation in Lex. block")
                for citation in clause.get("terminal_citation_candidates", []):
                    node = add("citation", citation["start"], citation["end"], citation["evidence"])
                    if node is not None:
                        node["candidate_status"] = citation["status"]
        for field in article.get("qualifiers", []):
            a, b = bounds(field)
            add("qualifier", a, b, "explicit HTML metrical qualifier tag")
        for name, kind in (("sanskrit", "sanskrit"), ("tibetan_segments", "tibetan")):
            for field in article.get(name, []):
                a, b = bounds(field)
                # An existing complete Tibetan field already preserves these
                # children; do not create duplicate nested language claims.
                if kind == "tibetan" and any(n["kind"] == kind and n["start"] <= a < b <= n["end"] for n in nodes):
                    continue
                add(kind, a, b, f"explicit HTML {name} tag")
        for ref in article.get("cross_references", []):
            if "locator" in ref:
                a, b = bounds(ref)
                add("cross_reference", a, b, "explicit HTML reference link")
    if structure is not None:
        lines = structure["visual_lines"]
        if "\n".join(line["text"] for line in lines) != text:
            raise ValueError("PDF structural text differs from packet")
        for block in structure["candidates"].get("lexical_blocks", []):
            for clause in block["clauses"]:
                x, y = clause["start"], clause["end"]
                if text[x:y] != clause["source_text"]:
                    raise ValueError("PDF Lex. clause differs from source")
                # A quotation-derived candidate may cover only the German
                # end of a parallel. Preserve the complete literal clause as
                # a separate observation; do not widen that candidate or its
                # existing citation ownership edges.
                if not any(n["kind"] == "lexical_parallel" and n["start"] <= x and y <= n["end"] for n in nodes):
                    add("lexical_parallel", x, y, "literal PDF Lex. block / delimiter clause")
                for citation in clause.get("terminal_citation_candidates", []):
                    node = add("citation", citation["start"], citation["end"], citation["evidence"])
                    if node is not None:
                        node["candidate_status"] = citation["status"]
            unresolved.extend(block["diagnostics"])
        for ref in structure["candidates"]["cross_references"]:
            a, b = ref["visual_start"], ref["visual_end"]
            add("cross_reference", a, b, "literal arrow and source typography")
        for field in structure["candidates"].get("sanskrit", []):
            a, b = field["visual_start"], field["visual_end"]
            if text[a:b] != field["source_text"]:
                raise ValueError("PDF Sanskrit field differs from source")
            add("sanskrit", a, b, field["evidence"])
    # Lex. clauses may be added after pre-existing unowned citations. Refine
    # only their physical container, never a semantic owner or an edge.
    by_id = {n["id"]: n for n in nodes}
    for node in nodes:
        if node["kind"] != "citation":
            continue
        parent = by_id.get(node["parent"])
        if parent is not None and parent["kind"] != "source_division":
            continue
        clauses = sorted((n for n in nodes if n["kind"] == "lexical_parallel"
            and n["start"] <= node["start"] < node["end"] <= n["end"]),
            key=lambda n: (n["end"]-n["start"], n["id"]))
        if clauses:
            node["parent"] = clauses[0]["id"]
            node["association_status"] = "source_containment_only"
    return unresolved


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def literal(member):
    """Correction apparatus has a distinct, source-faithful field contract."""
    return member["literal_text"] if "literal_text" in member else member["text"]


def project(packet, nested, structure=None):
    text = packet["review_text"]
    if (packet["source_kind"] != "pdf" or packet["identity"] != nested["article_id"] or
            packet["review_text_sha256"] != digest(text) or
            nested["visual_sha256"] != digest(text) or
            packet["source"]["source_objects"] != nested["source_objects"]):
        raise ValueError("packet/candidate source identity mismatch")
    lines = packet["source"]["visual_lines"]
    if "\n".join(line["text"] for line in lines) != text:
        raise ValueError("packet visual lines differ")
    starts, position = [], 0
    for line in lines:
        starts.append(position)
        position += len(line["text"]) + 1
    nodes, edges, components, unsupported = [], [], [], []

    def add(kind, start, end, parent, anchor=None):
        node = dict(id=f"n{len(nodes)}", kind=kind, start=start, end=end, parent=parent)
        if anchor is not None:
            node["source_lines"] = anchor.get("source_lines", [])
        nodes.append(node)
        return node["id"]

    containers = {"belegstelle_candidate": ("example", "belegstellen"),
                  "uncited_example_candidate": ("example", None),
                  "lexicographic_parallel_candidate": ("lexical_parallel", "lexicographic_parallels"),
                  "definition_candidate": ("definition", "definitions")}
    for division in nested["divisions"]:
        first, last = division["start_line_index"], division["end_line_index_exclusive"]
        if not 0 <= first < last <= len(lines):
            raise ValueError("invalid division line bounds")
        start, end = starts[first], starts[last - 1] + len(lines[last - 1]["text"])
        parent = add("sense" if division["kind"] == "sense_candidate" else "source_division",
                     start, end, None)
        for item in division["items"]:
            members = item["components"]
            # Audit *all* original components, even those with no semantic node.
            for name, member in members.items():
                a, b = member["visual_start"], member["visual_end"]
                if not start <= a < b <= end or text[a:b] != literal(member):
                    raise ValueError("component differs from exact source span")
                components.append({"division_index": division["division_index"],
                    "item_kind": item["kind"], "collection": name,
                    "reference": item["references"].get(name), "component": member})
            owner = parent
            container = containers.get(item["kind"])
            if container:
                kind, collection = container
                anchor = members.get(collection) if collection else None
                a = min(m["visual_start"] for m in members.values())
                b = max(m["visual_end"] for m in members.values())
                owner = add(kind, a, b, parent, anchor)
            else:
                unsupported.append({"kind": item["kind"], "references": item["references"],
                                    "reason": "no reviewed semantic projection"})
            tibetan = None
            for name, kind in (("tibetan_examples", "tibetan"), ("translations", "translation"),
                               ("citations", "citation")):
                member = members.get(name)
                if member is None:
                    continue
                if kind != "citation" and not container:
                    continue
                node_id = add(kind, member["visual_start"], member["visual_end"], owner, member)
                if kind == "tibetan":
                    tibetan = node_id
                elif kind == "translation" and tibetan is not None:
                    edges.append({"kind": "translation_of", "from": node_id, "to": tibetan})
                elif kind == "citation" and container:
                    edges.append({"kind": "citation_of", "from": node_id, "to": owner})
            for correction in item.get("corrections", []):
                a, b = correction["visual_start"], correction["visual_end"]
                if not start <= a < b <= end or text[a:b] != literal(correction):
                    raise ValueError("correction differs from exact source span")
                components.append({"item_kind": item["kind"], "collection": "correction_apparatus",
                                   "component": correction})
                if tibetan is not None:
                    add("correction", a, b, tibetan, correction)
                else:
                    unsupported.append({"kind": "correction", "reason": "no Tibetan owner"})
    if structure is not None:
        if structure["article_id"] != packet["identity"] or structure["source_objects"] != packet["source"]["source_objects"]:
            raise ValueError("PDF structural source identity mismatch")
        unsupported.extend(enrich(nodes, text, structure=structure))
    graph(nodes, edges, text)
    return {**{k: packet[k] for k in ("identity", "source_kind", "source", "group", "stratum", "split",
                                     "review_text_sha256")},
            "contract_version": VERSION, "nodes": nodes, "edges": edges,
            "nested_record_sha256": digest(json.dumps(nested, ensure_ascii=False, sort_keys=True,
                                                      separators=(",", ":"))),
            "original_components": components, "unprojected": unsupported,
            "original_structure": structure,
            "unassigned_source_candidates": nested["unassigned_source_candidates"],
            "limitations": ["candidate relationships, not reviewed gold", "headword absent from packet text",
                            "PDF italic language remains unresolved without explicit source evidence",
                            "new structural components do not assert citation ownership"]}


def citation_inventory(articles):
    """Keep every unassigned citation, with literal context; no nearest-owner rule."""
    result, seen = [], set()
    for article in articles:
        for division in article["divisions"]:
            for item in division["items"]:
                if item["kind"] != "unassigned_citation_candidate":
                    continue
                member = item["components"]["citations"]
                key = article["article_id"], item["references"]["citations"]
                if key in seen:
                    raise ValueError("duplicate unassigned citation")
                seen.add(key)
                result.append({"article_id": key[0], "citation_index": key[1],
                    "volume": article["volume"], "loc_headword": article["loc_headword"],
                    "visual_sha256": article["visual_sha256"],
                    "source_objects": article["source_objects"], "citation": member,
                    "division_kind": division["kind"], "division_text": division["source_text"],
                    "review_status": "pending_source_ownership_review",
                    "ownership": None})
    return sorted(result, key=lambda r: (r["article_id"], r["citation_index"]))


def project_html(packet, records, article=None):
    """Expose existing lexical claims, not a new HTML parser or gold annotation.

    Container extents are derived from the existing field spans; they are not
    independently established sense boundaries. All original records survive.
    Shared/absent owners are deliberately not resolved by proximity.
    """
    text = packet["review_text"]
    if (packet["source_kind"] != "html" or digest(text) != packet["review_text_sha256"] or
            packet["source"]["article_source_text"] != text):
        raise ValueError("HTML packet source identity mismatch")
    source_sha = packet["source"]["source_object"]["sha256"]
    records = sorted(records, key=lambda r: r["id"])
    by_id = {r["id"]: r for r in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate HTML record identity")
    entries = [r for r in records if r["record_type"] == "entry"]
    if len(entries) != 1 or any(r.get("entry_id", entries[0]["id"]) != entries[0]["id"] for r in records):
        raise ValueError("HTML records belong to different entries")
    for record in records:
        for span in record["source_spans"]:
            if (span["field"] != "article_source_text" or span["source_id"] != packet["identity"] or
                    span["source_sha256"] != source_sha or
                    type(span["start"]) is not int or type(span["end"]) is not int or
                    not 0 <= span["start"] < span["end"] <= len(text)):
                raise ValueError("HTML record has stale or invalid source span")
    nodes, edges, unprojected = [], [], []

    def add(kind, a, b, parent, record):
        node = dict(id=f"n{len(nodes)}", kind=kind, start=a, end=b, parent=parent,
                    lexical_record_id=record["id"])
        nodes.append(node)
        return node["id"]

    def field(record, index, value):
        span = record["source_spans"][index]
        if text[span["start"]:span["end"]] != value:
            raise ValueError("HTML lexical field differs from exact source span")
        return span["start"], span["end"]

    entry = entries[0]
    for index, language in enumerate(("loc", "tibetan")):
        a, b = field(entry, index, entry["headword"][language])
        add("headword", a, b, None, entry)
    senses = sorted((r for r in records if r["record_type"] == "sense"), key=lambda r: r["ordinal"])
    attestations = [r for r in records if r["record_type"] == "attestation"]
    owners, division = {}, None
    if senses:
        division = add("source_division", min(r["source_spans"][0]["start"] for r in senses),
                       len(text), None, entry)
    for sense in senses:
        a, b = field(sense, 0, sense["definition"])
        owner = division
        if sense.get("source_label"):
            children = [r for r in attestations if r.get("sense_id") == sense["id"]]
            spans = list(sense["source_spans"])
            for child in children:
                spans.extend(child["source_spans"])
                for cite_id in child["citation_ids"]:
                    if cite_id not in by_id:
                        raise ValueError("missing HTML citation record")
                    spans.extend(by_id[cite_id]["source_spans"])
            owner = add("sense", min(s["start"] for s in spans), max(s["end"] for s in spans), division, sense)
        owners[sense["id"]] = owner
        if sense["definition"].strip():
            add("definition", a, b, owner, sense)
        else:
            unprojected.append({"record_id": sense["id"], "reason": "empty definition"})
    cite_uses = Counter(c for r in attestations for c in r["citation_ids"])
    projected_cites = set()
    for attestation in attestations:
        if attestation.get("association_status") != "explicit" or attestation.get("sense_id") not in owners:
            unprojected.append({"record_id": attestation["id"], "reason": "no explicit sense association"})
            continue
        ta, tb = field(attestation, 0, attestation["tibetan"])
        ga, gb = field(attestation, 1, attestation["german_translation"])
        cites = []
        for cite_id in attestation["citation_ids"]:
            if cite_id not in by_id or by_id[cite_id]["record_type"] != "citation":
                raise ValueError("missing HTML citation record")
            cite = by_id[cite_id]
            ca, cb = field(cite, 0, cite["raw_text"])
            if cite_uses[cite_id] == 1:
                cites.append((cite, ca, cb))
        bounds = [(ta, tb), (ga, gb)] + [(a, b) for _, a, b in cites]
        owner = add("example", min(a for a, _ in bounds), max(b for _, b in bounds),
                    owners[attestation["sense_id"]], attestation)
        t = add("tibetan", ta, tb, owner, attestation)
        g = add("translation", ga, gb, owner, attestation)
        edges.append({"kind": "translation_of", "from": g, "to": t})
        for cite, ca, cb in cites:
            c = add("citation", ca, cb, owner, cite)
            edges.append({"kind": "citation_of", "from": c, "to": owner})
            projected_cites.add(cite["id"])
    for record in records:
        kind = record["record_type"]
        if kind == "citation" and record["id"] not in projected_cites:
            a, b = field(record, 0, record["raw_text"])
            parent = division if division and a >= nodes[int(division[1:])]["start"] else None
            add("citation", a, b, parent, record)
            unprojected.append({"record_id": record["id"], "reason": "citation owner not asserted"})
        elif kind == "cross_reference":
            span = record["source_spans"][0]
            add("cross_reference", span["start"], span["end"], None, record)
        elif kind not in {"entry", "sense", "citation", "attestation"}:
            unprojected.append({"record_id": record["id"], "reason": "unsupported lexical record kind"})
    if article is not None:
        if article["source_identifier"] != packet["identity"] or article["source_object"]["sha256"] != source_sha:
            raise ValueError("HTML structural source identity mismatch")
        unprojected.extend(enrich(nodes, text, article=article))
    graph(nodes, edges, text)
    return {**{k: packet[k] for k in ("identity", "source_kind", "source", "group", "stratum", "split",
                                     "review_text_sha256")},
            "contract_version": VERSION, "nodes": nodes, "edges": edges,
            "original_records": records, "unprojected": unprojected,
            "original_structure": article,
            "limitations": ["existing lexical claims, not reviewed gold", "derived container boundaries",
                            "new structural components do not assert citation ownership"]}


def citation_challenge(inventory, per_volume=20):
    """Deterministic volume-balanced source-only sample; no owner predictions."""
    if type(per_volume) is not int or per_volume <= 0:
        raise ValueError("sample size must be positive")
    result = []
    for volume in (2, 3, 4):
        candidates = [r for r in inventory if r["volume"] == volume]
        # Spread the sample through lexical/source order instead of taking the
        # first twenty, while retaining the complete pending inventory.
        candidates.sort(key=lambda r: (r["loc_headword"], r["article_id"], r["citation_index"]))
        count = min(per_volume, len(candidates))
        result.extend(candidates[i * len(candidates) // count] for i in range(count))
    return result


def write(path, records):
    if path.exists():
        raise ValueError("refusing to overwrite existing output")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def unique_rows(path, key):
    result = {}
    for record in rows(path):
        identity = record[key]
        if identity in result:
            raise ValueError("duplicate structural source identity")
        result[identity] = record
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--nested", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--html-records", type=Path)
    parser.add_argument("--html-articles", type=Path)
    parser.add_argument("--pdf-structures", type=Path)
    parser.add_argument("--challenge", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--canonical-root", type=Path)
    args = parser.parse_args()
    outputs = [args.output, args.inventory] + ([args.challenge] if args.challenge else [])
    if len(set(p.resolve() for p in outputs)) != len(outputs) or any(p.exists() for p in outputs):
        raise ValueError("output paths must be distinct and not already exist")
    all_packets = list(rows(args.packets))
    packets = {}
    for packet in all_packets:
        if packet["source_kind"] != "pdf" or packet["split"] != "development":
            continue
        if packet["identity"] in packets:
            raise ValueError("duplicate pinned PDF identity")
        packets[packet["identity"]] = packet
    articles = list(rows(args.nested))
    structures = unique_rows(args.pdf_structures, "article_id") if args.pdf_structures else {}
    if args.pdf_structures and packets.keys() - structures.keys():
        raise ValueError("missing pinned PDF structural source")
    predictions = [project(packets[a["article_id"]], a, structures.get(a["article_id"])) for a in articles if a["article_id"] in packets]
    if len(predictions) != len(packets):
        raise ValueError("missing/duplicate pinned PDF article")
    inventory = citation_inventory(articles)
    if args.html_records:
        selected = {p["identity"]: p for p in all_packets
                    if p["source_kind"] == "html" and p["split"] == "development"}
        if len(selected) != sum(p["source_kind"] == "html" and p["split"] == "development" for p in all_packets):
            raise ValueError("duplicate pinned HTML identity")
        grouped = {key: [] for key in selected}
        for record in rows(args.html_records):
            keys = {s["source_id"] for s in record["source_spans"]} & selected.keys()
            for key in keys:
                grouped[key].append(record)
        html = unique_rows(args.html_articles, "source_identifier") if args.html_articles else {}
        if args.html_articles and selected.keys() - html.keys():
            raise ValueError("missing pinned HTML structural source")
        predictions.extend(project_html(selected[key], grouped[key], html.get(key)) for key in sorted(selected))
    if args.annotations:
        if args.cache is None:
            raise ValueError("semantic annotations require offline source-cache verification")
        from badw_semantic_annotations import validate, apply_validated_annotations
        annotations = validate(all_packets, rows(args.annotations), cache=args.cache,
                               canonical_root=args.canonical_root)
        selected_packets = {p["identity"]: p for p in all_packets}
        predictions = [apply_validated_annotations(selected_packets[p["identity"]], p, annotations)
                       for p in predictions]
    write(args.output, sorted(predictions, key=lambda r: r["identity"]))
    write(args.inventory, inventory)
    if args.challenge:
        write(args.challenge, citation_challenge(inventory))
    print(json.dumps({"predictions": len(predictions), "unassigned_citations": len(inventory),
                      "by_volume": dict(Counter(r["volume"] for r in inventory)),
                      "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
