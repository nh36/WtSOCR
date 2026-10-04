"""Exact reviewed citation identities; never a fuzzy spelling/year rule.

Offsets address the original Unicode citation. Evidence objects and official
target occurrences are hash-pinned. An unresolved disposition is not an edge.
"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class CitationReviews:
    def __init__(self, path: Path | None, rows: list[dict], cache: Path,
                 registry: Path | None):
        self.reviews, self.seen = {}, set()
        if path is None:
            return
        occurrences = {r["occurrence_id"]: r for r in rows}
        prints = {}
        if registry:
            with registry.open(encoding="utf-8") as stream:
                prints = {r["sha256"]: r for r in csv.DictReader(stream, delimiter="\t")}
        checked = set()
        with path.open(encoding="utf-8") as stream:
            for review in csv.DictReader(stream, delimiter="\t"):
                key = review["layer"], review["citation_id"]
                if key in self.reviews or key[0] != "pdf":
                    raise ValueError("duplicate or unsupported citation review")
                if not re.fullmatch("[0-9a-f]{64}", review["text_sha256"]) or not review["evidence_note"].strip():
                    raise ValueError("citation review lacks source hash/note")
                evidence = review["evidence_sha256"]
                if not re.fullmatch("[0-9a-f]{64}", evidence):
                    raise ValueError("invalid citation evidence hash")
                if evidence in prints:
                    obj = Path(prints[evidence]["filename"])
                else:
                    obj = cache / "objects" / "sha256" / evidence[:2] / evidence
                if evidence not in checked:
                    if not obj.is_file() or sha(obj) != evidence:
                        raise ValueError("citation evidence object/hash mismatch")
                    checked.add(evidence)
                if not review["evidence_page"].isdecimal() or int(review["evidence_page"]) < 1:
                    raise ValueError("citation evidence requires positive page")
                if evidence in prints and int(review["evidence_page"]) > int(prints[evidence]["pages"]):
                    raise ValueError("citation evidence page outside registered source")
                if review["status"] == "reviewed_identity":
                    target = occurrences.get(review["online_occurrence_id"])
                    if (not target or target["source_sha256"] != review["online_source_sha256"] or
                            target["kind"] not in {"publication", "abbreviation"}):
                        raise ValueError("citation target occurrence/hash mismatch")
                    review["authority_id"] = target["id"]
                    review["kind"] = target["kind"]
                    review["start"], review["end"] = int(review["start"]), int(review["end"])
                elif review["status"] == "unresolved_publication_or_edition":
                    if any(review[k] for k in ("online_occurrence_id", "online_source_sha256", "start", "end")):
                        raise ValueError("unresolved disposition must not supply a target")
                else:
                    raise ValueError("unsupported citation review status")
                self.reviews[key] = review

    def apply(self, layer: str, citation_id: str, result: dict) -> dict:
        key = layer, citation_id
        review = self.reviews.get(key)
        if review is None:
            return result
        self.seen.add(key)
        if hashlib.sha256(result["text"].encode("utf-8")).hexdigest() != review["text_sha256"]:
            raise ValueError("stale citation review text hash")
        result["citation_review"] = review
        if review["status"] != "reviewed_identity":
            return result
        if result["matches"] or result.get("unresolved_dom_components"):
            raise ValueError("exact citation review requires an unmatched source occurrence")
        start, end = review["start"], review["end"]
        if not 0 <= start < end <= len(result["text"]):
            raise ValueError("reviewed citation span outside source")
        for marker in re.finditer(r"⟦UNKNOWN:[^⟧]*⟧", result["text"]):
            if any(marker.start() < boundary < marker.end() for boundary in (start, end)):
                raise ValueError("reviewed citation span bisects an unknown-glyph marker")
        result["matches"].append({"start": start, "end": end,
            "label": result["text"][start:end], "authority_ids": [review["authority_id"]],
            "status": "exact_online_" + review["kind"] + "_row",
            "method": "exact_citation_source_review", "review_evidence": review,
            "edition_status": "unreviewed", "print_status": "identity_reviewed_only"})
        result["matches"].sort(key=lambda m: (m["start"], m["end"], m["label"]))
        result["status"] = "exact_online_source_rows"
        return result

    def finish(self):
        if set(self.reviews) != self.seen:
            raise ValueError("orphan citation reviews absent from staging snapshot")
