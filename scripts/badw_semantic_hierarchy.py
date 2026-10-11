"""Derived, source-bound Lex. items and citable passages.

Observation nodes remain unchanged. Ownership uses explicit HTML division
membership, validated example edges, or unique Lex. clause containment.
No distance-based association, punctuation repair, or language guessing.
"""
import hashlib
import re
from badw_source_components import lexical_clauses, terminal_lexical_citation

VERSION = 'badw-semantic-hierarchy-v1'


def hierarchy(projection, text):
    identity = projection['identity']
    sha = hashlib.sha256(text.encode()).hexdigest()
    if sha != projection['review_text_sha256']:
        raise ValueError('hierarchy source hash mismatch')
    nodes = projection['nodes']
    by_id = {n['id']: n for n in nodes}
    structure = projection.get('original_structure') or {}
    html = projection['source_kind'] == 'html'

    def object_(kind, a, b, **fields):
        if not 0 <= a < b <= len(text):
            raise ValueError('semantic object outside source')
        key = f'{identity}\0{sha}\0{kind}\0{a}\0{b}'
        return dict(id=hashlib.sha256(key.encode()).hexdigest(), type=kind,
                    entry_identity=identity, start=a, end=b, literal=text[a:b],
                    source_binding=dict(identity=identity, text_sha256=sha),
                    status='derived_source_structure', **fields)

    senses = {n['lexical_record_id']: n['id'] for n in nodes
              if n['kind'] == 'sense' and n.get('lexical_record_id')}
    records = {r.get('ordinal'): r for r in projection.get('original_records', [])
               if r.get('record_type') == 'sense'}
    block_senses = {}
    if html:
        for division in structure.get('divisions', []):
            record = records.get(division['meaning_index'] + 1, {})
            for index in division.get('lexical_block_indices', []):
                block_senses[index] = senses.get(record.get('id'))
    pdf_divisions = {}
    if not html:
        starts, offset = [], 0
        for line in structure.get('visual_lines', []):
            starts.append(offset)
            offset += len(line['text']) + 1
        for index, division in enumerate(structure.get('divisions', [])):
            first, last = division['start_line_index'], division['end_line_index_exclusive']
            a = starts[first]
            b = starts[last - 1] + len(structure['visual_lines'][last - 1]['text'])
            matches = [n['id'] for n in nodes if n['kind'] == 'sense'
                       and (n['start'], n['end']) == (a, b)]
            pdf_divisions[index] = (matches[0] if len(matches) == 1 else None,
                                   division['kind'] == 'unsegmented')
    blocks, items, passages, owners = [], [], [], []
    source_blocks = (structure.get('lexical_blocks', []) if html else
                     structure.get('candidates', {}).get('lexical_blocks', []))
    seen = set()
    for index, block in enumerate(source_blocks):
        loc = block.get('locator', {})
        a = loc.get('visible_text_start') if html else block.get('label_start', block.get('visual_start'))
        b = loc.get('visible_text_end') if html else block.get('visual_end')
        if a is None or b is None or a == b:
            continue
        division_indices = {c.get('division_index') for c in block.get('clauses', [])}
        pdf_owner = pdf_divisions.get(next(iter(division_indices)), (None, False)) if len(division_indices) == 1 else (None, False)
        sense = block_senses.get(index) if html else pdf_owner[0]
        ownership = ('sense' if sense else 'entry' if
                     (html and index in block_senses) or (not html and pdf_owner[1]) else 'unresolved')
        envelope = object_('lex_block', a, b, sense_node_id=sense,
                           ownership=ownership, evidence='explicit HTML division membership' if html else
                           'exact printed numbered/unsegmented division envelope')
        envelope['marker_span'] = dict(start=a, end=a+4, literal=text[a:a+4]) if text[a:a+4] == 'Lex.' else None
        blocks.append(envelope)
        for clause in block.get('clauses', []):
            x, y = clause['start'], clause['end']
            if text[x:y] != clause['source_text'] or not a <= x < y <= b:
                raise ValueError('Lex. clause source contract mismatch')
            if (x, y) in seen:
                raise ValueError('duplicate canonical Lex. item')
            seen.add((x, y))
            clause_diagnostics = lexical_clauses(text, x, y)[1]
            item_sense, item_ownership = sense, ownership
            if not html:
                owner = pdf_divisions.get(clause.get('division_index'), (None, False))
                item_sense = owner[0]
                item_ownership = 'sense' if item_sense else 'entry' if owner[1] else 'unresolved'
            contained = [n for n in nodes if x <= n['start'] < n['end'] <= y]
            fields = {kind: [dict(node_id=n['id'], start=n['start'], end=n['end'],
                                 literal=text[n['start']:n['end']]) for n in contained if n['kind'] == kind]
                      for kind in ('tibetan', 'sanskrit', 'translation', 'citation')}
            sigla = []
            for sig in clause.get('tagged_fields', {}).get('sigla', []):
                sl = sig['locator']; sa, sb = sl['visible_text_start'], sl['visible_text_end']
                if x <= sa < sb <= y:
                    sigla.append(dict(start=sa, end=sb, literal=text[sa:sb]))
            if not html:
                terminal = terminal_lexical_citation(text, x, y)
                if terminal:
                    for match in re.finditer(r'(?:^|,\s*)(?:ähnl\.\s*)?([A-Za-z][A-Za-z0-9’\']*)', text[terminal['start']+1:terminal['end']-1]):
                        sa = terminal['start'] + 1 + match.start(1)
                        sb = terminal['start'] + 1 + match.end(1)
                        sigla.append(dict(start=sa, end=sb, literal=text[sa:sb]))
            relation = ('equivalence' if any(c in text[x:y] for c in ('=', '≅', '≈')) else
                        'gloss' if fields['translation'] else 'unresolved')
            item = object_('lex_item', x, y, block_id=envelope['id'], sense_node_id=item_sense,
                           ownership=item_ownership, relation_type=relation, fields=fields,
                           sigla=sigla, delimiter_diagnostics=clause_diagnostics)
            item['source_locator'] = clause.get('locator') or {k: clause[k] for k in ('source_line', 'source_line_end', 'start_line_index', 'end_line_index', 'line_start', 'line_end', 'division_index') if k in clause}
            items.append(item)
            passage = object_('citable_passage', x, y, passage_type='lex_item',
                              lex_item_id=item['id'], sense_node_id=item_sense,
                              ownership=item_ownership, evidence='bounded source Lex. delimiter clause',
                              citation_node_ids=[] if clause_diagnostics else [c['node_id'] for c in fields['citation']])
            passages.append(passage)
    # Explicit attestation edges are asserted only by the HTML lexical adapter.
    # PDF candidate edges are intentionally excluded here.
    if html:
        grouped = {}
        for edge in projection.get('edges', []):
            if edge.get('kind') == 'citation_of':
                source, target = by_id[edge['from']], by_id[edge['to']]
                if target['kind'] == 'example':
                    grouped.setdefault(target['id'], []).append(source['id'])
        for node_id, cites in grouped.items():
            node = by_id[node_id]
            parent = by_id.get(node.get('parent'), {})
            sense = parent.get('id') if parent.get('kind') == 'sense' else None
            passages.append(object_('citable_passage', node['start'], node['end'],
                            passage_type='example', example_node_id=node_id,
                            sense_node_id=sense, ownership='sense' if sense else 'entry',
                            evidence='explicit DOM attestation association and citation_of edge',
                            citation_node_ids=cites))
    for node in nodes:
        if node['kind'] != 'citation':
            continue
        candidates = [p for p in passages if node['id'] in p['citation_node_ids']]
        if len(candidates) == 1:
            p = candidates[0]
            owners.append(dict(citation_node_id=node['id'], passage_id=p['id'],
                               sense_node_id=p['sense_node_id'], ownership=p['ownership'],
                               evidence=p['evidence'], status='derived_source_structure'))
        elif candidates:
            owners.append(dict(citation_node_id=node['id'], ownership='unresolved',
                               reason='multiple explicit passage candidates',
                               candidate_passage_ids=[p['id'] for p in candidates]))
    # Effective language is derived from explicit source-language observations.
    # A narrower Sanskrit tag/correspondence overrides a broad Tibetan envelope;
    # both observations remain in the source graph for inspection.
    languages = [n for n in nodes if n['kind'] in ('tibetan', 'sanskrit')]
    cuts = sorted({v for n in languages for v in (n['start'], n['end'])})
    effective = []
    for a, b in zip(cuts, cuts[1:]):
        covering = [n for n in languages if n['start'] <= a < b <= n['end']]
        explicit_sa = [n for n in covering if n['kind'] == 'sanskrit' and
                       ('source_evidence' in n or n.get('lexical_record_id'))]
        kinds = {n['kind'] for n in covering}
        language = 'sa' if explicit_sa else 'bo' if kinds == {'tibetan'} else 'sa' if kinds == {'sanskrit'} else 'unresolved'
        if covering:
            effective.append(object_('language_span', a, b, language=language,
                             observation_node_ids=[n['id'] for n in covering],
                             evidence='explicit Sanskrit source field overrides enclosing Tibetan observation' if explicit_sa else 'source language observation'))
    return dict(effective_language_spans=effective, contract_version=VERSION, lex_blocks=blocks, lex_items=items,
                citable_passages=passages, citation_ownership=owners)
