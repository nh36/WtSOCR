"""Bounded Roman glosses inside independently established PDF Lex./examples.

Quote punctuation establishes boundaries, never role. Role additionally requires
an existing lexical/example envelope and an immediately preceding italic form,
or an italic lemma-substitution expression, quoted Roman translation and
immediately enclosed source citation in one continuous layout unit.
Raw candidates and source text remain immutable, including nested punctuation.
"""
import copy
import hashlib
import re
from badw_header_structure import contiguous_pdf_lines
from badw_pdf_mixed_clauses import style_runs
from badw_recovered_fragment_integrity import delimiter_error

VERSION = 'pdf-bounded-quotation-v1'


def balanced_quotes(text):
    stack = []
    for i, char in enumerate(text):
        if char == '„':
            stack.append(i)
        elif char == '“':
            if not stack:
                continue
            start = stack.pop()
            if not stack:
                yield dict(visual_start=start, visual_end=i+1, evidence='balanced_literal_quote_sequence')


def recover_quotations(projection, text):
    if projection['source_kind'] != 'pdf':
        return projection
    lines, runs = style_runs(projection, text)
    result = copy.deepcopy(projection)
    for quote in balanced_quotes(text):
        a, b = quote['visual_start'], quote.get('visual_end', quote['visual_start'])
        if not a < b or text[a] != '„' or text[b-1] != '“' or delimiter_error(text[a:b]):
            continue
        inside = [r for r in runs if r['start'] < b and a < r['end']]
        if not inside or any(r['style'] != 'regular' for r in inside):
            continue
        if any(not contiguous_pdf_lines(lines, l['line'], r['line']) for l, r in zip(inside, inside[1:])):
            continue
        envelopes = [n for n in result['nodes'] if n['kind'] in ('example', 'lexicographic', 'lexical_parallel')
                     and n['start'] <= a < b <= n['end']]
        additions = []
        citation_to_reparent = None
        if not envelopes:
            # Independently bounded substitution example: italic expression
            # containing the printed lemma substitution, Roman quoted gloss,
            # then an existing parenthesized source citation. No nearest-sense
            # or nearest-example association is used.
            prior = [r for r in runs if r['end'] <= a]
            if not prior or prior[-1]['style'] != 'italic' or text[prior[-1]['end']:a].strip():
                continue
            form = [prior[-1]]
            for run in reversed(prior[:-1]):
                if run['style'] != 'italic' or text[run['end']:form[0]['start']].strip():
                    break
                if not contiguous_pdf_lines(lines, run['line'], form[0]['line']):
                    break
                form.insert(0, run)
            start = form[0]['start']
            # Editorially bracketed initial letters interrupt font runs.
            # Include the whole observed bracket, never a truncated suffix.
            earlier = [r for r in prior if r['end'] <= start]
            if text[:start].endswith(']'):
                if len(earlier) < 3:
                    continue
                opening, letter, closing = earlier[-3:]
                if (text[opening['start']:opening['end']] != '['
                    or text[closing['start']:closing['end']] != ']'
                    or letter['style'] != 'italic'
                    or not text[letter['start']:letter['end']].isalpha()
                    or opening['end'] != letter['start']
                    or letter['end'] != closing['start']
                    or closing['end'] != start):
                    continue
                form = [opening, letter, closing] + form
                start = opening['start']
            elif start and not text[start-1].isspace() and text[start-1] not in ';.:':
                continue
            if '~' not in text[start:a] or delimiter_error(text[start:a]):
                continue
            if not contiguous_pdf_lines(lines, form[-1]['line'], inside[0]['line']):
                continue
            citations = [n for n in result['nodes'] if n['kind'] == 'citation'
                         and n['start'] >= b and not text[b:n['start']].strip()]
            if len(citations) != 1:
                continue
            citation = citations[0]
            end = citation['end']
            if not text[citation['start']:end].startswith('(') or delimiter_error(text[citation['start']:end]):
                continue
            tail = [r for r in runs if r['start'] < end and b <= r['end']]
            if not tail or any(not contiguous_pdf_lines(lines, l['line'], r['line'])
                               for l, r in zip(inside[-1:]+tail, tail)):
                continue
            if any(n['kind'] not in ('source_division', 'sense') and n['id'] != citation['id']
                   and n['start'] < end and start < n['end'] for n in result['nodes']):
                continue
            parents = [n for n in result['nodes'] if n['kind'] in ('sense', 'source_division')
                       and n['start'] <= start < end <= n['end']]
            if not parents:
                continue
            parent = min(parents, key=lambda n: n['end']-n['start'])
            key = f"{projection['identity']}:{VERSION}:example:{start}:{end}"
            example_id = 'recovered-example:'+hashlib.sha256(key.encode()).hexdigest()
            evidence = dict(rule=VERSION, role='italic_substitution_quoted_translation_citation')
            owner = dict(id=example_id, kind='example', start=start, end=end,
                         parent=parent['id'], structural_recovery=evidence,
                         source_evidence=dict(rule=VERSION, typography=form+inside+tail,
                                              citation_node=citation['id']))
            additions = [owner, dict(id=example_id+':form', kind='tibetan',
                start=start, end=a-1 if text[a-1:a].isspace() else a,
                parent=example_id, source_evidence=dict(rule=VERSION, typography=form))]
            citation_to_reparent = citation
            envelopes = [owner]
        owner = min(envelopes, key=lambda n: n['end']-n['start'])
        left = [r for r in runs if owner['start'] <= r['start'] < r['end'] <= a]
        if not left or left[-1]['style'] != 'italic' or text[left[-1]['end']:a].strip():
            continue
        if not contiguous_pdf_lines(lines, left[-1]['line'], inside[0]['line']):
            continue
        # A complete translation cannot be made by subtracting existing pieces.
        # Citation, sense or sibling Lex. crossings reject the whole production.
        crossing = [n for n in result['nodes'] if n['start'] < b and a < n['end']
                    and n['kind'] not in ('source_division', 'sense', 'example', 'lexicographic', 'lexical_parallel')]
        if crossing:
            continue
        if any(n['kind'] in ('sense', 'lexicographic', 'lexical_parallel')
               and n['start'] < b and a < n['end'] and not n['start'] <= a < b <= n['end']
               for n in result['nodes']):
            continue
        result['nodes'].extend(additions)
        if citation_to_reparent is not None:
            citation_to_reparent['parent'] = owner['id']
            citation_to_reparent['derived_parent_evidence'] = owner['structural_recovery']
        key = f"{projection['identity']}:{VERSION}:{a}:{b}"
        result['nodes'].append(dict(id='recovered-translation:'+hashlib.sha256(key.encode()).hexdigest(),
            kind='translation', start=a, end=b, parent=owner['id'],
            source_evidence=dict(rule=VERSION, quoted_span=quote, typography=inside,
                                 italic_form_span=dict(start=left[-1]['start'], end=left[-1]['end'])),
            structural_recovery=dict(rule=VERSION, role='bounded_lexical_or_example_gloss')))
    return result
