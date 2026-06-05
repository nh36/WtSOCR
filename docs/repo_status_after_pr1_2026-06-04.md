# Repository Status After PR #1

Date: 2026-06-04

## Trusted Main State

- Branch checked: `main`
- Pre-diagnostics trusted baseline commit: `f35811e825cad284101aa5d98e0c25215de03bb2`
- Current diagnostics commit under review: `ed14e57e801c3ffba62c4448552bcaae9ea5fa07`
- Latest trusted PR: PR #1, `nh36/loc-end-to-end-audit`, merged by commit `f35811e825`
- Baseline regression check before diagnostics edits: `84 passed in 0.63s`
- Post-diagnostics regression check: `85 passed in 0.55s`

The 83-vs-84 discrepancy is reconciled as stale PR-body text versus the merged main state. The current main regression test file reports 84 passing tests before the new diagnostics-only regression test; after adding that test, the count is 85.

## Copilot Review Follow-up

All three review concerns are addressed on main:

- OCR text reads tolerate malformed UTF-8 explicitly with `errors="replace"` in `scripts/postprocess_entry_map.py`.
- Chunk verification no longer depends on an undocumented Perl call; `scripts/ocr_full_twopass_chunked.sh` uses shell tools for the form-feed check.
- The regression test module loader raises `ImportError` instead of relying on a bare `assert`.

## Source PDF Inventory

| Label | Path | Pages | Size bytes | SHA-256 | Status |
| --- | --- | ---: | ---: | --- | --- |
| WtS_1-34 | `pdfs/WtS 1-34.pdf` | 1352 | 110232410 | `20021354ae3c838a5641f59af4a4421c1e59e6b0d2c1760d5fe3f62faeb47c62` | ingested |
| WtS_35-51 | `pdfs/WtS 35-51.pdf` | 1128 | 79764217 | `8babd045a04876d373631169677eff7fc033066a3ed1f5649aeaaad5eed67239` | ingested |
| WtS_8-b | `pdfs/WtS 8-b.pdf` | 585 | 97173325 | `f9d94766c88362472576250c34dcc313c55e3036e19dcfe454e0a82b9d1d4263` | ingested |
| WtS_9-m | `pdfs/WtS 9-m.pdf` | 401 | 71529965 | `7c9366616d41c2788088085208e5395111d19abb31bb801a03443af14910ffeb` | ingested |

Google Vision witness text is also present for all four volumes under `pdfs/*.vision.txt`.

## Latest Verification Outputs

Previous trusted verification snapshot:

- Directory: `work/postprocess_google_arbitrated_verify_20260519T083005Z`
- `wts_1_34`: 34 alternate-witness adoptions, 3034 unresolved rows
- `wts_35_51`: 1164 alternate-witness adoptions, 1893 unresolved rows

Current refined-attribution diagnostics QA bundle:

- Directory: `work/postprocess_google_attribution_refined_qa_20260605T072002Z`
- `wts_1_34`: 5471 alternate-witness adoptions, 3232 unresolved rows
- `wts_35_51`: 1317 alternate-witness adoptions, 2034 unresolved rows
- Bundle includes corrected text, changes TSVs, alternate-witness adoption and unresolved TSVs, bucket reports, checksums, and `manual_audit_sample.tsv`.

The refined-attribution rerun changes only adoption attribution labels. Corrected text files, changes TSVs, unresolved TSVs, adoption row counts, and unresolved row counts match the `work/postprocess_google_attribution_qa_20260604T221702Z` bundle exactly. The adoption TSVs differ only in `resynchronization_attribution` and `resynchronization_source` fields: 134 rows in `wts_1_34` and 46 rows in `wts_35_51`.

Recorded attribution breakdown before refinement:

| Volume | Ordinary page alignment | Rewrapped page alignment | Recovered rewrapped fallback | Downstream after fallback |
| --- | ---: | ---: | ---: | ---: |
| `wts_1_34` | 7 | 145 | 5319 | 149 |
| `wts_35_51` | 5 | 41 | 1271 | 46 |

Refined attribution breakdown:

| Volume | Ordinary page alignment | Rewrapped page alignment | Recovered rewrapped fallback | Direct same/offset page | Downstream after fallback |
| --- | ---: | ---: | ---: | ---: | ---: |
| `wts_1_34` | 7 | 145 | 5319 | 137 | 15 |
| `wts_35_51` | 5 | 41 | 1271 | 46 | 0 |

## Known Caveats

- The May 2026 verification snapshot predates later curated OCR, Sanskrit, and citation changes now present on `main`. Its corrected-text checksums are expected to differ from the current-main QA bundle because of those text-normalisation commits; diagnostics-only attribution changes should not change corrected text.
- `scripts/generate_production_qa_report.py` is not present on merged main. Current verification uses `scripts/postprocess_entry_map.py`, `scripts/report_unresolved_buckets.py`, and existing QA packet helpers.
- WtS 8-b and WtS 9-m source PDFs and Google Vision witnesses are present. The existing PDF_3/PDF_4 runner path is documented below for the next full OCR pass.

## Reproduction Commands

The `work/` directories named below are local generated artifacts. They are not versioned in the repository; rerunning these commands recreates them locally.

Regression and syntax checks:

```bash
python3 -m pytest tests/test_postprocess_regressions.py -q
python3 -m py_compile scripts/postprocess_entry_map.py scripts/build_qa_packet_v6.py scripts/report_unresolved_buckets.py
```

Rebuild the current refined-attribution two-volume QA bundle:

```bash
OUT=work/postprocess_google_attribution_refined_qa_20260605T072002Z

python3 scripts/postprocess_entry_map.py \
  --merged "work/full_twopass/WtS 1-34_merged_Adefault.txt" \
  --outdir "$OUT/wts_1_34" \
  --label wts_1_34 \
  --alternate-merged "pdfs/WtS 1-34.vision.txt" \
  --alternate-google-vision

python3 scripts/postprocess_entry_map.py \
  --merged "work/full_twopass/WtS 35-51_merged_Adefault.txt" \
  --outdir "$OUT/wts_35_51" \
  --label wts_35_51 \
  --alternate-merged "pdfs/WtS 35-51.vision.txt" \
  --alternate-google-vision

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT/wts_1_34" \
  --out-prefix "$OUT/wts_1_34/bucket_report"

python3 scripts/report_unresolved_buckets.py \
  --run-dir "$OUT/wts_35_51" \
  --out-prefix "$OUT/wts_35_51/bucket_report"
```

Regenerate checksums for the QA bundle:

```bash
python3 - <<'PY'
import hashlib
from pathlib import Path

root = Path("work/postprocess_google_attribution_refined_qa_20260605T072002Z")
with (root / "checksums.sha256").open("w", encoding="utf-8") as out:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            out.write(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n")
PY
```

Proceed to WtS 8-b and WtS 9-m through the existing optional PDF runner path:

```bash
PDF_3="pdfs/WtS 8-b.pdf" \
LABEL_3="WtS_8-b" \
PDF_4="pdfs/WtS 9-m.pdf" \
LABEL_4="WtS_9-m" \
scripts/run_line_anchor_full_locked.sh "work/line_anchor_full_YYYYMMDDTHHMMSSZ"
```
