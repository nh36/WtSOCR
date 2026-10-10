import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from badw_reader_bibliography import (exact_glyph_key, pdf_occurrence_bridge,
                                    validate_bibliography_export,
                                    html_occurrence_resolutions)
from build_badw_dictionary_prototype import bibliography_links


def test_html_lex_and_example_share_exact_source_contract(tmp_path):
    from badw_article_parser import parse_database_article
    body = (Path(__file__).parent / 'fixtures' / 'badw' / 'article.html').read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    metadata = dict(sha256=sha, delivery_type='database_article', valid_resource=True,
                    requested_url='https://wts-digital.badw.de/lemma/ka/2',
                    final_url='https://wts-digital.badw.de/lemma/ka/2',
                    headers={'Content-Type': 'text/html; charset=UTF-8'})
    article = parse_database_article(body, source_metadata=metadata)
    text = article['article_source_text']
    object_path = tmp_path / 'objects' / 'sha256' / sha[:2] / sha
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(body)
    nodes = []
    for label in ('TS', 'LX'):
        start = text.index(label)
        nodes.append(dict(id=label, kind='citation', start=start, end=start+len(label)))
    projection = dict(identity='article', source_kind='html', nodes=nodes,
                      source=dict(source_object=metadata, article_source_text=text))
    class Resolver:
        def resolve_dom(self, literal, evidence):
            assert evidence[0]['label'] == literal
            return dict(text=literal, matches=[dict(target_status='accepted_identity', authority_ids=['book'])])
        def resolve(self, literal):
            return dict(text=literal, matches=[])
    resolutions, diagnostics = html_occurrence_resolutions([projection], tmp_path, Resolver())
    assert set(resolutions) == {('article', 'TS'), ('article', 'LX')}
    assert all(d['source_sha256'] == sha for d in diagnostics)
    assert all(d['literal'] == text[d['start']:d['end']] for d in diagnostics)
    projection['nodes'].append(dict(nodes[0], id='duplicate'))
    with pytest.raises(ValueError, match='duplicate HTML'):
        html_occurrence_resolutions([projection], tmp_path, Resolver())
    projection['nodes'].pop()
    projection['source']['article_source_text'] += ' changed'
    with pytest.raises(ValueError, match='source view mismatch'):
        html_occurrence_resolutions([projection], tmp_path, Resolver())
    projection['source']['article_source_text'] = text
    object_path.write_bytes(body + b' ')
    with pytest.raises(ValueError, match='object hash mismatch'):
        html_occurrence_resolutions([projection], tmp_path, Resolver())


def test_exact_glyph_replay_survives_small_cap_line_split():
    def span(start, end, first, last):
        return dict(start=start, end=end, font_id='f', first_run_index=first,
                    last_run_index=last, first_glyph_index=0, last_glyph_index=0)
    runs = [dict(run_index=i, font_id='f', font_size=10,
                 glyphs=[dict(unicode=c, x=i*10, y=20, cid_hex=str(i), unknown=False)])
            for i, c in enumerate('(ABC)')]
    pages = {'p': dict(positioned_page=dict(positioned_text_runs=runs))}
    merged = [dict(text='(ABC)', style_spans=[span(0,5,0,4)])]
    split = [dict(text='(A', style_spans=[span(0,2,0,1)]),
             dict(text='BC)', style_spans=[span(0,3,2,4)])]
    loc = lambda i, end: dict(page_id='p', line_index=i, line_char_start=0, line_char_end=end)
    key = exact_glyph_key([loc(0,5)], merged, pages)
    assert len(key) == 5
    assert key == exact_glyph_key([loc(0,2),loc(1,3)], split, pages)
    split[1]['text'] = 'BD)'
    assert exact_glyph_key([loc(0,2),loc(1,3)], split, pages) == ()
    merged[0]['style_spans'][0]['font_id'] = 'other'
    assert exact_glyph_key([loc(0,5)], merged, pages) == ()


def fixture(tmp_path):
    span = dict(start=0, end=5, font_id='font', first_run_index=10,
                last_run_index=12, first_glyph_index=0, last_glyph_index=1)
    line = dict(text='(Abc)', style_spans=[span])
    loc = dict(line_index=0, page_id='page', run_start=10,
               run_end_exclusive=13, line_char_start=0, line_char_end=5)
    obj = dict(page_id='page', pdf_sha256='pdf', source_text_sha256='text',
               run_start=0, run_end_exclusive=20)
    source = dict(source_faithful_text='raw', source_objects=[obj], visual_lines=[line])
    p = dict(identity='article', source_kind='pdf', source=source,
             nodes=[dict(id='n1', kind='citation', start=0, end=5, source_lines=[loc])])
    path = tmp_path / 'staging.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE pdf_article_analysis(article_id,source_faithful_sha256,structural_json)')
        db.execute('CREATE TABLE pdf_lexical_candidate(article_id,kind,ordinal,candidate_json)')
        db.execute('INSERT INTO pdf_article_analysis VALUES (?,?,?)',
                   ('article', hashlib.sha256(b'raw').hexdigest(), json.dumps(source)))
        db.execute('INSERT INTO pdf_lexical_candidate VALUES (?,?,?,?)',
                   ('article','citation',0,json.dumps(dict(text='(Abc)',source_lines=[loc]))))
    return p, path


