"""Evaluation observations must not silently survive changed evidence."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_html_print_alignment import FAMILIES, object_digest
from evaluate_badw_qa_pdf_coordinates import evaluate, placement


def fixture(tmp_path):
    (tmp_path/'data').mkdir()
    family='wts_8_b'
    qa=tmp_path/f'release/current/qa/{family}/{family}_line_zones.tsv'
    qa.parent.mkdir(parents=True)
    row=dict(page='17',line='63',line_text='independent source reading')
    with qa.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(row),delimiter='\t');w.writeheader();w.writerow(row)
    (tmp_path/'data/source_pdfs.tsv').write_text('label\tsha256\n'+FAMILIES[family]+'\tsourcehash\n')
    image=tmp_path/'page.png';image.write_bytes(b'inspected rendering')
    label=dict(id='example',family=family,physical_page=17,qa_line=63,
               source_sha256='sourcehash',image_name=image.name,
               image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
               qa_row_sha256=object_digest(row),qa_text=row['line_text'],
               split='heldout',region=[.1,.1,.5,.5],observation='source image observation')
    benchmark=tmp_path/'labels.json'
    benchmark.write_text(json.dumps(dict(authority='test',selection='fixture',cases=[label])))
    database=tmp_path/'index.sqlite'
    db=sqlite3.connect(database)
    db.execute('CREATE TABLE lines(family,page,line,body)')
    db.execute('CREATE TABLE pages(family,page,features)')
    db.execute('INSERT INTO lines VALUES(?,?,?,?)',(family,17,63,json.dumps(dict(row,coordinate=dict(box=[20,20,30,30])))))
    db.execute('INSERT INTO pages VALUES(?,?,?)',(family,17,json.dumps(dict(width=100,height=100))))
    db.commit();db.close()
    return database,benchmark,image,qa


def test_placement_abstentions_are_not_successes():
    assert placement(None,[0,0,1,1],100,100)=='unlocated'
    assert placement(dict(box=[70,70,80,80]),[0,0,.5,.5],100,100)=='outside_observed_region'


def test_evaluation_checks_current_evidence(tmp_path):
    database,benchmark,image,qa=fixture(tmp_path)
    report=evaluate(tmp_path,database,benchmark,tmp_path)
    assert report['counts']['heldout']['reconciled:within_observed_region']==1
    qa.write_text(qa.read_text().replace('independent','changed'))
    with pytest.raises(ValueError,match='changed QA observation'):
        evaluate(tmp_path,database,benchmark,tmp_path)


def test_stale_index_and_changed_rendering_rejected(tmp_path):
    database,benchmark,image,qa=fixture(tmp_path)
    db=sqlite3.connect(database)
    row=json.loads(db.execute('SELECT body FROM lines').fetchone()[0]);row['line_text']='wrong'
    db.execute('UPDATE lines SET body=?',(json.dumps(row),));db.commit();db.close()
    with pytest.raises(ValueError,match='stale indexed QA'):
        evaluate(tmp_path,database,benchmark,tmp_path)
    image.write_bytes(b'changed')
    with pytest.raises(ValueError,match='changed inspected rendering'):
        evaluate(tmp_path,database,benchmark,tmp_path)


def sequence_fixture(tmp_path):
    _, _, image, qa = fixture(tmp_path)
    from evaluate_badw_qa_pdf_coordinates import verify_sequence_assessments
    row = next(csv.DictReader(qa.open(), delimiter='\t'))
    record = dict(family='wts_8_b', physical_page=17, source_sha256='sourcehash',
                  raster_sha256='rasterhash')
    directory = tmp_path/'coordinates/verified/wts_8_b'
    directory.mkdir(parents=True)
    (directory/'0017.json').write_text(json.dumps(dict(record=record, record_sha256=object_digest(record))))
    candidate = dict(anchor='wts_8_b:17:63', source_sha256='sourcehash',
                     raster_sha256='rasterhash', qa_row_sha256=object_digest(row), qa_text=row['line_text'])
    case = dict(source_id='test', html_sha256='htmlhash',
                candidates=[dict(candidate,label='local'),dict(candidate,label='adjusted')],
                publication_eligible=False, comparison_image=image.name,
                comparison_image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                assessment='both_wrong_article_start', homonym_assessment='unread')
    labels=tmp_path/'assessments.json'
    labels.write_text(json.dumps(dict(authority='test observation',cases=[case])))
    witness=dict(source_id='test',html_sha256='htmlhash',
                 local_ranking=[dict(anchor=candidate['anchor'])],sequence_ranking=[dict(anchor=candidate['anchor'])])
    witnesses=tmp_path/'witnesses.jsonl';witnesses.write_text(json.dumps(witness)+'\n')
    def check():
        return verify_sequence_assessments(tmp_path,labels,witnesses,tmp_path/'coordinates',tmp_path)
    return check,labels,witnesses,directory/'0017.json'


def test_sequence_observations_bind_frozen_predictions(tmp_path):
    check,labels,witnesses,page=sequence_fixture(tmp_path)
    assert check()['count']==1
    witness=json.loads(witnesses.read_text());witness['sequence_ranking'][0]['anchor']='wts_8_b:17:64'
    witnesses.write_text(json.dumps(witness)+'\n')
    with pytest.raises(ValueError,match='changed assessed predictions'):
        check()


def test_sequence_observations_reject_stale_render_and_inconsistent_reuse(tmp_path):
    check,labels,witnesses,page=sequence_fixture(tmp_path)
    data=json.loads(labels.read_text());data['cases'][0]['candidates'][1]['qa_text']='neighbour'
    labels.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='inconsistent repeated assessed anchor'):
        check()
    data['cases'][0]['candidates'][1]['qa_text']=data['cases'][0]['candidates'][0]['qa_text']
    labels.write_text(json.dumps(data))
    value=json.loads(page.read_text());value['record']['family']='wrong';value['record_sha256']=object_digest(value['record'])
    page.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='changed assessed source rendering'):
        check()


def test_sequence_observations_cannot_authorise_publication(tmp_path):
    check,labels,_,_=sequence_fixture(tmp_path)
    value=json.loads(labels.read_text());value['cases'][0]['publication_eligible']=True
    labels.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='cannot authorise publication'):
        check()
