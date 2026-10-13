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
    fields=header_fields(p,text)
    assert fields[0]['relation_type']=='has_short_form'
    assert fields[0]['target_span']['literal']=='ba ru'


def pdf_projection(text, lines):
    return dict(identity='pdf', source_kind='pdf',
        review_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        original_structure=dict(visual_lines=lines))


def test_pdf_wrapped_relation_stops_before_german_definition():
    text=' Kurzf. für khams kyi\nrgyal po Kleinkönig, Vasall.'
    p=pdf_projection(text,[dict(text=' Kurzf. für khams kyi',page_id='p1',printed_page=1,first_x=100,y=10,style_spans=[dict(style='italic',start=12,end=21)]),
        dict(text='rgyal po Kleinkönig, Vasall.',page_id='p1',printed_page=1,first_x=98,y=8.8,style_spans=[dict(style='italic',start=0,end=8)])])
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


def test_down_arrow_relation_keeps_homonym_separate():
    text='pf. zu ↓1’bab'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,9),
        (ROOT+'/span[2]/a[1]/text()[1]',9,len(text))])
    relation=[f for f in header_fields(p,text) if f['header_kind']=='header_relation'][0]
    assert relation['target_span']['literal']=='’bab'
    assert relation['target_homonym']=='1'
    assert relation['literal']==text


def test_shared_relation_marker_governs_explicit_link_list_only():
    text='pf. und fut. zu ↓first, ↓second; prose ↓wrong'
    a=text.index('first');b=text.index('second');c=text.index('wrong')
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,a),
        (ROOT+'/span[2]/a[1]/text()[1]',a,a+5),
        (ROOT+'/span[2]/text()[2]',a+5,b),
        (ROOT+'/span[2]/a[2]/text()[1]',b,b+6),
        (ROOT+'/span[2]/text()[3]',b+6,c),
        (ROOT+'/span[2]/a[3]/text()[1]',c,len(text))])
    fields=header_fields(p,text)
    assert [f['target_span']['literal'] for f in fields]==['first','second']
    assert all(f['relation_types']==['perfect_of','future_of'] for f in fields)
    assert len({f['list_id'] for f in fields})==1
    assert fields[1]['marker_span']==fields[0]['marker_span']


def test_bzw_alias_list_preserves_multiword_members():
    text='auch first form, second form bzw. third form'
    a=text.index('first');b=text.index('second');c=text.index('third')
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,a),
        (ROOT+'/span[2]/tib[1]/text()[1]',a,b-2),
        (ROOT+'/span[2]/text()[2]',b-2,b),
        (ROOT+'/span[2]/tib[2]/text()[1]',b,c-6),
        (ROOT+'/span[2]/text()[3]',c-6,c),
        (ROOT+'/span[2]/tib[3]/text()[1]',c,len(text))])
    fields=header_fields(p,text)
    assert [f['form_span']['literal'] for f in fields]==['first form','second form','third form']
    assert len({f['list_id'] for f in fields})==1


def test_pdf_list_accepts_roman_separator_but_not_roman_prose():
    text='auch ka, ga bzw. kha German explanation'
    p=pdf_projection(text,[dict(text=text,style_spans=[
        dict(style='italic',start=5,end=7),dict(style='italic',start=9,end=11),
        dict(style='italic',start=text.index('kha'),end=text.index('kha')+3),
        dict(style='italic',start=text.index('explanation'),end=len(text))])])
    assert [f['form_span']['literal'] for f in header_fields(p,text)]==['ka','ga','kha']


def test_postposition_is_complete_heading_label():
    text='postpos.'
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,len(text))])
    assert header_fields(p,text)[0]['header_kind']=='grammatical_label'


def test_shared_tense_without_zu_requires_arrow():
    for label in ['pf. und imp. ↓', 'pf. und imp. ']:
        text=label+'target'
        p=projection(text,[(ROOT+'/span[2]/text()[1]',0,len(label)),
            (ROOT+'/span[2]/tib[1]/text()[1]',len(label),len(text))])
        relations=[f for f in header_fields(p,text) if f['header_kind']=='header_relation']
        if '↓' in label:
            assert relations[0]['relation_types']==['perfect_of','imperative_of']
        else:
            assert not relations


def test_whole_multiword_relation_targets_in_one_field():
    text='Kurzf. für bla ma und mchod gnas'
    a=text.index('bla ma')
    p=projection(text,[(ROOT+'/span[2]/text()[1]',0,a),
        (ROOT+'/span[2]/tib[1]/text()[1]',a,len(text))])
    fields=header_fields(p,text)
    assert [f['target_span']['literal'] for f in fields]==['bla ma','mchod gnas']
    assert len({f['list_id'] for f in fields})==1


def test_historical_form_and_comparison_have_distinct_relations():
    for label,kind in [('alttib. ', 'has_historical_form'),
                       ('alttib. für ', 'historical_form_of'),
                       ('vgl. ↑', 'compare_with'),
                       ('Verbalnomen zu ', 'verbal_noun_of')]:
        text=label+'whole target'
        p=projection(text,[(ROOT+'/span[2]/text()[1]',0,len(label)),
            (ROOT+'/span[2]/tib[1]/text()[1]',len(label),len(text))])
        fields=header_fields(p,text)
        assert fields[0]['relation_type']==kind
        assert fields[0]['target_span']['literal']=='whole target'


def test_pdf_wrapping_rejects_column_jump():
    from badw_header_structure import contiguous_pdf_lines
    rows=[dict(page_id='p',printed_page=1,first_x=100,y=10),
          dict(page_id='p',printed_page=1,first_x=300,y=8.8)]
    assert not contiguous_pdf_lines(rows,0,1)
    rows[1]['first_x']=98
    assert contiguous_pdf_lines(rows,0,1)
    rows[1]['page_id']='next'
    assert not contiguous_pdf_lines(rows,0,1)


def test_pdf_bare_paradigm_is_not_a_relation():
    text='pf. form Erklärung'
    p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=4,end=8)])])
    fields=header_fields(p,text)
    assert len(fields)==1
    assert fields[0]['header_kind']=='verb_form'
    assert fields[0]['form_span']['literal']=='form'


def test_pdf_repeated_auch_group_and_regular_prose_stop():
    text='auch kha, auch ga explanation auch wrong'
    p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=5,end=8),dict(style='italic',start=15,end=17),dict(style='italic',start=35,end=40)])])
    fields=header_fields(p,text)
    assert [f['form_span']['literal'] for f in fields]==['kha','ga']
    assert len({f['list_id'] for f in fields})==1


def test_pdf_numbered_initial_relation_and_shared_tense():
    for label,types in [('. 1. pf. zu ',['perfect_of']),('pf. bzw. imp. zu ',['perfect_of','imperative_of']),('imp. von ',['imperative_of'])]:
        text=label+'whole form explanation'
        p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=len(label),end=len(label)+10)])])
        fields=header_fields(p,text)
        assert fields[0]['target_span']['literal']=='whole form'
        assert fields[0]['relation_types']==types


def test_pdf_bare_shared_tense_is_paradigm_not_relation():
    text='fut. und pf. form explanation'
    p=pdf_projection(text,[dict(text=text,style_spans=[dict(style='italic',start=13,end=17)])])
    fields=header_fields(p,text)
    assert fields[0]['header_kind']=='verb_form'
    assert fields[0]['form_span']['literal']=='form'
