"""Controller recovery tests run real worker fixture validation, never paid calls."""
import json
from pathlib import Path
import sys

from PIL import Image
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_badw_linking_campaign as c


@pytest.fixture
def campaign(tmp_path,monkeypatch):
    def private(path):
        path=Path(path)
        path.mkdir(parents=True,exist_ok=True)
        return path
    monkeypatch.setattr(c.w,'private',private)
    root=tmp_path/'campaign'
    pages=[dict(family='wts_8_b',physical_page=n) for n in (21,22)]
    c.plan(root,pages,tmp_path/'bodies',tmp_path/'budget')
    monkeypatch.setattr(c.w,'authoritative',lambda _: ({},{},{},[],{},{}))
    calls=[]
    def prepare(spec,resources,directory,dpi):
        calls.append(spec['physical_page'])
        directory=private(directory)
        Image.new('RGB',(100,100),'white').save(directory/'page.png')
        pack=dict(family=spec['family'],physical_page=spec['physical_page'],source_sha256='source',
            geometry=None,bindings={},candidates=[],input_hashes={},image=dict(path='page.png',
            pixels=[100,100],sha256=c.w.a.digest(directory/'page.png'),transform=dict(
            pdf_to_mupdf=[1,0,0,1,0,0],points_per_pixel=[1,1],image_device_origin=[0,0])))
        c.w.write(directory/'pack.json',pack)
    monkeypatch.setattr(c.w,'prepare_page',prepare)
    fixtures=tmp_path/'fixtures'
    for page in pages:
        folder=private(fixtures/f"wts_8_b-{page['physical_page']}")
        item=dict(item_id='unassociated',heading_loc='unknown',heading_tibetan=None,
            printed_homonym=None,bbox=[10,10,40,20],column='left',classification='article',
            printed_evidence='unreadable definition',preceding='previous',following='next',uncertainty='uncertain')
        c.w.write(folder/'inventory.json',dict(visible_folios='?',completeness='partial',limitations='fixture',items=[item]))
        c.w.write(folder/'match.json',dict(matches=[dict(item_id='unassociated',outcome='unmatched',
            source_id=None,component_index=None,printed_evidence='',html_evidence='',boundary_evidence='',
            homonym_evidence='',alternatives='',uncertainty='no counterpart')]))
    return root,fixtures,calls


def test_complete_fixture_loop_resume_and_nonpromotion(campaign):
    root,fixtures,calls=campaign
    first=c.run(root,max_pages=1,fixtures=fixtures)
    assert first['stages']=={'pending':1,'awaiting_review':1}
    assert first['api_actual_usd']==0
    assert first['published_additional_links']==0
    second=c.run(root,fixtures=fixtures)
    assert second['stages']=={'awaiting_review':2}
    assert calls==[21,22]
    c.run(root,fixtures=fixtures)
    assert calls==[21,22]
    prediction=c.w.load(root/'pages/wts_8_b-21/prediction.json')
    assert prediction['items'][0]['item_id']=='unassociated'
    assert prediction['items'][0]['source_id'] is None
    assert prediction['items'][0]['pdf_bbox']==[10,10,40,20]
    assert c.status(root)['corpus_physical_scans']==3466


def test_status_observes_publication_lock_and_clears_after_exit(campaign):
    root,_,_=campaign
    with (root/'publication.lock').open('a') as lock:
        c.fcntl.flock(lock,c.fcntl.LOCK_EX|c.fcntl.LOCK_NB)
        state=c.status(root)
        assert state['process_running']
        assert state['publication_running']
        assert state['process_state']=='publishing'
    assert not c.status(root)['process_running']


def test_status_counts_finished_reader_instead_of_unpublished_proposals(campaign):
    root,_,_=campaign
    output=root/'finished'
    (output/'reader').mkdir(parents=True)
    c.w.write(output/'reader/print_facsimiles.json',dict(witnesses=['certified']))
    c.w.write(output/'reader/provisional_print_links.json',dict(witnesses=['one','two']))
    assert c.status(root)['published_reader_provisional_links'] is None
    with c.database(root) as db:
        c.event(db,None,'local_reader_published',dict(output=str(output)))
    state=c.status(root)
    assert state['published_reader_certified_links']==1
    assert state['published_reader_provisional_links']==2
    assert state['model_supported_proposals']==0
    (output/'reader/provisional_print_links.json').unlink()
    assert c.status(root)['published_reader_provisional_links']==0


def test_stop_after_inventory_reuses_paid_equivalent_cache(campaign,monkeypatch):
    root,fixtures,calls=campaign
    execute=c.w.execute
    def stop(*args,**kwargs):
        result=execute(*args,**kwargs)
        if args[0]['stage']=='inventory':
            (root/'STOP').touch()
        return result
    monkeypatch.setattr(c.w,'execute',stop)
    c.run(root,fixtures=fixtures)
    assert c.status(root)['stages']=={'inventoried':1,'pending':1}
    monkeypatch.setattr(c.w,'execute',execute)
    (root/'STOP').unlink()
    c.run(root,fixtures=fixtures)
    assert c.status(root)['stages']=={'awaiting_review':2}
    assert calls==[21,22]
    assert len(list((root/'pages/wts_8_b-21/fixtures').glob('*.json')))==2


