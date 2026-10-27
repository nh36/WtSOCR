"""Source observations and ownership probes are not publication authority."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from badw_html_print_alignment import object_digest
from evaluate_badw_article_ownership import compare, verify_region


def heading(n, probe):
    return dict(qa_line=n, printed_heading=str(n),
                definition_probes=[dict(qa_line=probe)])


def test_foreign_definition_is_not_ownership_success():
    heads = [heading(1, 2), heading(3, 4)]
    counts, cases = compare(heads, {1, 3, 9}, {
        1: dict(refs=[[7, 1], [7, 2], [7, 3], [7, 4]], status='coordinate_bounded'),
        3: dict(refs=[[7, 3], [7, 4]], status='coordinate_bounded')}, 7)
    assert counts['true_positive'] == 2
    assert counts['false_positive'] == 1
    assert counts['extents_with_foreign_observed_text'] == 1
    assert cases[0]['foreign_observed_refs'] == [(7, 3), (7, 4)]
    assert cases[1]['ownership'] == 'no_observed_contamination'


def test_missing_qa_heading_counts_against_recall():
    counts, cases = compare([heading(None, 4)], set(), {}, 7)
    assert counts['false_negative'] == counts['missing_qa_heading'] == 1
    assert cases[0]['ownership'] == 'no_testable_extent'


def test_merged_qa_row_does_not_prove_subline_ownership():
    counts, cases = compare([heading(1, 2), heading(3, 2)], {1, 3}, {
        1: dict(refs=[[7, 1], [7, 2]], status='coordinate_extent_alternative')}, 7)
    assert counts['definition_probes_testable'] == 0
    assert cases[0]['shared_rows_not_assessable'] == [(7, 2)]
    assert counts['extents_with_foreign_observed_text'] == 0


@pytest.fixture
def source_region(tmp_path):
    (tmp_path/'data').mkdir()
    (tmp_path/'data/source_pdfs.tsv').write_text('label\tsha256\nWtS_8-b\t'+'a'*64+'\n')
    qa = tmp_path/'release/current/qa/wts_8_b'
    qa.mkdir(parents=True)
    row = dict(page='7', line='1', line_text='original source text')
    with (qa/'wts_8_b_line_zones.tsv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row), delimiter='\t')
        writer.writeheader()
        writer.writerow(row)
    (tmp_path/'page.png').write_bytes(b'fixed observed image')
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE lines(family,page,line,body); CREATE TABLE pages(family,page,features);')
    db.execute('INSERT INTO lines VALUES (?,?,?,?)', ('wts_8_b', 7, 1, json.dumps(row)))
    db.execute('INSERT INTO pages VALUES (?,?,?)', ('wts_8_b', 7, json.dumps(dict(source_sha256='a'*64))))
    region = dict(family='wts_8_b', physical_page=7, split='held_out', source_sha256='a'*64,
                  image_name='page.png', image_sha256=hashlib.sha256(b'fixed observed image').hexdigest(),
                  page_qa_sha256=object_digest([row]), headings=[dict(
                      qa_line=1, qa_row_sha256=object_digest(row), qa_text=row['line_text'], definition_probes=[])])
    yield tmp_path, region, db
    db.close()


def test_exact_source_bindings_are_repeatable(source_region):
    root, region, db = source_region
    assert verify_region(root, region, root, db) == verify_region(root, region, root, db)


@pytest.mark.parametrize('field,value,message', [
    ('split', 'training', 'invalid fixed split'),
    ('source_sha256', 'b'*64, 'changed registered source'),
    ('image_name', '../private.png', 'unsafe image name'),
    ('image_sha256', 'b'*64, 'changed observed image'),
    ('page_qa_sha256', 'b'*64, 'changed page QA')])
def test_stale_or_unsafe_observation_rejected(source_region, field, value, message):
    root, region, db = source_region
    region[field] = value
    with pytest.raises(ValueError, match=message):
        verify_region(root, region, root, db)


def test_index_cannot_substitute_different_qa(source_region):
    root, region, db = source_region
    db.execute('UPDATE lines SET body=?', (json.dumps(dict(page='7', line='1', line_text='changed')),))
    with pytest.raises(ValueError, match='indexed QA differs'):
        verify_region(root, region, root, db)


def test_index_cannot_substitute_different_scan(source_region):
    root, region, db = source_region
    db.execute('UPDATE pages SET features=?', (json.dumps(dict(source_sha256='b'*64)),))
    with pytest.raises(ValueError, match='indexed scan differs'):
        verify_region(root, region, root, db)


def test_changed_observed_row_rejected(source_region):
    root, region, db = source_region
    region['headings'][0]['qa_text'] = 'mechanically restated observation'
    with pytest.raises(ValueError, match='changed observed QA row'):
        verify_region(root, region, root, db)
