"""Coordinate alignment tests use independent text/box fixtures, not predictions."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_qa_pdf_coordinates import reconcile, normal, geometric_lines, align_between_anchors


def qa(*texts):
    return [dict(line=str(i+1),line_text=t) for i,t in enumerate(texts)]


def pdf(text,x=10,y=10):
    return dict(text=text,box=[x,y,x+150,y+10])


def test_originals_preserved_and_line_breaks_do_not_change_readings():
    rows=qa('Distinctive hyphenated encyclopedia wording')
    layout=[pdf('Distinctive hyphen-',y=10),pdf('ated encyclopedia wording',y=25)]
    result=reconcile(rows,layout)[0]
    assert result['status']=='unique'
    assert result['coordinate']['pdf_lines']==[0,1]
    assert rows[0]['line_text']=='Distinctive hyphenated encyclopedia wording'
    assert layout[0]['text']=='Distinctive hyphen-'


def test_many_qa_lines_can_share_pdf_line_without_inventing_boxes():
    layout=[pdf('An unusually distinctive first clause. A second distinctive clause.')]
    results=reconcile(qa('An unusually distinctive first clause','A second distinctive clause'),layout)
    assert all(r['status']=='unique' for r in results)
    assert all(r['coordinate']['box']==layout[0]['box'] for r in results)


def test_repeated_lines_ambiguous_and_missing_text_unlocated():
    result=reconcile(qa('Repeated generic dictionary text','unrecoverable nonsense'),
                     [pdf('Repeated generic dictionary text'),pdf('Repeated generic dictionary text',x=300)])
    assert result[0]['status']=='ambiguous' and len(result[0]['alternatives'])==2
    assert result[1]['status']=='unmatched' and result[1]['coordinate'] is None


def test_reversed_baseline_fragments_join_spatially_without_crossing_gutter():
    layout=[dict(text='second',box=[45,10,75,20]),dict(text='first',box=[10,10,42,20]),pdf('other column',x=300)]
    groups=geometric_lines(layout)
    assert any(g['text']=='first second' and g['ids']==[1,0] for g in groups)
    assert not any('other' in g['text'] and 'first' in g['text'] for g in groups)


def test_bounded_sequence_joins_changed_line_breaks_but_never_interpolates():
    rows=qa('Distinctive opening anchor text','middle distinctive words split differently',
            'No corresponding original text','Distinctive closing anchor text')
    layout=[pdf(rows[0]['line_text'],y=10),pdf('middle distinctive words',y=30),
            pdf('split differently',y=45),pdf(rows[-1]['line_text'],y=75)]
    results=[dict(status='unique',normalized_length=30,coordinate=dict(box=layout[0]['box'],score=1)),
             dict(status='unmatched'),dict(status='unmatched'),
             dict(status='unique',normalized_length=30,coordinate=dict(box=layout[-1]['box'],score=1))]
    r=align_between_anchors(rows,layout,results)
    assert r[1]['status']=='unique_sequence' and r[1]['coordinate']['pdf_lines']==[1,2]
    assert r[2]['status']=='unmatched'


def test_canonical_equivalence_preserves_meaningful_distinctions():
    assert normal('é')==normal('e\u0301')
    assert normal('ཀ་')!=normal('ཁ་')
    assert normal('n')!=normal('ṅ')
