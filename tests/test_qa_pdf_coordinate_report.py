"""Comparison reports must account for changed predictions and source drift."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from report_badw_qa_pdf_coordinates import compare_predictions, diagnostic_traits


def test_diagnostic_strata_preserve_position_provenance():
    row=dict(line_text='བ་ short-',zone='headword_line',
             legacy_coordinate=dict(box=[20,5,90,15]))
    model=dict(status='coordinate_clusters',centres=[20,120])
    traits=diagnostic_traits(row,True,dict(height=200),model)
    assert traits['position_basis']=='legacy_only'
    assert traits['page_position']=='top'
    assert traits['tibetan'] and traits['hyphenated'] and traits['repeated_on_page']
    row['coordinate']=dict(box=[120,100,180,110])
    traits=diagnostic_traits(row,False,dict(height=200),model)
    assert traits['position_basis']=='reconciled'
    assert traits['page_position']=='body'
    del row['coordinate'];del row['legacy_coordinate']
    traits=diagnostic_traits(row,False,dict(height=200),model)
    assert traits['page_position']=='unlocated' and traits['column'] is None


def test_changed_top_is_unassessed_and_changed_evidence_counted(tmp_path):
    a=dict(source_id='witness',html_sha256='hash',eligible_for_original_print_link=True,
           reviewed_page='page',machine_publication=dict(eligible=False),
           proposed=[dict(anchor='a',definition_evidence={'word':'old'},evidence_lines=[1])])
    b=dict(a,proposed=[dict(anchor='b',definition_evidence={},evidence_lines=[2]),
                       dict(anchor='a',definition_evidence={'word':'new'},evidence_lines=[1])])
    old,new=tmp_path/'old.jsonl',tmp_path/'new.jsonl'
    old.write_text(json.dumps(a)+'\n');new.write_text(json.dumps(b)+'\n')
    report=compare_predictions(old,new)
    assert report['counts']['changed_top_predictions']==1
    assert report['counts']['changed_definition_evidence']==1
    assert report['counts']['reviewed_page_changed']==0
    assert report['counts']['machine_eligible']==0
    assert report['changed_predictions'][0]['assessment']=='unassessed'
    assert report['changed_predictions'][0]['original']['anchor']=='a'
    assert report['changed_predictions'][0]['reconstructed']['anchor']=='b'
    assert report['changed_evidence'][0]['original']['definition_evidence']=={'word':'old'}
    assert report['changed_evidence'][0]['reconstructed']['definition_evidence']=={'word':'new'}
    b['html_sha256']='reacquired'
    new.write_text(json.dumps(b)+'\n')
    with pytest.raises(ValueError,match='identities/checksums'):
        compare_predictions(old,new)
    new.write_text('')
    with pytest.raises(ValueError,match='inventory lengths'):
        compare_predictions(old,new)


def test_span_hypotheses_are_not_verified_boundaries():
    import sqlite3
    from report_badw_qa_pdf_coordinates import crossed_candidates, evidence_delta
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE starts(aid TEXT,family TEXT,page INTEGER,line INTEGER,body TEXT)')
    for aid,line in [('own',16),('intervening',38),('outside',45)]:
        db.execute('INSERT INTO starts VALUES(?,?,?,?,?)',
                   (aid,'family',267,line,json.dumps(dict(text=aid,line=line))))
    proposal=dict(anchor='own',family='family',physical_page=267,evidence_lines=[16,40])
    report=crossed_candidates(proposal,db)
    assert [r['anchor'] for r in report['candidates']]==['intervening']
    assert report['candidates'][0]['heading']=='intervening'
    assert report['status']=='mechanical_hypotheses_not_verified_boundaries'
    a=dict(definition_evidence=dict(rare_definition_tokens=['salt']))
    b=dict(definition_evidence=dict(rare_definition_tokens=['salt','cow']))
    delta=evidence_delta(a,b)
    assert delta['feature_direction']=='stronger_overlap'
    assert delta['correctness']=='unassessed'
