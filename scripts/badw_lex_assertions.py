"""Recover independently delimited assertions inside damaged Lex. items.

A malformed earlier quote must not consume a later semicolon + typed form +
assertion + balanced terminal source enclosure. The original item and its
errors remain intact. No delimiter is repaired and no broad block owns cites.
"""
import re
from badw_source_components import lexical_clauses
from badw_bounded_passages import envelopes
from badw_pdf_mixed_clauses import style_runs


def lex_assertions(projection, text, items, assigned, object_):
    nodes = projection['nodes']
    runs = style_runs(projection, text)[1] if projection['source_kind']=='pdf' else []
    result = []
    for item in items:
        if not item['delimiter_diagnostics']:
            continue
        a, b = item['start'], item['end']
        cuts = [a] + [a+m.end() for m in re.finditer(';', text[a:b])] + [b]
        for left, right in zip(cuts[1:-1], cuts[2:]):
            end = right-1 if text[right-1:right]==';' else right
            start = left
            while start < end and text[start].isspace(): start += 1
            while end > start and text[end-1].isspace(): end -= 1
            if start >= end or lexical_clauses(text,start,end)[1]: continue
            initial = any(n['kind']=='tibetan' and n['start']==start and n['end']<=end for n in nodes)
            initial |= any(r['style']=='italic' and r['start']<=start<r['end'] for r in runs)
            if not initial: continue
            local = text[start:end]
            if not (re.search('[=≅≈„]',local) or re.search(r'\bni\b',local)): continue
            terminals = [(s,e) for s,e,o in envelopes(text[start:end]) if o=='('
                         and text[start+e:end].strip() in ('','.')] 
            if not terminals: continue
            s,e = max(terminals,key=lambda se:se[1]-se[0])
            x,y = start+s,start+e
            cites = [n for n in nodes if n['kind']=='citation' and n['id'] not in assigned
                     and x<=n['start']<n['end']<=y]
            if not cites: continue
            if any(n['kind']=='sense' and max(start,n['start'])<min(end,n['end'])
                   and not n['start']<=start<end<=n['end'] for n in nodes): continue
            result.append(object_('citable_passage',start,end,passage_type='lex_assertion',
                lex_item_id=item['id'], sense_node_id=item['sense_node_id'], ownership=item['ownership'],
                evidence='semicolon restart, observed initial lexical form, locally balanced assertion and terminal source enclosure',
                boundary_evidence=dict(left_semicolon=left-1, terminal_enclosure=dict(start=x,end=y),
                                       right_semicolon=right-1 if right!=b else None),
                citation_node_ids=[n['id'] for n in cites]))
            assigned.update(n['id'] for n in cites)
    return result
