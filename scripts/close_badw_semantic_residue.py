#!/usr/bin/env python3
"""Seal reviewed citation cues and ownership transitions against pinned stores."""
import collections, json, sqlite3
from pathlib import Path

ROOT=Path('data/badw_semantic_residue')
def records(path):
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    result={i:json.loads(raw) for i,raw in db.execute('select id,record_json from citation')}
    db.close();return result

def main():
    baseline=records(Path('work/badw_contextual_semantics/semantic.sqlite'))
    previous=records(Path('work/badw_relationship_closure/semantic.sqlite'))
    current=records(Path('work/badw_semantic_residue/semantic.sqlite'))
    byentry=collections.defaultdict(list)
    for i,r in current.items():byentry[r['source_binding']['identity']].append((i,r))
    cues=[]
    for line in Path('data/badw_contextual_semantics/residual_review.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r.get('reviewed_classification')!='genuine_missed_citation':continue
        hits=[]
        for i,c in byentry[r['identity']]:
            s=c['source_span']
            if any(s['start']<b and a<s['end'] for a,b in r['source_spans']):
                assert c['source_binding']['text_sha256']==r['text_sha256']
                hits.append(dict(id=i,literal=c['source_form'],source_span=s,accepted_authority_ids=c.get('accepted_authority_ids',[]),ownership=c['ownership'],residual_reason=c.get('ownership_residual_reason')))
        cues.append(dict(review=r,extracted=bool(hits),citations=hits))
    transitions=[]
    for i,r in baseline.items():
        if r['ownership']!='unresolved':continue
        current_id=i
        transition_evidence='stable_source_span_id'
        if i not in current:
            old=r['source_span']
            hits=[(j,c) for j,c in byentry[r['source_binding']['identity']]
                  if c['source_binding']==r['source_binding']
                  and c['source_span']['start']==old['start']
                  and c['source_span']['end']>=old['end']
                  and c['source_form'].startswith(r['source_form'])]
            assert len(hits)==1, (i, hits)
            current_id,c=hits[0]
            transition_evidence='same_source_hash_and_start_literal_prefix_extended_locator'
        else:
            c=current[i]
        transitions.append(dict(id=i,current_id=current_id,transition_evidence=transition_evidence,identity=r['source_binding']['identity'],source_sha256=r['source_binding']['text_sha256'],source_span=r['source_span'],literal=r['source_form'],origin='old_baseline_unresolved' if i in previous else 'new_contextual_citation',baseline_family=r.get('source_structural_family'),current_ownership=c['ownership'],current_reason=c.get('ownership_residual_reason'),current_family=c.get('source_structural_family')))
    for filename,rows in [('citation_cue_closure.jsonl',cues),('ownership_transitions.jsonl',transitions)]:
        (ROOT/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    unresolved=[r for r in current.values() if r['ownership']=='unresolved']
    summary=dict(reviewed_cues=len(cues),extracted_cues=sum(r['extracted'] for r in cues),resolved_cues=sum(any(c['accepted_authority_ids'] for c in r['citations']) for r in cues),owned_cues=sum(any(c['ownership']!='unresolved' for c in r['citations']) for r in cues),baseline_unresolved=len(transitions),baseline_origin=dict(collections.Counter(r['origin'] for r in transitions)),baseline_newly_owned=sum(r['current_ownership']!='unresolved' for r in transitions),current_unresolved=len(unresolved),current_families=dict(collections.Counter(r.get('source_structural_family','unspecified') for r in unresolved)),current_reasons=dict(collections.Counter(r.get('ownership_residual_reason','unspecified') for r in unresolved)),policy='Identity does not imply ownership. Entry-owned passages have bounded local evidence; unresolved clauses are not assigned by proximity.')
    (ROOT/'residue_closure.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
if __name__=='__main__':main()
