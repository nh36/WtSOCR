"""Explicit source comparison lists with independent punctuation boundaries.

Citation nodes establish leaves, never ends. A complete top-level sentence or
semicolon establishes the end; unparsed prose, competing structures, layout
jumps and malformed delimiters reject the whole production.
"""
import re
from badw_bounded_passages import PAIRS, envelopes
from badw_header_structure import contiguous_pdf_lines
from badw_pdf_mixed_clauses import style_runs

ABBREVIATIONS = {'vgl','f','ff','Nr','Anm','s','v','Bd','S','fig','p','vol'}


def comparison_end(text, start, limit):
    stack = []
    for i in range(start,limit):
        c=text[i]
        if c in PAIRS.values(): stack.append(c)
        elif c in PAIRS:
            if not stack or stack.pop()!=PAIRS[c]: return None
        elif not stack:
            if c==';': return i+1
            if c in '↑↓→⇒།': return None
            if c=='.':
                token=re.search(r'(\w+)$',text[start:i])
                decimal=i>start and text[i-1].isdigit() and i+1<limit and text[i+1].isdigit()
                if decimal: continue
                if token and token[1] in ABBREVIATIONS:
                    if token[1] in ('f','ff') and (i+1==limit or re.match(r'\s*(?:།|$)',text[i+1:limit])):
                        return i+1
                    continue
                return i+1
    return None


def comparison_clauses(projection,text,assigned,object_):
    # HTML heading comparison lists need DOM assertion segmentation first.
    if projection['source_kind']!='pdf': return []
    nodes=projection['nodes'];result=[]
    lines,runs=style_runs(projection,text)
    bounded=envelopes(text)
    for m in re.finditer(r'\bvgl\.\s+',text):
        start=m.start()
        if any(s<start<e for s,e,_ in bounded): continue
        containers=[n for n in nodes if n['kind'] in ('sense','source_division') and n['start']<=start<n['end']]
        if not containers: continue
        container=min(containers,key=lambda n:n['end']-n['start'])
        end=comparison_end(text,start,container['end'])
        if end is None: continue
        if any(n['kind'] in ('example','lexical','lexical_parallel','cross_reference')
               and n['start']<end and start<n['end'] for n in nodes): continue
        if any(n['kind']=='sense' and n['start']<end and start<n['end']
               and not n['start']<=start<end<=n['end'] for n in nodes): continue
        layout=[r for r in runs if r['start']<end and start<r['end']]
        if not layout or any(not contiguous_pdf_lines(lines,l['line'],r['line']) for l,r in zip(layout,layout[1:])): continue
        cites=[n for n in nodes if n['kind']=='citation' and start<=n['start']<n['end']<=end]
        if not cites or any(n['id'] in assigned for n in cites): continue
        # Parse all material outside observed citation leaves. Locator suffixes
        # and s.v. headwords are bibliographical syntax, additional prose is not.
        remaining=text[start:end]
        for n in sorted(cites,key=lambda n:n['start'],reverse=True):
            remaining=remaining[:n['start']-start]+' '+remaining[n['end']-start:]
        remaining=re.sub(r'\bvgl\.',' ',remaining)
        remaining=re.sub(r'\bs\.\s*v\.\s+[^\s,;().]+',' ',remaining)
        remaining=re.sub(r'\b(?:f|ff|Nr|Anm|Bd|S|fig|p|vol)\.', ' ',remaining)
        if re.sub(r'[\s\d.,;:()\[\]/–-]|\bund\b','',remaining): continue
        senses=[n for n in containers if n['kind']=='sense' and end<=n['end']]
        sense=min(senses,key=lambda n:n['end']-n['start'])['id'] if senses else None
        result.append(object_('citable_passage',start,end,passage_type='punctuated_comparison_list',
            containing_node_id=container['id'],sense_node_id=sense,ownership='sense' if sense else 'entry',
            evidence='explicit vgl., complete reference-list grammar, independent top-level punctuation and continuous PDF layout',
            boundary_evidence=dict(marker='vgl.',terminal=text[end-1],typography=layout),
            citation_node_ids=[n['id'] for n in cites]))
        assigned.update(n['id'] for n in cites)
    return result
