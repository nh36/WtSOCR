"""Pin actual acquired HTML entries and source-bound PDF article headings.

Catalogue/search rows alone are not entries. PDF witness identifiers remain
distinct from HTML identities: this is not a speculative cross-witness merge.
Only observed HTML URLs are addressable; never invent /lemma/ aliases for PDFs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

VERSION = "badw-actual-entry-index-v1"


def rows(path):
    with (gzip.open if path.suffix == ".gz" else open)(path, "rt", encoding="utf-8") as stream:
        yield from (json.loads(line) for line in stream if line.strip())


def build(html, pdf):
    result = {}
    for record in html:
        if record.get("record_type") != "entry":
            continue
        entry = record
        if not entry.get("source_spans") or not entry.get("stable_url"):
            raise ValueError("HTML entry lacks observed address/source spans")
        if entry["id"] in result:
            raise ValueError("duplicate actual entry identifier")
        result[entry["id"]] = entry
    for witness in pdf:
        if witness.get("contract_version") != "badw-pdf-article-witness-v1":
            raise ValueError("unsupported PDF witness contract")
        label = witness.get("loc_headword_reading") or witness.get("loc_headword")
        if not label or not witness.get("source_spans") or not witness.get("entry_start_source_span"):
            raise ValueError("PDF entry lacks a source-bound heading")
        entry = dict(record_type="entry", id=witness["id"],
                     headword=dict(loc=label, source_loc=witness["loc_headword"],
                                   tibetan=witness.get("tibetan_headword")),
                     homonym=str(witness.get("homonym") or ""),
                     witness_ids=[witness["id"]], source_spans=witness["source_spans"],
                     entry_start_source_span=witness["entry_start_source_span"],
                     source_kind="pdf", volume=witness["volume"])
        if entry["id"] in result:
            raise ValueError("duplicate actual entry identifier")
        result[entry["id"]] = entry
    return [result[key] for key in sorted(result)]


def encode(records):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n"
                   for r in records).encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.with_suffix(".manifest.json").exists():
        parser.error("refusing to overwrite pinned index")
    records = build(rows(args.html), rows(args.pdf))
    body = encode(records)
    manifest = dict(contract_version=VERSION, entries=len(records),
                    scope="all actual entries in pinned acquired witnesses; not all possible future BAdW entries",
                    sha256=hashlib.sha256(body).hexdigest(),
                    inputs=[dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                            for p in (args.html, args.pdf)])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(body)
    args.output.with_suffix(".manifest.json").write_bytes(encode([manifest]))
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
