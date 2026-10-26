"""Conservative source-coordinate segmentation, separate from lexical acceptance.

An OCR number is not a visually verified homonym. A missing number is unknown,
never homonym one. Missing coordinates prevent a geometrically bounded extent.
"""
import re
import unicodedata
from statistics import median

TIB = r'[\u0f00-\u0fff]+'
LEADING = re.compile(r'^\s*(?:(\d{1,2}|[¹²³⁴⁵⁶⁷⁸⁹])\s*[.)]?\s*)?(' + TIB + r')\s*(.*)$')


def heading_features(text):
    match = LEADING.match(unicodedata.normalize('NFC', text))
    if not match:
        return dict(leading_tibetan=False, homonym=None, homonym_status='unread')
    number, tib, rest = match.groups()
    # Only a numeral BEFORE the leading Tibetan cluster is a possible homonym.
    # Numbers in the definition or sense list never enter this parser.
    return dict(leading_tibetan=True, tibetan=tib, transliteration_tail=rest,
                homonym=str(int(unicodedata.normalize('NFKC', number))) if number else None,
                homonym_status='ocr_prefix_number_candidate' if number else 'absence_not_verified')


def box(row):
    return (row.get('coordinate') or {}).get('box')


def same_column(a, b):
    """Substantial horizontal overlap; does not assume fixed width or central gutter."""
    if not a or not b:
        return None
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    return overlap >= .45 * min(a[2]-a[0], b[2]-b[0])


def boundary(start):
    features = heading_features(start['text'])
    if not features['leading_tibetan'] or not re.search(r'[\u0f40-\u0fbc]', features['tibetan']):
        return False
    # The longest observed compound is eligible as a boundary, its shorter
    # prefixes are not. QA-only Tibetan headings remain possible boundaries.
    return (start.get('zone') == 'headword_line' or any(
        'displaced_prefix' not in evidence and
        'prefix_of_longer_observed_heading' not in evidence and
        ('loc_exact' in evidence or 'loc_spacing_candidate' in evidence)
        for evidence in start['matches'].values()))


def heading_layout(rows, column):
    """Measure prose baselines per physical column, independently of HTML matches.

    No baseline is inferred from sparse columns. Measurements are observations,
    not heading labels: indentation alone also occurs in quotations and senses.
    """
    groups = {}
    for n, row in rows.items():
        b = box(row)
        col = column(b)
        if b and col is not None:
            groups.setdefault(col, []).append((b[1], b[0], n, row))
    result = {}
    for col, values in groups.items():
        values.sort(key=lambda v: (v[0], v[1], v[2]))
        prose = [box(r) for _, _, _, r in values
                 if not heading_features(r.get('line_text', r.get('text', '')))['leading_tibetan']
                 and len(r.get('line_text', r.get('text', ''))) >= 25]
        if len(prose) < 8:
            continue
        left = median(b[0] for b in prose)
        line_height = median(b[3] - b[1] for b in prose)
        if line_height <= 0:
            continue
        previous = None
        for _, _, n, row in values:
            b = box(row)
            result[n] = dict(column=col, prose_left=left, prose_height=line_height,
                             baseline_observations=len(prose),
                             outdent_heights=round((left-b[0])/line_height, 4),
                             height_ratio=round((b[3]-b[1])/line_height, 4),
                             preceding_gap_heights=None if previous is None else
                             round((b[1]-previous[3])/line_height, 4))
            previous = b
    return result


def source_heading(row, height=None, layout=None):
    """Source-only boundary hypothesis, never a lexical identity assertion.

    Tibetan digits/punctuation alone cannot head an article. A Tibetan spelling
    followed by a lower-case transliteration token is a possible boundary even
    without a catalogue match or coordinates. QA labels corroborate but do not
    establish an article start. Quotations and damaged readings remain possible
    false splits: the result limits evidence, rather than authorising ownership.
    """
    text = row.get('line_text', row.get('text', ''))
    features = heading_features(text)
    if not features['leading_tibetan']:
        return dict(status='not_heading', reasons=['no_leading_tibetan'])
    if not re.search(r'[\u0f40-\u0fbc]', features['tibetan']):
        return dict(status='not_heading', reasons=['tibetan_punctuation_or_number_only'])
    b = box(row)
    if b and height and b[1] < .09 * height:
        return dict(status='furniture_candidate', reasons=['top_margin'])
    tail = features['transliteration_tail']
    token = re.match(r"[’‘'ʼ]?[a-zāīūṛṝḷṅñṭḍṇśṣṃḥ][a-zāīūṛṝḷṅñṭḍṇśṣṃḥ’‘'ʼ]*", tail)
    reasons = []
    if token:
        reasons.append('leading_tibetan_and_transliteration_candidate')
    if row.get('zone') == 'headword_line':
        reasons.append('qa_heading_hypothesis')
    if layout and token:
        if layout['outdent_heights'] >= .5:
            reasons.append('measured_column_outdent')
        if layout['height_ratio'] >= 1.25:
            reasons.append('larger_than_column_prose')
        if (layout['preceding_gap_heights'] or 0) >= .5:
            reasons.append('measured_vertical_separation')
    return dict(status='possible_heading' if reasons else 'uncertain_tibetan_lead',
                reasons=reasons, coordinates='located' if b else 'unlocated',
                layout=layout,
                authority='source structural hypothesis; not independently verified')


