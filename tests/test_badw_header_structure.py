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
