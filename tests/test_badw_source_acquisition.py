import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unicodedata
from urllib.error import URLError
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "badw"
sys.path.insert(0, str(SCRIPTS))

from badw_article_parser import (  # noqa: E402
    parse_cached_article,
    write_cached_catalogue_jsonl,
)
from badw_catalogue import (  # noqa: E402
    CatalogueRecord,
    acquire_catalogue_records,
    enumerate_catalogue,
    parse_search_results,
    read_catalogue,
    select_stratified_records,
    write_catalogue,
)
from badw_source_cache import (  # noqa: E402
    NetworkResponse,
    RequestSpec,
    SourceCache,
    classify_response,
    delivery_type_for_url,
)


ARTICLE_BYTES = (FIXTURES / "article.html").read_bytes()
SEARCH_BYTES = (FIXTURES / "search_results.html").read_bytes()
ERROR_BYTES = (FIXTURES / "error_page.html").read_bytes()


def html_response(request, body=ARTICLE_BYTES, *, status=200, final_url=None):
    return NetworkResponse(
        status=status,
        final_url=final_url or request.full_url,
        headers={"Content-Type": "text/html; charset=UTF-8", "ETag": '"fixture"'},
        body=body,
    )


def article_record(url):
    lemma = url.rsplit("/", 2)[-2]
    homonym = url.rsplit("/", 1)[-1]
    return CatalogueRecord(
        lemma=lemma,
        display_lemma=lemma,
        homonym=homonym,
        canonical_url=url,
        delivery_type="database_article",
        enumeration_prefix=lemma[:1],
        catalogue_observed_at_utc="2026-09-02T00:00:00+00:00",
    )


def test_prefix_enumeration_deduplicates_and_orders_deterministically():
    calls = []

    def transport(request, timeout):
        calls.append(
            (
                request.full_url,
                parse_qs((request.data or b"").decode(), keep_blank_values=True),
            )
        )
        return html_response(request, SEARCH_BYTES, final_url="https://wts-digital.badw.de/suche")

    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        records, summary = enumerate_catalogue(
            cache,
            prefixes=("k",),
            observed_at_utc="2026-09-02T00:00:00+00:00",
        )
        assert [record.canonical_url for record in records] == [
            "https://wts-digital.badw.de/lemma/ka/2",
            "https://wts-digital.badw.de/pdf/kha",
        ]
        assert records[0].homonym == "2"
        assert records[0].enumeration_prefix == "k"
        assert summary["unique_results"] == 2
        assert summary["duplicate_url_count"] == 1
        assert summary["duplicate_occurrences"] == 1
        assert calls[0][1] == {"bedeutung": [""], "lemma": ["k"]}

        restarted = SourceCache(
            temporary,
            delay_seconds=0,
            transport=lambda request, timeout: (_ for _ in ()).throw(
                AssertionError("network called on cached restart")
            ),
        )
        repeated, repeated_summary = enumerate_catalogue(
            restarted,
            prefixes=("k",),
            observed_at_utc="2026-09-02T00:00:00+00:00",
        )
        assert repeated == records
        assert repeated_summary["unique_results"] == 2
        assert repeated_summary["cache_hits"] == 1
        assert repeated_summary["network_fetches"] == 0


def test_prefix_enumeration_follows_pagination_once():
    first_page = b"""<html><body>
    <span class='lemlink'><a href='/lemma/ka/1'><span class='lem'>ka</span></a></span>
    <a rel='next' href='/suche?page=2'>weiter</a>
    </body></html>"""
    second_page = b"""<html><body>
    <span class='lemlink'><a href='/lemma/kha/1'><span class='lem'>kha</span></a></span>
    </body></html>"""
    calls = []

    def transport(request, timeout):
        calls.append((request.method, request.full_url))
        body = second_page if "page=2" in request.full_url else first_page
        return html_response(request, body, final_url=request.full_url)

    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        records, summary = enumerate_catalogue(
            cache,
            prefixes=("k",),
            observed_at_utc="2026-09-02T00:00:00+00:00",
        )
        assert [record.lemma for record in records] == ["ka", "kha"]
        assert summary["pages_processed"] == 2
        assert summary["network_fetches"] == 2
        assert calls == [
            ("POST", "https://wts-digital.badw.de/suche"),
            ("GET", "https://wts-digital.badw.de/suche?page=2"),
        ]


