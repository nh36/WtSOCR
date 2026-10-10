"""Exact source occurrence bridges; no spelling or ownership inference.

The visual text can change after positioning repairs. Bind through immutable
PDF hashes and source run/character coordinates, not visual-view offsets.
Canonical JSON hashes are deliberately not source PDF identities.
"""
import hashlib
import gzip
import json
import sqlite3
from collections import Counter

from parse_badw_pdf_articles import _visual_glyphs


def html_occurrence_resolutions(records, cache_root, resolver):
    """Resolve exact cached HTML occurrences through the existing resolver.

    Replaying the immutable object verifies the view before DOM evidence is
    used. A lexical-record ID is neither necessary nor sufficient here.
    """
    from badw_article_parser import parse_database_article
    results, diagnostics = {}, []
    for p in records:
        if p['source_kind'] != 'html':
            continue
        metadata = dict(p['source']['source_object'],
                        delivery_type='database_article', valid_resource=True)
        sha = metadata['sha256']
        body = (cache_root / 'objects' / 'sha256' / sha[:2] / sha).read_bytes()
        if hashlib.sha256(body).hexdigest() != sha:
            raise ValueError('cached HTML object hash mismatch')
        article = parse_database_article(body, source_metadata=metadata)
        text = article['article_source_text']
        if text != p['source']['article_source_text']:
            raise ValueError('cached HTML source view mismatch')
        seen = set()
        for node in p['nodes']:
            if node['kind'] != 'citation':
                continue
            start, end = node['start'], node['end']
            if not (isinstance(start, int) and isinstance(end, int)
                    and 0 <= start < end <= len(text)):
                raise ValueError('invalid HTML citation source bounds')
            key = (sha, start, end, text[start:end])
            if key in seen:
                raise ValueError('ambiguous duplicate HTML citation occurrence')
            seen.add(key)
            evidence = []
            for siglum in article['sigla']:
                loc = siglum['locator']
                a, b = loc['visible_text_start'], loc['visible_text_end']
                if start <= a < b <= end:
                    evidence.append(dict(start=a-start, end=b-start,
                        label=text[a:b], expansion=siglum['expanded_display_text']))
            resolution = (resolver.resolve_dom(text[start:end], evidence) if evidence
                          else resolver.resolve(text[start:end]))
            results[(p['identity'], node['id'])] = resolution
            diagnostics.append(dict(entry_id=p['identity'], node_id=node['id'],
                status='matched', source_sha256=sha, start=start, end=end,
                literal=text[start:end], resolution=resolution))
    return results, diagnostics


def exact_glyph_key(locations, visual_lines, pages):
    """Replay style envelopes against immutable glyphs, then select characters.

    Unlike an envelope identity, this survives line/style-envelope merging.
    Every character must reproduce the source view before it may be joined.
    Layout-generated newlines are not glyphs; actual spaces remain characters.
    """
    result = []
    for location in locations:
        index = location.get('line_index')
        page = pages.get(location.get('page_id'))
        if page is None or index is None or not 0 <= index < len(visual_lines):
            return ()
        line = visual_lines[index]
        if '_bridge_atoms' not in page:
            page['_bridge_atoms'] = _visual_glyphs(
                page['positioned_page']['positioned_text_runs'], set())[0]
        atoms = page['_bridge_atoms']
        start, end = location['line_char_start'], location['line_char_end']
        covered = 0
        for span in line.get('style_spans', []):
            a, b = max(start, span['start']), min(end, span['end'])
            if a >= b:
                continue
            first = (span['first_run_index'], span['first_glyph_index'])
            last = (span['last_run_index'], span['last_glyph_index'])
            selected = [atom for atom in atoms if first <=
                        (atom['run_index'], atom['glyph_index']) <= last]
            if not selected or any(atom['font_id'] != span['font_id'] for atom in selected):
                return ()
            chars = [(location['page_id'], atom['font_id'], atom['run_index'],
                      atom['glyph_index'], i, char)
                     for atom in selected for i, char in enumerate(atom['unicode'])]
            if ''.join(c[-1] for c in chars) != line['text'][span['start']:span['end']]:
                return ()
            result.extend(chars[a-span['start']:b-span['start']])
            covered += b-a
        if covered != end-start:
            return ()
    return tuple(result)


