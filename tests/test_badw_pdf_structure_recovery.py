import copy
import gzip
import json
import hashlib
from pathlib import Path
import sys
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


def test_frozen_quotation_role_occurrences_recover_only_source_bounded_examples():
    """Replay the seven cached observations that exposed the role-gate bug."""
    fixture=Path('data/badw_forensic_structure/quotation_role_regression_sources.json.gz')
    cases=json.load(gzip.open(fixture,'rt',encoding='utf-8'))['cases']
    assert {str(c['suffix']) for c in cases}=={'1780','849','707','1482','44','1490','380'}
    expected={'1780','707','1482','44','1490','380'}
    for case in cases:
        text=case['source_text']; p=case['projection']
        assert hashlib.sha256(text.encode()).hexdigest()==case['source_text_sha256']
        assert p['identity']==case['identity']
        citation=next(n for n in p['nodes'] if n['kind']=='citation'
                      and (n['start'],n['end'])==tuple(case['citation_span']))
        assert text[citation['start']:citation['end']]==case['citation_literal']
        recovered=recover_quotations(p,text)
        examples=[n for n in recovered['nodes'] if n['kind']=='example'
                  and n.get('structural_recovery',{}).get('rule')=='pdf-bounded-quotation-v1']
        if str(case['suffix']) not in expected:
            # 849 is a complete form, not a tilde substitution. This
            # production must not claim it merely because a quotation follows.
            assert not examples
            assert citation.get('parent')==next(n for n in p['nodes'] if n['id']==citation['id']).get('parent')
            continue
        assert len(examples)==1, case['suffix']
        example=examples[0]
        assert example['end']==citation['end']
        assert text[example['start']:example['end']].endswith(case['citation_literal'])
        updated_citation=next(n for n in recovered['nodes'] if n['id']==citation['id'])
        assert updated_citation['parent']==example['id']
        translation=next(n for n in recovered['nodes'] if n['kind']=='translation'
                         and n.get('parent')==example['id'])
        assert text[translation['start']:translation['end']].startswith('„')
        assert text[translation['start']:translation['end']].endswith('“')
        assert translation['end']<=citation['start']
        # The reconstructed example may not cross any pre-existing semantic
        # component other than its containing sense/source division.
        for node in p['nodes']:
            if node['kind'] not in ('source_division','sense','citation'):
                assert not (node['start']<example['end'] and example['start']<node['end']), case['suffix']
        from badw_semantic_hierarchy import hierarchy
        semantic=hierarchy(recovered,text)
        ownership=next((o for o in semantic['citation_ownership']
                        if o['citation_node_id']==citation['id']),None)
        assert (ownership is not None)==(str(case['suffix']) in expected),case['suffix']
        if ownership:
            assert ownership['evidence_class']=='PDF_example_quotation'
            assert ownership['passage_id']
            assert ownership['sense_node_id'] is None or any(
                n['id']==ownership['sense_node_id'] and n['kind']=='sense'
                for n in recovered['nodes'])


def test_bracketed_initial_recovery_requires_complete_token_boundary():
    # Multiple glyph runs are legitimate, but a bracket fragment embedded
    # in preceding prose and an unmatched bracket are not complete forms.
    text='[l]ab gleṅ ~ „eine Form“ (Dagy).'
    a=text.index('„'); c=text.index('(Dagy)')
    p=dict(identity='pdf:bracket-runs',source_kind='pdf',nodes=[
        dict(id='source',kind='source_division',start=0,end=len(text),parent=None),
        dict(id='cite',kind='citation',start=c,end=c+6,parent='source')],
        original_structure=dict(visual_lines=[dict(text=text,page_id='p1',first_x=100,y=10,
            style_spans=[dict(start=0,end=1,style='regular'),dict(start=1,end=2,style='italic'),
                         dict(start=2,end=3,style='regular'),dict(start=3,end=7,style='italic'),
                         dict(start=7,end=a-1,style='italic'),dict(start=a-1,end=len(text),style='regular')])]))
    r=recover_quotations(p,text)
    ex=next(n for n in r['nodes'] if n['kind']=='example')
    assert text[ex['start']:ex['start']+5]=='[l]ab'
    for bad in ('prefix[l]ab gleṅ ~ „eine Form“ (Dagy).',
                '[l ab gleṅ ~ „eine Form“ (Dagy).'):
        t=bad; qa=t.index('„'); qc=t.index('(Dagy)')
        q=dict(identity='pdf:bad-bracket',source_kind='pdf',nodes=[
            dict(id='source',kind='source_division',start=0,end=len(t),parent=None),
            dict(id='cite',kind='citation',start=qc,end=qc+6,parent='source')],
            original_structure=dict(visual_lines=[dict(text=t,page_id='p1',first_x=100,y=10,
                style_spans=[dict(start=0,end=qa-1,style='italic'),dict(start=qa-1,end=len(t),style='regular')])]))
        assert recover_quotations(q,t)==q


