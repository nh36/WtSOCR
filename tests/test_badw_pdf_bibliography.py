from badw_pdf_bibliography import Resolver


def test_exact_unicode_offsets_and_numeric_locator():
    result = Resolver([("a", "Liś")]).resolve("(Liś12, 3)")
    assert result["status"] == "exact_label_expansion_candidates"
    assert result["matches"] == [{"start": 1, "end": 4, "label": "Liś",
        "authority_ids": ["a"], "status": "exact_label_expansion_candidate"}]
    assert Resolver([("a", "Liś")]).resolve("Liš 3") ["status"] == "unmatched"
    assert Resolver([("a", "Liś")]).resolve("xLiś") ["status"] == "unmatched"


def test_competing_authorities_and_overlapping_spellings_remain_ambiguous():
    resolver = Resolver([("a", "Dol"), ("b", "Dol4"), ("c", "Dol")])
    result = resolver.resolve("Dol4 3")
    assert result["status"] == "ambiguous"
    assert [m["status"] for m in result["matches"]] == ["ambiguous", "ambiguous"]
    assert result == Resolver(list(reversed([("a", "Dol"), ("b", "Dol4"),
                                            ("c", "Dol")]))).resolve("Dol4 3")


def test_multiple_nonoverlapping_sources_and_empty_registry():
    assert Resolver([("a", "A"), ("b", "B")]).resolve("A 3; B 4")["status"] == "exact_label_expansion_candidates"
    assert Resolver([]).resolve("(unidentified)")["status"] == "unmatched"