def source_key(lines):
    return tuple(tuple(line.get(k) for k in (
        'page_id', 'run_start', 'run_end_exclusive',
        'line_char_start', 'line_char_end')) for line in lines)


def source_objects(objects):
    return sorted((o['page_id'], o['pdf_sha256'], o['source_text_sha256'],
                   o['run_start'], o['run_end_exclusive']) for o in objects)


def glyph_envelope_key(lines, visual_lines):
    """Bind character slices to unchanged style/glyph envelopes.

    Line merging changes line offsets, but not these PDF run identities. Only
    complete, unchanged envelopes qualify; changed envelopes fail closed.
    """
    result = []
    for location in lines:
        index = location.get('line_index')
        if index is None or not 0 <= index < len(visual_lines):
            return ()
        line = visual_lines[index]
        start, end = location['line_char_start'], location['line_char_end']
        covered = 0
        for span in line.get('style_spans', []):
            a, b = max(start, span['start']), min(end, span['end'])
            if a >= b:
                continue
            if any(span.get(k) is None for k in ('font_id', 'first_run_index',
                    'first_glyph_index', 'last_run_index', 'last_glyph_index')):
                return ()
            covered += b - a
            result.append((location['page_id'], span.get('font_id'),
                           span.get('first_run_index'), span.get('first_glyph_index'),
                           span.get('last_run_index'), span.get('last_glyph_index'),
                           a - span['start'], b - span['start'],
                           line['text'][a:b]))
        if covered != end - start:
            return ()
    return tuple(result)


def pdf_occurrence_bridge(records, staging, canonical_root=None):
    """Return uniquely bound node→resolver occurrence IDs plus diagnostics."""
    matches, diagnostics = {}, []
    with sqlite3.connect(staging.resolve().as_uri() + '?mode=ro', uri=True) as db:
        for p in records:
            if p['source_kind'] != 'pdf':
                continue
            row = db.execute('SELECT source_faithful_sha256, structural_json '
                             'FROM pdf_article_analysis WHERE article_id=?',
                             (p['identity'],)).fetchone()
            valid = False
            candidates = []
            pages = {}
            if row:
                old = json.loads(row[1])
                valid = (row[0] == hashlib.sha256(
                    p['source']['source_faithful_text'].encode()).hexdigest()
                    and source_objects(old['source_objects']) ==
                    source_objects(p['source']['source_objects']))
                if valid:
                    candidates = [(ordinal, json.loads(body)) for ordinal, body in
                                  db.execute('SELECT ordinal,candidate_json FROM '
                                             'pdf_lexical_candidate WHERE article_id=? '
                                             'AND kind="citation" ORDER BY ordinal',
                                             (p['identity'],))]
                    if canonical_root is not None:
                        for obj in p['source']['source_objects']:
                            path = (canonical_root / obj['canonical_object']).resolve()
                            if not path.is_relative_to(canonical_root.resolve()):
                                raise ValueError('canonical object escapes source root')
                            body = path.read_bytes()
                            if hashlib.sha256(body).hexdigest() != obj['canonical_object_sha256']:
                                raise ValueError('canonical glyph object hash mismatch')
                            page = json.loads(gzip.decompress(body))
                            if page['page_id'] != obj['page_id']:
                                raise ValueError('canonical page identity mismatch')
                            pages[obj['page_id']] = page
            text = '\n'.join(l['text'] for l in p['source']['visual_lines'])
            for node in p['nodes']:
                if node['kind'] != 'citation':
                    continue
                start, end = node['start'], node['end']
                if not (isinstance(start, int) and isinstance(end, int)
                        and 0 <= start < end <= len(text)):
                    raise ValueError('invalid PDF citation source bounds')
                literal = text[start:end]
                key = source_key(node.get('source_lines', []))
                found = [ordinal for ordinal, c in candidates
                         if key and source_key(c.get('source_lines', [])) == key
                         and c['text'] == literal]
                if not found and valid:
                    anchor = glyph_envelope_key(node.get('source_lines', []),
                                                p['source']['visual_lines'])
                    found = [ordinal for ordinal, c in candidates
                             if anchor and c['text'] == literal and anchor ==
                             glyph_envelope_key(c.get('source_lines', []),
                                                old['visual_lines'])]
                if not found and valid and pages:
                    anchor = exact_glyph_key(node.get('source_lines', []),
                                             p['source']['visual_lines'], pages)
                    found = [ordinal for ordinal, c in candidates if anchor and anchor ==
                             exact_glyph_key(c.get('source_lines', []), old['visual_lines'], pages)]
                status = ('source_mismatch' if not valid else
                          'matched' if len(found) == 1 else
                          'ambiguous' if found else 'no_exact_occurrence')
                if len(found) == 1:
                    matches[(p['identity'], node['id'])] = f"{p['identity']}:{found[0]}"
                diagnostics.append(dict(entry_id=p['identity'], node_id=node['id'],
                                        literal=literal, status=status,
                                        resolver_literal=next((c['text'] for ordinal, c in candidates
                                                               if found == [ordinal]), None)))
    return matches, diagnostics


