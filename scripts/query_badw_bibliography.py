"""Read-only source-authority queries; never infer editions from spelling links."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


class Bibliography:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        self.db.execute("PRAGMA query_only=ON")
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    def search(self, text: str, kind: str | None = None) -> list[dict]:
        """Literal, case-sensitive substring search; SQL wildcards are not input syntax."""
        return [json.loads(row[0]) for row in self.db.execute(
            "SELECT record_json FROM authority WHERE instr(label,?)>0 "
            "AND (? IS NULL OR kind=?) ORDER BY kind,label,id", (text, kind, kind))]

    def authority(self, identity: str) -> dict | None:
        row = self.db.execute("SELECT record_json FROM authority WHERE id=?", (identity,)).fetchone()
        if row is None:
            return None
        return {"authority": json.loads(row[0]),
                "occurrences": [json.loads(r[0]) for r in self.db.execute(
                    "SELECT record_json FROM occurrence WHERE authority_id=? ORDER BY id", (identity,))],
                "print_occurrences": [json.loads(r[0]) for r in self.db.execute(
                    "SELECT record_json FROM print_occurrence WHERE authority_id=? ORDER BY id", (identity,))],
                "publication_relations": [json.loads(r[0]) for r in self.db.execute(
                    "SELECT record_json FROM publication_relation WHERE source_id=? OR target_id=? ORDER BY id", (identity, identity))],
                "relations": [json.loads(r[0]) for r in self.db.execute(
                    "SELECT record_json FROM relation WHERE work_id=? ORDER BY occurrence_id,ordinal", (identity,))]}

    def reconciliation(self) -> dict | None:
        row = self.db.execute("SELECT record_json FROM apparatus_summary WHERE id='completed-registered-corpus'").fetchone()
        return json.loads(row[0]) if row else None

    def scholarly_notes(self) -> list[dict]:
        return [json.loads(r[0]) for r in self.db.execute("SELECT record_json FROM apparatus_annotation ORDER BY id")]

    def canonical_history(self, identity: str) -> dict | None:
        row = self.db.execute("SELECT canonical_id FROM canonical_membership WHERE authority_id=?", (identity,)).fetchone()
        canonical = row[0] if row and not identity.startswith('publication-') else identity
        history = self.db.execute("SELECT record_json FROM authority_history WHERE canonical_id=?", (canonical,)).fetchone()
        return json.loads(history[0]) if history else None

    def citation(self, layer: str, citation_id: str) -> dict | None:
        row = self.db.execute("SELECT record_json FROM citation_resolution WHERE layer=? AND citation_id=?",
                              (layer, citation_id)).fetchone()
        if row is None:
            return None
        targets = [dict(r) for r in self.db.execute(
            "SELECT t.*,a.kind,a.label FROM citation_target t JOIN authority a ON a.id=t.authority_id "
            "WHERE t.layer=? AND t.citation_id=? ORDER BY component_ordinal,authority_id", (layer, citation_id))]
        return {"layer": layer, "citation_id": citation_id, "resolution": json.loads(row[0]),
                "accepted_targets": [r for r in targets if r["target_status"] == "accepted_identity"],
                "candidate_targets": [r for r in targets if r["target_status"] == "candidate"],
                "limitations": "Accepted identity is not a verified edition or a fully parsed citation"}

    def apparatus_history(self, identity: str) -> dict | None:
        """Order reviewed appearances without asserting an exhaustive first introduction.

        Delivery ranges describe the manifestation, not a publication date. Legacy
        occurrences without reviewed chronology remain visible in a separate list.
        Alternate typesettings remain occurrences but are not new introductions.
        """
        authority = self.authority(identity)
        if authority is None:
            return None
        ordered, undated = [], []
        for occurrence in authority["print_occurrences"]:
            review = occurrence.get("review", {})
            chronology = review.get("chronology", {})
            span = chronology.get("delivery_range")
            item = {"occurrence": occurrence, "chronology": chronology,
                    "manifestation_of": review.get("manifestation_of"),
                    "variants": review.get("variants", [])}
            if (isinstance(span, list) and len(span) == 2
                    and all(type(n) is int for n in span) and span[0] <= span[1]):
                ordered.append(item)
            else:
                undated.append(item)
        ordered.sort(key=lambda item: (
            *item["chronology"]["delivery_range"], item["occurrence"]["id"]))
        appearances = [item for item in ordered if not item["manifestation_of"]]
        earliest = []
        if appearances:
            first_range = appearances[0]["chronology"]["delivery_range"]
            earliest = [item["occurrence"]["id"] for item in appearances
                        if item["chronology"]["delivery_range"] == first_range]
        return {"authority": authority["authority"], "ordered_print_occurrences": ordered,
                "occurrences_without_delivery_order": undated,
                "earliest_observed_occurrence_ids": earliest,
                "online_occurrences": authority["occurrences"],
                "publication_relations": authority["publication_relations"],
                "limitations": "Earliest observed in reviewed occurrences; not an exhaustive first WTS introduction. Delivery-range order is not a publication date."}

    def citations_for(self, identity: str, include_candidates: bool = False) -> list[dict]:
        """Reverse links default to accepted identities; candidates require explicit opt-in."""
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM citation_target WHERE authority_id=? AND "
            "(? OR target_status='accepted_identity') ORDER BY layer,citation_id,component_ordinal",
            (identity, include_candidates))]

    def literal_citations(self, text: str) -> list[dict]:
        """Search preserved citation wording, independently of resolved identity."""
        result = []
        for row in self.db.execute("SELECT layer,citation_id,record_json FROM citation_resolution ORDER BY layer,citation_id"):
            resolution = json.loads(row["record_json"])
            if text in resolution["text"]:
                result.append({"layer": row["layer"], "citation_id": row["citation_id"], "resolution": resolution})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("reconciliation")
    sub.add_parser("scholarly-notes")
    canonical = sub.add_parser("canonical-history")
    canonical.add_argument("id")
    search = sub.add_parser("search")
    search.add_argument("text")
    search.add_argument("--kind", choices=("work", "publication", "abbreviation"))
    authority = sub.add_parser("authority")
    authority.add_argument("id")
    history = sub.add_parser("apparatus-history")
    history.add_argument("id")
    citation = sub.add_parser("citation")
    citation.add_argument("layer", choices=("html", "pdf"))
    citation.add_argument("id")
    reverse = sub.add_parser("citations-for")
    reverse.add_argument("id")
    reverse.add_argument("--include-candidates", action="store_true")
    literal = sub.add_parser("literal-citations")
    literal.add_argument("text")
    args = parser.parse_args()
    db = Bibliography(args.database)
    try:
        if args.command == "reconciliation":
            result = db.reconciliation()
        elif args.command == "scholarly-notes":
            result = db.scholarly_notes()
        elif args.command == "canonical-history":
            result = db.canonical_history(args.id)
        elif args.command == "search":
            result = db.search(args.text, args.kind)
        elif args.command == "authority":
            result = db.authority(args.id)
        elif args.command == "apparatus-history":
            result = db.apparatus_history(args.id)
        elif args.command == "citation":
            result = db.citation(args.layer, args.id)
        elif args.command == "literal-citations":
            result = db.literal_citations(args.text)
        else:
            result = db.citations_for(args.id, args.include_candidates)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
