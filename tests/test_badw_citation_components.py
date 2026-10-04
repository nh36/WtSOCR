"""Synthetic fixtures only: exact component identity, not inferred editions."""
from test_badw_bibliography import parse, WORK, PUBLICATION
from badw_citation_components import ComponentResolver
import badw_bibliography as bib
import pytest


def resolver(labels):
    rows = [parse(WORK.replace("PW", label))[0] for label in labels]
    return bib.AuthorityResolver(bib.authority_graph(rows)[0], rows)


@pytest.mark.parametrize("text,label", [("K4568 143b5", "K4568"),
    ("Pd-H\n163a", "Pd-H"), ("Lśdz-K 89", "Lśdz-K"),
    ("Bhu-\nKkh 12", "BhuKkh"), ("Bhu\nKkh 12", "BhuKkh")])
def test_complete_spellings_and_reversible_layout(text, label):
    result = resolver(["K", "K4", "K45", "K4568", "Pd", "Pd-H", "Lśdz", "Lśdz-K", "BhuKkh"]).resolve(text)
    assert result["status"] == "exact_online_work_rows"
    match, = result["matches"]
    assert match["canonical_label"] == label
    assert match["raw_text"] == text[match["start"]:match["end"]]
    assert match["target_status"] == "accepted_identity"
    assert result["edition_status"] == "unreviewed"


@pytest.mark.parametrize("text", ["Pd-Z 3", "xPd 3", "Pd/unknown", "Bhu Kkh 3", "bhuKkh 3"])
def test_unknown_suffixes_and_character_changes_do_not_fall_back(text):
    assert resolver(["Pd", "BhuKkh"]).resolve(text)["status"] == "unmatched"


def test_compounds_require_source_description_and_tooltip_agreement():
    row = parse(WORK.replace("PW", "MTH3/5").replace("Title", "Nummer des Dokuments"))[0]
    rows = [row]
    r = bib.AuthorityResolver(bib.authority_graph(rows)[0], rows)
    evidence = [{"label": "MTH3/5/21", "start": 1, "end": 10, "expansion": row["text"]}]
    result = r.resolve_dom("(MTH3/5/21 3)", evidence)
    match, = result["matches"]
    assert match["canonical_label"] == "MTH3/5" and match["selector"] == "/21"
    assert match["grammar_evidence"][0]["source_sha256"] == row["source_sha256"]
    evidence[0]["expansion"] = "conflicting edition"
    assert r.resolve_dom("(MTH3/5/21 3)", evidence)["status"] == "ambiguous"
    no_evidence = resolver(["MTH3/5"])
    assert no_evidence.resolve("MTH3/5/21 3")["status"] == "unmatched"
    pdf = r.resolve("(MTH3/\n5/21 3)")
    assert pdf["matches"][0]["selector"] == "/21"
    split_selector = r.resolve("(MTH3/5/\n21 3)")
    assert split_selector["matches"][0]["selector"] == "/\n21"
    assert split_selector["matches"][0]["raw_text"] == "MTH3/5/\n21"


def test_conflicting_identity_and_unparsed_text_remain_explicit():
    r = ComponentResolver([("one", "PW"), ("two", "PW")])
    assert r.resolve("PW 3")["status"] == "ambiguous"
    result = resolver(["PW"]).resolve("PW 3; Unregistered 2000")
    assert "Unregistered 2000" in "".join(s["raw_text"] for s in result["unparsed_spans"])
    assert result["coverage_status"] == "matched_components_only_not_complete_citation_resolution"
    assert result == resolver(["PW"]).resolve("PW 3; Unregistered 2000")


def test_hyphenated_author_and_year_range_keep_raw_offsets():
    rows = parse(PUBLICATION.replace("Author", "Oberhammer").replace("2001", "1991–2006"), "publication")
    r = bib.AuthorityResolver(bib.authority_graph(rows)[0], rows)
    text = "OBER-\nHAMMER 1991–\n2006, 4"
    result = r.resolve(text)
    assert result["status"] == "exact_online_publication_rows"
    match, = result["matches"]
    assert match["raw_text"] == text[:match["end"]]
    assert r.resolve("OBER HAMMER 1991–2006")["status"] == "unmatched"
    assert r.resolve("OBERHAMMER 1991–2006–2009")["status"] == "unmatched"


def test_unknowns_are_not_repaired():
    text = "DEMI⟦UNKNOWN:font:cid⟧VILLE 1952"
    result = resolver(["PW"]).resolve(text)
    assert result["text"] == text
    assert result["residual_reason"] == "unknown_glyph_in_unmatched_reference"


@pytest.mark.parametrize("text", ["MTH 3/5/35", "MTH3/ 5/35", "MTH 3/\n5/35"])
def test_mth_layout_requires_document_series_evidence(text):
    row = parse(WORK.replace("PW", "MTH3/5").replace("Title", "Nummer des Dokuments"))[0]
    r = bib.AuthorityResolver(bib.authority_graph([row])[0], [row])
    result = r.resolve(text)
    assert result["matches"][0]["raw_text"] == text
    assert result["matches"][0]["selector"] == "/35"
    assert resolver(["MTH3/5"]).resolve(text)["status"] == "unmatched"
    assert r.resolve("M TH3/5/35")["status"] == "unmatched"
    assert r.resolve("MTH3/5/35x")["status"] == "unmatched"


def test_otm_collection_item_tooltip_is_not_an_edition_guess():
    description = ("Manuskripte aus der Sammlung Example. Ed.: Editor 1997–1998, "
                   "zit. mit Textnummer und Zeile im Manuskript (z. B. OTM184 3)")
    row = parse(WORK.replace("PW", "OTM"))[0]
    row["text"] = description
    r = bib.AuthorityResolver(bib.authority_graph([row])[0], [row])
    expansion = "Manuskript aus der Sammlung Example. Ed.: Editor 1997–1998, Nr. 648"
    evidence = [{"label": "OTM648", "start": 1, "end": 7, "expansion": expansion}]
    result = r.resolve_dom("(OTM648 a7)", evidence)
    assert result["status"] == "exact_online_work_rows"
    assert result["matches"][0]["method"] == "same_dom_item_selector_collection_and_edition_agreement"
    assert result["edition_status"] == "unreviewed"
    for wrong in [expansion.replace("648", "649"), expansion.replace("Example", "Other"),
                  expansion.replace("1997–1998", "2003"), expansion + " extra"]:
        evidence[0]["expansion"] = wrong
        rejected = r.resolve_dom("(OTM648 a7)", evidence)
        assert rejected["status"] == "ambiguous"
        assert rejected["unresolved_dom_components"][0]["target_status"] == "candidate"
        assert "OTM648" in "".join(s["raw_text"] for s in rejected["unparsed_spans"])


def test_acceptance_uses_closed_status_vocabulary():
    result = {"text": "PW", "status": "ambiguous", "matches": [
        {"start": 0, "end": 2, "status": "exact_online_future_unreviewed"}]}
    bib.AuthorityResolver.component_contract(result)
    assert result["matches"][0]["target_status"] == "candidate"
