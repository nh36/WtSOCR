"""Stream the acquired corpus through current reader adapters into entry shards.

All outputs are derived, offline files under work/. Existing outputs are refused.
The 83-witness connected reader is an independent regression fixture.
"""
import argparse
import collections
import hashlib
import json
import shutil
import sqlite3
from itertools import chain
from pathlib import Path

from build_badw_connected_reader import ROOT, CACHE, CANON, INDEX, BIB, SEEDS, digest, write, validate_reviewed
from audit_badw_corpus_structure import rows, file_hash
from parse_badw_pdf_articles import reindex_article
from badw_article_parser import replay_empty_reference_labels
from build_badw_dictionary_prototype import view, bibliography_descriptions
from badw_dictionary_entry_view import entry_view, identifier
from badw_semantic_annotations import PACKET_VERSION, validate, apply_validated_annotations
from badw_pdf_structure_recovery import recover
from badw_contextual_semantics import augment_citations
from resolve_badw_cross_references import EntryIndex
from badw_bibliography import AuthorityResolver
from badw_bibliography_aliases import load_reviews
from badw_bibliography_citation_reviews import CitationReviews
from badw_bibliography_external import load_publications
from badw_reader_supplements import load_supplements, MANIFEST as SUPPLEMENTS


def citation_baseline(packet, projection, reader):
    """Keep accepted identities only at their original, exact source spans."""
    nodes = [n for n in projection['nodes'] if n['kind'] == 'citation']
    citations = reader['citations']
    if len(nodes) != len(citations):
        raise ValueError('baseline citation count mismatch')
    baseline = {}
    for node, citation in zip(nodes, citations):
        span = (node['start'], node['end'])
        if packet['review_text'][span[0]:span[1]] != citation['source_form']:
            raise ValueError('baseline citation literal mismatch')
        if span in baseline:
            raise ValueError('duplicate baseline citation span')
        baseline[span] = citation
    return baseline


def preserve_relationships(before, after, extent_reviews=()):
    """Do not discard accepted identities, ownership, or reference destinations."""
    citations = {c['component_id']: c for c in after['citations']}
    for old in before['citations']:
        new = citations.get(old['component_id'])
        if new is None or not set(old['accepted_authority_ids']) <= set(new['accepted_authority_ids']):
            raise ValueError('accepted citation identity changed')
        if old['ownership'] != 'unresolved' and (
            new['ownership'] == 'unresolved' or old['supports'] != new['supports']
            or old.get('sense_node_id') != new.get('sense_node_id')
        ):
            raise ValueError('accepted citation ownership changed')
    references = {r['component_id']: r for r in after['cross_references']}
    for old in before['cross_references']:
        new = references.get(old['component_id'])
        if new is None:
            transitions = [r for r in references.values() if
                r.get('supersedes_component_id') == old['component_id'] and
                r.get('extent_review') in extent_reviews]
            if len(transitions) != 1:
                raise ValueError('reference occurrence lost')
            new = transitions[0]
            review = new['extent_review']
            previous, span = review['claim']['previous_range'], review['ranges'][0]
            binding = old['source_binding']
            if (review['kind'] != 'cross_reference_extent' or review['effective_status'] != 'accepted' or
                    old['component_id'] != identifier(binding['identity'], binding['text_sha256'],
                        'cross_reference', previous['start'], previous['end']) or
                    old['source_span'] != {k: previous[k] for k in ('start', 'end')} or
                    new['source_span'] != {k: span[k] for k in ('start', 'end')} or
                    new['source_binding'] != binding):
                raise ValueError('unbound reference extent transition')
        if old['status'] == 'resolved' and (new['status'] != 'resolved' or (
            old.get('target_entry_id') and old['target_entry_id'] not in new['candidate_entry_ids']
        )):
            raise ValueError('accepted cross-reference changed')
        for member in old.get('target_members', []):
            if member['resolution_status'] != 'resolved':
                continue
            matches = [m for m in new.get('target_members', []) if
                       m['source_span'] == member['source_span'] and m['literal'] == member['literal']]
            # A reviewed contraction can remove a duplicated second arrow from
            # a plural extent. Its surviving accepted member becomes a single
            # reference, with exactly the same literal, span and destination.
            review = new.get('extent_review', {})
            if (not matches and review in extent_reviews and
                    review.get('claim', {}).get('basis') == 'reviewed_printed_arrow_boundary' and
                    new.get('supersedes_component_id') == old['component_id'] and
                    new.get('status') == 'resolved' and not new.get('target_members') and
                    member['source_binding']['identity'] == old['source_binding']['identity'] and
                    member['source_span'] == dict(start=new['source_span']['start'] + 1,
                                                  end=new['source_span']['end']) and
                    member['literal'] == new.get('wording') and
                    member.get('target_entry_id') == new.get('target_entry_id') and
                    member.get('target_lexical_entity') == new.get('target_lexical_entity') and
                    member.get('exact_index_candidate_ids') == new.get('candidate_entry_ids') and
                    member.get('printed_target') == new.get('parsed_target')):
                continue
            if (len(matches) != 1 or matches[0]['resolution_status'] != 'resolved' or
                    matches[0]['source_binding'] != member['source_binding'] or
                    matches[0].get('target_entry_id') != member.get('target_entry_id') or
                    matches[0].get('target_lexical_entity') != member.get('target_lexical_entity') or
                    matches[0].get('exact_index_candidate_ids') != member.get('exact_index_candidate_ids') or
                    matches[0].get('printed_target') != member.get('printed_target')):
                raise ValueError('accepted cross-reference member changed')


