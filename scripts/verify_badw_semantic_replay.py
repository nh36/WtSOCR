"""Compact post-replay checks; does not rerun extraction or alter source evidence."""
import collections
import csv
import hashlib
import gzip
import json
import sqlite3
from pathlib import Path
from badw_semantic_hierarchy import hierarchy
from badw_dictionary_entry_view import entry_view
from resolve_badw_cross_references import EntryIndex

OUT=Path('data/badw_semantic_hierarchy')
WORK=Path('work/badw_semantic_hierarchy')
BASE=Path('data/badw_corpus_structure')

def rows(path):
    with path.open() as f:
        for line in f:yield json.loads(line)

def refine_boundary_diagnostics():
    # The frozen baseline ran this same diagnostic pass. Retain raw boundary
    # warnings; canonical Lex. grouping is measured separately, never by
    # reintroducing flat block/item duplicates as semantic anomalies.
    from review_badw_corpus_structure import detailed_indicators, gap_category
    from audit_badw_corpus_structure import accounting
    selected = {'empty_numbered_sense', 'sense_numbering', 'definition_boundary_cue'}
    extra = []; gaps = collections.Counter()
    for r in rows(WORK/'projections.jsonl'):
        packet, projection = r['packet'], r['projection']
        text = packet['review_text']
        for a, b in accounting(text, projection['nodes'])[0]:
            category = gap_category(text[a:b])
            gaps[category+'_characters'] += b-a
            gaps[category+'_alphabetic'] += sum(c.isalpha() for c in text[a:b])
            gaps[category+'_runs'] += 1
        for family, spans, details in detailed_indicators(packet, projection):
            if family in selected:
                extra.append(dict(family=family, identity=packet['identity'],
                    source_kind=packet['source_kind'], text_sha256=packet['review_text_sha256'],
                    spans=spans, details=details))
    with gzip.open(OUT/'anomalies.jsonl.gz', 'rt') as f:
        anomalies = [json.loads(line) for line in f]
    anomalies = [a for a in anomalies if a['family'] not in selected] + extra
    with gzip.GzipFile(filename=str(OUT/'anomalies.jsonl.gz'), mode='wb', mtime=0) as f:
        for a in anomalies:
            f.write((json.dumps(a, ensure_ascii=False, sort_keys=True)+'\n').encode())
    families = json.loads((OUT/'families.json').read_text())
    families = [r for r in families if r['family'] not in selected]
    for family in sorted({a['family'] for a in extra}):
        found = [a for a in extra if a['family']==family]
        families.append(dict(family=family, entries=len({a['identity'] for a in found}),
            occurrences=len(found), distribution=dict(collections.Counter(a['source_kind'] for a in found)),
            classification='indicator_requires_review', examples=found[:6]))
    (OUT/'families.json').write_text(json.dumps(families, ensure_ascii=False, indent=2, sort_keys=True)+'\n')
    (OUT/'accounting.json').write_text(json.dumps(dict(gaps=dict(gaps),
        interpretation='Same layout/label diagnostic as baseline; no source coverage widened.'), indent=2, sort_keys=True)+'\n')
    summary = json.loads((OUT/'summary.json').read_text())
    summary['counts']['anomaly_occurrences'] = len(anomalies)
    summary['entry_anomaly_distribution'] = dict(collections.Counter(str(v) for v in collections.Counter(a['identity'] for a in anomalies).values()))
    (OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)+'\n')


