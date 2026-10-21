"""Recount a full reader and retain exact, provisional residual diagnoses.

This is a case ledger, not a review annotation or authority for new links.
Missing index identities do not establish missing books or printing errors.
"""
import argparse
import collections
import gzip
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from audit_badw_corpus_structure import rows
from build_badw_connected_reader import INDEX
from resolve_badw_cross_references import EntryIndex


def classify(ref, unit, index):
    # Independently resolved members have their own printed-target parse. Never
    # diagnose one member using its plural parent's combined lexical label.
    parsed = unit.get('printed_target') or unit.get('parsed_target') or {}
    label = parsed.get('lexical_target') or unit.get('lexical_target') or unit.get('wording') or unit.get('literal') or ''
    url = ref.get('source_url')
    if url and unit is ref:
        parts = urlsplit(url).path.split('/')
        if len(parts) == 4 and parts[1] == 'lemma':
            label = unquote(parts[2])
    evidence = unit.get('resolution_evidence', ref.get('resolution_evidence')) or {}
    review = evidence.get('target_review') or {}
    reviewed_editorial = (evidence.get('method') == 'reviewed_exact_editorial_target'
                         and review.get('source_target_url') == url)
    reviewed_printed = evidence.get('method') == 'reviewed_exact_printed_substitution'
    if reviewed_editorial or reviewed_printed:
        label = review['lemma']
    candidates = sorted(index.labels.get(label, set()))
    accepted_candidates = unit.get('candidate_entry_ids', unit.get('exact_index_candidate_ids', []))
    status = unit.get('resolution_status', unit.get('status'))
    if status == 'ambiguous':
        cause, reason = 'ambiguity', 'Several exact homonym identities; source qualifier does not select one.'
    elif not label.strip('↑↓ ,'):
        cause, reason = 'parser_failure', 'Arrow retained but no lexical target inside the extracted span; DOM boundary review required.'
    elif candidates:
        cause, reason = 'identity_or_manifestation_mismatch', 'Exact label exists, but explicit source homonym/manifestation identity is not established. Facsimile review required.'
    else:
        cause, reason = 'missing_exact_identity', 'No exact acquired headword. Acquisition gap, source error and decoding remain competing explanations; not a confirmed printing error.'
    if reviewed_printed and not candidates:
        reason = 'Printed headword abbreviation checked against the facsimile; exact expanded target absent from the acquired index. No printing error or acquisition gap established.'
    return dict(classification=cause, diagnostic_reason=reason, target_label=label,
                candidate_destinations=[dict(id=i, headword=index.records[i]['headword'], homonym=index.records[i].get('homonym')) for i in sorted(set(candidates+accepted_candidates))],
                review_status=('printed_abbreviation_reviewed_destination_absent' if reviewed_printed and not candidates
                               else 'editorial_link_reviewed_destination_absent' if reviewed_editorial and not candidates
                               else 'investigation_required'), printed_facsimile_checked=reviewed_printed)


def case_record(entry, ref, unit, index):
    component=next(c for c in entry['components'] if c['id']==ref['component_id'])
    return dict(entry_id=entry['id'], headword=entry['headword'], source_kind=entry['source_kind'],
        source_binding=unit.get('source_binding',ref['source_binding']),
        parent_source_binding=ref['source_binding'],
        source_span=unit.get('source_span',ref['source_span']),
        literal=unit.get('literal',component['source_form']), target_wording=ref['wording'],
        source_url=ref.get('source_url'), sources=entry['sources'],
        component_id=ref['component_id'], member_id=unit.get('member_id'),
        resolution_evidence=unit.get('resolution_evidence',ref.get('resolution_evidence')),
        member_resolution=unit if unit is not ref else None,
        **classify(ref,unit,index))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reader', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args=ap.parse_args()
    if args.output.exists(): ap.error('refuse to overwrite a ledger')
    index=EntryIndex(rows(INDEX)); catalog=json.loads((args.reader/'data.json').read_text())
    counts=collections.Counter(); causes=collections.Counter(); total=0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opener=gzip.open if args.output.suffix=='.gz' else open
    with opener(args.output,'wt',encoding='utf-8') as ledger:
        for meta in catalog['entries']:
            entry=json.loads((args.reader/meta['path']).read_text())
            kind=entry['source_kind']
            for ref in entry['cross_references']:
                counts[kind+':parents:'+ref['status']]+=1
                for unit in ref.get('target_members',[ref]):
                    status=unit.get('resolution_status',unit.get('status'))
                    counts[kind+':targets:'+status]+=1
                    if status=='resolved': continue
                    diagnosis=classify(ref,unit,index)
                    causes[kind+':'+diagnosis['classification']]+=1;total+=1
                    ledger.write(json.dumps(case_record(entry,ref,unit,index),ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(witnesses=len(catalog['entries']),counts=dict(counts),residual=total,causes=dict(causes)),indent=2))


if __name__=='__main__': main()
