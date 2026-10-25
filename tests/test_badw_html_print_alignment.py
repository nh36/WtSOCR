"""Independent controls for page certificates, not tests of lexical similarity."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import badw_html_print_alignment as a


def fixture_rows():
    return {('wts_1_34',41,20):dict(line_text='test 2 Eine Heilpflanze',zone='headword_line')}

@pytest.fixture
def evidence():
    body = dict(inspection_id='html:one', source_kind='html', source_url='https://wts-digital.badw.de/lemma/test/2',
                sources=[dict(sha256='a'*64)], headword=dict(loc='test'), homonym=2,
                components=[dict(type='definition', source_form='Eine bestimmte Heilpflanze.')])
    anchor = dict(anchor_id='v:41:20', volume='wts_1_34', start_page=41, start_line=20)
    assertion = dict(source_id='html:one', anchor=anchor['anchor_id'], heading_position='left column',
                     printed_homonym=2, definition_evidence='bestimmte Heilpflanze', scan_review='Printed numeral 2 and plant definition, not numeral 1 meaning a vessel.',
                     html_sha256='a'*64, anchor_sha256=a.object_digest(anchor), definition_component_sha256=a.object_digest(body['components'][0]))
    edge = dict(source_id='html:one', local_anchor_id=anchor['anchor_id'])
    page = dict(key='v1-p16', family='wts_1_34', source='WtS_1-34', source_sha256='b'*64,
                physical_page=41, volume=1, printed_page=16, side='left', crop=[0,0,438,640],
                geometry_review='Noncentral empty gutter checked', page_evidence='Printed folio 16 visible', accepted=[assertion])
    assertion['print_observation'] = dict(heading='test (printed spelling)', homonym=2,
        evidence='Eine Heilpflanze; printed numeral 2.', identity_context='Numeral 1 above describes a vessel; this heading begins a separate paragraph.',
        heading_anchor=anchor['anchor_id'], evidence_anchor=anchor['anchor_id'], column='left column',
        page_sha256=a.object_digest({k:page[k] for k in ('source','source_sha256','physical_page','volume','printed_page','side','crop')}),
        verification='visual transcription; not machine-verified')
    assertion['editorial'] = dict(source_url=body['source_url'], headword='test', homonym=2)
    rows = {('wts_1_34',41,20):dict(line_text='test 2 Eine Heilpflanze', zone='headword_line')}
    assertion['article_boundary'] = dict(classification='reviewed lexical article start', heading_lines=[20],
        evidence_lines=[20], excluded_lines=[1], qa_rows_sha256=a.object_digest(list(rows.values())),
        review_reason='Printed numeral distinguishes vessel above from plant here.')
    return body, anchor, assertion, [edge], dict(pages=[page])


def test_expansion_identity_pagination_and_reproducibility(evidence):
    body, anchor, assertion, edges, cert = evidence
    args = (cert, {'html:one':body}, {anchor['anchor_id']:anchor}, edges, {'WtS_1-34':dict(sha256='b'*64)})
    first = a.compile_records(*args, qa_rows=fixture_rows())
    assert first == a.compile_records(*args, qa_rows=fixture_rows())
    assert first['pages']['v1-p16']['physical_page'] == 41
    assert first['pages']['v1-p16']['printed_page'] == 16
    assert first['witnesses'][0]['homonym'] == 2
    # Absent is a distinct assertion, never implicitly numbered 1. Definition
    # identity is still required for the exact editorial witness.
    assertion['printed_homonym'] = None
    assertion['print_observation']['homonym'] = None
    assert a.compile_records(*args, qa_rows=fixture_rows())['witnesses'][0]['evidence']['certificate']['printed_homonym'] is None
    del assertion['printed_homonym']
    with pytest.raises(ValueError, match='explicit'):
        a.compile_records(*args, qa_rows=fixture_rows())


@pytest.mark.parametrize('change, message', [
    ({'heading_position':'running header'}, 'not a heading'),
    ({'heading_position':'continuation'}, 'not a heading'),
    ({'printed_homonym':1}, 'competing'),
    ({'html_sha256':'c'*64}, 'stale'),
    ({'anchor_sha256':'c'*64}, 'stale'),
    ({'definition_component_sha256':'c'*64}, 'stale definition'),
    ({'definition_evidence':'unrelated long definition'}, 'not present'),
    ({'scan_review':''}, 'scan identity'),
])
def test_rejects_false_or_stale_evidence(evidence, change, message):
    body, anchor, assertion, edges, _ = evidence
    assertion.update(change)
    with pytest.raises(ValueError, match=message):
        a.validate_assertion(assertion, body, anchor, edges)


def test_wrong_source_page_duplicate_and_pdf_fail_closed(evidence):
    body, anchor, assertion, edges, cert = evidence
    def compile():
        return a.compile_records(cert, {'html:one':body}, {anchor['anchor_id']:anchor}, edges, {'WtS_1-34':dict(sha256='b'*64)}, qa_rows=fixture_rows())
    cert['pages'][0]['source_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='stale source'): compile()
    cert['pages'][0]['source_sha256'] = 'b'*64
    cert['pages'][0]['physical_page'] = 42
    with pytest.raises(ValueError, match='physical anchor'): compile()
    cert['pages'][0]['physical_page'] = 41
    body['source_kind'] = 'pdf'
    with pytest.raises(ValueError, match='HTML'): compile()
    body['source_kind'] = 'html'
    cert['pages'][0]['accepted'].append(copy.deepcopy(assertion))
    with pytest.raises(ValueError, match='twice'): compile()


def test_real_batch_is_bounded_explicit_and_contains_negative_controls():
    cert = json.loads(a.CERTIFICATE.read_text())
    generated = json.loads(a.GENERATED.read_text())
    assert generated['certificate_sha256'] == a.object_digest(cert)
    assert cert['inspected_pages'] == 40
    assert len(generated['pages']) == 38
    assert len(generated['witnesses']) == 131
    assert len({(r['source_url'], r['html_sha256']) for r in generated['witnesses']}) == 131
    assert {p['source'] for p in cert['pages']} == {'WtS_1-34','WtS_35-51','WtS_8-b','WtS_9-m'}
    assert all('printed_homonym' in r for p in cert['pages'] for r in p['accepted'])
    assert any('continu' in r['reason'] for r in cert['decisions'])
    assert any('Lexical/edition' in r['reason'] for r in cert['decisions'])
    assert not any(p['printed_page']==360 and p['volume']==5 for p in cert['pages'])


def compile_fixture(evidence):
    body, anchor, _, edges, cert = evidence
    return a.compile_records(cert, {body['inspection_id']:body}, {anchor['anchor_id']:anchor}, edges, {'WtS_1-34':dict(sha256='b'*64)}, qa_rows=fixture_rows())


def test_short_generic_definition_requires_independent_context_not_length(evidence):
    body, _, assertion, _, _ = evidence
    body['components'][0]['source_form'] = 'ein Vogel'
    assertion['definition_evidence'] = 'ein Vogel'
    assertion['definition_component_sha256'] = a.object_digest(body['components'][0])
    assertion['print_observation']['evidence'] = 'ein Vogel, cited in the printed source'
    result = compile_fixture(evidence)
    assert result['witnesses'][0]['printed_heading'] == 'test (printed spelling)'
    assert result['witnesses'][0]['headword'] == 'test'
    assertion['print_observation']['identity_context'] = ''
    with pytest.raises(ValueError, match='identity_context'):
        compile_fixture(evidence)


@pytest.mark.parametrize('field,value,message', [
    ('heading_anchor','neighbour','same inspected entry'),
    ('evidence_anchor','neighbour','same inspected entry'),
    ('column','right column','column'),
    ('homonym',None,'homonym observation'),
    ('heading','','independent printed'),
    ('evidence','','independent printed'),
    ('verification','automatically verified','visual scholarship'),
    ('page_sha256','wrong','folio/geometry'),
])
def test_observation_binding(evidence, field, value, message):
    evidence[2]['print_observation'][field] = value
    with pytest.raises(ValueError, match=message): compile_fixture(evidence)


def test_wrong_family_volume_folio_and_geometry(evidence):
    page = evidence[4]['pages'][0]
    page['family'] = 'wts_9_m'
    with pytest.raises(ValueError, match='scan family'): compile_fixture(evidence)
    page['family'] = 'wts_1_34'
    evidence[1]['volume'] = 'wts_9_m'
    with pytest.raises(ValueError, match='physical anchor'): compile_fixture(evidence)
    evidence[1]['volume'] = 'wts_1_34'
    page['printed_page'] = 17
    with pytest.raises(ValueError, match='folio/geometry'): compile_fixture(evidence)


def test_prior_negative_decision_cannot_be_silently_promoted(evidence):
    decision = dict(source_id='html:one', anchor=evidence[1]['anchor_id'], status='deferred', reason='Competing same-spelling heading')
    evidence[4]['decisions'] = [decision]
    with pytest.raises(ValueError, match='reconsideration'): compile_fixture(evidence)
    evidence[2]['reconsideration'] = dict(decision_sha256=a.object_digest(decision), reason='New independent numeral and citation reviewed')
    assert len(compile_fixture(evidence)['witnesses']) == 1
    decision['reason'] = 'Changed decision'
    with pytest.raises(ValueError, match='reconsideration'): compile_fixture(evidence)


def test_conflicting_same_spelling_heading_reuse_requires_explicit_relation(evidence):
    body, anchor, assertion, edges, cert = evidence
    other = copy.deepcopy(body)
    other.update(inspection_id='html:two', source_url=body['source_url']+'-other')
    second = copy.deepcopy(assertion)
    second['source_id'] = 'html:two'
    second['editorial']['source_url'] = other['source_url']
    cert['pages'][0]['accepted'].append(second)
    edges.append(dict(source_id='html:two', local_anchor_id=anchor['anchor_id']))
    args = (cert, {'html:one':body,'html:two':other}, {anchor['anchor_id']:anchor}, edges, {'WtS_1-34':dict(sha256='b'*64)})
    with pytest.raises(ValueError, match='conflicting reuse'): a.compile_records(*args, qa_rows=fixture_rows())
    relation = dict(source_ids=['html:one','html:two'], reason='Separately reviewed editorial split of one printed article')
    assertion['multi_witness_relationship'] = second['multi_witness_relationship'] = relation
    assert len(a.compile_records(*args, qa_rows=fixture_rows())['witnesses']) == 2
    second['print_observation']['evidence'] = 'An adjacent definition'
    with pytest.raises(ValueError, match='conflicting reuse'): a.compile_records(*args, qa_rows=fixture_rows())


def test_generated_projection_detects_tampering_even_with_updated_content_digest(evidence):
    expanded = compile_fixture(evidence)
    a.validate_expansion(evidence[4], expanded)
    expanded['witnesses'][0]['printed_heading'] = 'HTML restatement'
    with pytest.raises(ValueError, match='content'): a.validate_expansion(evidence[4], expanded)
    expanded['content_sha256'] = a.object_digest({k:v for k,v in expanded.items() if k != 'content_sha256'})
    with pytest.raises(ValueError, match='witness differs'): a.validate_expansion(evidence[4], expanded)


@pytest.mark.parametrize('field,value', [
    ('source_url','https://example.org/other'), ('headword','neighbour'),
    ('homonym',1), ('review_basis','automatic'), ('page','v1-p17'),
    ('html_sha256','f'*64), ('printed_homonym',None),
    ('evidence',{'anchor_sha256':'f'*64}),
])
def test_every_generated_witness_field_is_certificate_bound(evidence, field, value):
    expanded = compile_fixture(evidence)
    expanded['witnesses'][0][field] = value
    expanded['content_sha256'] = a.object_digest({k:v for k,v in expanded.items() if k != 'content_sha256'})
    with pytest.raises(ValueError, match='witness differs'):
        a.validate_expansion(evidence[4], expanded)


@pytest.mark.parametrize('classification', ['running header','continuation','neighbouring compound'])
def test_reviewed_boundary_is_required_not_just_an_existing_anchor(evidence, classification):
    evidence[2]['article_boundary']['classification'] = classification
    with pytest.raises(ValueError, match='article beginning'): compile_fixture(evidence)


def test_article_span_rejects_wrong_heading_and_excluded_neighbour(evidence):
    boundary = evidence[2]['article_boundary']
    boundary['heading_lines'] = [21]
    with pytest.raises(ValueError, match='article beginning'): compile_fixture(evidence)
    boundary['heading_lines'] = [20]
    boundary['evidence_lines'] = [1]
    with pytest.raises(ValueError, match='article beginning'): compile_fixture(evidence)
    boundary['evidence_lines'] = [20]
    boundary['qa_rows_sha256'] = 'f'*64
    with pytest.raises(ValueError, match='stale article-boundary'): compile_fixture(evidence)


def test_reviewed_candidate_anchor_correction_is_explicit_and_edge_bound(evidence):
    assertion, edges = evidence[2], evidence[3]
    edges[0]['local_anchor_id'] = 'v:41:77'
    with pytest.raises(ValueError, match='reviewed anchor correction'): compile_fixture(evidence)
    assertion['candidate_anchor_correction'] = dict(previous_anchor='v:41:77',
        previous_edge_sha256=a.object_digest(edges[0]), reason='77 belongs to neighbouring compound, not heading 20')
    assert len(compile_fixture(evidence)['witnesses']) == 1
    edges[0]['changed'] = True
    with pytest.raises(ValueError, match='reviewed anchor correction'): compile_fixture(evidence)


def test_three_reported_bindings_cannot_return_as_accepted_headings():
    cert = json.loads(a.CERTIFICATE.read_text())
    accepted = {r['anchor']: r for p in cert['pages'] for r in p['accepted']}
    decisions = {r['anchor']: r for r in cert['decisions']}
    for old, true in [('wts_1_34:1090:55',89),('wts_35_51:106:47',59)]:
        assert old not in accepted
        assert decisions[old]['status'] == 'deferred'
        assert decisions[old]['observed_heading_lines'] == [true]
    assert 'wts_8_b:17:77' not in accepted
    corrected = accepted['wts_8_b:17:63']
    assert corrected['candidate_anchor_correction']['previous_anchor'] == 'wts_8_b:17:77'
    assert corrected['article_boundary']['heading_lines'] == [63]
    assert set(corrected['article_boundary']['evidence_lines']) == {63,64,65,66}
    assert {77,78} <= set(corrected['article_boundary']['excluded_lines'])
    for old, true in [(55,89),(47,59),(77,63)]:
        assertion = dict(article_boundary=dict(classification='reviewed lexical article start',
            heading_lines=[true],evidence_lines=[true],excluded_lines=[old]))
        with pytest.raises(ValueError, match='article beginning'):
            a.validate_boundary(assertion,dict(start_line=old),{})


def test_coverage_requires_current_html_checksum_and_exact_url(evidence):
    body = evidence[0]
    accepted = {(body['source_url'],body['sources'][0]['sha256'])}
    assert a.inventory({'html:one':body},{},[],accepted)['categories'] == {'reviewed_exact_heading_page':1}
    body['sources'][0]['sha256'] = 'c'*64
    assert a.inventory({'html:one':body},{},[],accepted)['categories'] == {'no_usable_candidate':1}


def test_queue_exclusion_requires_current_checksum_for_baseline_and_generated(evidence):
    body, anchor, assertion, edges, cert = evidence
    edges[0].update(latin_exact=True,tibetan_exact=True)
    baseline = dict(witnesses=[dict(source_url=body['source_url'],html_sha256='a'*64)],pages={})
    empty_cert = dict(pages=[],inputs={})
    assert a.review_queue(empty_cert,baseline,{'html:one':body},{anchor['anchor_id']:anchor},edges)['candidates'] == 0
    body['sources'][0]['sha256'] = 'c'*64
    assert a.review_queue(empty_cert,baseline,{'html:one':body},{anchor['anchor_id']:anchor},edges)['candidates'] == 1
    # A stale generated acceptance must not exclude the witness on another candidate page.
    cert['inputs'] = {}
    other = dict(anchor_id='v:42:20',volume='wts_1_34',start_page=42,start_line=20)
    edges[0]['local_anchor_id'] = other['anchor_id']
    assert a.review_queue(cert,dict(witnesses=[],pages={}),{'html:one':body},{other['anchor_id']:other},edges)['candidates'] == 1


def test_review_queue_is_reproducible_bounded_and_never_accepts_candidates():
    bodies, anchors, edges = {}, {}, []
    for family in a.FAMILIES:
        for physical in range(200, 220):
            sid = aid = f'{family}:{physical}'
            bodies[sid] = dict(source_url='https://example.org/'+sid, sources=[dict(sha256='a'*64)],
                headword=dict(loc='candidate'), homonym=2 if physical % 2 else None,
                components=[dict(type='definition', source_form='ein Vogel')])
            anchors[aid] = dict(volume=family, start_page=physical, start_line=1)
            edges.append(dict(source_id=sid, local_anchor_id=aid, latin_exact=True, tibetan_exact=True))
    cert = dict(pages=[], inputs={})
    baseline = dict(witnesses=[], pages={'occupied':dict(source='WtS_1-34',physical_page=200)})
    q = a.review_queue(cert, baseline, bodies, anchors, edges)
    assert q == a.review_queue(cert, baseline, bodies, anchors, edges)
    assert q['physical_pages'] == 48
    assert len({(p['family'],p['physical_page']) for p in q['pages']}) == 48
    assert not any(p['family']=='wts_1_34' and p['physical_page']==200 for p in q['pages'])
    assert all(p['printed_folio'] is None and p['geometry'] is None for p in q['pages'])
    assert {p['selection_reason'] for p in q['pages']} == {
        'density and independent-review potential', 'competing/numbered homonym control', 'sparse-definition control'}
    assert all(p['status']=='unreviewed candidate page' and 'accepted' not in p for p in q['pages'])


def test_committed_next_queue_contains_no_new_assignments():
    queue = json.loads((a.ROOT/'data/badw_html_print_review_queue.json').read_text())
    assert queue['certificate_sha256'] == a.object_digest(json.loads(a.CERTIFICATE.read_text()))
    assert queue['physical_pages'] == 48
    assert queue['candidates'] == 683
    assert all(p['printed_volume'] is None and p['printed_folio'] is None and p['geometry'] is None for p in queue['pages'])
