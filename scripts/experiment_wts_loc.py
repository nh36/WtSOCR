"""Evaluate bounded WTS LoC inversion against independently paired headwords.

All experiment artifacts stay under work/. A deterministic Tibetan-syllable
split prevents the same syllable from teaching and testing template coverage.
Problematic includes uncorroborated pairs; it does not mean printed error.
"""
import argparse
import collections
import hashlib
import json
import re
from pathlib import Path

from wts_loc_converter import Converter, held_out, read, ROOT


def paired_syllables(catalog):
    pairs = collections.defaultdict(set)
    rejected = collections.Counter()
    for entry in catalog['entries']:
        h = entry['headword']; latin = h.get('loc') or ''; tib = h.get('tibetan') or ''
        if not tib:
            rejected['no_independent_tibetan'] += 1
            continue
        ls, ts = latin.split(' '), re.split('[་། ]+', tib.strip('་། '))
        if len(ls) != len(ts) or not all(ls) or any(not t for t in ts):
            rejected['unalignable_pair'] += 1
            continue
        for l, t in zip(ls, ts):
            pairs[t].add(l)
    return pairs, rejected


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reader', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args=ap.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'work') or args.output.exists():
        ap.error('output must be new and under work/')
    args.output.mkdir(parents=True)
    catalog=json.loads((args.reader/'data.json').read_text())
    pairs, rejected=paired_syllables(catalog)
    training=[(next(iter(ls)),t) for t,ls in pairs.items() if len(ls)==1 and not held_out(t)]
    converter=Converter(training)
    concordance=read(ROOT/'data/tibetan_latin_syllable_concordance.tsv')
    corroborated={(r['tibetan_syllable'],r['latin_form']) for r in concordance if int(r.get('independent_teaching_occurrences') or 0)>0}
    counts=collections.defaultdict(collections.Counter)
    with (args.output/'held_out.jsonl').open('w') as f:
        for t,ls in sorted(pairs.items()):
            if not held_out(t): continue
            assert t not in converter.training_syllables
            for latin in sorted(ls):
                group='clean_corroborated' if len(ls)==1 and (t,latin) in corroborated else 'problematic_or_uncorroborated'
                result=converter.syllable(latin)
                outcome=('exact' if result['tibetan']==t else 'different_attested_form') if result['status']=='converted' else result['status']
                counts[group]['total']+=1;counts[group][outcome]+=1
                f.write(json.dumps(dict(latin=latin,attested_tibetan=t,group=group,outcome=outcome,**result),ensure_ascii=False)+'\n')
        # This is a separate stress set, not additional independent holdout.
        # A damaged source occurrence need not imply a damaged transliteration.
        for r in concordance:
            if int(r.get('damaged_occurrences') or 0)==0: continue
            latin,t=r['latin_form'],r['tibetan_syllable']
            result=converter.syllable(latin)
            outcome=('exact' if result['tibetan']==t else 'different_attested_form') if result['status']=='converted' else result['status']
            group='damaged_source_stress_set'
            counts[group]['total']+=1;counts[group][outcome]+=1
            f.write(json.dumps(dict(latin=latin,attested_tibetan=t,group=group,outcome=outcome,**result),ensure_ascii=False)+'\n')
    metrics={}
    for group,c in counts.items():
        converted=c['exact']+c['different_attested_form']
        metrics[group]=dict(c,converted=converted,coverage=converted/c['total'],exact_match_of_converted=c['exact']/converted if converted else None,exact_match_of_all=c['exact']/c['total'])
    # The browser is allowed only conversions which also agree with the
    # independent paired form. The model's predictions alone are not evidence.
    agreed={}
    for t,ls in pairs.items():
        if len(ls)!=1: continue
        latin=next(iter(ls)); r=converter.syllable(latin)
        if r['tibetan']==t: agreed[latin]=t
    headwords={}
    for e in catalog['entries']:
        h=e['headword']; parts=(h.get('loc') or '').split(' ')
        if parts and all(p in agreed for p in parts):
            value='་'.join(agreed[p] for p in parts)+'་'
            if value==h.get('tibetan'):
                headwords[h['loc']]=value
    provenance={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sorted((ROOT/'data').glob('*tibetan*.tsv')),ROOT/'scripts/build_tibetan_role_transcription_model.py',Path(__file__),ROOT/'scripts/wts_loc_converter.py']}
    report=dict(version='wts-loc-experiment-v1',split='sha256(Tibetan syllable) first 32 bits modulo 5 == 0; no held-out syllable trains templates; previously reviewed role mappings are fixed inputs, not held-out discoveries',metrics=metrics,input_rejections=dict(rejected),training_syllables=len(converter.training_syllables),onset_templates=len(converter.onsets),coda_templates=len(converter.codas),independently_confirmed_syllables=len(agreed),independently_confirmed_headwords=len(headwords),input_sha256=provenance,catalog_sha256=hashlib.sha256((args.reader/'data.json').read_bytes()).hexdigest(),limitations=['No OCR repair or Unicode/LoC normalization.', 'Unsupported orthography is not diagnosed as corruption.', 'Only independently corroborated agreements may be displayed.', 'Period-conditioned onsets, Sanskrit stacks and damaged input abstain.', 'The damaged-source stress set is not independent holdout and does not diagnose individual OCR errors.', 'This tests recombination of onset/coda templates, not independent discovery of the previously reviewed role mappings.'])
    (args.output/'attested_display.json').write_text(json.dumps(dict(version=report['version'],syllables=agreed,headwords=headwords),ensure_ascii=False,sort_keys=True)+'\n')
    report['display_sha256']=hashlib.sha256((args.output/'attested_display.json').read_bytes()).hexdigest()
    (args.output/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
