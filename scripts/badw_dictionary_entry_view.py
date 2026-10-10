"""Read-only reader contract, derived from validated structural projections.

No language, ownership, bibliography or target inference is performed here.
Offsets and parser payloads live in the separate inspection export. Components
retain source-bound identities; missing derived forms are explicitly null.
"""
from __future__ import annotations

import hashlib
import re

VERSION = "badw-dictionary-entry-view-v1"


def display_blocks(segments):
    """Presentation-only layout; no language or ownership inference.

    Layout whitespace becomes spaces, including PDF line wraps. Source
    segments remain untouched. Only explicit extracted boundaries create
    paragraph breaks; a qualifier or citation never creates a break.
    """
    blocks = []
    current = dict(kind='entry', segments=[])
    for segment in segments:
        starts = set(segment['starts_types'])
        kind = next((k for k in ('sense', 'source_division', 'example', 'lexical_section', 'lexical_parallel')
                     if k in starts), None)
        if kind and current['segments']:
            blocks.append(current)
            current = dict(kind=kind, segments=[])
        elif kind:
            current['kind'] = kind
        value = re.sub(r'\s+', ' ', segment['text'])
        # Avoid repeated spaces across component boundaries without moving
        # a character into a different language/citation component.
        if current['segments'] and current['segments'][-1]['text'].endswith(' '):
            value = value.lstrip(' ')
        if value:
            current['segments'].append(dict(segment, text=value))
    if current['segments']:
        blocks.append(current)
    return blocks


def identifier(entry, text_hash, kind, start, end):
    key = f"{entry}\0{text_hash}\0{kind}\0{start}\0{end}"
    return "span:" + hashlib.sha256(key.encode()).hexdigest()


