"""Blind model review cannot acquire certificate authority through agreement."""
import copy
import sys
import json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_campaign_review as r
from test_badw_model_worker import item, pack, match


def test_bounded_review_advances_past_completed_failed_and_uncached_pages(tmp_path):
    pages=[]
    for name in ['completed','uncached','cached','failed','exhausted']:
        directory=tmp_path/name
        (directory/'cache').mkdir(parents=True);pages.append(directory)
    r.w.write(pages[0]/'source_review.json',{})
    r.w.write(pages[2]/'cache/paid.json',dict(request=dict(stage='source_review')))
    r.w.write(pages[3]/'source-review-attempt.json',dict(attempts=1,at=1))
    r.w.write(pages[4]/'source-review-attempt.json',dict(attempts=3,at=1))
    assert r.unfinished_pages(pages)==[pages[2]]
    assert r.unfinished_pages(pages,live=True)==[pages[2],pages[1],pages[3]]
    r.w.write(pages[2]/'source_review.json',{})
    assert r.unfinished_pages(pages,live=True)[:1]==[pages[1]]


def observation():
    p=pack()
    return dict(inventory=p['inventory'],matching=match())


def test_blind_request_excludes_favored_answer_and_first_inventory():
    p=pack()
    p['inventory']['items'][0]['printed_evidence']='SECRET FIRST READING'
    p['match_images']=[dict(item_id='SECRET FAVORED',path='answer.png')]
    p['matches']=match()
    spec=r.w.request_spec('source_review',p,'gpt-6.1-terra','original',16000)
    assert 'SECRET' not in str(spec)
    assert 'inventory' not in spec['evidence']
    assert set(spec['evidence'])=={'candidates','image_pixels'}
    assert spec['evidence']['candidates'][0]['source_id']=='html:known'


def test_reconciliation_requires_location_identity_and_explicit_homonym():
    p=pack(); second=observation()
    result=r.reconcile(p['inventory'],match(),second)
    assert result[0]['state']=='model-source-reviewed'
    assert 'certified' not in result[0]
    for mutate in [lambda s:s['inventory']['items'][0].update(printed_homonym=1),
                   lambda s:s['inventory']['items'][0].update(bbox=[11,11,19,19]),
                   lambda s:s['matching']['matches'][0].update(source_id='competitor'),
                   lambda s:s['matching']['matches'][0].update(outcome='ambiguous'),
                   lambda s:s['inventory']['items'][0].update(classification='running_header'),
                   lambda s:s['matching'].update(matches=[])]:
        changed=copy.deepcopy(second);mutate(changed)
        assert r.reconcile(p['inventory'],match(),changed)[0]['state']=='exception'


def test_competing_overlapping_heading_is_not_hidden():
    p=pack(); second=observation()
    second['inventory']['items'].append(item('b'))
    other=copy.deepcopy(second['matching']['matches'][0]);other['item_id']='b';other['source_id']='competitor'
    second['matching']['matches'].append(other)
    assert r.reconcile(p['inventory'],match(),second)[0]['state']=='exception'


def test_nested_reference_abstention_does_not_veto_unique_article():
    p=pack(); second=observation()
    second['inventory']['items'].append(item('reference','embedded_reference'))
    other=copy.deepcopy(second['matching']['matches'][0])
    other.update(item_id='reference',outcome='insufficient',source_id=None,component_index=None)
    second['matching']['matches'].append(other)
    row=r.reconcile(p['inventory'],match(),second)[0]
    assert row['state']=='model-source-reviewed'
    assert row['second_item_ids']==['a','reference']
    other.update(outcome='supported',source_id='competitor')
    assert r.reconcile(p['inventory'],match(),second)[0]['state']=='exception'


def test_strict_combined_review_keeps_exclusions_and_abstentions():
    p=pack(); second=observation()
    second['inventory']['items'].append(item('header','running_header'))
    abstain=copy.deepcopy(second['matching']['matches'][0])
    abstain.update(item_id='header',outcome='unmatched',source_id=None,component_index=None)
    second['matching']['matches'].append(abstain)
    r.w.validate('source_review',second,p)
    second['matching']['matches'].pop()
    with pytest.raises(ValueError,match='omitted'):
        r.w.validate('source_review',second,p)


def test_budget_extension_preserves_paid_and_uncertain_requests(tmp_path,monkeypatch):
    monkeypatch.setattr(r.w.a,'ROOT',tmp_path)
    directory=tmp_path/'work'/'budget';directory.mkdir(parents=True)
    old=r.w.Spending(directory,1,'old')
    old.change('paid',reservation=.1);old.change('paid',actual=.02)
    old.change('uncertain',reservation=.3)
    before=r.w.load(directory/'spending.json')['requests']
    new=r.w.Spending(directory,2,'new')
    with pytest.raises(ValueError):new.extend('wrong','explicit approval')
    state=new.extend('old','explicit additional USD 1 approval')
    assert state['requests']==before
    assert state['authorization_history'][0]['cap']==1
    new.change('next',reservation=.1)
    with pytest.raises(ValueError,match='already reserved'):
        new.change('uncertain',reservation=.3)