def main():
    global OUT, WORK, BASE
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refine-boundaries', action='store_true')
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--baseline', type=Path, default=BASE)
    args = parser.parse_args()
    OUT, WORK, BASE = args.output, args.work, args.baseline
    if args.refine_boundaries:
        refine_boundary_diagnostics()
    db=sqlite3.connect('file:'+str(WORK/'semantic.sqlite')+'?mode=ro',uri=True)
    by_entry=collections.defaultdict(list)
    for row in db.execute('SELECT entry,record_json FROM lex_item'):
        by_entry[row[0]].append(json.loads(row[1]))
    duplicate=overlap=0
    for items in by_entry.values():
        seen=set();items.sort(key=lambda x:(x['start'],x['end']))
        for i,item in enumerate(items):
            span=(item['start'],item['end']);duplicate+=span in seen;seen.add(span)
            overlap+=sum(previous['end']>item['start'] for previous in items[:i])
    def table(path):
        with path.open() as f:return {r['identity']:r for r in csv.DictReader(f,delimiter='\t')}
    old,new=table(BASE/'entries.tsv'),table(OUT/'entries.tsv'); common=old.keys()&new.keys()
    accounting={k:dict(baseline=sum(int(old[i].get(k,0)) for i in common),current=sum(int(new[i].get(k,0)) for i in common)) for k in ('unassigned_alphabetic','unassigned_characters','lexical_gap_runs')}
    family_counts=[]
    for path in (BASE/'anomalies.jsonl.gz',OUT/'anomalies.jsonl.gz'):
        counts=collections.Counter()
        with gzip.open(path,'rt') as f:
            for line in f:
                r=json.loads(line)
                if r['identity'] in common:counts[r['family']]+=1
        family_counts.append(counts)
    comparison={k:dict(baseline=family_counts[0][k],current=family_counts[1][k]) for k in sorted(set(family_counts[0])|set(family_counts[1]))}
    index=EntryIndex(list(rows(Path('work/badw_relationship_targets_20261005/actual_entry_index.jsonl'))))
    frozen=[]
    for r in (r for path in (Path('work/badw_corpus_structure/holdout_packets.jsonl'),
                             Path('work/badw_semantic_hierarchy/holdout_packets.jsonl'))
              for r in rows(path)):
        p=r['projection'];text=r['packet']['review_text'];semantic=hierarchy(p,text)
        refs=[]
        if p['source_kind']=='html':refs=[index.resolve_manifestation(x) for x in p['original_records'] if x.get('record_type')=='cross_reference']
        else:
            for c in p['original_structure']['candidates']['cross_references']:
                refs.append(index.resolve_source_candidate(dict(marker=c.get('marker'),target_label=c.get('target_label_candidate',''),source_candidate=c), structure=p['original_structure'], text=text))
        reader=r['reader'];entry=dict(id=reader['id'],headword=reader['headword'],homonym=reader['homonym'],stable_url=reader['source_url'])
        bibliography={(p['identity'],n['id']):c['bibliography'] for n,c in zip((n for n in p['nodes'] if n['kind']=='citation'),reader['citations'])}
        view=entry_view(dict(projection=p,entry=entry,review_text=text,cross_references=refs),bibliography)
        assert ''.join(s['text'] for s in view['segments'])==text
        assert [c['accepted_authority_ids'] for c in view['citations']]==[c['accepted_authority_ids'] for c in reader['citations']]
        frozen.append(dict(identity=p['identity'],source_kind=p['source_kind'],text_sha256=p['review_text_sha256'],reader_integrity='passed',lex_items=len(semantic['lex_items']),passage_owners=len(semantic['citation_ownership']),resolved_xrefs=sum(x['status']=='resolved' for x in view['cross_references']),unresolved_xrefs=sum(x['status']!='resolved' for x in view['cross_references']),scope='Frozen source/structure replay; original manual observations retained. No tuning to this sample.'))
    with (OUT/'frozen_holdout_replay.jsonl').open('w') as f:
        for r in frozen:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')
    result=dict(common_entries=len(common),newly_projected=sorted(new.keys()-old.keys()),common_accounting=accounting,anomaly_comparison=comparison,canonical_lex_duplicate_spans=duplicate,canonical_lex_overlapping_pairs=overlap,frozen_holdout_reader_passes=len(frozen),foreign_key_violations=list(db.execute('PRAGMA foreign_key_check')),store_rows={table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('lex_item','passage','citation','citation_passage','xref')},script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    manifest=json.loads((OUT/'manifest.json').read_text())
    manifest['outputs_sha256']={str(p):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(OUT.glob('*')) if p.is_file() and p.name not in ('manifest.json','anomalies.jsonl')}
    manifest['code_sha256']['scripts/verify_badw_semantic_replay.py']=result['script_sha256']
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='anomaly_comparison'},indent=2))

if __name__=='__main__':main()
