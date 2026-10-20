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
    parsed = unit.get('parsed_target') or ref.get('parsed_target') or {}
    label = parsed.get('lexical_target') or unit.get('lexical_target') or unit.get('wording') or unit.get('literal') or ''
    url = ref.get('source_url')
    if url:
        parts = urlsplit(url).path.split('/')
        if len(parts) == 4 and parts[1] == 'lemma':
            label = unquote(parts[2])
    candidates = sorted(index.labels.get(label, set()))
    accepted_candidates = unit.get('candidate_entry_ids', [])
    status = unit.get('resolution_status', unit.get('status'))
    if status == 'ambiguous':
        cause, reason = 'ambiguity', 'Several exact homonym identities; source qualifier does not select one.'
    elif not label.strip('↑↓ ,'):
        cause, reason = 'parser_failure', 'Arrow retained but no lexical target inside the extracted span; DOM boundary review required.'
    elif candidates:
        cause, reason = 'identity_or_manifestation_mismatch', 'Exact label exists, but explicit source homonym/manifestation identity is not established. Facsimile review required.'
    else:
        cause, reason = 'missing_exact_identity', 'No exact acquired headword. Acquisition gap, source error and decoding remain competing explanations; not a confirmed printing error.'
    return dict(classification=cause, diagnostic_reason=reason, target_label=label,
                candidate_destinations=[dict(id=i, headword=index.records[i]['headword'], homonym=index.records[i].get('homonym')) for i in sorted(set(candidates+accepted_candidates))],
                review_status='investigation_required', printed_facsimile_checked=False)


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
                    component=next(c for c in entry['components'] if c['id']==ref['component_id'])
                    ledger.write(json.dumps(dict(entry_id=entry['id'], headword=entry['headword'], source_kind=kind,
                        source_binding=ref['source_binding'], source_span=unit.get('source_span',ref['source_span']),
                        literal=unit.get('literal',component['source_form']), target_wording=ref['wording'],
                        source_url=ref.get('source_url'), sources=entry['sources'],
                        component_id=ref['component_id'], member_id=unit.get('member_id'),
                        resolution_evidence=unit.get('resolution_evidence',ref.get('resolution_evidence')),
                        **diagnosis),ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps(dict(witnesses=len(catalog['entries']),counts=dict(counts),residual=total,causes=dict(causes)),indent=2))


if __name__=='__main__': main()
