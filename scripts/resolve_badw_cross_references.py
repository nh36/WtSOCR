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
                return lines[i], spans[0] if len(spans) == 1 else {}
        return {}, {}
    match = re.match(r'\s*([1-9][0-9]?)\s+', literal)
    start = a
    if match:
        number_start = a + match.start(1)
        word_start = a + match.end()
        number_line, number_style = glyph(number_start)
        word_line, word_style = glyph(word_start)
        if (number_style.get('style') != 'regular' or word_style.get('style') != 'italic'
                or number_line.get('page_id') != word_line.get('page_id')
                or not 1 < number_line.get('y', 0) - word_line.get('y', 0) < 10
                or not number_line.get('first_x', 0) < word_line.get('first_x', 0)):
            result['shape'] = 'unverified_numeric_qualifier'
            return result
        result.update(homonym=match.group(1), qualifier_span=dict(start=number_start,
                      end=a+match.end(1)), shape='raised_homonym_prefix')
        start = word_start
    positions = [i for i in range(start, b) if not text[i].isspace()]
    styles = [glyph(i)[1] for i in positions]
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
