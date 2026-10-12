"""Exact contextual language and inline citation derivation.

Source nodes are observations, never rewritten. Registered bibliography names
are a grammar vocabulary, not evidence of passage ownership. Numeric text alone
is never a citation. Every derived span retains the original Unicode offsets.
"""
import copy
import hashlib
import re
from pathlib import Path
import json
from functools import lru_cache

@lru_cache(maxsize=1)
def glyph_reviews():
    return [json.loads(line) for line in (Path(__file__).resolve().parents[1] / "data/badw_language_glyph_reviews.jsonl").read_text().splitlines()]

VERSION = 'badw-contextual-semantics-v2'
WORD = r"[^\W\d_]+(?:[-’'][^\W\d_]+)*"
NON_FORMS = {'Optativ', 'Imperativ', 'Futur', 'Passiv', 'Text', 'Original',
             'Feronia', 'Ausdruck', 'Form', 'Wort', 'Skt', 'skt'}


def typography(projection, text):
    """Map preserved DOM Sanskrit fields / printed italic runs to source text."""
    structure = projection.get('original_structure') or {}
    spans = []
    if projection['source_kind'] == 'html':
        for f in structure.get('text_fragments', []):
            if '/skt[' in f.get('dom_path', '') and f.get('visible'):
                a, b = f.get('visible_text_start'), f.get('visible_text_end')
                if a is not None and b is not None and a < b:
                    spans.append((a, b, 'explicit DOM skt field'))
    else:
        offset = 0
        for line in structure.get('visual_lines', []):
            value = line['text']
            if text[offset:offset+len(value)] != value:
                raise ValueError('visual line mapping differs from source')
            for s in line.get('style_spans', []):
                if s.get('style') == 'italic':
                    spans.append((offset+s['start'], offset+s['end'], 'printed italic run'))
            offset += len(value)+1
    return spans


