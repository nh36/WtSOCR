"""Build a bounded, source-verified connected reader; never replace an output.

Run from the repository root. All acquired sources and generated data stay in
ignored work/. No acquisition, OCR, release rebuild or resolution guessing.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys

from build_badw_structural_review_packet import rows
from audit_badw_corpus_structure import packet
from parse_badw_pdf_articles import reindex_article
from extract_badw_pdf_lexical_candidates import extract
from build_badw_pdf_nested_candidates import project as nested_project
from project_badw_structural_candidates import project, project_html
from badw_article_parser import parse_database_article
from extract_badw_lexical_records import extract_article
from resolve_badw_cross_references import EntryIndex
from build_badw_dictionary_prototype import view
from badw_semantic_annotations import validate, apply_validated_annotations, PACKET_VERSION

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work/badw_source_cache'
CANON = ROOT / 'work/badw_verified_rebuild_20261003/canonical_v2'
INDEX = ROOT / 'work/badw_relationship_targets_20261005/actual_entry_index.jsonl'
SEEDS = ROOT / 'work/badw_pdf_multitarget_review/multitarget_occurrences.jsonl'
PDF = ROOT / 'work/badw_verified_rebuild_20261003/structure_replay_v2/pdf_article_structure.jsonl.gz'
HTML = ROOT / 'work/badw_stage_c13_20260928/parsed/database_articles.jsonl'
BIB = ROOT / 'work/wts_apparatus_20261010/ingested_completed'


def digest(body):
    return hashlib.sha256(body).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n')


def destinations(reference):
    """Accepted entry witnesses only; plural parents are never promoted."""
    if reference.get('target_members') is not None:
        return {m['target_entry_id'] for m in reference['target_members']
                if m['resolution_status'] == 'resolved' and m.get('target_entry_id')}
    return {reference['target_entry_id']} if reference.get('status') == 'resolved' and reference.get('target_entry_id') else set()


def validate_reviewed(entries, seeds):
    """Accept exactly the checkpoint's reviewed members and available targets."""
    by_id = {e['id']: e for e in entries}
    statuses, collections = [], []
    for seed in seeds:
        matches = [r for r in by_id[seed['source_identity']]['cross_references']
                   if r['wording'] == seed['recorded_target_label'] and
                   [(m['literal'], m['source_span']['start'], m['source_span']['end'])
                    for m in r.get('target_members', [])] ==
                   [(m['literal'], m['start'], m['end']) for m in seed['candidate_spans']]]
        if len(matches) != 1:
            raise ValueError('reviewed reference missing, duplicated or rebound')
        ref = matches[0]
        if ref['status'] != 'unresolved' or ref.get('target_entry_id') or ref.get('target_lexical_entity'):
            raise ValueError('plural parent promoted')
        collections.append(ref['target_members_status'])
        for member in ref['target_members']:
            statuses.append(member['resolution_status'])
            if member['resolution_status'] == 'resolved' and member['target_entry_id'] not in by_id:
                raise ValueError('reviewed resolved destination absent')
    if (len(statuses), statuses.count('resolved'), statuses.count('unresolved'),
            collections.count('complete'), collections.count('partial')) != (50, 47, 3, 20, 3):
        raise ValueError('reviewed checkpoint totals differ')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--max-entries', type=int, default=150)
    args = ap.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'work') or output.exists():
        ap.error('output must be a new directory under ignored work/')
    seeds = list(rows(SEEDS))
    if len(seeds) != 23 or digest(SEEDS.read_bytes()) != '4281022c8fd103d6b30205f0da3ba477e10f19fb5cd533b401e40fc9a7260097':
        raise ValueError('reviewed occurrence set changed')
    if digest(INDEX.read_bytes()) != 'bac43a0aa32713ce7d700cf832a26dfafbe9c7a730de2cd35a00cacf341edbe3':
        raise ValueError('entry identity index changed')
    index = EntryIndex(rows(INDEX))
    pdf = {r['article_id']: r for r in rows(PDF)}
    html = {r['source_identifier']: r for r in rows(HTML)}
    annotations = list(rows(ROOT/'data/reviewed_badw_semantic_annotations.jsonl'))
    projections = {}
    selected = {r['source_identity'] for r in seeds}
    missing = set()
    while selected - projections.keys():
        if len(selected) > args.max_entries:
            raise ValueError('connected closure exceeds explicit corpus bound')
        for entry_id in sorted(selected - projections.keys()):
            entry = index.records[entry_id]
            if entry_id in pdf:
                article = reindex_article(pdf[entry_id])
                for obj in article['source_objects']:
                    sha = obj['pdf_sha256']
                    if digest((CACHE/'objects/sha256'/sha[:2]/sha).read_bytes()) != sha:
                        raise ValueError('PDF witness hash mismatch')
                    if digest((CANON/obj['canonical_object']).read_bytes()) != obj['canonical_object_sha256']:
                        raise ValueError('canonical witness hash mismatch')
                article['review_text_sha256'] = digest('\n'.join(l['text'] for l in article['visual_lines']).encode())
                p = packet(article, 'pdf')
                projection = project(p, nested_project(article, extract(article)), article)
            else:
                identity = entry['source_spans'][0]['source_id']
                original = html[identity]
                obj = original['source_object']
                body = (CACHE/obj['object_path']).read_bytes()
                if digest(body) != obj['sha256']:
                    raise ValueError('HTML witness hash mismatch')
                meta = dict(obj, fetched_at_utc=obj['fetch_timestamp_utc'], delivery_type='database_article', valid_resource=True,
                            response_headers={'content-type':'text/html; charset='+obj['decoded_encoding']})
                article = parse_database_article(body, source_metadata=meta)
                if article['article_source_text'] != original['article_source_text']:
                    raise ValueError('HTML source text changed')
                p = packet(article, 'html')
                records = extract_article(article, snapshot_id='connected-reader', extraction_run_id='connected-reader-v1')
                # Canonical identities must match the pinned acquisition index.
                if records[0]['id'] != entry_id:
                    raise ValueError('HTML entry identity differs from pinned index')
                projection = project_html(p, records, article)
            p['contract_version'] = PACKET_VERSION
            chosen = [a for a in annotations if a['identity'] == p['identity']]
            if chosen:
                accepted = validate([p], chosen, cache=CACHE, canonical_root=CANON)
                projection = apply_validated_annotations(p, projection, accepted)
            projections[entry_id] = projection
        inspected = view(list(projections.values()), index)
        from badw_dictionary_entry_view import entry_view
        for item in inspected:
            for ref in entry_view(item)['cross_references']:
                for target in destinations(ref):
                    if target in index.records:
                        selected.add(target)
                    else:
                        missing.add(target)
    output.mkdir(parents=True)
    projection_path = output/'projections.jsonl'
    projection_path.write_text(''.join(json.dumps(p, ensure_ascii=False, sort_keys=True)+'\n' for p in projections.values()))
    # HTML review validation requires every supplied review to occur. Scope the
    # immutable ledger by selected source identity, retaining the original rows.
    review_path = output/'citation_reviews.tsv'
    with (ROOT/'data/bibliography_citation_reviews.tsv').open() as stream:
        ledger = csv.DictReader(stream, delimiter='\t')
        fields = ledger.fieldnames
        selected_reviews = [r for r in ledger if r['layer'] == 'html' and r['source_article_id'] in projections]
    with review_path.open('w') as stream:
        writer = csv.DictWriter(stream, fields, delimiter='\t')
        writer.writeheader()
        writer.writerows(selected_reviews)
    reader = output/'reader'
    command = [sys.executable, str(ROOT/'scripts/build_badw_dictionary_prototype.py'), '--projection', str(projection_path),
               '--entry-index', str(INDEX), '--output', str(reader), '--citation-links', str(BIB/'citation_links.jsonl'),
               '--bibliography', str(BIB/'bibliography.sqlite'), '--source-cache', str(CACHE),
               '--pdf-citation-staging', str(ROOT/'work/badw_verified_rebuild_20261003/staging.sqlite'),
               '--pdf-canonical-root', str(CANON), '--source-citation-reviews', str(review_path),
               '--alias-reviews', str(ROOT/'data/bibliography_alias_reviews.tsv')]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    data = json.loads((reader/'data.json').read_text())
    source_dir = reader/'sources'
    source_dir.mkdir()
    for entry in data['entries']:
        projection = projections[entry['id']]
        entry['source_kind'] = projection['source_kind']
        entry['sources'] = []
        if projection['source_kind'] == 'pdf':
            for obj in projection['source']['source_objects']:
                sha = obj['pdf_sha256']
                source = CACHE/'objects/sha256'/sha[:2]/sha
                dest = source_dir/(sha+'.pdf')
                if not dest.exists():
                    shutil.copyfile(source, dest)
                pages = sorted({str(l.get('printed_page')) for l in projection['source']['visual_lines']
                                if l.get('page_id') == obj.get('page_id') and l.get('printed_page') is not None})
                entry['sources'].append(dict(url='sources/'+sha+'.pdf', original_url=obj['pdf_url'],
                                             label='Facsimile'+(' · p. '+', '.join(pages) if pages else ''), sha256=sha))
        else:
            entry['sources'].append(dict(url=entry['source_url'], label='BAdW editorial source', sha256=projection['source']['source_object']['sha256']))
    validate_reviewed(data['entries'], seeds)
    data['preview'] = dict(reviewed_occurrences=23, reviewed_entries=len({r['source_identity'] for r in seeds}),
        ordering='Unicode order of LoC headword, then homonym, then source identity; not traditional Tibetan collation.',
        scope='Reviewed multiple-target entries and the closure of their independently resolved entry destinations.',
        suggested_entries=[dict(id=r['source_identity'], label=r['headword']) for r in seeds[:5]],
        unavailable_destinations=sorted(missing))
    write(reader/'data.json', data)
    manifest = json.loads((reader/'manifest.json').read_text())
    manifest.update(data_sha256=digest((reader/'data.json').read_bytes()), preview=data['preview'],
                    recipe='scripts/build_badw_connected_reader.py',
                    implementation_inputs=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p.read_bytes()))
                                           for p in sorted((ROOT/'scripts').glob('*.py'))]+
                                          [dict(path=str(p.relative_to(ROOT)),sha256=digest(p.read_bytes()))
                                           for p in sorted((ROOT/'scripts/badw_dictionary_prototype').rglob('*')) if p.is_file()],
                    selection_inputs=[dict(path=str(p.relative_to(ROOT)),sha256=digest(p.read_bytes())) for p in (SEEDS,INDEX,PDF,HTML,ROOT/'data/reviewed_badw_semantic_annotations.jsonl', ROOT/'data/bibliography_citation_reviews.tsv')])
    write(reader/'manifest.json', manifest)
    print(json.dumps(dict(reader=str(reader), entries=len(data['entries']), sources=len(list(source_dir.iterdir())), reviewed_occurrences=23)))


if __name__ == '__main__':
    main()
