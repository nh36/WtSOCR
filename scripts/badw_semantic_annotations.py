#!/usr/bin/env python3
"""Validate a small scholarly overlay against frozen source review packets.

No extraction, normalization, entity resolution or database promotion occurs.
Packet offsets are half-open Unicode code-point offsets, not OCR token indices.
Source binding verifies cached bytes and the frozen extraction view; it does not
certify the extraction itself or turn same-agent review into independent gold.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import gzip
import json
from pathlib import Path
import re

from build_badw_structural_review_packet import VERSION as PACKET_VERSION, rows

VERSION = "badw-semantic-annotation-v1"
SHA = re.compile(r"[0-9a-f]{64}\Z")
RELATIONS = {
    "citation_of": ({"citation"}, {"example", "definition", "sense", "lexical_parallel", "citable_passage"}),
    "translation_of": ({"translation"}, {"tibetan", "sanskrit"}),
    "gloss_of": ({"translation"}, {"tibetan", "sanskrit"}),
}


def relationship_claim(claim, ranges):
    """Validate exact endpoints, including shared/discontinuous support.

    Evidence ranges may contain endpoints; they do not assert ownership.
    Endpoints are source-view spans, never nearest-node or canonical identities.
    """
    _keys(claim, ("relation", "from", "to", "basis"))
    if claim["relation"] not in RELATIONS or claim["basis"] not in (
            "explicit_dom", "lex_item_punctuation", "reviewed_parallel_text"):
        raise ValueError("unsupported relationship or evidence basis")
    if not isinstance(claim["to"], list) or not claim["to"]:
        raise ValueError("relationship requires target endpoints")
    allowed_from, allowed_to = RELATIONS[claim["relation"]]
    seen = set()
    for endpoint, allowed in [(claim["from"], allowed_from)] + [(t, allowed_to) for t in claim["to"]]:
        _keys(endpoint, ("kind", "start", "end"))
        a, b = endpoint["start"], endpoint["end"]
        if endpoint["kind"] not in allowed or type(a) is not int or type(b) is not int or not any(
                r["start"] <= a < b <= r["end"] for r in ranges):
            raise ValueError("invalid or unbound relationship endpoint")
        key = (endpoint["kind"], a, b)
        if key in seen:
            raise ValueError("duplicate relationship endpoint")
        seen.add(key)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def binding(packet):
    """Bind the entire source view, including physical anchors, not review labels."""
    keys = ("contract_version", "identity", "source_kind", "source", "review_text",
            "review_text_sha256")
    return {"view_version": packet["contract_version"],
            "view_sha256": digest(canonical({key: packet[key] for key in keys})),
            "text_sha256": packet["review_text_sha256"]}


def physical_selectors(packet, ranges):
    """Return source-view anchors; PDF style/run envelopes are not glyph-exact."""
    if packet["source_kind"] == "html":
        return [{"kind": "html_visible_text", "source_sha256":
                 packet["source"]["source_object"]["sha256"],
                 "ranges": [[r["start"], r["end"]] for r in ranges]}]
    result = []
    offset = 0
    for index, line in enumerate(packet["source"]["visual_lines"]):
        for r in ranges:
            start, end = max(r["start"], offset), min(r["end"], offset + len(line["text"]))
            if start < end:
                result.append({"kind": "pdf_visual_line", "visual_line_index": index,
                    "page_id": line["page_id"], "line_start": start-offset,
                    "line_end": end-offset, "run_start": line["run_start"],
                    "run_end_exclusive": line["run_end_exclusive"],
                    "style_envelopes": [s for s in line["style_spans"]
                                        if s["start"] < end-offset and s["end"] > start-offset]})
        offset += len(line["text"]) + 1
    return result


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("missing or unsupported contract fields")


def _string(value):
    return isinstance(value, str) and bool(value.strip())


def _object(root, relative, expected, verified):
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise ValueError("invalid object hash")
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("object path escapes source root")
    key = (path, expected)
    if key not in verified:
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("cached object hash mismatch")
        verified.add(key)


def _packet(packet, cache, canonical_root, verified):
    if packet["contract_version"] != PACKET_VERSION:
        raise ValueError("unsupported source view version")
    text = packet["review_text"]
    if digest(text) != packet["review_text_sha256"]:
        raise ValueError("source view text hash mismatch")
    source = packet["source"]
    if packet["source_kind"] == "html":
        if source["article_source_text"] != text:
            raise ValueError("HTML view text differs from source text")
        obj = source["source_object"]
        _object(cache, obj["object_path"], obj["sha256"], verified)
    elif packet["source_kind"] == "pdf":
        if not source["source_objects"] or canonical_root is None:
            raise ValueError("PDF source requires canonical objects and root")
        if "\n".join(line["text"] for line in source["visual_lines"]) != text:
            raise ValueError("PDF visual lines differ from source view text")
        page_ids = {obj["page_id"] for obj in source["source_objects"]}
        if any(line["page_id"] not in page_ids for line in source["visual_lines"]):
            raise ValueError("visual line has no source page")
        for obj in source["source_objects"]:
            sha = obj["pdf_sha256"]
            _object(cache, f"objects/sha256/{sha[:2]}/{sha}", sha, verified)
            _object(canonical_root, obj["canonical_object"], obj["canonical_object_sha256"], verified)
    else:
        raise ValueError("unsupported source kind")


def reviewed_pdf_heading(claim, cache, canonical_root, verified, *, compound=False):
    """Check an individually reviewed destination against immutable PDF runs.

    The index key stays literal, including any line break. This is neither a
    corpus-wide alias nor permission to discard an explicit homonym qualifier.
    """
    from extract_badw_pdf_entries import _heading_reading
    proof = claim.get('destination_heading')
    _keys(proof, ('entry_id', 'headword', 'homonym', 'entry_start_source_span',
                  'canonical_object_sha256', 'printed_page'))
    span = proof['entry_start_source_span']
    if (not isinstance(span, dict) or canonical_root is None or
            proof['homonym'] != '' or span.get('homonym_run_indices') != [] or
            not isinstance(proof['headword'], dict) or
            proof['headword'].get('loc') != claim['lemma'] or
            not isinstance(claim['lemma'], str) or (not compound and '\n' not in claim['lemma']) or
            any(not part or part != part.strip() for part in claim['lemma'].split('\n'))):
        raise ValueError('invalid reviewed wrapped heading identity')
    if compound and (not _string(claim.get('source_target_label')) or
            '-' not in claim['source_target_label'] or
            any(c in claim['source_target_label'] for c in ('~', '\n')) or
            '\n' in claim['lemma'] or
            claim['source_target_label'].replace('-', ' ') != claim['lemma'] or
            any(not part for part in claim['lemma'].split(' ')) or 'source_headword' in claim):
        raise ValueError('invalid individually reviewed printed compound identity')
    logical = ' '.join(claim['source_target_label'].split())
    if '~' in logical:
        if logical.count('~') != 1 or not _string(claim.get('source_headword')):
            raise ValueError('wrapped heading requires an exact abbreviation expansion')
        logical = logical.replace('~', claim['source_headword'])
    elif 'source_headword' in claim:
        raise ValueError('unexpected abbreviation headword')
    if (not compound and logical != claim['lemma'].replace('\n', ' ')):
        raise ValueError('wrapped heading differs from literal target')
    _object(canonical_root, span['canonical_object'], proof['canonical_object_sha256'], verified)
    sha = span['representative_pdf_sha256']
    _object(cache, f'objects/sha256/{sha[:2]}/{sha}', sha, verified)
    with gzip.open(Path(canonical_root) / span['canonical_object'], 'rt', encoding='utf-8') as handle:
        page = json.load(handle)
    runs = page['positioned_page']['positioned_text_runs']
    indices = span.get('loc_run_indices', [])
    start, end = span.get('run_start'), span.get('run_end_exclusive')
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(runs) or
            not indices or any(type(i) is not int for i in indices) or
            indices != sorted(set(indices)) or not all(start <= i < end for i in indices)):
        raise ValueError('invalid wrapped heading run selection')
    selected = [runs[i] for i in indices]
    if (proof['entry_id'] != f"badw:pdf:{page['page_id']}:{start}" or
            proof['printed_page'] != page['printed_page'] or
            span['visible_body_sha256'] != page['visible_body_sha256'] or
            span['representative_pdf_url'] != page['representative_source']['canonical_url'] or
            sha != page['representative_source']['source_sha256'] or
            page['visible_body_sha256'] != digest(page['source_faithful_decoded_text']) or
            any(r.get('run_index') != i or r.get('unknown_glyphs') or
                r.get('x') is None or r.get('y') is None or
                any(g.get('unknown') for g in r.get('glyphs', [])) for i, r in zip(indices, selected)) or
            (not compound and len({r['y'] for r in selected}) < 2) or
            _heading_reading(selected) != claim['lemma'] or
            ''.join(r['decoded_unicode'] for r in selected).strip() != proof['headword'].get('source_loc')):
        raise ValueError('wrapped heading differs from canonical PDF evidence')


def reciprocal_perfect_introduction(claim, text, start):
    """Admit exact reviewed grammatical introductions, never arbitrary prose.

    An alternate spelling is evidence retained in the individually bound claim;
    it is not an alias used for destination lookup or reciprocal matching.
    """
    prefix = text[:start].strip()
    if claim.get('basis') == 'reviewed_printed_qualified_reciprocal_perfect':
        return 'source_alternate_headword' not in claim and prefix == 'pf. zu'
    if claim.get('basis') == 'reviewed_printed_reciprocal_perfect_future':
        return ('source_alternate_headword' not in claim and
                prefix in ('pf. und fut. zu', 'pf. und fut.'))
    alternate = claim.get('source_alternate_headword')
    if 'source_alternate_headword' in claim:
        return (isinstance(alternate, str) and 0 < len(alternate) <= 40 and
                re.fullmatch(r"[^\W\d_]+(?:[ ’][^\W\d_]+)*", alternate) is not None and
                prefix == 'auch ' + alternate + ', pf. zu')
    return prefix in ('pf. zu', 'pf. bzw. imp. zu')


def reciprocal_perfect_passage(passage, source_headword, source_marker, *,
        basis="reviewed_printed_reciprocal_perfect", source_introduction=None, source_homonym=None):
    """Check an exact reciprocal expression, retaining any shared-run comma.

    The optional offset selects past exactly ``, `` in the first PDF run;
    it is not punctuation stripping or an unrestricted substring search.
    Arrow direction must reciprocate the literal source arrow.
    """
    offset = passage.get('run_start_offset', 0)
    literal = passage.get('literal', '')
    if (type(offset) is not int or offset not in (0, 2) or
            (offset == 2 and not literal.startswith(', ')) or
            source_marker not in ('↑', '↓') or not source_headword):
        return False
    opposite = {'↑': '↓', '↓': '↑'}[source_marker]
    if basis == 'reviewed_printed_qualified_reciprocal_perfect':
        return (offset == 0 and isinstance(source_homonym, str) and
                re.fullmatch(r'[1-9][0-9]*', source_homonym) is not None and
                literal.strip() == 'pf. ' + opposite + source_homonym + source_headword)
    if basis == 'reviewed_printed_reciprocal_perfect_future':
        complementary = {'pf. und fut. zu': 'pf. und fut. ',
                         'pf. und fut.': 'pf. und fut. zu '}
        prefix = complementary.get(source_introduction)
        return prefix is not None and literal[offset:].strip() == prefix + opposite + source_headword
    return (basis == 'reviewed_printed_reciprocal_perfect' and
            literal[offset:].strip() == 'pf. ' + opposite + source_headword)


def qualified_reciprocal_geometry(page, runs, source_homonym):
    """One raised upright qualifier immediately preceding an italic headword.

    This replays individually reviewed canonical runs, not a general PDF parser.
    The arrow and preceding grammatical text remain on the body baseline.
    """
    fonts = {f['font_id']: (f.get('family'), f.get('style'))
             for f in page['representative_fonts']}
    numerals = [i for i, r in enumerate(runs) if r['decoded_unicode'] == source_homonym]
    if len(numerals) != 1:
        return False
    i = numerals[0]
    if not 0 < i < len(runs)-1:
        return False
    baseline = runs[0].get('y')
    if any(r.get('x') is None or r.get('y') is None for r in runs):
        return False
    return (1 <= runs[i]['y']-baseline <= 6 and
            0 <= runs[i+1]['x']-runs[i]['x'] <= 5 and
            all(r['y'] == baseline for j, r in enumerate(runs) if j != i) and
            all(fonts.get(r.get('font_id')) == ('TGaramond', 'regular' if j <= i else 'italic')
                for j, r in enumerate(runs)))


def reviewed_source_homonym(claim, packet, canonical_root):
    """Recover the source's numbered identity independently of the reciprocal."""
    from extract_badw_pdf_entries import extract_page
    matches = []
    for obj in packet['source']['source_objects']:
        # _packet has already verified every canonical object and original PDF.
        with gzip.open(Path(canonical_root)/obj['canonical_object'], 'rt', encoding='utf-8') as handle:
            page = json.load(handle)
        if page['visible_body_sha256'] != digest(page['source_faithful_decoded_text']):
            raise ValueError('qualified reciprocal source body hash differs')
        entries, _ = extract_page(page, obj['canonical_object'])
        matches.extend(e for e in entries if e['id'] == packet['identity'])
    if (len(matches) != 1 or matches[0]['homonym'] != claim.get('source_homonym') or
            matches[0]['loc_headword_reading'] != claim['source_headword']):
        raise ValueError('qualified reciprocal differs from canonical source homonym')


