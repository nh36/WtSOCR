"""Derived PDF reference expressions over immutable small-cap observation runs.

This layer consumes an independently bounded comparison, never supplies its end.
An observed citation leaf anchors a complete author/year expression. Unobserved
prefixes must be split capital initials (or a hyphenated small-cap continuation),
not arbitrary capitalized prose. Exact replay geometry validates every join.
"""
import re
from badw_assertion_layout import passage_layout

# WTS small capitals may put each capital initial on its own observation line.
AUTHOR = r'[A-ZÄÖÜ][A-ZÄÖÜÉÈÁÀÇẞ-]*(?:[ \n]+[A-ZÄÖÜÉÈÁÀÇẞ-]+)*(?:/[ \n]*[A-ZÄÖÜ][A-ZÄÖÜÉÈÁÀÇẞ-]*(?:[ \n]+[A-ZÄÖÜÉÈÁÀÇẞ-]+)*)?'
REFERENCE = re.compile(r'(?<![\w])' + AUTHOR + r'\s+\d{4}[a-z]?(?!\d)')


def compose_reference_runs(projection, text, start, end, citations, runs):
    result=[]
    for match in REFERENCE.finditer(text,start,end):
        a,b=match.span()
        leaves=[n for n in citations if a<=n['start']<b and n['end']>=b]
        if len(leaves)!=1: continue
        leaf=leaves[0]
        if a==leaf['start']: continue
        prefix=text[a:leaf['start']]
        # Each incomplete author component ends in a genuinely split initial or
        # hyphen. Ordinary whole uppercase words cannot be silently prefixed.
        if not re.fullmatch(r'(?:[A-ZÄÖÜ]\s*\n\s*[A-ZÄÖÜÉÈÁÀÇẞ-]*/?\s*)*[A-ZÄÖÜ]\s*\n\s*|[A-ZÄÖÜ]\s*\n\s*[A-ZÄÖÜÉÈÁÀÇẞ/-]+-\s*\n\s*',prefix):
            continue
        spans=[r for r in runs if r['start']<b and a<r['end']]
        physical=passage_layout(projection,spans)
        if physical is None: continue
        if any(n['kind'] in ('sense','example','lexical','lexical_parallel','cross_reference')
               and n['start']<b and a<n['end'] and not n['start']<=a<b<=n['end']
               for n in projection['nodes']): continue
        result.append(dict(start=a,end=leaf['end'],citation_node_id=leaf['id'],
            literal=text[a:leaf['end']],normalized_label=re.sub(r'\s*\n\s*','',re.sub(r'-\s*\n\s*','',text[a:b])),
            production='split_small_cap_author_year',typography=spans,derived_geometry=physical))
    return result


def compose_reference_locators(projection, text, start, end, runs):
    """A multiword s.v. headword ends at an observed italic/Roman transition.

    The font change supplies the form's envelope; no last-citation heuristic or
    unrestricted prose after s.v. is accepted. Ordinary one-word locators remain
    handled by the established reference grammar.
    """
    result=[]
    for match in re.finditer(r'\bs\.\s*v\.\s+',text[start:end]):
        a=start+match.start();form_start=start+match.end()
        current=form_start
        selected=[]
        for run in runs:
            if run['end']<=current: continue
            if run['start']>current and text[current:run['start']].strip(): break
            if run['style']!='italic': break
            selected.append(run);current=run['end']
        form=text[form_start:current]
        if not selected or not re.fullmatch(r"[\w’' -]+(?:\n[\w’' -]+)*",form): continue
        if not text[current:end] or not re.match(r'\s*[.,;)]',text[current:end]): continue
        physical=passage_layout(projection,selected)
        if physical is None: continue
        result.append(dict(start=a,end=current,form_span=dict(start=form_start,end=current),
                           production='italic_s_v_headword',typography=selected,derived_geometry=physical))
    return result
