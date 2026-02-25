# OCR Plan (Tibetan–German Dictionary)

## Goals
- Produce the highest-quality plain-text OCR of the full PDFs.
- Preserve diacritics and Tibetan script in the OCR output.
- Keep the pipeline reproducible and tunable.

## Strategy
1. **Assess existing text layers** using `pdftotext` to decide between:
   - `--skip-text` (OCR only pages without text), or
   - `--force-ocr` (re-OCR everything for consistency).
2. **Pilot OCR** on representative pages (front matter, mid-dictionary, later pages) with different OCR settings.
3. **Choose final settings** based on pilot accuracy.
4. **Run full OCR** with a two-pass pipeline:
   - Pass A (layout/structure): `deu+bod`, `psm 3`
   - Pass B (diacritics): `deu+bod+script/Latin`, `psm 4`
5. **Run full heuristic line-anchor merge** with locked profile (`deu+bod+san+script/Latin`, crop variants, conservative similarity gates).
6. **QA**: sample pages, verify diacritics and Tibetan strings, and estimate character error rate on a small gold sample. Scan for IPA codepoints and review any hits (no auto-filtering).

## Baseline OCR Settings (current)
- Engine: `ocrmypdf` + Tesseract
- Pass A: `--language deu+bod --tesseract-pagesegmode 3 --oversample 400`
- Pass B: `--language deu+bod+script/Latin --tesseract-pagesegmode 4 --oversample 400`
- Both passes use `--force-ocr --output-type none --sidecar` for plain-text output.

## Outputs
- Pass A plain text sidecar (structure)
- Pass B plain text sidecar (diacritics)
- Line-anchored merged text (`*_lineanchored_merged_sample.txt`; filename kept for compatibility even in full runs)
- Line-anchored summary and audit CSVs
- IPA scan report (stdout)

## Next Steps
1. Run `scripts/sample_pages.py` to assess text layers.
2. Run `scripts/ocr_pilot.sh` to OCR selected pages.
3. Review pilot results and adjust settings.

## Notes on Fonts
- If Tibetan glyphs render as boxes in the output PDF, install `NotoSansTibetan-Regular`.
- OCR accuracy is mostly unaffected; this is for PDF text rendering quality.

## Recommended Full OCR Command (resumable two-pass)
Use `scripts/ocr_full_twopass_chunked.sh` for robust runs that survive interruption.

Example (`tmux` + combined stdout/stderr logging):
```bash
tmux new -s wts_ocr
scripts/ocr_full_twopass_chunked.sh "pdfs/WtS 1-34.pdf" "work/full_twopass" 100 2>&1 | tee -a "work/full_twopass/run_1_34_chunked.log"
```

Resume behavior:
- Completed chunks are skipped automatically on rerun.
- Chunk state and logs are stored under `work/full_twopass/<PDF>_chunk_state/`.
- Final merged outputs are written only after all chunks succeed.

Useful overrides:
- `START_PAGE=401 END_PAGE=800` to run a subrange.
- `FORCE_REDO=1` to rerun already-complete chunks.

## Production Heuristic Stage (default after two-pass)
Use `scripts/run_line_anchor_full_locked.sh` to run the full heuristic cleanup on both volumes.

```bash
scripts/run_line_anchor_full_locked.sh "work/line_anchor_full_YYYYMMDDTHHMMSSZ"
```

Resume examples (after an interruption):
```bash
V2_START_PAGE=861 scripts/run_line_anchor_full_locked.sh "work/line_anchor_full_resume_YYYYMMDDTHHMMSSZ"
V1_START_PAGE=401 V1_END_PAGE=900 scripts/run_line_anchor_full_locked.sh "work/line_anchor_full_slice_YYYYMMDDTHHMMSSZ"
```

## QA + Merge Workflow (two-pass outputs)
Use a stratified sample first, then page-level metrics, then deterministic merge.

Sample page diffs:
```bash
scripts/qa_sample_page_diffs.sh "work/qa_samples_YYYYMMDD" "5,400,1200" "5,400,1100"
```

