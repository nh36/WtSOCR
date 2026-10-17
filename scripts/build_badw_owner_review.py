#!/usr/bin/env python3
"""Occurrence-level structural review; classifications never license owners.

Reproduce from the frozen input census and cached immutable projection packets.
The small packet cache is optional: --packets can name projections.jsonl.
"""
import argparse
import collections
import gzip
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

from badw_semantic_hierarchy import hierarchy
from badw_source_components import lexical_clauses
from badw_bounded_passages import envelopes
from badw_pdf_structure_recovery import recover
from badw_comparison_clauses import comparison_end
from badw_header_structure import contiguous_pdf_lines
from badw_pdf_mixed_clauses import style_runs


def comparison_failure(projection, text, start, citation_end):
    """Explain the failed production without relaxing any ownership gates."""
    nodes = projection['nodes']
    if any(s < start < e for s, e, _ in envelopes(text)):
        return dict(reason='comparison_marker_in_enclosure_role_unestablished')
    containers = [n for n in nodes if n['kind'] in ('sense', 'source_division')
                  and n['start'] <= start < n['end']]
    if not containers:
        return dict(reason='comparison_canonical_scope_missing')
    container = min(containers, key=lambda n: n['end']-n['start'])
    end = comparison_end(text, start, container['end'])
    if end is None or end < citation_end:
        return dict(reason='comparison_independent_right_boundary_missing',
                    container=container['id'], candidate_end=end)
    competing = [n for n in nodes if n['kind'] in ('example', 'lexical', 'lexical_parallel', 'cross_reference')
                 and n['start'] < end and start < n['end']]
    if competing:
        return dict(reason='comparison_competing_source_components', candidate_end=end,
                    competing_nodes=[dict(id=n['id'], kind=n['kind'], start=n['start'], end=n['end']) for n in competing])
    if any(n['kind']=='sense' and n['start']<end and start<n['end']
           and not n['start']<=start<end<=n['end'] for n in nodes):
        return dict(reason='comparison_crosses_sense_boundary', candidate_end=end)
    if projection['source_kind']=='pdf':
        lines, runs = style_runs(projection, text)
        layout = [r for r in runs if r['start']<end and start<r['end']]
        if not layout or any(not contiguous_pdf_lines(lines, l['line'], r['line']) for l,r in zip(layout,layout[1:])):
            return dict(reason='comparison_PDF_layout_boundary_unestablished', candidate_end=end)
    remaining = text[start:end]
    cites = [n for n in nodes if n['kind']=='citation' and start<=n['start']<n['end']<=end]
    for n in sorted(cites, key=lambda n:n['start'], reverse=True):
        remaining = remaining[:n['start']-start]+' '+remaining[n['end']-start:]
    remaining = re.sub(r'\bvgl\.', ' ', remaining)
    remaining = re.sub(r'\bs\.\s*v\.\s+[^\s,;().]+', ' ', remaining)
    remaining = re.sub(r'\b(?:f|ff|Nr|Anm|Bd|S|fig|p|vol)\.', ' ', remaining)
    residue = re.sub(r'[\s\d.,;:()\[\]/–-]|\bund\b', '', remaining)
    reason = ('comparison_production_passes' if not residue else
              'comparison_reference_label_split_across_font_runs' if residue.isupper() else
              'comparison_source_language_clause_missing' if re.search(r'\b(?:chin|mong|skt)\.', remaining) else
              'comparison_reference_or_prose_grammar_incomplete')
    return dict(reason=reason, candidate_end=end, unparsed_material=remaining,
                unparsed_alphabetic_material=residue)


