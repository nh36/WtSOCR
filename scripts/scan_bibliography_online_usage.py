"""Generate online apparatus candidates from whole article bodies and marked sigla.

Candidates are not accepted identities or defects. Digits in Mim1/Mim2 survive.
Use the existing parsed HTML JSONL, decoded-PDF staging database and apparatus
JSONL; outputs stay in ignored work storage. Explicit review resolves aliases,
wrapped tokens, authors, ordinary prose and edition selectors.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from badw_citation_components import ComponentResolver


def candidates(text, known, resolver):
    for match in re.finditer(r"[(;]\s*([^\s(),;«»“”„]{1,45})", text):
        label = match[1]
        if not re.search("[A-Za-zÀ-ž]", label) or label in known or resolver.compound(label):
            continue
        yield {"type": "source_token_candidate", "label": label, "start": match.start(1), "end": match.end(1),
               "numeric_locator": bool(re.match(r"\s*\d", text[match.end():match.end()+30])),
               "context": text[max(0, match.start()-50):match.end()+110]}
    for match in re.finditer(r"\b[A-ZÀ-Ž][\w’.'-]+(?:\s*/\s*[A-ZÀ-Ž][\w’.'-]+)?\s+\d{4}[a-z]?(?:[–-]\d{2,4})?", text):
        yield {"type": "author_year_candidate", "literal": match[0], "start": match.start(), "end": match.end(),
               "context": text[max(0, match.start()-50):match.end()+110]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True)
    parser.add_argument("--pdf-database", type=Path, required=True)
    parser.add_argument("--apparatus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.apparatus.read_text()
    rows = json.loads(raw) if raw.lstrip().startswith("[") else [json.loads(s) for s in raw.splitlines() if s]
    resolver = ComponentResolver([(x["id"], x["label"]) for x in rows], rows)
    known = {x["label"] for x in rows}
    counts = collections.Counter()
    with args.output.open("w") as out:
        def write(text, source):
            for candidate in candidates(text, known, resolver):
                out.write(json.dumps({**candidate, "source": source}, ensure_ascii=False) + "\n")
                counts[candidate["type"]] += 1
        for line in args.articles.open():
            article = json.loads(line)
            source = article["source_object"]
            write(article["article_source_text"], {"layer": "html", "url": source["final_url"], "sha256": source["sha256"]})
            for siglum in article.get("sigla", []):
                label = siglum.get("label", siglum.get("text", ""))
                if label and label not in known and not resolver.compound(label):
                    out.write(json.dumps({"type": "marked_siglum_candidate", "label": label, "record": siglum,
                                          "source": source}, ensure_ascii=False) + "\n")
                    counts["marked_siglum_candidate"] += 1
        db = sqlite3.connect(args.pdf_database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for identity, text in db.execute("SELECT id,source_faithful_text FROM pdf_article_witness"):
                write(text, {"layer": "pdf", "article_id": identity,
                             "provenance_table": "pdf_article_source_span"})
        finally:
            db.close()
    print(json.dumps({"candidate_counts": counts, "input_sha256": {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.articles, args.pdf_database, args.apparatus]}}, sort_keys=True))


if __name__ == "__main__":
    main()
