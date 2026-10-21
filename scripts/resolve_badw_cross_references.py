"""Bounded canonical linking of existing source cross-reference records.

URL capture (the older ``resolution_status``) is not entry resolution. This
adds a separate, replayable ``canonical_resolution`` annotation without
altering literal observations. Only actual supplied entry records can be
targets. There is deliberately no nearest-lemma, arrow-direction, Unicode
normalization, stem expansion, or morphological inference.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from urllib.parse import urlsplit, unquote
from collections import defaultdict
from pathlib import Path

METHOD_VERSION = "badw-cross-reference-exact-v1"


def printed_target(target, structure, text):
    """Separate printed superscript homonym and verified italic continuation.

    Whitespace joining is permitted only within the parser's bounded target;
    every nonspace lexical character must retain the same italic source font.
    An isolated regular numeral must be visibly raised before the target.
    """
    a, b = target['visual_start'], target['visual_end']
    literal = target['source_text']
    result = dict(literal=literal, lexical_target=literal, homonym=None,
                  other_qualifier=None, shape='exact_typographic_target', valid=False,
                  source_span=dict(start=a, end=b))
    if text[a:b] != literal:
        return result
    lines = structure.get('visual_lines', [])
    offsets = []; offset = 0
    for line in lines:
        offsets.append(offset); offset += len(line['text']) + 1
    def glyph(position):
        for i, start in enumerate(offsets):
            if start <= position < start + len(lines[i]['text']):
                local = position - start
                spans = [s for s in lines[i].get('style_spans', []) if s['start'] <= local < s['end']]
                return i, lines[i], spans[0] if len(spans) == 1 else {}
        return None, {}, {}
    match = re.match(r'\s*([1-9][0-9]?)\s+', literal)
    start = a
    if match:
        number_start = a + match.start(1)
        word_start = a + match.end()
        number_line_index, number_line, number_style = glyph(number_start)
        word_line_index, word_line, word_style = glyph(word_start)
        raised = (number_line.get('y') is not None and word_line.get('y') is not None
                  and number_line.get('first_x') is not None and word_line.get('first_x') is not None
                  and 1 < number_line['y'] - word_line['y'] < 10
                  and number_line['first_x'] < word_line['first_x'])
        same_page = (number_line.get('page_id') and number_line.get('page_id') == word_line.get('page_id')
                     and number_line.get('printed_page') is not None
                     and number_line.get('printed_page') == word_line.get('printed_page'))
        if number_style.get('style') == 'regular':
            # Preserve the established regular-font qualifier path.
            verified_number = (word_style.get('style') == 'italic'
                               and number_line.get('page_id') == word_line.get('page_id')
                               and 1 < number_line.get('y', 0) - word_line.get('y', 0) < 10
                               and number_line.get('first_x', 0) < word_line.get('first_x', 0))
        else:
            # An italic numeral is a homonym only when separate physical lines
            # and exact source spans independently establish an isolated raised
            # qualifier before the lexical form.
            number_digits = match.group(1)
            digit_styles = []
            for position in range(number_start, number_start + len(number_digits)):
                _, _, style = glyph(position)
                digit_styles.append(style)
            number_explicit = (number_style.get('style') == 'italic'
                                and number_style.get('font_id')
                                and number_line.get('text', '').strip() == number_digits
                                and len(digit_styles) == len(number_digits)
                                and all(s.get('style') == 'italic' and s.get('font_id')
                                        for s in digit_styles)
                                and len({s.get('font_id') for s in digit_styles}) == 1)
            word_local = word_start - offsets[word_line_index] if word_line_index is not None else -1
            word_explicit = (word_style.get('style') == 'italic' and word_style.get('font_id')
                             and number_line_index is not None
                             and word_line_index == number_line_index + 1
                             and word_local >= 0
                             and (not word_line.get('text', '')[:word_local]
                                  or word_line.get('text', '')[:word_local].isspace())) if word_line_index is not None else False
            verified_number = (number_explicit and word_explicit and same_page and raised
                               and number_line_index is not None and word_line_index is not None
                               and text[number_start + len(number_digits):word_start].isspace())
        if not verified_number:
            result['shape'] = 'unverified_numeric_qualifier'
            return result
        result.update(homonym=match.group(1), qualifier_span=dict(start=number_start,
                      end=a+match.end(1)), shape='raised_homonym_prefix')
        start = word_start
    positions = [i for i in range(start, b) if not text[i].isspace()]
    styles = [glyph(i)[2] for i in positions]
    if not positions or any(s.get('style') != 'italic' for s in styles) or len({s.get('font_id') for s in styles}) != 1:
        result['shape'] = 'mixed_typography_or_punctuation'
        # Exact unchanged labels retain the previously accepted parser contract;
        # changed boundaries require the stronger typography gate.
        result['valid'] = start == a and '\n' not in literal
        return result
    result.update(lexical_target=' '.join(text[start:b].split()), valid=True,
                  lexical_span=dict(start=start, end=b))
    if '\n' in text[start:b]:
        result['shape'] = 'raised_homonym_and_wrapped_target' if match else 'wrapped_italic_target'
    return result


class EntryIndex:
    def __init__(self, entries):
        self.urls = defaultdict(set)
        self.labels = defaultdict(set)
        self.identities = defaultdict(set)
        self.records = {}
        for entry in entries:
            if entry.get("record_type") != "entry":
                continue
            identifier = entry["id"]
            if identifier in self.records and self.records[identifier] != entry:
                raise ValueError(f"conflicting entry record: {identifier}")
            self.records[identifier] = entry
            url = entry.get("stable_url")
            if url:
                self.urls[url].add(identifier)
            label = entry.get("headword", {}).get("loc")
            if label:
                self.labels[label].add(identifier)
                self.identities[(label, str(entry.get("homonym") or ""))].add(identifier)
        encoded = json.dumps(sorted(self.records.values(), key=lambda r: r["id"]),
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.sha256 = hashlib.sha256(encoded.encode()).hexdigest()

    def resolve_source_candidate(self, occurrence, *, structure=None, text=None):
        """Derived exact printed label, preserving witness/homonym ambiguity.

        Requires the parser's single typographic target to reproduce the exact
        label. No normalization or collapsing homonyms / manifestations.
        """
        candidate = occurrence.get('source_candidate', {})
        label = occurrence.get('target_label', '')
        targets = candidate.get('target_candidates', [])
        valid = len(targets) == 1 and targets[0].get('source_text') == label
        parsed = dict(literal=label, lexical_target=label, homonym=None,
                      other_qualifier=None, shape='exact_typographic_target')
        if valid and structure is not None and text is not None:
            parsed = printed_target(targets[0], structure, text)
            valid = parsed['valid']
        lexical = parsed['lexical_target']
        ids = sorted((self.identities.get((lexical, parsed['homonym']), set())
                      if parsed['homonym'] else self.labels.get(lexical, set()))) if valid else []
        result = copy.deepcopy(occurrence)
        result['canonical_resolution'] = dict(
            method_version='badw-cross-reference-exact-v2',
            method='derived_exact_single_typographic_target' if valid else 'unresolved_target_extent',
            entry_index_sha256=self.sha256, candidate_entry_ids=ids,
            status='resolved' if len(ids) == 1 else 'ambiguous' if ids else 'unresolved',
            evidence_status='derived_source_structure', parsed_target=parsed,
            residual_reason='multiple_exact_homonym_identities' if ids else
                'exact_target_absent_from_acquired_index' if valid else 'unestablished_target_extent')
        if len(ids) == 1:
            result['canonical_resolution']['target_entry_id'] = ids[0]
            result['canonical_resolution']['target_lexical_entity'] = self.target_identity(ids[0])
        self._same_entity(result['canonical_resolution'])
        return result

    def resolve_source_candidate_with_members(self, occurrence, *, structure, text,
                                              source_binding):
        """Annotate independently bounded, explicitly separated PDF targets.

        This is deliberately separate from the historical single-target path:
        if any source, geometry, or list-boundary check fails, the exact old
        annotation is returned.  A plural occurrence remains one observation.
        """
        result = self.resolve_source_candidate(occurrence, structure=structure, text=text)
        members = _verified_target_members(
            self, occurrence, structure=structure, text=text,
            source_binding=source_binding)
        if members is None:
            return result
        resolutions = [m['resolution_status'] for m in members]
        established = sum(s == 'resolved' for s in resolutions)
        aggregate = ('complete' if established == len(members) else
                     'partial' if established else 'unresolved')
        # Preserve the old conservative parent status and all original source
        # fields. In particular, no singular parent target is introduced.
        annotation = result['canonical_resolution']
        annotation['target_members'] = members
        annotation['target_members_status'] = aggregate
        annotation.pop('target_entry_id', None)
        annotation.pop('target_lexical_entity', None)
        return result

    def _same_entity(self, resolution):
        ids = resolution['candidate_entry_ids']
        keys = {(self.records[i]['headword']['loc'], str(self.records[i].get('homonym') or '')) for i in ids}
        if ids and len(keys) == 1:
            resolution.update(status='resolved', target_lexical_entity=self.target_identity(ids[0]))
            # Witness ambiguity is independent of lexical identity. No
            # arbitrary witness is selected when several manifestations exist.
            if len(ids) > 1:
                resolution.pop('target_entry_id', None)
                resolution['witness_status'] = 'multiple_exact_manifestations'
            resolution.pop('residual_reason', None)

    def target_identity(self, entry_id):
        """Exact index identity, with witness membership kept separate."""
        entry = self.records[entry_id]
        label = entry['headword']['loc']
        homonym = str(entry.get('homonym') or '')
        key = json.dumps([label, homonym], ensure_ascii=False)
        return dict(id='lexical:' + hashlib.sha256(key.encode()).hexdigest(),
                    headword=label, homonym=homonym,
                    evidence='exact actual-entry headword and homonym index key',
                    witness_entry_ids=sorted(self.identities[(label, homonym)]))

    def resolve_manifestation(self, occurrence):
        result = self.resolve(occurrence)
        resolution = result['canonical_resolution']
        if resolution['status'] == 'unresolved' and occurrence.get('target_url'):
            label, homonym = occurrence.get('target_label'), occurrence.get('target_homonym')
            url = urlsplit(occurrence['target_url'])
            match = re.fullmatch(r'/lemma/([^/]+)/([1-9][0-9]*)', url.path)
            if (homonym is None and url.hostname == 'wts-digital.badw.de' and match
                    and unquote(match.group(1)) == label):
                homonym = match.group(2)
                resolution['anchor_identity_evidence'] = dict(
                    exact_decoded_headword=label, explicit_homonym=homonym,
                    source_url=occurrence['target_url'])
            # The explicit anchor supplies the exact headword and homonym.
            # An absent URL is preserved; a different witness can supply the target.
            if label and homonym is not None:
                candidates = sorted(self.identities.get((label, str(homonym)), set()))
                if candidates:
                    resolution.update(method='exact_anchor_identity_other_manifestation',
                                      candidate_entry_ids=candidates,
                                      status='resolved' if len(candidates)==1 else 'ambiguous')
                    if len(candidates)==1:resolution['target_entry_id']=candidates[0]
        if resolution['status'] == 'unresolved' and not occurrence.get('target_url'):
            label = occurrence.get('target_label')
            if label:
                candidates = sorted(self.labels.get(label, set()))
                resolution.update(method='exact_unlinked_source_target', candidate_entry_ids=candidates,
                                  status='ambiguous' if candidates else 'unresolved')
        self._same_entity(resolution)
        if resolution['status'] != 'resolved':
            resolution['residual_reason'] = ('multiple_exact_homonym_identities' if resolution['candidate_entry_ids']
                else 'explicit_link_target_absent_from_acquired_index' if occurrence.get('target_url')
                else 'exact_target_absent_from_acquired_index')
        target = resolution.get('target_entry_id')
        if target:resolution['target_lexical_entity']=self.target_identity(target)
        return result

    def resolve_reviewed_editorial_target(self, occurrence, review):
        """Apply an offline-validated exact interpretation; keep the defective URL.

        This is a separate editorial assertion, never a URL normalizer. Existing
        accepted destinations cannot be replaced through this path.
        """
        source = copy.deepcopy(occurrence)
        old = source.pop('canonical_resolution', None)
        if (old and old.get('status') == 'resolved') or self.resolve_manifestation(source)['canonical_resolution']['status'] == 'resolved':
            raise ValueError('review cannot replace an accepted cross-reference')
        if (not source.get('target_url') or review.get('source_target_url') != source['target_url']
                or not review.get('annotation_id') or not review.get('binding')
                or not review.get('physical_selectors') or not review.get('ranges')):
            raise ValueError('editorial target review is not source-bound')
        url = source.pop('target_url')
        result = self.resolve(source, reviewed_target=review)
        result['target_url'] = url
        resolution = result['canonical_resolution']
        resolution['method'] = 'reviewed_exact_editorial_target'
        self._same_entity(resolution)
        if resolution['status'] != 'resolved':
            resolution['residual_reason'] = ('multiple_exact_homonym_identities' if resolution['candidate_entry_ids']
                else 'reviewed_target_absent_from_acquired_index')
        target = resolution.get('target_entry_id')
        if target: resolution['target_lexical_entity'] = self.target_identity(target)
        return result

    def resolve(self, occurrence, *, reviewed_target=None):
        """Return a copy annotated with exact-index resolution.

        PDF targets require a source-bound review of the exact printed target
        extent. ``reviewed_target`` is not an unreviewed text normalizer. The
        literal, review and source spans remain attached to the annotation.
        A URL with no entry never falls back to an attractive nearby lemma.
        """
        if occurrence.get("record_type") != "cross_reference":
            raise ValueError("expected existing cross_reference record")
        if not occurrence.get("source_spans"):
            raise ValueError("cross-reference lacks exact source provenance")
        if "canonical_resolution" in occurrence:
            raise ValueError("already annotated; replay from the source record")
        url = occurrence.get("target_url")
        review = None
        if url:
            candidates = self.urls.get(url, set())
            method = "exact_explicit_url"
        elif reviewed_target is not None:
            review = copy.deepcopy(reviewed_target)
            if (review.get("occurrence_id") != occurrence.get("id") or
                    review.get("source_spans") != occurrence["source_spans"] or
                    review.get("literal") != occurrence.get("target_label") or
                    not isinstance(review.get("lemma"), str) or
                    not isinstance(review.get("review"), dict) or
                    not all(review["review"].get(k) for k in ("reviewer", "reviewed_at", "evidence"))):
                raise ValueError("printed target review is not bound to this occurrence")
            candidates = (self.identities.get((review["lemma"], str(review["homonym"])), set())
                          if review.get("homonym") is not None else
                          self.labels.get(review["lemma"], set()))
            method = "reviewed_exact_printed_target"
        else:
            candidates = set()
            method = "no_reviewed_target"
        ids = sorted(candidates)
        annotation = dict(method_version=METHOD_VERSION, method=method,
                          entry_index_sha256=self.sha256, candidate_entry_ids=ids,
                          status="resolved" if len(ids)==1 else "ambiguous" if ids else "unresolved")
        if len(ids)==1:
            annotation["target_entry_id"] = ids[0]
        if review is not None:
            annotation["target_review"] = review
        result = copy.deepcopy(occurrence)
        result["canonical_resolution"] = annotation
        return result


_EXPLICIT_MEMBER_SEPARATOR = re.compile(
    r"(?:\s*[,;]\s*|\s+(?:und|oder|bzw\.)\s+|\s*[↑↓↗↘]\s*)", re.IGNORECASE)


def _verified_target_members(index, occurrence, *, structure, text, source_binding):
    """Return strict member records, or None when source evidence is incomplete."""
    if (not isinstance(source_binding, dict) or
            not source_binding.get('identity') or
            not source_binding.get('text_sha256') or
            source_binding.get('identity') != structure.get('article_id') or
            source_binding.get('text_sha256') != structure.get('source_faithful_sha256') or
            not structure.get('review_text_sha256') or
            hashlib.sha256(text.encode('utf-8')).hexdigest() != structure.get('review_text_sha256')):
        return None
    candidate = occurrence.get('source_candidate')
    if not isinstance(candidate, dict):
        return None
    targets = candidate.get('target_candidates')
    label = occurrence.get('target_label')
    marker = occurrence.get('marker')
    parent_start, parent_end = candidate.get('visual_start'), candidate.get('visual_end')
    if (not isinstance(targets, list) or len(targets) < 2 or
            candidate.get('target_label_candidate') != label or
            not isinstance(parent_start, int) or not isinstance(parent_end, int) or
            not 0 <= parent_start < parent_end <= len(text) or
            not isinstance(marker, str) or not marker or
            text[parent_start:parent_end] != marker + label):
        return None
    source_spans = occurrence.get('source_spans')
    if not isinstance(source_spans, list) or not any(
            isinstance(span, dict) and
            span.get('visual_start') == parent_start and
            span.get('visual_end') == parent_end and
            span.get('target_label_candidate') == label
            for span in source_spans):
        return None
    lines = structure.get('visual_lines')
    if not isinstance(lines, list):
        return None
    line_offsets, offset = [], 0
    for line in lines:
        line_offsets.append(offset)
        offset += len(line.get('text', '')) + 1
    if offset - 1 != len(text):
        return None

    def glyph(position):
        for li, start in enumerate(line_offsets):
            end = start + len(lines[li].get('text', ''))
            if start <= position < end:
                local = position - start
                styles = [s for s in lines[li].get('style_spans', [])
                          if s.get('start', -1) <= local < s.get('end', -1)]
                return li, lines[li], styles[0] if len(styles) == 1 else None
        return None, None, None

    records, previous_end = [], None
    previous_start = None
    page_key = None
    for ordinal, target in enumerate(targets):
        start, end = target.get('visual_start'), target.get('visual_end')
        literal = target.get('source_text')
        if (not isinstance(start, int) or not isinstance(end, int) or
                not isinstance(literal, str) or not parent_start <= start < end <= parent_end or
                text[start:end] != literal or
                (previous_start is not None and start <= previous_start) or
                (previous_end is not None and start < previous_end)):
            return None
        separator = None
        if previous_end is not None:
            separator = text[previous_end:start]
            if not separator or not _EXPLICIT_MEMBER_SEPARATOR.fullmatch(separator):
                return None
        parsed = printed_target(target, structure, text)
        if not parsed.get('valid'):
            return None
        lexical_start = parsed.get('lexical_span', {}).get('start', start)
        lexical_end = parsed.get('lexical_span', {}).get('end', end)
        positions = [p for p in range(lexical_start, lexical_end) if not text[p].isspace()]
        styles = [glyph(p)[2] for p in positions]
        # Plural interpretation requires explicit, continuous italic evidence;
        # printed_target's compatibility fallback is insufficient here.
        if (not styles or any(not s or s.get('style') != 'italic' or not s.get('font_id')
                              for s in styles) or
                len({s.get('font_id') for s in styles}) != 1):
            return None
        line_ids = sorted({glyph(p)[0] for p in positions})
        if not line_ids or None in line_ids:
            return None
        locations = set()
        for li in line_ids:
            line = lines[li]
            if (not line.get('page_id') or line.get('printed_page') is None or
                    line.get('first_x') is None or line.get('y') is None):
                return None
            locations.add((line['page_id'], line['printed_page']))
        if len(locations) != 1:
            return None
        member_page = next(iter(locations))
        if page_key is None:
            page_key = member_page
        elif member_page != page_key:
            return None
        lexical = parsed['lexical_target']
        homonym = parsed.get('homonym')
        ids = sorted(index.identities.get((lexical, str(homonym)), set()) if homonym
                     else index.labels.get(lexical, set()))
        identity_keys = {(index.records[i]['headword']['loc'],
                          str(index.records[i].get('homonym') or '')) for i in ids}
        if not ids:
            status, entity = 'unresolved', None
        elif len(identity_keys) > 1:
            status, entity = 'ambiguous', None
        else:
            status, entity = 'resolved', index.target_identity(ids[0])
        member = dict(ordinal=ordinal, literal=literal,
                      source_span=dict(start=start, end=end),
                      source_binding=dict(identity=source_binding['identity'],
                                          text_sha256=source_binding['text_sha256']),
                      preceding_separator=separator, printed_target=parsed,
                      homonym_qualifier=homonym, exact_index_candidate_ids=ids,
                      resolution_status=status)
        if entity is not None:
            member['target_lexical_entity'] = entity
            if len(ids) == 1:
                member['target_entry_id'] = ids[0]
        elif status == 'ambiguous':
            member['residual_reason'] = 'multiple_exact_homonym_identities'
        else:
            member['residual_reason'] = 'exact_target_absent_from_acquired_index'
        records.append(member)
        previous_start = start
        previous_end = end
    if (not targets or targets[0].get('visual_start') != parent_start + len(marker) or
            targets[-1].get('visual_end') != parent_end):
        return None
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True,
                        help="explicit bounded source-reference JSONL, not a corpus assignment job")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.entries.open(encoding="utf-8") as stream:
        index = EntryIndex(json.loads(line) for line in stream if line.strip())
    with args.references.open(encoding="utf-8") as stream:
        records = [index.resolve(json.loads(line)) for line in stream if line.strip()]
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":"))+"\n" for r in records),
                           encoding="utf-8")


if __name__ == "__main__":
    main()
