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
LANGUAGE = re.compile(r'(?:auch\s+)?(?:für\s+)?(?:skt|chin)\.|(?:in der\s+phil\.\s+Literatur\s+steht)\b')
GRAMMAR = re.compile(r'(?:a\s+topic\s+marker\s+similar\s+to\b|(?:eine?\s+)?(?:Partikel|Suffix)\s+(?:für|mit)\b)')

# Finite editorial constructions. These classify a punctuation-bounded clause;
# they never determine its extent from the position of its supporting source.
EDITORIAL = re.compile(
    r'(?:Kurzf\.\s+für\b|synon\.\s+|wird\s+dem\s+Element\s+\w+\s+zugeordnet\b|'
    r'auch\s+[^„“();]+?\s+(?:Bez\.\s+für|eine\s+Gruppe)\b|'
    r'[^„“();]+?\s+wird\s+auch\s+als\s+[^„“();]+?\s+angesehen\b|'
    r'ein\s+Gewand,\s+das\s+[^„“();]+?\s+getragen\s+wird\b)')
SUBLABEL = re.compile(r'(?:Indefinitpartikel|Indefinitsuffix|selector|Koordinationspartikel|coordinative conjunction)')


def comma_subclauses(text,a,b):
    """Balanced top-level comma boundaries, independent of source-note leaves."""
    stack=[];cuts=[a]
    for i in range(a,b):
        c=text[i]
        if c in PAIRS.values(): stack.append(c)
        elif c in PAIRS:
            if not stack or stack.pop()!=PAIRS[c]: return []
        elif not stack and c==',': cuts.append(i+1)
    return list(zip(cuts,cuts[1:]+[b])) if not stack else []


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
        clauses=list(zip(cuts,cuts[1:]))
        # Try the original sentence productions first to preserve accepted spans.
        clauses += [pair for x,y in zip(cuts,cuts[1:]) for pair in comma_subclauses(text,x,y)]
        for left,end in clauses:
            start=left
            while start<end and text[start].isspace(): start+=1
            stop=end
            while stop>start and text[stop-1] in ' \n\t.,;།': stop-=1
            if stop<=start: continue
            definitions=[n for n in nodes if n['kind']=='definition' and start<=n['start']<stop]
            opening=next((n for n in definitions if not text[start:n['start']].strip() or
                          re.fullmatch(r'\d+\.\s*',text[start:n['start']])),None)
            if opening is None:
                # An already accepted definition after a wholly italic form has
                # its own canonical beginning; the form stays outside the new
                # assertion. Never extend that definition to cover the note.
                for d in definitions:
                    lead=[r for r in runs if r['start']<d['start'] and start<r['end']
                          and text[max(start,r['start']):min(d['start'],r['end'])].strip()]
                    if lead and all(r['style']=='italic' for r in lead):
                        opening=d;break
            if opening: start=opening['start']
            prefix=text[start:stop]
            role='source_language_assertion' if LANGUAGE.match(prefix) else 'grammatical_assertion' if GRAMMAR.match(prefix) else 'editorial_assertion' if EDITORIAL.match(prefix) else 'grammatical_label_assertion' if SUBLABEL.match(prefix) else 'definition_assertion' if opening else None
            if role is None: continue
            # Nested senses, examples, Lex. and xrefs establish competing scope.
            if any(n['kind'] in ('example','lexical','lexical_parallel') and n['start']<stop and start<n['end'] for n in nodes): continue
            nested_refs=[n for n in nodes if n['kind']=='cross_reference' and n['start']<stop and start<n['end']]
            if nested_refs:
                # Three explicit relational productions embed a lexical operand
                # inside a canonical definition continuation. The arrow remains
                # an independent child, never a comparison or source note.
                if not opening or len(nested_refs)!=1: continue
                ref=nested_refs[0]
                lead=text[start:ref['start']]
                if not start<=ref['start']<ref['end']<=stop: continue
                if not re.search(r'(?:gehört\s+zu\s+den|aus\s+der\s+Gruppe\s+der|sind\s+\d+)\s*$',lead): continue
                if 'vgl.' in lead or any(c in prefix for c in '„“'): continue
            if any(n['kind']=='sense' and n['start']<stop and start<n['end'] and not n['start']<=start<stop<=n['end'] for n in nodes): continue
            terminal=[(s,e) for s,e,o in envelopes(text[start:stop]) if o=='(' and e==stop-start]
            if not terminal: continue
            x,y=min(terminal)
            if role=='grammatical_label_assertion' and not SUBLABEL.fullmatch(text[start:start+x].strip()): continue
            x+=start;y+=start
            if any(n['end']>x for n in nested_refs): continue
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
            if not first or (first['style']!='regular' and role!='editorial_assertion'): continue
            if any(n['kind']=='translation' and n['start']<stop and start<n['end'] and
                   not any(d['start']<=n['start']<n['end']<=d['end'] for d in definitions) for n in nodes): continue
            sense=scope['id'] if scope['kind']=='sense' else None
            result.append(object_('citable_passage',start,end,passage_type='source_supported_assertion',
                assertion_role=role,containing_node_id=scope['id'],definition_node_ids=[d['id'] for d in definitions],
                nested_reference_node_ids=[n['id'] for n in nested_refs],
                sense_node_id=sense,ownership='sense' if sense else 'entry',
                evidence='accepted scope, canonical definition opening or finite language/grammatical/editorial production, independent clause punctuation and replayed PDF geometry',
                boundary_evidence=dict(left_boundary=left,right_punctuation=end-1,terminal_enclosure=dict(start=x,end=y),derived_geometry=physical),
                citation_node_ids=[n['id'] for n in cites]))
            assigned.update(n['id'] for n in cites)
    return result