def test_failed_page_continues_and_retains_diagnostics(campaign):
    root,fixtures,_=campaign
    c.w.write(fixtures/'wts_8_b-21/inventory.json',dict(invalid='rejected'))
    result=c.run(root,fixtures=fixtures)
    assert result['stages']=={'prepared':1,'awaiting_review':1}
    assert result['recent_errors'][0]['id']=='wts_8_b-21'
    assert result['published_additional_links']==0


def test_duplicate_views_fail_closed(tmp_path,monkeypatch):
    monkeypatch.setattr(c.w,'private',lambda p:(Path(p).mkdir(parents=True,exist_ok=True) or Path(p)))
    page=dict(family='wts_8_b',physical_page=21)
    with pytest.raises(ValueError,match='duplicate'):
        c.plan(tmp_path,[page,page],tmp_path/'bodies',tmp_path/'budget')
    assert c.database(tmp_path).execute('SELECT count(*) FROM views').fetchone()[0]==0


def test_prompt_change_prevents_requests(campaign):
    root,fixtures,_=campaign
    db=c.database(root)
    with db:
        db.execute('UPDATE config SET value=? WHERE key=?',(json.dumps({'inventory':'tampered'}),'prompt_hashes'))
    with pytest.raises(ValueError,match='prompt changed'):
        c.run(root,fixtures=fixtures)


def test_failed_publication_never_marks_assignments_published(campaign,monkeypatch,tmp_path):
    root,_,_=campaign
    monkeypatch.setattr(c,'sync_reviews',lambda _:None)
    db=c.database(root)
    with db:
        db.execute('INSERT INTO reviewed VALUES(?,?,?,?,?,0)',('sid','wts_8_b-21','sha','page','reviewer'))
    def fail(*args,**kwargs):
        raise c.subprocess.CalledProcessError(1,args[0])
    monkeypatch.setattr(c.subprocess,'run',fail)
    with pytest.raises(c.subprocess.CalledProcessError):
        c.publish(root,tmp_path/'reader')
    assert db.execute('SELECT published FROM reviewed').fetchone()[0]==0
    assert not (tmp_path/'reader/publication.json').exists()


def test_systematic_selection_uses_all_registered_families():
    pages=c.select_pages(200)
    assert len(pages)==200
    assert {p['family'] for p in pages}==set(c.w.a.FAMILIES)
    assert len({(p['family'],p['physical_page']) for p in pages})==200
    prior={(p['family'],p['physical_page']) for p in c.w.load(c.w.a.CERTIFICATE)['pages'] if p['accepted']}
    assert prior.intersection((p['family'],p['physical_page']) for p in pages), 'partially linked scans must remain eligible'
    with pytest.raises(ValueError):
        c.select_pages(1,{'wts_8_b':False})


def test_review_batch_requires_explicit_decisions_and_leaves_ledger_untouched(campaign,tmp_path):
    root,_,_=campaign
    before=c.w.a.digest(c.w.a.CERTIFICATE)
    decisions=tmp_path/'decisions.json'
    c.w.write(decisions,dict(bindings=[]))
    with pytest.raises(ValueError,match='explicit reviewed bindings'):
        c.review_batch(root,decisions,tmp_path/'proposed.json')
    assert c.w.a.digest(c.w.a.CERTIFICATE)==before
    assert not (tmp_path/'proposed.json').exists()


def test_publication_checkpoint_rejects_changed_build(campaign,monkeypatch,tmp_path):
    root,_,_=campaign
    monkeypatch.setattr(c,'sync_reviews',lambda _:None)
    output=tmp_path/'publication'
    files={}
    for name in ('pages/manifest.json','reader/data.json','reader/print_facsimiles.json','reader/manifest.json'):
        path=output/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('{}')
        files[name]=c.w.a.digest(path)
    c.w.write(output/'build-checkpoint.json',dict(certificate_sha256=c.w.a.digest(c.w.a.CERTIFICATE),files=files))
    (output/'reader/data.json').write_text('{"tampered":true}')
    with pytest.raises(ValueError,match='checkpoint changed'):
        c.publish(root,output,resume_build=True)
    assert c.status(root)['published_additional_links']==0


def test_status_accounts_for_paid_rejected_responses(campaign):
    root,_,_=campaign
    cfg=c.config(c.database(root))
    cache=c.w.private(root/'pages/wts_8_b-21/cache')
    c.w.write(cache/'rejected.json',dict(request_sha256='rejected',
        status='rejected model response; no evidence authority',usd=0.2,elapsed_seconds=4))
    budget=c.w.private(Path(cfg['budget_root']))
    c.w.write(budget/'spending.json',dict(requests={
        'rejected:0':dict(reserved=1,actual=0.2),
        'other-campaign:0':dict(reserved=1,actual=0.7),
        'uncertain:0':dict(reserved=1)}))
    result=c.status(root)
    assert result['campaign_returned_usage_usd']==0.2
    assert result['campaign_completed_requests']==1
    assert result['campaign_rejected_responses']==1
    assert result['api_actual_usd']==pytest.approx(0.9)
    assert result['api_unresolved_reservations_usd']==1
    assert result['model_supported_proposals']==0
