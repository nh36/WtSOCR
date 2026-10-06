"""Replay a source-only relationship packet offline and freeze predictions.

The packet is never edited. This does not infer citation ownership or apply
reviewed annotations. A repeat run verifies bytes rather than replacing them.
Keep source-bearing outputs under ignored work/, not in version control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from badw_article_parser import parse_database_article
from build_badw_entry_index import encode
from build_badw_structural_review_packet import rows
from build_badw_pdf_nested_candidates import project as nested_project
from extract_badw_lexical_records import extract_article
from extract_badw_pdf_lexical_candidates import (
    extract, load_role_reviews, load_span_reviews, ROLE_REVIEWS, SPAN_REVIEWS,
)
from parse_badw_pdf_articles import _structure, _candidates
from project_badw_structural_candidates import project, project_html

VERSION = "badw-relationship-prediction-freeze-v1"


def digest(body):
    return hashlib.sha256(body).hexdigest()


def verify_pdf_objects(objects, cache):
    """Verify immutable PDF bodies without refreshing request manifests."""
    if not objects:
        raise ValueError("PDF packet lacks source objects")
    for obj in objects:
        sha = obj["pdf_sha256"]
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid PDF source hash")
        body = (cache / "objects" / "sha256" / sha[:2] / sha).read_bytes()
        if digest(body) != sha:
            raise ValueError("cached PDF hash mismatch")


def projection_packet(packet):
    if packet["contract_version"] != "badw-blind-relationship-review-v1":
        raise ValueError("expected source-only relationship packet")
    if digest(packet["review_text"].encode()) != packet["review_text_sha256"]:
        raise ValueError("review text hash mismatch")
    if packet.get("reviewed_relationships") or packet.get("reviewer"):
        raise ValueError("predictions must be frozen before review")
    return dict(packet, contract_version="badw-structural-review-packet-v1",
                group=packet["sampling_cue"], stratum=packet["sampling_cue"],
                split="development")


def verify_unseen_pdf_cases(packets, role_reviews, span_reviews):
    """Existing exact-row reviews must not leak into unseen predictions."""
    selected = {p["identity"] for p in packets if p["source_kind"] == "pdf"}
    reviewed = {identity for identity, _ in (*role_reviews, *span_reviews)}
    if selected & reviewed:
        raise ValueError("PDF packet contains previously reviewed source identities")


def predict(packet, cache, structure=None):
    p = projection_packet(packet)
    if p["source_kind"] == "html":
        obj = p["source"]["source_object"]
        body = (cache / obj["object_path"]).read_bytes()
        if digest(body) != obj["sha256"]:
            raise ValueError("cached HTML hash mismatch")
        meta = dict(obj, fetched_at_utc=obj["fetch_timestamp_utc"],
                    delivery_type="database_article", valid_resource=True,
                    response_headers={"content-type": "text/html; charset=" + obj["decoded_encoding"]})
        article = parse_database_article(body, source_metadata=meta)
        if article["source_object"] != obj or article["article_source_text"] != p["review_text"]:
            raise ValueError("parser source differs from pinned packet")
        records = extract_article(article, snapshot_id="relationship-validation",
                                  extraction_run_id=VERSION)
        return project_html(p, records, article)
    if p["source_kind"] != "pdf" or structure is None:
        raise ValueError("missing supported PDF source structure")
    if structure["article_id"] != p["identity"]:
        raise ValueError("PDF identity mismatch")
    if structure["visual_lines"] != p["source"]["visual_lines"]:
        raise ValueError("PDF lines differ from pinned packet")
    verify_pdf_objects(p["source"]["source_objects"], cache)
    updated = dict(structure)
    updated["divisions"], _ = _structure(updated["visual_lines"])
    updated["candidates"] = _candidates(updated["visual_lines"], updated["divisions"], p["identity"])
    return project(p, nested_project(updated, extract(updated)), updated)


def freeze(path, body):
    """Never overwrite a baseline; repeat replay must be byte-identical."""
    if path.exists():
        if path.read_bytes() != body:
            raise ValueError(f"frozen output differs: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--pdf-structure", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    packets = list(rows(args.packet))
    ids = [p["identity"] for p in packets]
    if len(ids) != len(set(ids)):
        ap.error("duplicate packet identities")
    verify_unseen_pdf_cases(packets, load_role_reviews(), load_span_reviews())
    selected = {p["identity"] for p in packets if p["source_kind"] == "pdf"}
    structures = {}
    for r in rows(args.pdf_structure):
        if r["article_id"] in selected:
            if r["article_id"] in structures:
                ap.error("duplicate PDF source identity")
            structures[r["article_id"]] = r
    predictions = [predict(p, args.cache, structures.get(p["identity"]))
                   for p in sorted(packets, key=lambda p: p["identity"])]
    body = encode(predictions)
    manifest = dict(contract_version=VERSION, cases=len(predictions), sha256=digest(body),
                    inputs=[dict(path=str(p), sha256=digest(p.read_bytes()))
                            for p in (args.packet, args.pdf_structure)],
                    rule_files=[dict(path=str(p), sha256=digest(p.read_bytes()))
                                for p in sorted(Path(__file__).parent.glob("*.py"))],
                    review_contract_files=[dict(path=str(p), sha256=digest(p.read_bytes()))
                                           for p in (ROLE_REVIEWS, SPAN_REVIEWS)],
                    reviewed_annotations_applied=False, network_requests=0)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Check both artifacts before creating either when replaying a baseline.
    for path, data in ((args.output, body),
                       (args.output.with_suffix(".manifest.json"), encode([manifest]))):
        if path.exists() and path.read_bytes() != data:
            ap.error(f"frozen output differs: {path}")
    freeze(args.output, body)
    freeze(args.output.with_suffix(".manifest.json"), encode([manifest]))
    print(json.dumps({k: manifest[k] for k in ("cases", "sha256", "network_requests")}, sort_keys=True))


if __name__ == "__main__":
    main()
