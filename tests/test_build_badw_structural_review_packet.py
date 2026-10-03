import pytest

from build_badw_structural_review_packet import select


def inputs():
    pdf = [{"article_id": f"{v}-{i}", "volume": v, "source_objects": [],
            "source_faithful_text": "text", "visual_lines": [{"text": "x"*i + "„"*(i%5)}],
            "divisions": ["MUST NOT LEAK"], "candidates": {"gold": "NOT GOLD"}}
           for v in (2, 3, 4) for i in range(36)]
    html = [{"source_identifier": f"html-{i}", "source_object": {"sha256": str(i)},
             "article_source_text": "x"*i, "dom_full_text": "original",
             "meanings": ["MUST NOT LEAK"]} for i in range(36)]
    return pdf, html


def test_packet_is_blinded_deterministic_and_not_gold():
    pdf, html = inputs()
    packet = select(pdf, html)
    assert packet == select(reversed(pdf), reversed(html))
    assert len(packet) == 120
    assert sum(r["split"] == "holdout" for r in packet) == 24
    assert len({r["identity"] for r in packet}) == 120
    assert all(r["review_status"] == "pending_independent_review" and not r["reviewed_nodes"] for r in packet)
    assert all("meanings" not in r["source"] and "divisions" not in r["source"] and "candidates" not in r["source"] for r in packet)


def test_insufficient_or_duplicate_sources_rejected():
    pdf, html = inputs()
    with pytest.raises(ValueError, match="duplicate"):
        select(pdf + [pdf[0]], html)
    with pytest.raises(ValueError, match="insufficient"):
        select(pdf[:3], html)
