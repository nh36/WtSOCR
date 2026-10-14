"""Exact header fields from the source heading, never from definition proximity.

HTML heading ancestry comes from the observed lemma locator. Alias forms need
an explicit ``auch`` and a source <tib> field. Grammatical labels must be
complete source text leaves. Remaining heading prose stays reviewable.
PDF article text often starts after the printed heading; absent headings are
not reconstructed from a lemma string or lexical text.
"""
import hashlib
import re

VERSION = 'badw-header-structure-v7'
GRAMMAR = re.compile(r'(?:pf\.|präs\.|pr\.|fut\.|imp\.|imper\.|vb\.|v\. tr\.|v\. intr\.|trans\.|intrans\.|subst\.|adj\.|adv\.|postpos\.)', re.I)


TENSE_MARKER = r'(?:pf\.|fut\.|imp\.|imper\.)'
RELATION_LABEL = (
    r'(?:Kurzf\.(?:\s+für)?|alttib\.(?:\s+für)?|vgl\.|'
    r'Verbalnomen\s+zu|ungenau\s+für|'
    + TENSE_MARKER + r'(?:\s+(?:und|bzw\.)\s+' + TENSE_MARKER + r')?(?:\s+(?:zu|von)|(?=\s*[↑↓])))')
RELATION_MARKER = re.compile(
    r'(' + RELATION_LABEL + r')\s*[↑↓]?\s*(?P<homonym>\d+)?\s*$')
RELATION_TYPES = {'pf.': 'perfect_of', 'fut.': 'future_of',
                  'imp.': 'imperative_of', 'imper.': 'imperative_of'}
LIST_CONNECTOR = re.compile(r'\s*(?:,|bzw\.|und)\s*[↑↓]?\s*(?:\d+)?\s*')


def relation_types(label):
    """Preserve direction: a bare Kurzf. lists the entry's shortened form."""
    label = re.sub(r'\s+', ' ', label).strip()
    special = {'Kurzf. für': 'short_form_of', 'Kurzf.': 'has_short_form',
               'alttib. für': 'historical_form_of', 'alttib.': 'has_historical_form',
               'vgl.': 'compare_with', 'Verbalnomen zu': 'verbal_noun_of',
               'ungenau für': 'imprecise_form_of'}
    if label in special:
        return [special[label]]
    return [RELATION_TYPES[x] for x in re.findall(r'pf\.|fut\.|imp\.|imper\.', label)]


def list_members(text, a, b):
    """Exact members separated by explicit header list punctuation/connectives."""
    start = a
    for separator in re.finditer(r',|\bbzw\.|\bund\b', text[a:b]):
        yield start, a + separator.start()
        start = a + separator.end()
    yield start, b


def heading_fragments(projection):
    if projection['source_kind'] != 'html':
        return []
    structure = projection.get('original_structure') or {}
    path = structure.get('lemma_field', {}).get('locator', {}).get('dom_path', '')
    # The source lemma is a field inside the main-headword span in the heading.
    match = re.fullmatch(r'(.*/div\[\d+\])/span\[1\]/span\[\d+\]', path)
    if not match:
        return []
    root = match.group(1) + '/'
    return [f for f in structure.get('text_fragments', [])
            if f.get('dom_path', '').startswith(root)
            and f.get('visible_text_start') is not None and f.get('visible_text_end') is not None]


def contiguous_pdf_lines(lines, left, right):
    """Same source line, or consecutive baselines in the same printed column.

    Coordinates use the source adapter's transformed units. Missing geometry
    permits same-line evidence only, never inferred physical wrapping.
    """
    if left == right:
        return True
    if right != left + 1:
        return False
    a, b = lines[left], lines[right]
    if (a.get('page_id'), a.get('printed_page')) != (b.get('page_id'), b.get('printed_page')):
        return False
    if any(row.get(key) is None for row in (a, b) for key in ('first_x', 'y')):
        return False
    return abs(a['first_x'] - b['first_x']) < 20 and 0 < a['y'] - b['y'] < 4