def language_forms(projection, text):
    forms = {}
    def add(a, b, evidence, marker=None):
        while a < b and text[a].isspace(): a += 1
        while b > a and (text[b-1].isspace() or text[b-1] in '.,;'): b -= 1
        if a == b: return
        forms.setdefault((a, b), dict(start=a, end=b, literal=text[a:b],
            language='sa', evidence=evidence, marker_span=marker))
    styles = typography(projection, text)
    # Explicit DOM language is stronger than enclosing Tibetan observations.
    for a, b, evidence in styles:
        if evidence == 'explicit DOM skt field': add(a, b, evidence)
    classifications = []
    reviewed = []
    for review in glyph_reviews():
        if review["identity"] != projection.get("identity"): continue
        a,b=review["start"],review["end"]
        if review["text_sha256"] != projection["review_text_sha256"] or text[a:b] != review["literal"]:
            raise ValueError("reviewed language glyph source contract changed")
        reviewed.append(review)
    for m in re.finditer(r'\bskt\.', text):
        a = m.end()
        prefix = re.match(r'\s*[\]*]*\s*(?:(?:abw\.|Wurzel)\s*)?', text[a:])
        a += prefix.end()
        match = re.match(r'-?(?:\['+WORD+r'\])?'+WORD, text[a:])
        family = 'unresolved_source_syntax'
        if a < len(text) and text[a].isdigit(): family = 'Sanskrit_edition_locator_not_language_form'
        elif match and match.group() in NON_FORMS: family = 'German_metalinguistic_or_botanical_prose'
        elif match:
            b = a+match.end()
            # Typography bounds multiword forms, never German continuation.
            runs = [(x,y,e) for x,y,e in styles if x <= a < y]
            if runs:
                _, y, _ = min(runs, key=lambda s:s[1]-s[0])
                if not re.search(r'[;„“(),:=⟦]', text[a:y]): b = y
            if '⟦' in text[a:b+1]: family = 'source_decoding_corruption'
            else:
                add(a,b,'explicit skt. label with bounded form',[m.start(),m.end()])
                family = 'explicit_skt_bounded_form'
                # Parallel alternatives require explicit connective and form
                # typography; an unstyled German noun cannot be promoted.
                tail = b
                for _ in range(5):
                    alt = re.match(r'\s*(?:/|oder|bzw\.|auch)\s*',text[tail:])
                    if not alt: break
                    x=tail+alt.end()
                    candidates=[s for s in styles if s[0]<=x<s[1]]
                    if not candidates: break
                    y=min(candidates,key=lambda s:s[1]-s[0])[1]
                    if re.search(r'[;„“(),:=⟦]',text[x:y]): break
                    add(x,y,'explicit skt. parallel form',[m.start(),m.end()]);tail=y
        exact=[r for r in reviewed if m.end() <= r['start'] <= m.end()+2]
        if exact:
            r=exact[0];add(r['start'],r['end'],'explicit skt. label and facsimile-reviewed decoding',[m.start(),m.end()])
            forms[(r['start'],r['end'])].update(reviewed_reading=r['reviewed_reading'],decoding_review=r)
            family='explicit_skt_facsimile_reviewed_form'
        classifications.append(dict(start=m.start(),end=m.end(),family=family))
    if projection['source_kind']=='pdf':
        # Mvy is evidence of a Sanskrit correspondence only in a bounded
        # lexical construction, never a language label for every nearby word.
        for block in projection.get('original_structure',{}).get('candidates',{}).get('lexical_blocks',[]):
            for clause in block.get('clauses',[]):
                x,y=clause['start'],clause['end']; value=text[x:y]
                source=re.search(r'\((?:Mvy|Ak)\s*\d',value)
                if not source:continue
                eq=list(re.finditer('[=≅≈]',value[:source.start()]))
                lower=x+eq[-1].end() if eq else x
                for a,b,_ in styles:
                    if not lower<=a<b<=x+source.start():continue
                    before=text[lower:a].strip();after=text[b:x+source.start()].strip()
                    if before:continue
                    # Singleton Sanskrit lemma immediately followed by Mvy,
                    # or an equivalence followed by an explicitly quoted gloss.
                    if not after or (eq and after.startswith('„') and after.endswith('“')):
                        add(a,b,'printed italic lexical-source lemma / equivalence with bounded gloss')
        # Example correspondences may sit outside Lex. blocks. Require an
        # equivalence, a quoted German gloss and Mvy in the same local clause.
        for m in re.finditer(r'[≅≈=]\s*',text):
            candidates=[s for s in styles if s[0]==m.end()]
            if not candidates:continue
            a,b,_=candidates[0]
            tail=text[b:b+300]
            if re.match(r'\s*„[^„“]*“\s*\(Mvy\s*\d',tail):
                add(a,b,'printed equivalence, italic form, quoted gloss and Mvy')
    return list(forms.values()), classifications


def inline_vocabulary(resolver, source_kind):
    """Compile a pinned resolver vocabulary once per manifestation."""
    cache=getattr(resolver,'_contextual_inline_vocabulary',None)
    if cache is None:
        cache={};resolver._contextual_inline_vocabulary=cache
    if source_kind in cache:return cache[source_kind]
    patterns=[(key,pattern,'registered author-year') for key,_,pattern in resolver.publication_patterns]
    patterns += [(label,pattern,'registered source and locator') for label,pattern in resolver.resolver.patterns]
    patterns += [(r['alias'], p, 'reviewed publication occurrence alias' if
                  getattr(resolver,'by_id',{}).get(r['authority_id'],{}).get('kind')=='publication'
                  else 'reviewed source alias and locator')
                 for r,p in getattr(resolver,'alias_patterns',[]) if r['layer']==source_kind]
    # Registered author syntax may cite an unregistered year/edition. Extraction
    # records it literally; the existing resolver must leave identity uncertain.
    from badw_bibliography import spelling_pattern, YEAR_PATTERN
    authors=set()
    for key,_,_ in resolver.publication_patterns:
        split=re.fullmatch(r'(.+?) ('+YEAR_PATTERN+r')',key)
        if split: authors.add(split[1])
    for author in sorted(authors):
        for spelling in {author,author.upper()}:
            pat=spelling_pattern(spelling).replace(re.escape(' '),r'\s+')
            patterns.append((author,re.compile(r'(?<!\w)'+pat+r'\s+(?:'+YEAR_PATTERN+r')(?![\w–-])'),'registered author, literal edition year'))
    cache[source_kind]=patterns
    return patterns


