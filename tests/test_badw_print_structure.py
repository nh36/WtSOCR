import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
"""Structural rules, actual release coordinates, and independent DP equivalence."""
import csv
import random
from pathlib import Path
import pytest
from badw_print_structure import heading_features, segment, increasing_chain, same_column, source_heading, clip_at_unlocated_heading, heading_layout
import badw_html_print_engine as engine


def start(anchor, text, coordinate=None, zone='german_prose_with_translit'):
    return dict(anchor=anchor, text=text, coordinate=coordinate, zone=zone,
                matches={'a':['loc_exact']})


def test_measured_heading_layout_keeps_columns_separate_and_has_no_authority():
    rows={}
    for col,left in enumerate((30,550)):
        for i in range(8):
            rows[col*100+i]=dict(line_text='An ordinary definition with sufficient prose.',
                                coordinate={'box':[left,100+i*20,left+300,110+i*20]})
    rows[20]=dict(line_text='ཀ་ ka definition',coordinate={'box':[20,270,330,286]})
    rows[120]=dict(line_text='ཁ་ kha definition',coordinate={'box':[540,270,850,286]})
    rows[21]=dict(line_text='1. An indented numbered sense.',
                  coordinate={'box':[20,300,330,316]})
    measured=heading_layout(rows,lambda b: int(b[0]>400) if b else None)
    assert measured[20]['prose_left']==30
    assert measured[120]['prose_left']==550
    for n in (20,120):
        observation=source_heading(rows[n],1000,measured[n])
        assert observation['status']=='possible_heading'
        assert 'measured_column_outdent' in observation['reasons']
        assert 'larger_than_column_prose' in observation['reasons']
        assert 'not independently verified' in observation['authority']
    assert source_heading(rows[21],1000,measured[21])['status']=='not_heading'


def test_sparse_or_unlocated_columns_do_not_invent_prose_baselines():
    rows={1:dict(line_text='A sufficiently long ordinary prose line.',
                 coordinate={'box':[30,100,330,110]}),
          2:dict(line_text='ཀ་ ka',coordinate=None)}
    assert heading_layout(rows,lambda b: 0 if b else None)=={}


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
    assert 'unverified_article_extent' in result['risks']
    assert 'unverified_definition_ownership' in result['risks']
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


def test_unindexed_unlocated_heading_excludes_neighbours_definition():
    a = start('x:1:1', 'ཀ་ ka', {'box': [10, 30, 90, 40]})
    rows = {
        1: dict(line_text=a['text'], coordinate=a['coordinate']),
        2: dict(line_text='own definition'),
        3: dict(line_text='ཁ་ kha'),  # No C6 anchor, QA label or coordinate.
        4: dict(line_text='neighbour distinctive definition'),
    }
    result = segment(1, a, rows, [(1, a)])
    assert result['lines'] == [(1, a['text']), (2, 'own definition')]
    assert result['next_line'] == 3
    assert result['next_anchor'] is None
    assert result['boundary_method'] == 'line_order_heading_uncertain'
    assert 'unverified_definition_ownership' in result['risks']


def test_unlocated_heading_interrupts_physical_interval():
    selected = [((267, 0, n * 10, 10, n), n, {}) for n in (16, 17, 37, 39, 40)]
    safe, threats = clip_at_unlocated_heading(selected, 267, 16, [(267, 38)])
    assert [n for _, n, _ in safe] == [16, 17, 37]
    assert threats == [(267, 38)]
    assert clip_at_unlocated_heading(selected, 267, 16, [(267, 15)]) == (selected, [])


@pytest.mark.parametrize('positions,barrier,expected', [
    ([(1,1),(1,2),(2,1)], (1,3), [(1,1),(1,2)]),
    ([(1,1),(3,1)], (2,1), [(1,1)]),
    ([(1,1),(1,4),(1,2)], (1,3), [(1,1)]),
])
def test_unlocated_barrier_keeps_only_physical_prefix(positions, barrier, expected):
    selected = [((p,0,i,10,n),n,{}) for i,(p,n) in enumerate(positions)]
    safe, threats = clip_at_unlocated_heading(selected, 1, 1, [barrier])
    assert [(key[0],n) for key,n,_ in safe] == expected
    assert threats == [barrier]


@pytest.mark.parametrize('text', ['༡༢་ 12', '།་ ka', 'German prose', '2. Bedeutung'])
def test_punctuation_and_sense_numbers_are_not_source_headings(text):
    assert source_heading(dict(line_text=text))['status'] == 'not_heading'


def test_real_repeated_ldongs_heading_interrupts_without_inventory_or_coordinates():
    path = Path(__file__).resolve().parents[1] / 'release/current/qa/wts_35_51/wts_35_51_line_zones.tsv'
    rows = {int(r['line']): r for r in csv.DictReader(path.open(), delimiter='\t')
            if int(r['page']) == 267}
    assert 'ldo' in rows[16]['line_text']
    # The second transliteration is damaged (T'mdoṅs); do not silently repair it.
    assert rows[38]['line_text'].startswith('ལྡོངས་')
    a = start('wts_35_51:267:16', rows[16]['line_text'])
    result = segment(16, a, rows, [(16, a)])
    assert result['next_line'] <= 38
    assert all(n < 38 for n, _ in result['lines'])
    assert source_heading(rows[38])['status'] == 'possible_heading'


def test_real_tibetan_digit_continuation_does_not_split_article():
    path = Path(__file__).resolve().parents[1] / 'release/current/qa/wts_9_m/wts_9_m_line_zones.tsv'
    rows = {int(r['line']): r for r in csv.DictReader(path.open(), delimiter='\t')
            if int(r['page']) == 17}
    assert rows[29]['zone'] == 'headword_line'
    assert 'ter geboren' in rows[29]['line_text']
    assert source_heading(rows[29])['status'] == 'not_heading'
    a = start('wts_9_m:17:28', rows[28]['line_text'])
    result = segment(28, a, rows, [(28, a)])
    assert result['next_line'] == 34
    assert 29 in [n for n, _ in result['lines']]
