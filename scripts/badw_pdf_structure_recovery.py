"""Recover missing definition fragments from explicit PDF header typography.

Existing observations are immutable. Only uncovered portions of an independently
bounded Roman opening gloss are added; later prose is never selected by proximity.
"""
import copy
import hashlib
import re
from badw_header_structure import header_fields, contiguous_pdf_lines

from badw_recovered_fragment_integrity import bounded_definition_end, definition_error

# Stable IDs remain unchanged for unchanged accepted spans.
VERSION = 'pdf-opening-gloss-recovery-v3'


def recover_opening(projection, text):
    if projection['source_kind'] != 'pdf':
        return projection
    headers = header_fields(projection, text)
    targets = [h for h in headers if h['header_kind'] in ('header_relation', 'alternate_headword', 'verb_form')]
    if not targets:
        return projection
    end = max(h['end'] for h in targets)
    styles, offset = [], 0
    lines = (projection.get('original_structure') or {}).get('visual_lines', [])
    for i, line in enumerate(lines):
        if text[offset:offset + len(line['text'])] != line['text']:
            raise ValueError('PDF recovery line differs from source')
        for s in line.get('style_spans', []):
            styles.append((offset+s['start'], offset+s['end'], s.get('style'),
                           dict(line_index=i, page_id=line.get('page_id'),
                                printed_page=line.get('printed_page'), style_span=s)))
        offset += len(line['text']) + 1
    a = end
    while a < len(text) and text[a].isspace():
        a += 1
    first = next((i for i, (x,y,style,loc) in enumerate(styles)
                  if x <= a < y and style == 'regular'), None)
    if first is None:
        return projection
    b = styles[first][1]
    locations = [styles[first][3]]
    for x,y,style,loc in styles[first+1:]:
        if style != 'regular' or not re.fullmatch(r'\s*', text[b:x]):
            break
        # A new numbered sense or physical page is a hard boundary.
        if not contiguous_pdf_lines(lines, locations[-1]['line_index'], loc['line_index']) or re.match(r'\s*\d+\.', text[x:y]):
            break
        b = y
        locations.append(loc)
    boundary = re.search(r'Lex\.|[།↑↓]|\n\s*\d+\.', text[a:b])
    if boundary:
        b = a + boundary.start()
    # Opening definitions may have quoted glosses, but an unbalanced quote is
    # insufficient evidence. Semicolons delimit separate constructions.
    if ';' in text[a:b]:
        b = a + text[a:b].index(';')
    while b > a and text[b-1].isspace():
        b -= 1
    b = bounded_definition_end(text, a, b)
    literal = text[a:b]
    # A second header connective, reference introducer or paradigm marker is
    # not a German opening gloss. It requires its own target grammar.
    if re.match(r'\s*[,;]?\s*(?:auch\b|vgl\.|pf\.|fut\.|imp\.|imper\.|präs\.|Kurzf\.)', literal):
        return projection
    if not any(c.isalpha() for c in literal) or len(literal) > 500:
        return projection
    if definition_error(literal):
        return projection
    # A pre-existing example/Lex. observation forbids reinterpretation.
    forbidden = {'example', 'lexicographic', 'lexicon', 'citation', 'sanskrit', 'tibetan'}
    if any(n['kind'] in forbidden and n['start'] < b and a < n['end']
           for n in projection['nodes']):
        return projection
    occupied = sorted((max(a,n['start']),min(b,n['end'])) for n in projection['nodes']
                      if n['kind'] == 'definition' and n['start'] < b and a < n['end'])
    gaps, cursor = [], a
    for x,y in occupied:
        if cursor < x:
            gaps.append((cursor,x))
        cursor = max(cursor,y)
    if cursor < b:
        gaps.append((cursor,b))
    containers = [n for n in projection['nodes']
                  if n['kind'] in ('sense', 'source_division')
                  and n['start'] <= a < b <= n['end']]
    if not containers:
        return projection
    parent = min(containers, key=lambda n: (n['end']-n['start'], n['id']))['id']
    result = copy.deepcopy(projection)
    for x,y in gaps:
        while x < y and text[x].isspace(): x += 1
        while y > x and text[y-1].isspace(): y -= 1
        if not any(c.isalpha() for c in text[x:y]) or definition_error(text[x:y]): continue
        key = f"{projection['identity']}:{VERSION}:{x}:{y}"
        node = dict(id='recovered-definition:'+hashlib.sha256(key.encode()).hexdigest(),
                    kind='definition', start=x, end=y, parent=parent,
                    source_lines=locations,
                    source_evidence=dict(rule=VERSION, exact_header_end=end,
                                         envelope=dict(start=a,end=b,literal=literal)),
                    structural_recovery=dict(rule=VERSION, role='opening_definition',
                        envelope=dict(start=a,end=b,literal=literal),
                        continuation_of=[n['id'] for n in projection['nodes']
                                         if n['kind']=='definition' and n['start']<b and a<n['end']]))
        result['nodes'].append(node)
    return result


