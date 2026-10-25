"""Independent discovery, non-promotion and atomic recovery regression fixtures."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import badw_html_print_engine as engine


def witness(loc, tib='', definition=''):
    return dict(headword=dict(loc=loc, tibetan=tib), definition=definition,
                citations=[], homonym='1', order=1)


def test_stream_json_map(tmp_path):
    records={'a': {'text': 'ö' * 1100000}, 'b': {'text': 'second'}}
    path=tmp_path/'bodies.json'
    path.write_text(json.dumps(records))
    assert dict(engine.json_map(path)) == records
    path.write_text('{} trailing')
    with pytest.raises(ValueError):
        list(engine.json_map(path))


def test_missing_c6_starts_are_independent_of_zone():
    words={'da':witness('da yaṅ','ད་ཡང་'), 'md':witness('mdun','མདུན་'),
           'salt':witness('ba tshwa','བ་ཚྭ་'), 'salty':witness('ba tshwa can','བ་ཚྭ་ཅན་')}
    indexes=engine.lexical_indexes(words)
    assert 'da' in engine.discover_line({'line_text':'ད་ཡང་ dayan nun; auch jetzt, auch jetzt noch;'}, indexes)
    assert 'md' in engine.discover_line({'line_text':'zz mdun auch sdun.'}, indexes)
    assert 'salt' in engine.discover_line({'line_text':'བ་ཚྭ་ ba tshwa auch ba tsha "Kuhsalz"'}, indexes)
    assert 'salty' in engine.discover_line({'line_text':'བ་ཚྭ་ཅན་ ba tshwa can.'}, indexes)


def test_held_out_lexical_candidates_and_diacritics():
    indexes=engine.lexical_indexes({'a':witness('rdo rje','རྡོ་རྗེ་'), 'b':witness('ṅa')})
    assert 'a' in engine.discover_line({'line_text':'རྡོ་རྗེ་ rdo rje Diamant, Donnerkeil'},indexes)
    assert 'b' not in engine.discover_line({'line_text':'na bedeutet etwas anderes'},indexes)
    assert not engine.discover_line({'line_text':'Continuation without a lexical heading.'},indexes)


def test_sequence_dynamic_program():
    options=[(1,10,3,'a'),(2,5,1,'wrong'),(3,20,4,'b'),(3,21,2,'duplicate')]
    assert engine.monotone_chain(options)=={'a','b'}


def test_checkpoint_data_and_marker_are_atomic(tmp_path):
    path=tmp_path/'index.sqlite'
    db=engine.connection(path)
    db.execute('INSERT INTO witnesses VALUES (?,?)', ('lost','{}'))
    db.rollback()
    assert engine.completed(db,'test') is None
    assert db.execute('SELECT count(*) FROM witnesses').fetchone()[0]==0
    db.execute('INSERT INTO witnesses VALUES (?,?)', ('kept','{}'))
    engine.checkpoint(db,'test',{'count':1})
    db.close()
    db=engine.connection(path)
    assert engine.completed(db,'test')=={'count':1}
    assert db.execute('SELECT sid FROM witnesses').fetchone()[0]=='kept'


def test_machine_category_is_explicitly_provisional():
    p=dict(score=12, heading_evidence=['loc_exact','leading_tibetan_exact'],
           definition_evidence={'rare_definition_tokens':['distinctive','definition']},
           sequence_consistent=True, risks=['printed_homonym_unread'])
    assert engine.baseline_category([p])[0]=='mechanically_supported_provisional'
    assert engine.category([p])[0]=='review_required'
    p['risks'].append('header_or_continuation_with_better_article_on_page')
    assert engine.category([p])[0]=='review_required'
    assert engine.category([])[0]=='unresolved'


def test_generic_definition_cannot_establish_identity():
    p=dict(score=10,heading_evidence=['loc_exact','leading_tibetan_exact'],
           definition_evidence={'rare_definition_tokens':[]},sequence_consistent=True,risks=[])
    assert engine.category([p])[0]=='review_required'


def page_proposals(tmp_path, words, lines, family='test', page=1):
    """Independent fixture: QA labels deliberately include a false header."""
    from collections import Counter
    db = engine.connection(tmp_path / 'page.sqlite')
    indexes = engine.lexical_indexes(words)
    for number, text, zone in lines:
        body = dict(line_text=text, zone=zone, coordinate=None)
        db.execute('INSERT INTO lines VALUES (?,?,?,?)',
                   (family, page, number, json.dumps(body)))
        matches = engine.discover_line(body, indexes)
        if matches:
            start = dict(anchor=f'{family}:{page}:{number}', text=text,
                         coordinate=None, historical_c6=False, matches=matches)
            db.execute('INSERT INTO starts VALUES (?,?,?,?,?)',
                       (start['anchor'], family, page, number, json.dumps(start)))
    for word in words.values():
        word.update(html_sha256='fixture', definition_components=[])
    frequencies = Counter(t for w in words.values() for t in engine.tokens(w['definition']))
    engine.match_page(db, family, page, words, frequencies)
    return {aid: json.loads(body) for aid, body in db.execute('SELECT aid,body FROM proposals')}


@pytest.mark.parametrize('loc,tib,header,start,definition', [
    ('da yaṅ', 'ད་ཡང་', 55, 89, 'nun; auch jetzt, auch jetzt noch;'),
    ('mdun', 'མདུན་', 47, 59, 'das Vordere, Vorderseite, Frontseite;'),
    # Held-out synthetic repetition exercises the same rule without special names.
    ('rdo rje', 'རྡོ་རྗེ་', 2, 8, 'Diamant unzerstörbarer Donnerkeil'),
])
def test_running_header_cannot_borrow_article_definition(tmp_path, loc, tib, header, start, definition):
    words = {'a': witness(loc, tib, definition)}
    results = page_proposals(tmp_path, words, [
        (header, f'{tib} {loc}', 'headword_line'),
        (start, f'{tib} {loc} {definition}', 'german_prose_with_translit'),
    ])
    earlier, article = results[f'test:1:{header}'], results[f'test:1:{start}']
    assert earlier['definition_evidence']['rare_definition_tokens'] == []
    assert 'header_or_continuation_with_better_article_on_page' in earlier['risks']
    assert engine.category([earlier])[0] == 'review_required'
    assert article['score'] > earlier['score']
    assert article['definition_evidence']['rare_definition_tokens']


def test_neighbouring_compound_is_not_the_salt_article():
    words = {'salt': witness('ba tshwa', 'བ་ཚྭ་'),
             'salty': witness('ba tshwa can', 'བ་ཚྭ་ཅན་')}
    indexes = engine.lexical_indexes(words)
    heading = engine.discover_line({'line_text': 'བཚྭ་ཅན་ ba tshwa can.'}, indexes)
    assert 'prefix_of_longer_observed_heading' in heading['salt']
    assert 'prefix_of_longer_observed_heading' not in heading['salty']
    own = engine.discover_line({'line_text': 'བ་ཚ་ batshwa auch ba tsha "Kuhsalz", ein Salz;'}, indexes)
    assert 'salt' in own
    assert 'salty' not in own


def corpus_fixture(tmp_path):
    row = dict(id='entry', source_kind='html', headword={'loc':'ka'}, homonym=None)
    body = dict(row, inspection_id='badw:https://wts-digital.badw.de/lemma/ka',
                source_url='https://wts-digital.badw.de/lemma/ka', components=[],
                sources=[dict(url='https://wts-digital.badw.de/lemma/ka',sha256='a'*64)])
    catalogue, bodies = tmp_path/'catalogue.json', tmp_path/'bodies.json'
    catalogue.write_text(json.dumps(dict(entries=[row])))
    bodies.write_text(json.dumps({body['inspection_id']:body}))
    return catalogue, bodies, row, body


def test_complete_identity_preflight(tmp_path):
    catalogue, bodies, row, body = corpus_fixture(tmp_path)
    db = engine.connection(':memory:')
    assert engine.index_witnesses(db,bodies,catalogue,expected=(1,1))['html_witnesses']==1
    with pytest.raises(ValueError, match='incomplete catalogue'):
        engine.index_witnesses(engine.connection(':memory:'),bodies,catalogue)
    bodies.write_text('{}')
    with pytest.raises(ValueError, match='incomplete HTML'):
        engine.index_witnesses(engine.connection(':memory:'),bodies,catalogue,expected=(1,1))


@pytest.mark.parametrize('change', ['headword','id','checksum','duplicate'])
def test_inconsistent_corpus_is_rejected(tmp_path, change):
    catalogue, bodies, row, body = corpus_fixture(tmp_path)
    if change == 'headword':
        body['headword'] = {'loc':'other'}
    elif change == 'id':
        body['id'] = 'absent'
    elif change == 'checksum':
        body['sources'][0]['sha256'] = 'invalid'
    else:
        catalogue.write_text(json.dumps(dict(entries=[row,row])))
    bodies.write_text(json.dumps({body['inspection_id']:body}))
    with pytest.raises(ValueError):
        engine.index_witnesses(engine.connection(':memory:'),bodies,catalogue,expected=(1,1))


def test_history_is_explicitly_optional():
    result = engine.index_history(engine.connection(':memory:'),Path('/absent'),{})
    assert result['edges']==result['anchors']==0
    assert 'not supplied' in result['status']
