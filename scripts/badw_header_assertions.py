"""Individually delimited grammatical assertions in an observed HTML heading."""
import re
from badw_header_structure import heading_fragments
from badw_bounded_passages import PAIRS, envelopes

LABEL = r'(?:adnominal |adversative |conjunction |agency |role )*(?:particle|[A-ZÄÖÜ][a-zäöüß]*(?:partikel|suffix)|Suffix)'
GRAMMAR_LABEL = re.compile(LABEL + r'(?:\s+bzw\.\s+' + LABEL + r')?')
DESCRIPTIONS = re.compile(
    r'(?:topicalizer|thématiseur|ergatif-instrumental|particule génitive-relative|'
    r'(?:Gradsuffix|Suffix), (?:bildet auch Indefinitpronomen und Konverben zum Ausdruck eines konzessiven Verhältnisses|das den Ergativ und Instrumental markiert)|'
    r'connecteur mit intensivierender, adversativer und additiver Funktion|'
    r'Partikel für den (?:engeren Lokativ, Lokativ I|Ablativ I)|Inessiv|Elativ|'
    r'Kollektiv- bzw\. Multiplikativpartikel bei Zahlwörtern|-(?:partikel|suffix))')


def heading_delimiters(text, a, b):
    """Balanced scholarly quotes, including English quotes inside German ones."""
    stack, enclosed, separators = [], [], []
    for i in range(a,b):
        c = text[i]
        if c == '‘' and stack and stack[-1][0] == '„':
            stack.append(('‘',i))
        elif c == '’' and stack and stack[-1][0] == '‘':
            _,start = stack.pop(); enclosed.append((start,i+1,'‘'))
        elif c in PAIRS.values(): stack.append((c,i))
        elif c in PAIRS:
            if not stack or stack[-1][0] != PAIRS[c]: return None
            opening,start = stack.pop(); enclosed.append((start,i+1,opening))
        elif not stack and c in ',;': separators.append(i)
    return None if stack else (enclosed,separators)


def grammatical_description(prefix):
    if GRAMMAR_LABEL.fullmatch(prefix) or DESCRIPTIONS.fullmatch(prefix): return True
    # A role label followed by its complete quoted definition is one assertion.
    return bool(re.fullmatch(r'bounded (?:locus|source) role particle, „.+“',prefix, re.S))


def header_assertions(projection, text, assigned, object_):
    fragments = heading_fragments(projection)
    if not fragments:
        return []
    # Only the descriptive sibling of the observed main lemma field.
    path = projection['original_structure']['lemma_field']['locator']['dom_path']
    root = re.fullmatch(r'(.*/div\[\d+\])/span\[1\]/span\[\d+\]', path)[1] + '/span[2]/'
    fragments = [f for f in fragments if f['dom_path'].startswith(root)]
    if not fragments:
        return []
    a = min(f['visible_text_start'] for f in fragments)
    b = max(f['visible_text_end'] for f in fragments)
    parsed = heading_delimiters(text,a,b)
    if parsed is None: return []
    enclosed,separators = parsed
    # Preserve the established comma/semicolon productions before attempting
    # longer coordinated phrases. Otherwise a newly recognized whole phrase
    # could replace the exact span of an already accepted quoted assertion.
    legacy_cuts = [a]+[i+1 for i in separators]+[b]
    candidates = [(x,y,True) for x,y in zip(legacy_cuts,legacy_cuts[1:])]
    semi = [a]+[i+1 for i in separators if text[i]==';']+[b]
    candidates.extend((x,y,False) for x,y in zip(semi,semi[1:]))
    cuts = [a]+[i+1 for i in separators]+[b]
    # A conjunction between complete assertions is an independent boundary.
    for m in re.finditer(r'\s+bzw\.\s+',text[a:b]):
        pos=a+m.start()
        if not any(x<=pos<y for x,y,_ in enclosed) and text[a:pos].rstrip().endswith(')'):
            cuts.extend((pos,a+m.end()))
    cuts=sorted(set(cuts))
    # Commas within a complete recognized label are internal grammar, while
    # other top-level commas separate assertions. Try whole finite phrases;
    # full matching below prevents a free-prose span from becoming an owner.
    candidates.extend((x,y,False) for x in cuts for y in cuts if x<y
                      and not any(x<z<y for z in semi[1:-1]))
    # A separately marked heading form can precede a grammatical label without
    # punctuation ("... bo Nominalsuffix"). Its observed DOM end is a boundary.
    for f in fragments:
        if any('/'+tag+'[' in f['dom_path'] for tag in ('i', 'em', 'tib')):
            x=f['visible_text_end']
            candidates.extend((x,y,False) for y in cuts if x<y
                              and not any(x<z<y for z in semi[1:-1]))
    result = []
    for left,right,legacy in candidates:
        start,end = left,right
        while start<end and text[start].isspace(): start+=1
        while start<end and text[end-1] in ' \n\t.,;': end-=1
        local=text[start:end]
        parsed_local=heading_delimiters(local,0,len(local))
        if parsed_local is None: continue
        terminal=[(s,e) for s,e,o in parsed_local[0] if o=='(' and e==len(local)]
        if not terminal: continue
        s,e=min(terminal)
        prefix=local[:s].strip()
        quoted=any(x==0 and y==len(prefix) and o=='„' for x,y,o in parsed_local[0])
        if not quoted and not (GRAMMAR_LABEL.fullmatch(prefix) if legacy else grammatical_description(prefix)): continue
        cites=[n for n in projection['nodes'] if n['kind']=='citation' and start+s<n['start']<n['end']<=start+e]
        if not cites or any(n['id'] in assigned for n in cites): continue
        if any(n['kind'] in ('sense','source_division','example','lexical') and n['start']<end and start<n['end'] for n in projection['nodes']): continue
        result.append(object_('citable_passage',start,end,passage_type='heading_grammatical_assertion',
            sense_node_id=None,ownership='entry',evidence='heading descriptive DOM sibling, complete grammatical label or quotation, terminal source enclosure',
            boundary_evidence=dict(dom_path=root,left_separator=left-1 if left>a else None,
                terminal_enclosure=dict(start=start+s,end=start+e),assertion_kind='quoted_description' if quoted else 'grammatical_label'),
            citation_node_ids=[n['id'] for n in cites]))
        assigned.update(n['id'] for n in cites)
    return result