def pdf_heading_fields(projection, text, add, cursor=0):
    """Explicit initial header connective plus contiguous printed italic field.

    A regular-font German continuation terminates the field. Italics alone
    never establish a header, and a connective later in prose is insufficient.
    """
    lines = (projection.get('original_structure') or {}).get('visual_lines', [])
    styles, offset = [], 0
    for index, line in enumerate(lines):
        if text[offset:offset + len(line['text'])] != line['text']:
            raise ValueError('PDF header line differs from source')
        for span in line.get('style_spans', []):
            if span.get('style') == 'italic':
                styles.append((offset + span['start'], offset + span['end'],
                               dict(line_index=index, page_id=line.get('page_id'),
                                    printed_page=line.get('printed_page'), style_span=span)))
        offset += len(line['text']) + 1
    marker = re.compile(
        r'\s*(?:[.,]\s*)?(?:\d+\.\s*)?(?P<label>' + RELATION_LABEL + r'|auch|' + TENSE_MARKER + r'(?:\s+und\s+' + TENSE_MARKER + r')?)'
        r'\s*[↑↓]?\s*(?P<homonym>\d+)?\s*').match(text, cursor)
    if not marker:
        return
    a = marker.end()
    first = next((i for i, (x, y, loc) in enumerate(styles) if x == a), None)
    if first is None:
        return
    b = styles[first][1]
    locations = [styles[first][2]]
    for x, y, loc in styles[first + 1:]:
        connector = text[b:x]
        if not contiguous_pdf_lines(lines, locations[-1]['line_index'], loc['line_index']):
            break
        # Only physical whitespace wrapping or an explicit list connective
        # joins printed italic fields. Roman explanation/sense labels stop it.
        alias_connector = marker.group('label') == 'auch' and re.fullmatch(r'\s*,\s*(?:auch\s*)?', connector)
        if not (re.fullmatch(r'\s*', connector) or LIST_CONNECTOR.fullmatch(connector) or alias_connector):
            break
        b = y
        locations.append(loc)
    while b > a and text[b - 1].isspace():
        b -= 1
    label = re.sub(r'\s+', ' ', marker.group('label'))
    ma = marker.start('label')
    list_kind = 'alias-list' if label == 'auch' else 'relation-list'
    for fa, fb in list_members(text, a, b):
        fa += len(text[fa:fb]) - len(text[fa:fb].lstrip())
        fb = fa + len(text[fa:fb].rstrip())
        qualifier = re.match(r'[↑↓]\s*(?P<homonym>\d+)?\s*', text[fa:fb])
        homonym = marker.group('homonym') if fa == a else None
        if qualifier:
            homonym = qualifier.group('homonym')
            fa += qualifier.end()
        alias_marker = None
        if label == 'auch':
            alias_marker = re.match(r'auch\s+', text[fa:fb])
            if alias_marker:
                fa += alias_marker.end()
        if fa >= fb:
            continue
        if re.fullmatch(TENSE_MARKER + r'(?:\s+und\s+' + TENSE_MARKER + r')?', label):
            add('verb_form', ma if fa == a else fa, fb,
                'initial grammatical marker and contiguous PDF italic paradigm field',
                label_span=dict(start=ma,end=a,literal=text[ma:a]),
                form_span=dict(start=fa,end=fb,literal=text[fa:fb]),
                list_id=f"{projection['identity']}:paradigm-list:{ma}", source_locators=locations)
        elif label != 'auch':
            kinds = relation_types(label)
            add('header_relation', ma if fa == a else fa, fb,
                'initial explicit connective and contiguous PDF italic target list',
                relation_type=kinds[0], relation_types=kinds, direction='entry_to_target',
                target_span=dict(start=fa,end=fb,literal=text[fa:fb]), target_homonym=homonym,
                marker_span=dict(start=ma,end=a,literal=text[ma:a]),
                list_id=f"{projection['identity']}:{list_kind}:{ma}", source_locators=locations)

        else:
            add('alternate_headword', ma if fa == a else fa, fb,
                'initial auch and contiguous PDF italic alias list',
                form_span=dict(start=fa,end=fb,literal=text[fa:fb]),
                marker_span=dict(start=ma,end=ma+4,literal=text[ma:ma+4]),
                list_id=f"{projection['identity']}:{list_kind}:{ma}", source_locators=locations)
    # A chain remains a heading only across another explicit marker and its
    # contiguous italic field. A Roman gloss terminates it; body markers cannot
    # restart this grammar. Keep every marker and target's absolute offsets.
    following = re.match(r'\s*(?:,\s*)?(?:' + RELATION_LABEL + r'|auch|' + TENSE_MARKER + r')', text[b:])
    if following and b > cursor:
        next_italic = next((loc for x, y, loc in styles if x >= b), None)
        continuous = next_italic and contiguous_pdf_lines(lines, locations[-1]['line_index'], next_italic['line_index'])
        # The adapter puts an arrow and superscript homonym on separate
        # physical lines. Bridge only those exact observed xref lines, never
        # arbitrary missing prose or another column.
        if next_italic and not continuous:
            left, right = locations[-1]['line_index'], next_italic['line_index']
            between = lines[left + 1:right]
            same_page = all((line.get('page_id'), line.get('printed_page')) ==
                (lines[left].get('page_id'), lines[left].get('printed_page'))
                for line in lines[left:right + 1])
            xref = any(n['kind'] == 'cross_reference' and b <= n['start'] < n['end']
                and n['start'] <= next(x for x, y, loc in styles if loc == next_italic) < n['end']
                for n in projection.get('nodes', []))
            continuous = bool(between and same_page and xref
                and all(re.fullmatch(r'\s*(?:[↑↓]|\d+)\s*', line['text']) for line in between)
                and all(line.get('first_x') is not None and line.get('y') is not None
                    for line in (lines[left], lines[right]))
                and ((abs(lines[left]['first_x'] - lines[right]['first_x']) < 20
                      and abs(lines[left]['y'] - lines[right]['y']) < 4)
                     or (abs(lines[left]['y'] - lines[right]['y']) < .1
                         and 0 < lines[right]['first_x'] - lines[left]['first_x'] < 100)))
        if next_italic and continuous:
            pdf_heading_fields(projection, text, add, cursor=b)



