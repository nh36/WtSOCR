"""The preview closure follows accepted witnesses without promoting parents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_badw_connected_reader import destinations


def test_plural_closure_ignores_parent_and_uncertain_member_targets():
    reference = dict(status='resolved', target_entry_id='forbidden-parent', target_members=[
        dict(resolution_status='resolved', target_entry_id='accepted'),
        dict(resolution_status='ambiguous', target_entry_id='ambiguous'),
        dict(resolution_status='unresolved', target_entry_id='unresolved')])
    assert destinations(reference) == {'accepted'}
    assert destinations(dict(reference, target_members=[])) == set()


def test_single_target_closure_requires_resolved_unique_witness():
    assert destinations(dict(status='resolved', target_entry_id='accepted')) == {'accepted'}
    for status in ('unresolved', 'ambiguous'):
        assert destinations(dict(status=status, target_entry_id='candidate')) == set()
    assert destinations(dict(status='resolved')) == set()
