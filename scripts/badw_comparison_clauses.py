"""Explicit source comparison lists with independent punctuation boundaries.

Citation nodes establish leaves, never ends. A complete top-level sentence or
semicolon establishes the end; unparsed prose, competing structures, layout
jumps and malformed delimiters reject the whole production.
"""
import re
from badw_bounded_passages import PAIRS, envelopes
from badw_header_structure import contiguous_pdf_lines
from badw_pdf_mixed_clauses import style_runs
from badw_assertion_layout import passage_layout
from badw_reference_runs import compose_reference_runs, compose_reference_locators
from badw_header_structure import heading_fragments

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
    nodes=projection['nodes'];result=[]
    pdf=projection['source_kind']=='pdf'
    lines,runs=style_runs(projection,text) if pdf else ([],[])
    headings=[]
    if not pdf:
        path=projection.get('original_structure',{}).get('lemma_field',{}).get('locator',{}).get('dom_path','')
        match=re.fullmatch(r'(.*/div\[\d+\])/span\[1\]/span\[\d+\]',path)
        if not match: return []
        root=match[1]+'/span[2]/'
        fragments=[f for f in heading_fragments(projection) if f['dom_path'].startswith(root)]
        if not fragments: return []
        headings=[dict(id=None,kind='heading',start=min(f['visible_text_start'] for f in fragments),
                       end=max(f['visible_text_end'] for f in fragments),dom_path=root)]
    bounded=envelopes(text)
    for m in re.finditer(r'\bvgl\.\s+',text):
        start=m.start()
        if any(s<start<e for s,e,_ in bounded): continue
        containers=[n for n in nodes+headings if n['kind'] in ('sense','source_division','heading') and n['start']<=start<n['end']]
        if not containers: continue
        container=min(containers,key=lambda n:n['end']-n['start'])
        end=comparison_end(text,start,container['end'])
        if end is None: continue
        if any(n['kind'] in ('example','lexical','lexical_parallel','cross_reference')
               and n['start']<end and start<n['end'] for n in nodes): continue
        if any(n['kind']=='sense' and n['start']<end and start<n['end']
               and not n['start']<=start<end<=n['end'] for n in nodes): continue
        layout=[r for r in runs if r['start']<end and start<r['end']]
        if pdf and not layout: continue
        physical = None
        if pdf and any(not contiguous_pdf_lines(lines,l['line'],r['line']) for l,r in zip(layout,layout[1:])):
            physical = passage_layout(projection, layout)
            if physical is None: continue
        cites=[n for n in nodes if n['kind']=='citation' and start<=n['start']<n['end']<=end]
        if not cites or any(n['id'] in assigned for n in cites): continue
        # Parse all material outside observed citation leaves. Locator suffixes
        # and s.v. headwords are bibliographical syntax, additional prose is not.
        composed=compose_reference_runs(projection,text,start,end,cites,runs)
        leaves=[dict(start=n['start'],end=n['end']) for n in cites]
        for expression in composed:
            leaf=next(n for n in cites if n['id']==expression['citation_node_id'])
            leaves.remove(dict(start=leaf['start'],end=leaf['end']))
            leaves.append(dict(start=expression['start'],end=expression['end']))
        locators=compose_reference_locators(projection,text,start,end,runs)
        leaves.extend(dict(start=n['start'],end=n['end']) for n in locators)
        # Locators can already lie inside an observed citation. Merge coverage
        # before masking so nested structural objects never shift offsets twice.
        coverage=[]
        for leaf in sorted(leaves,key=lambda n:n['start']):
            if coverage and leaf['start']<=coverage[-1]['end']:
                coverage[-1]['end']=max(coverage[-1]['end'],leaf['end'])
            else: coverage.append(dict(leaf))
        remaining=text[start:end]
        for n in reversed(coverage):
            remaining=remaining[:n['start']-start]+' '+remaining[n['end']-start:]
        remaining=re.sub(r'\bvgl\.',' ',remaining)
        remaining=re.sub(r'\bs\.\s*v\.\s+[^\s,;().]+',' ',remaining)
        remaining=re.sub(r'\b(?:f|ff|Nr|Anm|Bd|S|fig|p|vol)\.', ' ',remaining)
        # Roman front-matter pagination is a locator, not an author label.
        remaining=re.sub(r'(?<=:)\s*[IVXLCDM]+(?=[.,;\s]|$)', ' ',remaining)
        if re.sub(r'[\s\d.,;:()\[\]/–-]|\bund\b','',remaining): continue
        senses=[n for n in containers if n['kind']=='sense' and end<=n['end']]
        sense=min(senses,key=lambda n:n['end']-n['start'])['id'] if senses else None
        result.append(object_('citable_passage',start,end,passage_type='punctuated_comparison_list',
            containing_node_id=container['id'],sense_node_id=sense,ownership='sense' if sense else 'entry',
            evidence='explicit vgl., complete reference-list grammar, independent top-level punctuation and continuous PDF layout',
            boundary_evidence=dict(marker='vgl.',terminal=text[end-1],typography=layout,derived_geometry=physical,reference_expressions=composed,reference_locators=locators,dom_path=container.get('dom_path')),
            citation_node_ids=[n['id'] for n in cites]))
        assigned.update(n['id'] for n in cites)
    return result
