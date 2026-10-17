"""Strict nested passage grammar; source observations are never modified.

Only balanced source delimiters establish these envelopes. Citation identity,
distance and the presence of a nearby example are not boundary evidence.
"""
import re

PAIRS = {')': '(', ']': '[', '“': '„', '‘': '‚', '»': '«'}


def envelopes(text):
    stack, result = [], []
    for i, char in enumerate(text):
        if char in PAIRS.values():
            stack.append((char, i))
        elif char in PAIRS:
            if not stack or stack[-1][0] != PAIRS[char]:
                # A malformed enclosure cannot license an enclosing passage.
                stack.clear()
                continue
            opener, start = stack.pop()
            result.append((start, i + 1, opener))
    return result


def nested_passages(nodes, text, assigned, object_):
    result = []
    bounded = envelopes(text)
    for cite in nodes:
        if cite['kind'] != 'citation' or cite['id'] in assigned:
            continue
        a, b = cite['start'], cite['end']
        candidates = []
        for start, end, opener in bounded:
            if not start <= a < b <= end:
                continue
            containers = [n for n in nodes if n['kind'] in
                          ('example', 'definition', 'lexical', 'sense', 'source_division')
                          and n['start'] <= start < end <= n['end']]
            if not containers:
                continue
            if any(n['kind'] in ('sense', 'lexical') and
                   max(start, n['start']) < min(end, n['end']) and
                   not n['start'] <= start < end <= n['end'] for n in nodes):
                continue
            prefix = text[start + 1:a]
            suffix = text[b:end - 1]
            substantive = re.sub(r'\W', '', prefix + suffix)
            kinds = {n['kind'] for n in containers}
            correction = next((n for n in nodes if n['kind'] == 'correction'
                               and n['start'] == start and n['end'] == end), None)
            short_variant = (opener == '(' and 'example' in kinds
                             and correction is not None
                             and re.match(r'\s*(?:v\.\s*l\.|r\.)\s+\S', prefix))
            if len(substantive) < 4 and not short_variant:
                continue  # A citation's own parentheses prove no assertion.
            if re.match(r'\s*vgl\.\s+', prefix):
                kind = 'bounded_comparison'
            elif 'example' in kinds and re.match(r'\s*(?:v\.\s*l\.|r\.)\s+', prefix):
                kind = 'variant_reading'
            elif opener == '„' and 'example' in kinds and any(
                    n['kind'] == 'translation' and n['start'] <= start < end <= n['end']
                    for n in nodes):
                kind = 'quoted_translation'
            elif opener == '(' and 'definition' in kinds and re.match(r'\s*(?:zw\.|skt\.)\s+', prefix):
                kind = 'definition_source_note'
            else:
                continue
            container = min(containers, key=lambda n: n['end'] - n['start'])
            senses = [n for n in containers if n['kind'] == 'sense']
            sense = min(senses, key=lambda n: n['end']-n['start'])['id'] if senses else None
            correction_id = correction['id'] if short_variant and len(substantive) < 4 else None
            candidates.append((end-start, start, end, kind, container, sense, correction_id))
        if not candidates:
            continue
        _, start, end, kind, container, sense, correction_id = min(candidates, key=lambda x: x[0])
        key = (start, end, kind, container['id'])
        existing = next((p for p in result if p['_key'] == key), None)
        if existing:
            existing['citation_node_ids'].append(cite['id'])
        else:
            boundary = dict(opener=text[start], closer=text[end-1],
                            containing_kind=container['kind'])
            if correction_id is not None:
                boundary['correction_node_id'] = correction_id
            result.append(object_('citable_passage', start, end,
                passage_type=kind, containing_node_id=container['id'],
                sense_node_id=sense, ownership='sense' if sense else 'entry',
                evidence='balanced source enclosure, explicit local syntax and exact component containment',
                boundary_evidence=boundary,
                citation_node_ids=[cite['id']], _key=key))
    for passage in result:
        del passage['_key']
    return result


