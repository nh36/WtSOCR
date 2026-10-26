#!/usr/bin/env python3
"""Mechanical coordinate diagnostics; unmatched text is not proof of absent geometry."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3
from itertools import zip_longest, groupby
from badw_qa_pdf_coordinates import normal
from badw_print_reconstruction import column_of


def evidence_snapshot(proposal):
    """Retain evidence for assessment, without inferring correctness from overlap."""
    if proposal is None:
        return None
    return {key:proposal.get(key) for key in (
        'anchor','family','physical_page','line','heading_text','score','printed_evidence',
        'evidence_lines','definition_evidence','segmentation','reconstruction')}


def evidence_delta(before, after):
    """Feature direction is not a judgment of lexical correctness."""
    old=before.get('definition_evidence',{});new=after.get('definition_evidence',{})
    keys=('rare_definition_tokens','citation_tokens','definition_shared_tokens')
    delta={key:len(new.get(key,[]))-len(old.get(key,[])) for key in keys}
    values=list(delta.values())
    direction=('stronger_overlap' if any(v>0 for v in values) and all(v>=0 for v in values)
               else 'weaker_overlap' if any(v<0 for v in values) and all(v<=0 for v in values)
               else 'different_or_equal_overlap')
    return dict(token_count_changes=delta,feature_direction=direction,
                correctness='unassessed')


def crossed_candidates(proposal, db):
    """Identify plausible start hypotheses inside a span, not actual articles."""
    if db is None:
        return dict(status='not_checked_without_source_index',candidates=[])
    refs=proposal.get('reconstruction',{}).get('refs')
    if not refs:
        refs=[(proposal.get('physical_page'),line) for line in proposal.get('evidence_lines',[])]
    candidates=[]
    by_page=defaultdict(list)
    for page,line in refs:
        by_page[page].append(line)
    for page,lines in sorted(by_page.items()):
        for aid,body in db.execute('SELECT aid,body FROM starts WHERE family=? AND page=? AND line BETWEEN ? AND ?',
                                  (proposal.get('family'),page,min(lines),max(lines))):
            if aid!=proposal.get('anchor'):
                row=json.loads(body)
                candidates.append(dict(anchor=aid,line=row.get('line'),heading=row.get('text',row.get('line_text'))))
    return dict(status='mechanical_hypotheses_not_verified_boundaries',candidates=candidates)


def compare_predictions(baseline, current, db=None):
    """Stream pinned witness inventories; never label a ranking change correct."""
    counts=Counter();changes=[];evidence_changes=[]
    with baseline.open() as old, current.open() as new:
        for a,b in zip_longest(old,new):
            if a is None or b is None:
                raise ValueError('different witness inventory lengths')
            a,b=json.loads(a),json.loads(b)
            if (a['source_id'],a['html_sha256']) != (b['source_id'],b['html_sha256']):
                raise ValueError('different ordered source identities/checksums')
            counts['witnesses']+=1
            before,after=a['proposed'],b['proposed']
            local_before=a.get('local_ranking',before);local_after=b.get('local_ranking',after)
            local_first=lambda rows: rows[0]['anchor'] if rows else None
            counts['changed_local_top_predictions']+=local_first(local_before)!=local_first(local_after)
            first=lambda rows: rows[0]['anchor'] if rows else None
            if first(before)!=first(after):
                counts['changed_top_predictions']+=1
                changes.append(dict(source_id=b['source_id'],before=first(before),
                                    after=first(after),assessment='unassessed',
                                    original=evidence_snapshot(before[0] if before else None),
                                    reconstructed=evidence_snapshot(after[0] if after else None)))
            prior={p['anchor']:p for p in before}
            for p in after:
                q=prior.get(p['anchor'])
                if q:
                    counts['shared_proposals']+=1
                    counts['changed_definition_evidence']+=p['definition_evidence']!=q['definition_evidence']
                    counts['changed_evidence_lines']+=p['evidence_lines']!=q['evidence_lines']
                    if (p['definition_evidence'],p['evidence_lines']) != (q['definition_evidence'],q['evidence_lines']):
                        evidence_changes.append(dict(source_id=b['source_id'],anchor=p['anchor'],
                            original=evidence_snapshot(q),reconstructed=evidence_snapshot(p),
                            assessment='unassessed',
                            feature_comparison=evidence_delta(q,p),
                            original_intervening_candidates=crossed_candidates(q,db),
                            reconstructed_intervening_candidates=crossed_candidates(p,db)))
            reviewed=a.get('eligible_for_original_print_link',False)
            counts['previously_reviewed_attachable']+=reviewed
            counts['reviewed_attachment_status_changed']+=reviewed != b.get('eligible_for_original_print_link',False)
            if reviewed:
                counts['reviewed_page_changed']+=a.get('reviewed_page')!=b.get('reviewed_page')
            counts['machine_eligible']+=b['machine_publication']['eligible']
    return dict(counts=dict(counts),changed_predictions=changes,changed_evidence=evidence_changes,
                authority='Ranking changes are unassessed; unchanged reviewed attachment metadata is not machine recovery of lexical identity.')


def diagnostic_traits(row, repeated, geometry, model):
    """Observable strata, not inferred causes or correctness labels."""
    text=row['line_text']; length=len(normal(text))
    coordinate=row.get('coordinate') or row.get('legacy_coordinate')
    b=coordinate.get('box') if coordinate else None
    return dict(length='under10' if length<10 else '10to39' if length<40 else '40plus',
                repeated_on_page=repeated,
                zone=row.get('zone','unknown'),
                tibetan=any('\u0f00'<=c<='\u0fff' for c in text),
                hyphenated=any(c in text for c in '-‐\u00ad'),
                page_position=('top' if b[1]<.12*geometry['height'] else
                               'bottom' if b[1]>.9*geometry['height'] else 'body') if b else 'unlocated',
                column=column_of(b,model) if b else None,
                position_basis='reconciled' if row.get('coordinate') else
                               'legacy_only' if b else 'none')


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
    strata=defaultdict(Counter);samples=defaultdict(list)
    query='SELECT family,page,line,body FROM lines ORDER BY family,page,line'
    for (family,page),group in groupby(db.execute(query),key=lambda r:r[:2]):
        rows=[(line,json.loads(body)) for _,_,line,body in group]
        frequency=Counter(normal(row['line_text']) for _,row in rows)
        geometry=json.loads(db.execute('SELECT features FROM pages WHERE family=? AND page=?',(family,page)).fetchone()[0])
        model=json.loads(db.execute('SELECT body FROM reading_pages WHERE family=? AND page=?',(family,page)).fetchone()[0])['model']
        for line,row in rows:
            old,new=row.get('legacy_coordinate'),row.get('coordinate')
            status=row['coordinate_reconciliation']['status']
            disjoint=False
            if old and new:
                a,b=old['box'],new['box']
                disjoint=min(a[2],b[2])<=max(a[0],b[0]) or min(a[3],b[3])<=max(a[1],b[1])
            population='disjoint' if disjoint else 'located' if new else status
            traits=diagnostic_traits(row,frequency[normal(row['line_text'])]>1,geometry,model)
            for name,value in traits.items():
                strata[family][f'{population}:{name}={value}']+=1
            # Deterministic bounded sample per family/zone/length/population.
            # Kept separate from any later image-based assessment.
            key=(family,population,traits['zone'],traits['length'])
            if population!='located' and len(samples[key])<3:
                samples[key].append(dict(family=family,physical_page=page,line=line,
                    qa_text=row['line_text'],qa_source_sha256=row.get('qa_source_sha256'),
                    legacy=old,reconciled=new,traits=traits,
                    alternatives=row['coordinate_reconciliation'].get('span_alternatives',row['coordinate_reconciliation'].get('alternatives',[])),
                    assessment='unassessed'))
    return dict(by_family={k:dict(v) for k,v in sorted(families.items())},
                diagnostic_strata={k:dict(sorted(v.items())) for k,v in sorted(strata.items())},
                stratified_sample=[row for key in sorted(samples) for row in samples[key]],
                interpretation='Disjoint boxes require inspection, not automatic error labels. Unlocated lines may have recoverable physical positions. Traits overlap and do not prove causes. No accuracy claim without image observations.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline',type=Path,help='Optional baseline witnesses.jsonl for streamed prediction comparison')
    a=p.parse_args();value=report(a.database)
    if a.baseline:
        with sqlite3.connect('file:'+str(a.database.resolve())+'?mode=ro',uri=True) as db:
            value['prediction_comparison']=compare_predictions(a.baseline,a.database.parent/'witnesses.jsonl',db)
    a.output.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value['by_family'],sort_keys=True))

if __name__=='__main__':main()
