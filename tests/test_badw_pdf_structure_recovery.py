import copy
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_pdf_structure_recovery import recover


def packet(text, italic_end, nodes=()):
    return dict(identity='pdf:test', source_kind='pdf', nodes=[dict(id='source',kind='source_division',start=0,end=len(text),parent=None), *nodes],
        review_text_sha256=hashlib.sha256(text.encode()).hexdigest(), original_structure=dict(visual_lines=[dict(text=text,page_id='p1',printed_page=1,
            style_spans=[dict(start=0,end=5,style='regular'),
                         dict(start=5,end=italic_end,style='italic'),
                         dict(start=italic_end,end=len(text),style='regular')])]))


def test_initial_alias_gloss_is_recovered_without_changing_old_node():
    text='auch form Kleinkönig, Vasall.'
    old=dict(id='old',kind='definition',start=10,end=22,parent=None)
    p=packet(text,9,[old]);before=copy.deepcopy(p)
    r=recover(p,text)
    assert p==before and r['nodes'][1]==old
    n=r['nodes'][2]
    assert text[n['start']:n['end']]=='Vasall.'
    assert n['structural_recovery']['continuation_of']==['old']


def test_non_header_prose_is_not_recovered():
    text='hier form Erklärung.'
    p=packet(text,9)
    assert recover(p,text)==p


def test_unbalanced_quote_and_existing_example_are_rejected():
    text='auch form „Erklärung.'
    p=packet(text,9)
    assert recover(p,text)==p
    text='auch form Erklärung.'
    p=packet(text,9,[dict(id='ex',kind='example',start=10,end=len(text))])
    assert recover(p,text)==p


def test_semicolon_does_not_swallow_next_construction():
    text='auch form Erklärung; andere Konstruktion.'
    r=recover(packet(text,9),text)
    n=r['nodes'][1]
    assert text[n['start']:n['end']]=='Erklärung'


def test_header_continuations_are_not_definitions():
    for tail in (',auch other', ',fut. zu other', 'vgl. other'):
        text='auch form '+tail
        p=packet(text,9)
        assert recover(p,text)==p

def test_missing_source_container_is_rejected():
    text='auch form Erklärung.'
    p=packet(text,9)
    p['nodes']=[]
    assert recover(p,text)==p


def hyphen_packet(column=100, tail='ren, lenken; neue Konstruktion.'):
    text='regie-\n'+tail
    return text, dict(identity='pdf:hyphen',source_kind='pdf',
        review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        nodes=[dict(id='source',kind='source_division',start=0,end=len(text),parent=None),
               dict(id='def',kind='definition',start=0,end=6,parent='source')],
        original_structure=dict(visual_lines=[
            dict(text='regie-',page_id='p1',printed_page=1,first_x=100,y=10,
                 style_spans=[dict(start=0,end=6,style='regular')]),
            dict(text=tail,page_id='p1',printed_page=1,first_x=column,y=8.8,
                 style_spans=[dict(start=0,end=len(tail),style='regular')])]))


def test_explicit_hyphen_continuation_stops_at_semicolon():
    text,p=hyphen_packet();before=copy.deepcopy(p)
    r=recover(p,text)
    assert p==before
    n=r['nodes'][-1]
    assert text[n['start']:n['end']]=='ren, lenken'
    assert n['structural_recovery']['continuation_of']==['def']


def test_hyphen_continuation_rejects_column_jump_and_existing_example():
    text,p=hyphen_packet(column=350)
    assert recover(p,text)==p
    text,p=hyphen_packet()
    p['nodes'].append(dict(id='ex',kind='example',start=7,end=len(text),parent='source'))
    assert recover(p,text)==p
