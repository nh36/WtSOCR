"""Comparison reports must account for changed predictions and source drift."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from report_badw_qa_pdf_coordinates import compare_predictions


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
    b['html_sha256']='reacquired'
    new.write_text(json.dumps(b)+'\n')
    with pytest.raises(ValueError,match='identities/checksums'):
        compare_predictions(old,new)
    new.write_text('')
    with pytest.raises(ValueError,match='inventory lengths'):
        compare_predictions(old,new)
