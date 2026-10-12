import copy
import hashlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from badw_contextual_semantics import language_forms, inline_candidates


def projection(kind='html',**structure):
    return dict(source_kind=kind,nodes=[],original_structure=structure)


def test_explicit_labels_exclude_edition_and_german_prose():
    text='skt. yatheṣṭam; skt. 104,7; skt. Optativ; skt. Feronia elephantum'
    forms,markers=language_forms(projection(),text)
    assert [f['literal'] for f in forms]==['yatheṣṭam']
    assert [m['family'] for m in markers]==['explicit_skt_bounded_form','Sanskrit_edition_locator_not_language_form','German_metalinguistic_or_botanical_prose','German_metalinguistic_or_botanical_prose']


def test_explicit_dom_field_preserves_narrow_language_subspan():
    text='Tibetan ≅ luñcate „er rauft“'
    a=text.index('luñcate');b=a+len('luñcate')
    p=projection(text_fragments=[dict(dom_path='/entry/skt[1]',visible=True,visible_text_start=a,visible_text_end=b)])
    before=copy.deepcopy(p)
    forms,_=language_forms(p,text)
    assert [f['literal'] for f in forms]==['luñcate'] and p==before


def test_pdf_mvy_requires_local_lemma_or_equivalence():
    text='Lex. x ≅ eta yūyam „ihr da“ (Mvy 6646)'
    a=text.index('eta');b=a+len('eta yūyam')
    p=projection('pdf',visual_lines=[dict(text=text,style_spans=[dict(style='italic',start=a,end=b)])],candidates=dict(lexical_blocks=[dict(clauses=[dict(start=5,end=len(text))])]))
    forms,_=language_forms(p,text)
    assert [f['literal'] for f in forms]==['eta yūyam']
    p['original_structure']['candidates']['lexical_blocks']=[]
    assert [f['literal'] for f in language_forms(p,text)[0]]==['eta yūyam']
    text2=text.replace('≅',';')
    p['original_structure']['visual_lines'][0]['text']=text2
    assert language_forms(p,text2)[0]==[]


def resolver():
    return SimpleNamespace(publication_patterns=[('Maurer 2001',[],re.compile(r'\bMaurer 2001\b'))],resolver=SimpleNamespace(patterns=[('PW',re.compile(r'\bPW\b'))]))


def test_inline_grammar_requires_registry_locator_and_local_syntax():
    text='vgl. PW 5.3; (Maurer 2001: 12); PW 5.3; (1653–1705); (Unknown 2001)'
    found=inline_candidates(projection(),text,resolver())
    assert [f['literal'] for f in found]==['PW 5.3','Maurer 2001: 12']


def test_existing_envelope_prevents_duplicate_extraction():
    text='(vgl. PW 5.3)'
    p=projection();p['nodes']=[dict(kind='citation',start=0,end=len(text))]
    assert inline_candidates(p,text,resolver())==[]


def test_registered_author_unknown_edition_is_extracted_without_identity_claim():
    found=inline_candidates(projection(),'vgl. Maurer 2009: 12',resolver())
    assert [f['literal'] for f in found]==['Maurer 2009: 12']
    assert all('authority_id' not in f for f in found)


def test_unsupported_inline_citation_does_not_invalidate_existing_pdf_owner():
    from badw_semantic_hierarchy import hierarchy
    text='German definition (PW 1); Maurer 2009: 12'
    a=text.index('(PW');b=text.index(')')+1;c=text.index('Maurer')
    p=projection('pdf');p.update(identity='regression',review_text_sha256=hashlib.sha256(text.encode()).hexdigest())
    p['nodes']=[dict(id='d',kind='definition',start=0,end=len(text)),
        dict(id='old',kind='citation',start=a,end=b)]
    before=hierarchy(p,text)['citation_ownership']
    p['nodes'].append(dict(id='new',kind='citation',start=c,end=len(text)))
    after=hierarchy(p,text)['citation_ownership']
    assert before==after and {r['citation_node_id'] for r in after}=={'old'}


def test_pdf_internal_correction_reference_preserves_terminal_example_owner():
    from badw_semantic_hierarchy import hierarchy
    text='tib (r. x, PW 2) „German gloss“ (PW 1)'
    g=text.index('„');ge=text.index('“')+1;c=text.rindex('(PW')
    p=projection('pdf',candidates=dict(german_quotes=[dict(visual_start=g,visual_end=ge)]))
    p.update(identity='regression',review_text_sha256=hashlib.sha256(text.encode()).hexdigest())
    p['nodes']=[dict(id='e',kind='example',start=0,end=len(text)),
        dict(id='t',kind='tibetan',start=0,end=g-1,parent='e'),
        dict(id='g',kind='translation',start=g,end=ge,parent='e'),
        dict(id='old',kind='citation',start=c,end=len(text),parent='e')]
    before=hierarchy(p,text)['citation_ownership']
    a=text.index('PW 2')
    p['nodes'].append(dict(id='new',kind='citation',start=a,end=a+4,parent='e'))
    assert hierarchy(p,text)['citation_ownership']==before


def test_reviewed_compound_author_precedes_shorter_cue():
    r=resolver()
    r.alias_patterns=[({'alias':'Sørensen / Hazod 2007','authority_id':'joint','layer':'html'},re.compile(r'Sørensen / Hazod 2007'))]
    r.by_id={'joint':{'kind':'publication'}}
    text='vgl. Sørensen / Hazod 2007: vol. 2, p. 675, Anm. 12.'
    found=inline_candidates(projection(),text,r)
    assert [f['literal'] for f in found]==['Sørensen / Hazod 2007: vol. 2, p. 675']
    assert inline_candidates(projection(),'Sørensen / Hazod 2007 ordinary prose',r)==[]


def test_matching_layout_artifact_does_not_rewrite_literal():
    from badw_bibliography import spelling_pattern
    r=resolver()
    r.publication_patterns=[('Pasang 1998',[],re.compile(spelling_pattern('Pasang 1998')))]
    text='(P\u00adasang 1998: 136)'
    found=inline_candidates(projection(),text,r)
    assert [f['literal'] for f in found]==['P\u00adasang 1998: 136']
