"""Exact grammatical templates for individually reviewed reciprocal evidence.

Descriptions are syntax gates, never automatic homonym adjudication. Historical
basis names and their geometry policies remain part of the annotation contract.
"""
import re

# Single, undamaged transliteration words; neither prose nor arbitrary arrows
# can be consumed as a preceding paradigm member. Productions match the whole
# introduction and remain subordinate to an individually source-bound review.
PARADIGM_WORD = r"’?[^\W\d_]{1,40}(?:’[^\W\d_]{1,40})?"
COMPOUND_FUTURE = (
    r'(?:auch ' + PARADIGM_WORD + r'(?:, ' + PARADIGM_WORD + r'){0,1}, )?'
    r'pf\. [↑↓]' + PARADIGM_WORD + r' fut\.'
)

PERFECT = 'reviewed_printed_reciprocal_perfect'
FUTURE = PERFECT + '_future'
IMPERATIVE = PERFECT + '_imperative'
QUALIFIED = 'reviewed_printed_qualified_reciprocal_perfect'
GRAMMATICAL = 'reviewed_printed_grammatical_reciprocal'

# (exact source introduction, exact complementary destination introduction).
# Whitespace, punctuation and the historical wrapped zu spelling are literal.
PATTERNS = {
    PERFECT: dict(pairs=(('pf. zu', 'pf. '), ('pf. bzw. imp. zu', 'pf. ')),
                  alternate=('auch {alternate}, pf. zu', 'pf. '), offsets=(0, 2)),
    FUTURE: dict(pairs=(('pf. und fut. zu', 'pf. und fut. '),
                        ('pf. und fut.', 'pf. und fut. zu ')), offsets=(0, 2)),
    IMPERATIVE: dict(pairs=(('pf. und imp. zu', 'pf. und imp. '),
                            ('pf. und imp.', 'pf. und imp. zu')),
                     alternate=('alttib. auch {alternate} pf. und imp. zu', 'pf. und imp. '), offsets=(0,)),
    QUALIFIED: dict(pairs=(('pf. zu', 'pf. '),), offsets=(0,), qualified=True),
    'perfect_to_paradigm': dict(pairs=(('pf. zu', 'pf. '),),
                               alternate=('auch {alternate} pf. zu', 'pf.'), offsets=(0,)),
    'paradigm_to_perfect': dict(pairs=(('pf.', 'pf. zu '), ('pf.', 'pf. bzw. imp. zu ')),
                               alternate=('auch {alternate} pf.', 'pf. zu '), offsets=(0,)),
    'future_to_paradigm': dict(pairs=(('fut. zu', 'fut. '), ('fut. zu', 'fut.')), offsets=(0,)),
    'paradigm_to_future': dict(pairs=(('fut.', 'fut. zu '),), offsets=(0,),
                               productions=((COMPOUND_FUTURE, 'fut. zu '),)),
}
BASES = frozenset((PERFECT, FUTURE, IMPERATIVE, QUALIFIED, GRAMMATICAL))
METHODS = {basis: basis.replace('reviewed_printed_', 'reviewed_exact_') for basis in BASES}


def description(claim):
    basis = claim.get('basis', PERFECT)
    key = claim.get('grammatical_pattern') if basis == GRAMMATICAL else basis
    if basis not in BASES or (basis != GRAMMATICAL and 'grammatical_pattern' in claim):
        return None
    if basis == GRAMMATICAL and key in BASES:
        return None
    return PATTERNS.get(key)


def pairs(claim):
    desc = description(claim)
    if desc is None:
        return ()
    if 'source_alternate_headword' not in claim:
        return desc['pairs']
    alternate = claim['source_alternate_headword']
    template = desc.get('alternate')
    if (template is None or not isinstance(alternate, str) or not 0 < len(alternate) <= 40 or
            re.fullmatch(r"[^\W\d_]+(?:[ ’][^\W\d_]+)*", alternate) is None):
        return ()
    return ((template[0].format(alternate=alternate), template[1]),)


def destinations(claim, source_introduction):
    desc = description(claim)
    if desc is None or not isinstance(source_introduction, str):
        return set()
    result = {destination for source, destination in pairs(claim)
              if source_introduction == source}
    if 'source_alternate_headword' not in claim and len(source_introduction) <= 120:
        result.update(destination for production, destination in desc.get('productions', ())
                      if re.fullmatch(production, source_introduction))
    return result


def introduction(claim, text, start):
    return bool(destinations(claim, text[:start].strip()))


def passage_matches(passage, source_headword, source_marker, *, basis=PERFECT,
                    source_introduction=None, source_homonym=None, grammatical_pattern=None):
    claim = dict(basis=basis)
    if grammatical_pattern is not None:
        claim['grammatical_pattern'] = grammatical_pattern
    desc = description(claim)
    offset = passage.get('run_start_offset', 0)
    literal = passage.get('literal', '')
    numbered = (basis == GRAMMATICAL and offset == 3 and
                literal.startswith('.  ') and isinstance(passage.get('numbered_sense'), dict) and
                passage['numbered_sense'].get('label') == '1.')
    if (desc is None or type(offset) is not int or (offset not in desc['offsets'] and not numbered) or
            (offset == 2 and not literal.startswith(', ')) or
            source_marker not in ('↑', '↓') or not source_headword):
        return False
    opposite = {'↑': '↓', '↓': '↑'}[source_marker]
    suffix = opposite + source_headword
    if desc.get('qualified'):
        if not isinstance(source_homonym, str) or re.fullmatch(r'[1-9][0-9]*', source_homonym) is None:
            return False
        suffix = opposite + source_homonym + source_headword
    # Historical perfect/qualified records did not pass an introduction into
    # this helper. Their source validator still checks its exact introduction.
    prefixes = destinations(claim, source_introduction)
    if desc.get('alternate'):
        template, destination = desc['alternate']
        before, after = template.split('{alternate}')
        if (isinstance(source_introduction, str) and source_introduction.startswith(before) and
                source_introduction.endswith(after)):
            alternate = source_introduction[len(before):len(source_introduction)-len(after)]
            if pairs(dict(claim, source_alternate_headword=alternate)):
                prefixes.add(destination)
    if basis in (PERFECT, QUALIFIED):
        prefixes = {'pf. '}
    return any(literal[offset:].strip() == prefix + suffix for prefix in prefixes)


