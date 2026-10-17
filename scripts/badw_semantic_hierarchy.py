"""Derived, source-bound Lex. items and citable passages.

Observation nodes remain unchanged. Ownership uses explicit HTML division
membership, validated example edges, or unique Lex. clause containment.
No distance-based association, punctuation repair, or language guessing.
"""
import hashlib
import re
from badw_source_components import lexical_clauses, terminal_lexical_citation
from badw_header_structure import header_fields
from badw_bounded_passages import nested_passages, terminal_comparisons, semicolon_comparisons

VERSION = 'badw-semantic-hierarchy-v4'


def citation_family(projection, text, node):
    """Classify observed containment; this function never asserts an owner."""
    a, b = node['start'], node['end']
    nodes = projection['nodes']
    containing = [n for n in nodes if n['id'] != node['id'] and
                  n['start'] <= a < b <= n['end']]
    crossing = [n for n in nodes if n['kind'] == 'sense' and
                max(a, n['start']) < min(b, n['end']) and
                not n['start'] <= a < b <= n['end']]
    if crossing:
        return 'crossing_sense_boundary'
    if any(n['kind'] == 'example' for n in containing):
        return 'PDF_example_candidate' if projection['source_kind'] == 'pdf' else 'HTML_example_envelope'
    if any(n['kind'] == 'lexical' for n in containing):
        return 'residual_Lex_structure'
    definitions = [n for n in containing if n['kind'] == 'definition']
    if definitions:
        start = min(n['start'] for n in definitions)
        return 'explicit_comparison_clause' if 'vgl.' in text[start:b] else 'definition_clause'
    if any(n['kind'] == 'sense' for n in containing):
        return 'sense_prose_without_bounded_passage'
    if any(n['kind'] == 'source_division' for n in containing):
        return 'entry_prose_without_bounded_passage'
    return 'no_structural_envelope'


