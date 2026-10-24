"""Discovery preserves competitors and exact evidence without accepting links."""
import gzip
import hashlib
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from discover_badw_grammatical_references import discover


def fixture(tmp_path):
    reader=tmp_path/'reader';reader.mkdir()
    canonical=tmp_path/'canonical';canonical.mkdir()
    text='pf. zu ↓ka'
    body=json.dumps(dict(segments=[dict(text=text)])).encode()
    (reader/'entry.json').write_bytes(body)
    (reader/'data.json').write_text(json.dumps(dict(entries=[dict(id='source',path='entry.json',sha256=hashlib.sha256(body).hexdigest())])))
    records=[]
    for identity, tail in [('source','ka'),('one','bcum'),('two','bcums')]:
        runs=[dict(decoded_unicode=t) for t in ['ka',' pf. ↑',tail[:4],tail[4:]]]
        span=dict(canonical_object=identity+'.gz',run_start=0,run_end_exclusive=4,loc_run_indices=[0])
        (canonical/span['canonical_object']).write_bytes(gzip.compress(json.dumps(dict(printed_page=2,positioned_page=dict(positioned_text_runs=runs))).encode()))
        records.append(dict(id=identity,entry_start_source_span=span))
    index=tmp_path/'index.jsonl';index.write_text(''.join(json.dumps(r)+'\n' for r in records))
    case=dict(source_kind='pdf',classification='ambiguity',entry_id='source',source_binding=dict(text_sha256=hashlib.sha256(text.encode()).hexdigest()),source_span=dict(start=7,end=10),literal='↓ka',headword=dict(loc='bcum'),candidate_destinations=[dict(id='one'),dict(id='two')])
    census=tmp_path/'census.gz';census.write_bytes(gzip.compress((json.dumps(case)+'\n').encode()))
    return reader,census,index,canonical


def test_queue_is_reproducible_pinned_and_preserves_competing_interpretations(tmp_path):
    args=fixture(tmp_path)
    queue=list(discover(*args))
    assert queue==list(discover(*args))
    row,=queue
    assert row['decision']=='deferred'
    assert [c['id'] for c in row['competitors']]==['one','two']
    one,two=row['competitors']
    assert one['status']=='potentially_supported'
    assert two['status']=='contradicted'
    assert one['reciprocal_windows'] and two['contradicted_windows']
    assert row['source_evidence']['canonical_object_sha256']
    assert one['canonical_object_sha256'] and one['entry_start_source_span']


@pytest.mark.parametrize('fault',['shard','hash','extent'])
def test_queue_refuses_stale_reader_or_occurrence(tmp_path,fault):
    args=fixture(tmp_path);reader,census,_,_=args
    if fault=='shard':(reader/'entry.json').write_text('{}')
    else:
        row=json.loads(gzip.decompress(census.read_bytes()))
        if fault=='hash':row['source_binding']['text_sha256']='0'*64
        else:row['source_span']['end']-=1
        census.write_bytes(gzip.compress((json.dumps(row)+'\n').encode()))
    with pytest.raises(ValueError):list(discover(*args))