def header_fields(projection, text):
    fragments = heading_fragments(projection)
    result = []
    def add(kind, a, b, evidence, **fields):
        if not 0 <= a < b <= len(text):
            raise ValueError('header outside source')
        key = '\0'.join((projection['identity'], projection['review_text_sha256'], kind, str(a), str(b)))
        result.append(dict(id=hashlib.sha256(key.encode()).hexdigest(), type='header_field',
            header_kind=kind, start=a, end=b, literal=text[a:b],
            entry_identity=projection['identity'], status='derived_source_structure',
            source_binding=dict(identity=projection['identity'],text_sha256=projection['review_text_sha256']),
            evidence=evidence, **fields))
    if projection['source_kind'] == 'pdf':
        pdf_heading_fields(projection, text, add)
    for i, f in enumerate(fragments):
        a,b=f['visible_text_start'],f['visible_text_end']
        if text[a:b] != f['source_text']:
            raise ValueError('header fragment source mismatch')
        value=text[a:b].strip()
        if not value:
            continue
        a += len(text[a:b])-len(text[a:b].lstrip()); b=a+len(value)
        if re.search(r'/span\[1\]/sup\[\d+\]/text\(\)',f['dom_path']) and value.isdigit():
            add('homonym_marker',a,b,'superscript within source lemma heading',source_locator=f)
        elif GRAMMAR.fullmatch(value):
            add('grammatical_label',a,b,'complete labelled heading leaf',source_locator=f)
    # Group all leaves of one explicit Tibetan field, including nested markup.
    # A field is a source object; comma-separated forms within it are a list.
    groups = {}
    for f in fragments:
        match = re.search(r'^(.*?/tib\[\d+\])/', f['dom_path'])
        if match:
            groups.setdefault(match.group(1), []).append(f)
        elif re.search(r'/a\[\d+\]/text\(\)', f['dom_path']):
            groups.setdefault(f['dom_path'].rsplit('/text()', 1)[0], []).append(f)
    aliases = {}
    active_relations = {}
    relation_marker_spans = {}
    for path, leaves in sorted(groups.items(), key=lambda pair: pair[1][0]['visible_text_start']):
        a = min(f['visible_text_start'] for f in leaves)
        b = max(f['visible_text_end'] for f in leaves)
        a += len(text[a:b]) - len(text[a:b].lstrip())
        b = a + len(text[a:b].rstrip())
        if a >= b:
            continue
        parent = path.split('/tib[')[0] if '/tib[' in path else path.rsplit('/a[', 1)[0]
        if '/a[' in path and '/tib[' not in path:
            # An arrow wrapper may nest the link below the connective. Use
            # its enclosing heading field, never another heading or body div.
            root = re.fullmatch(r'(.*/div\[\d+\])/span\[1\]/span\[\d+\]',
                projection['original_structure']['lemma_field']['locator']['dom_path']).group(1)
            child = path[len(root) + 1:].split('/', 1)[0]
            parent = root + '/' + child
        preceding = [f for f in fragments if f['visible_text_end'] <= a
                     and f['dom_path'].startswith(parent + '/')]
        prefix = ''.join(f['source_text'] for f in preceding)
        relation = RELATION_MARKER.search(prefix)
        ma = None
        if relation:
            source_marker = RELATION_MARKER.search(text[:a])
            if source_marker is None:
                raise ValueError('header relation source mismatch')
            ma = source_marker.start()
            kinds = relation_types(relation.group(1))
            relation_marker_spans[ma] = dict(start=ma, end=a, literal=text[ma:a])
            active_relations[parent] = (ma, a, kinds, source_marker.group('homonym'))
        elif parent in active_relations:
            old_ma, previous_end, kinds, homonym = active_relations[parent]
            connector = text[previous_end:a]
            if LIST_CONNECTOR.fullmatch(connector):
                ma = old_ma
                number = re.search(r'(\d+)\s*$', connector)
                active_relations[parent] = (ma, a, kinds, number.group(1) if number else None)
            else:
                active_relations.pop(parent)
        if ma is not None:
            ma, _, kinds, homonym = active_relations[parent]
            for fa, fb in list_members(text, a, b):
                fa += len(text[fa:fb]) - len(text[fa:fb].lstrip())
                fb = fa + len(text[fa:fb].rstrip())
                if fa >= fb:
                    continue
                add('header_relation', ma if relation and fa == a else fa, fb,
                    'explicit heading connective and source target field; shared list marker only across explicit connectors',
                    relation_type=kinds[0], relation_types=kinds, direction='entry_to_target',
                    target_span=dict(start=fa, end=fb, literal=text[fa:fb]),
                    target_homonym=homonym if fa == a else None,
                    marker_span=relation_marker_spans[ma],
                    list_id=f"{projection['identity']}:relation-list:{ma}", source_locators=leaves)
            active_relations[parent] = (ma, b, kinds, homonym)
            aliases.pop(parent, None)
            continue
        marker = re.search(r'\bauch\s*$', prefix)
        if marker:
            source_marker = re.search(r'\bauch\s*$', text[:a])
            if source_marker is None:
                raise ValueError('alias marker differs from source')
            ma = source_marker.start()
            aliases[parent] = (ma, a)
        elif parent in aliases:
            ma, previous_end = aliases[parent]
            if not LIST_CONNECTOR.fullmatch(text[previous_end:a]):
                aliases.pop(parent)
        if parent in aliases:
            ma, _ = aliases[parent]
            # Commas separate forms only inside the explicitly labelled list;
            # no punctuation/prose outside the source Tibetan field is consumed.
            for fa, fb in list_members(text, a, b):
                fa += len(text[fa:fb]) - len(text[fa:fb].lstrip())
                fb = fa + len(text[fa:fb].rstrip())
                if fa < fb:
                    add('alternate_headword', ma if fa == a and marker else fa, fb,
                        'explicit auch-governed heading list and Tibetan field',
                        form_span=dict(start=fa,end=fb,literal=text[fa:fb]),
                        marker_span=dict(start=ma,end=ma+4,literal=text[ma:ma+4]),
                        list_id=f"{projection['identity']}:alias-list:{ma}", source_locators=leaves)
            aliases[parent] = (ma, b)
        elif '/tib[' in path:
            labels = [f for f in preceding if GRAMMAR.fullmatch(f['source_text'].strip())]
            if labels and not re.search(r'[.;]',text[labels[-1]['visible_text_end']:a]):
                add('verb_form',a,b,'labelled Tibetan paradigm field within source heading',
                    label_span=dict(start=labels[-1]['visible_text_start'],end=labels[-1]['visible_text_end'],literal=labels[-1]['source_text']),source_locators=leaves)
    spans=[(r['start'],r['end']) for r in result]
    if len(set(spans)) != len(spans):
        raise ValueError('duplicate canonical header span')
    return result
