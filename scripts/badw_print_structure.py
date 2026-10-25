"""Conservative source-coordinate segmentation, separate from lexical acceptance.

An OCR number is not a visually verified homonym. A missing number is unknown,
never homonym one. Missing coordinates prevent a geometrically bounded extent.
"""
import re
import unicodedata

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
    if not features['leading_tibetan']:
        return False
    # The longest observed compound is eligible as a boundary, its shorter
    # prefixes are not. QA-only Tibetan headings remain possible boundaries.
    return (start.get('zone') == 'headword_line' or any(
        'displaced_prefix' not in evidence and
        'prefix_of_longer_observed_heading' not in evidence and
        ('loc_exact' in evidence or 'loc_spacing_candidate' in evidence)
        for evidence in start['matches'].values()))


def segment(line, start, rows, starts, height=None):
    """Stop at independent plausible headings, even when QA missed the heading.

    Retain line-order fallbacks as uncertain. Do not concatenate the next column
    or page without proof of continuation. Strong boundaries may over-segment;
    that costs recall rather than borrowing a neighbouring article's definition.
    """
    origin = box(start)
    stops = []
    for n, other in starts:
        if n <= line or not boundary(other):
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
    risks = []
    if not origin or missing:
        risks.append('uncertain_column_membership')
    if stop[1] != 'coordinate_heading':
        risks.append('unverified_article_extent')
    if not boundary(start):
        risks.append('weak_article_start_structure')
    # A top-of-page bare heading is furniture/continuation, not an article start.
    # Only geometric placement is used here; the repeated-heading check is separate.
    if origin and height and origin[1] < height*.09 and not re.search(
            r'[;,=]|\b(?:auch|ein|eine|das|der|die)\b', start['text']):
        risks.append('top_margin_bare_heading')
    return dict(lines=selected, next_anchor=stop[2], boundary_method=stop[1],
                risks=risks, homonym=heading_features(start['text']),
                continuation='not joined across page/column; unresolved if open')


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
