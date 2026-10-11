"""Refine structural indicators and run the registered-print zoning adapter.

Offline third pass. Review decisions are separate, hash-bound observations;
none changes source, parser, relationships, or release text.
"""
import collections
import csv
import gzip
import json
import re
from pathlib import Path

from audit_badw_corpus_structure import accounting, file_hash, rows, write_json
from finalize_badw_corpus_structure import OUT, WORK
from postprocess_entry_map import parse_entries


def gap_category(literal):
    if not any(c.isalpha() for c in literal):
        return 'layout'
    if not re.sub(r'\b(?:Lex|pf|imp|pr|fut|vb|skt)\b|[^\w]|\d', '', literal):
        return 'structural_label'
    return 'lexical_or_header_review'


def detailed_indicators(packet, projection):
    text = packet['review_text']; nodes = projection['nodes']
    senses = sorted((n for n in nodes if n['kind'] == 'sense'), key=lambda n:n['start'])
    lex = [n for n in nodes if n['kind'] == 'lexical_parallel']
    for n in lex:
        if senses and not any(s['start'] <= n['start'] < n['end'] <= s['end'] for s in senses):
            yield 'lex_outside_numbered_sense', [[n['start'], n['end']]], {}
    for kind in ('citation', 'lexical_parallel', 'definition', 'example'):
        seen = {}
        for n in (n for n in nodes if n['kind'] == kind):
            key = (n['start'], n['end'])
            if key in seen:
                yield 'duplicate_component', [list(key)], {'kind': kind, 'nodes': [seen[key], n['id']]}
            seen[key] = n['id']
        if kind == 'lexical_parallel':
            for i, n in enumerate(lex):
                for m in lex[i+1:]:
                    if max(n['start'], m['start']) < min(n['end'], m['end']) and (n['start'],n['end']) != (m['start'],m['end']):
                        yield 'overlapping_lex_items', [[n['start'],n['end']], [m['start'],m['end']]], {}
    labels = []
    for s in senses:
        m = re.match(r'\s*(\d+)[.)]', text[s['start']:s['end']])
        if m:
            labels.append(int(m[1]))
            if not re.sub(r'\s*\d+[.)]\s*', '', text[s['start']:s['end']]).strip():
                yield 'empty_numbered_sense', [[s['start'],s['end']]], {}
    if any(a >= b for a,b in zip(labels, labels[1:])):
        yield 'sense_numbering', [[s['start'],s['end']] for s in senses], {'labels':labels, 'nested_label_reuse_requires_review':True}
    for n in (n for n in nodes if n['kind'] == 'definition'):
        literal = re.sub(r'^\s*\d+[.)]\s*', '', text[n['start']:n['end']])
        # Quotation marks alone do not indicate swallowed material.
        if re.search(r'Lex\.|\n\s*\d+[.)]', literal):
            yield 'definition_boundary_cue', [[n['start'],n['end']]], {}


