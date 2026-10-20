"""Member resolution survives generation, display segmentation and SQL queries."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_dictionary_prototype import view
from badw_dictionary_entry_view import entry_view
from badw_semantic_store import create, ingest
from test_badw_cross_reference_resolution import entry, plural_fixture
from resolve_badw_cross_references import EntryIndex


def inspected_fixture(lemmas=('ka', 'kha')):
    occurrence, structure, text, binding = plural_fixture('ka, kha')
    candidate = dict(occurrence['source_candidate'], marker='↑')
    structure['candidates'] = dict(cross_references=[candidate])
    projection = dict(contract_version='badw-structural-candidate-projection-v6',
        identity=binding['identity'], source_kind='pdf', source=dict(visual_lines=structure['visual_lines']),
        review_text_sha256=structure['review_text_sha256'], original_structure=structure,
        nodes=[dict(id='xref', kind='cross_reference', start=0, end=len(text)),
               dict(id='citation', kind='citation', start=0, end=1)], edges=[])
    index = EntryIndex([entry(binding['identity'], lemma='source')] +
                       [entry('target:'+str(i), lemma=lemma) for i, lemma in enumerate(lemmas)])
    before = copy.deepcopy(projection)
    inspected = view([projection], index)[0]
    assert projection == before
    return inspected


@pytest.mark.parametrize('lemmas,aggregate,statuses', [
    (('ka', 'kha'), 'complete', ['resolved', 'resolved']),
    (('ka',), 'partial', ['resolved', 'unresolved']),
    ((), 'unresolved', ['unresolved', 'unresolved']),
])
def test_member_pipeline_preserves_parent_citations_and_exact_display(lemmas, aggregate, statuses):
    inspected = inspected_fixture(lemmas)
    result = entry_view(inspected)
    ref, = result['cross_references']
    resolution = inspected['cross_references'][0]['canonical_resolution']
    assert ref['target_members'] == resolution['target_members']
    assert ref['target_members_status'] == aggregate
    assert [m['resolution_status'] for m in ref['target_members']] == statuses
    assert ref['status'] == 'unresolved' and ref['target_entry_id'] is None
    assert ref['target_lexical_entity'] is None
    assert ''.join(s['text'] for s in result['segments']) == inspected['review_text']
    members = [s for s in result['segments'] if 'cross_reference_member' in s]
    assert [s['text'] for s in members] == ['ka', 'kha']
    assert [s['cross_reference_member']['ordinal'] for s in members] == [0, 1]
    without = copy.deepcopy(inspected)
    del without['cross_references'][0]['canonical_resolution']['target_members']
    del without['cross_references'][0]['canonical_resolution']['target_members_status']
    prior = entry_view(without)
    for field in ('components', 'citations', 'semantic_hierarchy', 'relationships', 'senses'):
        assert result[field] == prior[field]


@pytest.mark.parametrize('damage', ['literal', 'span', 'identity', 'hash', 'ordinal', 'parent'])
def test_reader_rejects_detached_members(damage):
    inspected = inspected_fixture()
    resolution = inspected['cross_references'][0]['canonical_resolution']
    member = resolution['target_members'][0]
    if damage == 'literal': member['literal'] = 'other'
    if damage == 'span': member['source_span']['end'] += 1
    if damage == 'identity': member['source_binding']['identity'] = 'other'
    if damage == 'hash': member['source_binding']['text_sha256'] = 'other'
    if damage == 'ordinal': member['ordinal'] = 1
    if damage == 'parent': resolution['target_entry_id'] = 'target:0'
    with pytest.raises(ValueError): entry_view(inspected)


def test_sql_members_are_queryable_without_resolving_parent(tmp_path):
    result = entry_view(inspected_fixture(('ka',)))
    path = tmp_path/'semantic.sqlite'
    db = create(path)
    ingest(db, result)
    db.commit()
    assert db.execute('SELECT target, entity, status FROM xref').fetchall() == [(None, None, 'unresolved')]
    assert db.execute('SELECT ordinal,target,status FROM xref_member ORDER BY ordinal').fetchall() == [
        (0, 'target:0', 'resolved'), (1, None, 'unresolved')]
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []
    db.close()
    def query(*args):
        output = subprocess.check_output([sys.executable, 'scripts/badw_semantic_store.py',
            '--db', str(path), 'xrefs', *args], text=True)
        return [json.loads(line) for line in output.splitlines()]
    assert query('--target', 'target:0') == result['cross_references']
    members = result['cross_references'][0]['target_members']
    assert query('--members', '--target', 'target:0') == members[:1]
    assert query('--members', '--target', members[0]['target_lexical_entity']['id']) == members[:1]
    assert query('--members', '--unresolved', '--entry', result['inspection_id']) == members[1:]
    assert query('--unresolved') == result['cross_references']


def test_missing_source_geometry_falls_back_without_member_promotion():
    inspected = inspected_fixture()
    p = inspected['projection']
    del p['original_structure']['visual_lines'][0]['first_x']
    index = EntryIndex([inspected['entry'], entry('target:0', lemma='ka'), entry('target:1', lemma='kha')])
    ref = entry_view(view([p], index)[0])['cross_references'][0]
    assert 'target_members' not in ref
    assert ref['status'] == 'unresolved' and ref['target_entry_id'] is None


def test_same_identity_witnesses_never_choose_an_arbitrary_target(tmp_path):
    result = entry_view(inspected_fixture(('ka', 'ka', 'kha')))
    member = result['cross_references'][0]['target_members'][0]
    assert member['resolution_status'] == 'resolved'
    assert 'target_entry_id' not in member
    assert member['target_lexical_entity']['witness_entry_ids'] == ['target:0', 'target:1']
    db = create(tmp_path/'semantic.sqlite')
    ingest(db, result)
    assert db.execute('SELECT target,entity,status FROM xref_member WHERE ordinal=0').fetchone() == (
        None, member['target_lexical_entity']['id'], 'resolved')
    db.close()


def test_ambiguous_homonyms_remain_unresolved_in_reader_and_sql(tmp_path):
    inspected = inspected_fixture()
    index = EntryIndex([inspected['entry'], entry('ka:1'), entry('ka:2', homonym='2'),
                        entry('kha:1', lemma='kha')])
    result = entry_view(view([inspected['projection']], index)[0])
    member = result['cross_references'][0]['target_members'][0]
    assert member['resolution_status'] == 'ambiguous'
    assert 'target_entry_id' not in member and 'target_lexical_entity' not in member
    db = create(tmp_path/'semantic.sqlite')
    ingest(db, result)
    assert db.execute('SELECT target,entity,status FROM xref_member WHERE ordinal=0').fetchone() == (
        None, None, 'ambiguous')
    db.close()


def test_existing_single_target_queries_work_on_older_sqlite_schema(tmp_path):
    path = tmp_path/'legacy.sqlite'
    db = create(path)
    db.execute('DROP TABLE xref_member')
    db.execute('INSERT INTO xref VALUES(?,?,?,?,?,?)',
               ('ref', 'source', 'target', None, 'resolved', '{"single":true}'))
    db.commit()
    db.close()
    output = subprocess.check_output([sys.executable, 'scripts/badw_semantic_store.py',
        '--db', str(path), 'xrefs', '--target', 'target'], text=True)
    assert json.loads(output) == {'single': True}
