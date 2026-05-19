# Google Witness Rewrapped Page Fallback Audit

Date: 2026-05-19

## Rationale

Google Vision pages often contain the same dictionary page content as the locked
line-anchor OCR witness, but with different line wrapping. The previous page
alignment layer treated many of these same-page witnesses as
`unalignable_rewrapped_page`, which prevented the existing token-gated Google
witness adoption rules from seeing otherwise useful alternate tokens.

The guarded fallback was added only to create a token-comparison structure for
these rewrapped pages. It does not replace base lines with raw Google text.

## Fallback Gates

The fallback applies only when all of these alignment-layer gates pass:

- The best alternate candidate is inside the searched page window.
- Candidate score is at least 0.50.
- The alternate page is same/near page: `abs(best_alt - base_page) <= 2`.
- Non-empty line-count ratio is plausible: `0.5 <= ratio <= 2.0`.
- Canonical token overlap coefficient is at least 0.35.
- At least 10 canonical tokens are shared.
- Any token adoption still passes the existing `alternate_witness_reason` logic.

The fallback compares token runs only. Full-line Google replacement remains
forbidden, especially because Google can introduce leading digit garbage or
other OCR noise.

## Verification Counts

Verification output directory:
`work/postprocess_google_arbitrated_verify_20260519T083005Z/`

Before fallback:

- `wts_1_34`: 5 alternate-witness adoptions.
- `wts_35_51`: 3 alternate-witness adoptions.

After fallback:

- `wts_1_34`: 34 alternate-witness adoptions.
- `wts_35_51`: 1164 alternate-witness adoptions.

The `wts_35_51` jump is now understood. The shadow estimate treated eligible
rewrapped pages roughly as adoption opportunities, but the implementation
properly applies token-level adoption across each eligible page. The fallback
directly accepted 152 same-page candidates and produced 1086 of the 1161 new
`wts_35_51` adoptions. The remaining 75 came from downstream resynchronization
effects after page alignment improved.

## High-Risk Audit

The audit sampled the highest-risk adoption categories in `wts_35_51`:

- 100 `alternate_witness_google_loc_nasal_upgrade` cases.
- 50 `alternate_witness_initial_i_to_l_translit` cases.
- All 40 `alternate_witness_google_loc_velar_nasal_upgrade` cases.
- All pages with more than 50 adoptions; there were none.

No bad cases were found in the sampled high-risk categories. Known noisy Google
leading digit patterns such as `55 gdun` and `155 gdun` appeared in the raw
Google OCR, but did not produce adoption rows.

## Caveat

Some downstream resynchronization adoptions would benefit from clearer
attribution diagnostics later, so future audits can distinguish direct fallback
adoptions from secondary effects. That should be diagnostic-only unless a later
sample shows unsafe behavior.
