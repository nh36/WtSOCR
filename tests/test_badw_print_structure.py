import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
"""Structural rules, actual release coordinates, and independent DP equivalence."""
import csv
import random
from pathlib import Path
import pytest
from badw_print_structure import heading_features, segment, increasing_chain, same_column
import badw_html_print_engine as engine


def start(anchor, text, coordinate=None, zone='german_prose_with_translit'):
    return dict(anchor=anchor, text=text, coordinate=coordinate, zone=zone,
                matches={'a':['loc_exact']})


def test_independent_heading_stops_definition_borrowing():
    a=start('x:1:1', 'ཀ་ ka', {'box':[10,30,90,40]})
    b=start('x:1:3', 'ཁ་ kha', {'box':[10,70,90,80]})
    rows={1:dict(line_text=a['text'],coordinate=a['coordinate']),
          2:dict(line_text='own definition',coordinate={'box':[12,50,90,60]}),
          3:dict(line_text=b['text'],coordinate=b['coordinate']),
          4:dict(line_text='neighbour distinctive definition',coordinate={'box':[12,85,90,95]})}
    result=segment(1,a,rows,[(1,a),(3,b)])
    assert result['lines']==[(1,a['text']),(2,'own definition')]
    assert result['next_anchor']=='x:1:3'
    assert result['boundary_method']=='coordinate_heading'
    assert 'unverified_article_extent' not in result['risks']
    # Missing coordinates do not become a geometrically verified extent.
    b['coordinate']=None
    assert 'unverified_article_extent' in segment(1,a,rows,[(1,a),(3,b)])['risks']


def test_separate_columns_and_no_unproved_continuation():
    assert same_column([10,20,90,30],[120,20,200,30]) is False
    a=start('a','ཀ་ ka',{'box':[10,20,90,30]})
    rows={1:dict(line_text=a['text'],coordinate=a['coordinate']),
          2:dict(line_text='other column',coordinate={'box':[120,40,200,50]})}
    result=segment(1,a,rows,[(1,a)])
    assert len(result['lines'])==1
    assert 'unverified_article_extent' in result['risks']
    assert 'not joined' in result['continuation']


@pytest.mark.parametrize('text,number,status',[
    ('² ཀ་ ka', '2','ocr_prefix_number_candidate'),
    ('ཀ་ ka 2. Bedeutung',None,'absence_not_verified'),
    ('2. Bedeutung',None,'unread'),
    ('ཀ་ ka (12)',None,'absence_not_verified'),
])
def test_homonym_prefix_is_not_a_sense(text,number,status):
    assert heading_features(text)['homonym']==number
    assert heading_features(text)['homonym_status']==status


def test_fast_chain_matches_optimum_with_equal_positions_and_gaps():
    rng=random.Random(20261025)
    for _ in range(100):
        values=[(rng.randrange(10),rng.randrange(10),rng.randrange(1,9),i) for i in range(30)]
        old=engine.monotone_chain(values); new=increasing_chain(values)
        weights={v[3]:v[2] for v in values}
        assert sum(weights[k] for k in old)==sum(weights[k] for k in new)


@pytest.mark.parametrize('family,page,header,article,loc,tib',[
    ('wts_1_34',1090,55,89,'da yaṅ','ད་ཡང་'),
    ('wts_35_51',106,47,59,'mdun','མདུན་'),
])
def test_real_release_header_and_start(tmp_path,family,page,header,article,loc,tib):
    """Uses the release QA, not a restatement of the expected heading string."""
    path=Path(__file__).resolve().parents[1]/f'release/current/qa/{family}/{family}_line_zones.tsv'
    rows=[r for r in csv.DictReader(path.open(),delimiter='\t') if int(r['page'])==page]
    definition='nun jetzt noch' if family=='wts_1_34' else 'Vordere Vorderseite Frontseite'
    from test_badw_html_print_engine import witness,page_proposals
    results=page_proposals(tmp_path,{'a':witness(loc,tib,definition)},
        [(int(r['line']),r['line_text'],r['zone']) for r in rows],family,page)
    wrong,correct=results[f'{family}:{page}:{header}'],results[f'{family}:{page}:{article}']
    assert article not in wrong['evidence_lines']
    assert correct['score']>wrong['score']
    assert correct['definition_evidence']['rare_definition_tokens']
    assert engine.category([wrong])[0]=='review_required'


def test_real_salt_and_salty_are_distinct():
    from test_badw_html_print_engine import witness
    path=Path(__file__).resolve().parents[1]/'release/current/qa/wts_8_b/wts_8_b_line_zones.tsv'
    rows={int(r['line']):r for r in csv.DictReader(path.open(),delimiter='\t') if int(r['page'])==17}
    indexes=engine.lexical_indexes({'salt':witness('ba tshwa','བ་ཚྭ་'), 'salty':witness('ba tshwa can','བ་ཚྭ་ཅན་')})
    assert 'Kuhsalz' in rows[63]['line_text']
    assert 'salzig' in rows[78]['line_text']
    assert 'salt' in engine.discover_line(rows[63],indexes)
    matches=engine.discover_line(rows[77],indexes)
    assert 'prefix_of_longer_observed_heading' in matches['salt']
    assert 'prefix_of_longer_observed_heading' not in matches['salty']