def recover_hyphenated_definitions(projection, text):
    """Continue an observed Roman definition across an explicit printed hyphen.

    The hyphen, adjacent physical baseline, same column, and uninterrupted
    Roman run jointly establish the continuation. A style change, semicolon,
    new sense, citation or example is a hard stop. No lexical nearness rule.
    """
    lines = (projection.get('original_structure') or {}).get('visual_lines', [])
    spans, offset = [], 0
    for i, line in enumerate(lines):
        for s in line.get('style_spans', []):
            spans.append((offset+s['start'], offset+s['end'], s.get('style'), i))
        offset += len(line['text']) + 1
    result = projection
    for node in projection['nodes']:
        if node['kind'] != 'definition':
            continue
        end = node['end']
        if not text[:end].endswith('-'):
            continue
        left = next((s for s in spans if s[0] < end == s[1] and s[2] == 'regular'), None)
        right = next((s for s in spans if s[0] > end and s[2] == 'regular'), None)
        if not left or not right or text[end:right[0]] != '\n':
            continue
        if not contiguous_pdf_lines(lines, left[3], right[3]):
            continue
        a, b = right[:2]
        if not re.match(r'[a-zäöüß]', text[a:b]):
            continue
        boundary = re.search(r';|Lex\.|[།↑↓]|\n\s*\d+\.', text[a:b])
        if boundary:
            b = a + boundary.start()
        while b > a and text[b-1].isspace(): b -= 1
        b = bounded_definition_end(text, a, b)
        if not a < b or definition_error(text[a:b]) or definition_error(text[node['start']:b]):
            continue
        if any(n['kind'] not in ('sense','source_division') and n['start'] < b and a < n['end']
               for n in result['nodes']):
            continue
        containers = [n for n in projection['nodes'] if n['kind'] in ('sense','source_division')
                      and n['start'] <= node['start'] < b <= n['end']]
        if not containers:
            continue
        if result is projection:
            result = copy.deepcopy(projection)
        parent = min(containers,key=lambda n:n['end']-n['start'])['id']
        key = f"{projection['identity']}:{VERSION}:hyphen:{a}:{b}"
        result['nodes'].append(dict(id='recovered-definition:'+hashlib.sha256(key.encode()).hexdigest(),
            kind='definition',start=a,end=b,parent=parent,
            source_evidence=dict(rule=VERSION,hyphen_span=dict(start=end-1,end=end),
                                 physical_lines=[left[3],right[3]]),
            structural_recovery=dict(rule=VERSION,role='hyphenated_definition_continuation',
                                     continuation_of=[node['id']],
                                     envelope=dict(start=node['start'],end=b,literal=text[node['start']:b]))))
    return result


def recover(projection, text):
    if projection['source_kind'] != 'pdf':
        return projection
    from badw_pdf_mixed_clauses import recover_mixed_clauses
    from badw_pdf_quotation_recovery import recover_quotations
    return recover_quotations(recover_mixed_clauses(recover_hyphenated_definitions(recover_opening(projection,text),text),text),text)