def terminal_comparisons(nodes, text, assigned, object_):
    """Explicit vgl. tail bounded by an independently parsed definition end.

    Earlier examples may intersect the definition envelope; they cannot
    intersect this local clause. A citation alone never supplies its end.
    """
    result = []
    for definition in nodes:
        if definition['kind'] != 'definition':
            continue
        a, b = definition['start'], definition['end']
        markers = list(re.finditer(r'\bvgl\.\s+', text[a:b]))
        if not markers:
            continue
        start = a + markers[-1].start()
        literal = text[start:b]
        if not re.search(r'[.;]\s*$', literal):
            continue
        # Every delimiter in the clause must participate in a balanced pair.
        covered = {v for s, e, _ in envelopes(literal) for v in (s, e-1)}
        if any(c in '()[]„“‚‘«»' and i not in covered for i, c in enumerate(literal)):
            continue
        if any(n['kind'] in ('example', 'lexical', 'lexical_parallel', 'lex_block') and
               max(start, n['start']) < min(b, n['end']) for n in nodes):
            continue
        if any(n['kind'] == 'sense' and max(start, n['start']) < min(b, n['end'])
               and not n['start'] <= start < b <= n['end'] for n in nodes):
            continue
        cites = [n for n in nodes if n['kind'] == 'citation' and
                 start <= n['start'] < n['end'] <= b and n['id'] not in assigned]
        if not cites or re.sub(r'[\s.;]', '', text[max(n['end'] for n in cites):b]):
            continue
        senses = [n for n in nodes if n['kind']=='sense' and n['start']<=start<b<=n['end']]
        sense = min(senses, key=lambda n:n['end']-n['start'])['id'] if senses else None
        result.append(object_('citable_passage', start, b,
            passage_type='terminal_comparison', containing_node_id=definition['id'],
            sense_node_id=sense, ownership='sense' if sense else 'entry',
            evidence='explicit comparison marker and independent definition terminal boundary',
            boundary_evidence=dict(marker='vgl.', containing_kind='definition', terminal=text[b-1:b]),
            citation_node_ids=[n['id'] for n in cites]))
        assigned.update(n['id'] for n in cites)
    return result


def semicolon_comparisons(nodes, text, assigned, object_):
    """A comparison closed by a top-level semicolon inside a definition.

    The marker and punctuation establish the passage before citations are
    considered. Delimiters, competing components and sense boundaries fail
    closed; neither a citation nor its bibliography identity supplies an end.
    """
    result = []
    for definition in nodes:
        if definition['kind'] != 'definition':
            continue
        a, b = definition['start'], definition['end']
        for marker in re.finditer(r'\bvgl\.\s+', text[a:b]):
            start = a + marker.start()
            # Parenthetical comparisons belong to the enclosure grammar.
            if any(s < start < e for s, e, _ in envelopes(text)
                   if s >= a and e <= b):
                continue
            stack, end = [], None
            for i in range(start, b):
                char = text[i]
                if char in PAIRS.values():
                    stack.append(char)
                elif char in PAIRS:
                    if not stack or stack.pop() != PAIRS[char]:
                        break
                elif char == ';' and not stack:
                    end = i + 1
                    break
                elif char == '.' and not stack:
                    token = re.search(r'([\w]+)$', text[start:i])
                    abbreviation = token and token[1] in ('vgl', 'f', 'ff', 'Nr', 'Anm', 's', 'v', 'Bd')
                    decimal = i > start and text[i-1].isdigit() and i+1 < b and text[i+1].isdigit()
                    if not abbreviation and not decimal:
                        break
            if end is None:
                continue
            if any(n['kind'] in ('example', 'lexical', 'lexical_parallel', 'lex_block')
                   and max(start, n['start']) < min(end, n['end']) for n in nodes):
                continue
            if any(n['kind'] == 'sense' and
                   max(start, n['start']) < min(end, n['end']) and
                   not n['start'] <= start < end <= n['end'] for n in nodes):
                continue
            cites = [n for n in nodes if n['kind'] == 'citation' and
                     start <= n['start'] < n['end'] <= end and n['id'] not in assigned]
            if not cites:
                continue
            senses = [n for n in nodes if n['kind'] == 'sense' and
                      n['start'] <= start < end <= n['end']]
            sense = min(senses, key=lambda n: n['end']-n['start'])['id'] if senses else None
            result.append(object_('citable_passage', start, end,
                passage_type='semicolon_comparison', containing_node_id=definition['id'],
                sense_node_id=sense, ownership='sense' if sense else 'entry',
                evidence='explicit comparison marker and balanced top-level semicolon within definition',
                boundary_evidence=dict(marker='vgl.', terminal=';', containing_kind='definition'),
                citation_node_ids=[n['id'] for n in cites]))
            assigned.update(n['id'] for n in cites)
    return result
