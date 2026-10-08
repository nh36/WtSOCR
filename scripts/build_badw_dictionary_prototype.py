"""Build an offline, read-only view of a frozen development projection.

No component extraction, ownership inference or text normalization happens
here. Source-bearing output belongs in ignored work/, never in the repository.
Serve the output with Python's local http.server; no application server needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from build_badw_entry_index import encode
from resolve_badw_cross_references import EntryIndex
from badw_dictionary_entry_view import entry_view


def bibliography_links(records, links_path, database):
    """Export only accepted, exactly source-bound existing bibliography claims."""
    originals = {r['id']: r for p in records for r in p.get('original_records', [])
                 if r.get('record_type') == 'citation'}
    result = {}
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        for line in links_path.read_text().split('\n'):
            if not line:
                continue
            link = json.loads(line)
            original = originals.get(link['citation_id'])
            if original is None:
                continue
            for match in link['resolution'].get('matches', []):
                if match.get('target_status') != 'accepted_identity':
                    continue
                spans = original.get('source_spans', [])
                start, end = match.get('article_start'), match.get('article_end')
                if not (match.get('source_sha256') and isinstance(start, int)
                        and isinstance(end, int) and 0 <= start < end):
                    continue
                if not any(s.get('source_sha256') == match['source_sha256']
                           and isinstance(s.get('start'), int) and isinstance(s.get('end'), int)
                           and 0 <= s['start'] <= start < end <= s['end']
                           for s in spans):
                    continue
                for authority_id in match.get('authority_ids', []):
                    authority = db.execute('SELECT label FROM authority WHERE id=?', (authority_id,)).fetchone()
                    if authority is None:
                        continue
                    descriptions = [json.loads(r[0]).get('text', '') for r in db.execute(
                        'SELECT record_json FROM occurrence WHERE authority_id=? ORDER BY id', (authority_id,))]
                    result.setdefault(link['citation_id'], []).append(dict(
                        id=authority_id, label=authority[0], descriptions=descriptions,
                        coverage_status=link['resolution'].get('coverage_status', 'unreviewed'),
                        edition_status=link['resolution'].get('edition_status', 'unreviewed')))
    return result


def view(records, index):
    result = []
    seen = set()
    for record in records:
        if record.get("contract_version") != "badw-structural-candidate-projection-v6":
            raise ValueError("unsupported projection contract")
        identity = record["identity"]
        if identity in seen:
            raise ValueError("duplicate development identity")
        seen.add(identity)
        source = record["source"]
        text = (source["article_source_text"] if record["source_kind"] == "html"
                else "\n".join(line["text"] for line in source["visual_lines"]))
        if hashlib.sha256(text.encode()).hexdigest() != record["review_text_sha256"]:
            raise ValueError("projection review text hash mismatch")
        nodes = record["nodes"]
        ids = {node["id"] for node in nodes}
        if len(ids) != len(nodes):
            raise ValueError("duplicate node ID")
        for node in nodes:
            if not 0 <= node["start"] <= node["end"] <= len(text):
                raise ValueError("node outside source text")
            if node.get("parent") and node["parent"] not in ids:
                raise ValueError("missing parent")
        parents = {n["id"]: n.get("parent") for n in nodes}
        for identity_node in parents:
            visited = set()
            cursor = identity_node
            while cursor:
                if cursor in visited:
                    raise ValueError("cyclic source containment")
                visited.add(cursor)
                cursor = parents[cursor]
        original = record.get("original_records", [])
        entries = [r for r in original if r["record_type"] == "entry"]
        if record["source_kind"] == "pdf":
            # PDF projections deliberately do not duplicate canonical entry
            # records. Reuse the pinned index by exact source identity only.
            entry = index.records.get(identity)
            entries = [entry] if entry is not None else []
        if len(entries) != 1:
            raise ValueError("expected one actual entry record")
        references = []
        for r in original:
            if r["record_type"] == "cross_reference":
                # Reuse the existing canonical resolver; never resolve printed
                # targets by approximate spelling in a presentation adapter.
                references.append(r if "canonical_resolution" in r else index.resolve(r))
        if record["source_kind"] == "pdf":
            # Display existing printed candidates, not new resolver claims.
            # A source-bound printed-target review is required for linking.
            for candidate in record["original_structure"]["candidates"]["cross_references"]:
                references.append(dict(marker=candidate["marker"],
                                       target_label=candidate.get("target_label_candidate", ""),
                                       source_candidate=candidate))
        result.append(dict(projection=record, entry=entries[0], review_text=text,
                           cross_references=references))
    return sorted(result, key=lambda r: (r["entry"]["headword"].get("loc", ""),
                                         str(r["entry"].get("homonym") or ""),
                                         r["projection"]["identity"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--entry-index", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--citation-links", type=Path)
    ap.add_argument("--bibliography", type=Path)
    args = ap.parse_args()
    if bool(args.citation_links) != bool(args.bibliography):
        ap.error('--citation-links and --bibliography must be supplied together')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root / "work"):
        ap.error("source-bearing prototype must be under ignored work/")
    if output.exists():
        ap.error("refusing to replace a frozen prototype")
    # JSONL delimiters are LF, not every Unicode line separator: a literal
    # U+2028 in source evidence must remain inside its JSON string.
    records = [json.loads(line) for line in args.projection.read_text().split("\n") if line]
    index = EntryIndex(json.loads(line) for line in args.entry_index.read_text().split("\n") if line)
    entries = view(records, index)
    bib = bibliography_links(records, args.citation_links, args.bibliography) if args.bibliography else {}
    payload = dict(contract_version="badw-dictionary-reader-v1", entries=[entry_view(e, bib) for e in entries],
                   entry_index_sha256=index.sha256,
                   limitations=["Development candidates, not a production dictionary",
                                "Review is not independent gold; unresolved ownership remains explicit"])
    body = encode([payload])
    output.mkdir(parents=True)
    (output / "data.json").write_bytes(body)
    inspection = encode([dict(entries=entries)])
    (output / "inspection.json").write_bytes(inspection)
    assets = Path(__file__).with_name("badw_dictionary_prototype")
    for name in ("index.html", "app.js", "style.css"):
        shutil.copyfile(assets / name, output / name)
    manifest = dict(entries=len(entries), data_sha256=hashlib.sha256(body).hexdigest(),
                    inputs=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in (args.projection, args.entry_index, args.citation_links, args.bibliography)
                            if p is not None], network_requests=0,
                    inspection_sha256=hashlib.sha256(inspection).hexdigest())
    (output / "manifest.json").write_bytes(encode([manifest]))
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
