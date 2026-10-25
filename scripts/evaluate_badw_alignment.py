#!/usr/bin/env python3
"""Compare complete private runs, diagnose uncertainty and evaluate separate labels.

Labels are independent human source observations, never generated predictions.
Unknown judgments are excluded from precision denominators and counted explicitly.
No output of this utility authorises reader attachment.
"""
import argparse
import collections
import hashlib
import json
import math
import sqlite3
from badw_html_print_alignment import digest, object_digest
from pathlib import Path
from badw_html_print_engine import atomic_json

CAUSES = {
 'uncertain_article_start': {'weak_article_start_structure', 'displaced_or_incidental_heading'},
 'uncertain_page_or_column': {'no_unique_embedded_ocr_coordinates', 'uncertain_column_membership'},
 'header_or_continuation': {'top_margin_bare_heading', 'same_spelling_heading_repeated_on_page', 'header_or_continuation_with_better_article_on_page'},
 'neighbouring_compound': {'neighbouring_compound_heading'},
 'generic_definition': {'generic_or_absent_definition_evidence'},
 'ocr_spacing': {'loc_spacing_or_ocr_difference'},
 'incomplete_article': {'unverified_article_extent'},
 'ambiguous_homonym': {'printed_homonym_unread', 'printed_homonym_conflict'},
}


def causes(row):
    if not row['proposed']:
        return ['no_lexical_start_candidate']
    p = row['proposed'][0]
    risks = set(p['risks'])
    result = [name for name, flags in CAUSES.items() if flags & risks]
    if not p['historical_identity_edge']:
        result.append('missing_historical_identity_edge')
    if not p.get('reviewed_page_geometry'):
        result.append('unreviewed_folio_or_crop')
    if not p['definition_evidence']['rare_definition_tokens']:
        result.append('lexical_identity_not_discriminated')
    elif 'weak_article_start_structure' not in risks:
        result.append('plausible_start_lexical_identity_unvalidated')
    if len(row['proposed']) > 1 and p['score'] - row['proposed'][1]['score'] < 2:
        result.append('competing_identity_or_location')
    return sorted(set(result))


def wilson(correct, n):
    if not n:
        return None
    z = 1.959963984540054
    den = 1+z*z/n
    centre = (correct/n+z*z/(2*n))/den
    half = z*math.sqrt(correct/n*(1-correct/n)/n+z*z/(4*n*n))/den
    return [round(max(0,centre-half),6),round(min(1,centre+half),6)]


