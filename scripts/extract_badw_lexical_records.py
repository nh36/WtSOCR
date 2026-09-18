#!/usr/bin/env python3
"""Emit source-faithful lexical records from cached BAdW HTML parser records.

The input is the deterministic JSONL emitted by ``badw_article_parser.py``.
This tool performs no WtSOCR matching, OCR normalisation, or bibliographic
authority resolution.  It makes BAdW's editorial structure queryable while
leaving raw HTML in the ignored source cache and preserving every emitted
field's exact cached-object provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from validate_lexical_record_contract import CONTRACT_VERSION, validate


EXTRACTOR_VERSION = "badw-html-lexical-extractor-v1"


class ExtractionError(ValueError):
    """An article cannot be represented without inventing a source span."""


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record_id(kind: str, source_identifier: str, ordinal: int | None = None) -> str:
    suffix = _digest(source_identifier)
    return f"badw:{kind}:{suffix}" + (f":{ordinal}" if ordinal is not None else "")


def _source_span(article: dict[str, Any], field: dict[str, Any] | None) -> dict[str, Any]:
    """Return an auditable span in ``article_source_text`` for a parsed field."""

    if not isinstance(field, dict):
        raise ExtractionError("missing located source field")
    locator = field.get("locator")
    source = article.get("source_object")
    source_id = article.get("source_identifier")
    if not isinstance(locator, dict) or not isinstance(source, dict) or not isinstance(source_id, str):
        raise ExtractionError("source field lacks locator or source identity")
    start, end = locator.get("visible_text_start"), locator.get("visible_text_end")
    source_hash = source.get("sha256")
    if (not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start
            or not isinstance(source_hash, str) or len(source_hash) != 64):
        raise ExtractionError("source field lacks a non-empty visible-text span")
    return {
        "source_id": source_id,
        "source_sha256": source_hash,
        "field": "article_source_text",
        "start": start,
        "end": end,
    }


def _field_text(field: dict[str, Any] | None, name: str) -> str:
    if not isinstance(field, dict) or not isinstance(field.get("source_text"), str):
        raise ExtractionError(f"{name} lacks source_text")
    return field["source_text"]


def _base_record(
    record_type: str,
    identifier: str,
    spans: list[dict[str, Any]],
    snapshot_id: str,
    extraction_run_id: str,
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": record_type,
        "id": identifier,
        "source_snapshot_id": snapshot_id,
        "extraction_run_id": extraction_run_id,
        "source_spans": spans,
    }


def extract_article(
    article: dict[str, Any], *, snapshot_id: str, extraction_run_id: str
) -> list[dict[str, Any]]:
    """Turn one parsed article into ordered v2 lexical records.

    The BAdW parser's divisions supply sense/example links.  Examples outside
    a division remain entry-level rather than being assigned heuristically.
    """

    source_identifier = article.get("source_identifier")
    lemma_field = article.get("lemma_field")
    if not isinstance(source_identifier, str) or not source_identifier:
        raise ExtractionError("article has no source_identifier")
    lemma = _field_text(lemma_field, "lemma")
    lemma_span = _source_span(article, lemma_field)
    tibetan_field = article.get("tibetan_heading")
    tibetan = _field_text(tibetan_field, "tibetan heading") if tibetan_field else ""
    entry_spans = [lemma_span]
    if tibetan_field:
        entry_spans.append(_source_span(article, tibetan_field))
    entry_id = _record_id("entry", source_identifier)
    records: list[dict[str, Any]] = []
    entry = _base_record("entry", entry_id, entry_spans, snapshot_id, extraction_run_id)
    entry.update(
        {
            "layer": "badw_editorial",
            "headword": {"loc": lemma, "tibetan": tibetan},
            "homonym": str(article.get("homonym") or ""),
            "stable_url": str(article.get("source_object", {}).get("final_url") or source_identifier.removeprefix("badw:")),
            "witness_ids": [source_identifier],
        }
    )
    records.append(entry)

    meanings = article.get("meanings")
    if not isinstance(meanings, list):
        raise ExtractionError("article meanings is not an array")
    sense_ids: dict[int, str] = {}
    for index, meaning in enumerate(meanings, 1):
        if not isinstance(meaning, dict):
            raise ExtractionError(f"meaning {index} is not an object")
        sense_id = _record_id("sense", source_identifier, index)
        sense = _base_record("sense", sense_id, [_source_span(article, meaning)], snapshot_id, extraction_run_id)
        sense.update(
            {
                "entry_id": entry_id,
                "ordinal": index,
                "source_label": str(meaning.get("number") or ""),
                "definition": _field_text(meaning, f"meaning {index}"),
            }
        )
        records.append(sense)
        sense_ids[index - 1] = sense_id

    examples = article.get("examples")
    divisions = article.get("divisions")
    if not isinstance(examples, list) or not isinstance(divisions, list):
        raise ExtractionError("article examples or divisions is not an array")
    example_senses: dict[int, str] = {}
    for division in divisions:
        if not isinstance(division, dict):
            continue
        meaning_index = division.get("meaning_index")
        if meaning_index not in sense_ids:
            continue
        for example_index in division.get("example_indices", []):
            if isinstance(example_index, int) and example_index not in example_senses:
                example_senses[example_index] = sense_ids[meaning_index]

    citations_by_example: dict[int, list[str]] = defaultdict(list)
    citation_fields_seen: set[tuple[int, int]] = set()
    citation_ordinal = 0
    for example_index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise ExtractionError(f"example {example_index + 1} is not an object")
        citation = example.get("citation")
        if not isinstance(citation, dict):
            continue
        raw_text = _field_text(citation, f"example {example_index + 1} citation")
        if not raw_text:
            continue
        citation_ordinal += 1
        citation_id = _record_id("citation", source_identifier, citation_ordinal)
        citation_record = _base_record("citation", citation_id, [_source_span(article, citation)], snapshot_id, extraction_run_id)
        citation_record.update(
            {
                "entry_id": entry_id,
                "raw_text": raw_text,
                "authority_status": "unresolved",
            }
        )
        sigla = example.get("citation_sigla")
        if isinstance(sigla, list) and sigla and isinstance(sigla[0], dict):
            siglum = _field_text(sigla[0], "citation siglum")
            if siglum:
                citation_record["siglum"] = siglum
        location = example.get("location")
        if isinstance(location, dict):
            locator = _field_text(location, "citation locator")
            if locator:
                citation_record["locator"] = locator
        records.append(citation_record)
        citations_by_example[example_index].append(citation_id)
        span = citation_record["source_spans"][0]
        citation_fields_seen.add((span["start"], span["end"]))

    # Citations outside an example remain entry-level evidence.
    for citation in article.get("citations", []):
        if not isinstance(citation, dict):
            continue
        span = _source_span(article, citation)
        key = (span["start"], span["end"])
        if key in citation_fields_seen:
            continue
        raw_text = _field_text(citation, "entry citation")
        if not raw_text:
            continue
        citation_ordinal += 1
        citation_id = _record_id("citation", source_identifier, citation_ordinal)
        citation_record = _base_record("citation", citation_id, [span], snapshot_id, extraction_run_id)
        citation_record.update({"entry_id": entry_id, "raw_text": raw_text, "authority_status": "unresolved"})
        records.append(citation_record)

    sense_ordinals: Counter[str] = Counter()
    entry_ordinal = 0
    for example_index, example in enumerate(examples):
        if not isinstance(example, dict):
            continue
        tibetan_field = example.get("tibetan")
        if not isinstance(tibetan_field, dict):
            continue
        tibetan_text = _field_text(tibetan_field, f"example {example_index + 1} Tibetan")
        if not tibetan_text:
            continue
        sense_id = example_senses.get(example_index)
        if sense_id is None:
            entry_ordinal += 1
            ordinal = entry_ordinal
            association_status = "entry_level"
        else:
            sense_ordinals[sense_id] += 1
            ordinal = sense_ordinals[sense_id]
            association_status = "explicit"
        attestation = _base_record(
            "attestation",
            _record_id("attestation", source_identifier, example_index + 1),
            [_source_span(article, tibetan_field)],
            snapshot_id,
            extraction_run_id,
        )
        attestation.update(
            {
                "entry_id": entry_id,
                "association_status": association_status,
                "ordinal": ordinal,
                "tibetan": tibetan_text,
                "citation_ids": citations_by_example[example_index],
            }
        )
        if sense_id is not None:
            attestation["sense_id"] = sense_id
        translation = example.get("translation")
        if isinstance(translation, dict):
            translation_text = _field_text(translation, f"example {example_index + 1} translation")
            if translation_text:
                attestation["german_translation"] = translation_text
        records.append(attestation)

    for index, reference in enumerate(article.get("cross_references", []), 1):
        if not isinstance(reference, dict):
            continue
        marker = reference.get("marker")
        if marker not in {"↑", "↓"}:
            continue
        cross_reference = _base_record(
            "cross_reference",
            _record_id("cross_reference", source_identifier, index),
            [_source_span(article, reference)],
            snapshot_id,
            extraction_run_id,
        )
        cross_reference.update(
            {
                "entry_id": entry_id,
                "marker": marker,
                "resolution_status": "resolved",
                "target_url": str(reference["target_url"]),
            }
        )
        if isinstance(reference.get("target_text"), str):
            cross_reference["target_label"] = reference["target_text"]
        records.append(cross_reference)
    return records


def _read_articles(path: Path) -> Iterable[dict[str, Any]]:
    # U+2028 is legitimate preserved source Unicode; ``str.splitlines()``
    # would incorrectly treat it as a JSONL record boundary.
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError as error:
                raise ExtractionError(f"input line {line_number}: invalid JSON: {error.msg}") from error
            if not isinstance(article, dict):
                raise ExtractionError(f"input line {line_number}: article is not an object")
            yield article


def extract_jsonl(
    input_path: Path,
    output_path: Path,
    diagnostics_path: Path,
    manifest_path: Path,
    *,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Emit deterministic JSONL plus a deterministic manifest and diagnostics."""

    with input_path.open("rb") as handle:
        input_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    snapshot = snapshot_id or f"badw-html:{input_sha256}"
    run = f"{EXTRACTOR_VERSION}:{input_sha256}"
    articles = sorted(_read_articles(input_path), key=lambda article: str(article.get("source_identifier") or ""))
    records: list[dict[str, Any]] = []
    diagnostics: list[dict[str, str]] = []
    source_objects: list[dict[str, str]] = []
    for article in articles:
        identifier = str(article.get("source_identifier") or "")
        try:
            records.extend(extract_article(article, snapshot_id=snapshot, extraction_run_id=run))
            source = article.get("source_object", {})
            source_objects.append({"source_identifier": identifier, "sha256": str(source.get("sha256") or "")})
        except ExtractionError as error:
            diagnostics.append({"source_identifier": identifier, "reason": str(error)})
    errors = validate(records)
    if errors:
        raise ExtractionError("emitted contract failure: " + "; ".join(errors[:3]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    diagnostics_path.write_text(
        "".join(json.dumps(diagnostic, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for diagnostic in diagnostics),
        encoding="utf-8",
    )
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "diagnostic_count": len(diagnostics),
        "extraction_run_id": run,
        "extractor_version": EXTRACTOR_VERSION,
        "input_sha256": input_sha256,
        "record_count": len(records),
        "snapshot_id": snapshot,
        "source_object_count": len(source_objects),
        "source_objects": sorted(source_objects, key=lambda item: item["source_identifier"]),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"articles": len(articles), "diagnostics": len(diagnostics), "records": len(records), "snapshot_id": snapshot}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--articles", type=Path, required=True, help="Cached BAdW parser JSONL input")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot-id", help="Optional stable identifier for the cached source snapshot")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        summary = extract_jsonl(args.articles, args.output, args.diagnostics, args.manifest, snapshot_id=args.snapshot_id)
    except ExtractionError as error:
        print(str(error))
        return 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
