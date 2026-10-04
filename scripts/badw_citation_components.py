"""Source-preserving citation components, not OCR corrections or edition guesses.

Matching views may join layout line breaks only inside registered spellings.
Every match retains its exact raw span. Compound selector grammars are enabled
only by explicit first-party description evidence, retained on each component.
"""
from __future__ import annotations

import re
from badw_pdf_bibliography import Resolver

VERSION = "badw-citation-components-v1"

# These are bounded citation conventions, not transliteration substitutions.
# Collection-number grammars without an explicit description are not enabled.
GRAMMARS = {
    "MTH3/3": (r"/[ \t\n]*\d+", "Nummer des Dokuments"),
    "MTH3/5": (r"/[ \t\n]*\d+", "Nummer des Dokuments"),
    "Ctr": (r"\d+[A-Z]?", "Textnummer"),
    "OTM": (r"\d+", "Textnummer"),
    "Folk": (r"\d+[A-Z]?", "Textnummer und Zeile"),
    "K": (r"\d+", "Textnummer nach"),
    "T": (r"\d+", "Textnummer nach"),
}


def spelling_pattern(label: str) -> str:
    """Reversible layout view: no spaces, case or character substitutions.

    A discretionary hyphen must be followed by a newline and the rest of an
    exact registered spelling. Matching ambiguity is still retained.
    """
    return r"(?:-?[ \t]*\n[ \t]*)?".join(re.escape(c) for c in label)


def following_boundary(text: str, end: int) -> bool:
    # Slash/hyphen are siglum-internal: unknown suffixes must not resolve to a
    # shorter known work. Digits remain permissible attached page locators.
    return end == len(text) or (not text[end].isalnum() and text[end] not in "_/-") or text[end].isdigit()


class ComponentResolver:
    def __init__(self, authorities: list[tuple[str, str]], rows: list[dict] = ()):
        self.legacy = Resolver(authorities)
        self.labels = self.legacy.labels
        self.patterns = [(label, re.compile(r"(?<![\w/-])" + spelling_pattern(label)))
                         for label in self.labels]
        self.grammar_evidence = {}
        for row in rows:
            label = row["label"]
            if row["kind"] == "work" and label in GRAMMARS and GRAMMARS[label][1] in row["text"]:
                self.grammar_evidence.setdefault(label, []).append({
                    "occurrence_id": row["occurrence_id"], "source_sha256": row["source_sha256"],
                    "description": row["text"]})

    def compound(self, label: str) -> tuple[str, str] | None:
        """A compound must have exactly one evidenced base/selector analysis."""
        analyses = []
        for base in sorted(self.grammar_evidence):
            if label.startswith(base) and re.fullmatch(GRAMMARS[base][0], label[len(base):]):
                analyses.append((base, label[len(base):]))
        return analyses[0] if len(analyses) == 1 else None

    def resolve(self, text: str) -> dict:
        legacy = self.legacy.resolve(text)
        rejected = list(legacy["rejected_matches"])
        rejected_spans = {(r["start"], r["end"], r["label"]) for r in rejected}
        found = []
        for label, pattern in self.patterns:
            for hit in pattern.finditer(text):
                start, end = hit.span()
                if (start, end, label) in rejected_spans:
                    continue
                selector = None
                if label in self.grammar_evidence:
                    tail = re.match(GRAMMARS[label][0], text[end:])
                    if tail:
                        selector = tail.group()
                        end += len(selector)
                if not following_boundary(text, end):
                    continue
                found.append({"start": start, "end": end, "label": text[start:end],
                    "canonical_label": label, "authority_ids": self.labels[label],
                    "selector": selector, "method": "exact_registered_spelling_with_layout",
                    "grammar_evidence": self.grammar_evidence.get(label, []) if selector else [],
                    "base_end": hit.end()})
        found.sort(key=lambda r: (r["start"], r["end"], r["canonical_label"]))
        # Prefer a complete registered spelling over a contained prefix. Do not
        # break same-span competing analyses or conflicting authority identities.
        for row in found[:]:
            containers = [other for other in found if other is not row and
                          other["start"] <= row["start"] and row["end"] <= other["end"] and
                          (other["start"], other["end"]) != (row["start"], row["end"])]
            if containers:
                found.remove(row)
                rejected.append({**row, "reason": "contained_in_complete_registered_component"})
        # A known individual work wins over a collection selector at the same
        # span only when their canonical labels differ and the former is exact.
        for row in found[:]:
            if row["selector"] and any(other["selector"] is None and
                other["start"] == row["start"] and other["end"] == row["end"] and
                other["canonical_label"] != row["canonical_label"] for other in found):
                found.remove(row)
                rejected.append({**row, "reason": "exact_work_precedes_collection_selector"})
        for row in found:
            overlap = any(other is not row and other["start"] < row["end"] and
                          row["start"] < other["end"] for other in found)
            row["status"] = "ambiguous" if overlap or len(row["authority_ids"]) != 1 else "exact_label_expansion_candidate"
        return {"contract_version": VERSION, "text": text, "matches": found,
                "rejected_matches": rejected, "legacy_spelling_candidates": legacy["matches"],
                "status": "unmatched" if not found else "ambiguous" if any(
                    r["status"] == "ambiguous" for r in found) else "exact_label_expansion_candidates"}
