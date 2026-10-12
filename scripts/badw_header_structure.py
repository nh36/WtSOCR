"""Exact header fields from the source heading, never from definition proximity.

HTML heading ancestry comes from the observed lemma locator. Alias forms need
an explicit ``auch`` and a source <tib> field. Grammatical labels must be
complete source text leaves. Remaining heading prose stays reviewable.
PDF article text often starts after the printed heading; absent headings are
not reconstructed from a lemma string or lexical text.
"""
import hashlib
import re

VERSION = 'badw-header-structure-v1'
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
        elif re.search(r'/tib\[\d+\]/text\(\)', f['dom_path']):
            parent=f['dom_path'].split('/tib[')[0]
            preceding=[g for g in fragments[:i] if g['dom_path'].startswith(parent+'/')]
            # Only the immediate preceding nonblank leaf establishes an alias.
            previous=next((g for g in reversed(preceding) if g['source_text'].strip()),None)
            if previous and re.search(r'\bauch\s*$',previous['source_text']):
                ma=previous['visible_text_start']+previous['source_text'].rfind('auch')
                add('alternate_headword',ma,b,'explicit auch + Tibetan field in source heading',
                    form_span=dict(start=a,end=b,literal=text[a:b]),marker_span=dict(start=ma,end=ma+4,literal='auch'),source_locator=f)
            else:
                # A verb paradigm form needs an explicit label in its own heading group.
                labels=[g for g in preceding if GRAMMAR.fullmatch(g['source_text'].strip())]
                if labels and not re.search(r'[.;]',text[labels[-1]['visible_text_end']:a]):
                    add('verb_form',a,b,'labelled Tibetan paradigm field within source heading',
                        label_span=dict(start=labels[-1]['visible_text_start'],end=labels[-1]['visible_text_end'],literal=labels[-1]['source_text']),source_locator=f)
    spans=[(r['start'],r['end']) for r in result]
    if len(set(spans)) != len(spans):
        raise ValueError('duplicate canonical header span')
    return result