def source_barriers(rows, starts, height=None, layout=None):
    """Include possible starts absent from C6 and the HTML candidate graph."""
    layout = layout or {}
    result = {n: dict(other, source_observation=source_heading(other, height, layout.get(n)))
              for n, other in starts if boundary(other)
              and source_heading(other, height, layout.get(n))['status'] != 'furniture_candidate'}
    for n, row in rows.items():
        observation = source_heading(row, height, layout.get(n))
        if observation['status'] == 'possible_heading':
            result.setdefault(n, dict(text=row['line_text'], coordinate=row.get('coordinate'),
                                      anchor=None, source_observation=observation))
    return sorted(result.items())


def segment(line, start, rows, starts, height=None):
    """Stop at independent plausible headings, even when QA missed the heading.

    Retain line-order fallbacks as uncertain. Do not concatenate the next column
    or page without proof of continuation. Strong boundaries may over-segment;
    that costs recall rather than borrowing a neighbouring article's definition.
    """
    origin = box(start)
    stops = []
    for n, other in source_barriers(rows, starts, height):
        if n <= line:
            continue
        other_box = box(other)
        if origin and other_box:
            if same_column(origin, other_box) and other_box[1] > origin[1]:
                stops.append((n, 'coordinate_heading', other['anchor']))
        else:
            stops.append((n, 'line_order_heading_uncertain', other['anchor']))
    stop = min(stops, default=(None, 'open_extent', None), key=lambda x:x[0])
    selected = []
    for n, row in sorted(rows.items()):
        if n < line or n > line+48 or (stop[0] is not None and n >= stop[0]):
            continue
        b = box(row)
        if origin and b and (not same_column(origin, b) or b[1] < origin[1]):
            continue
        selected.append((n, row['line_text']))
    missing = any(not box(rows[n]) for n, _ in selected)
    # A plausible geometric stop limits contamination; it does not independently
    # verify either lexical boundary or ownership of the intervening definition.
    risks = ['unverified_article_extent', 'unverified_definition_ownership']
    if not origin or missing:
        risks.append('uncertain_column_membership')
    if not boundary(start):
        risks.append('weak_article_start_structure')
    # A top-of-page bare heading is furniture/continuation, not an article start.
    # Only geometric placement is used here; the repeated-heading check is separate.
    if origin and height and origin[1] < height*.09 and not re.search(
            r'[;,=]|\b(?:auch|ein|eine|das|der|die)\b', start['text']):
        risks.append('top_margin_bare_heading')
    return dict(lines=selected, next_anchor=stop[2], next_line=stop[0], boundary_method=stop[1],
                risks=risks, homonym=heading_features(start['text']),
                continuation='not joined across page/column; unresolved if open')


def clip_at_unlocated_heading(selected, start_page, start_line, barriers, end_page=None):
    """Conservatively exclude text after an unlocated possible heading.

    QA order is not asserted to be physical reading order. If it introduces an
    unresolved boundary within a proposed physical interval, retaining that text
    as owned evidence would be unsafe. Return the removed boundary identities so
    callers can preserve the competing hypothesis and its exact source location.
    ``selected`` contains ((page, column, y, x, line), line, row) tuples.
    """
    threats = []
    for page, line in barriers:
        if page < start_page or (page == start_page and line <= start_line):
            continue
        if (end_page is not None and page < end_page) or any(
                key[0] > page or (key[0] == page and n >= line)
                for key, n, _ in selected):
            threats.append((page, line))
    if not threats:
        return selected, []
    page, line = min(threats)
    # Keep a prefix in physical order. Filtering individual QA line numbers can
    # reintroduce text from a later column whose QA numbers happen to be smaller.
    safe = []
    for item in selected:
        if item[0][0] > page or (item[0][0] == page and item[1] >= line):
            break
        safe.append(item)
    return safe, threats


def increasing_chain(options):
    """O(n log n) weighted chain; equal positions/ranks cannot align twice."""
    from itertools import groupby
    options = sorted(options)
    ranks = {rank:i+1 for i,rank in enumerate(sorted({o[1] for o in options}))}
    tree = [(0, -1)] * (len(ranks)+1)
    scores, parents = [], []
    def query(i):
        best = (0,-1)
        while i:
            best = max(best, tree[i]); i -= i & -i
        return best
    for _, group in groupby(enumerate(options), key=lambda x:x[1][0]):
        pending = []
        for j, (_, rank, weight, key) in group:
            score, parent = query(ranks[rank]-1)
            scores.append(score+weight); parents.append(parent)
            pending.append((ranks[rank], (score+weight,j)))
        for i, value in pending:
            while i < len(tree):
                tree[i] = max(tree[i], value); i += i & -i
    result = set()
    j = max(range(len(scores)), key=lambda i:(scores[i],i)) if scores else -1
    while j != -1:
        result.add(options[j][3]); j = parents[j]
    return result