def test_independent_facsimile_panel_distinguishes_attestation_from_definition(monkeypatch, tmp_path):
    panel=json.load(gzip.open(
        'data/badw_forensic_structure/quotation_role_independent_panel.json.gz',
        'rt',encoding='utf-8'))
    assert {c['label'] for c in panel['cases']}=={
        'textual_attestation_positive','editorial_quoted_definition_negative',
        'previously_facsimile_verified_positive_control'}
    positive=next(c for c in panel['cases'] if c['label']=='textual_attestation_positive')
    negative=next(c for c in panel['cases'] if c['label']=='editorial_quoted_definition_negative')
    for case in panel['cases']:
        assert hashlib.sha256(case['source_text'].encode()).hexdigest()==case['source_text_sha256']
        a,b=case['source_span']
        assert case['source_text'][a:b]==case['literal']
        assert case['printed_page'] and case['facsimile_pdf_sha256']
    assert 'gto bcos ~' in positive['literal'] and '(Gesar 175, 23)' in positive['literal']
    assert 'Bez. für etwas Nutz-' in negative['literal'] and '(S\nTEIN 1956: 361)' in negative['literal']
    # The source positive already has an independently bounded example;
    # its mixed italic/Roman German quote remains a translation child.
    # Keep this test portable: its only physical-layout dependency is a
    # narrowly scoped, tracked copy of the exact hash-verified line geometry.
    # Production passage_layout/page_runs still require the PDF and canonical
    # objects; this test exercises the semantic result against frozen evidence.
    geometry=json.loads(Path(__file__).with_name('fixtures').joinpath(
        'badw_pdf_attestation_positive_geometry.json').read_text(encoding='utf-8'))
    source=positive['projection']['source']['source_objects'][0]
    assert geometry['source']['identity']==positive['identity']
    assert geometry['source']['source_text_sha256']==positive['source_text_sha256']
    assert geometry['source']['facsimile_pdf_sha256']==positive['facsimile_pdf_sha256']
    assert geometry['source']['canonical_object_sha256']==source['canonical_object_sha256']
    assert geometry['source']['source_span']==positive['source_span']
    assert geometry['source']['literal']==positive['literal']
    observed=positive['projection']['original_structure']['visual_lines']
    assert [(x['line_index'],x['page_id'],x['run_start'],x['run_end_exclusive'],x['text'])
            for x in observed]==[(x['line_index'],x['page_id'],x['run_start'],
                                 x['run_end_exclusive'],x['text'])
                                for x in geometry['visual_lines']]
    # Prove the semantic test cannot accidentally fall back to a developer's
    # ignored cache. A different projection or source object fails closed.
    missing=tmp_path/'absent-canonical-cache'
    monkeypatch.setattr('badw_assertion_layout.CANON',missing/'canonical_v2')
    monkeypatch.setattr('badw_assertion_layout.CACHE',missing/'pdf-cache')
    def portable_lines(projection):
        candidate=projection['source']['source_objects'][0]
        assert projection['identity']==geometry['source']['identity']
        assert candidate['canonical_object_sha256']==geometry['source']['canonical_object_sha256']
        assert candidate['pdf_sha256']==geometry['source']['facsimile_pdf_sha256']
        assert [(x['line_index'],x['page_id'],x['run_start'],x['run_end_exclusive'],x['text'])
                for x in projection['original_structure']['visual_lines']]==[
                    (x['line_index'],x['page_id'],x['run_start'],x['run_end_exclusive'],x['text'])
                    for x in geometry['visual_lines']]
        return geometry['physical_lines']
    monkeypatch.setattr('badw_assertion_layout.physical_lines',portable_lines)
    assert not missing.exists()
    recovered=recover(positive['projection'],positive['source_text'])
    from badw_semantic_hierarchy import hierarchy
    semantic=hierarchy(recovered,positive['source_text'])
    citation=next(n for n in recovered['nodes'] if n['kind']=='citation'
                  and n['start']>=positive['source_span'][0]
                  and n['end']<=positive['source_span'][1])
    owner=next(o for o in semantic['citation_ownership']
               if o['citation_node_id']==citation['id'])
    assert owner['evidence_class']=='PDF_example_quotation'
    translations=[n for n in recovered['nodes'] if n['kind']=='translation'
                  and 'gto[-Rituale wie]' in positive['source_text'][n['start']:n['end']]]
    assert len(translations)==1
    assert translations[0]['start']>=positive['source_span'][0]
    assert translations[0]['end']<citation['start']
    # Use the independently captured full observation for the negative too;
    # the existing adjacent attestation is a hard semantic boundary.
    negative_projection=negative['projection']
    before=copy.deepcopy(negative_projection['nodes'])
    result=recover_quotations(negative_projection,negative['source_text'])
    assert result['nodes']==before