def entry_view(inspected, bibliography=None):
    p = inspected["projection"]
    entry = inspected["entry"]
    text = inspected["review_text"]
    components = []
    by_node = {}
    for node in p["nodes"]:
        start, end, kind = node["start"], node["end"], node["kind"]
        item = dict(id=identifier(entry["id"], p["review_text_sha256"], kind, start, end),
                    type=kind, source_form=text[start:end], language=None,
                    normalized_wylie=None, tibetan_script=None)
        if kind in ("tibetan", "sanskrit"):
            item["language"] = "bo" if kind == "tibetan" else "sa"
        components.append((start, end, item))
        by_node[node["id"]] = item
    for node in p["nodes"]:
        if node.get("parent"):
            by_node[node["id"]]["source_parent_id"] = by_node[node["parent"]]["id"]
    # A reviewed annotation supplements, never replaces, a source observation.
    for a in p.get("semantic_annotations", []):
        if a.get("effective_status", a.get("status")) != "accepted":
            continue
        if a.get("kind") != "language_span":
            continue
        if a.get("binding", {}).get("text_sha256") not in (None, p["review_text_sha256"]):
            raise ValueError("language annotation belongs to a different source view")
        language = a.get("claim", {}).get("language")
        for r in a.get("ranges", []):
            start, end = r["start"], r["end"]
            if not 0 <= start <= end <= len(text) or text[start:end] != r["literal"]:
                raise ValueError("language annotation literal mismatch")
            item = dict(id=a["annotation_id"] + f":{start}:{end}", type="language_annotation",
                        source_form=text[start:end], language=language,
                        normalized_wylie=None, tibetan_script=None)
            components.append((start, end, item))
    citations = []
    for node in p["nodes"]:
        if node["kind"] != "citation":
            continue
        cid = node.get("lexical_record_id")
        authorities = (bibliography or {}).get((p['identity'], node['id']),
                                               (bibliography or {}).get(cid, []))
        citations.append(dict(component_id=by_node[node["id"]]["id"],
                              source_form=text[node["start"]:node["end"]],
                              bibliography=authorities,
                              bibliography_status="resolved" if authorities else "unresolved",
                              accepted_authority_ids=sorted({a['id'] for a in authorities}),
                              ownership="unresolved"))
    relationships = []
    for r in p.get("semantic_relationships", []):
        # These are already accepted, source-bound projection relationships.
        if r.get("effective_status", r.get("status", "accepted")) != "accepted":
            continue
        if r.get("binding", {}).get("text_sha256") not in (None, p["review_text_sha256"]):
            raise ValueError("relationship belongs to a different source view")
        source = r.get("from", {})
        if source.get("node_id") not in by_node:
            raise ValueError("accepted relationship has no source component")
        targets = []
        for t in r.get("to", []):
            if t.get("node_id") in by_node:
                targets.append(by_node[t["node_id"]]["id"])
            elif "start" in t and "end" in t:
                start, end = t["start"], t["end"]
                if not 0 <= start < end <= len(text):
                    raise ValueError("citable passage outside source view")
                if "literal" in t and t["literal"] != text[start:end]:
                    raise ValueError("citable passage literal mismatch")
                target = dict(id=t.get("passage_id") or identifier(entry["id"], p["review_text_sha256"],
                              "citable_passage", start, end), type="citable_passage",
                              source_form=text[start:end], language=None)
                if not any(c["id"] == target["id"] for _, _, c in components):
                    components.append((start, end, target))
                targets.append(target["id"])
            else:
                raise ValueError("accepted relationship has no target component")
        if not targets:
            raise ValueError("accepted relationship has empty targets")
        relationships.append(dict(id=r["annotation_id"], type=r["relation"],
                                  from_id=by_node[source["node_id"]]["id"], to_ids=targets))
        if r["relation"] == "citation_of":
            for c in citations:
                if c["component_id"] == by_node[source["node_id"]]["id"]:
                    c["ownership"] = "reviewed"
                    c["supports"] = targets
    # Include reviewed subpassages in the display boundaries too. Every literal
    # character is emitted once even when several annotations overlap.
    # Section labels are source observations, not inferred citation owners.
    # Their extracted block coordinates also keep the literal Lex. label out
    # of the preceding example in the reader-only layout.
    structure = p.get('original_structure', {})
    blocks = (structure.get('lexical_blocks', []) if p['source_kind'] == 'html'
              else structure.get('candidates', {}).get('lexical_blocks', []))
    lexical_starts = set()
    for block in blocks:
        start = (block.get('locator', {}).get('visible_text_start')
                 if p['source_kind'] == 'html' else block.get('label_start'))
        if start is not None:
            match = re.match(r'\s*Lex\.', text[start:])
            if not match:
                raise ValueError('Lex. display boundary differs from source label')
            lexical_starts.add(start)
    boundaries = sorted({0, len(text)} | lexical_starts |
                        {v for s, e, _ in components for v in (s, e)})
    # Nested lexical observations (a quoted equivalent inside a full parallel)
    # retain their identities, but do not start additional reader paragraphs.
    # Punctuation-only observations likewise are not independent parallels.
    lexical_display_starts = {
        s for s, e, c in components if c['type'] == 'lexical_parallel'
        and any(char.isalnum() for char in text[s:e])
        and not any(os <= s and e <= oe and (os, oe) != (s, e)
                    for os, oe, outer in components
                    if outer['type'] == 'lexical_parallel')
    }
    segments = []
    for start, end in zip(boundaries, boundaries[1:]):
        active = [c for s, e, c in components if s <= start and end <= e]
        starts_types = {c['type'] for s, _, c in components if s == start}
        if start not in lexical_display_starts:
            starts_types.discard('lexical_parallel')
        segments.append(dict(text=text[start:end], component_ids=[c["id"] for c in active],
                             starts_types=sorted(starts_types |
                                                 ({'lexical_section'} if start in lexical_starts else set())),
                             types=sorted({c["type"] for c in active}),
                             languages=sorted({c["language"] for c in active if c["language"]})))
    references = []
    for ref in inspected["cross_references"]:
        resolution = ref.get("canonical_resolution", {})
        node = next((n for n in p["nodes"] if n.get("lexical_record_id") == ref.get("id")
                     and ref.get("id") is not None), None)
        references.append(dict(component_id=by_node[node["id"]]["id"] if node else None,
                               marker=ref.get("marker"), wording=ref.get("target_label", ""),
                               source_url=ref.get("target_url"),
                               target_entry_id=resolution.get("target_entry_id"),
                               status=resolution.get("status", "unresolved")))
    return dict(contract_version=VERSION, id=entry["id"],
                headword=entry["headword"], homonym=entry.get("homonym"),
                headword_forms=[dict(id=identifier(entry["id"],
                                     hashlib.sha256(value.encode()).hexdigest(), key, 0, len(value)),
                                     type="headword", language="bo", source_form=value,
                                     representation="tibetan_script" if key == "tibetan" else "WTS/LoC",
                                     normalized_wylie=None, tibetan_script=value if key == "tibetan" else None)
                                for key in ("loc", "tibetan")
                                if (value := entry["headword"].get(key))],
                source_url=entry.get("stable_url"),
                senses=[by_node[n["id"]]["id"] for n in sorted(p["nodes"], key=lambda n: (n["start"], n["end"]))
                        if n["kind"] in ("sense", "source_division")],
                components=[c for _, _, c in sorted(components, key=lambda x: (x[0], x[1], x[2]["id"]))],
                segments=segments, display_blocks=display_blocks(segments),
                citations=citations, cross_references=references,
                relationships=relationships, inspection_id=p["identity"])
