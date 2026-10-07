"""Literal structural components, not semantic ownership or language inference.

All offsets refer to the supplied Unicode source, never a normalized reading.
Semicolons delimit Lex. clauses only outside balanced parentheses and quotes.
Incomplete delimiters are retained as an explicit diagnostic.
"""
from __future__ import annotations

import re

QUOTE_PAIRS = {"„": "“", "«": "»", "‚": "‘"}


def author_year_reference_candidates(text, start, end):
    """Observe unquoted capitalized author/year/locator references only.

    A colon and numeric locator are required. Observation does not assert
    bibliography identity or citation ownership, including in etymologies.
    """
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid citation bounds")
    pattern = re.compile(r"(?<!\w)[A-ZÄÖÜ][A-Za-zÄÖÜäöüẞß-]{2,}\s+"
                         r"(?:18|19|20)\d{2}:\s*\d+(?:[–-]\d+)?"
                         r"(?:\s+ff?\.)?(?!\w)")
    quotes = quoted_spans(text, start, end)
    return [dict(start=m.start(), end=m.end(), source_text=m.group(),
                 status="unresolved_source_citation_candidate",
                 evidence="capitalized author year colon and numeric locator")
            for m in pattern.finditer(text, start, end)
            if not any(q['start'] <= m.start() < q['end'] for q in quotes)]


def comparison_reference_candidates(text, start, end):
    """Observe explicit ``vgl.`` references, without asserting what they cite.

    Require a source-shaped abbreviation plus a numeric locator or ``s.v.``
    headword. These remain unresolved candidates, not accepted bibliography
    links. Quoted examples are not evidence for an editorial reference.
    """
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid citation bounds")
    pattern = re.compile(
        r"(?<!\w)vgl\.\s+(?P<siglum>[A-Z][A-Za-z0-9]{1,23})\s+"
        r"(?:\d+(?:[,:]\s*\d+)*(?:\s+ff?\.)?(?:\s+s\.v\.\s+[^\W\d_][^\s,;().„“]*)?"
        r"|s\.v\.\s+[^\W\d_][^\s,;().„“]*)")
    quotations = quoted_spans(text, start, end)
    result = []
    for match in pattern.finditer(text, start, end):
        a, b = match.span()
        label = match['siglum']
        # Restrict untagged observations to short or capital-rich sigla.
        # Longer title-case author names need explicit bibliography evidence.
        if len(label) > 4 and sum(c.isupper() for c in label) < 2:
            continue
        if any(q["start"] <= a < q["end"] for q in quotations):
            continue
        result.append(dict(start=a, end=b, source_text=text[a:b],
            status="unresolved_source_citation_candidate",
            evidence="explicit vgl. reference with source-shaped label and locator or s.v. headword"))
    return result


def siglum_parentheses(text, start, end, siglum_spans):
    """Outermost balanced parentheses supported by explicit source siglum tags.

    This observes citation boundaries, not their ownership. Never generalize
    untagged prose parentheses or use tooltip bibliography text as evidence.
    """
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid citation bounds")
    stack, quotes, result = [], [], []
    for i in range(start, end):
        char = text[i]
        if char in QUOTE_PAIRS:
            quotes.append(QUOTE_PAIRS[char])
        elif quotes:
            if char == quotes[-1]:
                quotes.pop()
        elif char == "(":
            stack.append(i)
        elif char == ")" and stack:
            a = stack.pop()
            if not stack and any(a < x < y <= i for x, y in siglum_spans):
                result.append(dict(start=a, end=i + 1, source_text=text[a:i + 1],
                    status="unresolved_source_citation_candidate",
                    evidence="balanced parenthesis containing explicit DOM textsiglum"))
    return result


