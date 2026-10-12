"""Exact header fields from the source heading, never from definition proximity.

HTML heading ancestry comes from the observed lemma locator. Alias forms need
an explicit ``auch`` and a source <tib> field. Grammatical labels must be
complete source text leaves. Remaining heading prose stays reviewable.
PDF article text often starts after the printed heading; absent headings are
not reconstructed from a lemma string or lexical text.
"""
import hashlib
import re

VERSION = 'badw-header-structure-v2'
GRAMMAR = re.compile(r'(?:pf\.|präs\.|pr\.|fut\.|imp\.|imper\.|vb\.|v\. tr\.|v\. intr\.|trans\.|intrans\.|subst\.|adj\.|adv\.)', re.I)


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


def pdf_heading_fields(projection, text, add):
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
    marker = re.match(r'\s*(?:\d+\.\s*)?(Kurzf\.\s+für|pf\.\s+zu|fut\.\s+zu|imp\.\s+zu|imper\.\s+zu|auch)\s*[↑↓]?\s*', text)
    if not marker:
        return
    a = marker.end()
    first = next((i for i, (x, y, loc) in enumerate(styles) if x == a), None)
    if first is None:
        return
    b = styles[first][1]
    locations = [styles[first][2]]
    for x, y, loc in styles[first + 1:]:
        # Newline wrapping is accepted only across whitespace, never across
        # regular-font explanation, punctuation, another label or a sense.
        if not re.fullmatch(r'\s*', text[b:x]):
            break
        b = y
        locations.append(loc)
    while b > a and text[b - 1].isspace():
        b -= 1
    label = re.sub(r'\s+', ' ', marker.group(1))
    ma = marker.start(1)
    if label != 'auch':
        relation = {'Kurzf. für':'short_form_of', 'pf. zu':'perfect_of',
                    'fut. zu':'future_of', 'imp. zu':'imperative_of',
                    'imper. zu':'imperative_of'}[label]
        add('header_relation', ma, b, 'initial explicit connective and contiguous PDF italic target',
            relation_type=relation, direction='entry_to_target',
            target_span=dict(start=a,end=b,literal=text[a:b]),
            marker_span=dict(start=ma,end=a,literal=text[ma:a]), source_locators=locations)
    else:
        for form in re.finditer(r'[^,]+', text[a:b]):
            fa, fb = a + form.start(), a + form.end()
            fa += len(text[fa:fb]) - len(text[fa:fb].lstrip())
            fb = fa + len(text[fa:fb].rstrip())
            if fa < fb:
                add('alternate_headword', ma if fa == a else fa, fb,
                    'initial auch and contiguous PDF italic alias list',
                    form_span=dict(start=fa,end=fb,literal=text[fa:fb]),
                    marker_span=dict(start=ma,end=ma+4,literal=text[ma:ma+4]),
                    list_id=f"{projection['identity']}:alias-list:{ma}", source_locators=locations)


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
    relations = {'Kurzf. für': 'short_form_of', 'pf. zu': 'perfect_of',
                 'fut. zu': 'future_of', 'imp. zu': 'imperative_of',
                 'imper. zu': 'imperative_of'}
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
        relation = next((label for label in relations
                         if re.search(re.escape(label).replace(r'\ ', r'\s+') + r'\s*↑?\s*$', prefix)), None)
        if relation:
            # The connective and target are explicit heading fields. Preserve
            # lexical target separately from any future graph resolution.
            marker = re.search(re.escape(relation).replace(r'\ ', r'\s+') + r'\s*↑?\s*$', text[:a])
            if marker is None:
                raise ValueError('header relation source mismatch')
            ma = marker.start()
            add('header_relation', ma, b, 'explicit heading connective and source target field',
                relation_type=relations[relation], direction='entry_to_target',
                target_span=dict(start=a, end=b, literal=text[a:b]),
                marker_span=dict(start=ma, end=a, literal=text[ma:a]), source_locators=leaves)
            aliases.pop(parent, None)
            continue
        marker = re.search(r'\bauch\s*$', prefix)
        if marker:
            ma = preceding[0]['visible_text_start'] + marker.start()
            aliases[parent] = (ma, a)
        elif parent in aliases:
            ma, previous_end = aliases[parent]
            if not re.fullmatch(r'\s*,\s*', text[previous_end:a]):
                aliases.pop(parent)
        if parent in aliases and '/tib[' in path:
            ma, _ = aliases[parent]
            # Commas separate forms only inside the explicitly labelled list;
            # no punctuation/prose outside the source Tibetan field is consumed.
            for form in re.finditer(r'[^,]+', text[a:b]):
                fa, fb = a + form.start(), a + form.end()
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
