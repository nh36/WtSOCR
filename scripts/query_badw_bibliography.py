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
                "relations": [json.loads(r[0]) for r in self.db.execute(
                    "SELECT record_json FROM relation WHERE work_id=? ORDER BY occurrence_id,ordinal", (identity,))]}

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

    def citations_for(self, identity: str, include_candidates: bool = False) -> list[dict]:
        """Reverse links default to accepted identities; candidates require explicit opt-in."""
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM citation_target WHERE authority_id=? AND "
            "(? OR target_status='accepted_identity') ORDER BY layer,citation_id,component_ordinal",
            (identity, include_candidates))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("text")
    search.add_argument("--kind", choices=("work", "publication", "abbreviation"))
    authority = sub.add_parser("authority")
    authority.add_argument("id")
    citation = sub.add_parser("citation")
    citation.add_argument("layer", choices=("html", "pdf"))
    citation.add_argument("id")
    reverse = sub.add_parser("citations-for")
    reverse.add_argument("id")
    reverse.add_argument("--include-candidates", action="store_true")
    args = parser.parse_args()
    db = Bibliography(args.database)
    try:
        if args.command == "search":
            result = db.search(args.text, args.kind)
        elif args.command == "authority":
            result = db.authority(args.id)
        elif args.command == "citation":
            result = db.citation(args.layer, args.id)
        else:
            result = db.citations_for(args.id, args.include_candidates)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