def reviewed_pdf_reciprocal_perfect(claim, ranges, packet, cache, canonical_root, verified):
    """Replay one facsimile-reviewed perfect-tense reciprocal homonym identity.

    This is an individual interpretation, never a rule choosing homonym 1.
    Re-extract the numbered destination heading from hash-pinned PDF runs and
    bind its exact reciprocal grammatical passage within that same article.
    """
    from extract_badw_pdf_entries import extract_page
    if (packet['source_kind'] != 'pdf' or len(ranges) != 1 or canonical_root is None or
            claim.get('source_target_url') is not None or
            any(not _string(claim.get(k)) for k in ('occurrence_id', 'source_headword',
                'source_target_label', 'lemma', 'homonym')) or
            not re.fullmatch(r'[1-9][0-9]*', claim['homonym']) or
            claim['source_target_label'] != claim['lemma'] or
            not reciprocal_perfect_introduction(claim, packet['review_text'], ranges[0]['start']) or
            ranges[0]['literal'] not in ('↓' + claim['lemma'], '↑' + claim['lemma'])):
        raise ValueError('invalid reviewed reciprocal perfect reference')
    qualified = claim['basis'] == 'reviewed_printed_qualified_reciprocal_perfect'
    if qualified:
        if not isinstance(claim.get('source_homonym'), str) or not re.fullmatch(r'[1-9][0-9]*', claim['source_homonym']):
            raise ValueError('qualified reciprocal requires an explicit source homonym')
        reviewed_source_homonym(claim, packet, canonical_root)
    proof = claim.get('destination_heading')
    _keys(proof, ('entry_id', 'headword', 'homonym', 'entry_start_source_span',
                  'canonical_object_sha256', 'printed_page', 'reciprocal_passage'))
    span = proof['entry_start_source_span']
    _object(canonical_root, span['canonical_object'], proof['canonical_object_sha256'], verified)
    sha = span['representative_pdf_sha256']
    _object(cache, f'objects/sha256/{sha[:2]}/{sha}', sha, verified)
    with gzip.open(Path(canonical_root) / span['canonical_object'], 'rt', encoding='utf-8') as handle:
        page = json.load(handle)
    entries, _ = extract_page(page, span['canonical_object'])
    matches = [e for e in entries if e['id'] == proof['entry_id']]
    if (len(matches) != 1 or matches[0]['source_span'] != span or
            matches[0]['homonym'] != claim['homonym'] or proof['homonym'] != claim['homonym'] or
            matches[0]['loc_headword_reading'] != claim['lemma'] or
            proof['headword'] != dict(loc=claim['lemma'], source_loc=matches[0]['loc_headword'],
                                      tibetan=matches[0]['tibetan_headword']) or
            proof['printed_page'] != page['printed_page'] or
            page['visible_body_sha256'] != digest(page['source_faithful_decoded_text'])):
        raise ValueError('reciprocal destination differs from canonical numbered heading')
    passage = proof['reciprocal_passage']
    _keys(passage, ('run_start', 'run_end_exclusive', 'literal'), ('run_start_offset',))
    a, b = passage['run_start'], passage['run_end_exclusive']
    if (type(a) is not int or type(b) is not int or
            not max(span['loc_run_indices']) < a < b <= span['run_end_exclusive'] or b-a > 32):
        raise ValueError('reciprocal passage outside reviewed destination')
    runs = page['positioned_page']['positioned_text_runs'][a:b]
    if (''.join(r['decoded_unicode'] for r in runs) != passage['literal'] or
            not reciprocal_perfect_passage(passage, claim['source_headword'], ranges[0]['literal'][0],
                basis=claim['basis'], source_introduction=packet['review_text'][:ranges[0]['start']].strip(),
                source_homonym=claim.get('source_homonym')) or
            passage.get('run_start_offset', 0) >= len(runs[0]['decoded_unicode']) or
            (not qualified_reciprocal_geometry(page, runs, claim.get('source_homonym')) if qualified
             else len({r.get('y') for r in runs}) != 1) or
            any(r.get('x') is None or r.get('y') is None or r.get('unknown_glyphs') or
                any(g.get('unknown') for g in r.get('glyphs', [])) for r in runs)):
        raise ValueError('reciprocal perfect lacks exact positioned source evidence')


