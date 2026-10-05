"""Exact source-backed claims, separate from accepted publication links.

A publication can witness a work identity without being the cited edition.
Likewise a locator corroborated in another edition is not a verified locator
in the unresolved cited edition. An explicit author-confirmed year correction
may accept a reviewed publication candidate; it never changes source wording
or verifies a locator merely by accepting that publication.
"""
from __future__ import annotations

import csv
from datetime import date
import hashlib
from pathlib import Path
import re

from pypdf import PdfReader

from badw_bibliography_citation_reviews import sha


class CitationClaims:
    def __init__(self, path: Path | None, cache: Path):
        self.claims, self.seen = {}, set()
        if path is None:
            return
        checked = {}
        with path.open(encoding="utf-8") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                key = row["layer"], row["citation_id"], row["claim"]
                if key in self.claims or key[0] not in {"html", "pdf"}:
                    raise ValueError("duplicate or unsupported citation claim")
                allowed = {"work_identity": "reviewed_work_identity",
                           "locator": "corroborated_in_other_edition",
                           "citation_year": "reviewed_year_correction"}
                if allowed.get(row["claim"]) != row["status"]:
                    raise ValueError("unsupported claim/status combination")
                if (not row["evidence_note"].strip() or
                        not row["witness_authority_id"].strip() or
                        not row["literal_locator"].strip()):
                    raise ValueError("citation claim lacks evidence or locator")
                if row["claim"] == "citation_year":
                    # A private scholarly communication is an assertion, not a
                    # fabricated public evidence-object hash or a verified locator.
                    if row.get("evidence_kind") != "author_confirmation_reported_by_user":
                        raise ValueError("year correction requires explicit author-confirmation provenance")
                    try:
                        date.fromisoformat(row.get("evidence_reported_date") or "")
                    except ValueError as exc:
                        raise ValueError("year correction requires ISO reported date") from exc
                    if (not re.fullmatch("[0-9a-f]{64}", row["text_sha256"]) or
                            any(row.get(k) for k in ("evidence_sha256", "evidence_pdf_page", "witness_printed_page")) or
                            not re.fullmatch(r"[0-9]{4}", row.get("corrected_year") or "")):
                        raise ValueError("invalid author-confirmed year assertion")
                    self.claims[key] = row
                    continue
                if not row["witness_printed_page"].strip():
                    raise ValueError("citation claim lacks evidence or locator")
                for field in ("text_sha256", "evidence_sha256"):
                    if not re.fullmatch("[0-9a-f]{64}", row[field]):
                        raise ValueError("invalid claim hash")
                digest = row["evidence_sha256"]
                obj = cache / "objects" / "sha256" / digest[:2] / digest
                if digest not in checked:
                    if not obj.is_file() or sha(obj) != digest:
                        raise ValueError("claim evidence object/hash mismatch")
                    checked[digest] = len(PdfReader(obj).pages)
                page = row["evidence_pdf_page"]
                if not page.isdecimal() or not 1 <= int(page) <= checked[digest]:
                    raise ValueError("claim evidence page outside PDF")
                row["evidence_pdf_page"] = int(page)
                self.claims[key] = row

    def apply(self, layer: str, citation_id: str, result: dict):
        claims = [r for key, r in sorted(self.claims.items()) if key[:2] == (layer, citation_id)]
        for row in claims:
            if hashlib.sha256(result["text"].encode("utf-8")).hexdigest() != row["text_sha256"]:
                raise ValueError("stale citation claim text hash")
            if not re.search(r":\s*" + re.escape(row["literal_locator"]) + r"(?!\w)", result["text"]):
                raise ValueError("claim locator absent from citation")
            matches = [m for m in result["matches"]
                       if m["authority_ids"] == [row["witness_authority_id"]]
                       and m.get("method") == "exact_citation_source_review"]
            if len(matches) != 1:
                raise ValueError("claim requires unique exact reviewed witness")
            if row["claim"] == "locator" and matches[0].get("edition_status") != "year_discrepancy_unresolved":
                raise ValueError("cross-edition locator requires unresolved cited edition")
            if row["claim"] == "citation_year":
                match = matches[0]
                relation = match.get("publication_year_relation")
                if (match.get("status") != "reviewed_work_candidate" or not relation or
                        relation["target_year"] != row["corrected_year"]):
                    raise ValueError("year correction requires exact differing-year publication candidate")
                match["publication_year_relation"] = dict(relation,
                    status="reviewed_year_correction", evidence=dict(row))
                match["status"] = "exact_online_publication_row"
                # Confirmed publication/year, not a verified page or printing.
                match["edition_status"] = "publication_year_author_confirmed"
                result["status"] = "exact_online_source_rows"
            result.setdefault("reviewed_claims", []).append(dict(row))
            self.seen.add((layer, citation_id, row["claim"]))
        return result

    def finish(self):
        if set(self.claims) != self.seen:
            raise ValueError("orphan citation claims absent from staging snapshot")
