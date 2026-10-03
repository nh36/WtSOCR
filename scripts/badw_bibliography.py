#!/usr/bin/env python3
"""Offline bibliography inventory and source-scoped authority sidecar.

Source rows are authoritative observations, not inferred cataloguing metadata.
Works and publications remain distinct; references between them are candidates
until edition/containment review. No OCR, transliteration or case folding occurs.
Raw material and generated databases/exports must live under ignored work/.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from badw_html import (Element, TextNode, compact_text, decode_html_bytes,
                       dom_path, element_locator, find_all, parse_html)
from badw_pdf_bibliography import Resolver
from badw_source_cache import RequestSpec, SourceCache

VERSION = "badw-bibliography-v1"
BASE = "https://wts-digital.badw.de/"
PAGES = {"texte": "work", "bibliographie": "publication",
         "abkuerzungen": "abbreviation"}
YEAR_PATTERN = r"(?:1[5-9]|20)\d{2}[a-z]?(?:[–/-]\d{2,4})?(?:\s+ff\.)?"


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def file_digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def identifier(kind: str, *parts: str) -> str:
    return kind + "-" + digest(dumps(parts).encode())[:32]


def visible_nodes(node: Element):
    """Exclude tooltip/UI descendants, including nested bibliography tooltips."""
    if node.classes & {"infotext"} or node.tag in {"script", "style", "input"}:
        return
    if node.attrs.get("hidden") is not None or node.attrs.get("aria-hidden") == "true":
        return
    for child in node.children:
        if isinstance(child, TextNode):
            yield child
        else:
            yield from visible_nodes(child)


def visible(node: Element) -> str:
    return "".join(n.text for n in visible_nodes(node))


def visible_elements(node: Element, tag=None, class_name=None):
    """Elements whose text is part of the visible row (not hidden expansions)."""
    visible_ids = {id(n) for n in visible_nodes(node)}
    return [e for e in find_all(node, tag=tag, class_name=class_name)
            if any(id(n) in visible_ids for n in visible_nodes(e))]


def reference_key(node: Element) -> str | None:
    authors = [compact_text(visible(e)) for e in visible_elements(node, tag="sc")]
    years = [compact_text(visible(e)) for e in visible_elements(node, tag="j")]
    if not authors:
        return None
    if len(years) == 1:
        return "/".join(authors) + " " + years[0]
    # Some official references have an untagged year. Accept only the exact
    # visible author/year form; never read the nested tooltip as a substitute.
    label = compact_text(visible(node))
    author = "/".join(authors)
    if not years and re.fullmatch(re.escape(author) + r"\s+" + YEAR_PATTERN, label):
        return label
    return None


def parse_page(body: bytes, metadata: dict, kind: str) -> list[dict]:
    """Recover table rows, exact visible text and replayable text-node spans."""
    if kind not in PAGES.values():
        raise ValueError("unsupported bibliography page kind")
    sha = digest(body)
    if metadata["sha256"] != sha or metadata["http_status"] != 200:
        raise ValueError("source hash/status mismatch")
    text, encoding, replacement = decode_html_bytes(body, metadata.get("response_headers"))
    if replacement:
        raise ValueError("bibliography source decoding required replacement characters")
    root = parse_html(text)
    rows = []
    for tr in find_all(root, tag="tr"):
        cells = [c for c in tr.children if isinstance(c, Element) and c.tag == "td"]
        if len(cells) != 2:
            continue
        left, right = cells
        expected = {"work": ("textsiglum", "textallg"),
                    "publication": ("autor_jahr", "titel_etc")}.get(kind)
        if expected and not (expected[0] in left.classes and expected[1] in right.classes):
            continue
        # The abbreviation page has plain td cells, inside the content table.
        if kind == "abbreviation":
            ancestor = tr.parent
            while ancestor and "content" not in ancestor.classes:
                ancestor = ancestor.parent
            if ancestor is None:
                continue
        label = compact_text(visible(left))
        if not label:
            raise ValueError("empty bibliography row label")
        record_id = identifier(kind, metadata["requested_url"], label)
        spans, offset = [], 0
        for n in visible_nodes(right):
            spans.append({"dom_path": dom_path(n), "source_line": n.line,
                          "source_column": n.column, "start": offset,
                          "end": offset + len(n.text), "text": n.text})
            offset += len(n.text)
        authors = [compact_text(visible(e)) for e in visible_elements(left, tag="sc")]
        year_match = re.search(r"\b" + YEAR_PATTERN, visible(left))
        year = year_match.group() if year_match else None
        key = ("/".join(authors) + " " + year) if authors and year else None
        refs = [{"label": compact_text(visible(e)), "key": reference_key(e),
                 "source_span": element_locator(e)}
                for e in visible_elements(right, class_name="bibl")]
        sigla = [compact_text(visible(e)) for e in
                 visible_elements(right, class_name="textsiglum")]
        rows.append({"contract_version": VERSION, "id": record_id, "kind": kind,
                     "label": label, "label_text": visible(left),
                     "text": visible(right), "text_nodes": spans,
                     "source_span": element_locator(tr),
                     "occurrence_id": identifier("occurrence", sha, dom_path(tr)),
                     "source_url": metadata["requested_url"],
                     "final_url": metadata["final_url"],
                     "source_sha256": sha, "fetched_at_utc": metadata["fetched_at_utc"],
                     "encoding": encoding, "scope": "badw_online",
                     "print_status": "unverified", "metadata_status": "partial",
                     "author_year_text": visible(left) if kind == "publication" else None,
                     "reference_key": key if kind == "publication" else None,
                     "year": year if kind == "publication" else None,
                     "publication_references": refs, "associated_sigla": sigla,
                     "italic_fragments": [visible(e) for e in visible_elements(right)
                                          if e.tag in {"i", "em"}]})
    if not rows:
        raise ValueError("no recognized bibliography rows")
    return sorted(rows, key=lambda r: (r["kind"], r["label"], r["occurrence_id"]))


def authority_graph(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["id"]].append(row)
    authorities = []
    for key, occurrences in sorted(grouped.items()):
        definitions = {r["text"] for r in occurrences}
        first = occurrences[0]
        authorities.append({"id": key, "kind": first["kind"], "label": first["label"],
                            "scope": first["scope"], "occurrence_ids": sorted(r["occurrence_id"] for r in occurrences),
                            "status": "first_party_source_row" if len(definitions) == 1 else "conflicting_source_rows"})
    keys = defaultdict(set)
    for row in rows:
        if row["kind"] == "publication" and row["reference_key"]:
            keys[row["reference_key"]].add(row["id"])
    relations = []
    for row in rows:
        if row["kind"] != "work":
            continue
        for index, ref in enumerate(row["publication_references"]):
            candidates = sorted(keys.get(ref["key"], set()))
            relations.append({"work_id": row["id"], "occurrence_id": row["occurrence_id"],
                              "ordinal": index + 1, "reference": ref,
                              "publication_candidates": candidates,
                              "status": "exact_reference_candidate" if len(candidates) == 1
                                        else "ambiguous" if candidates else "unmatched",
                              "relation_kind": "edition_or_containment_unreviewed"})
    return authorities, relations


def bibtex_escape(text: str) -> str:
    escapes = {"\\": r"{\textbackslash}", "{": r"\{", "}": r"\}",
               "%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_",
               "$": r"\$", "~": r"{\textasciitilde}", "^": r"{\textasciicircum}"}
    return "".join(escapes.get(c, c) for c in compact_text(text))


def export_bibtex(rows: list[dict]) -> str:
    """Source descriptions as partial @misc, never invented titles.

    Rich source-node and relationship data is in JSON/SQLite. Italic fragments
    are NOT necessarily full titles; author-year strings are not parsed names.
    Each source occurrence gets an entry, so conflicting descriptions survive.
    """
    entries = []
    for row in sorted(rows, key=lambda r: r["occurrence_id"]):
        fields = {"note": row["label"] + ": " + row["text"],
                  "url": row["source_url"], "keywords": row["kind"],
                  "annotation": "Partial source record; print compatibility and edition identity unverified",
                  "wtsauthority": row["id"], "wtssourcesha": row["source_sha256"]}
        if row["year"]:
            fields["year"] = row["year"]
        entries.append("@misc{" + row["occurrence_id"] + ",\n" +
                       ",\n".join("  " + k + " = {" + bibtex_escape(v) + "}" for k, v in sorted(fields.items())) + "\n}\n")
    return "\n".join(entries)


class AuthorityResolver:
    """Exact source-row identity only; no automatic edition/semantic ownership."""
    def __init__(self, authorities: list[dict]):
        self.by_id = {a["id"]: a for a in authorities}
        self.resolver = Resolver([(a["id"], a["label"]) for a in authorities
                                  if a["kind"] == "work"])

    def resolve(self, text: str) -> dict:
        result = self.resolver.resolve(text)
        for match in result["matches"]:
            safe = (match["status"] != "ambiguous" and
                    all(self.by_id[i]["status"] == "first_party_source_row" for i in match["authority_ids"]))
            match["status"] = "exact_online_work_row" if safe else "ambiguous"
            match["edition_status"] = "unreviewed"
            match["print_status"] = "unverified"
        result["contract_version"] = VERSION
        result["match_method"] = "exact_case_sensitive_siglum_spelling"
        result["coverage_status"] = "matched_sigla_only_not_complete_citation_resolution"
        result["status"] = ("unmatched" if not result["matches"] else
                            "ambiguous" if any(m["status"] == "ambiguous" for m in result["matches"])
                            else "exact_online_work_rows")
        return result


def print_inventory(registry: Path) -> list[dict]:
    """Find all heading hits in registered scan OCR; candidates need scan review.

    Includes fascicle/volume supplements, not just Literaturverzeichnis.
    Does not claim OCR-derived pages are complete bibliography occurrences.
    """
    pattern = re.compile(r"Literaturverzeichnis|Quellenverzeichnis|"
                         r"hinzugekommene.{0,100}(?:Quellentexte|Literatur)|"
                         r"(?:Quellentexte|Literatur).{0,80}Abkürzungen", re.I)
    results = []
    with registry.open(encoding="utf-8") as f:
        for source in csv.DictReader(f, delimiter="\t"):
            if not source["label"]:
                continue
            pdf = Path(source["filename"])
            actual = file_digest(pdf)
            if actual != source["sha256"]:
                raise ValueError("registered print PDF hash mismatch: " + str(pdf))
            ocr = pdf.with_suffix(".vision.txt")
            raw = ocr.read_text(encoding="utf-8")
            ocr_sha = file_digest(ocr)
            chunks = re.split(r"(?m)^=== page (\d+) ===\s*$", raw)
            if len(chunks) < 3:
                raise ValueError("missing OCR page delimiters: " + str(ocr))
            for i in range(1, len(chunks), 2):
                page, text = int(chunks[i]), chunks[i + 1]
                for hit in pattern.finditer(text):
                    results.append({"source_label": source["label"], "pdf_path": str(pdf),
                                    "pdf_sha256": actual, "ocr_path": str(ocr),
                                    "ocr_sha256": ocr_sha, "scan_page": page,
                                    "start": hit.start(), "end": hit.end(), "heading": hit.group(),
                                    "context": text[max(0, hit.start()-120):hit.end()+180],
                                    "status": "heading_candidate_requires_print_review"})
    return sorted(results, key=lambda r: (r["source_label"], r["scan_page"], r["start"]))


def write_jsonl(path: Path, records):
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(dumps(record) + "\n")


def build(cache: Path, output: Path, schema: Path, staging: Path | None = None,
          registry: Path | None = None) -> dict:
    if output.exists():
        raise ValueError("use a new output directory; snapshots are immutable")
    if "work" not in output.resolve().parts:
        raise ValueError("generated source material must remain under work/")
    client = SourceCache(cache)
    rows, observations = [], []
    for page, kind in PAGES.items():
        response = client.fetch(RequestSpec(BASE + page), offline=True)
        rows.extend(parse_page(response.body, dict(response.metadata), kind))
        observations.append(dict(response.metadata))
    authorities, relations = authority_graph(rows)
    inventory = print_inventory(registry) if registry else []
    output.mkdir(parents=True)
    write_jsonl(output / "source_rows.jsonl", rows)
    write_jsonl(output / "relations.jsonl", relations)
    write_jsonl(output / "print_inventory.jsonl", inventory)
    (output / "sources.bib").write_text(export_bibtex(rows), encoding="utf-8")
    db = sqlite3.connect(output / "bibliography.sqlite")
    db.executescript(schema.read_text(encoding="utf-8"))
    with db:
        db.executemany("INSERT INTO authority VALUES (?,?,?,?,?,?)",
                       [(a["id"], a["kind"], a["label"], a["scope"], a["status"], dumps(a)) for a in authorities])
        db.executemany("INSERT INTO occurrence VALUES (?,?,?,?,?)",
                       [(r["occurrence_id"], r["id"], r["source_sha256"], r["source_url"], dumps(r)) for r in rows])
        db.executemany("INSERT INTO relation VALUES (?,?,?,?,?)",
                       [(r["occurrence_id"], r["ordinal"], r["work_id"], r["status"], dumps(r)) for r in relations])
        for relation in relations:
            db.executemany("INSERT INTO relation_candidate VALUES (?,?,?)",
                           [(relation["occurrence_id"], relation["ordinal"], p) for p in relation["publication_candidates"]])
    counts = Counter()
    resolver = AuthorityResolver(authorities)
    if staging:
        src = sqlite3.connect(staging.resolve().as_uri() + "?mode=ro", uri=True)
        queries = [("html", "SELECT id,raw_text FROM citation ORDER BY id"),
                   ("pdf", "SELECT article_id || ':' || ordinal,text FROM pdf_lexical_candidate WHERE kind='citation' ORDER BY article_id,ordinal")]
        with db, (output / "citation_links.jsonl").open("w", encoding="utf-8") as f, \
                (output / "citation_review_queue.jsonl").open("w", encoding="utf-8") as review:
            for layer, query in queries:
                for citation_id, text in src.execute(query):
                    result = resolver.resolve(text)
                    record = {"layer": layer, "citation_id": citation_id, "resolution": result}
                    f.write(dumps(record) + "\n")
                    if result["status"] != "exact_online_work_rows":
                        review.write(dumps(record) + "\n")
                    counts[layer + ":" + result["status"]] += 1
                    db.execute("INSERT INTO citation_resolution VALUES (?,?,?,?)",
                               (layer, citation_id, result["status"], dumps(result)))
                    for ordinal, match in enumerate(result["matches"], 1):
                        for authority_id in match["authority_ids"]:
                            db.execute("INSERT INTO citation_target VALUES (?,?,?,?,?,?)",
                                       (layer, citation_id, ordinal, authority_id, match["start"], match["end"]))
        src.close()
    if db.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("authority foreign key failure")
    db.close()
    summary = {"contract_version": VERSION, "sources": observations,
               "authority_counts": dict(Counter(a["kind"] for a in authorities)),
               "source_rows": len(rows), "relations": len(relations),
               "relation_statuses": dict(Counter(r["status"] for r in relations)),
               "citation_statuses": dict(sorted(counts.items())),
               "print_heading_candidates": len(inventory),
               "staging_database_sha256": file_digest(staging) if staging else None,
               "schema_sha256": file_digest(schema),
               "limitations": ["Print inventory candidates require scan review and page-range boundaries",
                                "Source-row links do not verify editions, citation ownership or print compatibility",
                                "BibTeX metadata is partial; original descriptions are preserved"]}
    summary["output_hashes"] = {p.name: file_digest(p) for p in sorted(output.iterdir()) if p.suffix != ".sqlite"}
    (output / "manifest.json").write_text(dumps(summary) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--staging", type=Path)
    parser.add_argument("--print-registry", type=Path)
    parser.add_argument("--schema", type=Path, default=Path("data/bibliography_database.schema.sql"))
    args = parser.parse_args()
    print(dumps(build(args.cache, args.output, args.schema, args.staging, args.print_registry)))


if __name__ == "__main__":
    main()