def inline_candidates(projection, text, resolver):
    """Registered source + locator, or registered author/year, in local syntax.

    Already observed citation envelopes take precedence. Overlapping candidates
    are not silently combined. Bibliographic equivalence is resolved elsewhere.
    """
    existing=[n for n in projection['nodes'] if n['kind']=='citation']
    candidates=[]
    locator=re.compile(r'\s*(?:(?:[.:]|Anm\.)\s*)?(?:[IVX]+\s+)?\d+[a-zA-Z]?(?:[.,:/–-]\s*\d+[a-zA-Z]?)*')
    patterns=inline_vocabulary(resolver,projection['source_kind'])
    for label, pattern, evidence in patterns:
        for m in pattern.finditer(text):
            a,b=m.span()
            if evidence in ('registered source and locator','reviewed source alias and locator'):
                loc=locator.match(text,b)
                if not loc: continue
                b=loc.end()
            else:
                loc=re.match(r'\s*:\s*(?:(?:vol\.\s*\d+,\s*)?p\.\s*)?\d+[a-z]?(?:[,–-]\s*\d+[a-z]?)*(?:\s*(?:ff?\.|s\.\s*v\.))?',text[b:])
                if loc:b+=loc.end()
            if b<len(text) and (text[b].isalnum() or text[b] in '/_'):continue
            # Source vocabulary is necessary but not sufficient: require a
            # bounded parenthesis or explicit comparison construction locally.
            left=text[max(0,a-150):a]
            paren=left.rfind('(')>left.rfind(')') and ')' in text[b:b+150]
            comparison=bool(re.search(r'\b(?:vgl\.|anders|Abb\.)\s*(?:[^;\n()]{0,80},\s*)?$',left))
            if not(paren or comparison):continue
            if any(max(a,n['start'])<min(b,n['end']) for n in existing):continue
            candidates.append(dict(start=a,end=b,literal=text[a:b],evidence=evidence,registered_label=label,local_syntax='bounded_parenthesis' if paren else 'explicit_comparison'))
    # Bounded source references still exist when their authority is unknown.
    # These grammars assert occurrence syntax, never an inherited identity.
    residual = [
        (r"(?<=vgl\. )[A-Z][^\W\d_]+\s+(?:18|19|20)\d{2}[a-z]?(?!\w)", 'explicit comparison author-year'),
        (r"(?<=\()Schwieger\s+\d+\s*(?:ff?\.)?", 'bounded author without year'),
        (r"(?<=\()dBe’uD\s+\d+,\d+", 'bounded unresolved source spelling'),
        (r"(?<=\()(?:Abt\.\s*\d+|\d+,\s*Abt\.)[^()]*?(?=\))", 'bounded implicit-source division reference'),
    ]
    for grammar,evidence in residual:
        for match in re.finditer(grammar,text):
            a,b=match.span()
            if not any(max(a,n['start'])<min(b,n['end']) for n in existing):
                candidates.append(dict(start=a,end=b,literal=text[a:b],evidence=evidence,
                    registered_label=None,local_syntax='explicit_bounded_reference'))
    unique={ (c['start'],c['end']):c for c in candidates }
    # A shorter registered label contained within an exact longer author or
    # source spelling is a grammar candidate, not another occurrence.
    return [c for (a,b),c in sorted(unique.items()) if not any(x<=a<b<=y and (x,y)!=(a,b) for x,y in unique)]


def augment_citations(projection,text,resolver):
    from benchmark_badw_structure import graph, PARENTS
    result=copy.deepcopy(projection)
    additions=inline_candidates(result,text,resolver)
    for c in additions:
        a,b=c['start'],c['end']
        parents=[n for n in result['nodes'] if n['kind'] in PARENTS['citation'] and n['start']<=a<b<=n['end']]
        parent=min(parents,key=lambda n:(n['end']-n['start'],n['id']))['id'] if parents else None
        key=f"{result['identity']}\0{result['review_text_sha256']}\0inline_citation\0{a}\0{b}"
        result['nodes'].append(dict(id=hashlib.sha256(key.encode()).hexdigest(),kind='citation',start=a,end=b,
            parent=parent,source_evidence=dict(rule=VERSION,**c)))
    graph(result['nodes'],result['edges'],text)
    return result,additions


