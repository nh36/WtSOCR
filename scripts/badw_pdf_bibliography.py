"""Exact PDF siglum spelling candidates against first-party tooltip expansions.

These links establish an expansion, not a verified edition or citation owner.
No fuzzy matching, case folding, transliteration or OCR correction is used.
Offsets are into the unmodified citation candidate text. Unknown and competing
authorities remain explicit. HTML's stronger same-DOM-span method is separate.
"""
from __future__ import annotations

import re
from collections import defaultdict

VERSION = "badw-pdf-bibliography-v1"


class Resolver:
    def __init__(self, authorities: list[tuple[str, str]]) -> None:
        labels: dict[str, set[str]] = defaultdict(set)
        for authority_id, label in authorities:
            if label:
                labels[label].add(authority_id)
        self.labels = {label: sorted(ids) for label, ids in sorted(labels.items())}
        # Numeric locators can immediately follow a label in the printed WTS.
        # Retain overlaps (e.g. Dol / Dol4) as competing exact spellings rather
        # than choosing a longest-match reading without source review.
        self.patterns = [(label, re.compile(r"(?<!\w)" + re.escape(label) +
                          r"(?=$|[^\w]|[0-9])")) for label in self.labels]

    def resolve(self, text: str) -> dict:
        found = [{"start": m.start(), "end": m.end(), "label": label,
                  "authority_ids": self.labels[label]}
                 for label, pattern in self.patterns for m in pattern.finditer(text)]
        found.sort(key=lambda row: (row["start"], row["end"], row["label"]))
        for row in found:
            overlap = any(other is not row and other["start"] < row["end"]
                          and row["start"] < other["end"] for other in found)
            row["status"] = ("ambiguous" if overlap or len(row["authority_ids"]) != 1
                             else "exact_label_expansion_candidate")
            assert text[row["start"]:row["end"]] == row["label"]
        return {"contract_version": VERSION,
                "status": "unmatched" if not found else
                          "ambiguous" if any(r["status"] == "ambiguous" for r in found)
                          else "exact_label_expansion_candidates",
                "text": text, "matches": found}
