#!/usr/bin/env python3
"""Partition exact baseline gaps without widening canonical lexical components."""
import argparse, collections, gzip, hashlib, json, re, sqlite3
from pathlib import Path
from audit_badw_corpus_structure import accounting
from badw_header_structure import header_fields, heading_fragments

def classify(text, a, b, headers, headings, semantic):
    for h in semantic:
        if h["start"] <= a and b <= h["end"]:
            return h["family"]
    for h in headers:
        if h['start'] <= a and b <= h['end']:
            return 'typed_' + h['header_kind']
    if any(h['visible_text_start'] <= a and b <= h['visible_text_end'] for h in headings):
        return 'source_heading_pending_type'
    literal=text[a:b]
    if not any(c.isalpha() for c in literal): return 'punctuation_layout'
    if 'UNKNOWN' in literal or '\ufffd' in literal: return 'source_decoding_residue'
    if re.fullmatch(r'[\s.,;:–—-]*(?:Lex\.|skt\.|vgl\.|Anm\.|r\.)[\s.,;:–—-]*', literal): return 'source_structural_label'
    if re.search(r'\bLex\.',literal): return 'unparsed_lex_clause'
    if re.search(r'[→↓↑]',literal): return 'cross_reference_residue'
    return 'unparsed_lexical_prose_pending_review'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,default=Path('work/badw_semantic_residue'));ap.add_argument('--output',type=Path,default=Path('data/badw_semantic_residue'));args=ap.parse_args()
    db=sqlite3.connect('file:'+str(args.work/'semantic.sqlite')+'?mode=ro',uri=True)
    semantic=collections.defaultdict(list)
    for table,family in [('language_form','typed_Sanskrit_form'),('citation','typed_citation'),('lex_item','typed_Lex_item')]:
        for entry,raw in db.execute('select entry,record_json from '+table):
            r=json.loads(raw);span=r.get('source_span',r)
            semantic[entry].append(dict(start=span['start'],end=span['end'],family=family))
    for entry, raw in db.execute('select entry,record_json from passage'):
        r = json.loads(raw)
        if r.get('passage_type') in ('bounded_comparison', 'variant_reading', 'definition_source_note', 'terminal_comparison'):
            span = r.get('source_span', r)
            semantic[entry].append(dict(start=span['start'], end=span['end'], family='typed_'+r['passage_type']))
    db.close()
    counts=collections.Counter();alpha=collections.Counter();candidates=collections.Counter();headcounts=collections.Counter();examples=collections.defaultdict(list);total=0
    with (args.work/'projections.jsonl').open() as src, gzip.open(args.output/'header_accounting.jsonl.gz','wt',encoding='utf8') as out:
        for line in src:
            row=json.loads(line);p=row['projection'];packet=row['packet'];text=packet['review_text'];identity=packet['identity'];headers=header_fields(p,text);headings=heading_fragments(p)
            from badw_pdf_structure_recovery import recover
            recovered=recover(p,text)
            semantic[identity].extend(dict(start=n['start'],end=n['end'],family=('typed_bounded_'+n['kind'] if n['structural_recovery'].get('rule')=='pdf-bounded-quotation-v1' else 'typed_mixed_clause_definition' if n['structural_recovery'].get('rule')=='pdf-mixed-clause-v1' else 'typed_opening_definition')) for n in recovered['nodes'] if n.get('structural_recovery'))
            headcounts.update(h['header_kind'] for h in headers)
            typed=sorted(semantic[identity],key=lambda h:h['end']-h['start'])
            gaps,lexical,n=accounting(text,p['nodes']);total+=n
            boundaries={h[k] for h in headers for k in ('start','end')}
            boundaries.update(h[k] for h in headings for k in ('visible_text_start','visible_text_end'))
            boundaries.update(h[k] for h in typed for k in ('start','end'))
            # Split labels from preceding lexical prose rather than calling an
            # entire residual prefix an unparsed Lex. block. The raw gaps stay.
            for marker in re.finditer(r'\b(?:Lex\.|skt\.|vgl\.|Anm\.)', text):
                boundaries.update((marker.start(), marker.end()))
            records=[]
            for a,b in gaps:
                cuts=[a]+sorted(v for v in boundaries if a<v<b)+[b]
                for x,y in zip(cuts,cuts[1:]):
                    family=classify(text,x,y,headers,headings,typed);nalpha=sum(c.isalpha() for c in text[x:y]);counts[(packet['source_kind'],family)]+=1;alpha[(packet['source_kind'],family)]+=nalpha
                    records.append(dict(start=x,end=y,family=family,alphabetic_characters=nalpha))
                    if nalpha and len(examples[family])<8:examples[family].append(dict(identity=identity,start=x,end=y,literal=text[x:y],source_sha256=packet['review_text_sha256']))
            residual=[]
            for c in p.get('unassigned_source_candidates',[]):
                rec=c['record'];collection=c['collection']
                family='printed_correction_apparatus' if collection=='correction_apparatus' else 'source_candidate_'+collection
                candidates[(family,rec.get('status','unspecified'))]+=1
                residual.append(dict(family=family,source_collection=collection,index=c['index'],record=rec))
            if records or residual:
                out.write(json.dumps(dict(identity=identity,source_kind=packet['source_kind'],source_sha256=packet['review_text_sha256'],gaps=records,source_candidates=residual),ensure_ascii=False)+'\n')
    assert sum(alpha.values())==total
    def table(counter):return [dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(counter.items())]
    summary=dict(version='exact-header-accounting-v3',source_projection_sha256=hashlib.sha256((args.work/'projections.jsonl').read_bytes()).hexdigest(),baseline_unassigned_alphabetic_characters=total,partition_runs=table(counts),alphabetic_characters=table(alpha),canonical_header_fields=dict(headcounts),pdf_candidates=[dict(family=k[0],status=k[1],count=v) for k,v in sorted(candidates.items())],examples=dict(examples),policy='Pending heading/prose classifications are diagnostics, not accepted semantic containers. Printed correction proposals remain unapplied source observations.')
    (args.output/'header_accounting.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('examples','partition_runs')},ensure_ascii=False))
if __name__=='__main__':main()