def read_rows(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def sample_key(row, seed):
    return hashlib.sha256((seed+':'+row['source_id']).encode()).hexdigest()


def select_sample(rows, seed='20261026-independent', per_class=4):
    """Stratify on baseline top family and classification BEFORE inspection."""
    groups = collections.defaultdict(list)
    for row in rows:
        if not row['proposed']:
            continue
        group = (row['proposed'][0]['family'],row['result_category'])
        groups[group].append(row)
        groups[group] = sorted(groups[group],key=lambda r:sample_key(r,seed))[:per_class]
    result = []
    for group, candidates in sorted(groups.items()):
        if group[1] == 'unresolved':
            continue
        for i,row in enumerate(sorted(candidates,key=lambda r:sample_key(r,seed))[:per_class]):
            p = row['proposed'][0]
            result.append(dict(source_id=row['source_id'], anchor=p['anchor'],
                family=p['family'], stratum=list(group), split='development' if i%2==0 else 'held_out',
                html_sha256=row['html_sha256'], evidence_sha256=p['evidence_sha256'],
                heading=p['heading_text'], editorial_headword=row['editorial_headword'],
                editorial_homonym=row['editorial_homonym'], editorial_definition=row['editorial_definition'],
                printed_evidence=p['printed_evidence'], coordinate=p['coordinate'],
                judgments={k:None for k in ('heading','page','article_start','lexical_identity','homonym','own_evidence','crop')},
                source_observation=None))
    return result


def verify_observations(labels, run, render_root):
    """Check stored source bindings, not the truth of a human transcription."""
    pins=json.loads((run/'inputs.json').read_text())['inputs']
    db=sqlite3.connect('file:'+str((run/'index.sqlite').resolve())+'?mode=ro',uri=True)
    try:
        for label in labels['cases']:
            family,page,line=label['anchor'].split(':')
            if family != label['family'] or pins['scan:'+family] != labels['scan_sha256'][family]:
                raise ValueError('stale evaluation scan/coordinate binding')
            found=db.execute('SELECT body FROM lines WHERE family=? AND page=? AND line=?',
                             (family,int(page),int(line))).fetchone()
            if not found:
                raise ValueError('evaluation QA row absent')
            row=json.loads(found[0])
            if (hashlib.sha256(row['line_text'].encode()).hexdigest() != label['qa_line_sha256'] or
                object_digest({k:v for k,v in row.items() if k!='coordinate'}) != label['qa_row_sha256']):
                raise ValueError('stale evaluation QA binding')
            if row['coordinate'] != label['coordinate']:
                raise ValueError('stale evaluation coordinate binding')
            image=render_root/f'{family}-{page}.png'
            record=json.loads(image.with_suffix('.json').read_text())
            if (record['scan_sha256'] != pins['scan:'+family] or
                record['physical_page'] != int(page) or record['family'] != family or
                digest(image) != label['inspected_render_sha256'] or
                record['image_sha256'] != label['inspected_render_sha256']):
                raise ValueError('stale evaluation rendered evidence')
    finally:
        db.close()


def calibration_queue(baseline, run, excluded=()):
    """Select unlabelled calibration cases; source bindings are not judgments."""
    cases=select_sample((r for r in read_rows(baseline/'witnesses.jsonl')
                         if r['source_id'] not in set(excluded)),
                        seed='20261027-reconstruction-calibration',per_class=25)
    pins=json.loads((run/'inputs.json').read_text())['inputs']
    db=sqlite3.connect('file:'+str((run/'index.sqlite').resolve())+'?mode=ro',uri=True)
    try:
        for case in cases:
            family,page,line=case['anchor'].split(':')
            found=db.execute('SELECT body FROM lines WHERE family=? AND page=? AND line=?',
                             (family,int(page),int(line))).fetchone()
            if found is None:
                raise ValueError('calibration QA row absent: '+case['anchor'])
            row=json.loads(found[0])
            case.update(scan_sha256=pins['scan:'+family],
                qa_line_sha256=hashlib.sha256(row['line_text'].encode()).hexdigest(),
                qa_row_sha256=object_digest({k:v for k,v in row.items() if k!='coordinate'}),
                coordinate=row['coordinate'],inspected_render_sha256=None)
    finally:
        db.close()
    return dict(seed='20261027-reconstruction-calibration',
        status='unadjudicated; not a gold standard or accuracy measurement',
        policy='Baseline-stratified; excludes prior evaluation cases. Held-out labels must remain unavailable during rule development.',
        cases=cases)


def prediction_changes(labels, predictions):
    """Changed anchors/evidence require assessment; never inherit a positive label."""
    counts=collections.Counter()
    records=[]
    for label in labels:
        top=next(iter(predictions[label['source_id']]['proposed']),None)
        changed=not top or top['anchor'] != label['anchor'] or top['evidence_sha256'] != label['evidence_sha256']
        judgment=label['judgments']['lexical_identity']
        status=('changed_prediction_not_yet_assessable' if changed else
                'explicitly_incorrect_identity' if judgment is False or label['judgments']['homonym'] is False else
                'retained_correct_prediction' if judgment is True else
                'insufficient_independent_ground_truth')
        counts[status]+=1
        records.append(dict(source_id=label['source_id'],status=status,
            inspected_anchor=label['anchor'],current_anchor=top['anchor'] if top else None))
    return dict(counts=dict(counts),cases=records,
        corrected_predictions=0,newly_incorrect_predictions=0,
        interpretation='Changed predictions need separate labels before correction/error rates can be measured. Binding verification is not visual adjudication.')


def evaluate(labels, predictions):
    metrics = collections.defaultdict(lambda:collections.Counter())
    for label in labels:
        sid = label['source_id']
        if sid not in predictions:
            raise ValueError('missing labeled witness: '+sid)
        row = predictions[sid]
        if row['html_sha256'] != label['html_sha256']:
            raise ValueError('stale evaluation HTML binding: '+sid)
        top = row['proposed'][0] if row['proposed'] else None
        # Judgments refer to the inspected baseline anchor. Changed proposals need
        # new inspection; do not transfer lexical judgments to another article.
        same = top and top['anchor']==label['anchor'] and top['evidence_sha256']==label['evidence_sha256']
        for metric, judgment in label['judgments'].items():
            for group in ('all', 'family:'+label['family'], 'split:'+label['split'], 'class:'+row['result_category'], 'baseline_class:'+label['stratum'][1]):
                key = group+'/'+metric
                if judgment is None or not same or (metric == 'own_evidence' and top['evidence_sha256'] != label['evidence_sha256']):
                    metrics[key]['unknown'] += 1
                else:
                    metrics[key]['n'] += 1
                    metrics[key]['correct'] += judgment is True
    return {k:dict(v, n=v['n'], correct=v['correct'], unknown=v['unknown'], precision=v['correct']/v['n'] if v['n'] else None,
                   wilson_95=wilson(v['correct'],v['n'])) for k,v in sorted(metrics.items())}


def compare(baseline, current):
    counts = collections.Counter()
    family = collections.defaultdict(collections.Counter)
    transitions = collections.Counter()
    sequences = collections.Counter()
    for row in current:
        old = baseline.pop(row['source_id'])
        if old['html_sha256'] != row['html_sha256']:
            raise ValueError('comparison corpus identity changed')
        transition = old['result_category']+' -> '+row['result_category']
        transitions[transition] += 1
        counts.update(causes(row))
        f = row['proposed'][0]['family'] if row['proposed'] else 'unresolved'
        family[f].update(causes(row))
        a = old['proposed'][0] if old['proposed'] else None
        b = row['proposed'][0] if row['proposed'] else None
        counts['top_anchor_changed'] += bool(a and b and a['anchor'] != b['anchor'])
        if b:
            sequences['top_page_chain_member'] += b['sequence_consistent']
            sequences['top_section_chain_member'] += b.get('section_sequence_consistent',False)
            sequences['top_chain_membership_changed'] += b['sequence_consistent'] != b.get('section_sequence_consistent',False)
    if baseline:
        raise ValueError('incomplete comparison corpus')
    return dict(multi_cause_counts=dict(counts),by_family={k:dict(v) for k,v in family.items()},
                transitions=dict(transitions),sequence_diagnostics=dict(sequences),
                interpretation='Uncertainty flags overlap; plausible starts are not verified lexical identities. Section paths are diagnostic, never acceptance evidence.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--labels',type=Path)
    p.add_argument('--observed-renders',type=Path,help='original inspected PNG directory; required with labels')
    p.add_argument('--prepare-calibration',action='store_true',help='prepare 200 unlabelled, source-bound cases, excluding prior labels')
    args=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    if not args.run.resolve().is_relative_to(root/'work'):
        p.error('private outputs must stay in work/')
    sample=select_sample(read_rows(args.baseline/'witnesses.jsonl'))
    baseline={r['source_id']:{k:r[k] for k in ('source_id','html_sha256','result_category')} |
              {'proposed':[{'anchor':r['proposed'][0]['anchor']}] if r['proposed'] else []}
              for r in read_rows(args.baseline/'witnesses.jsonl')}
    atomic_json(args.run/'evaluation-selection.json',dict(seed='20261026-independent',
        policy='Fixed before inspection; labels must be separately transcribed from sources. No automatic acceptance.',cases=sample))
    report=compare(baseline,read_rows(args.run/'witnesses.jsonl'))
    if args.labels:
        labels=json.loads(args.labels.read_text())
        pins=json.loads((args.run/'inputs.json').read_text())['inputs']
        for family, sha in labels['scan_sha256'].items():
            if pins['scan:'+family] != sha:
                raise ValueError('stale evaluation scan binding: '+family)
        if not args.observed_renders:
            p.error('--labels requires --observed-renders for verification')
        verify_observations(labels,args.run,args.observed_renders)
        ids={c['source_id'] for c in labels['cases']}
        predictions={r['source_id']:r for r in read_rows(args.run/'witnesses.jsonl') if r['source_id'] in ids}
        report['evaluation']=evaluate(labels['cases'],predictions)
        report['prediction_assessment']=prediction_changes(labels['cases'],predictions)
    atomic_json(args.run/'comparison.json',report)
    if args.prepare_calibration:
        excluded=[c['source_id'] for c in labels['cases']] if args.labels else []
        atomic_json(args.run/'calibration-selection.json',calibration_queue(args.baseline,args.run,excluded))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