def terminal_lexical_citation(text, start, end):
    """A balanced terminal Lex. source expression, not resolved ownership.

    Require a siglum-shaped label (optionally with a locator). Corrections,
    prose parentheses, and quoted parentheses are not citation evidence.
    """
    _, diagnostics = lexical_clauses(text, start, end)
    if diagnostics:
        return None
    stack, quotes, pairs = [], [], []
    for i in range(start, end):
        char = text[i]
        if char in QUOTE_PAIRS:
            quotes.append(QUOTE_PAIRS[char])
        elif quotes:
            if char == quotes[-1]:
                quotes.pop()
        elif char == "(":
            stack.append(i)
        elif char == ")" and stack:
            a = stack.pop()
            if not stack:
                pairs.append((a, i + 1))
    if not pairs:
        return None
    a, b = pairs[-1]
    inside = text[a + 1:b - 1]
    if (text[b:end].strip() not in ("", ".") or
            not all(re.fullmatch(r"(?:ähnl\.\s*)?[A-Za-z][A-Za-z0-9’']*(?:\s+\d[\w:., /–-]*)?", member.strip())
                    and re.search(r"[A-Z0-9]", member)
                    for member in re.split(r",\s*(?=[A-Za-zä])", inside))):
        return None
    return dict(start=a, end=b, source_text=text[a:b],
                status="unresolved_source_citation_candidate",
                evidence="balanced terminal Lex. siglum-shaped parenthesis")


def located_parenthetical_citations(text, start, end):
    """Nonterminal source candidates with a siglum and numeric locator.

    This deliberately does not attach a citation to the containing definition.
    Quoted prose, nested corrections and bare labels are not evidence here.
    """
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid citation bounds")
    stack, quotes, result = [], [], []
    for i in range(start, end):
        char = text[i]
        if char in QUOTE_PAIRS:
            quotes.append(QUOTE_PAIRS[char])
        elif quotes:
            if char == quotes[-1]:
                quotes.pop()
        elif char == "(":
            stack.append(i)
        elif char == ")" and stack:
            a = stack.pop()
            inside = text[a + 1:i]
            numeric = (re.fullmatch(r"[A-Za-z][A-Za-z0-9’']*\s+\d[\w:., /–-]*", inside)
                       and re.search(r"[A-Z]", inside))
            headword = re.fullmatch(r"[A-Z][A-Za-z0-9]*\.?\s+s\.\s*v\.\s+[^()\n]+", inside)
            if not stack and (numeric or headword):
                result.append(dict(start=a, end=i + 1, source_text=text[a:i + 1],
                    status="unresolved_source_citation_candidate",
                    evidence=("balanced abbreviated source with explicit s.v. headword locator"
                              if headword else "balanced siglum-shaped parenthesis with numeric locator")))
    return result


def lexical_clauses(text, start, end):
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid lexical block bounds")
    cuts, stack, quotes, diagnostics = [start], [], [], []
    for i in range(start, end):
        char = text[i]
        if char in QUOTE_PAIRS:
            quotes.append(QUOTE_PAIRS[char])
        elif quotes:
            if char == quotes[-1]:
                quotes.pop()
        elif char in "([":
            stack.append(char)
        elif char in ")]":
            if stack and stack[-1] == {")": "(", "]": "["}[char]:
                stack.pop()
            else:
                diagnostics.append({"offset": i, "reason": "unmatched_closing_delimiter"})
        elif char == ";" and not stack:
            cuts.append(i + 1)
    if quotes or stack:
        diagnostics.append({"offset": end, "reason": "unclosed_delimiter"})
    cuts.append(end)
    clauses = []
    for a, b in zip(cuts, cuts[1:]):
        while a < b and text[a].isspace():
            a += 1
        while b > a and (text[b - 1].isspace() or text[b - 1] == ";"):
            b -= 1
        if a < b:
            clauses.append({"start": a, "end": b, "source_text": text[a:b]})
    return clauses, diagnostics


def quoted_spans(text, start, end):
    """Balanced source German quotations; no inferred translation relationship."""
    if not 0 <= start <= end <= len(text):
        raise ValueError("invalid quotation bounds")
    result, stack = [], []
    for i in range(start, end):
        if text[i] in QUOTE_PAIRS:
            stack.append((i, QUOTE_PAIRS[text[i]]))
        elif stack and text[i] == stack[-1][1]:
            a, _ = stack.pop()
            if not stack:
                result.append({"start": a, "end": i + 1, "source_text": text[a:i + 1]})
    return result
