"""Reviewed external publications; never inferred from citation author/year.

Use the common authority/occurrence contract. External records are excluded
from automatic label matching and require an exact citation review.
"""
import csv
import hashlib
from pathlib import Path

from badw_bibliography_citation_reviews import sha


def load_publications(path: Path | None, cache: Path) -> list[dict]:
    if path is None:
        return []
    records, seen = [], set()
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            required = ("key", "label", "year", "author", "title", "publisher",
                        "source_url", "source_sha256", "evidence_note")
            if any(not row.get(k, "").strip() for k in required):
                raise ValueError("external publication lacks reviewed metadata/evidence")
            if row["key"] in seen or not row["year"].isdecimal() or len(row["year"]) != 4:
                raise ValueError("duplicate external publication or invalid year")
            seen.add(row["key"])
            digest = row["source_sha256"]
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid external source hash")
            obj = cache / "objects" / "sha256" / digest[:2] / digest
            if not obj.is_file() or sha(obj) != digest:
                raise ValueError("external publication source object/hash mismatch")
            if not row["source_url"].startswith("https://"):
                raise ValueError("external publication requires HTTPS provenance")
            identity = hashlib.sha256(row["key"].encode()).hexdigest()[:32]
            records.append(dict(id="publication-external-" + identity,
                occurrence_id="occurrence-external-" + identity, kind="publication",
                scope="reviewed_external", status="reviewed_external_identity",
                label=row["label"], year=row["year"], source_url=row["source_url"],
                source_sha256=digest, text=row["title"], evidence_note=row["evidence_note"],
                reviewed_metadata=dict(entry_type="book", fields={
                    k: row[k] for k in ("author", "title", "publisher", "year", "isbn", "series", "volume")
                    if row.get(k)})))
    return sorted(records, key=lambda r: r["id"])