def reindex_for_review(original, reviews):
    """Keep reviewed frozen extents until the bound annotation is validated.

    Every other boundary must still match. This is staging, not acceptance:
    validate/apply_validated_annotations subsequently replay the source proof.
    """
    current = reindex_article(original)
    old = original['candidates']['cross_references']
    new = current['candidates']['cross_references']
    if len(old) != len(new):
        raise ValueError('reference boundaries changed; explicit structural replay required')
    for i, (before, after) in enumerate(zip(old, new)):
        previous = (before['visual_start'], before['visual_end'])
        proposed = (after['visual_start'], after['visual_end'])
        if previous == proposed:
            continue
        matches = [r for r in reviews if r.get('kind') == 'cross_reference_extent' and
            r.get('claim', {}).get('basis') == 'reviewed_printed_arrow_boundary' and
            (r['claim']['previous_range']['start'], r['claim']['previous_range']['end']) == previous and
            len(r.get('ranges', [])) == 1 and
            (r['ranges'][0]['start'], r['ranges'][0]['end']) == proposed]
        if len(matches) != 1:
            raise ValueError('reference boundaries changed; explicit structural replay required')
        new[i] = before
    return current


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--projections', type=Path, default=ROOT/'work/badw_semantic_hierarchy/projections.jsonl')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--baseline-store', type=Path, default=ROOT/'work/badw_forensic_structure/baseline_0f4849.sqlite', help='Frozen accepted citation relationships before the certified reference-owner tranche')
    ap.add_argument('--supplements', type=Path, default=SUPPLEMENTS, help='Pinned reviewed editorial acquisitions; frozen corpus stays unchanged')
    args = ap.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'work') or out.exists():
        ap.error('output must be a new directory under work/')
    out.mkdir(parents=True)
    (out/'entries').mkdir(); (out/'sources').mkdir()
    supplements, supplemental_projections = load_supplements(CACHE, args.supplements)
    original_entries = list(rows(INDEX))
    if {e['id'] for e in supplements} & {e['id'] for e in original_entries}:
        raise ValueError('supplement duplicates frozen entry identity')
    index = EntryIndex(original_entries + supplements)
    for r in supplemental_projections:
        r['reader'] = entry_view(view([r['projection']], index)[0])
    prior = sqlite3.connect('file:'+str(args.baseline_store.resolve())+'?mode=ro', uri=True)
    annotations = collections.defaultdict(list)
    for a in rows(ROOT/'data/reviewed_badw_semantic_annotations.jsonl'):
        annotations[a['identity']].append(a)
    db = sqlite3.connect(BIB/'bibliography.sqlite')
    authorities = [json.loads(r[0]) for r in db.execute('SELECT record_json FROM authority')]
    print_rows = [dict(id=a, occurrence_id=o, source_sha256=h, label=json.loads(j)['authority']['label']) for a,o,h,j in db.execute('SELECT authority_id,id,pdf_sha256,record_json FROM print_occurrence WHERE authority_id IS NOT NULL') if json.loads(j).get('authority')]
    source_rows = list(rows(BIB/'source_rows.jsonl'))
    external = load_publications(ROOT/'data/bibliography_external_publications.tsv', CACHE)
    authorities += [a for a in external if a['id'] not in {v['id'] for v in authorities}]
    source_rows += [a for a in external if a['occurrence_id'] not in {v['occurrence_id'] for v in source_rows}]
    aliases = load_reviews(ROOT/'data/bibliography_alias_reviews.tsv', source_rows, ROOT/'data/source_pdfs.tsv', CACHE)
    resolver = AuthorityResolver(authorities, source_rows, aliases, print_rows)
    reviews = CitationReviews(ROOT/'data/bibliography_citation_reviews.tsv', source_rows, CACHE, ROOT/'data/source_pdfs.tsv', list(rows(BIB/'print_occurrences.jsonl')))
    forensic_reviews = CitationReviews(ROOT/'data/bibliography_forensic_citation_reviews.tsv', source_rows, CACHE, ROOT/'data/source_pdfs.tsv')
    descriptions = {a['id']: bibliography_descriptions(db, a['id']) for a in authorities}
    db.close()
    catalog, seen, checked, sample = [], set(), set(), []
    seed_ids = {r['source_identity'] for r in rows(SEEDS)}
    census = collections.Counter()
    conflicts = []
    accepted_destinations = set()
    ledger = (out/'reference_cases.jsonl').open('w')
    for i, r in enumerate(chain(rows(args.projections), supplemental_projections)):
        p, pred = r['packet'], r['projection']
        baseline = citation_baseline(p, pred, r['reader'])
        identity, kind, text = p['identity'], p['source_kind'], p['review_text']
        prior_citations = [json.loads(v[0]) for v in prior.execute('SELECT record_json FROM citation WHERE entry=?', (identity,))]
        for c in prior_citations:
            span = c['source_span']
            if text[span['start']:span['end']] != c['source_form'] or c['source_binding']['text_sha256'] != p['review_text_sha256']:
                raise ValueError('frozen citation source binding changed: '+identity)
            baseline[(span['start'],span['end'])] = c
        if identity in seen: raise ValueError('duplicate witness: '+identity)
        seen.add(identity)
        if digest(text.encode()) != p['review_text_sha256']: raise ValueError('review hash mismatch')
        objects = ([p['source']['source_object']] if kind == 'html' else p['source']['source_objects'])
        sources = []
        for obj in objects:
            sha = obj['sha256'] if kind == 'html' else obj['pdf_sha256']
            path = CACHE/obj['object_path'] if kind == 'html' else CACHE/'objects/sha256'/sha[:2]/sha
            if sha not in checked:
                if digest(path.read_bytes()) != sha: raise ValueError('source hash mismatch')
                checked.add(sha)
            if kind == 'pdf':
                canonical = CANON/obj['canonical_object']
                if str(canonical) not in checked:
                    if digest(canonical.read_bytes()) != obj['canonical_object_sha256']: raise ValueError('canonical hash mismatch')
                    checked.add(str(canonical))
                dest = out/'sources'/(sha+'.pdf')
                if not dest.exists(): shutil.copyfile(path, dest)
                sources.append(dict(url='sources/'+sha+'.pdf', original_url=obj['pdf_url'], label='Printed facsimile', sha256=sha))
        if kind == 'pdf':
            original = pred['original_structure']
            current = reindex_for_review(original, annotations[identity])
            current['review_text_sha256'] = p['review_text_sha256']
            pred['original_structure'] = current
        pred = replay_empty_reference_labels(pred, CACHE)
        p['contract_version'] = PACKET_VERSION
        checkpoint_pred, extent_reviews = None, []
        if annotations[identity]:
            try:
                accepted = validate([p], annotations[identity], cache=CACHE, canonical_root=CANON)
            except ValueError as error:
                if str(error) != 'stale source view binding':
                    raise
                # Same policy as the full structural replay: retain the frozen
                # projection and record the incompatible review; never rebind it.
                conflicts.append(dict(identity=identity, reason=str(error),
                                      annotations=annotations[identity]))
            else:
                extent_reviews = [a for a in accepted if a['kind'] == 'cross_reference_extent'
                                  and a['effective_status'] == 'accepted']
                if extent_reviews:
                    checkpoint_pred = apply_validated_annotations(p, pred,
                        [a for a in accepted if a['kind'] != 'cross_reference_extent'])
                pred = apply_validated_annotations(p, pred, accepted)
        pred = recover(pred, text)
        pred, _ = augment_citations(pred, text, resolver)
        inspected = view([pred], index)[0]
        bibliography = {}
        for n in pred['nodes']:
            if n['kind'] != 'citation': continue
            resolution = resolver.resolve(text[n['start']:n['end']], kind)
            resolution = reviews.apply_source(kind, identity, text, n['start'], n['end'], resolution)
            resolution = forensic_reviews.apply_source(kind, identity, text, n['start'], n['end'], resolution)
            resolver.component_contract(resolution)
            ids = set(baseline.get((n['start'], n['end']), {}).get('accepted_authority_ids', []))
            ids.update(a for m in resolution['matches'] if m.get('target_status') == 'accepted_identity' for a in m['authority_ids'])
            bibliography[(identity,n['id'])] = [dict(resolver.by_id[a], descriptions=descriptions[a], coverage_status=resolution.get('coverage_status'), edition_status=resolution.get('edition_status')) for a in sorted(ids)]
        entry = entry_view(inspected, bibliography)
        checkpoint_entry = None
        if checkpoint_pred is not None:
            checkpoint_pred = recover(checkpoint_pred, text)
            checkpoint_pred, _ = augment_citations(checkpoint_pred, text, resolver)
            checkpoint_entry = entry_view(view([checkpoint_pred], index)[0], bibliography)
            preserve_relationships(checkpoint_entry, entry, extent_reviews)
        try:
            preserve_relationships(dict(citations=prior_citations, cross_references=r['reader']['cross_references']), entry, extent_reviews)
        except ValueError as error:
            raise ValueError(identity+': '+str(error)) from error
        entry['source_kind'] = kind
        entry['sources'] = sources or [dict(url=entry['source_url'], label='BAdW editorial source', sha256=objects[0]['sha256'])]
        for c in entry['citations']:
            census[kind+':citations:'+c['bibliography_status']] += 1
            census[kind+':ownership:'+('unresolved' if c['ownership']=='unresolved' else 'established')] += 1
        for ref in entry['cross_references']:
            census[kind+':parents:'+ref['status']] += 1
            for unit in ref.get('target_members', [ref]):
                status = unit.get('resolution_status', unit.get('status'))
                census[kind+':targets:'+status] += 1
                if status == 'resolved':
                    target = unit.get('target_entry_id')
                    choices = unit.get('candidate_entry_ids', [])
                    if target:
                        accepted_destinations.add(target)
                    elif unit.get('target_lexical_entity') and choices:
                        accepted_destinations.update(choices)
                    else:
                        raise ValueError('accepted reference lacks navigable witnesses')
                if status != 'resolved':
                    ledger.write(json.dumps(dict(identity=identity, source_kind=kind, source_binding=ref['source_binding'], reference=ref, unit=unit), ensure_ascii=False)+'\n')
        name = hashlib.sha256(identity.encode()).hexdigest()+'.json'
        body = json.dumps(entry, ensure_ascii=False, separators=(',',':')).encode()
        (out/'entries'/name).write_bytes(body)
        catalog.append(dict(id=entry['id'], headword=entry['headword'], homonym=entry.get('homonym'), source_kind=kind,
            path='entries/'+name, sha256=digest(body), search_aliases=[f['form_span']['literal'] for f in entry['semantic_hierarchy'].get('header_fields', []) if f.get('header_kind') == 'alternate_headword' and f.get('form_span', {}).get('literal')]))
        if identity in seed_ids: sample.append(checkpoint_entry or entry)
        if (i+1)%1000 == 0: print(i+1, 'witnesses', flush=True)
    ledger.close()
    witness_ids = {e['id'] for e in catalog}
    if accepted_destinations - witness_ids:
        raise ValueError('accepted destination absent from full corpus: '+repr(sorted(accepted_destinations-witness_ids)))
    write(out/'annotation_conflicts.json', conflicts)
    if len(catalog) != 29877 + len(supplements): raise ValueError('incomplete corpus')
    # Include independently resolved destinations in the existing checkpoint check.
    sample_ids = {e['id'] for e in sample}
    for e in catalog:
        if e['id'] not in sample_ids: sample.append(dict(id=e['id']))
    validate_reviewed(sample, list(rows(SEEDS)))
    catalog.sort(key=lambda e:(e['headword'].get('loc',''),str(e.get('homonym') or ''),e['id']))
    write(out/'data.json', dict(entries=catalog, sharded=True, preview=dict(scope='All acquired HTML and PDF witnesses. Source acquisition is not a claim of complete editorial coverage.', ordering='Unicode order of LoC headword, then homonym, then source identity; not traditional Tibetan collation.', reviewed_occurrences=23, suggested_entries=[dict(id=r['source_identity'],label=r['headword']) for r in list(rows(SEEDS))[:5]])))
    assets = ROOT/'scripts/badw_dictionary_prototype'
    for name in ('index.html','app.js','style.css'): shutil.copyfile(assets/name,out/name)
    shutil.copytree(assets/'fonts', out/'fonts')
    write(out/'manifest.json', dict(entries=len(catalog), frozen_witnesses=29877, supplemental_witnesses=len(supplements), supplemental_sources=str(args.supplements.resolve().relative_to(ROOT)), source_counts=dict(collections.Counter(e['source_kind'] for e in catalog)), census=dict(census), entry_index_sha256=index.sha256, catalog_sha256=digest((out/'data.json').read_bytes()), annotation_conflict_witnesses=len(conflicts), inputs=[dict(path=str(p.relative_to(ROOT)),sha256=file_hash(p)) for p in [args.projections.resolve(), args.baseline_store.resolve(), args.supplements.resolve(), INDEX, SEEDS, BIB/'bibliography.sqlite', BIB/'source_rows.jsonl', BIB/'print_occurrences.jsonl', ROOT/'data/source_pdfs.tsv', ROOT/'data/reviewed_badw_semantic_annotations.jsonl', *sorted((ROOT/'data').glob('bibliography*.tsv')), *sorted((ROOT/'scripts').glob('*.py')), *sorted(q for q in assets.rglob('*') if q.is_file())]]))
    print(json.dumps(dict(reader=str(out), census=dict(census))))


if __name__ == '__main__': main()