def test_existing_facsimile_positive_controls_keep_example_translation_and_citation():
    panel=json.load(gzip.open(
        'data/badw_forensic_structure/quotation_role_independent_panel.json.gz',
        'rt',encoding='utf-8'))
    controls=[c for c in panel['cases']
              if c['label']=='previously_facsimile_verified_positive_control']
    assert len(controls)==3
    from badw_semantic_hierarchy import hierarchy
    for case in controls:
        text=case['source_text']; a,b=case['source_span']
        assert hashlib.sha256(text.encode()).hexdigest()==case['source_text_sha256']
        assert text[a:b]==case['literal']
        cite=next(n for n in case['projection']['nodes'] if n['kind']=='citation'
                  and (n['start'],n['end'])==tuple(case['citation_span']))
        assert text[cite['start']:cite['end']]==case['citation_literal']
        recovered=recover(case['projection'],text)
        semantic=hierarchy(recovered,text)
        owner=next(o for o in semantic['citation_ownership']
                   if o['citation_node_id']==cite['id'])
        examples=[n for n in recovered['nodes'] if n['kind']=='example'
                  and n['start']<=cite['start']<n['end']]
        assert len(examples)==1
        example=examples[0]
        assert example['kind']=='example'
        translation=next(n for n in recovered['nodes'] if n['kind']=='translation'
                         and n.get('parent')==example['id']
                         and n['start']>=a and n['end']<=cite['start'])
        assert text[translation['start']:translation['end']].startswith('„')
        assert text[translation['start']:translation['end']].endswith('“')


def test_internal_italics_require_source_language_token_evidence():
    from badw_pdf_quotation_recovery import translation_italics_are_lexical
    text='gto „eine Lampe im gto-Rituale wie Wasser“'
    a=text.index('„'); b=text.index('“')+1
    external=dict(start=0,end=3,style='italic')
    internal=dict(start=text.rindex('gto'),end=text.rindex('gto')+3,style='italic')
    assert translation_italics_are_lexical([internal],[external,internal],text,a,b)
    for token in ('schön','Lampe'):
        t=f'„eine {token} wie Wasser“'; x=t.index('„'); y=t.index('“')+1
        italic=[dict(start=t.index(token),end=t.index(token)+len(token),style='italic')]
        assert not translation_italics_are_lexical(italic,italic,t,x,y)


def test_recovered_definition_rejects_decoding_placeholders():
    from badw_recovered_fragment_integrity import definition_error
    assert definition_error('word UNKNOWN glyph')=='unresolved_source_decoding'
    assert definition_error('word \ufffd')=='unresolved_source_decoding'