def bounded_example_quotes(quote, text):
    """Validate nesting only inside an already established example translation.

    This establishes no quotation role for free prose. Every literal delimiter,
    including all descendants, must already be complete in the source.
    """
    a,b=quote['visual_start'],quote['visual_end']
    if quote.get('diagnostics') or text[a:a+1]!='„' or text[b-1:b]!='“':
        return False
    previous=a
    for child in quote.get('children',[]):
        x,y=child['visual_start'],child['visual_end']
        if not a<x<y<b or x<previous or not bounded_example_quotes(child,text):
            return False
        previous=y
    return True


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

    from badw_contextual_semantics import language_forms
    contextual, language_indicators = language_forms(projection, text)
    forms = [object_('sanskrit_form', f['start'], f['end'], language='sa',
                     evidence=f['evidence'], marker_span=f['marker_span'],
                     **{k:f[k] for k in ('reviewed_reading','decoding_review') if k in f}) for f in contextual]
    correspondences = []

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
            for form in forms:
                if x <= form['start'] < form['end'] <= y:
                    form['lex_item_id'] = object_('lex_item', x, y)['id']
                    if not any(f['start']==form['start'] and f['end']==form['end'] for f in fields['sanskrit']):
                        fields['sanskrit'].append(dict(node_id=form['id'], start=form['start'], end=form['end'], literal=form['literal']))
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
            for form in forms:
                if form.get('lex_item_id') != item['id']: continue
                form['sigla'] = sigla
                # A correspondence requires an explicit equivalence sign.
                # A Sanskrit lemma with Mvy alone remains a sourced form.
                signs = list(re.finditer('[=≅≈]', text[x:form['start']]))
                if not signs: continue
                mark = x+signs[-1].start()
                tibetan = [f for f in fields['tibetan'] if f['end'] <= mark]
                if not tibetan: continue
                antecedent = max(tibetan, key=lambda f:f['end'])
                correspondences.append(dict(id=item['id']+':'+form['id'], lex_item_id=item['id'],
                    sanskrit_form_id=form['id'], tibetan_span=antecedent,
                    marker_span=dict(start=mark,end=mark+1,literal=text[mark]),
                    evidence='explicit Lex. equivalence between source-bound fields',
                    source_binding=item['source_binding']))
            passage = object_('citable_passage', x, y, passage_type='lex_item',
                              lex_item_id=item['id'], sense_node_id=item_sense,
                              ownership=item_ownership, evidence='bounded source Lex. delimiter clause',
                              citation_node_ids=[] if clause_diagnostics else [c['node_id'] for c in fields['citation']])
            passages.append(passage)
    # Explicit attestation edges are asserted only by the HTML lexical adapter.
    # PDF candidate edges alone are intentionally insufficient.
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
    # Promote PDF examples only when independently observed typography agrees
    # with the candidate envelope: italic expression, balanced quoted gloss,
    # whitespace-only attachment, citation, and no crossing sense boundary.
    # Candidate citation_of edges alone are deliberately insufficient.
    assigned = {cid for p in passages for cid in p['citation_node_ids']}
    from badw_lex_assertions import lex_assertions
    passages.extend(lex_assertions(projection, text, items, assigned, object_))
    if not html:
        quotes = {(q['visual_start'], q['visual_end']): q for q in
                  structure.get('candidates', {}).get('german_quotes', [])}
        for node in nodes:
            if node['kind'] != 'example':
                continue
            children = [n for n in nodes if n.get('parent') == node['id']]
            tib = [n for n in children if n['kind'] == 'tibetan']
            gloss = [n for n in children if n['kind'] == 'translation']
            cites = [n for n in children if n['kind'] == 'citation']
            if len(tib) != 1 or len(gloss) != 1 or not cites:
                continue
            t, g = tib[0], gloss[0]
            # Inline references inside the expression can support a local
            # correction rather than the quotation. They neither establish
            # nor invalidate its whitespace-attached terminal attribution.
            cites = [c for c in cites if c['start'] >= g['end']]
            if not cites:
                continue
            q = quotes.get((g['start'], g['end']))
            if not q or q.get('diagnostics') or (q.get('children') and not bounded_example_quotes(q, text)):
                continue
            ordered = sorted(cites, key=lambda n: n['start'])
            if (t['start'] != node['start'] or t['end'] > g['start'] or
                    not re.fullmatch(r'\s*(?:\(metr\.\s*\))?\s*', text[t['end']:g['start']]) or
                    text[g['end']:ordered[0]['start']].strip() or
                    ordered[-1]['end'] != node['end'] or
                    any(text[a['end']:b['start']].strip(' \n\t;,')
                        for a, b in zip(ordered, ordered[1:]))):
                continue
            if any(s['kind'] == 'sense' and
                   max(node['start'], s['start']) < min(node['end'], s['end']) and
                   not s['start'] <= node['start'] < node['end'] <= s['end']
                   for s in nodes):
                continue
            if any(c['id'] in assigned for c in cites):
                continue
            parent = by_id.get(node.get('parent'), {})
            sense = parent.get('id') if parent.get('kind') == 'sense' else None
            passages.append(object_('citable_passage', node['start'], node['end'],
                passage_type='example', example_node_id=node['id'], sense_node_id=sense,
                ownership='sense' if sense else 'entry',
                evidence='PDF italic expression, optional explicit metrical annotation, balanced quoted gloss and whitespace-attached citation',
                source_locator=node.get('source_lines', []),
                citation_node_ids=[c['id'] for c in cites]))
            assigned.update(c['id'] for c in cites)
    # Exact source definition envelopes, not a window around a citation. Reject
    # mixed example/Lex. envelopes and crossed senses. Multiple citations in the
    # same source-defined clause share one owner.
    for node in nodes:
        if node['kind'] != 'definition':
            continue
        a, b = node['start'], node['end']
        cites = [n for n in nodes if n['kind'] == 'citation' and
                 a <= n['start'] < n['end'] <= b and n['id'] not in assigned]
        if not cites or any(n['kind'] in ('example', 'lexical') and
                           max(a, n['start']) < min(b, n['end']) for n in nodes):
            continue
        if any(max(a, x['start']) < min(b, x['end']) for x in blocks):
            continue
        if any(s['kind'] == 'sense' and max(a, s['start']) < min(b, s['end'])
               and not s['start'] <= a < b <= s['end'] for s in nodes):
            continue
        parent = by_id.get(node.get('parent'), {})
        sense = parent.get('id') if parent.get('kind') == 'sense' else None
        # PDF definitions are candidates; require citations syntactically
        # enclosed in a parenthetical or an explicit comparison construction.
        if not html:
            # Eligibility belongs to each occurrence. An additional, unowned
            # inline reference must not invalidate established clause owners.
            cites = [c for c in cites if
                     text[c['start']:c['end']].startswith(('(', 'vgl.')) or
                     re.search(r'\bvgl\.\s*$', text[a:c['start']]) or
                     c.get('source_evidence', {}).get('local_syntax') in
                     ('bounded_parenthesis', 'explicit_comparison')]
            if not cites:
                continue
        passages.append(object_('citable_passage', a, b,
            passage_type='definition_clause', definition_node_id=node['id'],
            sense_node_id=sense, ownership='sense' if sense else 'entry',
            evidence='source definition envelope with embedded citation',
            source_locator=node.get('source_lines', []),
            citation_node_ids=[c['id'] for c in cites]))
        assigned.update(c['id'] for c in cites)
    nested = nested_passages(nodes, text, assigned, object_)
    passages.extend(nested)
    assigned.update(c for p in nested for c in p['citation_node_ids'])
    passages.extend(terminal_comparisons(nodes, text, assigned, object_))
    passages.extend(semicolon_comparisons(nodes, text, assigned, object_))
    from badw_header_assertions import header_assertions
    passages.extend(header_assertions(projection, text, assigned, object_))
    from badw_comparison_clauses import comparison_clauses
    passages.extend(comparison_clauses(projection, text, assigned, object_))
    from badw_source_assertions import source_assertions
    passages.extend(source_assertions(projection, text, assigned, object_))
    for node in nodes:
        if node['kind'] != 'citation':
            continue
        candidates = [p for p in passages if node['id'] in p['citation_node_ids']]
        if len(candidates) == 1:
            p = candidates[0]
            owners.append(dict(citation_node_id=node['id'], passage_id=p['id'],
                               sense_node_id=p['sense_node_id'], ownership=p['ownership'],
                               evidence=p['evidence'], evidence_class=(
                                   'Lex_containment' if p['passage_type'] in ('lex_item', 'lex_assertion') else
                                   'explicit_HTML_attestation' if html and p['passage_type']=='example' else
                                   'PDF_example_quotation' if p['passage_type']=='example' else
                                   'definition_comparison_clause'), status='derived_source_structure'))
        elif candidates:
            owners.append(dict(citation_node_id=node['id'], ownership='unresolved',
                               reason='multiple explicit passage candidates',
                               candidate_passage_ids=[p['id'] for p in candidates]))
    # Effective language is derived from explicit source-language observations.
    # A narrower Sanskrit tag/correspondence overrides a broad Tibetan envelope;
    # both observations remain in the source graph for inspection.
    languages = [n for n in nodes if n['kind'] in ('tibetan', 'sanskrit')]
    conflicts = []
    for bo in (n for n in languages if n['kind']=='tibetan'):
        for sa in (n for n in languages if n['kind']=='sanskrit'):
            a,b=max(bo['start'],sa['start']),min(bo['end'],sa['end'])
            if a<b:
                conflict=object_('language_conflict',a,b,observation_node_ids=[bo['id'],sa['id']],classification='legitimate_nested_observation' if (bo['start'],bo['end'])==(sa['start'],sa['end']) else 'broad_source_envelope',effective_resolution='explicit Sanskrit evidence')
                conflict['id']=hashlib.sha256((conflict['id']+'\0'+bo['id']+'\0'+sa['id']).encode()).hexdigest()
                conflicts.append(conflict)
    contextual_nodes = [dict(f, kind='sanskrit', source_evidence=f['evidence']) for f in forms]
    languages += contextual_nodes
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
    return dict(header_fields=header_fields(projection, text), sanskrit_forms=forms, sanskrit_correspondences=correspondences,
                language_indicators=language_indicators, source_language_conflicts=conflicts, effective_language_spans=effective, contract_version=VERSION, lex_blocks=blocks, lex_items=items,
                citable_passages=passages, citation_ownership=owners)
