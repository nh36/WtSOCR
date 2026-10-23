"""A missing acquisition needs complete, explicitly identified source evidence."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from badw_article_parser import parse_database_article
from extract_badw_lexical_records import extract_article
from badw_reader_supplements import load_supplements
from resolve_badw_cross_references import EntryIndex


def source(tmp_path, *, number='2', definition='ein Turkvolk', url_number='2'):
    body = ('<div class="text"><div class="lemma-head"><span class="lemma">'
            '<span class="lemtib">དྲུ་གུ་</span><span class="lem">dru gu</span>'
            + (f'<sup>{number}</sup>' if number else '')
            + '</span></div><div class="bedeutung">' + definition + '</div></div>').encode()
    sha = hashlib.sha256(body).hexdigest()
    key = 'a' * 64
    obj = 'objects/sha256/' + sha[:2] + '/' + sha
    url = 'https://wts-digital.badw.de/lemma/dru%20gu/' + url_number
    meta = dict(sha256=sha, request_key=key, requested_url=url, final_url=url,
                object_path=obj, content_type='text/html', delivery_type='database_article',
                valid_resource=True)
    article = parse_database_article(body, source_metadata=meta)
    entry = extract_article(article, snapshot_id='test', extraction_run_id='test')[0] if definition else {'id': 'unused'}
    review = dict(request_key=key, source_sha256=sha, url=url, lemma='dru gu',
                  homonym='2', snapshot_id='test', entry_id=entry['id'],
                  text_sha256=hashlib.sha256(article['article_source_text'].encode()).hexdigest())
    object_path = tmp_path / obj
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(body)
    meta_path = tmp_path / 'requests' / key[:2] / (key + '.json')
    meta_path.parent.mkdir(parents=True)
    meta_path.write_text(json.dumps(meta))
    manifest = tmp_path / 'reviews.jsonl'
    manifest.write_text(json.dumps(review) + '\n')
    return manifest, review, meta_path, object_path


def test_complete_numbered_acquisition_keeps_identity_and_source(tmp_path):
    manifest, review, _, body = source(tmp_path)
    entries, projections = load_supplements(tmp_path, manifest)
    entry, = entries
    assert entry['id'] == review['entry_id']
    index = EntryIndex(entries)
    assert len(index.labels['dru gu']) == 1
    projection, = projections
    assert projection['packet']['review_text'].strip()
    assert hashlib.sha256(body.read_bytes()).hexdigest() == review['source_sha256']


@pytest.mark.parametrize('number,definition,url_number', [
    ('', 'ein Turkvolk', '2'), ('1', 'ein Turkvolk', '2'),
    ('2', '', '2'), ('2', 'ein Turkvolk', '1'),
])
def test_shell_or_unproved_homonym_is_rejected(tmp_path, number, definition, url_number):
    manifest, *_ = source(tmp_path, number=number, definition=definition, url_number=url_number)
    with pytest.raises(ValueError):
        load_supplements(tmp_path, manifest)


@pytest.mark.parametrize('damage', ['bytes', 'text', 'entry', 'redirect', 'metadata', 'duplicate'])
def test_stale_or_misbound_acquisition_is_rejected(tmp_path, damage):
    manifest, review, meta_path, body = source(tmp_path)
    if damage == 'bytes':
        body.write_bytes(body.read_bytes() + b'changed')
    elif damage == 'text':
        review['text_sha256'] = '0' * 64
    elif damage == 'entry':
        review['entry_id'] = 'badw:entry:wrong'
    elif damage in ('redirect', 'metadata'):
        meta = json.loads(meta_path.read_text())
        meta['final_url' if damage == 'redirect' else 'sha256'] = 'wrong'
        meta_path.write_text(json.dumps(meta))
    manifest.write_text(json.dumps(review) + '\n')
    if damage == 'duplicate':
        manifest.write_text(manifest.read_text() * 2)
    with pytest.raises(ValueError):
        load_supplements(tmp_path, manifest)
