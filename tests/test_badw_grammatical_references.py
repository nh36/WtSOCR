"""The grammar gate validates evidence syntax; it never chooses a homonym."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import pytest
from badw_grammatical_references import (
    GRAMMATICAL, PERFECT, FUTURE, IMPERATIVE, QUALIFIED, description,
    introduction, passage_matches, positioned_passage, complete_target,
)


@pytest.mark.parametrize('pattern,source,destination', [
    ('perfect_to_paradigm','pf. zu','pf. ↑bcum'),
    ('paradigm_to_perfect','pf.','pf. zu ↑bcum'),
    ('paradigm_to_perfect','pf.','pf. bzw. imp. zu ↑bcum'),
    ('future_to_paradigm','fut. zu','fut. ↑bcum'),
    ('future_to_paradigm','fut. zu','fut.↑bcum'),
    ('paradigm_to_future','fut.','fut. zu ↑bcum'),
])
def test_declarative_complementary_grammatical_patterns(pattern,source,destination):
    claim=dict(basis=GRAMMATICAL,grammatical_pattern=pattern)
    text=source+' ↓ka'
    assert introduction(claim,text,text.index('↓'))
    assert passage_matches(dict(literal=' '+destination+' '),'bcum','↓',
        basis=GRAMMATICAL,grammatical_pattern=pattern,source_introduction=source)
    for literal in [destination.replace('↑','↓'), destination+'s', destination+' ↑kha',
                    destination+' deutscher Text', destination.replace('bcum','bcuṃ')]:
        assert not passage_matches(dict(literal=literal),'bcum','↓',basis=GRAMMATICAL,
                                  grammatical_pattern=pattern,source_introduction=source)
    assert not introduction(claim,'unrelated '+text,len('unrelated ')+text.index('↓'))
    assert not passage_matches(dict(literal=destination),'bcum','↓',basis=GRAMMATICAL,
                              grammatical_pattern=pattern,source_introduction='German prose')


@pytest.mark.parametrize('basis,source,dest', [
    (PERFECT,'pf. zu','pf. ↑bcum'), (FUTURE,'pf. und fut. zu','pf. und fut. ↑bcum'),
    (IMPERATIVE,'pf. und imp.','pf. und imp. zu↑bcum'),
    (QUALIFIED,'pf. zu','pf. ↑2bcum')])
def test_historical_descriptions_preserve_exact_contract(basis,source,dest):
    claim=dict(basis=basis)
    assert introduction(claim,source+' ↓ka',len(source)+1)
    assert passage_matches(dict(literal=dest),'bcum','↓',basis=basis,
                           source_introduction=source,source_homonym='2')
    assert not description(dict(claim,grammatical_pattern='future_to_paradigm'))


def test_alternate_form_is_literal_and_individually_bound():
    claim=dict(basis=GRAMMATICAL,grammatical_pattern='paradigm_to_perfect',source_alternate_headword='mkhu')
    assert introduction(claim,'auch mkhu pf. ↓ka',14)
    assert not introduction(claim,'auch khu pf. ↓ka',13)
    assert not introduction(dict(claim,source_alternate_headword='mkhu ↑ka'),'auch mkhu pf. ↓ka',14)
    assert not description(dict(basis=GRAMMATICAL,grammatical_pattern=PERFECT))


@pytest.mark.parametrize('prefix', ['pf. ↓brgyaṅs fut.', 'auch ’ged, gyed, pf. ↑bkye fut.'])
def test_future_inside_bounded_compound_paradigm(prefix):
    claim=dict(basis=GRAMMATICAL,grammatical_pattern='paradigm_to_future')
    text=prefix+' ↓ka'
    assert introduction(claim,text,len(prefix)+1)
    assert passage_matches(dict(literal=' fut. zu ↑bcum'),'bcum','↓',
        basis=GRAMMATICAL,grammatical_pattern='paradigm_to_future',source_introduction=prefix)
    assert not passage_matches(dict(literal=' pf. zu ↑bcum'),'bcum','↓',
        basis=GRAMMATICAL,grammatical_pattern='paradigm_to_future',source_introduction=prefix)


@pytest.mark.parametrize('prefix', [
    'German prose pf. ↓brgyaṅs fut.', 'pf. ↓brgyaṅs ↑ka fut.',
    'pf. ↓⟦UNKNOWN:ink⟧ fut.', 'pf. ↓'+'a'*41+' fut.',
    'pf. ↓brgyaṅs imp.', 'pf. ↓brgyaṅs, fut.',
    'auch ka, kha, ga, pf. ↑bkye fut.', 'auch ka German, pf. ↑bkye fut.',
    'pf. ↓brgyaṅs German fut.', 'pf. ↓brgyaṅs\nfut.',
])
def test_compound_paradigm_cannot_consume_prose_or_unbounded_members(prefix):
    claim=dict(basis=GRAMMATICAL,grammatical_pattern='paradigm_to_future')
    assert not introduction(claim,prefix+' ↓ka',len(prefix)+1)
    assert not passage_matches(dict(literal=' fut. zu ↑bcum'),'bcum','↓',
        basis=GRAMMATICAL,grammatical_pattern='paradigm_to_future',source_introduction=prefix)


def geometry():
    page=dict(representative_fonts=[dict(font_id='r',family='TGaramond',style='regular'),
                                    dict(font_id='i',family='TGaramond',style='italic')])
    runs=[dict(decoded_unicode=' pf. zu ',font_id='r',x=10,y=100),
          dict(decoded_unicode='↑',font_id='r',x=15,y=100),
          dict(decoded_unicode='bcum',font_id='i',x=17,y=100)]
    return page,runs


def test_positioned_complement_and_adjacent_single_wrap():
    page,runs=geometry()
    assert positioned_passage(page,runs,'bcum')
    runs[0]['x']=25
    for r in runs[1:]:r['y']=99
    assert positioned_passage(page,runs,'bcum')


@pytest.mark.parametrize('mutation', ['font','unknown','gap','baseline','column','arrow','prose','missing','combined'])
def test_positioned_evidence_rejects_incompatible_runs(mutation):
    page,runs=geometry()
    if mutation=='font':runs[-1]['font_id']='r'
    if mutation=='unknown':runs[-1]['unknown_glyphs']=['ink']
    if mutation=='gap':runs[-1]['x']=90
    if mutation=='baseline':runs[-1]['y']=90
    if mutation=='column':runs[-1]['x']=5
    if mutation=='arrow':runs[-1]['decoded_unicode']='bcum ↑ka'
    if mutation=='prose':runs[-1]['decoded_unicode']='bcum deutscher Text'
    if mutation=='missing':runs[-1]['x']=None
    if mutation=='combined':runs[1]['decoded_unicode']='↑b';runs[-1]['decoded_unicode']='cum'
    assert not positioned_passage(page,runs,'bcum')


@pytest.mark.parametrize('following,accepted',[('s',False),('ṅ',False),('’',False),(' ',True),(',',True),('.',True)])
def test_terminal_boundary_is_not_a_run_boundary(following,accepted):
    runs=[dict(decoded_unicode='bsgrag'),dict(decoded_unicode=following)]
    assert complete_target(runs,1,2)==accepted
    assert complete_target(runs,2,2)


def first_sense_geometry():
    from badw_grammatical_references import first_sense_prefix
    page,_=geometry()
    def run(text,xs):
        return dict(decoded_unicode=text,font_id='r',glyphs=[dict(unicode=c,x=x,y=100) for c,x in zip(text,xs)])
    runs=[run('heading',[1]*7),run('.',[11]),run('1',[10]),run('1.',[10,11]),
          run('.  pf. zu ↑',[11,11.3,11.6,12,12.5,13,13.5,14,14.5,15,15.5])]
    page['positioned_page']=dict(positioned_text_runs=runs)
    span=dict(loc_run_indices=[0],run_end_exclusive=8)
    proof=dict(run_start=4,run_end_exclusive=7,run_start_offset=3,
               literal='.  pf. zu ↑bcum',numbered_sense=dict(run_start=2,label='1.'))
    return page,span,proof


def test_overprinted_first_sense_retains_literal_and_requires_physical_proof():
    from badw_grammatical_references import first_sense_prefix
    page,span,proof=first_sense_geometry()
    assert first_sense_prefix(page,span,proof)
    assert passage_matches(proof,'bcum','↓',basis=GRAMMATICAL,
        source_introduction='pf.',grammatical_pattern='paradigm_to_perfect')
    assert proof['literal']=='.  pf. zu ↑bcum'
    assert not passage_matches(dict(proof,numbered_sense=None),'bcum','↓',basis=GRAMMATICAL,
        source_introduction='pf.',grammatical_pattern='paradigm_to_perfect')


@pytest.mark.parametrize('damage',['later_sense','prior_body','prior_sense','font','unknown',
    'baseline','horizontal','different_digit','missing_copy','offset','outside','heading'])
def test_first_sense_cannot_join_unrelated_or_unverified_typography(damage):
    from badw_grammatical_references import first_sense_prefix
    page,span,p=first_sense_geometry();r=page['positioned_page']['positioned_text_runs']
    if damage=='later_sense':p['numbered_sense']['label']='2.'
    if damage=='prior_body':r[1]['decoded_unicode']='German prose'
    if damage=='prior_sense':r[1]['decoded_unicode']='1. pf. ↑other 2.'
    if damage=='font':r[2]['font_id']='i'
    if damage=='unknown':r[2]['glyphs'][0]['unknown']=True
    if damage=='baseline':r[2]['glyphs'][0]['y']=99
    if damage=='horizontal':r[2]['glyphs'][0]['x']=30
    if damage=='different_digit':r[2]['decoded_unicode']='2';r[2]['glyphs'][0]['unicode']='2'
    if damage=='missing_copy':r[2]['decoded_unicode']='';r[2]['glyphs']=[]
    if damage=='offset':p['run_start_offset']=2
    if damage=='outside':span['run_end_exclusive']=4
    if damage=='heading':span['loc_run_indices']=[3]
    assert not first_sense_prefix(page,span,p)
