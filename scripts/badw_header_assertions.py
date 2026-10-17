"""Individually delimited grammatical assertions in an observed HTML heading."""
import re
from badw_header_structure import heading_fragments
from badw_bounded_passages import PAIRS, envelopes

LABEL = r'(?:adnominal |adversative |conjunction |agency |role )*(?:particle|[A-ZÄÖÜ][a-zäöüß]*(?:partikel|suffix)|Suffix)'
GRAMMAR_LABEL = re.compile(LABEL + r'(?:\s+bzw\.\s+' + LABEL + r')?')


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
    # Separators within a quotation or parenthetical source never split it.
    stack, cuts = [], [a]
    for i in range(a,b):
        c = text[i]
        if c in PAIRS.values(): stack.append(c)
        elif c in PAIRS:
            if not stack or stack.pop() != PAIRS[c]: return []
        elif not stack and c in ',;': cuts.append(i+1)
    if stack: return []
    cuts.append(b)
    result = []
    for left,right in zip(cuts,cuts[1:]):
        start,end = left,right
        while start<end and text[start].isspace(): start+=1
        while start<end and text[end-1] in ' \n\t.,;': end-=1
        local=text[start:end]
        terminal=[(s,e) for s,e,o in envelopes(local) if o=='(' and e==len(local)]
        if not terminal: continue
        s,e=min(terminal)
        prefix=local[:s].strip()
        quoted=any(x==0 and y==len(prefix) and o=='„' for x,y,o in envelopes(prefix))
        if not quoted and not GRAMMAR_LABEL.fullmatch(prefix): continue
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
