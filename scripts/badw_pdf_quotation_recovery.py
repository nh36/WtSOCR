"""Bounded Roman glosses inside independently established PDF Lex./examples.

Quote punctuation establishes boundaries, never role. Role additionally requires
an existing lexical/example envelope and an immediately preceding italic form,
or an italic lemma-substitution expression, quoted Roman translation and
immediately enclosed source citation in one continuous layout unit.
Raw candidates and source text remain immutable, including nested punctuation.
"""
import copy
import hashlib
import re
from badw_header_structure import contiguous_pdf_lines
from badw_pdf_mixed_clauses import style_runs
from badw_recovered_fragment_integrity import delimiter_error

VERSION = 'pdf-bounded-quotation-v1'


def balanced_quotes(text):
    stack = []
    for i, char in enumerate(text):
        if char == '„':
            stack.append(i)
        elif char == '“':
            if not stack:
                continue
            start = stack.pop()
            if not stack:
                yield dict(visual_start=start, visual_end=i+1, evidence='balanced_literal_quote_sequence')


def translation_italics_are_lexical(inside, runs, text, start, end):
    """Permit only source-language tokens embedded in a Roman translation.

    The outer German quotation and its layout continuity are checked by the
    caller. Italics must be internal, token-sized, and either contain
    transliteration diacritics or match an italic source-form token elsewhere
    in the observation. They must be surrounded by Roman translation text.
    """
    italic = [r for r in inside if r['style'] == 'italic']
    if not italic:
        return True
    for run in italic:
        a, b = max(start + 1, run['start']), min(end - 1, run['end'])
        literal = text[a:b].strip()
        if not literal or not re.fullmatch(r"[A-Za-z][A-Za-z0-9’'ṃṣṭḍṅñśḥāīūṛḷ-]*", literal):
            return False
        if not text[start + 1:a].strip() or not text[b:end - 1].strip():
            return False
        token = literal.strip("-’'").casefold()
        has_transliteration = bool(re.search(r"[ṃṣṭḍṅñśḥāīūṛḷ]", token))
        corroborated_source_form = any(
            other['style'] == 'italic'
            and not (other['start'] < end and start < other['end'])
            and text[other['start']:other['end']].strip("-’' ").casefold() == token
            for other in runs
        )
        if not (has_transliteration or corroborated_source_form):
            return False
    return True


def substitution_form_start(text, tilde):
    """Find a complete source-form clause ending at *tilde*.

    The left edge is a printed clause boundary, and the whole intervening
    material must be transliteration-form syntax. This avoids reconstructing
    a form by taking the nearest preceding bracket or italic run.
    """
    prefix = text[:tilde]
    boundaries = [0]
    # Physical source line starts are independent boundaries in these PDF
    # observations; keep them distinct from arbitrary whitespace wrapping.
    boundaries.extend(m.end() for m in re.finditer(r"(?:[;:.!?]\s+|\n[ \t]*)", prefix))
    token = re.compile(r"\[[^\[\]]+\]|[^\W\d_]+|[’'./-]|\s+", re.UNICODE)
    for start in reversed(boundaries):
        phrase = text[start:tilde]
        if not phrase or not phrase[0].isalpha() and phrase[0] != '[':
            continue
        pieces = token.findall(phrase)
        if ''.join(pieces) != phrase:
            continue
        if any(piece.startswith('[') and (not piece.endswith(']') or
               not piece[1:-1] or not all(char.isalpha() for char in piece[1:-1]))
               for piece in pieces):
            continue
        if '[' in phrase and (not phrase.startswith('[') or
                not re.match(r"\[[^\[\]]+\](?:[^\W\d_]|\s)", phrase, re.UNICODE)):
            continue
        if any(piece in (';', ':', ',', '(', ')') for piece in pieces):
            continue
        return start
    return None


def source_runs_covering(runs, start, end):
    """Return exact observed runs covering a literal source interval."""
    selected = sorted((r for r in runs if r['start'] < end and start < r['end']),
                      key=lambda r: (r['start'], r['end']))
    cursor = start
    for run in selected:
        if run['start'] > cursor:
            return []
        cursor = max(cursor, run['end'])
        if cursor >= end:
            return selected
    return []


