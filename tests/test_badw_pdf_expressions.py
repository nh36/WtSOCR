"""Synthetic boundary tests; no copied dictionary corpus or network."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from badw_pdf_expressions import apparatus_spans, boundary_mask, contains_unknown


@pytest.mark.parametrize("text", ["(r.ka)", "(v. l. ka)", "(Gl. ka (r. kha))",
                                    "⟨ka⟩", "{ka}", "[!]", "(metr. )"])
def test_balanced_apparatus_is_literal_and_positioned(text: str) -> None:
    source = "x " + text + " y"
    mask, spans = boundary_mask(source)
    assert (2, 2 + len(text)) in spans
    assert all(mask[2:2 + len(text)])
    assert not mask[0] and not mask[-1]
    assert source[2:2 + len(text)] == text


@pytest.mark.parametrize("text", ["(r. ka", "(r. ka]", "(Source 1)",
                                    "(Gl. ka; German)", "(Gl. „German“)"])
def test_malformed_or_unrecognized_apparatus_is_not_a_bridge(text: str) -> None:
    assert apparatus_spans(text) == []
    assert not all(boundary_mask(text)[0])


@pytest.mark.parametrize("token", [
    "⟦UNKNOWN:Arial:regular:0003:ebbba6ed181c⟧",
    "⟦UNKNOWN:Arial:italic:0003:ebbba6ed181c⟧",
    "⟦UNKNOWN:TT3678AC74tCID-WinCharSetFFFF-H2:regular:065B:ce91b893d20f⟧",
])
def test_verified_empty_outlines_are_boundaries_not_unicode_replacements(token: str) -> None:
    assert all(boundary_mask(token)[0])
    assert not contains_unknown(token)
    assert "UNKNOWN" in token  # No source mutation.


@pytest.mark.parametrize("token", [
    "⟦UNKNOWN:Arial:regular:0003:differentoutline⟧",
    "⟦UNKNOWN:Arial:bold:0003:ebbba6ed181c⟧",
    "⟦UNKNOWN:RabtenTibetan:regular:0003:ebbba6ed181c⟧",
    "⟦UNKNOWN:MicrosoftSansSerif:regular:0003:6dc2ca034cbe⟧",
    "⟦UNKNOWN:TGaramond:italic:00E2:960b47bc4fc7⟧",
])
def test_other_unknown_identity_is_not_a_layout_exception(token: str) -> None:
    assert contains_unknown(token)
    assert not all(boundary_mask(token)[0])
