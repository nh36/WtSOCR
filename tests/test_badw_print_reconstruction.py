"""Reconstruction observations must never be confused with publication authority."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pytest
from badw_print_reconstruction import (column_model,column_of,numeral_before_loc,
    homonym_evidence,page_destination,bracket_candidates)
from badw_html_print_engine import publication_eligibility


def geometry(landscape=False):
    return dict(width=1000,height=1000,landscape=landscape,rotation=0,
                mediabox=[0,0,1000,1000],source_sha256='a'*64,physical_page=12)


def columns(edges):
    return {str((x,i)):dict(coordinate=dict(box=[x,200+i*20,x+160,210+i*20]),
                           line_text='substantial body text') for x in edges for i in range(20)}


@pytest.mark.parametrize('intervening_box', [None, [450,340,900,350]])
def test_reconstruction_stops_at_heading_without_reliable_column(tmp_path, intervening_box):
    """A missing C6 start/column must not donate the next article's definition."""
    import json
    from badw_html_print_engine import connection, match_page, tokens
    from collections import Counter
    from badw_print_reconstruction import reconstruct
    db=connection(tmp_path/'ownership.sqlite')
    db.execute('INSERT INTO pages VALUES (?,?,?)',('fixture',1,json.dumps(geometry())))
    layout=[dict(box=r['coordinate']['box'],text=r['line_text'])
            for r in columns([30,550]).values()]
    db.execute('INSERT INTO layouts VALUES (?,?,?)',('fixture',1,json.dumps(layout)))
    rows={
        1:dict(line_text='ཀ ka first article',coordinate=dict(box=[30,300,190,310])),
        2:dict(line_text='first definition',coordinate=dict(box=[30,320,190,330])),
        3:dict(line_text='ཁ kha second article',coordinate=dict(box=intervening_box) if intervening_box else None),
        4:dict(line_text='definition belonging only to kha',coordinate=dict(box=[30,360,190,370])),
        5:dict(line_text='ག ga third article',coordinate=dict(box=[30,400,190,410])),
    }
    for n,row in rows.items():
        db.execute('INSERT INTO lines VALUES (?,?,?,?)',('fixture',1,n,json.dumps(row)))
    for n in (1,5):
        st=dict(rows[n],text=rows[n]['line_text'],anchor=f'fixture:1:{n}',
                matches={'w':{'loc_exact':True}},historical_c6=False)
        db.execute('INSERT INTO starts VALUES (?,?,?,?,?)',
                   (st['anchor'],'fixture',1,n,json.dumps(st)))
    reconstruct(db,{}, {'w':dict(headword=dict(loc='ka'))})
    extent=json.loads(db.execute('SELECT body FROM extents WHERE aid=?',('fixture:1:1',)).fetchone()[0])
    assert extent['refs']==[[1,1],[1,2]]
    assert extent['unlocated_boundary_alternatives']==[dict(family='fixture',page=1,line=3)]
    assert extent['evidence_states']['definition_ownership']=='unverified'
    assert extent['status']=='coordinate_extent_alternative'
    # Matching must consume the clipped alternative, rather than falling back
    # to QA order and borrowing the second article's distinctive definition.
    word=dict(headword=dict(loc='ka'), definition='definition belonging only to kha',
              citations=[], homonym=None, order=1, html_sha256='fixture',
              definition_components=[])
    match_page(db,'fixture',1,{'w':word},Counter(tokens(word['definition'])))
    proposal=json.loads(db.execute('SELECT body FROM proposals WHERE aid=?',
                                  ('fixture:1:1',)).fetchone()[0])
    assert proposal['evidence_lines']==[[1,1],[1,2]]
    assert 'belonging only to kha' not in proposal['printed_evidence']
    assert 'unverified_definition_ownership' in proposal['risks']
    db.close()


