import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import copy
import pytest
from evaluate_badw_alignment import wilson, evaluate, select_sample, causes


def row(sid='a'):
    return dict(source_id=sid,html_sha256='abc',result_category='review_required',
        editorial_headword={'loc':'ka'},editorial_homonym=None,editorial_definition='meaning',
        proposed=[dict(anchor='f:1:2',family='f',heading_text='ka',evidence_sha256='def',
            printed_evidence='meaning',coordinate=None, risks=['unverified_article_extent','printed_homonym_unread'],
            historical_identity_edge=False,definition_evidence={'rare_definition_tokens':[]},score=3)])


def test_intervals_and_unknowns_are_not_successes():
    assert wilson(0,0) is None
    assert wilson(0,10)[1] < .3
    label=select_sample([row()])[0]
    label['judgments']['heading']=True
    scores=evaluate([label],{'a':row()})
    assert scores['all/heading']['n']==1
    assert scores['all/lexical_identity']['unknown']==1
    assert scores['all/lexical_identity']['precision'] is None
    changed=row(); changed['proposed'][0]['anchor']='f:1:3'
    assert evaluate([label],{'a':changed})['all/heading']['n']==0
    changed['html_sha256']='stale'
    with pytest.raises(ValueError,match='stale'):
        evaluate([label],{'a':changed})


def test_seeded_selection_is_order_invariant_and_bounded():
    rows=[row(str(i)) for i in range(100)]
    assert select_sample(rows)==select_sample(reversed(rows))
    assert len(select_sample(rows))==4
    assert {c['split'] for c in select_sample(rows)}=={'development','held_out'}


def test_multiple_causes_are_not_exclusive_labels():
    value=causes(row())
    assert 'ambiguous_homonym' in value and 'incomplete_article' in value
    assert 'missing_historical_identity_edge' in value
    assert 'lexical_identity_not_discriminated' in value


def test_adjudication_is_bound_and_cannot_enable_attachment():
    from review_badw_alignment_cases import validate_decision, card
    value=row()
    d=dict(source_id='a',binding=dict(html_sha256='abc',scan_sha256='scan',
           anchor='f:1:2',evidence_sha256='def'),decision='defer',observation='Source is ambiguous',
           attachment_authority=True)
    assert validate_decision(d,value,'scan')['attachment_authority'] is False
    with pytest.raises(ValueError,match='stale'):
        validate_decision(d,value,'changed')
    d['observation']=''
    with pytest.raises(ValueError,match='observation'):
        validate_decision(d,value,'scan')
    value['proposed'][0]['physical_page']=1
    value['proposed'][0]['coordinate']=[1,2,3,4]
    value['editorial_definition']='<script>private</script>'
    assert '<script>' not in card(value)


def test_changed_predictions_remain_visible_and_do_not_inherit_labels():
    from evaluate_badw_alignment import prediction_changes
    label=select_sample([row()])[0]
    label['judgments']['lexical_identity']=True
    assert prediction_changes([label],{'a':row()})['counts']=={'retained_correct_prediction':1}
    label['judgments']['homonym']=False
    assert prediction_changes([label],{'a':row()})['counts']=={'explicitly_incorrect_identity':1}
    changed=row();changed['proposed'][0]['evidence_sha256']='new extent'
    report=prediction_changes([label],{'a':changed})
    assert report['counts']=={'changed_prediction_not_yet_assessable':1}
    assert evaluate([label],{'a':changed})['all/lexical_identity']['unknown']==1


def test_observation_source_bindings(tmp_path):
    import json, sqlite3
    from evaluate_badw_alignment import verify_observations
    from badw_html_print_alignment import digest, object_digest
    (tmp_path/'inputs.json').write_text(json.dumps({'inputs':{'scan:f':'scan'}}))
    db=sqlite3.connect(tmp_path/'index.sqlite')
    db.execute('CREATE TABLE lines(family,page,line,body)')
    qa={'line_text':'source heading','coordinate':[1,2,3,4]}
    db.execute('INSERT INTO lines VALUES(?,?,?,?)',('f',1,2,json.dumps(qa)))
    db.commit();db.close()
    image=tmp_path/'f-1.png';image.write_bytes(b'inspected image')
    image.with_suffix('.json').write_text(json.dumps(dict(family='f',physical_page=1,
        scan_sha256='scan',image_sha256=digest(image))))
    label=dict(anchor='f:1:2',family='f',coordinate=qa['coordinate'],
        qa_line_sha256=__import__('hashlib').sha256(b'source heading').hexdigest(),
        qa_row_sha256=object_digest({'line_text':'source heading'}),inspected_render_sha256=digest(image))
    labels=dict(scan_sha256={'f':'scan'},cases=[label])
    verify_observations(labels,tmp_path,tmp_path)
    for field,value,reason in [('coordinate',None,'coordinate'),('qa_line_sha256','stale','QA'),
                               ('inspected_render_sha256','stale','rendered')]:
        changed=copy.deepcopy(labels);changed['cases'][0][field]=value
        with pytest.raises(ValueError,match=reason):
            verify_observations(changed,tmp_path,tmp_path)
    labels['scan_sha256']['f']='changed'
    with pytest.raises(ValueError,match='scan'):
        verify_observations(labels,tmp_path,tmp_path)
