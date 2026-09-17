#!/usr/bin/env python3
"""Inventory unresolved glyphs in a canonical BAdW page corpus.

This deliberately reads canonical pages, rather than every overlapping source
PDF.  Counts therefore describe the text that is still unresolved in the
deduplicated source corpus.  The output is evidence only: this module never
infers or installs glyph mappings.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data/badw_pdf_glyph_mappings.tsv"
CONTRACT_VERSION = "badw-canonical-glyph-residuals-v2"
UNKNOWN_FIELDS = (
    "family",
    "style",
    "cid_hex",
    "glyph_signature",
    "registry_relation",
    "same_cid_registry_unicode",
    "same_outline_registry_unicode",
    "occurrence_count",
    "canonical_page_count",
    "volume_count",
    "volumes",
    "font_program_hashes",
    "font_resource_hashes",
    "page_ids",
    "printed_pages",
    "example_urls",
    "example_contexts",
)


def _registry_indexes(
    path: Path,
) -> tuple[
    dict[tuple[str, str, str, str], set[str]],
    dict[tuple[str, str, str], set[str]],
    dict[tuple[str, str, str], set[str]],
    set[tuple[str, str]],
    set[str],
]:
    exact: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    by_cid: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    by_outline: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    family_styles: set[tuple[str, str]] = set()
    families: set[str] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            family = row["family"]
            style = row["style"]
            cid = row["cid"].upper().zfill(4)
            signature = row["glyph_signature"]
            unicode_value = row["unicode"]
            exact[(family, style, cid, signature)].add(unicode_value)
            by_cid[(family, style, cid)].add(unicode_value)
            by_outline[(family, style, signature)].add(unicode_value)
            family_styles.add((family, style))
            families.add(family)
    return dict(exact), dict(by_cid), dict(by_outline), family_styles, families


def _registry_relation(
    key: tuple[str, str, str, str],
    indexes: tuple[
        dict[tuple[str, str, str, str], set[str]],
        dict[tuple[str, str, str], set[str]],
        dict[tuple[str, str, str], set[str]],
        set[tuple[str, str]],
        set[str],
    ],
) -> tuple[str, str, str]:
    exact, by_cid, by_outline, family_styles, families = indexes
    family, style, cid, signature = key
    exact_values = exact.get(key, set())
    cid_values = by_cid.get((family, style, cid), set())
    outline_values = by_outline.get((family, style, signature), set())
    if exact_values:
        relation = "exact_identity_registered"
    elif cid_values and outline_values:
        relation = (
            "registered_cid_and_outline_agree"
            if cid_values == outline_values and len(cid_values) == 1
            else "ambiguous_registry_analogy"
        )
    elif outline_values:
        relation = (
            "registered_outline_different_cid"
            if len(outline_values) == 1
            else "ambiguous_registry_analogy"
        )
    elif cid_values:
        relation = (
            "registered_cid_new_outline"
            if len(cid_values) == 1
            else "ambiguous_registry_analogy"
        )
    elif (family, style) in family_styles:
        relation = "novel_identity"
    elif family in families:
        relation = "style_not_in_registry"
    else:
        relation = "family_not_in_registry"
    return (
        relation,
        " | ".join(sorted(cid_values)),
        " | ".join(sorted(outline_values)),
    )


def _write_tsv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNKNOWN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _glyph_context(runs: list[dict[str, object]], run_index: int, limit: int = 80) -> str:
    left = max(0, run_index - 3)
    right = min(len(runs), run_index + 4)
    text = "".join(str(run.get("decoded_unicode", "")) for run in runs[left:right])
    return " ".join(text.split())[:limit]


def build_residual_inventory(
    canonical_root: Path,
    output_root: Path,
    volumes: Iterable[int] = (2, 3, 4),
    registry_path: Path = DEFAULT_REGISTRY,
) -> dict[str, object]:
    """Write a deterministic canonical-only unknown-glyph inventory."""

    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to mix output with existing data: {output_root}")

    indexes = _registry_indexes(registry_path)
    counts: Counter[tuple[str, str, str, str]] = Counter()
    pages: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    seen_volumes: defaultdict[tuple[str, str, str, str], set[int]] = defaultdict(set)
    program_hashes: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    resource_hashes: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    printed_pages: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    urls: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    contexts: defaultdict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    page_count = 0
    unknown_page_count = 0

    selected_volumes = tuple(sorted(set(volumes)))
    for volume in selected_volumes:
        pages_root = canonical_root / f"volume_{volume}" / "pages"
        paths = sorted(pages_root.glob("*.json.gz"))
        if not paths:
            raise FileNotFoundError(f"no canonical pages under {pages_root}")
        for path in paths:
            page_count += 1
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                record = json.load(handle)
            fonts = {
                str(font["font_id"]): font
                for font in record.get("representative_fonts", [])
            }
            runs = record["positioned_page"]["positioned_text_runs"]
            page_had_unknown = False
            for run_index, run in enumerate(runs):
                font = fonts.get(str(run.get("font_id", "")), {})
                for glyph in run.get("glyphs", []):
                    if not glyph.get("unknown"):
                        continue
                    page_had_unknown = True
                    key = (
                        str(font.get("family", "")),
                        str(font.get("style", "")),
                        str(glyph.get("cid_hex", "")),
                        str(glyph.get("glyph_signature", "")),
                    )
                    counts[key] += 1
                    pages[key].add(str(record["page_id"]))
                    seen_volumes[key].add(volume)
                    if font.get("program_sha256"):
                        program_hashes[key].add(str(font["program_sha256"]))
                    if font.get("font_resource_sha256"):
                        resource_hashes[key].add(str(font["font_resource_sha256"]))
                    printed_pages[key].add(f"v{volume}:p{record.get('printed_page', '')}")
                    urls[key].add(str(record["representative_source"]["canonical_url"]))
                    contexts[key].add(_glyph_context(runs, run_index))
            unknown_page_count += int(page_had_unknown)

    rows = []
    for key, occurrence_count in sorted(
        counts.items(), key=lambda item: (-item[1], -len(pages[item[0]]), item[0])
    ):
        relation, cid_values, outline_values = _registry_relation(key, indexes)
        rows.append(
            {
                "family": key[0],
                "style": key[1],
                "cid_hex": key[2],
                "glyph_signature": key[3],
                "registry_relation": relation,
                "same_cid_registry_unicode": cid_values,
                "same_outline_registry_unicode": outline_values,
                "occurrence_count": occurrence_count,
                "canonical_page_count": len(pages[key]),
                "volume_count": len(seen_volumes[key]),
                "volumes": ",".join(str(value) for value in sorted(seen_volumes[key])),
                "font_program_hashes": ",".join(sorted(program_hashes[key])),
                "font_resource_hashes": ",".join(sorted(resource_hashes[key])),
                "page_ids": ",".join(sorted(pages[key])),
                "printed_pages": ",".join(sorted(printed_pages[key])),
                "example_urls": " | ".join(sorted(urls[key])[:5]),
                "example_contexts": " | ".join(sorted(contexts[key])[:5]),
            }
        )

    _write_tsv(output_root / "unknown_glyph_identities.tsv", rows)
    by_family = Counter()
    identities_by_family = Counter()
    by_relation = Counter()
    occurrences_by_relation = Counter()
    for row in rows:
        family = str(row["family"] or "(unknown)")
        by_family[family] += int(row["occurrence_count"])
        identities_by_family[family] += 1
        relation = str(row["registry_relation"])
        by_relation[relation] += 1
        occurrences_by_relation[relation] += int(row["occurrence_count"])
    summary: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "canonical_root": canonical_root.as_posix(),
        "registry_path": registry_path.as_posix(),
        "registry_sha256": sha256(registry_path.read_bytes()).hexdigest(),
        "volumes": list(selected_volumes),
        "canonical_pages": page_count,
        "pages_with_unknowns": unknown_page_count,
        "distinct_unknown_identities": len(rows),
        "unknown_occurrences": sum(counts.values()),
        "unknown_identities_by_family": dict(sorted(identities_by_family.items())),
        "unknown_occurrences_by_family": dict(sorted(by_family.items())),
        "unknown_identities_by_registry_relation": dict(sorted(by_relation.items())),
        "unknown_occurrences_by_registry_relation": dict(
            sorted(occurrences_by_relation.items())
        ),
        "inventory_sha256": sha256(
            (output_root / "unknown_glyph_identities.tsv").read_bytes()
        ).hexdigest(),
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--volume", action="append", type=int, choices=(2, 3, 4))
    args = parser.parse_args()
    summary = build_residual_inventory(
        args.canonical_root,
        args.output_root,
        args.volume or (2, 3, 4),
        args.registry,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