def test_catalogue_tsv_order_is_stable():
    records = [
        article_record("https://wts-digital.badw.de/lemma/z/10"),
        article_record("https://wts-digital.badw.de/lemma/a/2"),
        article_record("https://wts-digital.badw.de/lemma/a/1"),
    ]
    with TemporaryDirectory() as temporary:
        first = Path(temporary) / "first.tsv"
        second = Path(temporary) / "second.tsv"
        write_catalogue(first, records)
        write_catalogue(second, reversed(records))
        assert first.read_bytes() == second.read_bytes()
        assert [record.homonym for record in read_catalogue(first)[:2]] == ["1", "2"]


def test_stratified_sample_is_deterministic_and_filters_delivery_type():
    records = [
        article_record(f"https://wts-digital.badw.de/lemma/{prefix}{index}/1")
        for prefix in ("a", "b")
        for index in range(5)
    ]
    records.append(
        CatalogueRecord(
            lemma="a-pdf",
            display_lemma="a-pdf",
            homonym="",
            canonical_url="https://wts-digital.badw.de/pdf/a-pdf",
            delivery_type="generated_pdf",
            enumeration_prefix="a",
            catalogue_observed_at_utc="2026-09-02T00:00:00+00:00",
        )
    )
    selected = select_stratified_records(
        list(reversed(records)),
        delivery_types=frozenset({"database_article"}),
        per_prefix=2,
    )
    assert [(record.enumeration_prefix, record.lemma) for record in selected] == [
        ("a", "a0"),
        ("a", "a4"),
        ("b", "b0"),
        ("b", "b4"),
    ]


def test_large_search_result_page_has_no_parser_limit():
    result_items = "".join(
        f'<li><span class="lemlink"><a href="/lemma/k{i}/1"><span class="lem">k{i}</span></a></span></li>'
        for i in range(5000)
    )
    page = parse_search_results(
        f"<html><body><ul>{result_items}</ul></body></html>",
        prefix="k",
        observed_at_utc="2026-09-02T00:00:00+00:00",
    )
    assert len(page.records) == 5000
    assert len({record.canonical_url for record in page.records}) == 5000


def test_content_addressed_hash_and_cache_hit_without_network():
    calls = []

    def transport(request, timeout):
        calls.append(request.full_url)
        return html_response(request)

    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        spec = RequestSpec("https://wts-digital.badw.de/lemma/ka/2")
        first = cache.fetch(spec)
        second = cache.fetch(spec)
        expected_hash = hashlib.sha256(ARTICLE_BYTES).hexdigest()
        assert first.metadata["sha256"] == expected_hash
        assert first.object_path == Path(temporary) / "objects" / "sha256" / expected_hash[:2] / expected_hash
        assert first.object_path.read_bytes() == ARTICLE_BYTES
        assert not first.cache_hit
        assert second.cache_hit
        assert second.body == ARTICLE_BYTES
        assert len(calls) == 1
        assert second.metadata["response_headers"]["etag"] == '"fixture"'


def test_partial_acquisition_resumes_and_reuses_shared_object():
    calls = []

    def transport(request, timeout):
        calls.append(request.full_url)
        return html_response(request)

    records = [
        article_record(f"https://wts-digital.badw.de/lemma/k{i}/1") for i in range(3)
    ]
    with TemporaryDirectory() as temporary:
        first_cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        first = acquire_catalogue_records(first_cache, records, maximum_items=2)
        assert first["network_fetches"] == 2
        assert first["remaining"] == 1

        restarted = SourceCache(temporary, delay_seconds=0, transport=transport)
        second = acquire_catalogue_records(restarted, records)
        assert second["cache_hits"] == 2
        assert second["network_fetches"] == 1
        assert second["valid_resources"] == 3
        assert len(calls) == 3
        object_files = list((Path(temporary) / "objects" / "sha256").glob("*/*"))
        assert len(object_files) == 1


