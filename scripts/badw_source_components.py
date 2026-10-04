"""Literal structural components, not semantic ownership or language inference.

All offsets refer to the supplied Unicode source, never a normalized reading.
Semicolons delimit Lex. clauses only outside balanced parentheses and quotes.
Incomplete delimiters are retained as an explicit diagnostic.
"""
from __future__ import annotations

QUOTE_PAIRS = {"„": "“", "«": "»", "‚": "‘"}


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