def recover_quotations(projection, text):
    if projection['source_kind'] != 'pdf':
        return projection
    lines, runs = style_runs(projection, text)
    result = copy.deepcopy(projection)
    for quote in balanced_quotes(text):
        a, b = quote['visual_start'], quote.get('visual_end', quote['visual_start'])
        if not a < b or text[a] != '„' or text[b-1] != '“' or delimiter_error(text[a:b]):
            continue
        inside = [r for r in runs if r['start'] < b and a < r['end']]
        if not inside:
            continue
        if any(not contiguous_pdf_lines(lines, l['line'], r['line']) for l, r in zip(inside, inside[1:])):
            continue
        envelopes = [n for n in result['nodes'] if n['kind'] in ('example', 'lexicographic', 'lexical_parallel')
                     and n['start'] <= a < b <= n['end']]
        additions = []
        citation_to_reparent = None
        if not envelopes:
            # Independently bounded substitution example: italic expression
            # containing the printed lemma substitution, Roman quoted gloss,
            # then an existing parenthesized source citation. No nearest-sense
            # or nearest-example association is used.
            prior = [r for r in runs if r['end'] <= a]
            if not prior or prior[-1]['style'] != 'italic' or text[prior[-1]['end']:a].strip():
                continue
            form = [prior[-1]]
            for run in reversed(prior[:-1]):
                if run['style'] != 'italic' or text[run['end']:form[0]['start']].strip():
                    break
                if not contiguous_pdf_lines(lines, run['line'], form[0]['line']):
                    break
                # Do not let a preceding italic component (for example a
                # Sanskrit definition) become part of the Tibetan form.
                if any(n['kind'] not in ('source_division', 'sense')
                       and n['start'] < run['end'] and run['start'] < n['end']
                       for n in result['nodes']):
                    break
                form.insert(0, run)
            start = form[0]['start']
            tilde = text.find('~', start, a)
            if tilde < 0 or delimiter_error(text[start:a]):
                continue
            complete_start = substitution_form_start(text, tilde)
            if complete_start is None:
                continue
            # An italic transliteration (or an editorially bracketed initial)
            # must begin the recovered source form. This independently bounds
            # the form and prevents a Roman definition or translation before
            # the tilde from being accepted merely because its letters fit
            # the permissive transliteration character grammar.
            if text[complete_start] == '[':
                if not re.match(r"\[[^\[\]]+\](?:[^\W\d_]|\s+[^\W\d_])", text[complete_start:tilde], re.UNICODE):
                    continue
            else:
                first_form_runs = [r for r in runs if r['start'] <= complete_start < r['end']]
                if not first_form_runs or first_form_runs[0]['style'] != 'italic':
                    continue
            observed = source_runs_covering(runs, complete_start, start)
            # Runs must preserve every observed character in the complete
            # printed form, even when brackets and the italic continuation
            # use different fonts or glyph runs.
            if ((complete_start < start and not observed) or ''.join(text[max(complete_start,r['start']):min(start,r['end'])]
                                        for r in observed) != text[complete_start:start]
                or any(not contiguous_pdf_lines(lines, l['line'], r['line'])
                       for l, r in zip(observed, observed[1:]))):
                continue
            if any(n['kind'] not in ('source_division','sense')
                   and n['start'] < start and complete_start < n['end']
                   for n in result['nodes']):
                continue
            form = observed + form
            start = complete_start
            if not translation_italics_are_lexical(inside, runs, text, a, b):
                continue
            if not contiguous_pdf_lines(lines, form[-1]['line'], inside[0]['line']):
                continue
            citations = [n for n in result['nodes'] if n['kind'] == 'citation'
                         and n['start'] >= b and not text[b:n['start']].strip()]
            if len(citations) != 1:
                continue
            citation = citations[0]
            end = citation['end']
            if not text[citation['start']:end].startswith('(') or delimiter_error(text[citation['start']:end]):
                continue
            tail = [r for r in runs if r['start'] < end and b <= r['end']]
            if not tail or any(not contiguous_pdf_lines(lines, l['line'], r['line'])
                               for l, r in zip(inside[-1:]+tail, tail)):
                continue
            if any(n['kind'] not in ('source_division', 'sense') and n['id'] != citation['id']
                   and n['start'] < end and start < n['end'] for n in result['nodes']):
                continue
            parents = [n for n in result['nodes'] if n['kind'] in ('sense', 'source_division')
                       and n['start'] <= start < end <= n['end']]
            if not parents:
                continue
            parent = min(parents, key=lambda n: n['end']-n['start'])
            key = f"{projection['identity']}:{VERSION}:example:{start}:{end}"
            example_id = 'recovered-example:'+hashlib.sha256(key.encode()).hexdigest()
            evidence = dict(rule=VERSION, role='italic_substitution_quoted_translation_citation')
            owner = dict(id=example_id, kind='example', start=start, end=end,
                         parent=parent['id'], structural_recovery=evidence,
                         source_evidence=dict(rule=VERSION, typography=form+inside+tail,
                                              citation_node=citation['id']))
            additions = [owner, dict(id=example_id+':form', kind='tibetan',
                start=start, end=a-1 if text[a-1:a].isspace() else a,
                parent=example_id, source_evidence=dict(rule=VERSION, typography=form))]
            citation_to_reparent = citation
            envelopes = [owner]
        owner = min(envelopes, key=lambda n: n['end']-n['start'])
        left = [r for r in runs if owner['start'] <= r['start'] < r['end'] <= a]
        if not left or left[-1]['style'] != 'italic' or text[left[-1]['end']:a].strip():
            continue
        if not contiguous_pdf_lines(lines, left[-1]['line'], inside[0]['line']):
            continue
        # A complete translation cannot be made by subtracting existing pieces.
        # Citation, sense or sibling Lex. crossings reject the whole production.
        crossing = [n for n in result['nodes'] if n['start'] < b and a < n['end']
                    and n['kind'] not in ('source_division', 'sense', 'example', 'lexicographic', 'lexical_parallel')]
        if crossing:
            continue
        if any(n['kind'] in ('sense', 'lexicographic', 'lexical_parallel')
               and n['start'] < b and a < n['end'] and not n['start'] <= a < b <= n['end']
               for n in result['nodes']):
            continue
        result['nodes'].extend(additions)
        if citation_to_reparent is not None:
            citation_to_reparent['parent'] = owner['id']
            citation_to_reparent['derived_parent_evidence'] = owner['structural_recovery']
        key = f"{projection['identity']}:{VERSION}:{a}:{b}"
        result['nodes'].append(dict(id='recovered-translation:'+hashlib.sha256(key.encode()).hexdigest(),
            kind='translation', start=a, end=b, parent=owner['id'],
            source_evidence=dict(rule=VERSION, quoted_span=quote, typography=inside,
                                 italic_form_span=dict(start=left[-1]['start'], end=left[-1]['end'])),
            structural_recovery=dict(rule=VERSION, role='bounded_lexical_or_example_gloss')))
    return result
