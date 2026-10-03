from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from migrate_badw_pdf_reviews import build, changed_lines, digest, migrate_review, visual


def fixture():
    lines = [{'page_id': 'old-page', 'span_index': 0, 'run_start': i,
              'run_end_exclusive': i + 1, 'text': text}
             for i, text in enumerate(['UNKNOWN', '„Beleg“', 'next'])]
    old = {'article_id': 'old-article', 'visual_lines': lines,
           'source_objects': [{'page_id': 'old-page', 'pdf_sha256': 'pdf',
                               'run_start': 0, 'run_end_exclusive': 3}]}
    new = deepcopy(old)
    new['article_id'] = 'new-article'
    new['source_objects'][0]['page_id'] = 'new-page'
    for line in new['visual_lines']:
        line['page_id'] = 'new-page'
    new['visual_lines'][0]['text'] = 'ź'
    row = {'article_id': 'old-article', 'visual_sha256': digest(visual(old)),
           'visual_start': '8', 'visual_end': '15', 'quote_sha256': digest('„Beleg“'),
           'role': 'definition', 'basis': 'independent source review'}
    return row, old, new, {'old-page': 'new-page'}


def test_offset_transfer_uses_unchanged_line_coordinates():
    row, old, new, pages = fixture()
    result = migrate_review(row, old, new, pages)
    assert (result['visual_start'], result['visual_end']) == ('2', '9')
    assert result['quote_sha256'] == row['quote_sha256']
    assert result['visual_sha256'] == digest(visual(new))
    assert result['article_id'] == 'new-article'
    assert row['article_id'] == 'old-article'


def test_changed_reviewed_line_requires_review():
    row, old, new, pages = fixture()
    new['visual_lines'][1]['text'] = '„Beleg!“'
    with pytest.raises(ValueError, match='reviewed line changed'):
        migrate_review(row, old, new, pages)


def test_identical_literal_at_another_source_location_is_not_a_match():
    row, old, new, pages = fixture()
    new['visual_lines'][1]['run_start'] = 99
    with pytest.raises(ValueError, match='reviewed line changed'):
        migrate_review(row, old, new, pages)


def test_changed_pdf_source_fails_closed():
    row, old, new, pages = fixture()
    new['source_objects'][0]['pdf_sha256'] = 'different'
    with pytest.raises(ValueError, match='source coordinates'):
        migrate_review(row, old, new, pages)


def test_stale_review_fails_closed():
    row, old, new, pages = fixture()
    row['quote_sha256'] = 'wrong'
    with pytest.raises(ValueError, match='stale original reviewed span'):
        migrate_review(row, old, new, pages)


def test_changed_lines_are_explicit_audit_evidence():
    row, old, new, pages = fixture()
    assert changed_lines(old, new, pages) == [{
        'anchor': ('new-page', 0, 0, 1), 'old_text': 'UNKNOWN', 'new_text': 'ź'}]
    assert changed_lines(None, new, pages) == []


def test_multiline_review_preserves_line_breaks():
    row, old, new, pages = fixture()
    row['visual_end'] = str(len(visual(old)))
    row['quote_sha256'] = digest(visual(old)[8:])
    result = migrate_review(row, old, new, pages)
    assert visual(new)[int(result['visual_start']):int(result['visual_end'])] == '„Beleg“\nnext'


def test_empty_review_table_fails_before_reading_article_corpora(tmp_path):
    crosswalk = tmp_path / 'pages.tsv'
    crosswalk.write_text('old_page_id\tnew_page_id\tgeometry_verified\n'
                         'old-page\tnew-page\tTrue\n', encoding='utf-8')
    reviews = tmp_path / 'reviews.tsv'
    reviews.write_text('article_id\tvisual_sha256\n', encoding='utf-8')
    with pytest.raises(ValueError, match='review table is empty'):
        build(tmp_path / 'absent-old.gz', tmp_path / 'absent-new.gz',
              crosswalk, reviews, tmp_path / 'proposals.tsv')
    assert not (tmp_path / 'proposals.tsv').exists()
