"""Seal reviewed diagnostic conclusions after the three offline replay passes.

Review decisions are checked-in source-bound observations, not generated gold.
Reapplication fails closed if the holdout selection or source contract changes.
"""
import collections
import csv
import json
from pathlib import Path

from audit_badw_corpus_structure import file_hash, rows, write_json
from finalize_badw_corpus_structure import OUT, WORK
from review_badw_corpus_structure import seal

PRIORITIES = [
    ('lex_sense_passage_model', ['lex_outside_numbered_sense','overlapping_lex_items','citation_owner_unresolved'], 'parser + canonical model', 'high', 'Lex. outside HTML sense envelopes and duplicated PDF Lex. components; bibliography identity is retained but semantic citation ownership is almost entirely unestablished.', 'Build typed Lex. items inside explicit sense envelopes, with exact citable-passage relations. Test source-bound boundaries before assigning owners.'),
    ('pdf_xref_binding', ['xref_component_missing','xref_unresolved'], 'canonical adapter + reader', 'high', 'All PDF target candidates remain unresolved under the current source binding; reader reference records cannot bind their existing source nodes. Most labels have a unique exact index candidate.', 'Carry stable source node/record identifiers through PDF adaptation; review target extents and homonym qualifiers, then replay exact target reviews.'),
    ('contextual_language_typing', ['language_evidence_untyped','language_conflict'], 'parser + canonical model', 'high', 'Explicit Sanskrit cues/correspondences are untyped, especially PDF Lex.; some HTML terms are assigned contradictory languages.', 'Use explicit skt./correspondence structure and source typography; avoid character-shape language guessing.'),
    ('registered_print_adapter', [], 'canonical model + legacy zoning', 'high', 'Four registered print PDFs run through legacy entry zoning only; no canonical sense/citation/reader adapter exists. Long entry groups are boundary candidates, not independently proved errors.', 'Design a print OCR witness adapter preserving original coordinates; review the 103 >150-line groups before treating them as reliable entries.'),
    ('unaccounted_headers_and_clauses', ['lexical_gap','pdf_unassigned_candidate'], 'parser + model / source review', 'medium', 'Alphabetic gaps include aliases, verb headers and source labels; raw gap counts overstate lexical loss. Holdout exposes displaced PDF header markers.', 'Type header/alias/verb material where source evidence supports it. Review remaining lexical gaps and PDF decoding failures by exact spans.'),
    ('inline_citation_grammar', ['ignored_citation_cue','citation_identity_unresolved'], 'parser / scholarly ambiguity', 'medium', 'Inline references such as vgl. PW 5.3 remain unextracted. Numeric parentheses also generate false positives; unresolved authority is distinct from unresolved owner.', 'Add general inline citation grammar after source review; preserve unresolved edition/reference identities rather than fuzzy resolving them.'),
    ('source_contract_failures', ['pipeline_exception'], 'canonical projection / integration', 'high', 'Two HTML witnesses raise duplicate typed-span exceptions. One existing PDF semantic overlay fails its endpoint/source contract.', 'Isolate duplicate-span construction and investigate the one exact overlay conflict; do not weaken validation to force acceptance.'),
    ('definition_and_numbered_sense_boundaries', ['definition_boundary_cue','empty_numbered_sense','crossing_components'], 'parser / source ambiguity', 'medium', 'Conservative boundary indicators require review: quote-only definitions and punctuation overlaps are frequently harmless; three empty numbered senses remain candidates.', 'Review the conservative Lex./later-number boundary queue, using hierarchical labels; handle malformed source quotes without silently swallowing adjacent items.'),
]


def main():
    packets={r['packet']['identity']:r['packet'] for r in rows(WORK/'holdout_packets.jsonl')}
    reviews={r['identity']:r for r in rows(OUT/'holdout_review.jsonl')}
    holdout=json.loads((OUT/'holdout.json').read_text())
    selected={r['metrics']['identity'] for r in holdout['cases']}
    if selected!=set(reviews) or selected!=set(packets):raise ValueError('reviewed holdout selection changed')
    for case in holdout['cases']:
        identity=case['metrics']['identity']; review=reviews[identity]; p=packets[identity]
        if review['text_sha256']!=p['review_text_sha256'] or case['metrics']['text_sha256']!=review['text_sha256']:raise ValueError('review text changed')
        for s in review['evidence_spans']:
            if p['review_text'][s['start']:s['end']]!=s['literal']:raise ValueError('review literal changed')
        case['review_status']=review['status']
    holdout['review_results']=dict(collections.Counter(r['status'] for r in reviews.values()))
    holdout['interpretation']='Fresh deliberately stratified sample, selected before inspection. Local defect observations are not statistical corpus accuracy or reviewed citation ownership. No parser tuning performed.'
    write_json(OUT/'holdout.json',holdout)
    anomalies=list(rows(OUT/'anomalies.jsonl.gz'))
    ranked=[]
    for rank,(name,families,layer,impact,cause,action) in enumerate(PRIORITIES,1):
        aa=[a for a in anomalies if a['family'] in families]
        ranked.append(dict(rank=rank,family=name,component_families=families,affected_entries=len({a['identity'] for a in aa}),occurrences=len(aa),html_entries=len({a['identity'] for a in aa if a['source_kind']=='html'}),pdf_entries=len({a['identity'] for a in aa if a['source_kind']=='pdf'}),occurrence_distribution=dict(collections.Counter(a['source_kind'] for a in aa)),layer=layer,usability_impact=impact,likely_cause=cause,recommended_action=action,count_scope='Union of indicators, not confirmed defect count' if families else '24,528 legacy entry groups; no canonical adapter',examples=[dict(identity=a['identity'],text_sha256=a['text_sha256'],spans=a['spans'],indicator=a['family']) for a in aa[:3]]))
    write_json(OUT/'priorities.json',ranked)
    with (OUT/'priorities.tsv').open('w') as f:
        fields=['rank','family','affected_entries','occurrences','html_entries','pdf_entries','layer','usability_impact','likely_cause','recommended_action','count_scope']
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t',extrasaction='ignore');w.writeheader();w.writerows(ranked)
    summary=json.loads((OUT/'summary.json').read_text());summary['counts']['anomaly_occurrences']=len(anomalies)
    summary['entry_anomaly_distribution']=dict(collections.Counter(str(n) for n in collections.Counter(a['identity'] for a in anomalies).values()))
    summary['holdout_review']=holdout['review_results']
    summary['next_tranche']='Typed Lex. items within sense envelopes and exact citable-passage ownership; preserve source spans and bibliography identities.'
    summary['random_review_assessment']='Further arbitrary entry batches have diminishing returns for discovering these recurrent families. Retain fresh stratified holdouts and targeted source review for validation and scholarly ambiguities.'
    write_json(OUT/'summary.json',summary)
    seal()
    manifest=json.loads((OUT/'manifest.json').read_text())
    manifest['code_sha256']['scripts/summarize_badw_corpus_structure.py']=file_hash(Path(__file__))
    print_inputs={}
    for v in json.loads((OUT/'registered_print.json').read_text())['volumes']:
        print_inputs[v['input_text']]=v['input_text_sha256']; print_inputs[v['source']['filename']]=v['source']['sha256']
    manifest['registered_print_inputs_sha256']=print_inputs
    write_json(OUT/'manifest.json',manifest)


if __name__=='__main__':main()
