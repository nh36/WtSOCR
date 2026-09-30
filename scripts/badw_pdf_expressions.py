"""Source-position-preserving syntax for mixed-font PDF expressions.

This is not a Unicode repair layer. In particular, verified zero-contour
glyphs retain their UNKNOWN tokens in the source; only the boundary predicate
treats them as nonprinting. Other unknown identities remain barriers.
"""
from __future__ import annotations

import re

# Independently checked embedded glyf records: Arial CID 3/GID 3 has zero
# contours and advance 278; TT3678... CID 1627/GID 1627 has zero contours and
# advance 500. Keys include family, style, CID and the outline fingerprint
# emitted by the decoder, NOT just CID. Rabten's empty shad outline must not
# inherit this treatment. MicrosoftSansSerif CID 3 has a contour: excluded.
NONPRINTING = re.compile(
    r"⟦UNKNOWN:(?:Arial:(?:regular|italic):0003:ebbba6ed181c|"
    r"TT3678AC74tCID-WinCharSetFFFF-H2:regular:065B:ce91b893d20f)⟧")
APPARATUS_PREFIX = re.compile(r"\s*(?:r\.|v\.\s*l\.|Gl\.|metr\.)")


def apparatus_spans(text: str) -> list[tuple[int, int]]:
    """Balanced literal apparatus, including nested gloss/correction syntax.

    A mismatched or unclosed delimiter never licenses association. Quotes and
    semicolons are barriers; these cannot absorb preceding examples/citations.
    """
    stack: list[tuple[str, int]] = []
    result = []
    opening = {"(": ")", "[": "]", "⟨": "⟩", "{": "}"}
    for i, char in enumerate(text):
        if char in opening:
            stack.append((char, i))
        elif char in opening.values():
            if not stack or opening[stack[-1][0]] != char:
                stack.clear()
                continue
            left, start = stack.pop()
            interior = text[start + 1:i]
            recognized = (left == "(" and APPARATUS_PREFIX.match(interior)
                          or left in "⟨{" or left == "[" and interior.strip() in ("!", "usw.", "ir"))
            if recognized and not any(c in interior for c in "„“;") and len(interior) <= 500:
                result.append((start, i + 1))
    return sorted(result)


def boundary_mask(text: str) -> tuple[list[bool], list[tuple[int, int]]]:
    """Characters allowed between italic runs without admitting roman prose."""
    mask = [c.isspace() or c in "~≈’'" for c in text]
    spans = apparatus_spans(text)
    for start, end in spans:
        mask[start:end] = [True] * (end - start)
    for match in NONPRINTING.finditer(text):
        mask[match.start():match.end()] = [True] * len(match.group())
    for match in re.finditer(r"\.\.\.|\(!\)|\(zw\.\)", text):
        mask[match.start():match.end()] = [True] * len(match.group())
    return mask, spans


def contains_unknown(text: str) -> bool:
    """Only independently established nonprinting identities are exempt."""
    return "⟦UNKNOWN:" in NONPRINTING.sub("", text)

