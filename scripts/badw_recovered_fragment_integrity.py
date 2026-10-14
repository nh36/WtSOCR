"""Fail-closed punctuation checks for derived semantic fragments.

These checks never edit source observations. A production must independently
establish role and geometry before using this additional boundary guard.
"""
import re

REFERENCE_MARKER = re.compile(r'\b(?:vgl\.|s\.\s*v\.|Abt\.|Lex\.|pf\.|fut\.|imp\.|imper\.|präs\.|Kurzf\.)')


def delimiter_error(literal):
    stack = []
    pairs = {')': '(', ']': '[', '“': '„', '‘': '‚', '»': '«'}
    for char in literal:
        if char in pairs.values():
            stack.append(char)
        elif char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return 'unmatched_closing_delimiter'
    return 'unmatched_opening_delimiter' if stack else None


def definition_error(literal):
    if 'UNKNOWN' in literal or '\ufffd' in literal:
        return 'unresolved_source_decoding'
    if REFERENCE_MARKER.search(literal):
        return 'reference_or_grammatical_marker'
    return delimiter_error(literal)


def bounded_definition_end(text, start, end):
    """Stop before a reference or unfinished delimiter, without repairing it."""
    marker = REFERENCE_MARKER.search(text[start:end])
    if marker:
        end = start + marker.start()
        while end > start and text[end - 1] in ' ,;\n\t':
            end -= 1
    stack = []
    pairs = {')': '(', ']': '[', '“': '„', '‘': '‚', '»': '«'}
    for position in range(start, end):
        char = text[position]
        if char in pairs.values():
            stack.append((char, position))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                return start
            stack.pop()
    if stack:
        end = stack[0][1]
    while end > start and text[end - 1].isspace():
        end -= 1
    return end
