"""Machine suggestions never acquire certificate authority or displace exact links."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_provisional_print_links as p


def test_checked_in_dataset_is_unique_uncertified_and_checksum_bound():
    data=p.w.load(p.DATA)
    p.validate_dataset(data)
    assert len(data['witnesses']) >= 100
    # Failed paid packets remain visible, but cannot supply reader links.
    assert not ({row['page'] for row in data['failures']} &
                {row['page'] for row in data['witnesses']})
    for change in [lambda d:d.update(certified=True),
                   lambda d:d.update(registry_sha256='wrong'),
                   lambda d:d['witnesses'].append(copy.deepcopy(d['witnesses'][0])),
                   lambda d:d['pages'][d['witnesses'][0]['page']].update(physical_page=100000),
                   lambda d:d['witnesses'][0]['second_reading'].update(matching=[])]:
        damaged=copy.deepcopy(data);change(damaged)
        with pytest.raises(ValueError): p.validate_dataset(damaged)


def test_competing_failed_candidates_block_otherwise_eligible_identity():
    rows=[dict(source_url='same',page='a',disposition='eligible'),
          dict(source_url='same',page='b',disposition='disputed'),
          dict(source_url='other',page='c',disposition='eligible'),
          dict(source_url='other',page='c',disposition='eligible')]
    assert p.deduplicate(rows)==[rows[2]]
    assert [r['disposition'] for r in rows]==['competing_pages','disputed','published_provisional','duplicate']


def test_wrong_homonym_and_nonheading_readings_are_withheld():
    body=dict(headword=dict(loc='koṅ po'),homonym='2')
    row=dict(already_certified=False,previous_decisions=[],state='model-source-reviewed',
             heading=dict(heading_loc='koṅ po',printed_homonym=2),second_item_ids=['a'])
    second=dict(inventory=dict(items=[dict(item_id='a',heading_loc='koṅ po',printed_homonym=2)]))
    assert p.eligibility(row,second,body)=='eligible'
    second['inventory']['items'][0]['printed_homonym']=1
    assert p.eligibility(row,second,body)=='homonym_mismatch'
    row['heading']['heading_loc']='left column';second['inventory']['items'][0]['heading_loc']='line 23'
    assert p.eligibility(row,second,body)=='heading_mismatch'
    row['already_certified']=True
    assert p.eligibility(row,None,body)=='already_certified'


def test_attachment_prefers_certified_and_checks_html_and_derivative(tmp_path):
    data=p.w.load(p.DATA); row=data['witnesses'][0]
    data['witnesses']=[row]
    (tmp_path/'dataset.json').write_text(json.dumps(data))
    pdf=tmp_path/'source.pdf';pdf.write_bytes(b'%PDF-test')
    p.w.write(tmp_path/'manifest.json',dict(dataset=str(tmp_path/'dataset.json'),
        dataset_sha256=p.w.a.digest(tmp_path/'dataset.json'),
        pages={row['page']:dict(path=pdf.name,sha256=p.w.a.digest(pdf))}))
    (tmp_path/'reader/sources').mkdir(parents=True)
    suggestions=p.Suggestions(tmp_path/'manifest.json',tmp_path/'reader')
    entry=dict(source_kind='html',source_url=row['source_url'],headword=dict(loc=row['headword']),
               homonym=row['homonym'],sources=[dict(sha256=row['html_sha256'])])
    certified=copy.deepcopy(entry);certified['sources'].append(dict(print_provenance={'certified':True}))
    suggestions.attach(certified);assert len(certified['sources'])==2
    wrong=copy.deepcopy(entry);wrong['sources'][0]['sha256']='wrong'
    suggestions.attach(wrong);assert len(wrong['sources'])==1
    damaged=copy.deepcopy(entry);damaged['homonym']='999'
    with pytest.raises(ValueError):suggestions.attach(damaged)
    pdf.write_bytes(b'changed')
    with pytest.raises(ValueError,match='derivative changed'):suggestions.attach(entry)
    pdf.write_bytes(b'%PDF-test');suggestions.attach(entry)
    assert len(entry['sources'])==2
    assert entry['sources'][1]['suggested_print_provenance']['printed_folio'] is None
    assert 'not yet verified' in entry['sources'][1]['label']
