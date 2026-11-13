"""Controls for measurement, independent of the private evaluation labels."""
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evaluate_badw_page_retrieval as e


def proposal(page=1, box=None):
    return dict(family='scan', physical_page=page, coordinate=box,
                anchor='heading', score=7, heading_text='head')


def test_shortlist_counts_pages_not_repeated_heading_anchors():
    left = proposal(box={'box': [10, 10, 20, 20]})
    right = proposal(box={'box': [70, 10, 80, 20]})
    destination = dict(geometry_status='unreviewed_gutter', candidates=[
        dict(side='left', crop=[0, 0, 50, 100]),
        dict(side='right', crop=[50, 0, 100, 100])])
    result = e.shortlist([left, left, right, proposal()], {('scan', 1): destination}, {})
    assert [r['side'] for r in result] == ['left', 'right', None]
    # Original-PDF crop coordinates cannot resolve an OCR coordinate frame.
    mapped = {'left': dict(family='scan', physical_page=1, side='left', crop=[0, 0, 100, 100])}
    assert e.candidate_side(left, {}, mapped)[0] is None


def test_unknown_side_is_not_an_individual_page_hit():
    label = dict(family='scan', physical_page=1, side='left')
    rows = e.assess(label, [dict(family='scan', physical_page=1, side=None)])
    assert rows['rank'] is None and rows['physical_rank'] == 1
    assert rows['correct_scan_unknown_side_top3']
    wrong = e.assess(label, [dict(family='scan', physical_page=1, side='right')])
    assert wrong['wrong_side_first'] and not wrong['wrong_first']
    assert e.assess(label, [])['missing']


def test_saved_request_retrieval_and_historical_certificates(tmp_path):
    """The matcher can receive identities absent from the initial page pack."""
    write = lambda p, value: p.write_text(json.dumps(value))
    db = sqlite3.connect(tmp_path / 'index.sqlite')
    db.executescript('CREATE TABLE reading_pages(family,page,body); '
                     'CREATE TABLE witnesses(sid,body); '
                     'CREATE TABLE proposals(sid,aid,score,body);')
    sid = 'badw:https://example.test/a'
    db.execute('insert into witnesses values(?,?)', (sid, json.dumps(dict(html_sha256='hash'))))
    db.execute('insert into reading_pages values(?,?,?)',
               ('scan', 1, json.dumps(dict(destination=dict(geometry_status='single_page_mediabox')))))
    db.execute('insert into proposals values(?,?,?,?)', (sid, 'a', 7, json.dumps(proposal())))
    db.commit()
    db.close()
    label = dict(family='scan', physical_page=1, side='single', source_id=sid,
                 html_sha256='hash', kind='ordinary')
    write(tmp_path / 'labels.json', dict(observations=[label]))
    write(tmp_path / 'manifest.json', {})
    write(tmp_path / 'map.json', dict(pages={}))
    write(tmp_path / 'compiled.json', dict(witnesses=[]))
    write(tmp_path / 'baseline.json', dict(witnesses=[dict(source_url='https://example.test/a')]))
    page = tmp_path / 'pages' / 'one'
    page.mkdir(parents=True)
    write(page / 'pack.json', dict(family='scan', physical_page=1, candidates=[]))
    write(page / 'match.json', dict(request=dict(evidence=dict(candidates=[dict(source_id=sid)])),
                                    result=dict(matches=[])))
    args = SimpleNamespace(run=tmp_path, labels=tmp_path / 'labels.json',
                           campaign=tmp_path, page_map=tmp_path / 'map.json',
                           compiled=tmp_path / 'compiled.json', baseline=tmp_path / 'baseline.json')
    result = e.evaluate(args)
    assert result['metrics']['core']['first'] == 1
    assert result['comparable_cached']['campaign'] == dict(n=1, retrieved=1, certified=1)
    label['html_sha256'] = 'changed'
    write(args.labels, dict(observations=[label]))
    with pytest.raises(ValueError, match='HTML identity changed'):
        e.evaluate(args)
