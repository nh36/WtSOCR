"""Derived conversion abstains and never rewrites source-bearing reader fields."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from wts_loc_converter import Converter, held_out
from build_badw_loc_reader import add_display


def model():
    return Converter([('ka', 'ཀ'), ('khi', 'ཁི'), ('ñi', 'ཉི'),
                      ('źi', 'ཞི'), ('skra', 'སྐྲ'), ('brgyad', 'བརྒྱད')])


def test_compositional_conversion_and_historical_letters():
    c = model()
    assert 'ཁ' not in c.training_syllables
    assert c.syllable('kha')['tibetan'] == 'ཁ'
    assert c.convert('ka kha')['tibetan'] == 'ཀ་ཁ་'
    assert c.convert('ñi źi skra brgyad')['tibetan'] == 'ཉི་ཞི་སྐྲ་བརྒྱད་'
    assert c.convert('ka། kha')['tibetan'] == 'ཀ། ཁ་'
    assert c.convert('ka།')['tibetan'] == 'ཀ།'


def test_ambiguous_damaged_and_unattested_inputs_abstain():
    c = model()
    c.inverse['ka'].add('ཁ')
    assert c.convert('ka')['status'] == 'ambiguous'
    for value in ('g.yo', 'k$a', 'ka\n', '', ' ', '།'):
        assert c.convert(value)['tibetan'] is None
    assert c.syllable('zzzz')['status'] == 'unattested_structure'
    assert held_out('ཀ') == held_out('ཀ')


def test_display_requires_independent_exact_pair_and_exclusive_language():
    entry = dict(headword=dict(loc='ka', tibetan='ཀ་'), display_blocks=[dict(segments=[
        dict(text='ka', languages=['bo'], component_id='xref', source_span=[2, 4]),
        dict(text='ka', languages=['bo', 'sa']),
        dict(text=' ka', languages=['bo']),
        dict(text='ka', languages=['de']),
    ])])
    original = copy.deepcopy(entry)
    assert add_display(entry, {'ka': 'ཀ་'}) == {'headwords': 1, 'passages': 1}
    assert entry['headword'] == original['headword']
    assert entry['display_blocks'][0]['segments'][0]['component_id'] == 'xref'
    for block in entry['display_blocks']:
        for segment in block['segments']:
            segment.pop('derived_tibetan', None)
            segment.pop('derived_evidence', None)
    entry.pop('derived_headword')
    assert entry == original
    entry['headword']['tibetan'] = 'ཁ་'
    assert add_display(entry, {'ka': 'ཀ་'})['headwords'] == 0