def printed_misplaced_arrow(claim, ranges, text, lines):
    """Replay a reviewed printed marker error; never change its source extent.

    Only the individually reviewed upright ``↑fut.`` followed immediately by
    an italic target on the same physical line is admitted. This is not a
    parser rule: each occurrence still requires immutable facsimile evidence.
    """
    if (len(ranges) != 2 or claim.get('source_target_url') is not None or
            claim.get('homonym') is not None or not _string(claim.get('source_headword'))):
        raise ValueError('invalid printed misplaced-arrow interpretation')
    first, target = ranges
    a, b, c, d = first['start'], first['end'], target['start'], target['end']
    if (not 0 <= a < b < c < d <= len(text) or d-a > 80 or
            first != dict(start=a, end=b, literal=text[a:b]) or
            target != dict(start=c, end=d, literal=text[c:d]) or
            text[a:b] != '↑fut' or claim.get('source_target_label') != 'fut' or
            text[b:c] != '. ' or text[c:d] != claim.get('lemma') or
            not re.fullmatch(r"[^\W\d_]+(?:[ ’‘'\-][^\W\d_]+)*", text[c:d]) or
            (d < len(text) and text[d] != ',')):
        raise ValueError('printed misplaced-arrow ranges differ from exact wording')
    offset = 0
    matches = []
    for line in lines:
        end = offset + len(line['text'])
        if offset <= a < d <= end:
            matches.append((line, offset))
        offset = end + 1
    if len(matches) != 1 or '\n'.join(l['text'] for l in lines) != text:
        raise ValueError('printed misplaced arrow crosses a physical line')
    line, offset = matches[0]
    if (not line.get('page_id') or line.get('printed_page') is None or
            line.get('first_x') is None or line.get('y') is None or
            not isinstance(line.get('run_start'), int) or
            not isinstance(line.get('run_end_exclusive'), int) or
            line['run_start'] >= line['run_end_exclusive']):
        raise ValueError('printed misplaced arrow lacks physical provenance')
    for start, end, style in ((a, c, 'regular'), (c, d, 'italic')):
        for position in range(start-offset, end-offset):
            spans = [s for s in line['style_spans'] if s['start'] <= position < s['end']]
            if (len(spans) != 1 or spans[0].get('style') != style or
                    spans[0].get('family') != 'TGaramond' or not spans[0].get('font_id')):
                raise ValueError('printed misplaced arrow lacks exact source typography')