def classify_residue(projection, text, view, residue, additions, baseline):
    """Account for every frozen diagnostic without deleting its source evidence."""
    semantic = view['semantic_hierarchy']
    forms = semantic['sanskrit_forms']
    records = []
    for old in residue:
        family = old['family']; spans = old['spans']
        a,b = spans[0] if spans else (0,0)
        value = text[a:b]
        record = dict(identity=projection['identity'], source_kind=projection['source_kind'],
            text_sha256=projection['review_text_sha256'], baseline_family=family,
            source_spans=spans, literal=value, baseline_details=old.get('details', {}))
        if family == 'language_evidence_untyped':
            marker = next((m for m in semantic['language_indicators'] if m['start']==a), None)
            record['classification'] = marker['family'] if marker else 'explicit_language_structure_needs_review'
            matched = [f for f in forms if f.get('marker_span') and f['marker_span'][0]==a]
            record['derived_form_ids'] = [f['id'] for f in matched]
            record['outcome'] = 'typed_exact_form' if matched else 'non_form_label' if marker and 'not_language_form' in marker['family'] or marker and 'prose' in marker['family'] else 'unresolved'
        elif family == 'language_conflict':
            observed = [n for n in projection['nodes'] if n['kind'] in ('tibetan','sanskrit') and any(n['start']==x and n['end']==y for x,y in spans)]
            bo=[n for n in observed if n['kind']=='tibetan'];sa=[n for n in observed if n['kind']=='sanskrit']
            record['classification'] = ('legitimate_nested_observation' if any(x['start']==y['start'] and x['end']==y['end'] for x in bo for y in sa) else 'broad_Tibetan_envelope_exact_Sanskrit_subspan' if bo and sa else 'unresolved_observation_overlap')
            record['outcome']='effective_source_structure'
            record['effective_assignments']=[s for s in semantic['effective_language_spans'] if max(a,s['start'])<min(b,s['end'])]
        elif family == 'ignored_citation_cue':
            new=[c for c in additions if (a<=c['start']<c['end']<=b or c['start']<=a<b<=c['end'])]
            existing=[c for c in view['citations'] if (a<=c['source_span']['start']<c['source_span']['end']<=b or c['source_span']['start']<=a<b<=c['source_span']['end']) and (c['source_span']['start'],c['source_span']['end']) in baseline]
            if new:
                record['classification']='inline_comparison' if 'vgl.' in value else 'inline_author_year' if any(c['evidence']=='registered author-year' for c in new) else 'inline_registered_source_locator'
                record['outcome']='new_citation_extracted'
            elif existing:
                record['classification']='existing_citation_in_broader_diagnostic_envelope';record['outcome']='diagnostic_false_positive'
            elif re.fullmatch(r'\s*\(?[\d\s,;:.–/\-]+\)?\s*',value):
                record['classification']='numeric_or_date_parenthesis';record['outcome']='diagnostic_false_positive'
            elif re.search(r'[↑↓→]|\bs\.\s*u\.|nicht testim\.|oder \d',value):
                record['classification']='cross_reference_or_internal_editorial_number';record['outcome']='diagnostic_false_positive'
            elif re.search(r'\b(?:reg\.|geb\.|Jhdt?\.|Jahrhundert|d\.\s*i\.)',value):
                record['classification']='date_lifespan_or_explanatory_number';record['outcome']='diagnostic_false_positive'
            elif 'skt.' in value:
                record['classification']='language_clause_not_bibliographic_reference';record['outcome']='diagnostic_false_positive'
            else:
                record['classification']='unregistered_or_malformed_reference_requires_review';record['outcome']='unresolved'
            record['new_citations']=[dict(c,accepted_authority_ids=v['accepted_authority_ids'],ownership=v['ownership'],ownership_reason=v.get('ownership_residual_reason')) for c in new for v in view['citations'] if v['source_span']['start']==c['start'] and v['source_span']['end']==c['end']]
        elif family == 'citation_owner_unresolved':
            c=next((c for c in view['citations'] if c['source_span']['start']==a and c['source_span']['end']==b),None)
            record['classification']=c.get('ownership_residual_reason') or c.get('source_structural_family') or 'no_bounded_passage' if c else 'source_span_contract_failure'
            record['outcome']=c['ownership'] if c else 'unresolved'
        else:raise ValueError('unexpected contextual baseline family: '+family)
        records.append(record)
    return records
