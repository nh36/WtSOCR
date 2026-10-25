"""Conservative, unattended HTML/print proposal engine (never an acceptance ledger).

QA zones, historical edges and embedded PDF OCR are fallible evidence. In particular,
page geometry is not a pagination crosswalk and an OCR heading is not a homonym
assertion. Only separately reviewed URL/checksum bindings remain link-eligible.
"""
from __future__ import annotations

import collections
import csv
import hashlib
import html
import itertools
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import unicodedata
import xml.etree.ElementTree as ET

from badw_html_print_alignment import FAMILIES, INPUTS, digest, object_digest
from badw_html_print_facsimiles import reviewed_records, REVIEWS
from badw_source_matcher import lemma_key, tibetan_key
from badw_print_crosswalk import tokens
from badw_print_structure import segment, increasing_chain

VERSION = 'html-print-engine-v4'
POLICY = 'All machine categories provisional; no automatic link promotion. Reviewed URL + HTML checksum bindings only.'


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    os.replace(temporary, path)


def json_map(path):
    """Stream a JSON object, holding one body plus a read buffer, not a 1GB map."""
    decoder = json.JSONDecoder()
    with Path(path).open() as stream:
        buffer = ''
        eof = False
        def fill():
            nonlocal buffer, eof
            chunk = stream.read(1024 * 1024)
            eof = not chunk
            buffer += chunk
        fill()
        buffer = buffer.lstrip()
        if not buffer.startswith('{'):
            raise ValueError('bodies must be a JSON object')
        buffer = buffer[1:]
        while True:
            buffer = buffer.lstrip()
            if not buffer and not eof:
                fill()
                continue
            if buffer.startswith('}'):
                if buffer[1:].strip() or stream.read().strip():
                    raise ValueError('trailing JSON data')
                return
            if buffer.startswith(','):
                buffer = buffer[1:].lstrip()
            try:
                key, end = decoder.raw_decode(buffer)
                offset = end
                while offset < len(buffer) and buffer[offset].isspace():
                    offset += 1
                if offset >= len(buffer):
                    raise json.JSONDecodeError('incomplete key', buffer, offset)
                if buffer[offset] != ':':
                    raise ValueError('invalid JSON map separator')
                offset += 1
                while offset < len(buffer) and buffer[offset].isspace():
                    offset += 1
                value, end = decoder.raw_decode(buffer, offset)
            except json.JSONDecodeError:
                if eof:
                    raise
                fill()
                continue
            yield key, value
            buffer = buffer[end:]


def loc_key(text):
    return lemma_key(text).casefold()


def packed(text):
    # Discovery only. Compact spellings/diacritics remain distinct in match evidence.
    return ''.join(c for c in loc_key(text) if c.isalpha() or c in '’')