def refine():
    extra=[]; gaps=collections.Counter(); totals=collections.Counter(); examples=collections.defaultdict(list)
    for r in rows(WORK/'projections.jsonl'):
        p=r['packet']; text=p['review_text']; pred=r['projection']
        for a,b in accounting(text,pred['nodes'])[0]:
            category=gap_category(text[a:b]);gaps[category+'_characters']+=b-a
            gaps[category+'_alphabetic']+=sum(c.isalpha() for c in text[a:b]);gaps[category+'_runs']+=1
            if category=='lexical_or_header_review' and len(examples[p['source_kind']])<6:
                examples[p['source_kind']].append(dict(identity=p['identity'],text_sha256=p['review_text_sha256'],span=[a,b],literal=text[a:b]))
        for f,spans,d in detailed_indicators(p,pred):
            extra.append(dict(family=f,identity=p['identity'],source_kind=p['source_kind'],text_sha256=p['review_text_sha256'],spans=spans,details=d))
        totals['entries_over_10_senses']+=int(r['metrics']['senses']>10)
        totals['max_senses']=max(totals['max_senses'],r['metrics']['senses'])
        for n in pred['nodes']:
            if n['kind']=='definition':totals['max_definition_characters']=max(totals['max_definition_characters'],n['end']-n['start'])
    # Retain original machine indicators, with their conservative diagnostic class.
    aa=list(rows(OUT/'anomalies.jsonl.gz'))
    aa=[a for a in aa if a['family'] not in {'lex_outside_numbered_sense','duplicate_component','overlapping_lex_items','empty_numbered_sense','sense_numbering','definition_boundary_cue'}]+extra
    with gzip.GzipFile(filename=str(OUT/'anomalies.jsonl.gz'),mode='wb',mtime=0) as f:
        for a in aa:f.write((json.dumps(a,ensure_ascii=False,sort_keys=True)+'\n').encode())
    families=[f for f in json.loads((OUT/'families.json').read_text()) if f['family'] not in {'lex_outside_numbered_sense','duplicate_component','overlapping_lex_items','empty_numbered_sense','sense_numbering','definition_boundary_cue'}]
    for family in sorted({a['family'] for a in extra}):
        selected=[a for a in extra if a['family']==family]
        families=[f for f in families if f['family']!=family]
        families.append(dict(family=family,entries=len({a['identity'] for a in selected}),occurrences=len(selected),distribution=dict(collections.Counter(a['source_kind'] for a in selected)),classification='indicator_requires_review',examples=selected[:6]))
    write_json(OUT/'families.json',families)
    write_json(OUT/'accounting.json',dict(gaps=dict(gaps),outliers=dict(totals),examples=dict(examples),interpretation='Label exclusions are diagnostics, never silently assigned lexical content. Remaining gaps include alias/header material as well as lexical omissions.'))


def registered_print():
    results=[]; output=[]
    sources=list(csv.DictReader(Path('data/source_pdfs.tsv').open(),delimiter='\t'))
    for source in sources:
        if not source['label']:continue
        volume=source['label'].lower().replace('-', '_')
        path=Path('release/current/text')/(volume+'_corrected_full.txt')
        if file_hash(source['filename'])!=source['sha256']:raise ValueError('registered print source hash changed')
        text=path.read_text();entries,infos,_,validators,summary,_=parse_entries(text,{})
        unbound=[i for i in infos if not i.entry_id]
        results.append(dict(volume=volume,source=source,input_text=str(path),input_text_sha256=file_hash(path),summary=summary,unassigned_nonempty_lines=len(unbound),unassigned_alphabetic=sum(c.isalpha() for i in unbound for c in i.line_text),entry_spans_over_150_lines=sum(e.line_count>150 for e in entries),max_entry_lines=max(e.line_count for e in entries),canonical_reader_status='adapter_not_available',boundary_accuracy='not_independent_gold'))
        output.extend(dict(volume=volume,entry_id=e.entry_id,headword=e.headword_latin,start_page=e.start_page,start_line=e.start_line,end_page=e.end_page,end_line=e.end_line,line_count=e.line_count) for e in entries)
        print('registered print',volume,len(entries),flush=True)
    with (OUT/'print_entries.tsv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]),delimiter='\t');w.writeheader();w.writerows(output)
    write_json(OUT/'registered_print.json',dict(volumes=results,total_entry_groups=len(output),limitation='Legacy zoning replay only: no canonical sense/citation/reader adapter exists for registered OCR. Internal legacy normalize_line is not written back; input and original PDF hashes retained. Entry-group counts are not added to online witness counts as distinct lexical entries.'))


def seal():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for name in ('audit_badw_corpus_structure.py','finalize_badw_corpus_structure.py','review_badw_corpus_structure.py','postprocess_entry_map.py'):
        p=Path('scripts')/name;manifest['code_sha256'][str(p)]=file_hash(p)
    manifest['outputs_sha256']={str(p):file_hash(p) for p in sorted(OUT.glob('*')) if p.is_file() and p.name!='manifest.json'}
    write_json(OUT/'manifest.json',manifest)


if __name__=='__main__':
    refine();registered_print();seal()
