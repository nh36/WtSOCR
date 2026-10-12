#!/usr/bin/env python3
"""Preserve forensic residue with bounded diagnostic classifications, never new owners."""
import argparse, collections, gzip, json, re, sqlite3
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,default=Path('work/badw_forensic_structure'));ap.add_argument('--output',type=Path,default=Path('data/badw_forensic_structure'));a=ap.parse_args()
    db=sqlite3.connect('file:'+str(a.work/'semantic.sqlite')+'?mode=ro',uri=True)
    owners=collections.defaultdict(list)
    for entry,raw in db.execute("select entry,record_json from citation where ownership='unresolved'"):
        owners[entry].append(json.loads(raw))
    gaps={}
    with gzip.open(a.output/'header_accounting.jsonl.gz','rt') as f:
        for line in f:
            r=json.loads(line);gaps[r['identity']]=r
    counts=collections.Counter();families=collections.Counter();glyphs=collections.Counter()
    with gzip.open(a.output/'ownership_residue.jsonl.gz','wt') as out, gzip.open(a.output/'pending_structure.jsonl.gz','wt') as pending:
        for line in (a.work/'projections.jsonl').open():
            row=json.loads(line);p=row['packet'];text=p['review_text'];identity=p['identity']
            for r in owners.get(identity,[]):
                span=r['source_span'];r['context']=text[max(0,span['start']-180):min(len(text),span['end']+180)]
                r['source_kind']=p['source_kind'];counts[(p['source_kind'],r['source_structural_family'])]+=1
                out.write(json.dumps(r,ensure_ascii=False)+'\n')
            for g in gaps.get(identity,{}).get('gaps',[]):
                if not g['alphabetic_characters']:continue
                literal=text[g['start']:g['end']]
                if g['family']=='source_decoding_residue':
                    glyphs.update(re.findall(r'⟦UNKNOWN:[^⟧]+⟧',literal))
                if g['family'] not in ('source_heading_pending_type','unparsed_lexical_prose_pending_review'):continue
                # Candidate labels express source grammar, not an accepted interpretation.
                if re.search(r'\b(?:pf\.|fut\.|imp\.|imper\.|Kurzf\.)',literal):family='header_form_or_relation_candidate'
                elif re.search(r'\bauch\b',literal) or (g['start']<20 and literal.lstrip().startswith(',')):family='alias_list_or_header_continuation_candidate'
                elif re.search(r'\b(?:vgl\.|s\.\s*v\.|Abt\.)',literal):family='reference_clause_candidate'
                elif '„' in literal or '“' in literal:family='quotation_or_gloss_candidate'
                elif g['family']=='source_heading_pending_type':family='other_heading_source_text'
                else:family='lexical_prose_without_proven_boundary'
                families[(p['source_kind'],family)]+=g['alphabetic_characters']
                pending.write(json.dumps(dict(identity=identity,source_sha256=p['review_text_sha256'],start=g['start'],end=g['end'],literal=literal,family=family,alphabetic_characters=g['alphabetic_characters'],status='diagnostic_candidate_not_semantic_claim'),ensure_ascii=False)+'\n')
    result=dict(ownership_families=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(counts.items())],pending_alphabetic_families=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(families.items())],unknown_glyph_signatures=dict(glyphs),policy='No owner or decoding mapping inferred from diagnostic family; literal spans preserved.')
    (a.output/'forensic_residue.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