def connection(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA cache_size=-32768')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS layouts(family TEXT,page INTEGER,body TEXT,PRIMARY KEY(family,page));
      CREATE TABLE IF NOT EXISTS reading_pages(family TEXT,page INTEGER,body TEXT,PRIMARY KEY(family,page));
      CREATE TABLE IF NOT EXISTS extents(aid TEXT PRIMARY KEY,body TEXT);
      CREATE TABLE IF NOT EXISTS reading_lines(family TEXT,page INTEGER,line INTEGER,position INTEGER,body TEXT,PRIMARY KEY(family,page,line));
      CREATE TABLE IF NOT EXISTS stages(name TEXT PRIMARY KEY, details TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS witnesses(sid TEXT PRIMARY KEY, body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS pages(family TEXT,page INTEGER,features TEXT NOT NULL,PRIMARY KEY(family,page));
      CREATE TABLE IF NOT EXISTS lines(family TEXT,page INTEGER,line INTEGER,body TEXT NOT NULL,PRIMARY KEY(family,page,line));
      CREATE TABLE IF NOT EXISTS anchors(aid TEXT PRIMARY KEY,body TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS edges(sid TEXT,aid TEXT,body TEXT NOT NULL,PRIMARY KEY(sid,aid));
      CREATE INDEX IF NOT EXISTS edges_aid ON edges(aid);
      CREATE TABLE IF NOT EXISTS starts(aid TEXT PRIMARY KEY,family TEXT,page INTEGER,line INTEGER,body TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS starts_page ON starts(family,page,line);
      CREATE TABLE IF NOT EXISTS proposals(sid TEXT,aid TEXT,score REAL,body TEXT NOT NULL,PRIMARY KEY(sid,aid));
      CREATE INDEX IF NOT EXISTS proposal_sid ON proposals(sid,score DESC,aid);
      CREATE INDEX IF NOT EXISTS proposal_aid ON proposals(aid);
    ''')
    return db


def completed(db, name):
    row = db.execute('SELECT details FROM stages WHERE name=?', (name,)).fetchone()
    return json.loads(row[0]) if row else None


def checkpoint(db, name, details):
    db.execute('INSERT INTO stages VALUES (?,?)', (name, json.dumps(details, sort_keys=True)))
    db.commit()  # Stage data and completion marker commit together or both roll back.


def catalogue_records(catalogue, expected=(29878, 18038)):
    rows = json.loads(Path(catalogue).read_text())['entries']
    records = {r['id']: r for r in rows}
    if len(records) != len(rows):
        raise ValueError('duplicate catalogue identity')
    html_count = sum(r['source_kind'] == 'html' for r in rows)
    if (len(rows), html_count) != expected:
        raise ValueError(f'incomplete catalogue: {(len(rows), html_count)}; expected {expected}')
    if any(r['source_kind'] not in ('html', 'pdf') for r in rows):
        raise ValueError('unknown catalogue source kind')
    return rows, records


def index_witnesses(db, bodies, catalogue, expected=(29878, 18038)):
    rows, records = catalogue_records(catalogue, expected)
    ranks = {r['id']: n for n, r in enumerate(rows)}
    seen = set()
    count = 0
    for sid, body in json_map(bodies):
        if body['source_kind'] != 'html':
            raise ValueError('non-HTML body in HTML input')
        if sid != body['inspection_id']:
            raise ValueError('body identity mismatch')
        record = records.get(body['id'])
        if record is None or record['source_kind'] != 'html':
            raise ValueError('HTML body absent from catalogue')
        if body['id'] in seen:
            raise ValueError('duplicate HTML body identity')
        seen.add(body['id'])
        if any(record.get(k) != body.get(k) for k in ('headword', 'homonym')):
            raise ValueError('catalogue/body lexical identity mismatch')
        source = body['sources'][0]
        if (sid != 'badw:' + body['source_url'] or source['url'] != body['source_url'] or
                not re.fullmatch(r'[0-9a-f]{64}', source['sha256'])):
            raise ValueError('invalid HTML source identity/checksum')
        definitions = [c for c in body['components'] if c['type'] == 'definition']
        citations = [c for c in body['components'] if 'citation' in c['type']]
        text = '\n'.join(c['source_form'] for c in definitions)
        record = dict(sid=sid, id=body['id'], source_url=body['source_url'],
            html_sha256=body['sources'][0]['sha256'], headword=body['headword'],
            homonym=body.get('homonym'), order=ranks.get(body['id']),
            definition=text, definition_components=[dict(id=c['id'], sha256=object_digest(c)) for c in definitions],
            citations=[c['source_form'] for c in citations])
        db.execute('INSERT INTO witnesses VALUES (?,?)', (sid, json.dumps(record, ensure_ascii=False)))
        count += 1
    if seen != {r['id'] for r in rows if r['source_kind'] == 'html'}:
        raise ValueError('incomplete HTML body corpus')
    return dict(html_witnesses=count, catalogue_ranks=len(ranks))


def pdf_layout(pdf, xml):
    """Use Poppler's source-bound embedded OCR coordinates, not guessed QA boxes."""
    temporary = xml.with_suffix('.tmp')
    subprocess.run(['pdftotext', '-bbox-layout', str(pdf), str(temporary)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    os.replace(temporary, xml)
    for _, element in ET.iterparse(xml, events=['end']):
        if element.tag.endswith('}page'):
            lines = []
            for node in element.iter():
                if node.tag.endswith('}line'):
                    words = [''.join(w.itertext()) for w in node if w.tag.endswith('}word')]
                    lines.append(dict(text=' '.join(words), box=[float(node.get(k)) for k in ('xMin','yMin','xMax','yMax')]))
            yield lines
            element.clear()


def locate_line(text, layout, inverted):
    wanted = tokens(text)
    votes = collections.Counter(i for t in wanted for i in inverted.get(t, []))
    ranked = sorted(((len(wanted & tokens(layout[i]['text'])) / max(1, len(wanted | tokens(layout[i]['text']))), i)
                     for i in votes), reverse=True)
    if not ranked:
        return None
    score, i = ranked[0]
    # Position is usable only for unique, substantial OCR agreement. Otherwise absent.
    if score < .45 or (len(ranked) > 1 and score - ranked[1][0] < .15):
        return None
    return dict(box=layout[i]['box'], embedded_text=layout[i]['text'], token_jaccard=round(score, 6),
                method='unique embedded-OCR line token agreement; not visual verification')


def index_family(db, root, family, registry, output):
    from pypdf import PdfReader
    source = registry[FAMILIES[family]]
    pdf = root / source['filename']
    reader = PdfReader(pdf)
    qa = root / f'release/current/qa/{family}/{family}_line_zones.tsv'
    grouped = itertools.groupby(csv.DictReader(qa.open(), delimiter='\t'), key=lambda r: int(r['page']))
    qa_pages = iter(grouped)
    current = next(qa_pages, (None, []))
    rows_count = 0
    for number, layout in enumerate(pdf_layout(pdf, output / (family + '.bbox.xml')), 1):
        db.execute('INSERT INTO layouts VALUES (?,?,?)',(family,number,json.dumps(layout,sort_keys=True)))
        page = reader.pages[number-1]
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        features = dict(source=FAMILIES[family], source_sha256=source['sha256'], physical_page=number,
            mediabox=list(map(float, page.mediabox)), rotation=page.rotation,
            width=width, height=height, landscape=width > height, embedded_ocr_lines=len(layout),
            printed_folio=None, crop=None, geometry_status='unreviewed; no automatic spread split')
        inv = collections.defaultdict(list)
        for i, row in enumerate(layout):
            for token in tokens(row['text']):
                inv[token].append(i)
        if current[0] == number:
            for row in current[1]:
                evidence = dict(row, coordinate=locate_line(row['line_text'], layout, inv))
                db.execute('INSERT INTO lines VALUES (?,?,?,?)', (family, number, int(row['line']), json.dumps(evidence, ensure_ascii=False)))
                rows_count += 1
            current = next(qa_pages, (None, []))
        db.execute('INSERT INTO pages VALUES (?,?,?)', (family, number, json.dumps(features, sort_keys=True)))
    if current[0] is not None or len(reader.pages) != number:
        raise ValueError('QA or extracted PDF page outside registered physical range')
    return dict(physical_pages=number, qa_lines=rows_count)


def index_history(db, root, inputs=None):
    inputs = inputs if inputs is not None else {k: root / v for k, v in INPUTS.items()}
    if not inputs:
        return dict(edges=0, anchors=0, status='historical corroboration not supplied')
    for line in Path(inputs['anchors']).open():
        row = json.loads(line)
        db.execute('INSERT INTO anchors VALUES (?,?)', (row['anchor_id'], line))
    count = 0
    for line in Path(inputs['edges']).open():
        row = json.loads(line)
        db.execute('INSERT OR IGNORE INTO edges VALUES (?,?,?)', (row['source_id'], row['local_anchor_id'], line))
        count += 1
    return dict(edges=count, anchors=db.execute('SELECT count(*) FROM anchors').fetchone()[0])


def lexical_indexes(witnesses):
    loc, tib, compact = (collections.defaultdict(set) for _ in range(3))
    for sid, w in witnesses.items():
        loc[loc_key(w['headword']['loc'])].add(sid)
        compact[packed(w['headword']['loc'])].add(sid)
        if tibetan_key(w['headword'].get('tibetan', '')):
            tib[tibetan_key(w['headword']['tibetan'])].add(sid)
    return loc, tib, compact


def discover_line(row, indexes):
    """Hypotheses from ALL QA lines, independent of C6 and QA zone labels.

    No OCR syllable repair. Compact LoC and displaced prefixes produce flagged
    candidates, never an assertion that a heading has been read correctly.
    """
    loc, tib, compact = indexes
    text = unicodedata.normalize('NFC', row['line_text'])
    observed = collections.defaultdict(set)
    exact_keys = {}
    leading = re.match(r'^[\s\d¹²³⁴⁵⁶⁷⁸⁹⁰.,()]*([\u0f00-\u0fff]+)', text)
    if leading:
        for sid in tib.get(tibetan_key(leading[1]), []):
            observed[sid].add('leading_tibetan_exact')
        text = text[leading.end():].lstrip()
    parts = text.split()
    for offset in range(min(3, len(parts))):
        for length in range(1, min(12, len(parts)-offset)+1):
            phrase = ' '.join(parts[offset:offset+length]).strip('.,;:()"“”')
            key = loc_key(phrase)
            exact = loc.get(key, set())
            if exact and offset == 0:
                exact_keys[key] = exact
            collapsed = compact.get(packed(phrase), set()) if length <= 8 else set()
            for sid in exact | collapsed:
                observed[sid].add('loc_exact' if sid in exact else 'loc_spacing_candidate')
                if offset:
                    observed[sid].add('displaced_prefix')
    # A shorter matching prefix is not the observed compound heading. Keep it as
    # an alternative, but explicitly exclude this class from mechanical support.
    matched_keys = list(exact_keys.items())
    for short, short_ids in matched_keys:
        if any(long.startswith(short + ' ') for long, _ in matched_keys):
            for sid in short_ids:
                observed[sid].add('prefix_of_longer_observed_heading')
    return {sid: sorted(evidence) for sid, evidence in observed.items()}


def discover(db, witnesses):
    indexes = lexical_indexes(witnesses)
    c6 = {r[0] for r in db.execute('SELECT aid FROM anchors')}
    count = missing = 0
    for family, page, line, body in db.execute('SELECT * FROM lines ORDER BY family,page,line'):
        row = json.loads(body)
        matches = discover_line(row, indexes)
        # QA-only headings without an HTML lexical candidate are retained as boundary hypotheses.
        if not matches and row['zone'] != 'headword_line':
            continue
        aid = f'{family}:{page}:{line}'
        record = dict(anchor=aid, qa_sha256=object_digest({k:v for k,v in row.items() if k != 'coordinate'}),
            text=row['line_text'], zone=row['zone'], coordinate=row['coordinate'],
            historical_c6=aid in c6, matches=matches,
            status='article-start hypothesis; not a verified boundary')
        db.execute('INSERT INTO starts VALUES (?,?,?,?,?)', (aid, family, page, line, json.dumps(record, ensure_ascii=False)))
        count += 1
        missing += aid not in c6
    return dict(candidate_starts=count, absent_from_c6=missing)


def monotone_chain(options):
    """Maximum-weight increasing chain of (position, catalogue rank, weight, key).

    A page-local sequence consistency check, not an acceptance rule. Equal positions
    or ranks cannot both be included. Quadratic DP is bounded by one physical page.
    """
    options = sorted(options)
    best, previous = [], []
    for i, (position, rank, weight, _) in enumerate(options):
        choices = [(best[j], j) for j in range(i) if options[j][0] < position and options[j][1] < rank]
        value, parent = max(choices, default=(0, -1))
        best.append(value + weight)
        previous.append(parent)
    chosen = set()
    index = max(range(len(best)), key=lambda i: best[i]) if best else -1
    while index != -1:
        chosen.add(options[index][3])
        index = previous[index]
    return chosen


def evidence_score(witness, article, frequencies, total):
    definition_tokens = tokens(witness['definition'])
    printed_tokens = tokens(article)
    shared = definition_tokens & printed_tokens
    rare = sorted(t for t in shared if frequencies[t] <= max(2, total // 400))
    weight = lambda t: math.log((total+1)/(frequencies[t]+1)) + 1
    numerator = sum(weight(t) for t in shared)
    denominator = sum(weight(t) for t in definition_tokens)
    citations = sorted(t for t in tokens(' '.join(witness['citations'])) & printed_tokens if frequencies[t] <= max(2, total//400))
    return dict(definition_shared_tokens=sorted(shared), rare_definition_tokens=rare,
                definition_weighted_recall=round(numerator / denominator, 6) if denominator else 0,
                citation_tokens=citations)


def match_page(db, family, page, witnesses, frequencies):
    rows = {line: json.loads(body) for line, body in db.execute('SELECT line,body FROM lines WHERE family=? AND page=? ORDER BY line', (family,page))}
    starts = [(line, json.loads(body)) for line, body in db.execute('SELECT line,body FROM starts WHERE family=? AND page=? ORDER BY line', (family,page))]
    proposals = []
    historical = {(sid,aid) for sid,aid in db.execute(
        'SELECT e.sid,e.aid FROM edges e JOIN starts s ON e.aid=s.aid WHERE s.family=? AND s.page=?', (family,page))}
    for line, start in starts:
        box = (start.get('coordinate') or {}).get('box')
        geometry = db.execute('SELECT features FROM pages WHERE family=? AND page=?', (family,page)).fetchone()
        geometry = json.loads(geometry[0]) if geometry else {}
        extent = segment(line, start, rows, starts, geometry.get('height'))
        reconstructed_row=db.execute('SELECT body FROM extents WHERE aid=?',(start['anchor'],)).fetchone()
        reconstructed=json.loads(reconstructed_row[0]) if reconstructed_row else {}
        # Only complete coordinate coverage permits replacing the local fallback.
        refs=reconstructed.get('refs',[]) if reconstructed.get('status')=='coordinate_bounded' else []
        if refs:
            extent['lines']=[((p,n),json.loads(db.execute('SELECT body FROM lines WHERE family=? AND page=? AND line=?',(family,p,n)).fetchone()[0])['line_text']) for p,n in refs]
            extent['risks']=[r for r in extent['risks'] if r not in ('uncertain_column_membership','unverified_article_extent')]
            extent['boundary_method']='source_coordinate_interval'
        selected = extent['lines']
        for sid, heading_evidence in start['matches'].items():
            witness = witnesses[sid]
            # A repeated spelling farther down the page is a competing article
            # beginning. Never borrow its definition to support the earlier header.
            repeat = next((n for n,s in starts if n > line and sid in s['matches']), None)
            own_selected = [(n,t) for n,t in selected if refs or repeat is None or n < repeat]
            own_article = '\n'.join(t for _,t in own_selected)
            proof = evidence_score(witness, own_article, frequencies, len(witnesses))
            hom=reconstructed.get('homonym_observation',dict(status='unread',number=None))
            risks = list(extent['risks'])
            risks.extend(homonym_risks(hom, witness['homonym'], extent['homonym']['homonym']))
            if 'prefix_of_longer_observed_heading' in heading_evidence:
                risks.append('neighbouring_compound_heading')
            if repeat is not None:
                risks.append('same_spelling_heading_repeated_on_page')
            if not box:
                risks.append('no_unique_embedded_ocr_coordinates')
            if 'displaced_prefix' in heading_evidence:
                risks.append('displaced_or_incidental_heading')
            if 'loc_spacing_candidate' in heading_evidence and 'loc_exact' not in heading_evidence:
                risks.append('loc_spacing_or_ocr_difference')
            if not proof['rare_definition_tokens']:
                risks.append('generic_or_absent_definition_evidence')
            score = (4 * ('leading_tibetan_exact' in heading_evidence) +
                     3 * ('loc_exact' in heading_evidence) +
                     min(6, len(proof['rare_definition_tokens'])) +
                     min(2, len(proof['citation_tokens'])) + 2 * proof['definition_weighted_recall'])
            if repeat is not None:
                score -= 6  # competing later start: conservative ranking penalty, not header adjudication
            if 'neighbouring_compound_heading' in risks:
                score -= 6
            proposal = dict(sid=sid, anchor=start['anchor'], family=family, physical_page=page,
                line=line, heading_text=start['text'], heading_evidence=heading_evidence,
                historical_c6=start['historical_c6'], historical_identity_edge=(sid,start['anchor']) in historical,
                independent_embedded_ocr_agreement=bool(start['coordinate']), coordinate=start['coordinate'],
                evidence_lines=[n for n,_ in own_selected], printed_evidence=own_article,
                evidence_sha256=object_digest(own_selected), html_sha256=witness['html_sha256'],
                definition_component_bindings=witness['definition_components'], definition_evidence=proof,
                score=round(score,6), risks=risks, sequence_consistent=False,
                segmentation={k:v for k,v in extent.items() if k != 'lines'},
                reconstruction=reconstructed,
                source_line_hash=start.get('qa_sha256'),
                lexical_identity_status='provisional; not independently validated')
            proposals.append(proposal)
    # Same lexical witness appearing as a bare heading before its substantive article
    # is a header/continuation risk even when C6 calls it a headword.
    for proposal in proposals:
        alternatives = [p for p in proposals if p['sid']==proposal['sid'] and p['line']!=proposal['line']]
        if (not proposal['definition_evidence']['rare_definition_tokens'] and
            any(p['definition_evidence']['rare_definition_tokens'] for p in alternatives)):
            proposal['risks'].append('header_or_continuation_with_better_article_on_page')
    options = []
    for p in proposals:
        rank = witnesses[p['sid']]['order']
        if rank is not None:
            # Layout x groups keep columns from being deliberately interleaved.
            box = (p['coordinate'] or {}).get('box')
            position = (round(box[0]/120), box[1]) if box else (0, p['line'])
            options.append((position, rank, p['score'], (p['sid'],p['anchor'])))
    chosen = monotone_chain(options)
    for p in proposals:
        p['sequence_consistent'] = (p['sid'],p['anchor']) in chosen
        db.execute('INSERT INTO proposals VALUES (?,?,?,?)', (p['sid'],p['anchor'],p['score'],json.dumps(p,ensure_ascii=False,sort_keys=True)))
    return len(proposals)


def baseline_category(proposals):
    if not proposals:
        return 'unresolved', ['no lexical article-start candidate']
    top = proposals[0]
    proof = top['definition_evidence']
    dual = {'loc_exact','leading_tibetan_exact'} <= set(top['heading_evidence'])
    margin = top['score'] - proposals[1]['score'] if len(proposals)>1 else top['score']
    # A testable hypothesis class. This is deliberately NOT a scholarly acceptance.
    if (dual and len(proof['rare_definition_tokens']) >= 2 and margin >= 2 and
        top['sequence_consistent'] and not any(r in top['risks'] for r in
            ('header_or_continuation_with_better_article_on_page','neighbouring_compound_heading',
             'same_spelling_heading_repeated_on_page','displaced_or_incidental_heading'))):
        return 'mechanically_supported_provisional', ['dual heading, distinctive definition, unique score margin and page sequence; uncalibrated']
    return 'review_required', ['OCR/identity/boundary or competing-candidate uncertainty']


def homonym_risks(observation, editorial_number, fallback_number=None):
    """Dependent OCR observations are not independently verified print readings."""
    status = observation['status']
    number = observation.get('number')
    if status == 'verified_printed_number':
        return ['verified_printed_homonym_conflict'] if number != str(editorial_number) else []
    if status == 'conflicting_ocr_number':
        return ['homonym_ocr_sources_disagree']
    if number and number != str(editorial_number):
        return ['homonym_agreeing_ocr_conflicts_html' if status == 'explicit_number_ocr_agreement'
                else 'homonym_single_ocr_conflicts_html']
    if fallback_number and fallback_number != str(editorial_number):
        return ['homonym_single_ocr_conflicts_html']
    if status == 'explicit_number_single_ocr':
        return ['printed_numeral_requires_corroboration']
    return ['printed_homonym_unread'] if status == 'unread' else []


def category(proposals):
    if proposals and 'verified_printed_homonym_conflict' in proposals[0]['risks']:
        return 'contradictory_identity', ['printed numeral contradicts editorial homonym; identity excluded']
    previous, reasons = baseline_category(proposals)
    if previous != 'mechanically_supported_provisional':
        return previous, reasons
    risks = set(proposals[0]['risks'])
    requirements = []
    if any(r.startswith('homonym_') for r in risks):
        requirements.append('tentative OCR homonym disagreement; requires source assessment')
    if 'printed_homonym_unread' in risks:
        requirements.append('printed homonym unresolved')
    structural = {'unverified_article_extent', 'uncertain_column_membership',
                  'weak_article_start_structure', 'top_margin_bare_heading',
                  'no_unique_embedded_ocr_coordinates'}
    if structural & risks:
        requirements.append('article extent or coordinates unresolved')
    return 'mechanically_supported_provisional', reasons + requirements


def publication_eligibility(proposal):
    """No machine evidence class has a validated publication policy.

    Deliberately independent of confidence/result metadata. Only the existing
    checksum-bound reviewed certificates can attach links in write_results.
    """
    return dict(eligible=False, requirements=[
        'independently validated lexical/homonym identity',
        'secure printed folio and single-page crop',
        'approved publication policy'])


def section_sequences(db, witnesses, width=3):
    """Disjoint three-physical-page chains, alongside the page-local baseline.

    No forced insertions or score boost. Unknown coordinates remain an uncertainty;
    a monotone path does not prove reading order or lexical identity.
    """
    from itertools import groupby
    total = changes = 0
    keys = db.execute('SELECT family,page FROM pages ORDER BY family,page').fetchall()
    for family, group in groupby(keys, key=lambda x:x[0]):
        pages = [p for _,p in group]
        for offset in range(0,len(pages),width):
            section = pages[offset:offset+width]
            rows = db.execute('SELECT p.sid,p.aid,p.body FROM proposals p JOIN starts s ON p.aid=s.aid WHERE s.family=? AND s.page BETWEEN ? AND ? ORDER BY s.page,s.line,p.sid',
                              (family,section[0],section[-1])).fetchall()
            options = []
            decoded = []
            for sid,aid,body in rows:
                p = json.loads(body); decoded.append((sid,aid,p))
                rank = witnesses[sid]['order']
                b = (p['coordinate'] or {}).get('box')
                position = (p['physical_page'],round(b[0]/120),b[1]) if b else (p['physical_page'],0,p['line'])
                if rank is not None:
                    options.append((position,rank,max(0,p['score']),(sid,aid)))
            chosen = increasing_chain(options)
            for sid,aid,p in decoded:
                p['section_sequence_consistent'] = (sid,aid) in chosen
                p['sequence_section'] = [family,section[0],section[-1]]
                p['section_sequence_role'] = 'diagnostic only; no ranking or acceptance boost'
                changes += p['section_sequence_consistent'] != p['sequence_consistent']
                total += 1
                db.execute('UPDATE proposals SET body=? WHERE sid=? AND aid=?',
                           (json.dumps(p,ensure_ascii=False,sort_keys=True),sid,aid))
    return dict(proposals=total,changed_sequence_membership=changes,width_physical_pages=width)


def write_results(db, output, root, witnesses, identity):
    reviewed, _ = reviewed_records(REVIEWS)
    accepted = {(r['source_url'],r['html_sha256']):r for r in reviewed['witnesses']}
    pages = {(FAMILIES_INV[row['source']], row['physical_page']): [] for row in reviewed['pages'].values()}
    for key, row in reviewed['pages'].items():
        pages[FAMILIES_INV[row['source']],row['physical_page']].append(dict(key=key, **row))
    cert = json.loads((root/'data/badw_html_print_alignment.json').read_text())
    reviewed_assertions = {a['source_id']:(page,a) for page in cert['pages'] for a in page['accepted']}
    counts, by_family = collections.Counter(), collections.defaultdict(collections.Counter)
    validation = []
    temporary = output/'witnesses.jsonl.tmp'
    sample_pool = []
    with temporary.open('w') as stream:
        for sid, witness in sorted(witnesses.items()):
            proposals = [json.loads(r[0]) for r in db.execute('SELECT body FROM proposals WHERE sid=? ORDER BY score DESC,aid', (sid,))]
            classification, reasons = category(proposals)
            attached = accepted.get((witness['source_url'],witness['html_sha256']))
            for p in proposals:
                p['reviewed_page_geometry'] = pages.get((p['family'],p['physical_page']), [])
            row = dict(source_id=sid, source_url=witness['source_url'], html_sha256=witness['html_sha256'],
                editorial_headword=witness['headword'], editorial_homonym=witness['homonym'],
                editorial_definition=witness['definition'], editorial_citations=witness['citations'],
                result_category=classification, reasons=reasons,
                baseline_feature_category=baseline_category(proposals)[0], proposed=proposals[:10],
                local_ranking=sorted([dict(anchor=p['anchor'], score=p.get('sequence_ranking',{}).get('local_score',p['score'])) for p in proposals], key=lambda p:(-p['score'],p['anchor'])),
                sequence_ranking=[dict(anchor=p['anchor'], score=p['score'], evidence=p.get('sequence_ranking')) for p in proposals],
                machine_publication=publication_eligibility(proposals[0] if proposals else None),
                candidate_count=len(proposals), omitted_candidates=max(0,len(proposals)-10),
                eligible_for_original_print_link=attached is not None,
                eligibility_basis='existing reviewed checksum-bound certificate' if attached else 'none; machine proposal is provisional',
                reviewed_page=attached['page'] if attached else None,
                input_identity=identity)
            stream.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
            counts[classification] += 1
            counts['reviewed_attachable'] += bool(attached)
            if proposals:
                by_family[proposals[0]['family']][classification] += 1
            if baseline_category(proposals)[0]=='mechanically_supported_provisional':
                sample_pool.append((hashlib.sha256(('20261025:'+sid).encode()).hexdigest(),row))
            if sid in reviewed_assertions:
                page, assertion = reviewed_assertions[sid]
                expected = assertion['anchor']
                top = proposals[0] if proposals else None
                validation.append(dict(source_id=sid, expected_anchor=expected,
                    expected_family=page['family'], expected_page=page['physical_page'],
                    top_anchor=top['anchor'] if top else None, category=classification,
                    correct_start=bool(top and top['anchor']==expected),
                    correct_page=bool(top and top['family']==page['family'] and top['physical_page']==page['physical_page']),
                    expected_start_detected=any(p['anchor']==expected for p in proposals),
                    role='retrospective reviewed benchmark; not independent random precision estimate'))
    os.replace(temporary,output/'witnesses.jsonl')
    sample = [row for _,row in sorted(sample_pool)[:40]]
    atomic_json(output/'validation.json', dict(reviewed=validation,
        interpretation='Reviewed benchmark measures recovery, not full-corpus precision; all machine classes remain provisional.',
        deterministic_sample_seed='20261025', sample=[dict(source_id=r['source_id'],anchor=r['proposed'][0]['anchor']) for r in sample]))
    report = output/'report'
    report.mkdir(exist_ok=True)
    write_review(report, sample)
    summary = dict(version=VERSION, policy=POLICY, input_identity=identity,
        reconstruction=completed(db,'reconstruction'),
        sequence_ranking=completed(db,'sequence-rerank'),
        html_witnesses=len(witnesses), counts=dict(counts), by_proposed_scan_family=dict(by_family),
        physical_pages=db.execute('SELECT count(*) FROM pages').fetchone()[0],
        qa_lines=db.execute('SELECT count(*) FROM lines').fetchone()[0],
        candidate_starts=db.execute('SELECT count(*) FROM starts').fetchone()[0],
        absent_from_c6=sum(not json.loads(r[0])['historical_c6'] for r in db.execute('SELECT body FROM starts')),
        proposals=db.execute('SELECT count(*) FROM proposals').fetchone()[0],
        reviewed_benchmark=dict(n=len(validation), exact_start=sum(r['correct_start'] for r in validation),
            correct_physical_page=sum(r['correct_page'] for r in validation), detected=sum(r['expected_start_detected'] for r in validation)),
        limitations=['No new acceptance or crop/pagination extrapolation.',
            'QA columns and OCR-only heading/homonym readings can be ambiguous; article spans are provisional.',
            'Unreviewed pages have no securely established printed folio, spread side or gutter geometry.',
            'Independent random facsimile validation required before category promotion.'],
        artifacts={p.name:digest(p) for p in (output/'witnesses.jsonl',output/'validation.json',output/'report/review.html')})
    atomic_json(output/'manifest.json', summary)
    return summary


FAMILIES_INV = {v:k for k,v in FAMILIES.items()}


def write_review(output, sample):
    content = ['<!doctype html><meta charset="utf-8"><title>Provisional alignment review</title>',
        '<style>body{font:16px system-ui;max-width:1000px;margin:auto}article{border-top:2px solid #888;padding:1em}pre{white-space:pre-wrap}img{max-width:100%}</style>',
        '<h1>Deterministic random sample — not accepted links</h1>',
        '<p>Private local research only. No complete original PDFs are served. Unreviewed crop geometry and folios are not inferred.</p>']
    for n,row in enumerate(sample):
        p=row['proposed'][0]
        content += [f'<article id="case-{n}"><h2>{html.escape(row["editorial_headword"]["loc"])}</h2>',
            f'<p>{html.escape(p["anchor"])}; {html.escape(row["source_url"])}</p>',
            f'<p>Heading hypothesis: {html.escape(p["heading_text"])}</p>',
            f'<p>Review reasons: {html.escape(", ".join(p["risks"]))}</p>',
            '<h3>Printed OCR context (provisional article extent)</h3><pre>'+html.escape(p['printed_evidence'])+'</pre>',
            '<h3>Editorial definition</h3><pre>'+html.escape(row['editorial_definition'])+'</pre>',
            '<pre>'+html.escape(json.dumps(p['definition_evidence'],ensure_ascii=False,indent=2))+'</pre>',
            f'<p>Alternatives: {html.escape(", ".join(q["anchor"] for q in row["proposed"][1:]))}</p>',
            f'<p><a href="images/{n:02d}.png">Source-page review image (if rendered locally)</a></p></article>']
    temporary=output/'review.html.tmp'
    temporary.write_text('\n'.join(content)+'\n')
    os.replace(temporary,output/'review.html')
