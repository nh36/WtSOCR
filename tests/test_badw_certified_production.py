"""Fresh source controls, crop boundaries and crash recovery; never paid calls."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_certified_production as p
import certify_badw_model_links as c
import badw_print_page_map as m

EXAMPLES=json.loads((Path(__file__).parent/'fixtures/badw_model_fresh_policy_examples.json').read_text())['cases']

@pytest.mark.parametrize('example',EXAMPLES,ids=lambda x:x['body']['headword']['loc']+str(x['body']['homonym']))
def test_source_inspected_fresh_references(example):
    assert example['identity_correct']
    assert c.policy_reason(example['cached_row'],example['body'],example['headword_count'],fresh=True) is None

@pytest.mark.parametrize('change',['target','prefix','heading','numeral','uncertainty','prior','component'])
def test_independent_fresh_negative_controls(change):
    e=copy.deepcopy(EXAMPLES[0]);row=e['cached_row'];body=e['body']
    if change=='target': row['second_reading']['inventory'][0]['printed_evidence']='→ unrelated'
    if change=='prefix': row['second_reading']['inventory'][0]['printed_evidence']=row['first_matching']['html_evidence']+'suffix'
    if change=='heading':row['second_reading']['inventory'][0]['classification']='running_header'
    if change=='numeral':row['second_reading']['inventory'][0]['printed_homonym']=99
    if change=='uncertainty':row['second_reading']['inventory'][0]['uncertainty']='Could belong to the next article'
    if change=='prior':row['previous_decisions']=[{'decision':'reject'}]
    if change=='component':row['component_sha256']='0'*64
    assert c.policy_reason(row,body,e['headword_count'],fresh=True)


def test_geometry_requires_both_readings_on_one_side():
    row=copy.deepcopy(EXAMPLES[0]['cached_row'])
    hs=c.readings(row)[0]
    for h in hs:h['bbox']=[10,10,20,20]
    evidence=dict(source_sha256='hash',physical_page=1,image=dict(transform=dict(pdf_to_mupdf=[1,0,0,1,0,0],points_per_pixel=[1,1],image_device_origin=[0,0])))
    pages={s:dict(source_sha256='hash',physical_page=1,crop=box) for s,box in [('left',[0,0,50,100]),('right',[50,0,100,100])]}
    assert m.assign(row,evidence,pages)=='left'
    hs[1]['bbox']=[60,10,70,20]
    with pytest.raises(ValueError,match='disagree'):m.assign(row,evidence,pages)

@pytest.mark.parametrize('committed',[False,True])
def test_publication_recovery_keeps_last_working_reader(tmp_path,committed):
    canonical=tmp_path/'canonical';canonical.write_text('new')
    backup=tmp_path/'backup';backup.write_text('old')
    old=tmp_path/'old';old.mkdir();new=tmp_path/'new';new.mkdir()
    (tmp_path/'current').symlink_to(new if committed else old)
    p.w.write(tmp_path/'transaction.json',dict(generation=str(new),backups={str(canonical):str(backup)}))
    p.recover(tmp_path)
    assert canonical.read_text()==('new' if committed else 'old')
    assert (tmp_path/'current').resolve()==(new if committed else old)
    assert not (tmp_path/'transaction.json').exists()


# Selection predates this policy: two SHA-selected identities per scan family,
# including cases that abstain. This prevents reporting pass-selected controls
# as representative retrieval coverage.
AUDIT=json.loads((Path(__file__).parent/'fixtures/badw_model_policy_examples.json').read_text())['audit']

@pytest.mark.parametrize('example',AUDIT,ids=lambda x:x['page']+x['body']['headword']['loc'])
def test_prior_source_first_sample_under_fresh_policy(example):
    reason=c.policy_reason(example['cached_row'],example['body'],example['headword_count'],fresh=True)
    assert example['identity_correct']
    assert (reason is None)==(example['body']['headword']['loc']=='ma gnas')


def test_tibetan_heading_identity_when_loc_contains_location():
    e=copy.deepcopy(EXAMPLES[0]);h=e['cached_row']['heading']
    h['heading_loc']='left column, first article'
    h['heading_tibetan']=e['body']['headword']['tibetan']
    assert c.policy_reason(e['cached_row'],e['body'],e['headword_count'],fresh=True) is None
    h['heading_tibetan']='མ་'
    assert c.policy_reason(e['cached_row'],e['body'],e['headword_count'],fresh=True)=='independent heading identity'
    h['heading_tibetan']=e['body']['headword']['tibetan'];h['heading_loc']='different headword'
    assert c.policy_reason(e['cached_row'],e['body'],e['headword_count'],fresh=True)=='independent heading identity'


def test_cache_aliases_are_not_competing_physical_pages(monkeypatch):
    monkeypatch.setattr(m,'assign',lambda r,e,p:e['side'])
    rows=[dict(source_url='url',page=k) for k in ('whole','crop')]
    evidence={k:dict(source_sha256='sha',physical_page=1,side='left') for k in ('whole','crop')}
    assert not c.competing_assignments(rows,evidence,{})
    evidence['crop']['side']='right'
    assert c.competing_assignments(rows,evidence,{})=={'url'}
    evidence['crop']['side']='left';evidence['crop']['physical_page']=2
    assert c.competing_assignments(rows,evidence,{})=={'url'}
