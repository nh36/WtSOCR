#!/usr/bin/env python3
"""Freeze exact unresolved occurrences and their structural boundary evidence.

Diagnostic classifications never license ownership. Run against the baseline
store before replay; use --name to retain a separate after-replay census.
"""
import argparse
import collections
import gzip
import io
import json
import re
import sqlite3
from pathlib import Path

from badw_bounded_passages import envelopes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--work', type=Path, default=Path('work/badw_forensic_structure'))
    ap.add_argument('--output', type=Path, default=Path('data/badw_forensic_structure'))
    ap.add_argument('--store', default='baseline_dcac.sqlite')
    ap.add_argument('--name', default='passage_baseline')
    args = ap.parse_args()
    db = sqlite3.connect('file:' + str(args.work / args.store) + '?mode=ro', uri=True)
    unresolved = collections.defaultdict(list)
    for identity, raw in db.execute("select entry, record_json from citation where ownership='unresolved'"):
        unresolved[identity].append(json.loads(raw))
    counts = collections.Counter()
    with gzip.GzipFile(filename=str(args.output / (args.name + '.jsonl.gz')), mode='wb', mtime=0) as compressed, io.TextIOWrapper(compressed, encoding='utf-8') as out:
        for line in (args.work / 'projections.jsonl').open():
            row = json.loads(line)
            p = row['packet']
            identity, text = p['identity'], p['review_text']
            if identity not in unresolved:
                continue
            nodes = row['projection']['nodes']
            bounds = envelopes(text)
            layout = []
            offset = 0
            for visual in p.get('source', {}).get('visual_lines', []):
                if not isinstance(visual, dict):
                    continue
                layout.append(dict(visual, start=offset, end=offset+len(visual.get('text', ''))))
                offset += len(visual.get('text', '')) + 1
            for citation in unresolved[identity]:
                a, b = citation['source_span']['start'], citation['source_span']['end']
                containing = [n for n in nodes if n['kind'] != 'citation' and n['start'] <= a < b <= n['end']]
                enclosed = [dict(start=s, end=e, opener=o, literal=text[s:e]) for s, e, o in bounds if s <= a < b <= e]
                context = text[max(0, a-250):min(len(text), b+250)]
                kinds = {n['kind'] for n in containing}
                if any(re.match(r'\s*[\[(]\s*vgl\.', x['literal']) for x in enclosed):
                    family = 'balanced_comparison_enclosure'
                elif any(re.match(r'\s*\(\s*(?:v\.\s*l\.|r\.)', x['literal']) for x in enclosed):
                    family = 'variant_reading_parenthesis'
                elif kinds & {'lexical', 'lexical_parallel'}:
                    family = 'contained_lexical_source_node'
                elif 'example' in kinds:
                    family = 'contained_example_source_node'
                elif 'definition' in kinds:
                    family = 'contained_definition_source_node'
                elif re.search(r'\bvgl\.', context):
                    family = 'comparison_without_accepted_enclosure'
                elif 'heading' in kinds:
                    family = 'heading_source_note'
                else:
                    family = 'unbounded_or_missing_component'
                counts[(p['source_kind'], family)] += 1
                record = dict(citation=citation, identity=identity, source_kind=p['source_kind'],
                    source={k:v for k,v in p.get('source', {}).items() if k in ('source_objects','source_object','page_id','pdf_sha256','url','article_id')}, text_sha256=p['review_text_sha256'],
                    source_span=dict(start=a,end=b), literal=text[a:b], context=context,
                    original_family=citation.get('source_structural_family'), grammar_family=family,
                    containing_components=containing, punctuation_enclosures=enclosed,
                    adjacent_components=[n for n in nodes if n['start'] < b+80 and a-80 < n['end']],
                    layout_lines=[v for v in layout if v['start'] < b and a < v['end']],
                    residual_reason={'balanced_comparison_enclosure':'balanced enclosure alone fails component or local grammar gates', 'variant_reading_parenthesis':'variant enclosure fails exact example containment or local syntax', 'contained_lexical_source_node':'source lexical envelope does not establish an accepted canonical Lex item subclause', 'contained_example_source_node':'example envelope fails balanced quotation or exact citation attachment gates', 'contained_definition_source_node':'definition container does not establish an independently bounded local assertion', 'comparison_without_accepted_enclosure':'comparison marker present but no accepted balanced or terminal clause boundary', 'heading_source_note':'heading does not establish a citable lexical assertion', 'unbounded_or_missing_component':'no independently bounded source component or local assertion'}[family],
                    policy='Diagnostic evidence only; containment and punctuation require grammar-specific validation.')
                out.write(json.dumps(record,ensure_ascii=False)+'\n')
    summary = dict(projection_basis='Current source projection; unresolved citation set from '+args.store, total=sum(counts.values()), families=[dict(source_kind=k[0],family=k[1],count=v) for k,v in sorted(counts.items())])
    (args.output / (args.name+'.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
