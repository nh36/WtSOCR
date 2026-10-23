"""Source-preserving, reviewed continuation across verified nonprinting glyphs.

Only a single physical baseline ending at an upright stop is admitted. Frozen
observation lines and offsets remain untouched; coordinates come from an exact
CID/font/Unicode replay of the hash-checked original PDF.
"""
import re
from badw_pdf_expressions import NONPRINTING
from badw_assertion_layout import page_runs


def bridged_target(lines, divisions, start, sources):
    if not sources:
        return None
    text = '\n'.join(line['text'] for line in lines)
    if text[start:start+1] not in ('↑', '↓'):
        return None
    offsets = []; cursor = 0
    for line in lines:
        offsets.append(cursor); cursor += len(line['text']) + 1
    owners = {i: d for d, division in enumerate(divisions)
              for i in range(division['start_line_index'], division['end_line_index_exclusive'])}
    objects = {s['page_id']: s for s in sources}
    atoms = {}
    first_line = next((i for i, o in enumerate(offsets) if o <= start < o+len(lines[i]['text'])), None)
    if first_line is None or first_line not in owners:
        return None
    # At most three observation lines and 256 source characters, even when a
    # long diagnostic placeholder occupies only one nonprinting PDF glyph.
    for i in range(first_line, min(first_line+3, len(lines))):
        line = lines[i]
        if (line['page_id'] != lines[first_line]['page_id'] or
                line.get('printed_page') != lines[first_line].get('printed_page') or
                owners.get(i) != owners[first_line]):
            break
        source = objects.get(line['page_id'])
        if not source:
            return None
        runs = page_runs(source['canonical_object'], source['canonical_object_sha256'],
                         source['pdf_sha256'], source['pdf_url'])
        if runs is None:
            return None
        selected = runs[line['run_start']:line['run_end_exclusive']]
        if ''.join(r['decoded_unicode'] for r in selected) != line['text']:
            return None
        pos = offsets[i]
        for run in selected:
            for glyph in run['glyphs']:
                word = glyph['unicode']
                spans = [s for s in line['style_spans'] if s['start'] <= pos-offsets[i]
                         and pos-offsets[i]+len(word) <= s['end']]
                if len(spans) != 1 or spans[0]['font_id'] != run['font_id']:
                    return None
                atoms[pos] = (word, glyph, spans[0], i)
                pos += len(word)
    pos = start+1
    while text[pos:pos+1] in (' ', '\t'):
        pos += 1
    arrow = atoms.get(start)
    if arrow is None or arrow[0] != text[start] or arrow[2].get('style') != 'regular':
        return None
    begin = pos; logical = ''; removed = []; previous = (arrow[1], False); italic_font = None
    family = None; prefix = False; seen_italic = False
    while pos < min(len(text), start+256):
        if text[pos] == '\n':
            # Observation line breaks caused by a font switch are not lexical
            # whitespace. Require a nonprinting glyph at this exact boundary.
            if not (NONPRINTING.match(text, pos+1) or removed and removed[-1]['end'] == pos):
                return None
            pos += 1
            continue
        atom = atoms.get(pos)
        if atom is None:
            return None
        word, glyph, style, line = atom
        if previous is not None:
            prev, prev_nonprinting = previous
            edge = prev['x'] if prev_nonprinting else prev['x']+prev['advance']
            if abs(glyph['y']-prev['y']) > .5 or not -1 <= glyph['x']-edge <= 5:
                return None
        if style.get('style') == 'regular' and word in '.;:':
            if not seen_italic or not removed or not logical or len(logical) > 80:
                return None
            return dict(start=begin, end=pos, lexical_target=logical,
                        nonprinting_spans=removed, source_objects=sources)
        nonprinting = NONPRINTING.fullmatch(word) is not None
        if not nonprinting:
            if not re.fullmatch(r"[A-Za-zÀ-žḀ-ỿ’' \t]+", word):
                return None
            if style.get('style') != 'italic':
                # The printed opening apostrophe may be upright, but only
                # immediately before the verified layout-glyph interlude.
                if pos != begin or word != '’' or style.get('style') != 'regular':
                    return None
                prefix = True; family = style.get('family')
                if not NONPRINTING.match(text, pos+1+(text[pos+1:pos+2] == '\n')):
                    return None
            else:
                if italic_font is None:
                    italic_font = style.get('font_id')
                    if prefix and family != style.get('family'):
                        return None
                if not italic_font or italic_font != style.get('font_id'):
                    return None
                seen_italic = True
            logical += word
        else:
            removed.append(dict(start=pos, end=pos+len(word), literal=word))
            if len(removed) > 2:
                return None
        previous = glyph, nonprinting
        pos += len(word)
    return None
