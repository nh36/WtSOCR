"""Accounting diagnostics must not turn broad containers into successful parsing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from audit_badw_corpus_structure import accounting
from review_badw_corpus_structure import detailed_indicators, gap_category


def indicators(text, nodes):
    return [f for f, _, _ in detailed_indicators({'review_text': text}, {'nodes': nodes})]


def node(kind, start, end, identifier='n'):
    return dict(kind=kind, start=start, end=end, id=identifier)


def test_broad_sense_container_does_not_hide_lexical_gap():
    text='Wort Lex. tib'
    gaps, lexical, alphabetic=accounting(text,[node('sense',0,len(text)),node('definition',0,4)])
    assert gaps==[[4,len(text)]] and lexical==[(4,len(text))] and alphabetic==6


def test_leading_sense_number_and_quotes_are_not_swallowed_definition():
    text='\n  1.\n „Rinder zählend“, Bez. für Nomade.'
    assert 'definition_boundary_cue' not in indicators(text,[node('definition',0,len(text))])
    later=text+'\n 2. anderes Wort'
    assert 'definition_boundary_cue' in indicators(later,[node('definition',0,len(later))])


def test_lex_boundary_and_duplicate_overlap_remain_visible():
    text='1. Wort Lex. A; B'
    ns=[node('sense',0,7),node('lexical_parallel',8,16,'a'),node('lexical_parallel',12,16,'b')]
    flags=indicators(text,ns)
    assert flags.count('lex_outside_numbered_sense')==2
    assert flags.count('overlapping_lex_items')==1
    assert 'duplicate_component' not in flags


def test_layout_labels_are_distinct_from_untyped_header():
    assert gap_category(' \n')=='layout'
    assert gap_category('Lex. 1. pf.')=='structural_label'
    assert gap_category('auch ’phyugs')=='lexical_or_header_review'
