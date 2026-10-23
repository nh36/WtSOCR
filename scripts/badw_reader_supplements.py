"""Replay explicitly reviewed acquisitions without modifying the frozen corpus.

An HTTP-200 lemma shell is not an entry. Require an explicit numbered heading,
substantive definition, exact URL, immutable bytes and exact extracted text.
This adds source witnesses; it never equates an unnumbered PDF with homonym 1.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from badw_article_parser import parse_database_article
from badw_html import parse_html, find_first, exact_text
from extract_badw_lexical_records import extract_article
from audit_badw_corpus_structure import packet
from project_badw_structural_candidates import project_html
from badw_semantic_annotations import PACKET_VERSION

MANIFEST = Path(__file__).resolve().parents[1] / 'data/badw_reader_supplements.jsonl'


def load_supplements(cache, manifest=MANIFEST):
    entries, projections = [], []
    for line in Path(manifest).read_text().splitlines():
        review = json.loads(line)
        key, sha = review['request_key'], review['source_sha256']
        if any(len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in (key, sha)):
            raise ValueError('invalid supplemental cache identity')
        meta = json.loads((cache/'requests'/key[:2]/(key+'.json')).read_text())
        body = (cache/'objects/sha256'/sha[:2]/sha).read_bytes()
        if (hashlib.sha256(body).hexdigest() != sha or meta['sha256'] != sha or
                meta['request_key'] != key or meta['requested_url'] != review['url'] or
                meta['final_url'] != review['url'] or
                meta['object_path'] != 'objects/sha256/'+sha[:2]+'/'+sha):
            raise ValueError('supplemental source binding mismatch')
        article = parse_database_article(body, source_metadata=meta)
        heading = find_first(parse_html(body.decode(article['source_object']['decoded_encoding'])),
                             tag='span', class_name='lemma')
        number = find_first(heading, tag='sup') if heading is not None else None
        path = urlsplit(review['url'])
        parts = path.path.split('/')
        if (path.scheme != 'https' or path.netloc != 'wts-digital.badw.de' or
                len(parts) != 4 or parts[:2] != ['', 'lemma'] or parts[3] != review['homonym'] or
                unquote(parts[2]) != review['lemma'] or path.query or path.fragment or
                number is None or exact_text(number) != review['homonym'] or
                article['lemma'] != review['lemma'] or article['homonym'] != review['homonym']):
            raise ValueError('supplemental heading identity mismatch')
        if not article['meanings'] or not any(m.get('text', '').strip() for m in article['meanings']):
            raise ValueError('supplemental article has no substantive definition')
        if hashlib.sha256(article['article_source_text'].encode()).hexdigest() != review['text_sha256']:
            raise ValueError('supplemental text binding mismatch')
        records = extract_article(article, snapshot_id=review['snapshot_id'],
                                  extraction_run_id='reviewed-source-supplement-v1')
        entry = records[0]
        if entry['id'] != review['entry_id'] or entry['id'] in {e['id'] for e in entries}:
            raise ValueError('supplemental entry identity mismatch or duplicate')
        p = packet(article, 'html')
        p['contract_version'] = PACKET_VERSION
        entries.append(entry)
        projections.append(dict(packet=p, projection=project_html(p, records, article)))
    return entries, projections
