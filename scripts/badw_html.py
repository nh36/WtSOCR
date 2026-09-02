#!/usr/bin/env python3
"""Small, dependency-free HTML tree helpers for BAdW source records.

The raw response bytes remain the authoritative source object.  This module
only builds a deterministic DOM-like tree used by the catalogue and article
parsers; it deliberately performs no Unicode normalisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re
from typing import Callable, Iterator, Mapping, Sequence


VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass(eq=False)
class TextNode:
    """A text fragment with its location in the decoded HTML source."""

    text: str
    line: int
    column: int
    parent: "Element | None" = field(default=None, repr=False)


@dataclass(eq=False)
class Element:
    """A minimal HTML element node."""

    tag: str
    attrs: dict[str, str]
    line: int
    column: int
    parent: "Element | None" = field(default=None, repr=False)
    children: list["Element | TextNode"] = field(default_factory=list, repr=False)
    end_line: int | None = None
    end_column: int | None = None

    @property
    def classes(self) -> frozenset[str]:
        return frozenset(self.attrs.get("class", "").split())


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {}, 1, 0)
        self._stack = [self.root]

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        line, column = self.getpos()
        element = Element(
            tag=tag,
            attrs={name: value or "" for name, value in attrs},
            line=line,
            column=column,
            parent=self._stack[-1],
        )
        self._stack[-1].children.append(element)
        if tag not in VOID_ELEMENTS:
            self._stack.append(element)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            element = self._stack.pop()
            element.end_line, element.end_column = self.getpos()

    def handle_endtag(self, tag: str) -> None:
        line, column = self.getpos()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                for element in self._stack[index:]:
                    element.end_line = line
                    element.end_column = column
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if not data:
            return
        line, column = self.getpos()
        self._stack[-1].children.append(
            TextNode(data, line, column, parent=self._stack[-1])
        )


def parse_html(text: str) -> Element:
    """Parse decoded HTML without changing its Unicode code points."""

    parser = _TreeBuilder()
    parser.feed(text)
    parser.close()
    return parser.root


def iter_elements(node: Element, *, include_self: bool = False) -> Iterator[Element]:
    if include_self:
        yield node
    for child in node.children:
        if isinstance(child, Element):
            yield child
            yield from iter_elements(child)


def iter_text_nodes(node: Element) -> Iterator[TextNode]:
    for child in node.children:
        if isinstance(child, TextNode):
            yield child
        else:
            yield from iter_text_nodes(child)


def find_all(
    node: Element,
    *,
    tag: str | None = None,
    class_name: str | None = None,
    predicate: Callable[[Element], bool] | None = None,
) -> list[Element]:
    matches = []
    for element in iter_elements(node, include_self=True):
        if tag is not None and element.tag != tag:
            continue
        if class_name is not None and class_name not in element.classes:
            continue
        if predicate is not None and not predicate(element):
            continue
        matches.append(element)
    return matches


def find_first(
    node: Element,
    *,
    tag: str | None = None,
    class_name: str | None = None,
    predicate: Callable[[Element], bool] | None = None,
) -> Element | None:
    matches = find_all(node, tag=tag, class_name=class_name, predicate=predicate)
    return matches[0] if matches else None


def is_descendant_of(element: Element, ancestor: Element) -> bool:
    current: Element | None = element
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def dom_path(node: Element | TextNode) -> str:
    """Return a stable, XPath-like location within this parsed response."""

    if isinstance(node, TextNode):
        if node.parent is None:
            return "/text()[1]"
        siblings = [
            child for child in node.parent.children if isinstance(child, TextNode)
        ]
        return f"{dom_path(node.parent)}/text()[{siblings.index(node) + 1}]"

    if node.parent is None:
        return "/document[1]"
    same_tag = [
        child
        for child in node.parent.children
        if isinstance(child, Element) and child.tag == node.tag
    ]
    return f"{dom_path(node.parent)}/{node.tag}[{same_tag.index(node) + 1}]"


def exact_text(
    node: Element,
    *,
    excluded_classes: Sequence[str] = (),
    excluded_tags: Sequence[str] = (),
) -> str:
    """Concatenate source text nodes exactly, optionally omitting subtrees."""

    class_exclusions = frozenset(excluded_classes)
    tag_exclusions = frozenset(excluded_tags)

    def visit(element: Element) -> Iterator[str]:
        if element.tag in tag_exclusions or element.classes & class_exclusions:
            return
        for child in element.children:
            if isinstance(child, TextNode):
                yield child.text
            else:
                yield from visit(child)

    return "".join(visit(node))


def compact_text(text: str) -> str:
    """Fold layout whitespace only; do not normalise or transliterate."""

    return re.sub(r"\s+", " ", text).strip()


def element_locator(element: Element) -> dict[str, int | str | None]:
    return {
        "dom_path": dom_path(element),
        "source_line": element.line,
        "source_column": element.column,
        "source_end_line": element.end_line,
        "source_end_column": element.end_column,
    }


def decode_html_bytes(
    body: bytes, response_headers: Mapping[str, str] | None = None
) -> tuple[str, str, bool]:
    """Decode HTML using the declared charset, falling back to UTF-8.

    The boolean records whether replacement characters were needed.  The raw
    object is retained separately, so a malformed source is always auditable.
    """

    headers = {key.lower(): value for key, value in (response_headers or {}).items()}
    content_type = headers.get("content-type", "")
    match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding), encoding, False
    except (LookupError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace"), "utf-8", True