def test_redirect_and_final_url_are_recorded():
    final_url = "https://wts-digital.badw.de/lemma/ka/2"

    def transport(request, timeout):
        return html_response(request, final_url=final_url)

    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        response = cache.fetch(RequestSpec("https://wts-digital.badw.de/redirect/ka"))
        assert response.metadata["requested_url"].endswith("/redirect/ka")
        assert response.metadata["final_url"] == final_url
        assert response.metadata["delivery_type"] == "database_article"
        assert response.metadata["http_status"] == 200


def test_transient_failures_retry_with_bounded_attempts():
    outcomes = [
        NetworkResponse(503, "https://wts-digital.badw.de/lemma/ka/2", {"Retry-After": "0"}, b"busy"),
        URLError("temporary"),
        NetworkResponse(
            200,
            "https://wts-digital.badw.de/lemma/ka/2",
            {"Content-Type": "text/html; charset=UTF-8"},
            ARTICLE_BYTES,
        ),
    ]
    sleeps = []

    def transport(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    with TemporaryDirectory() as temporary:
        cache = SourceCache(
            temporary,
            delay_seconds=0,
            max_attempts=4,
            backoff_seconds=0.01,
            transport=transport,
            sleep=sleeps.append,
        )
        response = cache.fetch(RequestSpec("https://wts-digital.badw.de/lemma/ka/2"))
        assert response.is_valid_resource
        assert response.metadata["attempts_in_fetch"] == 3
        assert [item.get("http_status") for item in response.metadata["attempt_history"]] == [503, None, 200]
        assert len(sleeps) == 2


def test_permanent_failure_does_not_block_later_records():
    def transport(request, timeout):
        if request.full_url.endswith("/missing/1"):
            return html_response(request, ERROR_BYTES, status=404)
        return html_response(request)

    records = [
        article_record("https://wts-digital.badw.de/lemma/missing/1"),
        article_record("https://wts-digital.badw.de/lemma/present/1"),
    ]
    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        summary = acquire_catalogue_records(cache, records)
        assert summary["attempted"] == 2
        assert summary["valid_resources"] == 1
        assert summary["invalid_resources"] == 1
        assert summary["permanent"] == 1


def test_http_200_error_page_is_not_a_valid_article():
    with TemporaryDirectory() as temporary:
        cache = SourceCache(
            temporary,
            delay_seconds=0,
            transport=lambda request, timeout: html_response(request, ERROR_BYTES),
        )
        spec = RequestSpec("https://wts-digital.badw.de/lemma/unreleased/1")
        response = cache.fetch(spec)
        assert not response.is_valid_resource
        assert response.metadata["content_classification"] == "unreleased_page"
        assert response.metadata["failure_kind"] == "permanent"
        assert cache.fetch(spec).cache_hit


def test_database_and_pdf_content_classification():
    article_class, article_valid = classify_response(
        status=200,
        final_url="https://wts-digital.badw.de/lemma/ka/2",
        media_type="text/html",
        body=ARTICLE_BYTES,
    )
    pdf_class, pdf_valid = classify_response(
        status=200,
        final_url="https://wts-digital.badw.de/pdf/kha",
        media_type="application/pdf",
        body=b"%PDF-1.7\nfixture",
    )
    wrong_pdf_class, wrong_pdf_valid = classify_response(
        status=200,
        final_url="https://wts-digital.badw.de/pdf/kha",
        media_type="text/html",
        body=ERROR_BYTES,
    )
    assert (article_class, article_valid) == ("database_article", True)
    assert (pdf_class, pdf_valid) == ("generated_pdf", True)
    assert (wrong_pdf_class, wrong_pdf_valid) == ("unexpected_content", False)
    assert delivery_type_for_url("https://wts-digital.badw.de/lemma/ka/2") == "database_article"
    assert delivery_type_for_url("https://wts-digital.badw.de/pdf/kha") == "generated_pdf"


def test_article_parser_preserves_unicode_and_structure_from_cache():
    url = "https://wts-digital.badw.de/lemma/ka/2"
    with TemporaryDirectory() as temporary:
        cache = SourceCache(
            temporary,
            delay_seconds=0,
            transport=lambda request, timeout: html_response(request),
        )
        cache.fetch(RequestSpec(url))
        article = parse_cached_article(cache, RequestSpec(url))
        assert article["lemma"] == "kā"
        assert unicodedata.normalize("NFC", article["lemma"]) != article["lemma"]
        assert article["homonym"] == "2"
        assert article["tibetan_heading"]["text"] == "ཀ་"
        assert [meaning["number"] for meaning in article["meanings"]] == ["1", "2"]
        assert article["examples"][0]["tibetan"]["text"] == "ཀ་ཁ་"
        assert article["examples"][0]["translation"]["text"] == "Beispielübersetzung"
        assert article["examples"][0]["location"]["text"] == "1.2a"
        assert article["sanskrit"][0]["text"] == "kāya"
        assert article["sigla"][0]["text"] == "TS"
        assert article["sigla"][0]["expanded_text"] == "Test-Siglum Langform"
        assert [reference["marker"] for reference in article["cross_references"]] == ["↑", "↓"]
        assert article["cross_references"][1]["target_homonym"] == "3"
        assert article["cross_references"][1]["target_url"].endswith("/lemma/ga/3")
        assert article["divisions"][0]["example_indices"] == [0]
        assert article["divisions"][0]["lexical_block_indices"] == [0]
        assert "Test-Siglum Langform" not in article["article_source_text"]
        assert "Test-Siglum Langform" in article["dom_full_text"]
        assert article["source_object"]["sha256"] == hashlib.sha256(ARTICLE_BYTES).hexdigest()
        assert article["lemma_field"]["locator"]["dom_path"].endswith("/span[2]")
        assert any(fragment["source_text"] == "kā" for fragment in article["text_fragments"])


def test_article_parser_is_reproducible_offline_from_cached_bytes():
    url = "https://wts-digital.badw.de/lemma/ka/2"
    with TemporaryDirectory() as temporary:
        online_cache = SourceCache(
            temporary,
            delay_seconds=0,
            transport=lambda request, timeout: html_response(request),
            now=lambda: "2026-09-02T00:00:00+00:00",
        )
        online_cache.fetch(RequestSpec(url))
        offline_cache = SourceCache(
            temporary,
            delay_seconds=0,
            transport=lambda request, timeout: (_ for _ in ()).throw(
                AssertionError("parser attempted a network request")
            ),
        )
        first = parse_cached_article(offline_cache, RequestSpec(url))
        second = parse_cached_article(offline_cache, RequestSpec(url))
        assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
            second, ensure_ascii=False, sort_keys=True
        )


def test_catalogue_parser_streams_deterministic_jsonl():
    records = [
        article_record("https://wts-digital.badw.de/lemma/ka/2"),
        article_record("https://wts-digital.badw.de/lemma/kha/1"),
    ]
    calls = []

    def transport(request, timeout):
        calls.append(request.full_url)
        return html_response(request)

    with TemporaryDirectory() as temporary:
        cache = SourceCache(temporary, delay_seconds=0, transport=transport)
        for record in records:
            cache.fetch(RequestSpec(record.canonical_url))
        first = Path(temporary) / "first.jsonl"
        second = Path(temporary) / "second.jsonl"
        first_summary = write_cached_catalogue_jsonl(cache, iter(records), first)
        second_summary = write_cached_catalogue_jsonl(cache, iter(records), second)

        assert first_summary["parsed"] == 2
        assert first_summary == second_summary
        assert first.read_bytes() == second.read_bytes()
        assert len(first.read_text(encoding="utf-8").splitlines()) == 2
        assert calls == [record.canonical_url for record in records]