def test_wholly_unlocated_intermediate_page_interrupts_interval(tmp_path):
    """A page omitted from the located-line index still contains boundaries."""
    import json
    from badw_html_print_engine import connection
    from badw_print_reconstruction import reconstruct
    db=connection(tmp_path/'missing-page.sqlite')
    for page in (1,2,3):
        db.execute('INSERT INTO pages VALUES (?,?,?)',('fixture',page,json.dumps(geometry())))
        layout=[dict(box=r['coordinate']['box'],text=r['line_text'])
                for r in columns([30,550]).values()]
        db.execute('INSERT INTO layouts VALUES (?,?,?)',('fixture',page,json.dumps(layout)))
    for page,text in ((1,'ཀ ka first article'),(2,'ཁ kha second article'),
                      (3,'ག ga third article')):
        row=dict(line_text=text,coordinate=None if page==2 else dict(box=[30,300,190,310]))
        db.execute('INSERT INTO lines VALUES (?,?,?,?)',('fixture',page,1,json.dumps(row)))
        if page!=2:
            st=dict(row,text=text,anchor=f'fixture:{page}:1',
                    matches={'w':{'loc_exact':True}},historical_c6=False)
            db.execute('INSERT INTO starts VALUES (?,?,?,?,?)',
                       (st['anchor'],'fixture',page,1,json.dumps(st)))
    reconstruct(db,{}, {'w':dict(headword=dict(loc='ka'))})
    extent=json.loads(db.execute('SELECT body FROM extents WHERE aid=?',('fixture:1:1',)).fetchone()[0])
    assert extent['unlocated_boundary_alternatives']==[dict(family='fixture',page=2,line=1)]
    assert extent['refs']==[[1,1]]
    assert extent['status']=='coordinate_extent_alternative'
    db.close()


def test_noncentral_spread_content_gap_not_universal_half():
    rows=columns([30,230,610,810]);g=geometry(True);m=column_model(rows,g)
    assert m['status']=='coordinate_clusters'
    assert column_of([610,200,770,210],m)==2
    d=page_destination(rows,g,m,[])
    assert d['geometry_status']=='no_secure_inter_page_gap'
    # Use asymmetric content geometry with a gap <18% of the scan width.
    rows=columns([30,230,550,750]);m=column_model(rows,g)
    d=page_destination(rows,g,m,[])
    assert d['candidates'][0]['crop'][2]==470
    assert 'unverified' in d['geometry_status']
    assert d['printed_folio_status']=='unresolved'


def test_single_page_keeps_original_geometry_and_rotation_is_deferred():
    g=geometry();g['mediabox']=[12,14,1012,1014]
    assert page_destination({},g,{},[])['candidates'][0]['crop']==g['mediabox']
    g['rotation']=90
    assert not page_destination({},g,{},[])['candidates']
    assert column_model(columns([30]),geometry())['status']=='ambiguous_columns'


def test_orientation_does_not_determine_number_of_columns_or_spread_side():
    rows=columns([30,550]);g=geometry(True);m=column_model(rows,g)
    assert m['status']=='coordinate_clusters' and m['observed_columns']==2
    assert page_destination(rows,g,m,[])['geometry_status']=='spread_columns_unresolved'
    assert column_model(columns([30,230,550,750]),geometry())['observed_columns']==4


@pytest.mark.parametrize('text,status,number',[
    ('ཀ་ ² ka erstes Wort','explicit_ocr_number','2'),
    ('ཀ་ ka 2. Bedeutung','unnumbered_complete_qa_heading',None),
    ("ཀ་ 'ka Bedeutung",'unread',None),
    ('ཀ་ ?ka Bedeutung','unread',None),
    ('1:1 ka Bedeutung','unread',None),
    ('ཀ་ °ka Bedeutung','unread',None),
    ('² ཀ་ ka','explicit_ocr_number','2'),
])
def test_numeral_location_not_senses_or_damaged_tibetan(text,status,number):
    r=numeral_before_loc(text,'ka');assert (r['status'],r['number'])==(status,number)