def review(row, occurrence):
    packet, projection = row['packet'], row['projection']
    text = packet['review_text']
    assert packet['review_text_sha256'] == occurrence['text_sha256']
    a, b = (occurrence['source_span'][k] for k in ('start', 'end'))
    assert text[a:b] == occurrence['literal']
    projection = recover(projection, text)
    canonical = hierarchy(projection, text)
    start, end = max(0, a-350), min(len(text), b+350)
    components = [n for n in projection['nodes']
                  if n['start'] < end and start < n['end']]
    local = text[start:end]
    lex = [n for n in canonical['lex_items'] if n['start'] <= a < b <= n['end']]
    flags = []
    family = occurrence['grammar_family']
    if lex:
        for item in lex:
            flags += sorted({d['kind'] if 'kind' in d else str(d) for d in item['delimiter_diagnostics']})
        flags += ['canonical_Lex_item_present', 'equivalence' if any(x in text[min(n['start'] for n in lex):b] for x in '=≅≈') else 'gloss_or_assertion']
    marker = list(re.finditer(r'\bvgl\.', text[start:b]))
    if marker:
        m = start + marker[-1].start()
        tail = text[b:end]
        flags += ['comparison_marker_before_citation']
        if re.search(r'→|⇒|\bs\.', tail):
            flags += ['following_xref']
        if re.match(r'\s*[,;]', tail):
            flags += ['following_comma' if tail.lstrip().startswith(',') else 'following_semicolon']
        if any(n['kind'] == 'definition' and n['start'] <= m < b <= n['end'] for n in components):
            flags += ['comparison_within_definition']
        else:
            flags += ['comparison_outside_definition']
        flags += ['balanced_comparison' if any(e['start'] <= m < b <= e['end'] for e in occurrence['punctuation_enclosures']) else 'unenclosed_comparison']
    if not flags:
        flags = ['no_canonical_passage_containment']
    layout, offset = [], 0
    for line in packet.get('source', {}).get('visual_lines', []):
        e = offset + len(line['text'])
        if offset < end and start < e:
            layout.append(dict(line, start=offset, end=e))
        offset = e+1
    # Review taxonomy uses local syntax, not the coarse nearest-vgl bucket.
    enclosing = sorted((e for e in envelopes(text) if e[0] <= a < b <= e[1]), key=lambda e:e[1]-e[0])
    clause_start = max(text.rfind(';', 0, a), text.rfind('།', 0, a), text.rfind('Lex.', 0, a)) + 1
    # Some immutable citation observations include the vgl. introducer itself.
    markers = list(re.finditer(r'\bvgl\.\s+', text[clause_start:b]))
    marker_start = clause_start + markers[-1].start() if markers else None
    # A comparison marker inside an earlier closed enclosure cannot govern
    # the following independent prose or parenthetical attribution.
    if marker_start is not None and any(s <= marker_start < e <= a for s,e,_ in envelopes(text)):
        marker_start = None
    prefix = text[max(clause_start, a-200):a]
    if lex:
        taxonomy = 'Lex_assertion_delimiter_failure' if any(n['delimiter_diagnostics'] for n in lex) else 'Lex_item_owner_conflict'
    elif enclosing and re.match(r'\s*vgl\.\s+', text[enclosing[0][0]+1:enclosing[0][1]-1]):
        taxonomy = 'balanced_explicit_comparison'
    elif any(n['kind']=='example' and n['start']<=a<b<=n['end'] for n in components):
        taxonomy = 'example_nested_note' if enclosing and enclosing[0][0] < a else 'example_quotation_delimiter_failure'
    elif marker_start is not None:
        tail = text[b:min(len(text),b+180)]
        if re.search(r'(?:↑|↓|→|⇒)', tail.split('།')[0].split(';')[0]):
            taxonomy = 'comparison_then_lexical_xref'
        elif re.match(r'\s*,\s*(?:z\.\s*B\.|[a-zäöü])', tail):
            taxonomy = 'comparison_then_comma_prose'
        elif re.match(r'\s*[,;]', tail):
            taxonomy = 'comparison_reference_list_or_semicolon'
        elif re.match(r'\s*(?:[.;]|s\.\s*v\.|[fF]f?\.)', tail):
            taxonomy = 'comparison_locator_and_terminal_punctuation'
        else:
            taxonomy = 'comparison_following_material_needs_boundary'
    elif projection['source_kind']=='html' and not any(n['kind'] in ('sense','source_division') and n['start']<=a<b<=n['end'] for n in components):
        taxonomy = 'HTML_heading_grammatical_assertion'
    elif re.search(r'\b(?:aus\b|von\b|zu\b|chin\.|mong\.|skt\.|Herkunft\b|Lehnwort\b)', prefix):
        taxonomy = 'source_language_or_etymological_statement'
    elif enclosing and enclosing[0][2]=='(':
        taxonomy = 'parenthetical_source_in_prose_without_canonical_clause'
    elif any(n['kind']=='definition' and n['start']<=a<b<=n['end'] for n in components):
        taxonomy = 'definition_candidate_with_competing_components'
    else:
        taxonomy = 'editorial_source_statement_without_canonical_clause'
    fragments = projection.get('original_structure', {}).get('text_fragments', [])
    fragments = [f for f in fragments if f.get('visible_text_start') is not None
                 and f.get('visible_text_end') is not None
                 and f['visible_text_start'] < end and start < f['visible_text_end']]
    punct = r'[.;,:!?()\[\]„“«»→⇒]'
    left = list(re.finditer(punct, text[start:a]))
    right = re.search(punct, text[b:end])
    return dict(occurrence, headword=row['entry'].get('headword'),
                context_span=dict(start=start, end=end), context=local,
                canonical_Lex_items=lex,
                canonical_passages=[n for n in canonical['citable_passages'] if n['start'] <= a < b <= n['end']],
                source_nodes=components, layout_lines=layout, DOM_fragments=fragments,
                source_enclosures=[dict(start=s,end=e,opener=o,literal=text[s:e]) for s,e,o in enclosing],
                grammar_taxonomy=taxonomy, comparison_marker_start=marker_start,
                comparison_failure=comparison_failure(projection,text,marker_start,b) if marker_start is not None else None,
                nearest_punctuation=dict(left=dict(literal=left[-1].group(), start=start+left[-1].start()) if left else None,
                                         right=dict(literal=right.group(), start=b+right.start()) if right else None),
                markers=[dict(literal=m.group(), start=start+m.start(), end=start+m.end()) for m in re.finditer(r'vgl\.|v\.\s*l\.|\br\.|skt\.|zw\.|Abt\.|→|⇒|≅|≈|Lex\.', local)],
                structural_flags=sorted(set(flags)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--census', type=Path, default=Path('data/badw_forensic_structure/passage_after_short_variant.jsonl.gz'))
    ap.add_argument('--packets', type=Path, default=Path('work/badw_forensic_structure/projections.jsonl'))
    ap.add_argument('--output', type=Path, default=Path('data/badw_forensic_structure/owner_review'))
    ap.add_argument('--store', type=Path, help='Completed replay store, for final owner/disposition joins')
    args = ap.parse_args()
    occurrences = collections.defaultdict(list)
    for line in gzip.open(args.census, 'rt'):
        r = json.loads(line)
        occurrences[r['identity']].append(r)
    records = []
    for line in args.packets.open():
        row = json.loads(line)
        for occurrence in occurrences.pop(row['packet']['identity'], []):
            records.append(review(row, occurrence))
    assert not occurrences, list(occurrences)
    if args.store:
        db = sqlite3.connect('file:'+str(args.store)+'?mode=ro', uri=True)
        citations = {(entry, json.loads(raw)['source_span']['start'], json.loads(raw)['source_span']['end']): json.loads(raw)
                     for entry,raw in db.execute('SELECT entry,record_json FROM citation')}
        passages = {i: json.loads(raw) for i,raw in db.execute('SELECT id,record_json FROM passage')}
        for r in records:
            c = citations[(r['identity'], r['source_span']['start'], r['source_span']['end'])]
            owner = next((passages[i] for i in c.get('supports',[]) if i in passages), None)
            r['final_ownership'] = c['ownership']
            r['final_owner'] = owner
            if c['ownership'] != 'unresolved':
                r['disposition'] = dict(status='resolved_by_source_grammar', reason=owner['passage_type'] if owner else 'reviewed_relationship')
                continue
            reason = r['grammar_taxonomy']
            if r['comparison_failure'] and r['grammar_family']=='comparison_without_accepted_enclosure':
                reason = r['comparison_failure']['reason']
            if r['canonical_Lex_items']:
                a,b = r['source_span']['start'],r['source_span']['end']
                item = r['canonical_Lex_items'][0]
                local = item.get('literal', '')
                # Inspect the entire observed semicolon segment, not the citation
                # parentheses alone. These are diagnostics, never delimiter repairs.
                if not local:
                    local = next((n.get('source_text','') for n in r['source_nodes'] if n['kind']=='lexical'), '')
                offset = a-item['start']
                left = local.rfind(';',0,offset)+1
                right = local.find(';',b-item['start'])
                segment = local[left:right if right>=0 else len(local)]
                diagnostics = lexical_clauses(segment,0,len(segment))[1]
                reason = ('Lex_source_decoding_and_quotation_failure' if '⟦UNKNOWN:' in segment else
                          'Lex_local_quotation_delimiter_failure' if segment.count('„') != segment.count('“') and diagnostics else
                          'Lex_local_source_parenthesis_failure' if diagnostics else 'Lex_assertion_role_or_segmentation_missing')
                r['local_Lex_segment'] = segment
                r['local_delimiter_diagnostics'] = diagnostics
            elif 'example' in r['grammar_family']:
                reason = 'example_nested_source_note_role_missing' if r['source_enclosures'] else 'example_quotation_or_translation_envelope_missing'
            r['disposition'] = dict(status='parser_capability_or_source_boundary_review_pending', reason=reason,
                source_lacks_exact_passage=None,
                interpretation='No claim of irreducibility: diagnostic source grammar still requires a validated production or source-boundary adjudication.')
        db.close()
    records.sort(key=lambda r: (r['identity'], r['source_span']['start']))
    with gzip.GzipFile(filename=str(args.output)+'.jsonl.gz', mode='wb', mtime=0) as gz, io.TextIOWrapper(gz, encoding='utf-8') as out:
        for r in records:
            out.write(json.dumps(r, ensure_ascii=False)+'\n')
    clusters = collections.defaultdict(list)
    for r in records:
        clusters[(r['source_kind'], r['grammar_family'], r['grammar_taxonomy'])].append(r)
    summary = dict(baseline_unresolved=len(records), baseline_commit='e26c885e06', census=str(args.census),
                   census_sha256=hashlib.sha256(args.census.read_bytes()).hexdigest(),
                   script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   policy='Structural flags are review evidence, never ownership rules.',
                   clusters=[dict(source_kind=k[0], coarse_family=k[1], grammar=k[2], count=len(v),
                                  representatives=[dict(identity=r['identity'], span=r['source_span'], literal=r['literal'], context=r['context']) for r in v[:3]]) for k,v in sorted(clusters.items())])
    if args.store:
        summary['final_dispositions'] = [dict(status=k[0],reason=k[1],count=v) for k,v in sorted(collections.Counter(
            (r['disposition']['status'],r['disposition']['reason']) for r in records).items())]
        summary['final_unresolved'] = sum(r['final_ownership']=='unresolved' for r in records)
        summary['source_genuinely_lacks_exact_passage_established'] = 0
        summary['ownership_closed'] = False
        summary['finite_batch'] = [dict(identity=r['identity'],literal=r['literal'],context=r['context'],
            disposition=r['disposition']) for r in records if any(s in r['grammar_family'] for s in ('definition','example','balanced_comparison'))]
    Path(str(args.output)+'.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(total=len(records), clusters=len(clusters))))


if __name__ == '__main__':
    main()
