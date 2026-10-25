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
