"""Punctuation-bounded scholarly assertions within accepted source scopes.

A definition opening or a recognized language/grammatical production supplies
its left boundary. Top-level sentence/semicolon punctuation supplies its end.
The terminal parenthesis validates supporting-source syntax only after those
boundaries exist. Source forms, language observations and definitions remain
separate, immutable leaves under the recovered assertion.
"""
import re
from badw_bounded_passages import PAIRS, envelopes
from badw_pdf_mixed_clauses import style_runs
from badw_assertion_layout import passage_layout

ABBREVIATIONS = {'Bez','Kurzf','skt','chin','tib','alttib','synon','npr','divin','phil','etw',
    'vgl','bzw','z','B','L','Dec','Nr','Anm','s','v','f','ff','ca','t','T','d','i'}
LANGUAGE = re.compile(r'(?:für\s+)?(?:skt|chin)\.|(?:in der\s+phil\.\s+Literatur\s+steht)\b')
GRAMMAR = re.compile(r'(?:a\s+topic\s+marker\s+similar\s+to\b|(?:eine?\s+)?(?:Partikel|Suffix)\s+(?:für|mit)\b)')


def clause_ends(text,a,b):
    """Independent punctuation; no citation nodes are consulted here."""
    stack=[]
    for i in range(a,b):
        c=text[i]
        if c in PAIRS.values(): stack.append(c)
        elif c in PAIRS:
            if not stack or stack.pop()!=PAIRS[c]: return
        elif not stack:
            if c==';': yield i+1
            elif c=='.':
                word=re.search(r'(\w+)$',text[a:i])
                if word and word[1] in ABBREVIATIONS: continue
                if i and i+1<b and text[i-1].isdigit() and text[i+1].isdigit(): continue
                # A numbered sense marker is not a sentence.
                if re.fullmatch(r'\s*\d+',text[a:i]): continue
                yield i+1
            elif c=='།': yield i+1


def source_assertions(projection,text,assigned,object_):
    if projection['source_kind']!='pdf': return []
    nodes=projection['nodes'];lines,runs=style_runs(projection,text);result=[]
    scopes=[n for n in nodes if n['kind'] in ('sense','source_division')]
    for scope in scopes:
        a,b=scope['start'],scope['end']
        cuts=[a]+list(clause_ends(text,a,b))
        for left,end in zip(cuts,cuts[1:]):
            start=left
            while start<end and text[start].isspace(): start+=1
            stop=end
            while stop>start and text[stop-1] in ' \n\t.;།': stop-=1
            if stop<=start: continue
            definitions=[n for n in nodes if n['kind']=='definition' and start<=n['start']<stop]
            opening=next((n for n in definitions if not text[start:n['start']].strip() or
                          re.fullmatch(r'\d+\.\s*',text[start:n['start']])),None)
            if opening: start=opening['start']
            prefix=text[start:stop]
            role='source_language_assertion' if LANGUAGE.match(prefix) else 'grammatical_assertion' if GRAMMAR.match(prefix) else 'definition_assertion' if opening else None
            if role is None: continue
            # Nested senses, examples, Lex. and xrefs establish competing scope.
            if any(n['kind'] in ('example','lexical','lexical_parallel','cross_reference') and n['start']<stop and start<n['end'] for n in nodes): continue
            if any(n['kind']=='sense' and n['start']<stop and start<n['end'] and not n['start']<=start<stop<=n['end'] for n in nodes): continue
            terminal=[(s,e) for s,e,o in envelopes(text[start:stop]) if o=='(' and e==stop-start]
            if not terminal: continue
            x,y=min(terminal);x+=start;y+=start
            cites=[n for n in nodes if n['kind']=='citation' and x<=n['start']<n['end']<=y]
            if not cites or any(n['id'] in assigned for n in cites): continue
            # Every citation in this assertion must belong to that source note.
            if any(n['kind']=='citation' and start<=n['start']<n['end']<=stop and n not in cites for n in nodes): continue
            layout=[r for r in runs if r['start']<stop and start<r['end']]
            physical=passage_layout(projection,layout)
            if physical is None: continue
            # An italic excerpt cannot be promoted to ordinary supported prose.
            # Initial definition text must be Roman; interior italic forms are
            # retained as language leaves, never interpreted as quotations.
            first=next((r for r in layout if r['start']<=start<r['end']),None)
            if not first or first['style']!='regular': continue
            if any(n['kind']=='translation' and n['start']<stop and start<n['end'] and
                   not any(d['start']<=n['start']<n['end']<=d['end'] for d in definitions) for n in nodes): continue
            sense=scope['id'] if scope['kind']=='sense' else None
            result.append(object_('citable_passage',start,end,passage_type='source_supported_assertion',
                assertion_role=role,containing_node_id=scope['id'],definition_node_ids=[d['id'] for d in definitions],
                sense_node_id=sense,ownership='sense' if sense else 'entry',
                evidence='accepted scope, definition opening or explicit language/grammar production, independent punctuation and replayed PDF geometry',
                boundary_evidence=dict(left_boundary=left,right_punctuation=end-1,terminal_enclosure=dict(start=x,end=y),derived_geometry=physical),
                citation_node_ids=[n['id'] for n in cites]))
            assigned.update(n['id'] for n in cites)
    return result
