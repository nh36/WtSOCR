"""Positive PDF typography productions, separate from opening-gloss recovery.

An italic run is not intrinsically a lexical expression. The first production
requires the printed semicolon + tilde construction as well as a Roman gloss.
The second requires an unfinished German syntactic connective at a physical
line boundary. Both retain the observations and add only uncovered fragments.
"""
import copy
import hashlib
import re
from badw_header_structure import contiguous_pdf_lines

VERSION = 'pdf-mixed-clause-v1'
STOP = re.compile(r';|[↑↓།„“]|\b(?:Lex\.|vgl\.|s\.\s*v\.|pf\.|fut\.|imp\.)|\n\s*\d+\.')
UNFINISHED = re.compile(r'(?:\b(?:und|oder|bzw\.|von|für|mit|als|bei|des|der|die|das|einer|eines|eine|einen)|,)\s*$')


def style_runs(projection, text):
    lines = (projection.get('original_structure') or {}).get('visual_lines', [])
    spans, offset = [], 0
    for i, line in enumerate(lines):
        if text[offset:offset+len(line['text'])] != line['text']:
            raise ValueError('Mixed-clause source line differs from immutable text')
        for s in line.get('style_spans', []):
            spans.append(dict(start=offset+s['start'], end=offset+s['end'],
                              style=s.get('style'), line=i, observation=s))
        offset += len(line['text'])+1
    return lines, spans


def roman_envelope(text, lines, spans, index):
    """A single continuous Roman layout run; transitions are hard boundaries."""
    first = spans[index]
    a, b = first['start'], first['end']
    evidence = [first]
    for s in spans[index+1:]:
        if s['style'] != 'regular' or not re.fullmatch(r'\s*', text[b:s['start']]):
            break
        if s['observation'].get('font') != first['observation'].get('font'):
            break
        if not contiguous_pdf_lines(lines, evidence[-1]['line'], s['line']):
            break
        if re.match(r'\s*\d+\.', text[s['start']:s['end']]):
            break
        b = s['end']; evidence.append(s)
    stop = STOP.search(text[a:b])
    if stop: b = a+stop.start()
    while a < b and text[a].isspace(): a += 1
    while b > a and text[b-1].isspace(): b -= 1
    return a, b, evidence


def add_fragment(result, text, a, b, role, evidence, continuation=()):
    if re.fullmatch(r'(?:synon\.|skt\.|chin\.|t\.\s*t\.|dass\.)', text[a:b].strip()):
        return
    if text[a:b].rstrip().endswith((',', '-', ':')):
        return
    if re.search(r'\b(?:ein|eine|einen|einem|einer|eines|der|die|das|und|oder|von|für|mit)\s*$', text[a:b]):
        return
    if b <= a or not any(c.isalpha() for c in text[a:b]) or b-a > 500:
        return
    # A passage already typed as an example, language form, citation or Lex.
    # item cannot be reinterpreted as a definition by this production.
    if any(n['kind'] not in ('definition','sense','source_division')
           and n['start'] < b and a < n['end'] for n in result['nodes']):
        return
    parents = [n for n in result['nodes'] if n['kind'] in ('sense','source_division')
               and n['start'] <= a < b <= n['end']]
    if not parents: return
    parent = min(parents, key=lambda n:(n['end']-n['start'], n['id']))['id']
    occupied = sorted((max(a,n['start']),min(b,n['end'])) for n in result['nodes']
                      if n['kind']=='definition' and n['start']<b and a<n['end'])
    cursor=a; gaps=[]
    for x,y in occupied:
        if cursor<x: gaps.append((cursor,x))
        cursor=max(cursor,y)
    if cursor<b: gaps.append((cursor,b))
    for x,y in gaps:
        while x<y and text[x].isspace(): x+=1
        while y>x and text[y-1].isspace(): y-=1
        if not any(c.isalpha() for c in text[x:y]): continue
        key=f"{result['identity']}:{VERSION}:{role}:{x}:{y}"
        result['nodes'].append(dict(id='recovered-definition:'+hashlib.sha256(key.encode()).hexdigest(),
            kind='definition',start=x,end=y,parent=parent,
            source_evidence=dict(rule=VERSION,**evidence),
            structural_recovery=dict(rule=VERSION,role=role,continuation_of=list(continuation),
                envelope=dict(start=a,end=b,literal=text[a:b]))))


def recover_mixed_clauses(projection, text):
    if projection['source_kind'] != 'pdf': return projection
    lines, spans = style_runs(projection,text)
    result=copy.deepcopy(projection)
    for i,s in enumerate(spans):
        if s['style']!='regular' or not i: continue
        left=spans[i-1]
        if left['style']!='italic': continue
        form_start=left['start']; first_line=left['line']
        for earlier in reversed(spans[:i-1]):
            if earlier['style']!='italic' or not re.fullmatch(r'\s*',text[earlier['end']:form_start]): break
            if not contiguous_pdf_lines(lines,earlier['line'],first_line): break
            form_start=earlier['start']; first_line=earlier['line']
        form=text[form_start:left['end']]
        prefix=text[:form_start].rstrip()
        # Tilde marks a lexical substitution, unlike an ordinary italic example.
        if not prefix.endswith(';') or not re.match(r'\s*~\s*\S',form): continue
        if any(c in form for c in '„“↑↓') or 'UNKNOWN' in form: continue
        if not contiguous_pdf_lines(lines,left['line'],s['line']): continue
        if text[left['end']:s['start']].strip(): continue
        a,b,ev=roman_envelope(text,lines,spans,i)
        if not re.match(r'[A-Za-zÄÖÜäöüß]',text[a:b]): continue
        add_fragment(result,text,a,b,'semicolon_lexical_form_gloss',
            dict(form_span=dict(start=form_start,end=left['end'],literal=form),
                 typography=ev,delimiter_span=dict(start=len(prefix)-1,end=len(prefix))))
    for node in list(result['nodes']):
        if node['kind']!='definition': continue
        end=node['end']; literal=text[node['start']:end]
        if not UNFINISHED.search(literal) or any(c in literal for c in '„“'): continue
        if not re.search(r'\b(?:und|oder|von|für|mit|als|bei|des|der|die|das|einer|eines|eine|einen)\s*$', literal): continue
        left=next((s for s in spans if s['end']==end and s['style']=='regular'),None)
        if not left: continue
        right=next(((i,s) for i,s in enumerate(spans) if s['start']>end),None)
        if not right: continue
        i,s=right
        if s['style']!='regular' or text[end:s['start']]!='\n': continue
        if not contiguous_pdf_lines(lines,left['line'],s['line']): continue
        font = left['observation'].get('font')
        if not font or font != s['observation'].get('font'): continue
        a,b,ev=roman_envelope(text,lines,spans,i)
        # A lowercase continuation is necessary but not sufficient: the left
        # connective, matching Roman font run and geometry are also required.
        if not re.match(r'[a-zäöüß]',text[a:b]): continue
        if not re.search(r'[.!?]$',text[a:b]): continue
        add_fragment(result,text,a,b,'unfinished_Roman_clause_continuation',
            dict(connective_span=dict(start=node['start'],end=end,literal=literal),
                 physical_lines=[left['line'],s['line']],typography=ev),[node['id']])
    return result
