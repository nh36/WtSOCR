#!/usr/bin/env python3
"""Mechanical coordinate diagnostics; unmatched text is not proof of absent geometry."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
from itertools import zip_longest
from badw_qa_pdf_coordinates import normal


def compare_predictions(baseline, current):
    """Stream pinned witness inventories; never label a ranking change correct."""
    counts=Counter();changes=[]
    with baseline.open() as old, current.open() as new:
        for a,b in zip_longest(old,new):
            if a is None or b is None:
                raise ValueError('different witness inventory lengths')
            a,b=json.loads(a),json.loads(b)
            if (a['source_id'],a['html_sha256']) != (b['source_id'],b['html_sha256']):
                raise ValueError('different ordered source identities/checksums')
            counts['witnesses']+=1
            before,after=a['proposed'],b['proposed']
            first=lambda rows: rows[0]['anchor'] if rows else None
            if first(before)!=first(after):
                counts['changed_top_predictions']+=1
                changes.append(dict(source_id=b['source_id'],before=first(before),
                                    after=first(after),assessment='unassessed'))
            prior={p['anchor']:p for p in before}
            for p in after:
                q=prior.get(p['anchor'])
                if q:
                    counts['shared_proposals']+=1
                    counts['changed_definition_evidence']+=p['definition_evidence']!=q['definition_evidence']
                    counts['changed_evidence_lines']+=p['evidence_lines']!=q['evidence_lines']
            reviewed=a.get('eligible_for_original_print_link',False)
            counts['previously_reviewed_attachable']+=reviewed
            counts['reviewed_attachment_status_changed']+=reviewed != b.get('eligible_for_original_print_link',False)
            if reviewed:
                counts['reviewed_page_changed']+=a.get('reviewed_page')!=b.get('reviewed_page')
            counts['machine_eligible']+=b['machine_publication']['eligible']
    return dict(counts=dict(counts),changed_predictions=changes,
                authority='Ranking changes are unassessed; unchanged reviewed attachment metadata is not machine recovery of lexical identity.')


def report(database):
    db=sqlite3.connect('file:'+str(database.resolve())+'?mode=ro',uri=True)
    families=defaultdict(Counter);pages=defaultdict(lambda:[0,0])
    for family,page,body in db.execute('SELECT family,page,body FROM lines ORDER BY family,page,line'):
        row=json.loads(body);counts=families[family]
        mapping=row['coordinate_reconciliation'];status=mapping['status']
        old,new=row.get('legacy_coordinate'),row.get('coordinate')
        counts['qa_lines']+=1;counts[status]+=1
        counts['legacy_located']+=bool(old);counts['reconciled_located']+=bool(new)
        counts['newly_located']+=bool(new and not old)
        counts['previously_located_now_abstained']+=bool(old and not new)
        if old and new:
            a,b=old['box'],new['box']
            overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            counts['both_located_disjoint_boxes']+=overlap==0
        text=row['line_text']
        # Overlapping descriptive traits, not a causal diagnosis or error label.
        prefix='unlocated_trait:' if not new else 'located_trait:'
        counts[prefix+'short_normalized_under_10']+=len(normal(text))<10
        counts[prefix+'contains_hyphen']+=('-' in text or '‐' in text)
        counts[prefix+'contains_tibetan']+=any('\u0f00'<=c<='\u0fff' for c in text)
        if new:
            counts['multiple_pdf_lines']+=len(new.get('pdf_lines',[]))>1
            counts['context_or_sequence']+=status in ('unique_context','unique_sequence')
        pages[family,page][0]+=1;pages[family,page][1]+=bool(new)
    for (family,page),(total,located) in pages.items():
        families[family]['physical_pages']+=1
        families[family]['pages_at_least_95pct']+=located/total>=.95
    return dict(by_family={k:dict(v) for k,v in sorted(families.items())},
                interpretation='Disjoint boxes require inspection, not automatic error labels. Unlocated lines may have recoverable physical positions. Traits overlap and do not prove causes. No accuracy claim without image observations.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline',type=Path,help='Optional baseline witnesses.jsonl for streamed prediction comparison')
    a=p.parse_args();value=report(a.database)
    if a.baseline:
        value['prediction_comparison']=compare_predictions(a.baseline,a.database.parent/'witnesses.jsonl')
    a.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value['by_family'],sort_keys=True))

if __name__=='__main__':main()