def validate(packets, annotations, *, cache, canonical_root=None):
    """Fail closed. Preserve candidates and superseded claims in the output."""
    source = {}
    for packet in packets:
        if packet["identity"] in source:
            raise ValueError("duplicate packet identity")
        source[packet["identity"]] = packet
    records, verified, checked = {}, set(), set()
    required = ("contract_version", "annotation_id", "identity", "binding", "ranges",
                "physical_selectors", "kind", "claim", "status", "review", "supersedes")
    for row in annotations:
        _keys(row, required)
        if row["contract_version"] != VERSION:
            raise ValueError("unsupported annotation version")
        annotation_id = row["annotation_id"]
        if not _string(annotation_id) or annotation_id in records:
            raise ValueError("invalid or duplicate annotation ID")
        packet = source.get(row["identity"])
        if packet is None:
            raise ValueError("unknown source identity")
        if packet["identity"] not in checked:
            _packet(packet, cache, canonical_root, verified)
            checked.add(packet["identity"])
        if row["binding"] != binding(packet):
            raise ValueError("stale source view binding")
        ranges = row["ranges"]
        if not isinstance(ranges, list) or not ranges:
            raise ValueError("annotation requires source ranges")
        previous = -1
        for r in ranges:
            _keys(r, ("start", "end", "literal"))
            start, end = r["start"], r["end"]
            if type(start) is not int or type(end) is not int or not (0 <= start < end <= len(packet["review_text"])) or start < previous:
                raise ValueError("invalid, unordered or overlapping source ranges")
            if r["literal"] != packet["review_text"][start:end]:
                raise ValueError("literal does not match source range")
            previous = end
        if row["physical_selectors"] != physical_selectors(packet, ranges):
            raise ValueError("physical selectors differ from frozen source view")
        claim = row["claim"]
        if row["kind"] == "language_span":
            _keys(claim, ("language",))
            if claim["language"] not in ("sa", "bo", "de"):
                raise ValueError("unsupported pilot language")
        elif row["kind"] == "form_mention":
            _keys(claim, ("base_form", "base_language", "context_language", "relation"))
            if not _string(claim["base_form"]) or claim["base_language"] != "sa" or claim["context_language"] != "de" or claim["relation"] != "inflected_name_mention":
                raise ValueError("unsupported pilot form mention")
        elif row["kind"] == "relationship":
            relationship_claim(claim, ranges)
        elif row["kind"] == "cross_reference_extent":
            _keys(claim, ("node_id", "previous_range", "basis"))
            old = claim["previous_range"]
            _keys(old, ("start", "end", "literal"))
            if (packet["source_kind"] != "pdf" or len(ranges) != 1 or
                    not _string(claim["node_id"]) or
                    claim["basis"] not in ("reviewed_printed_extent", "reviewed_printed_terminal_letter", "reviewed_printed_nonprinting_bridge", "reviewed_printed_arrow_boundary", "reviewed_printed_upright_space", "reviewed_printed_page_continuation") or
                    type(old["start"]) is not int or type(old["end"]) is not int or
                    not (ranges[0]["start"] == old["start"] and
                         (old["start"] < ranges[0]["end"] < old["end"] <= len(packet["review_text"])
                          if claim['basis'] == 'reviewed_printed_arrow_boundary' else
                          old["start"] < old["end"] < ranges[0]["end"])) or
                    packet["review_text"][old["start"]:old["end"]] != old["literal"] or
                    ranges[0]["literal"][0] not in "↑↓"):
                raise ValueError("invalid reviewed cross-reference extent")
        elif row["kind"] == "cross_reference_target":
            _keys(claim, ("occurrence_id", "source_target_url", "source_target_label",
                          "lemma", "homonym", "basis"), ("source_headword", "destination_heading", "member_ordinal", "source_alternate_headword", "source_homonym"))
            if ('source_homonym' in claim and
                    claim['basis'] != 'reviewed_printed_qualified_reciprocal_perfect'):
                raise ValueError('source homonym outside qualified reciprocal review')
            if ('source_alternate_headword' in claim and
                    claim['basis'] != 'reviewed_printed_reciprocal_perfect'):
                raise ValueError('alternate source spelling outside reciprocal review')
            if claim['basis'] == 'reviewed_editorial_headword_variant':
                from badw_article_parser import parse_database_article
                from urllib.parse import unquote, urlsplit
                if (packet['source_kind'] != 'html' or len(ranges) != 1 or
                        'source_headword' in claim or 'member_ordinal' in claim or
                        any(not _string(claim.get(k)) for k in ('occurrence_id',
                            'source_target_url', 'source_target_label', 'lemma', 'homonym')) or
                        not re.fullmatch(r'[1-9][0-9]*', claim['homonym'])):
                    raise ValueError('invalid reviewed editorial headword variant')
                proof = claim.get('destination_heading')
                _keys(proof, ('object_path', 'sha256', 'source_url'))
                _object(cache, proof['object_path'], proof['sha256'], verified)
                path = urlsplit(proof['source_url'])
                if (path.scheme != 'https' or path.netloc != 'wts-digital.badw.de' or
                        path.query or path.fragment or unquote(path.path) !=
                        '/lemma/' + claim['lemma'] + '/' + claim['homonym']):
                    raise ValueError('destination URL differs from reviewed identity')
                destination = parse_database_article((Path(cache)/proof['object_path']).read_bytes(),
                    source_metadata=dict(proof, final_url=proof['source_url'],
                                         delivery_type='database_article', valid_resource=True))
                if (destination['lemma'] != claim['lemma'] or
                        str(destination['homonym'] or '1') != claim['homonym']):
                    raise ValueError('destination heading differs from reviewed identity')
                obj = packet['source']['source_object']
                article = parse_database_article((Path(cache)/obj['object_path']).read_bytes(),
                    source_metadata=dict(obj, delivery_type='database_article', valid_resource=True))
                matches = [r for r in article['cross_references']
                           if (r['locator']['visible_text_start'], r['locator']['visible_text_end']) ==
                           (ranges[0]['start'], ranges[0]['end']) and
                           r['target_url'] == claim['source_target_url'] and
                           r['target_text'] == claim['source_target_label']]
                if article['article_source_text'] != packet['review_text'] or len(matches) != 1:
                    raise ValueError('headword variant lacks exact source DOM evidence')
            elif claim['basis'] == 'reviewed_editorial_member_whitespace':
                from badw_article_parser import parse_database_article
                if (packet['source_kind'] != 'html' or len(ranges) != 1 or
                        'source_headword' in claim or 'destination_heading' in claim or
                        type(claim.get('member_ordinal')) is not int or claim['member_ordinal'] < 0 or
                        any(not _string(claim[k]) for k in ('occurrence_id', 'source_target_url',
                            'source_target_label', 'lemma')) or claim['homonym'] is not None):
                    raise ValueError('invalid reviewed editorial member whitespace')
                obj = packet['source']['source_object']
                article = parse_database_article((Path(cache)/obj['object_path']).read_bytes(),
                    source_metadata=dict(obj, delivery_type='database_article', valid_resource=True))
                matches = [r for r in article['cross_references']
                           if (r['locator']['visible_text_start'], r['locator']['visible_text_end']) ==
                           (ranges[0]['start'], ranges[0]['end']) and r.get('html_target_members')]
                if article['article_source_text'] != packet['review_text'] or len(matches) != 1:
                    raise ValueError('editorial member lacks exact DOM evidence')
                ref = matches[0]
                members = ref['html_target_members']['members']
                ordinal = claim['member_ordinal']
                if (ordinal >= len(members) or ref['target_url'] != claim['source_target_url'] or
                        ref['target_text'] != claim['source_target_label']):
                    raise ValueError('editorial member differs from exact source interpretation')
                member = members[ordinal]
                literal = member['lexical_target']
                if ('\u00a0' not in literal or literal.replace('\u00a0', ' ') != claim['lemma'] or
                        member['homonym'] is not None):
                    raise ValueError('editorial member whitespace interpretation is not exact')
            elif 'member_ordinal' in claim:
                raise ValueError('member ordinal requires editorial member review')
            elif claim['basis'] == 'reviewed_printed_misplaced_arrow':
                from badw_article_parser import parse_database_article
                if packet['source_kind'] != 'pdf':
                    raise ValueError('printed misplaced arrow requires PDF evidence')
                printed_misplaced_arrow(claim, ranges, packet['review_text'], packet['source']['visual_lines'])
                proof = claim.get('destination_heading')
                _keys(proof, ('object_path', 'sha256', 'source_url'))
                _object(cache, proof['object_path'], proof['sha256'], verified)
                destination = parse_database_article((Path(cache)/proof['object_path']).read_bytes(),
                    source_metadata=dict(proof, final_url=proof['source_url'],
                                         delivery_type='database_article', valid_resource=True))
                if (destination['lemma'] != claim['lemma'] or not any(
                        r['target_text'] == claim['source_headword']
                        for r in destination['cross_references'])):
                    raise ValueError('printed interpretation lacks exact reciprocal destination evidence')
            elif claim['basis'] in ('reviewed_printed_reciprocal_perfect', 'reviewed_printed_reciprocal_perfect_future', 'reviewed_printed_qualified_reciprocal_perfect'):
                reviewed_pdf_reciprocal_perfect(claim, ranges, packet, cache, canonical_root, verified)
            elif claim['basis'] in ('reviewed_printed_wrapped_headword', 'reviewed_printed_compound_headword'):
                if (packet['source_kind'] != 'pdf' or len(ranges) != 1 or
                        any(not _string(claim.get(k)) for k in ('occurrence_id', 'source_target_label', 'lemma')) or
                        claim['source_target_url'] is not None or claim['homonym'] is not None):
                    raise ValueError('invalid reviewed wrapped heading reference')
                reviewed_pdf_heading(claim, cache, canonical_root, verified,
                    compound=claim['basis'] == 'reviewed_printed_compound_headword')
            elif claim["basis"] == "reviewed_printed_headword_substitution":
                if (packet["source_kind"] != "pdf" or len(ranges) != 1 or
                        any(not _string(claim.get(k)) for k in (
                            "occurrence_id", "source_target_label", "lemma", "source_headword")) or
                        'destination_heading' in claim or claim["source_target_url"] is not None or claim["homonym"] is not None or
                        claim["source_target_label"].count("~") != 1 or
                        " ".join(claim["source_target_label"].split()).replace("~", claim["source_headword"]) != claim["lemma"]):
                    raise ValueError("invalid reviewed printed headword substitution")
            elif claim['basis'] == 'reviewed_split_editorial_anchor':
                from badw_article_parser import parse_database_article
                if (packet['source_kind'] != 'html' or len(ranges) != 2 or
                        'source_headword' in claim or 'destination_heading' in claim or
                        any(not _string(claim[k]) for k in ('occurrence_id', 'source_target_url',
                            'source_target_label', 'lemma')) or claim['homonym'] is not None):
                    raise ValueError('invalid reviewed split editorial anchor')
                obj = packet['source']['source_object']
                article = parse_database_article((Path(cache)/obj['object_path']).read_bytes(),
                    source_metadata=dict(obj, delivery_type='database_article', valid_resource=True))
                matches = [r for r in article['cross_references']
                           if (r['locator']['visible_text_start'], r['locator']['visible_text_end']) ==
                           (ranges[0]['start'], ranges[0]['end']) and r.get('split_target_evidence')]
                if article['article_source_text'] != packet['review_text'] or len(matches) != 1:
                    raise ValueError('split editorial anchor lacks exact DOM evidence')
                ref = matches[0]
                proof = ref['split_target_evidence']
                loc = proof['continuation_locator']
                if (ref['target_url'] != claim['source_target_url'] or
                        ref['target_text'] != claim['source_target_label'] or
                        proof['lemma'] != claim['lemma'] or
                        (loc['visible_text_start'], loc['visible_text_end']) !=
                        (ranges[1]['start'], ranges[1]['end']) or
                        ranges[0]['end'] != ranges[1]['start']):
                    raise ValueError('split editorial anchor differs from exact source interpretation')
            elif (packet["source_kind"] != "html" or len(ranges) != 1 or
                    "source_headword" in claim or 'destination_heading' in claim or
                    any(not _string(claim[k]) for k in ("occurrence_id", "source_target_url",
                        "source_target_label", "lemma", "homonym")) or
                    not re.fullmatch(r"[1-9][0-9]*", claim["homonym"]) or
                    claim["basis"] != "reviewed_malformed_editorial_href"):
                raise ValueError("invalid reviewed editorial cross-reference target")
        elif row["kind"] == "citable_passage":
            # A reviewed extent, not a newly inferred sense or language node.
            _keys(claim, ())
            if len(ranges) != 1:
                raise ValueError("citable passage requires one exact range; use multiple targets for grouped support")
        else:
            raise ValueError("unsupported annotation kind")
        if row["status"] not in ("candidate", "accepted", "rejected"):
            raise ValueError("invalid annotation status")
        review = row["review"]
        _keys(review, ("reviewer", "reviewed_at", "mode", "method_version", "evidence"))
        if any(not _string(v) for v in review.values()):
            raise ValueError("review fields must be nonempty strings")
        if review["mode"] not in ("same_agent_source_review", "prediction_exposed_review", "independent_source_review"):
            raise ValueError("unsupported review mode")
        if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None:
            raise ValueError("review timestamp requires timezone")
        if not isinstance(row["supersedes"], list) or any(not _string(v) for v in row["supersedes"]) or len(set(row["supersedes"])) != len(row["supersedes"]):
            raise ValueError("invalid supersession list")
        records[annotation_id] = row
    # An explicit replacement can change ranges/type, but not witness identity.
    retired = set()
    for key, row in records.items():
        for old in row["supersedes"]:
            if old not in records or records[old]["identity"] != row["identity"]:
                raise ValueError("supersession requires an existing same-witness claim")
            if row["status"] != "accepted" or old in retired:
                raise ValueError("supersession requires one accepted replacement")
            retired.add(old)
    def visit(key, active, done):
        if key in active:
            raise ValueError("supersession cycle")
        if key not in done:
            for old in records[key]["supersedes"]:
                visit(old, active | {key}, done)
            done.add(key)
    done = set()
    for key in records:
        visit(key, set(), done)
    output = [{**records[key], "effective_status": "superseded" if key in retired else records[key]["status"]}
              for key in sorted(records)]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    work = (Path.cwd() / "work").resolve()
    if not output.is_relative_to(work):
        parser.error("validated source-bound output belongs under ignored work/")
    result = validate(rows(args.packets), rows(args.annotations), cache=args.cache,
                      canonical_root=args.canonical_root)
    encoded = "".join(canonical(row) + "\n" for row in result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(canonical({"contract_version": VERSION, "annotations": len(result),
                     "sha256": digest(encoded), "status_counts":
                     {s: sum(r["effective_status"] == s for r in result)
                      for s in ("accepted", "candidate", "rejected", "superseded")}}))


def apply_validated_annotations(packet, prediction, annotations):
    """Project an offline-validated overlay, without changing observations.

    Call validate() with the source cache before calling this function. Physical
    containment is not citation ownership. Accepted relationships bind exact
    extracted endpoints separately from containment; inactive and base-form
    claims remain explicit. Neither typography nor a base-form annotation is a
    language rule. Discontinuous ranges remain separate source spans.
    """
    from copy import deepcopy
    from benchmark_badw_structure import PARENTS, graph

    if prediction["identity"] != packet["identity"]:
        raise ValueError("annotation projection witness mismatch")
    result = deepcopy(prediction)
    selected = sorted((r for r in annotations if r["identity"] == packet["identity"]),
                      key=lambda r: r["annotation_id"])
    text = packet["review_text"]
    for row in selected:
        if row["binding"] != binding(packet) or row["physical_selectors"] != physical_selectors(packet, row["ranges"]):
            raise ValueError("annotation projection source binding mismatch")
        if "effective_status" not in row:
            raise ValueError("annotation must be validated before projection")
        for span in row["ranges"]:
            if not 0 <= span["start"] < span["end"] <= len(text) or text[span["start"]:span["end"]] != span["literal"]:
                raise ValueError("annotation projection literal mismatch")
        if row["effective_status"] != "accepted" or row["kind"] != "language_span":
            continue
        kind = {"bo": "tibetan", "sa": "sanskrit"}.get(row["claim"]["language"])
        # German language does not imply definition or translation function.
        if kind is None:
            continue
        for span in row["ranges"]:
            a, b = span["start"], span["end"]
            existing = next((n for n in result["nodes"] if
                             (n["kind"], n["start"], n["end"]) == (kind, a, b)), None)
            if existing is None:
                possible = sorted((n for n in result["nodes"] if
                    n["kind"] in PARENTS[kind] and n["start"] <= a < b <= n["end"]),
                    key=lambda n: (n["end"]-n["start"],
                                   n["kind"] == "source_division", n["id"]))
                existing = dict(id=f"annotation:{row['annotation_id']}:{a}:{b}",
                    kind=kind, start=a, end=b,
                    parent=possible[0]["id"] if possible else None,
                    association_status="source_containment_only")
                result["nodes"].append(existing)
            ids = existing.setdefault("semantic_annotation_ids", [])
            if row["annotation_id"] not in ids:
                ids.append(row["annotation_id"])
                ids.sort()
    result["semantic_annotations"] = selected
    extents = []
    for row in selected:
        if row["kind"] != "cross_reference_extent" or row["effective_status"] != "accepted":
            continue
        from parse_badw_pdf_articles import _candidates
        old, span = row["claim"]["previous_range"], row["ranges"][0]
        nodes = [n for n in result["nodes"] if n["id"] == row["claim"]["node_id"]
                 and n["kind"] == "cross_reference" and
                 (n["start"], n["end"]) == (old["start"], old["end"])]
        structure = result.get("original_structure", {})
        if (packet["source_kind"] != "pdf" or len(nodes) != 1 or
                text[old["start"]:old["end"]] != old["literal"] or
                structure.get("visual_lines") != packet["source"].get("visual_lines")):
            raise ValueError("reviewed cross-reference extent differs from frozen occurrence")
        candidates = structure["candidates"]["cross_references"]
        positions = [i for i, c in enumerate(candidates) if
                     (c["visual_start"], c["visual_end"]) == (old["start"], old["end"])]
        proposed = _candidates(structure["visual_lines"], structure["divisions"],
                               structure["article_id"],
                               reviewed_wrapped_lists=row['claim']['basis'] == 'reviewed_printed_extent',
                               reviewed_terminal_letter=row['claim']['basis'] == 'reviewed_printed_terminal_letter',
                               nonprinting_sources=packet['source']['source_objects']
                               if row['claim']['basis'] == 'reviewed_printed_nonprinting_bridge' else None,
                               upright_space_sources=packet['source']['source_objects']
                               if row['claim']['basis'] == 'reviewed_printed_upright_space' else None,
                               page_continuation_sources=packet['source']['source_objects']
                               if row['claim']['basis'] == 'reviewed_printed_page_continuation' else None)
        matches = [c for c in proposed["cross_references"] if
                   (c["visual_start"], c["visual_end"]) == (span["start"], span["end"])]
        if len(positions) != 1 or len(matches) != 1:
            raise ValueError("reviewed cross-reference extent lacks exact typographic support")
        if row['claim']['basis'] == 'reviewed_printed_arrow_boundary':
            previous = candidates[positions[0]]
            following = [c for c in candidates if c['visual_start'] > span['end'] and
                         c['visual_end'] == old['end']]
            old_targets = previous.get('target_candidates', [])
            new_targets = matches[0].get('target_candidates', [])
            # Contract only a duplicated second-arrow member. Keep the first
            # exact target, and require the swallowed suffix to survive as an
            # independently frozen occurrence in this same division/page.
            if (len(old_targets) != 2 or len(new_targets) != 1 or
                    new_targets[0] != old_targets[0] or len(following) != 1 or
                    old_targets[1]['visual_start'] != following[0]['visual_start'] or
                    text[span['end']:following[0]['visual_start']].strip() != ',' or
                    text[following[0]['visual_start']] not in '↑↓' or
                    following[0]['division_index'] != previous['division_index'] or
                    following[0]['source_line']['page_id'] != previous['source_line']['page_id'] or
                    not any(n['kind'] == 'cross_reference' and
                            (n['start'], n['end']) == (following[0]['visual_start'], old['end'])
                            for n in result['nodes'])):
                raise ValueError('reviewed cross-reference extent lacks independent arrow boundary')
        node = nodes[0]
        containers = [n for n in result["nodes"] if n["id"] == node["parent"]]
        if (len(containers) != 1 or not containers[0]["start"] <= span["start"] < span["end"] <= containers[0]["end"] or
                any(n["parent"] == node["id"] for n in result["nodes"]) or
                any(n["kind"] == "cross_reference" and n["id"] != node["id"] and
                    n["start"] < span["end"] and span["start"] < n["end"] for n in result["nodes"])):
            raise ValueError("reviewed cross-reference extent crosses existing structure")
        candidates[positions[0]] = matches[0]
        node["end"] = span["end"]
        extents.append(deepcopy(row))
    result["reviewed_cross_reference_extents"] = extents
    targets = {}
    for row in selected:
        if row["kind"] != "cross_reference_target" or row["effective_status"] != "accepted":
            continue
        claim = row["claim"]
        if claim["basis"] in ("reviewed_printed_headword_substitution", "reviewed_printed_wrapped_headword", "reviewed_printed_compound_headword", "reviewed_printed_misplaced_arrow", "reviewed_printed_reciprocal_perfect", "reviewed_printed_reciprocal_perfect_future", "reviewed_printed_qualified_reciprocal_perfect"):
            span = row["ranges"][0]
            structure = result.get("original_structure", {})
            nodes = [n for n in result["nodes"] if n["id"] == claim["occurrence_id"]
                     and n["kind"] == "cross_reference" and
                     (n["start"], n["end"]) == (span["start"], span["end"])]
            candidates = [c for c in structure.get("candidates", {}).get("cross_references", [])
                          if (c["visual_start"], c["visual_end"]) == (span["start"], span["end"])]
            if (packet["source_kind"] != "pdf" or len(nodes) != 1 or len(candidates) != 1 or
                    claim["occurrence_id"] in targets or
                    structure.get("visual_lines") != packet["source"].get("visual_lines") or
                    ('source_headword' in claim and structure.get("loc_headword") != claim["source_headword"]) or
                    ('source_homonym' in claim and structure.get('homonym') != claim['source_homonym']) or
                    candidates[0].get("target_label_candidate") != claim["source_target_label"]):
                raise ValueError("reviewed printed cross-reference differs from exact source occurrence")
            targets[claim["occurrence_id"]] = dict(occurrence_id=claim["occurrence_id"],
                source_spans=[deepcopy(candidates[0])], literal=claim["source_target_label"],
                source_target_url=None,
                lemma=claim["lemma"], homonym=claim["homonym"], basis=claim["basis"],
                annotation_id=row["annotation_id"], binding=row["binding"],
                physical_selectors=row["physical_selectors"], ranges=row["ranges"], review=row["review"])
            for field in ('source_headword', 'destination_heading', 'source_alternate_headword', 'source_homonym'):
                if field in claim:
                    targets[claim['occurrence_id']][field] = deepcopy(claim[field])
            continue
        matches = [r for r in result.get("original_records", [])
                   if r.get("record_type") == "cross_reference" and r["id"] == claim["occurrence_id"]]
        if len(matches) != 1 or claim["occurrence_id"] in targets:
            raise ValueError("reviewed cross-reference absent, duplicated or conflicting")
        occurrence = matches[0]
        span = row["ranges"][0]
        nodes = [n for n in result["nodes"] if n.get("lexical_record_id") == occurrence["id"]
                 and n["kind"] == "cross_reference"]
        if (len(nodes) != 1 or (nodes[0]["start"], nodes[0]["end"]) != (span["start"], span["end"]) or
                occurrence.get("target_url") != claim["source_target_url"] or
                occurrence.get("target_label") != claim["source_target_label"]):
            raise ValueError("reviewed cross-reference differs from exact source occurrence")
        targets[occurrence["id"]] = dict(occurrence_id=occurrence["id"],
            source_spans=deepcopy(occurrence["source_spans"]), literal=occurrence["target_label"],
            source_target_url=occurrence["target_url"], lemma=claim["lemma"], homonym=claim["homonym"],
            annotation_id=row["annotation_id"], binding=row["binding"],
            physical_selectors=row["physical_selectors"], ranges=row["ranges"], review=row["review"])
        if claim['basis'] in ('reviewed_split_editorial_anchor', 'reviewed_editorial_member_whitespace',
                              'reviewed_editorial_headword_variant'):
            targets[occurrence['id']]['basis'] = claim['basis']
        if claim['basis'] == 'reviewed_editorial_headword_variant':
            targets[occurrence['id']]['destination_heading'] = deepcopy(claim['destination_heading'])
        if claim['basis'] == 'reviewed_editorial_member_whitespace':
            targets[occurrence['id']]['member_ordinal'] = claim['member_ordinal']
    result["reviewed_cross_reference_targets"] = targets
    passages = []
    seen_passages = set()
    for row in selected:
        if row["kind"] != "citable_passage" or row["effective_status"] != "accepted":
            continue
        span = row["ranges"][0]
        extent = (span["start"], span["end"])
        if extent in seen_passages:
            raise ValueError("duplicate accepted citable passage extent")
        seen_passages.add(extent)
        passages.append({"id": "passage:" + row["annotation_id"],
            "kind": "citable_passage", **span, "annotation_id": row["annotation_id"],
            "binding": row["binding"], "physical_selectors": row["physical_selectors"],
            "review": row["review"]})
    result["citable_passages"] = passages
    # Semantic ownership is not physical containment. Keep these reviewed
    # assertions separate from the extraction benchmark's containment edges.
    # Fail closed if extraction no longer exposes an exact reviewed endpoint.
    relationships = []
    for row in selected:
        if row["kind"] != "relationship" or row["effective_status"] != "accepted":
            continue
        claim = row["claim"]
        relationship_claim(claim, row["ranges"])
        def resolve(endpoint):
            pool = passages if endpoint["kind"] == "citable_passage" else result["nodes"]
            matches = [n for n in pool if all(n[k] == endpoint[k] for k in ("kind", "start", "end"))]
            if len(matches) != 1:
                raise ValueError("reviewed relationship endpoint absent or ambiguous")
            key = "passage_id" if endpoint["kind"] == "citable_passage" else "node_id"
            return {**endpoint, key: matches[0]["id"]}
        relationships.append({"annotation_id": row["annotation_id"],
            "relation": claim["relation"], "from": resolve(claim["from"]),
            "to": [resolve(t) for t in claim["to"]], "basis": claim["basis"],
            "binding": row["binding"], "physical_selectors": row["physical_selectors"],
            "review": row["review"]})
    result["semantic_relationships"] = relationships
    graph(result["nodes"], result["edges"], text)
    return result


if __name__ == "__main__":
    main()