def test_exact_bridge_and_position_repair(tmp_path):
    p, path = fixture(tmp_path)
    assert pdf_occurrence_bridge([p],path)[0] == {('article','n1'):'article:0'}
    p['source']['visual_lines'][0]['text'] += ' continuation'
    p['nodes'][0]['source_lines'][0]['run_end_exclusive'] = 20
    assert pdf_occurrence_bridge([p],path)[0] == {('article','n1'):'article:0'}
    p['source']['visual_lines'][0]['style_spans'][0]['font_id'] = 'different'
    assert pdf_occurrence_bridge([p],path)[0] == {}


def test_wrong_source_and_multiple_occurrences_fail_closed(tmp_path):
    p, path = fixture(tmp_path)
    bad = copy.deepcopy(p)
    bad['source']['source_objects'][0]['pdf_sha256'] = 'other'
    assert pdf_occurrence_bridge([bad],path)[1][0]['status'] == 'source_mismatch'
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO pdf_lexical_candidate SELECT article_id,kind,1,candidate_json FROM pdf_lexical_candidate')
    matches, diagnostics = pdf_occurrence_bridge([p],path)
    assert matches == {} and diagnostics[0]['status'] == 'ambiguous'


def test_pdf_invalid_span_fails_closed(tmp_path):
    p, path = fixture(tmp_path)
    p['nodes'][0]['start'] = -1
    with pytest.raises(ValueError, match='invalid PDF citation source bounds'):
        pdf_occurrence_bridge([p], path)


def test_reader_cannot_drop_known_identity(tmp_path):
    p, _ = fixture(tmp_path)
    bibliography = {('article','n1'):[dict(id='book')]}
    entry = dict(inspection_id='article', citations=[dict(source_form='(Abc)', accepted_authority_ids=['book'], ownership='unresolved')])
    validate_bibliography_export([p],[entry],bibliography)
    entry['citations'][0]['accepted_authority_ids'] = []
    with pytest.raises(ValueError, match='lost accepted'):
        validate_bibliography_export([p],[entry],bibliography)


def test_export_checks_identity_not_display_order(tmp_path):
    p, _ = fixture(tmp_path)
    second = dict(identity='second', nodes=[])
    entry = dict(inspection_id='article', citations=[dict(source_form='(Abc)', accepted_authority_ids=['book'])])
    empty = dict(inspection_id='second', citations=[])
    validate_bibliography_export([p, second], [empty, entry], {('article', 'n1'): [dict(id='book')]})


def test_pdf_reader_uses_exact_occurrence_not_shared_siglum(tmp_path):
    p, _ = fixture(tmp_path)
    database = tmp_path / 'bibliography.sqlite'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE authority(id,label)')
        db.execute('CREATE TABLE occurrence(id,authority_id,record_json)')
        db.execute('INSERT INTO authority VALUES (?,?)', ('book', 'Abc'))
        db.execute('INSERT INTO occurrence VALUES (?,?,?)',
                   ('description', 'book', json.dumps(dict(text='Full bibliography'))))
    links = tmp_path / 'links.jsonl'
    resolution = dict(text='(Abc)', matches=[dict(target_status='accepted_identity',
                                                authority_ids=['book'])])
    links.write_text(json.dumps(dict(citation_id='another-article:0', resolution=resolution))+'\n')
    bridge = {('article', 'n1'): 'article:0'}
    with pytest.raises(ValueError, match='occurrence absent'):
        bibliography_links([p], links, database, bridge)
    links.write_text(json.dumps(dict(citation_id='article:0', resolution=resolution))+'\n')
    result = bibliography_links([p], links, database, bridge)
    assert result[('article', 'n1')][0]['id'] == 'book'
    assert result[('article', 'n1')][0]['descriptions'] == ['Full bibliography']
    # An exact occurrence can exist without an accepted authority. Keep it
    # unlinked rather than borrowing the identity of another siglum occurrence.
    links.write_text(json.dumps(dict(citation_id='article:0',
                                    resolution=dict(text='(Abc)', matches=[])))+'\n')
    assert bibliography_links([p], links, database, bridge) == {}
    links.write_text(json.dumps(dict(citation_id='article:0', resolution=resolution))+'\n')
    links.write_text(links.read_text() * 2)
    with pytest.raises(ValueError, match='duplicate bibliography occurrence'):
        bibliography_links([p], links, database, bridge)
    resolution['text'] = '(Different)'
    links.write_text(json.dumps(dict(citation_id='article:0', resolution=resolution))+'\n')
    with pytest.raises(ValueError, match='literal mismatch'):
        bibliography_links([p], links, database, bridge)


def test_corrupt_canonical_object_fails_before_glyph_join(tmp_path):
    p, path = fixture(tmp_path)
    obj = p['source']['source_objects'][0]
    obj.update(canonical_object='page.json.gz', canonical_object_sha256='not-the-hash')
    with sqlite3.connect(path) as db:
        db.execute('UPDATE pdf_article_analysis SET structural_json=?',
                   (json.dumps(p['source']),))
    (tmp_path / 'page.json.gz').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash mismatch'):
        pdf_occurrence_bridge([p], path, tmp_path)
