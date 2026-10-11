"""Completion gates reject gaps, stale evidence and speculative relationship loss."""
import copy
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from badw_bibliography_completion import validate_accounting
from query_badw_bibliography import Bibliography


def test_completed_summary_is_bound_to_reviewed_inputs():
    summary = json.loads(Path('data/bibliography_apparatus_reconciliation.json').read_text())
    for name, digest in summary['input_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    assert len(summary['unresolved']) == 8
    assert summary['editorial_omissions'][0]['definition_search']['hits'] == []


def test_checked_accounting_covers_every_zone_page_and_record():
    zones = list(csv.DictReader(Path('data/bibliography_apparatus_zones.tsv').open(), delimiter='\t'))
    records = [json.loads(l) for l in Path('data/bibliography_apparatus_records.jsonl').read_text().splitlines()]
    pages = [json.loads(l) for l in Path('data/bibliography_apparatus_accounting.jsonl').read_text().splitlines()]
    assert validate_accounting(zones, pages, records) == 114
    covered = {i for page in pages for part in page['parts'] for i in part['record_ids']}
    assert covered == {r['id'] for r in records}
    bad = copy.deepcopy(pages)
    bad[0]['parts'][0]['record_ids'] = ['invented-record']
    with pytest.raises(ValueError, match='missing record'):
        validate_accounting(zones, bad, records)
    with pytest.raises(ValueError, match='Missing apparatus'):
        validate_accounting(zones, pages[1:], records)
    bad = copy.deepcopy(pages)
    bad[0]['parts'][0]['raw_text'] += 'changed'
    with pytest.raises(ValueError, match='text changed'):
        validate_accounting(zones, bad, records)


def test_canonical_history_retains_publication_editions_and_editorial_notes(tmp_path):
    path = tmp_path / 'bib.sqlite'
    db = sqlite3.connect(path)
    db.executescript(Path('data/bibliography_database.schema.sql').read_text())
    for identity in ['publication-first', 'publication-reprint']:
        db.execute('INSERT INTO authority VALUES(?,?,?,?,?,?)',
                   (identity, 'publication', identity, 'published_print', 'reviewed', '{}'))
        db.execute('INSERT INTO canonical_membership VALUES(?,?,?,?)',
                   (identity, 'work-of-first', 'publication_of_bibliographic_work', '{}'))
        db.execute('INSERT INTO authority_history VALUES(?,?)',
                   (identity, json.dumps({'canonical_id': identity, 'occurrences': [identity]})))
    db.execute('INSERT INTO authority_history VALUES(?,?)',
               ('work-of-first', json.dumps({'publication_ids': ['publication-first', 'publication-reprint']})))
    db.execute('INSERT INTO apparatus_annotation VALUES(?,?)',
               ('mim', json.dumps({'provenance': 'external, not WTS'})))
    db.commit()
    db.close()
    reader = Bibliography(path)
    try:
        assert reader.canonical_history('publication-first')['occurrences'] == ['publication-first']
        assert len(reader.canonical_history('work-of-first')['publication_ids']) == 2
        assert reader.scholarly_notes() == [{'provenance': 'external, not WTS'}]
        assert reader.reconciliation() is None
    finally:
        reader.close()