def validate_bibliography_export(records, entries, bibliography):
    """An accepted source-bound identity must survive the reader projection."""
    if len(records) != len(entries):
        raise ValueError('reader/projection entry count mismatch')
    by_identity = {entry['inspection_id']: entry for entry in entries}
    if len(by_identity) != len(entries) or set(by_identity) != {p['identity'] for p in records}:
        raise ValueError('reader/projection entry identity mismatch')
    for projection in records:
        entry = by_identity[projection['identity']]
        nodes = [n for n in projection['nodes'] if n['kind'] == 'citation']
        if len(nodes) != len(entry['citations']):
            raise ValueError('reader omitted a citation component')
        for node, citation in zip(nodes, entry['citations']):
            expected = bibliography.get((projection['identity'], node['id']),
                        bibliography.get(node.get('lexical_record_id'), []))
            if {a['id'] for a in expected} != set(citation['accepted_authority_ids']):
                raise ValueError('reader lost accepted bibliography resolution')
            text = (projection['source']['article_source_text'] if projection['source_kind'] == 'html'
                    else '\n'.join(l['text'] for l in projection['source']['visual_lines']))
            if citation['source_form'] != text[node['start']:node['end']]:
                raise ValueError('reader changed citation literal')


def bibliography_audit(records, entries, bibliography, diagnostics):
    """Count the displayed denominator; ownership is independent of identity.

    This is an export integrity audit, not an independent extraction review.
    A citation absent from the pinned PDF resolver snapshot is distinguished
    from an occurrence for which the resolver has not accepted an identity.
    """
    validate_bibliography_export(records, entries, bibliography)
    by_identity = {p['identity']: p for p in records}
    bridge = {(d['entry_id'], d['node_id']): d['status'] for d in diagnostics}
    counts, rows = {}, []
    for entry in entries:
        p = by_identity[entry['inspection_id']]
        kind = p['source_kind']
        tally = counts.setdefault(kind, Counter())
        source_text = (p['source']['article_source_text'] if kind == 'html' else
                       '\n'.join(l['text'] for l in p['source']['visual_lines']))
        if ''.join(s['text'] for s in entry['segments']) != source_text:
            raise ValueError('reader lost or duplicated source text')
        for node, citation in zip((n for n in p['nodes'] if n['kind'] == 'citation'), entry['citations']):
            resolved = bool(citation['accepted_authority_ids'])
            reviewed = citation['ownership'] == 'reviewed'
            tally['displayed'] += 1
            tally['bibliography_resolved' if resolved else 'bibliography_unresolved'] += 1
            tally['accepted_identity_lost'] += 0
            tally['resolved_relationship_unreviewed'] += int(resolved and not reviewed)
            tally['fully_resolved'] += int(resolved and reviewed)
            in_lex = any(n['kind'] == 'lexical_parallel'
                         and n['start'] <= node['start'] < node['end'] <= n['end']
                         for n in p['nodes'])
            if in_lex:
                tally['lex_displayed'] += 1
                tally['lex_bibliography_resolved' if resolved else 'lex_bibliography_unresolved'] += 1
            status = bridge.get((p['identity'], node['id']), 'html_lexical_record')
            if kind == 'pdf' and status != 'matched':
                tally['outside_exact_resolver_bridge'] += 1
            elif not resolved:
                tally['resolver_identity_unresolved'] += 1
            rows.append(dict(entry_id=p['identity'], source_kind=kind, node_id=node['id'],
                             literal=citation['source_form'], bridge_status=status,
                             lex_citation=in_lex,
                             authority_ids=citation['accepted_authority_ids'],
                             passage_relationship=citation['ownership']))
    return dict(counts={k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
                citations=rows, extraction_review='not inferred from export integrity')
