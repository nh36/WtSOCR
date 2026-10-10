"""Exact reviewed citation identities; never a fuzzy spelling/year rule.

Offsets address the original Unicode citation. Evidence objects and reviewed
target occurrences are hash-pinned. A work candidate is not an accepted edge;
neither it nor a reviewed identity changes the literal year or verifies a locator.
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
                 registry: Path | None, printed: list[dict] | None = None):
        self.reviews, self.seen = {}, set()
        if path is None:
            return
        occurrences = {r["occurrence_id"]: r for r in rows}
        print_occurrences = {r["id"]: r for r in printed or []}
        prints = {}
        if registry:
            with registry.open(encoding="utf-8") as stream:
                prints = {r["sha256"]: r for r in csv.DictReader(stream, delimiter="\t")}
        checked = set()
        with path.open(encoding="utf-8") as stream:
            for review in csv.DictReader(stream, delimiter="\t"):
                key = review["layer"], review["citation_id"]
                if key in self.reviews or key[0] not in {"html", "pdf"}:
                    raise ValueError("duplicate or unsupported citation review")
                if not re.fullmatch("[0-9a-f]{64}", review["text_sha256"]) or not review["evidence_note"].strip():
                    raise ValueError("citation review lacks source hash/note")
                source_keys = ("source_article_id", "source_text_sha256", "source_start", "source_end")
                if any(review.get(k) for k in source_keys):
                    if (not all(review.get(k) for k in source_keys) or
                            not re.fullmatch("[0-9a-f]{64}", review["source_text_sha256"]) or
                            not all(review[k].isdecimal() for k in ("source_start", "source_end"))):
                        raise ValueError("incomplete or invalid reviewed source-span binding")
                if key[0] == "html" and not all(review.get(k) for k in source_keys):
                    raise ValueError("HTML citation review requires exact source-span binding")
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
                if review["status"] in {"reviewed_identity", "reviewed_external_identity", "reviewed_work_candidate"}:
                    if any(review.get(k) for k in ("print_occurrence_id", "print_source_sha256")):
                        raise ValueError("online citation review must not supply a print target")
                    target = occurrences.get(review["online_occurrence_id"])
                    if (not target or target["source_sha256"] != review["online_source_sha256"] or
                            target["kind"] not in {"publication", "abbreviation"}):
                        raise ValueError("citation target occurrence/hash mismatch")
                    review["authority_id"] = target["id"]
                    review["kind"] = target["kind"]
                    external = target.get("scope") == "reviewed_external"
                    if external != (review["status"] == "reviewed_external_identity"):
                        raise ValueError("citation review target scope mismatch")
                    if review["status"] == "reviewed_work_candidate":
                        if target["kind"] != "publication" or not target.get("year"):
                            raise ValueError("work candidate requires publication/year evidence")
                        review["target_year"] = target["year"]
                    review["start"], review["end"] = int(review["start"]), int(review["end"])
                elif review["status"] == "reviewed_print_identity":
                    target = print_occurrences.get(review.get("print_occurrence_id"))
                    if (not target or target["candidate"]["pdf_sha256"] != review.get("print_source_sha256") or
                            review["online_occurrence_id"] or review["online_source_sha256"]):
                        raise ValueError("citation print target occurrence/hash mismatch")
                    review["authority_id"], review["kind"] = target["authority_id"], "publication"
                    review["start"], review["end"] = int(review["start"]), int(review["end"])
                elif review["status"] == "unresolved_publication_or_edition":
                    if any(review.get(k) for k in ("online_occurrence_id", "online_source_sha256", "print_occurrence_id", "print_source_sha256", "start", "end")):
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
        if review["status"] not in {"reviewed_identity", "reviewed_print_identity", "reviewed_external_identity", "reviewed_work_candidate"}:
            return result
        if result["matches"] or result.get("unresolved_dom_components"):
            raise ValueError("exact citation review requires an unmatched source occurrence")
        start, end = review["start"], review["end"]
        if not 0 <= start < end <= len(result["text"]):
            raise ValueError("reviewed citation span outside source")
        for marker in re.finditer(r"⟦UNKNOWN:[^⟧]*⟧", result["text"]):
            if any(marker.start() < boundary < marker.end() for boundary in (start, end)):
                raise ValueError("reviewed citation span bisects an unknown-glyph marker")
        years = re.findall(r"\b(?:1[5-9]|20)\d{2}[a-z]?\b", result["text"][start:end])
        candidate = review["status"] == "reviewed_work_candidate"
        if candidate and (len(years) != 1 or years[0] == review["target_year"]):
            raise ValueError("work candidate requires an explicit differing citation year")
        result["matches"].append({"start": start, "end": end,
            "label": result["text"][start:end], "authority_ids": [review["authority_id"]],
            "status": ("reviewed_work_candidate" if candidate else
                       "exact_external_publication_row" if review["status"] == "reviewed_external_identity" else
                       "exact_print_publication_row" if review["status"] == "reviewed_print_identity"
                       else "exact_online_" + review["kind"] + "_row"),
            "method": "exact_citation_source_review", "review_evidence": review,
            "edition_status": "year_discrepancy_unresolved" if candidate else "unreviewed", "locator_status": "unreviewed",
            "publication_year_relation": ({"literal_year": years[0], "target_year": review["target_year"],
                "status": "reviewed_candidate_not_a_year_correction"} if candidate else None),
            "literal_years": re.findall(r"\b(?:1[5-9]|20)\d{2}[a-z]?\b", result["text"]),
            "print_status": "identity_reviewed_only"})
        result["matches"].sort(key=lambda m: (m["start"], m["end"], m["label"]))
        result["status"] = ("reviewed_work_candidates" if candidate else
                            "exact_external_publication_rows" if review["status"] == "reviewed_external_identity" else
                            "exact_print_publication_rows" if review["status"] == "reviewed_print_identity"
                            else "exact_online_source_rows")
        return result

    def apply_source(self, layer, article_id, text, start, end, result):
        """Apply a reviewed identity only to its exact immutable source view."""
        identity = f"{article_id}:reviewed:{start}:{end}"
        review = self.reviews.get((layer, identity))
        if review is None:
            return result
        if (review.get("source_article_id") != article_id or
                review.get("source_text_sha256") != hashlib.sha256(text.encode()).hexdigest() or
                review.get("source_start") != str(start) or review.get("source_end") != str(end) or
                not 0 <= start < end <= len(text) or result["text"] != text[start:end]):
            raise ValueError("reviewed source article/span/hash mismatch")
        return self.apply(layer, identity, result)

    def finish(self):
        if set(self.reviews) != self.seen:
            raise ValueError("orphan citation reviews absent from staging snapshot")

    def supplemental_citations(self, db):
        """Exact reviewed source spans absent from the candidate parser.

        This is a bibliography observation, not inferred sense/example ownership.
        The existing article and its entire immutable Unicode text are hash-bound.
        """
        for (layer, identity), review in sorted(self.reviews.items()):
            article_id = review.get("source_article_id")
            if not article_id:
                continue
            if layer != "pdf" or identity != article_id + ":reviewed:" + review["source_start"] + ":" + review["source_end"]:
                raise ValueError("invalid reviewed source-span identity")
            row = db.execute("SELECT source_faithful_text FROM pdf_article_witness WHERE id=?", (article_id,)).fetchone()
            if row is None or hashlib.sha256(row[0].encode()).hexdigest() != review.get("source_text_sha256"):
                raise ValueError("reviewed source article/hash mismatch")
            start, end = int(review["source_start"]), int(review["source_end"])
            if not 0 <= start < end <= len(row[0]):
                raise ValueError("reviewed source span outside article")
            text = row[0][start:end]
            if hashlib.sha256(text.encode()).hexdigest() != review["text_sha256"]:
                raise ValueError("reviewed source-span text hash mismatch")
            review["source_field"] = "source_faithful_text"
            yield identity, text
