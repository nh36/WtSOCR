#!/usr/bin/env python3
"""Freeze a stratified source-review sample of the e14 bounded-passage gains.

This selects claims for source inspection; it never certifies their correctness.
PDF source objects stay in ignored storage. Review decisions belong in JSONL.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gains', type=Path, default=Path('work/badw_forensic_structure/gained_e14.json'))
    ap.add_argument('--packets', type=Path, default=Path('work/badw_forensic_structure/owner_review_packets.jsonl'))
    ap.add_argument('--output', type=Path, default=Path('data/badw_forensic_structure/passage_positive_selection.json'))
    ap.add_argument('--render', action='store_true')
    args = ap.parse_args()
    gains = json.loads(args.gains.read_text())
    unique = {r['passage']['id']: r['passage'] for r in gains}
    packets = {r['packet']['identity']: r for r in map(json.loads, args.packets.open())}
    groups = {}
    for p in unique.values():
        identity = p['entry_identity']
        volume = re.search(r'badw-v(\d)-', identity)
        group = (volume.group(1) if volume else 'html', p['passage_type'])
        groups.setdefault(group, []).append(p)
    selected = []
    for (volume, production), candidates in sorted(groups.items()):
        # Rare productions are exhaustive; terminal comparisons cover eight per volume.
        limit = 8 if production == 'terminal_comparison' else 3
        if production not in ('terminal_comparison', 'bounded_comparison'):
            limit = len(candidates)
        chosen = []
        predicates = [lambda p: len(p['citation_node_ids']) > 1,
                      lambda p: p['literal'].rstrip().endswith(';'),
                      lambda p: '(' in p['literal'],
                      lambda p: '\n' in p['literal']]
        ordered = sorted(candidates, key=lambda p: hashlib.sha256(p['id'].encode()).hexdigest())
        for predicate in predicates:
            matches = [p for p in ordered if predicate(p) and p not in chosen]
            if matches and len(chosen) < limit:
                chosen.append(matches[0])
        chosen.extend(p for p in ordered if p not in chosen)
        for p in chosen[:limit]:
            bundle = packets[p['entry_identity']]
            packet = bundle['packet']
            text = packet['review_text']
            assert text[p['start']:p['end']] == p['literal']
            container = next(n for n in bundle['projection']['nodes'] if n['id'] == p['containing_node_id'])
            row = {'passage': p, 'headword': bundle['entry']['headword']['loc'],
                   'stratum': [volume, production], 'container': container,
                   'container_literal': text[container['start']:container['end']],
                   'context': text[max(0,p['start']-180):p['end']+180],
                   'review_text_sha256': packet['review_text_sha256'],
                   'review_status': 'pending_source_inspection'}
            if packet['source_kind'] == 'pdf':
                sources = packet['source']['source_objects']
                row['candidate_pdf_sources'] = sources
                row['packet_reported_printed_pages'] = sorted({str(l.get('printed_page')) for l in packet['source']['visual_lines']})
                if args.render:
                    for source in sources:
                        digest = source['pdf_sha256']
                        target = Path('work/badw_forensic_structure/positive_facsimiles') / (p['id'] + '-' + digest[:12])
                        target.parent.mkdir(parents=True, exist_ok=True)
                        pdf = Path('work/badw_source_cache/objects/sha256') / digest[:2] / digest
                        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == digest
                        subprocess.run(['pdftoppm','-scale-to','1800','-png',str(pdf),str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            else:
                row['source_object'] = packet['source']['source_object']
            selected.append(row)
    result = {'baseline_commit':'e14c14598a', 'selection_policy':'deterministic feature-stratified; all rare productions; eight terminal comparisons per PDF volume',
              'gain_occurrences':len(gains), 'unique_gain_passages':len(unique),
              'gains_sha256':hashlib.sha256(args.gains.read_bytes()).hexdigest(),
              'packets_sha256':hashlib.sha256(args.packets.read_bytes()).hexdigest(), 'selected':selected}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(f'Selected {len(selected)} passages; decisions remain pending source inspection')


if __name__ == '__main__':
    main()