def rejected_review(p, result):
    spec=r.w.request_spec('source_review',p,'gpt-6.1-terra','original',16000)
    output=json.dumps(result)
    return spec,dict(status='rejected model response; no evidence authority',response_status='completed',
        request=spec,request_sha256=r.w.a.object_digest(spec),output_text=output,
        output_sha256=r.w.a.object_digest(output),model=spec['model'],response_id='fixture',usage={},usd=.01)


def test_quote_recovery_preserves_original_and_only_repairs_unique_whitespace():
    p=pack(); second=observation()
    p['candidates'][0]['components'][0]['source_form']='specific\u00a0\n gloss'
    spec,cached=rejected_review(p,second); original=copy.deepcopy(cached)
    restored=r.recover_review(cached,spec,p)
    assert cached==original
    assert restored['result']['matching']['matches'][0]['html_evidence']=='specific\u00a0\n gloss'
    assert restored['result']['matching']['matches'][0]['outcome']=='supported'
    assert restored['recovery'][0]['before']['html_evidence']=='specific gloss'


def test_matching_recovery_keeps_exact_rows_and_quarantines_only_bad_quote():
    p=pack(); result=match()
    p['inventory']['items'].append(item('bad'))
    bad=copy.deepcopy(result['matches'][0])
    bad.update(item_id='bad',html_evidence='invented quotation')
    result['matches'].append(bad)
    spec=r.w.request_spec('match',p,'gpt-6.1-terra','original',16000)
    _,cached=rejected_review(p,observation())
    cached.update(request=spec,request_sha256=r.w.a.object_digest(spec),output_text=json.dumps(result))
    cached['output_sha256']=r.w.a.object_digest(cached['output_text'])
    original=copy.deepcopy(cached)
    restored=r.recover_review(cached,spec,p)
    assert cached==original
    assert restored['result']['matches'][0]==result['matches'][0]
    assert restored['result']['matches'][1]['outcome']=='insufficient'


@pytest.mark.parametrize('quote',['invented gloss','specific … gloss','specific gloss specific gloss',''])
def test_unfaithful_quote_is_quarantined_not_repaired(quote):
    p=pack();second=observation();second['matching']['matches'][0]['html_evidence']=quote
    spec,cached=rejected_review(p,second)
    restored=r.recover_review(cached,spec,p)
    assert restored['result']['matching']['matches'][0]['outcome']=='insufficient'
    assert r.reconcile(p['inventory'],match(),restored['result'])[0]['state']=='exception'


def test_recovery_cannot_hide_invented_identity_or_missing_inventory_item():
    p=pack();second=observation()
    second['matching']['matches'][0].update(source_id='invented',html_evidence='invented')
    spec,cached=rejected_review(p,second)
    with pytest.raises(ValueError,match='identity'):r.recover_review(cached,spec,p)
    second=observation();second['inventory']['items'].append(item('lost'))
    second['matching']['matches'][0]['html_evidence']='invented'
    spec,cached=rejected_review(p,second)
    with pytest.raises(ValueError,match='omitted'):r.recover_review(cached,spec,p)


def test_bad_component_is_quarantined_without_guessing_a_replacement():
    p=pack(); second=observation()
    second['inventory']['items'].append(item('bad'))
    bad=copy.deepcopy(second['matching']['matches'][0])
    bad.update(item_id='bad',component_index=999)
    second['matching']['matches'].append(bad)
    spec,cached=rejected_review(p,second); original=copy.deepcopy(cached)
    restored=r.recover_review(cached,spec,p)
    rows=restored['result']['matching']['matches']
    assert cached==original
    assert rows[0]==second['matching']['matches'][0]
    assert rows[1]['outcome']=='insufficient'
    assert rows[1]['component_index']==999
    assert rows[1]['html_evidence']==bad['html_evidence']


@pytest.mark.parametrize('field',['printed_evidence','boundary_evidence','homonym_evidence'])
def test_missing_required_testimony_is_excluded_without_inventing_it(field):
    p=pack(); second=observation()
    second['matching']['matches'][0][field]=''
    spec,cached=rejected_review(p,second)
    restored=r.recover_review(cached,spec,p)
    row=restored['result']['matching']['matches'][0]
    assert row['outcome']=='insufficient'
    assert row[field]==''
    assert field in row['uncertainty']


def test_incomplete_paid_response_is_never_salvaged_as_complete():
    p=pack(); spec,cached=rejected_review(p,observation())
    cached['response_status']='incomplete'
    with pytest.raises(ValueError,match='incomplete model response'):
        r.recover_review(cached,spec,p)
