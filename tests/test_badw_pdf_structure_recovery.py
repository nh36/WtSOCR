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


def test_reference_after_gloss_is_not_recovered_as_definition():
    for marker in ('vgl.', 's. v.', 'Abt.', 'pf.'):
        text='auch form Erklärung, '+marker+' anderes'
        old=dict(id='old',kind='definition',start=10,end=19,parent='source')
        p=packet(text,9,[old])
        r=recover(p,text)
        assert r['nodes']==p['nodes']


def test_unfinished_parenthetical_stops_before_opening_delimiter():
    for delimiter in ('(', '['):
        text='auch form Erklärung '+delimiter
        r=recover(packet(text,9),text)
        assert text[r['nodes'][-1]['start']:r['nodes'][-1]['end']]=='Erklärung'


def test_balanced_nested_parenthetical_is_preserved():
    text='auch form Erklärung (mit [Zusatz]).'
    r=recover(packet(text,9),text)
    assert text[r['nodes'][-1]['start']:r['nodes'][-1]['end']]=='Erklärung (mit [Zusatz]).'


def test_subtraction_must_not_create_unbalanced_fragment():
    text='auch form Erklärung (Zusatz).'
    old=dict(id='old',kind='definition',start=10,end=25,parent='source')
    p=packet(text,9,[old])
    assert recover(p,text)['nodes']==p['nodes']

from badw_pdf_quotation_recovery import recover_quotations


def quote_packet(quote='„eine Form“', envelope=False):
    text='form ~ '+quote+' (Dagy).'
    a=text.index('„'); b=text.index(' (Dagy)')
    p=dict(identity='pdf:quote',source_kind='pdf',
        nodes=[dict(id='source',kind='source_division',start=0,end=len(text),parent=None),
               dict(id='cite',kind='citation',start=b+1,end=len(text)-1,parent='source')],
        original_structure=dict(visual_lines=[dict(text=text,page_id='p1',first_x=100,y=10,
            style_spans=[dict(start=0,end=a-1,style='italic'),
                         dict(start=a-1,end=len(text),style='regular')])]))
    if envelope:
        p['nodes'].append(dict(id='lex',kind='lexicographic',start=0,end=len(text),parent='source'))
    return text,p


def test_bounded_substitution_translation_keeps_source_and_citation():
    text,p=quote_packet(); before=copy.deepcopy(p)
    r=recover_quotations(p,text)
    assert p==before
    ex=next(n for n in r['nodes'] if n['kind']=='example')
    trans=next(n for n in r['nodes'] if n['kind']=='translation')
    assert text[trans['start']:trans['end']]=='„eine Form“'
    assert trans['parent']==ex['id']
    assert next(n for n in r['nodes'] if n['id']=='cite')['parent']==ex['id']
    assert recover_quotations(r,text)==r


def test_existing_lex_gloss_does_not_create_example():
    text,p=quote_packet(envelope=True)
    r=recover_quotations(p,text)
    assert not any(n['kind']=='example' for n in r['nodes'])
    assert r['nodes'][-1]['parent']=='lex'


def test_nested_quotes_preserve_literal_punctuation():
    text,p=quote_packet('„eine ‚innere‘ Form“')
    r=recover_quotations(p,text)
    assert text[r['nodes'][-1]['start']:r['nodes'][-1]['end']]=='„eine ‚innere‘ Form“'


def test_malformed_delimiter_and_non_substitution_are_not_promoted():
    text,p=quote_packet('„eine (Form“')
    assert recover_quotations(p,text)==p
    text,p=quote_packet()
    text=text.replace('~','x');p['original_structure']['visual_lines'][0]['text']=text
    assert recover_quotations(p,text)==p


def test_quote_cannot_swallow_sense_boundary_or_typed_citation():
    for kind in ('sense','citation','lexicographic'):
        text,p=quote_packet()
        a=text.index('„')
        p['nodes'].append(dict(id='hard',kind=kind,start=a+2,end=len(text),parent='source'))
        assert recover_quotations(p,text)==p


def test_multiline_quote_requires_continuous_column_geometry():
    text,p=quote_packet('„eine\nForm“')
    first,second=text.split('\n')
    a=text.index('„')
    p['original_structure']['visual_lines']=[
        dict(text=first,page_id='p1',first_x=100,y=10,
             style_spans=[dict(start=0,end=a-1,style='italic'),dict(start=a-1,end=len(first),style='regular')]),
        dict(text=second,page_id='p1',first_x=100,y=8.8,
             style_spans=[dict(start=0,end=len(second),style='regular')])]
    assert any(n['kind']=='translation' for n in recover_quotations(p,text)['nodes'])
    p['original_structure']['visual_lines'][1]['first_x']=350
    assert recover_quotations(p,text)==p


def test_recovered_definition_rejects_decoding_placeholders():
    from badw_recovered_fragment_integrity import definition_error
    assert definition_error('word UNKNOWN glyph')=='unresolved_source_decoding'
    assert definition_error('word \ufffd')=='unresolved_source_decoding'