def test_agreement_conflict_and_absence_are_distinct():
    s=dict(text='ཀ་ ² ka',coordinate=dict(embedded_text='xx ² ka'),loc_forms=['ka'])
    assert homonym_evidence(s,{})['status']=='explicit_number_ocr_agreement'
    s['coordinate']['embedded_text']='xx ³ ka'
    assert homonym_evidence(s,{})['status']=='conflicting_ocr_number'
    s.update(text='ཀ་ ka',coordinate=None)
    r=homonym_evidence(s,{})
    assert r['status']=='unnumbered_qa_heading_assessable' and r['number'] is None
    assert not publication_eligibility(r)['eligible']


def proposal(sid,page,y,score=10):
    return dict(sid=sid,anchor=f'x:{page}:{y}',family='x',physical_page=page,score=score,
        reconstruction=dict(position=[page,0,y]),risks=[],
        definition_evidence=dict(rare_definition_tokens=['distinctive','evidence']))


def test_two_other_witnesses_can_rerank_but_never_create_identity():
    a=proposal('a',2,100);b=proposal('b',4,100)
    p=proposal('p',3,100);q=proposal('p',3,150)
    ranks=dict(a=1,p=2,b=3)
    r=bracket_candidates([p],[a,b],ranks)[0]
    assert r['score']==11 and r['sequence_ranking']['anchors']==[a['anchor'],b['anchor']]
    assert not publication_eligibility(r)['eligible']
    assert bracket_candidates([p],[a],ranks)[0]['score']==10
    p['risks']=['printed_homonym_conflict']
    assert bracket_candidates([p],[a,b],ranks)[0]['score']==10
    p['risks']=[];p['definition_evidence']['rare_definition_tokens']=[]
    assert bracket_candidates([p],[a,b],ranks)[0]['score']==10
    assert bracket_candidates([q],[a,b],dict(a=3,p=2,b=1))[0]['score']==10


@pytest.mark.parametrize('enabled',[False,True])
def test_sequence_ablation_preserves_local_and_adjusted_ranks(tmp_path,enabled):
    import json
    from badw_html_print_engine import connection
    from badw_print_reconstruction import sequence_rerank
    db=connection(tmp_path/'index.sqlite')
    a=proposal('a',2,100); b=proposal('b',4,100)
    local=proposal('p',8,100,10.5); bracketed=proposal('p',3,100,10)
    for p in (a,b,local,bracketed):
        p['heading_evidence']=['leading_tibetan_exact','loc_exact']
        db.execute('INSERT INTO proposals VALUES (?,?,?,?)',
                   (p['sid'],p['anchor'],p['score'],json.dumps(p)))
    result=sequence_rerank(db,{s:dict(order=i) for i,s in enumerate(('a','p','b'))},enabled)
    rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM proposals WHERE sid=? ORDER BY score DESC,aid',('p',))]
    assert rows[0]['anchor']==(bracketed if enabled else local)['anchor']
    adjusted=next(p for p in rows if p['anchor']==bracketed['anchor'])['sequence_ranking']
    assert adjusted['local_rank']==2 and adjusted['adjusted_rank']==1
    assert adjusted['local_score']==10 and adjusted['adjusted_score']==11
    assert {r['source_id'] for r in adjusted['anchor_witnesses']}=={'a','b'}
    assert result['changed_top_predictions']==int(enabled)
    assert not publication_eligibility(rows[0])['eligible']


@pytest.mark.parametrize('family,page,line,loc',[
    ('wts_35_51',267,38,'ldoṅs'),
    ('wts_8_b',445,32,'’bum pa'),
])
def test_real_damaged_homonym_readings_do_not_become_numbers(family,page,line,loc):
    """The observed confusions must not become homonym 1 by default."""
    import csv
    path=Path(__file__).resolve().parents[1]/'release/current/qa'/family/(family+'_line_zones.tsv')
    with path.open() as f:
        row=next(r for r in csv.DictReader(f,delimiter='\t')
                 if r['page']==str(page) and r['line']==str(line))
    evidence=homonym_evidence(dict(text=row['line_text'],loc_forms=[loc],coordinate=None),{})
    assert evidence['status']=='unread'
    assert evidence['number'] is None
    assert not publication_eligibility(evidence)['eligible']
