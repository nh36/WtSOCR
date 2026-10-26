"""Independent discovery, non-promotion and atomic recovery regression fixtures."""
import json
from collections import Counter
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import badw_html_print_engine as engine


def test_render_bound_hocr_index_keeps_dependent_readings_separate(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    family = 'wts_1_34'
    pdf = tmp_path/'source.pdf'
    writer = PdfWriter(); writer.add_blank_page(width=400, height=600)
    writer.write(pdf)
    qa = tmp_path/f'release/current/qa/{family}/{family}_line_zones.tsv'
    qa.parent.mkdir(parents=True)
    qa.write_text('page\tline\tline_text\n1\t1\tdistinctive printed definition\n')
    bundle = tmp_path/'coordinates'; bundle.mkdir()
    record = dict(physical_page=1, source_sha256='registered', hocr_sha256='hocr',
                  raster_sha256='raster', lines=[dict(text='distinctive printed definition',
                                                    box=[20,100,200,110])])
    (bundle/(family+'.jsonl')).write_text(json.dumps(record)+'\n')
    # Damaged embedded OCR cannot become independent agreement just because
    # a different, render-bound OCR cache supplies the selected coordinates.
    monkeypatch.setattr(engine, 'pdf_layout', lambda *args: iter([
        [dict(text='unrelated damaged OCR', box=[20,100,200,110])]]))
    db = engine.connection(tmp_path/'index.sqlite')
    registry = {engine.FAMILIES[family]: dict(filename=pdf.name, sha256='registered')}
    result = engine.index_family(db,tmp_path,family,registry,tmp_path,bundle)
    row = json.loads(db.execute('SELECT body FROM lines').fetchone()[0])
    assert result['coordinates']['unique'] == 1
    assert row['coordinate']['hocr_text'] == 'distinctive printed definition'
    assert 'embedded_text' not in row['coordinate']
    assert row['coordinate_reconciliation']['hocr_sha256'] == 'hocr'
    assert row['embedded_reconciliation']['coordinate'] is None
    assert row['line_text'] == 'distinctive printed definition'
    db.close()


def witness(loc, tib='', definition=''):
    return dict(headword=dict(loc=loc, tibetan=tib), definition=definition,
                citations=[], homonym='1', order=1)


@pytest.mark.parametrize('empty_clip', [False, True])
def test_physical_repeated_heading_preserves_earlier_column_definition(tmp_path, empty_clip):
    db=engine.connection(tmp_path/'physical.sqlite')
    word=witness('ka',definition='distinctive earlier column definition')
    word.update(html_sha256='fixture',definition_components=[])
    rows={100:'ཀ ka',120:word['definition'],110:'ཀ ka competing article'}
    for n,text in rows.items():
        db.execute('INSERT INTO lines VALUES (?,?,?,?)',
                   ('fixture',1,n,json.dumps(dict(line_text=text))))
    # QA numbering interleaves columns. The definition at QA 120 precedes
    # the competing heading at QA 110 in physical reading order.
    for pos,n in enumerate((100,120,110)):
        db.execute('INSERT INTO reading_lines VALUES (?,?,?,?,?)',
                   ('fixture',1,n,pos,'{}'))
    for n in (100,110):
        start=dict(anchor=f'fixture:1:{n}',text=rows[n],coordinate=None,
                   historical_c6=False,matches={'w':{'loc_exact':True}})
        db.execute('INSERT INTO starts VALUES (?,?,?,?,?)',
                   (start['anchor'],'fixture',1,n,json.dumps(start)))
    extent=dict(status='coordinate_extent_alternative' if empty_clip else 'coordinate_bounded',
                refs=[] if empty_clip else [[1,100],[1,120]],
                unlocated_boundary_alternatives=[dict(page=1,line=101)] if empty_clip else [])
    db.execute('INSERT INTO extents VALUES (?,?)',('fixture:1:100',json.dumps(extent)))
    engine.match_page(db,'fixture',1,{'w':word},Counter(engine.tokens(word['definition'])))
    p=json.loads(db.execute('SELECT body FROM proposals WHERE aid=?',('fixture:1:100',)).fetchone()[0])
    assert p['evidence_lines']==([] if empty_clip else [[1,100],[1,120]])
    assert (word['definition'] in p['printed_evidence']) is not empty_clip
    assert 'unverified_definition_ownership' in p['risks']
    db.close()


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
    assert engine.category([p])[0]=='mechanically_supported_provisional'
    assert not engine.publication_eligibility(p)['eligible']
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


def test_homonym_contradiction_excludes_even_strong_identity():
    p=dict(score=12,heading_evidence=['loc_exact','leading_tibetan_exact'],
           definition_evidence={'rare_definition_tokens':['distinctive','definition']},
           sequence_consistent=True,risks=['verified_printed_homonym_conflict'])
    assert engine.category([p])[0]=='contradictory_identity'
    p['definition_evidence']['rare_definition_tokens']=[]
    assert engine.category([p])[0]=='contradictory_identity'
    assert not engine.publication_eligibility(dict(eligible=True,reviewed=True))['eligible']


def test_tentative_numerals_do_not_exclude_lexical_identity():
    p=dict(score=12,heading_evidence=['loc_exact','leading_tibetan_exact'],
           definition_evidence={'rare_definition_tokens':['distinctive','definition']},
           sequence_consistent=True,risks=[])
    cases=[('conflicting_ocr_number',None,'homonym_ocr_sources_disagree'),
           ('explicit_number_single_ocr','2','homonym_single_ocr_conflicts_html'),
           ('explicit_number_ocr_agreement','2','homonym_agreeing_ocr_conflicts_html')]
    for status,number,risk in cases:
        p['risks']=engine.homonym_risks(dict(status=status,number=number),'1')
        assert p['risks']==[risk]
        assert engine.category([p])[0]=='mechanically_supported_provisional'
        assert not engine.publication_eligibility(p)['eligible']
    assert engine.homonym_risks(dict(status='unread',number=None),None)==['printed_homonym_unread']


def test_coordinate_interval_does_not_certify_lexical_ownership():
    extent = dict(risks=['unverified_article_extent', 'uncertain_column_membership'])
    result = engine.coordinate_interval_evidence(extent, dict(status='coordinate_bounded'))
    assert result['evidence_states']['coordinates_recovered'] is True
    assert result['evidence_states']['lexical_boundaries'] == 'unverified'
    assert result['evidence_states']['definition_ownership'] == 'unverified'
    assert {'unverified_article_extent', 'uncertain_column_membership',
            'unverified_definition_ownership'} <= set(result['risks'])
    assert not engine.publication_eligibility(result)['eligible']
