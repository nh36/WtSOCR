import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('pilot', Path(__file__).resolve().parents[1]/'scripts/build_badw_page_link_pilot.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


@pytest.fixture
def inputs(tmp_path):
    filename = 'a'*64+'.pdf'
    (tmp_path/filename).write_bytes(b'local derivative')
    page = dict(source='WtS_8-b', source_sha256='b'*64, physical_page=18,
                crop=[0, 0, 480, 680], side='single', volume=8, printed_page=8,
                filename=filename, sha256=pilot.digest(tmp_path/filename),
                original_path='/private/source.pdf')
    manifest = dict(pages={'page': page}, witnesses=[])
    geometry = {k: page[k] for k in ('source', 'source_sha256', 'physical_page', 'crop', 'side', 'volume', 'printed_page')}
    geometry['key'] = 'page'
    top = dict(reviewed_page_geometry=[geometry], physical_page=18, family='wts_8_b',
               anchor='wts_8_b:18:26', line=26, heading_text='ba rdzi', printed_evidence='Viehhirte',
               evidence_lines=[26], risks=['unread_homonym'], definition_evidence={}, score=10)
    row = dict(source_id='html:one', source_url='https://wts-digital.badw.de/lemma/ba-rdzi/1',
               html_sha256='c'*64, input_identity='d'*64, editorial_headword={'loc':'ba rdzi'},
               editorial_homonym=1, editorial_definition='Viehhirte', editorial_citations=[], proposed=[top])
    proposals = tmp_path/'proposals.jsonl'
    proposals.write_text(json.dumps(row)+'\n')
    facsimiles = tmp_path/'manifest.json'
    facsimiles.write_text(json.dumps(manifest))
    return row, manifest, proposals, facsimiles


def select(row, manifest):
    return pilot.select(io.StringIO(json.dumps(row)+'\n'), manifest)


def test_exact_source_checksum_exclusion(inputs):
    row, manifest, _, _ = inputs
    manifest['witnesses'] = [dict(source_url=row['source_url'], html_sha256='old')]
    assert len(select(row, manifest)) == 1
    manifest['witnesses'][0]['html_sha256'] = row['html_sha256']
    assert select(row, manifest) == []


@pytest.mark.parametrize('field,value', [('physical_page', 19), ('family', 'wts_9_m')])
def test_wrong_page_or_family_rejected(inputs, field, value):
    row, manifest, _, _ = inputs
    row['proposed'][0][field] = value
    with pytest.raises(ValueError):
        select(row, manifest)


def test_changed_geometry_and_duplicate_identity_rejected(inputs):
    row, manifest, _, _ = inputs
    changed = copy.deepcopy(row)
    changed['proposed'][0]['reviewed_page_geometry'][0]['crop'][2] = 470
    with pytest.raises(ValueError):
        select(changed, manifest)
    with pytest.raises(ValueError, match='duplicate'):
        pilot.select(io.StringIO((json.dumps(row)+'\n')*2), manifest)


@pytest.mark.parametrize('url', ['file:///private/source.pdf', 'https://evil.test/lemma/a', 'https://wts-digital.badw.de@evil.test/lemma/a'])
def test_unsafe_editorial_url_rejected(url):
    with pytest.raises(ValueError):
        pilot.safe_url(url)


def test_deterministic_private_safe_pending_pack(inputs, tmp_path):
    _, _, proposals, facsimiles = inputs
    first, second = tmp_path/'first', tmp_path/'second'
    assert pilot.build(proposals, facsimiles, first) == pilot.build(proposals, facsimiles, second)
    assert (first/'pilot.json').read_bytes() == (second/'pilot.json').read_bytes()
    report = json.loads((first/'pilot.json').read_text())
    assert report['candidates'][0]['decision'] == 'pending'
    assert report['candidates'][0]['eligible_for_original_print_link'] is False
    for path in first.rglob('*'):
        assert not path.is_symlink()
        if path.suffix in ('.json', '.html'):
            assert '/private/' not in path.read_text()
    with pytest.raises(ValueError, match='fresh'):
        pilot.build(proposals, facsimiles, first)


def test_changed_derivative_fails_before_output_created(inputs, tmp_path):
    _, manifest, proposals, facsimiles = inputs
    (tmp_path/manifest['pages']['page']['filename']).write_bytes(b'changed')
    output = tmp_path/'output'
    with pytest.raises(ValueError):
        pilot.build(proposals, facsimiles, output)
    assert not output.exists()


def test_derivative_symlink_rejected(inputs, tmp_path):
    _, manifest, proposals, facsimiles = inputs
    pdf = tmp_path/manifest['pages']['page']['filename']
    target = tmp_path/'private.pdf'
    pdf.rename(target)
    pdf.symlink_to(target)
    with pytest.raises(ValueError):
        pilot.build(proposals, facsimiles, tmp_path/'output')


@pytest.fixture
def observation_pack(inputs, tmp_path):
    _, _, proposals, facsimiles = inputs
    output = tmp_path/'pack'
    pilot.build(proposals, facsimiles, output)
    pilot_path = output/'pilot.json'
    pack = json.loads(pilot_path.read_text())
    image_dir = tmp_path/'images'
    image_dir.mkdir()
    (image_dir/'page.png').write_bytes(b'rendered source evidence')
    fields = ('source_id', 'source_url', 'html_sha256', 'input_identity',
              'anchor', 'headword', 'homonym', 'family', 'physical_page')
    candidate = {key: pack['candidates'][0][key] for key in fields}
    candidate.update(observation_status='deferred', reason='Numbering requires review',
                     eligible_for_original_print_link=False)
    observed = dict(pilot_sha256=pilot.digest(pilot_path), observations=[dict(
        page_key='page', page=pack['pages']['page'], family='wts_8_b',
        image_sha256=pilot.digest(image_dir/'page.png'))], candidates=[candidate],
        counts=dict(printed_pages_observed=1, physical_pages_observed=1,
                    candidates_observed=1, new_verified_links=0))
    observations_path = tmp_path/'observations.json'
    return pilot_path, observations_path, image_dir, observed


def validate_pack(pack):
    pilot_path, observations_path, images, observed = pack
    observations_path.write_text(json.dumps(observed))
    return pilot.validate_observations(pilot_path, observations_path, images)


def test_observations_check_bindings_without_authorizing_links(observation_pack):
    assert validate_pack(observation_pack)['new_verified_links'] == 0
    for status in ('observed_candidate_requires_certificate', 'rejected_proposed_article'):
        observation_pack[3]['candidates'][0]['observation_status'] = status
        assert validate_pack(observation_pack)['candidates_observed'] == 1


@pytest.mark.parametrize('field,value', [('html_sha256', 'changed'),
    ('anchor', 'wts_8_b:18:99'), ('homonym', 2), ('source_url', 'https://evil.test')])
def test_changed_observed_identity_rejected(observation_pack, field, value):
    observation_pack[3]['candidates'][0][field] = value
    with pytest.raises(ValueError, match='identity'):
        validate_pack(observation_pack)


@pytest.mark.parametrize('change', ['pilot', 'geometry', 'family', 'duplicate',
                                  'authority', 'counts', 'image', 'unsafe_image'])
def test_stale_or_unsafe_observation_rejected(observation_pack, change):
    observed = observation_pack[3]
    if change == 'pilot':
        observed['pilot_sha256'] = 'changed'
    elif change == 'geometry':
        observed['observations'][0]['page']['crop'][2] = 470
    elif change == 'family':
        observed['observations'][0]['family'] = 'wts_9_m'
    elif change == 'duplicate':
        observed['candidates'].append(copy.deepcopy(observed['candidates'][0]))
    elif change == 'authority':
        observed['candidates'][0]['eligible_for_original_print_link'] = True
    elif change == 'counts':
        observed['counts']['new_verified_links'] = 1
    elif change == 'image':
        observed['observations'][0]['image_sha256'] = 'changed'
    elif change == 'unsafe_image':
        observed['observations'][0]['image_filename'] = '../private.png'
    with pytest.raises(ValueError):
        validate_pack(observation_pack)