def first_sense_prefix(page, span, passage):
    """Verify an overprinted first-sense label attached to a grammar run.

    This removes nothing from the source. It licenses a review's three-character
    lookup offset only at the beginning of an article, with independently
    positioned copies of the same 1 and period. Later senses cannot qualify.
    """
    proof = passage.get('numbered_sense')
    if not isinstance(proof, dict) or set(proof) != {'run_start', 'label'} or proof['label'] != '1.':
        return False
    start, a = proof['run_start'], passage['run_start']
    heading_end = max(span['loc_run_indices']) + 1
    if (type(start) is not int or passage.get('run_start_offset') != 3 or
            not heading_end <= start < a < span['run_end_exclusive'] or a-start > 8):
        return False
    runs = page['positioned_page']['positioned_text_runs']
    if ''.join(r['decoded_unicode'] for r in runs[heading_end:start]).strip() not in ('', '.'):
        return False
    fonts = {f['font_id']: (f.get('family'), f.get('style')) for f in page['representative_fonts']}
    selected = runs[start:a+1]
    first = selected[-1]
    if not first['decoded_unicode'].startswith('.  p') or len(first.get('glyphs', [])) < 4:
        return False
    glyphs = []
    for i, run in enumerate(selected):
        gs = run.get('glyphs', [])[:3] if i == len(selected)-1 else run.get('glyphs', [])
        text = run['decoded_unicode'][:3] if i == len(selected)-1 else run['decoded_unicode']
        if (fonts.get(run.get('font_id')) != ('TGaramond', 'regular') or run.get('unknown_glyphs') or
                not gs or ''.join(g.get('unicode', '') for g in gs) != text or
                any(g.get('unknown') or g.get('x') is None or g.get('y') is None for g in gs)):
            return False
        glyphs.extend(gs)
    p = first['glyphs'][3]
    if (p.get('unicode') != 'p' or p.get('x') is None or p.get('y') is None or
            any(g['unicode'] not in '1. ' or abs(g['y']-p['y']) > .04 or
                not 0 < p['x']-g['x'] < 3 for g in glyphs)):
        return False
    digits = [g for g in glyphs if g['unicode'] == '1']
    dots = [g for g in glyphs if g['unicode'] == '.']
    return (len(digits) >= 2 and len(dots) >= 2 and
            max(g['x'] for g in digits)-min(g['x'] for g in digits) <= .04 and
            max(g['x'] for g in dots)-min(g['x'] for g in dots) <= .04 and
            max(g['x'] for g in digits) < min(g['x'] for g in dots))


def positioned_passage(page, runs, source_headword):
    """Upright grammar/arrow, italic target, and an exact terminal boundary.

    A single wrap may occur immediately before the arrow. It must have an
    adjacent baseline and return within the same column. No text is normalized.
    The caller binds the complete window to a single re-extracted article.
    """
    fonts = {f['font_id']: (f.get('family'), f.get('style'))
             for f in page['representative_fonts']}
    literal = ''.join(r['decoded_unicode'] for r in runs)
    arrows = [i for i, c in enumerate(literal) if c in '↑↓']
    if len(arrows) != 1 or any(r.get('x') is None or r.get('y') is None for r in runs):
        return False
    arrow = arrows[0]
    if literal[arrow+1:].strip() != source_headword:
        return False
    lines, offset = [], 0
    for run in runs:
        value = run['decoded_unicode']
        style = 'regular' if offset+len(value) <= arrow+1 else 'italic'
        if (not value or (offset <= arrow < offset+len(value)-1) or
                fonts.get(run.get('font_id')) != ('TGaramond', style) or
                run.get('unknown_glyphs') or any(g.get('unknown') for g in run.get('glyphs', []))):
            return False
        if not lines or lines[-1][0]['y'] != run['y']:
            lines.append([])
        if lines[-1] and not 0 <= run['x']-lines[-1][-1]['x'] <= 40:
            return False
        lines[-1].append(run)
        offset += len(value)
    if len(lines) == 1:
        return True
    if len(lines) != 2:
        return False
    first, second = lines
    return (''.join(r['decoded_unicode'] for r in second) == literal[arrow:] and
            0.5 <= first[0]['y']-second[0]['y'] <= 2 and
            0 < first[-1]['x']-second[0]['x'] <= 40)


def complete_target(runs, end, article_end):
    """Reject a prefix ending inside a word split between PDF runs."""
    if end >= article_end or runs[end-1]['decoded_unicode'][-1:].isspace():
        return True
    following = runs[end]['decoded_unicode']
    return bool(following) and not (following[0].isalpha() or following[0] in '’‘\'')
