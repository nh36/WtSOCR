import hashlib
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_header_structure import header_fields

ROOT='/document[1]/div[1]'
def projection(text,leaves):
    return dict(identity='entry',review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),source_kind='html',original_structure=dict(lemma_field=dict(locator=dict(dom_path=ROOT+'/span[1]/span[2]')),text_fragments=[dict(dom_path=path,source_text=text[a:b],visible_text_start=a,visible_text_end=b) for path,a,b in leaves]))

def test_heading_alias_does_not_capture_definition_auch():
    text='lemma auch form auch wrong'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',6,11),(ROOT+'/span[2]/tib[1]/text()[1]',11,15),('/document[1]/div[2]/tib[1]/text()[1]',21,26)])
    fields=header_fields(p,text)
    assert len(fields)==1 and fields[0]['literal']=='auch form'
    assert fields[0]['form_span']['literal']=='form'

def test_unlabelled_heading_form_not_invented():
    text='lemma form'
    p=projection(text,[(ROOT+'/span[2]/tib[1]/text()[1]',6,10)])
    assert header_fields(p,text)==[]

def test_grammar_needs_complete_leaf_and_heading_ancestry():
    text='pf. pf. prose 2'
    p=projection(text,[(ROOT+'/span[2]/span[1]/text()[1]',0,3),(ROOT+'/span[2]/text()[1]',4,13),(ROOT+'/span[1]/sup[1]/text()[1]',14,15)])
    fields=header_fields(p,text)
    assert [f['header_kind'] for f in fields]==['grammatical_label','homonym_marker']

def test_pdf_lemma_does_not_reconstruct_missing_heading():
    p=projection('auch form',[]);p['source_kind']='pdf'
    assert header_fields(p,'auch form')==[]

def test_alias_list_across_fields_and_within_field():
    text='auch ba glaṅ, ban klaṅ, ban glaṅ, ban laṅ'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,5),
        (ROOT+'/span[2]/tib[1]/text()[1]',5,12),
        (ROOT+'/span[2]/text()[2]',12,14),
        (ROOT+'/span[2]/tib[2]/text()[1]',14,len(text))])
    fields=header_fields(p,text)
    assert [f['form_span']['literal'] for f in fields]==['ba glaṅ','ban klaṅ','ban glaṅ','ban laṅ']
    assert len({f['list_id'] for f in fields})==1
    assert all(f['marker_span']['literal']=='auch' for f in fields)

def test_alias_list_stops_at_qualifier():
    text='auch form; prose wrong'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,5),
        (ROOT+'/span[2]/tib[1]/text()[1]',5,9),
        (ROOT+'/span[2]/text()[2]',9,17),
        (ROOT+'/span[2]/tib[2]/text()[1]',17,22)])
    assert [f['form_span']['literal'] for f in header_fields(p,text)]==['form']

def test_explicit_relation_across_markup():
    text='Kurzf. für ↑target'
    p=projection(text,[(ROOT+'/span[2]/span[1]/text()[1]',0,6),
        (ROOT+'/span[2]/text()[1]',6,11),
        (ROOT+'/span[2]/span[2]/text()[1]',11,12),
        (ROOT+'/span[2]/span[2]/a[1]/text()[1]',12,18)])
    # Link target is nested in the arrow wrapper; its connective lives in
    # the outer heading group, as in the actual WTS heading.
    fields=header_fields(p,text)
    assert len(fields)==1
    assert fields[0]['relation_type']=='short_form_of'
    assert fields[0]['target_span']['literal']=='target'

def test_nested_tibetan_markup_keeps_one_complete_alias():
    text='auch bag gsar ma'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,5),
        (ROOT+'/span[2]/tib[1]/span[1]/text()[1]',5,13),
        (ROOT+'/span[2]/tib[1]/text()[1]',13,16)])
    assert [f['form_span']['literal'] for f in header_fields(p,text)]==['bag gsar ma']

def test_short_form_without_connective_is_not_reversed():
    text='Kurzf. ba ru'
    p=projection(text,[(ROOT+'/span[2]/span[1]/text()[1]',0,6),
        (ROOT+'/span[2]/text()[1]',6,7),
        (ROOT+'/span[2]/tib[1]/text()[1]',7,12)])
    assert header_fields(p,text)==[]


def pdf_projection(text, lines):
    return dict(identity='pdf', source_kind='pdf',
        review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        original_structure=dict(visual_lines=lines))


def test_pdf_wrapped_relation_stops_before_german_definition():
    text=' Kurzf. für khams kyi\nrgyal po Kleinkönig, Vasall.'
    p=pdf_projection(text,[dict(text=' Kurzf. für khams kyi',style_spans=[dict(style='italic',start=12,end=21)]),
        dict(text='rgyal po Kleinkönig, Vasall.',style_spans=[dict(style='italic',start=0,end=8)])])
    fields=header_fields(p,text)
    assert len(fields)==1
    assert fields[0]['target_span']['literal']=='khams kyi\nrgyal po'
    assert fields[0]['relation_type']=='short_form_of'
    assert 'Kleinkönig' not in fields[0]['literal']


def test_pdf_relation_requires_typography_and_initial_position():
    for text in ['Kurzf. für target','prose Kurzf. für target']:
        p=pdf_projection(text,[dict(text=text,style_spans=[])])
        assert header_fields(p,text)==[]
    text='prose Kurzf. für target'
    p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=16,end=22)])])
    assert header_fields(p,text)==[]


def test_pdf_alias_list_requires_explicit_initial_marker():
    text='auch ka, ga definition'
    p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=5,end=11)])])
    fields=header_fields(p,text)
    assert [f['form_span']['literal'] for f in fields]==['ka','ga']
    assert all('definition' not in f['literal'] for f in fields)
