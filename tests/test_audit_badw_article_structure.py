"""Offline parser-audit selection and provenance checks."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_badw_article_structure import audit, select
from badw_article_parser import parse_cached_article
from badw_source_cache import NetworkResponse, RequestSpec, SourceCache


FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "badw" / "article.html").read_bytes()
URL = "https://wts-digital.badw.de/lemma/ka/2"


def test_deterministic_selection_and_exact_offline_replay():
    with TemporaryDirectory() as directory:
        cache = SourceCache(directory, delay_seconds=0,
                            transport=lambda request, timeout: (_ for _ in ()).throw(
                                AssertionError("unexpected network call")))
        # The parser's public cache contract is tested elsewhere; this test
        # supplies a tiny object through the normal cache write path.
        warm = SourceCache(directory, delay_seconds=0, transport=lambda request, timeout: NetworkResponse(
            status=200, final_url=URL, headers={"Content-Type": "text/html; charset=utf-8"}, body=FIXTURE))
        warm.fetch(RequestSpec(URL))
        one = parse_cached_article(cache, RequestSpec(URL))
        assert select([one], 1) == [one]
        assert audit(one, cache)["errors"] == []
