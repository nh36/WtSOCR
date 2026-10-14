#!/usr/bin/env python3
"""Compare derived PDF definitions with a pinned earlier production.

Raw projection cache is immutable input; withdrawals retain literal observations.
"""
import argparse
import json
import subprocess
import sys
import types
from pathlib import Path
from badw_pdf_structure_recovery import recover
from badw_recovered_fragment_integrity import definition_error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='b677c3196c')
    parser.add_argument('--cache', type=Path, default=Path('work/badw_forensic_structure/projections.jsonl'))
    parser.add_argument('--output', type=Path, default=Path('data/badw_forensic_structure/definition_backaudit.json'))
    args = parser.parse_args()
    modules = {}
    for name in ('badw_pdf_structure_recovery', 'badw_pdf_mixed_clauses'):
        module = types.ModuleType('baseline_' + name)
        code = subprocess.check_output(['git', 'show', f'{args.baseline}:scripts/{name}.py'], text=True)
        exec(compile(code, name, 'exec'), module.__dict__)
        modules[name] = module
    old = modules['badw_pdf_structure_recovery']
    changes, examined, remaining_errors = [], 0, []
    with args.cache.open() as handle:
        for line in handle:
            row = json.loads(line)
            projection = row['projection']
            if projection['source_kind'] != 'pdf':
                continue
            text = row['packet']['review_text']
            before = modules['badw_pdf_mixed_clauses'].recover_mixed_clauses(
                old.recover_hyphenated_definitions(old.recover_opening(projection, text), text), text)
            after = recover(projection, text)
            accepted = {(n['start'], n['end']) for n in after['nodes'] if n['kind'] == 'definition'}
            for node in before['nodes']:
                if node['kind'] != 'definition' or not node.get('structural_recovery'):
                    continue
                examined += 1
                a, b = node['start'], node['end']
                if (a, b) not in accepted:
                    changes.append(dict(identity=projection['identity'], review_text_sha256=row['packet']['review_text_sha256'],
                        source_span=dict(start=a, end=b), literal=text[a:b],
                        prior_evidence=node['structural_recovery'], reason=definition_error(text[a:b]) or 'envelope_integrity_changed',
                        replacement_spans=[dict(start=n['start'], end=n['end'], literal=text[n['start']:n['end']])
                            for n in after['nodes'] if n['kind']=='definition' and n.get('structural_recovery') and n['start']<b and a<n['end']]))
            for node in after['nodes']:
                if node['kind']=='definition' and node.get('structural_recovery') and definition_error(text[node['start']:node['end']]):
                    remaining_errors.append(dict(identity=projection['identity'], node=node['id']))
    args.output.write_text(json.dumps(dict(baseline=args.baseline, examined_fragments=examined,
        withdrawn_or_shortened=len(changes), changes=changes, remaining_integrity_errors=remaining_errors), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(examined=examined, changed=len(changes), remaining_errors=len(remaining_errors))))
    if remaining_errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