Page-level scoring (conservative: A by default, B only on strong gains):
```bash
scripts/qa_twopass_page_metrics.py \
  "work/full_twopass/WtS 1-34_psm3_deu_bod.txt" \
  "work/full_twopass/WtS 1-34_psm4_deu_bod_lat.txt" \
  --csv work/qa_samples_YYYYMMDD/WtS_1-34_page_metrics.csv \
  --b-candidates work/qa_samples_YYYYMMDD/WtS_1-34_candidate_use_B.txt \
  --review work/qa_samples_YYYYMMDD/WtS_1-34_manual_review.txt
```

Build merged text from explicit page choices:
```bash
scripts/merge_twopass_select_pages.py \
  "work/full_twopass/WtS 1-34_psm3_deu_bod.txt" \
  "work/full_twopass/WtS 1-34_psm4_deu_bod_lat.txt" \
  "work/qa_samples_YYYYMMDD/WtS_1-34_candidate_use_B.txt" \
  --out "work/full_twopass/WtS 1-34_merged_Adefault.txt" \
  --log "work/full_twopass/WtS 1-34_merged_Adefault.log.csv"
```

## Geometry-Anchored Merge Pilot (for quick experiments)
To avoid page-level reflow mismatch, anchor merge on Pass A line geometry.

What it does:
1. Renders sampled pages to PNG.
2. Runs Pass A hOCR to get line boxes/text.
3. Re-runs Pass B only on candidate line crops (`psm 7` and `psm 6`).
4. Applies conservative replacement rules (diacritic gain + similarity + script sanity checks), plus a narrow OCR-confusable fix path.
5. Runs post-merge transliteration cleanup for stable confusions (`$->ś`, `Ita->lta`, `Iha->lha`, `Idan->ldan`, `Itar->ltar`).
6. Emits merged sample text, per-page summary CSV, and per-line audit CSV.

Run 25 pages per PDF:
```bash
scripts/run_line_anchor_pilot.sh "work/line_anchor_pilot_YYYYMMDD"
```

Robust profile (locked defaults):
- `--psm-b-lines 7,6`
- `--min-similarity 0.85`
- `--crop-variants raw,auto,bw180,up2x_auto`
- `--line-timeout-sec 20`

These are now passed explicitly by `scripts/run_line_anchor_pilot.sh` and can be overridden via env vars:
- `PSM_B_LINES`
- `MIN_SIMILARITY`
- `CROP_VARIANTS`
- `LINE_TIMEOUT_SEC`

Run a targeted sample manually:
```bash
python3 scripts/line_anchor_merge_pilot.py \
  "pdfs/WtS 1-34.pdf" \
  --outdir "work/line_anchor_smoke" \
  --pages "34,57,114"
```

Benchmark before full rerun (A/B baseline vs enhanced line-crop OCR):
```bash
bash scripts/benchmark_line_anchor_gain.sh \
  "pdfs/WtS 1-34.pdf" \
  "34,57,114,301,451,601,752,902,1052,1202" \
  "work/line_anchor_benchmark_YYYYMMDD"
```

Latest benchmark notes (2026-02-13):
- `WtS 1-34` sample: replacements `9 -> 13` on the same `147` candidates (`+44%` relative).
- `WtS 35-51` sample: replacements `2 -> 2` on the same `110` candidates (neutral, no regression).

Additional diagnostics (2026-02-13):
- Lowering similarity is not the main lever right now: only 3 candidate lines on the sampled `WtS 1-34` set failed solely on similarity (all around `0.75-0.78` and visibly noisy).
- Main blocker remains `no_diacritic_gain` from line OCR quality, not merge gating.
- Broadening to all-Latin candidate lines is computationally expensive and currently not suitable for full production runs.
- Locked-profile smoke validation with confusable cleanup (3+3 pages) removed the reported stable token errors on those pages (`$`, `Ita`, `Iha`, `Idan` all reduced to `0`), while preserving conservative merge behavior.

## Alternate OCR Settings to Test
- `--tesseract-pagesegmode 6` (single uniform block) for dense dictionary pages
- `--oversample 300` if 400 is too slow
- Avoid `--remove-background` unless it improves Tibetan strokes in tests
