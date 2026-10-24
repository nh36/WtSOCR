"""Build a source-pinned investigation queue; never accept a destination.

All exact homonym competitors are retained, including those without a return
reference. A reciprocal arrow is a discovery hint, not identity authority.
"""
import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

from build_badw_connected_reader import ROOT, INDEX, CANON
from badw_grammatical_references import complete_target, first_sense_prefix


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover(reader, census, index_path=INDEX, canonical=CANON):
    catalog = json.loads((reader/'data.json').read_text())
    entries = {e['id']: e for e in catalog['entries']}
    index = {e['id']: e for e in map(json.loads, index_path.open())}
    cases = [r for r in map(json.loads, gzip.open(census, 'rt'))
             if r['source_kind'] == 'pdf' and r['classification'] == 'ambiguity']
    for case in cases:
        meta = entries[case['entry_id']]
        path = reader/meta['path']
        if sha(path) != meta['sha256']:
            raise ValueError('reader shard hash differs')
        entry = json.loads(path.read_text())
        text = ''.join(s['text'] for s in entry['segments'])
        if hashlib.sha256(text.encode()).hexdigest() != case['source_binding']['text_sha256']:
            raise ValueError('source text hash differs')
        a, b = case['source_span']['start'], case['source_span']['end']
        if text[a:b] != case['literal']:
            raise ValueError('source extent differs')
        source_record = index[case['entry_id']]
        source_span = source_record['entry_start_source_span']
        source_path = canonical/source_span['canonical_object']
        source_page = json.loads(gzip.decompress(source_path.read_bytes()))
        source_runs = source_page['positioned_page']['positioned_text_runs']
        source_evidence = dict(canonical_object_sha256=sha(source_path),
            printed_page=source_page['printed_page'], source_span=source_span,
            runs=source_runs[source_span['run_start']:source_span['run_end_exclusive']])
        competitors = []
        for candidate in case['candidate_destinations']:
            record = index[candidate['id']]
            span = record.get('entry_start_source_span')
            item = dict(candidate, status='insufficiently_supported',
                        reason='No explicit reciprocal found; absence does not contradict identity.')
            if span:
                path = canonical/span['canonical_object']
                page = json.loads(gzip.decompress(path.read_bytes()))
                runs = page['positioned_page']['positioned_text_runs']
                lo, hi = span['run_start'], span['run_end_exclusive']
                matches, contradicted = [], []
                # Exact bounded run windows. No normalization or fuzzy search.
                for start in range(max(span['loc_run_indices'])+1, hi):
                    literal = ''
                    for end in range(start, min(hi, start+32)):
                        literal += runs[end]['decoded_unicode']
                        if len(literal) > 160:
                            break
                        tail = case['headword']['loc']
                        if any(literal.rstrip().endswith(arrow+tail) for arrow in '↑↓'):
                            window = dict(run_start=start, run_end_exclusive=end+1,
                                          literal=literal, runs=runs[start:end+1])
                            if complete_target(runs, end+1, hi):
                                # A discovery hint only: bind a possible first-sense
                                # offset to actual overprinted glyph coordinates.
                                for sense_start in range(max(max(span['loc_run_indices'])+1, start-8), start):
                                    proof = dict(window, run_start_offset=3,
                                                 numbered_sense=dict(run_start=sense_start, label='1.'))
                                    if first_sense_prefix(page, span, proof):
                                        window['numbered_sense_candidate'] = dict(
                                            run_start_offset=3, numbered_sense=proof['numbered_sense'])
                                matches.append(window)
                            else:
                                contradicted.append(dict(window, reason='Return is a prefix inside a longer word split across PDF runs.'))
                item.update(entry_start_source_span=span, canonical_object_sha256=sha(path),
                            printed_page=page['printed_page'],
                            article_run_text=''.join(r['decoded_unicode'] for r in runs[lo:hi]),
                            reciprocal_windows=matches, contradicted_windows=contradicted)
                if matches:
                    item.update(status='potentially_supported', reason='Exact return arrow found; grammatical role, identity and facsimiles require review.')
                elif contradicted:
                    item.update(status='contradicted', reason='Only apparent return matches end inside a longer printed target; this does not establish identity.')
            competitors.append(item)
        yield dict(case=case, source_index=source_record, source_evidence=source_evidence, source_text=text,
                   introduction=text[:a].strip(), competitors=competitors,
                   status='potentially_supported' if any(c['status']=='potentially_supported' for c in competitors)
                          else 'insufficiently_supported',
                   decision='deferred', reason='Discovery only; no facsimile adjudication yet.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reader', type=Path, required=True)
    ap.add_argument('--census', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to(ROOT/'work'):
        ap.error('output must be a new directory under work/')
    start = time.monotonic()
    args.output.mkdir(parents=True)
    queue = list(discover(args.reader, args.census))
    with (args.output/'queue.jsonl').open('w') as handle:
        for row in queue:
            handle.write(json.dumps(row, ensure_ascii=False)+'\n')
    summary = dict(examined=len(queue), potentially_supported=sum(r['status']=='potentially_supported' for r in queue),
                   reciprocal_candidates=sum(c['status']=='potentially_supported' for r in queue for c in r['competitors']),
                   seconds=round(time.monotonic()-start, 3),
                   inputs={str(p): sha(p) for p in (args.reader/'manifest.json', args.census, INDEX)})
    (args.output/'manifest.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
