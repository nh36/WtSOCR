import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_pdf_mixed_clauses import recover_mixed_clauses


def fixture(form='~ pa', gloss='Befreiung.', prefix='Bedeutung; ', occupied=()):
    text=prefix+form+' '+gloss
    a=len(prefix);b=a+len(form)
    p=dict(identity='pdf:mixed',source_kind='pdf',nodes=[dict(id='source',kind='source_division',start=0,end=len(text),parent=None),*occupied],original_structure=dict(visual_lines=[dict(text=text,page_id='p',first_x=100,y=10,style_spans=[dict(start=0,end=a,style='regular',font_id='roman'),dict(start=a,end=b,style='italic',font='italic'),dict(start=b,end=len(text),style='regular',font_id='roman')])]))
    return text,p


def test_semicolon_form_gloss_has_exact_boundaries_and_immutable_evidence():
    text,p=fixture(gloss='Befreiung; folgende Konstruktion.')
    before=copy.deepcopy(p)
    r=recover_mixed_clauses(p,text)
    assert p==before
    n=r['nodes'][-1]
    assert text[n['start']:n['end']]=='Befreiung'
    assert n['parent']=='source'
    assert n['source_evidence']['form_span']['literal']=='~ pa'
    assert n['structural_recovery']['role']=='semicolon_lexical_form_gloss'
    assert recover_mixed_clauses(r,text)==r


def test_ordinary_italic_examples_and_unfinished_glosses_are_not_definitions():
    for kwargs in (dict(form='bod skad'),dict(prefix='Bedeutung. '),dict(gloss='eine Eingabe vorbringen, ein'),dict(gloss='synon.'),dict(gloss='vgl. anderer Ausdruck')):
        text,p=fixture(**kwargs)
        assert recover_mixed_clauses(p,text)==p


def test_existing_semantic_passages_cannot_be_reinterpreted():
    text,p=fixture()
    a=text.index('Befreiung')
    for kind in ('example','lex_item','citation','language_span'):
        q=copy.deepcopy(p)
        q['nodes'].append(dict(id='existing',kind=kind,start=a,end=len(text),parent='source'))
        assert recover_mixed_clauses(q,text)==q


def test_continuation_requires_connective_font_and_column_continuity():
    text='abhängig von\nder Handlung.'
    p=dict(identity='pdf:continued',source_kind='pdf',nodes=[dict(id='source',kind='source_division',start=0,end=len(text),parent=None),dict(id='def',kind='definition',start=0,end=12,parent='source')],original_structure=dict(visual_lines=[dict(text='abhängig von',page_id='p',first_x=100,y=10,style_spans=[dict(start=0,end=12,style='regular',font_id='roman')]),dict(text='der Handlung.',page_id='p',first_x=100,y=8.8,style_spans=[dict(start=0,end=13,style='regular',font_id='roman')])]))
    r=recover_mixed_clauses(p,text)
    assert r['nodes'][-1]['structural_recovery']['continuation_of']==['def']
    assert text[r['nodes'][-1]['start']:r['nodes'][-1]['end']]=='der Handlung.'
    q=copy.deepcopy(p);q['original_structure']['visual_lines'][1]['first_x']=350
    assert recover_mixed_clauses(q,text)==q
    q=copy.deepcopy(p);q['original_structure']['visual_lines'][1]['style_spans'][0]['font_id']='other'
    assert recover_mixed_clauses(q,text)==q

    q=copy.deepcopy(p);q['original_structure']['visual_lines'][0]['style_spans'][0].pop('font_id')
    assert recover_mixed_clauses(q,text)==q
