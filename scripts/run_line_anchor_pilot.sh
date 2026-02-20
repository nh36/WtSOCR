#!/usr/bin/env bash
set -euo pipefail

OUT_ROOT=${1:-"work/line_anchor_pilot_$(date +%Y%m%d_%H%M%S)"}
SAMPLE_PER_PDF=${SAMPLE_PER_PDF:-25}
DPI=${DPI:-300}
PSM_B_LINES=${PSM_B_LINES:-"7,6"}
MIN_SIMILARITY=${MIN_SIMILARITY:-"0.85"}
CROP_VARIANTS=${CROP_VARIANTS:-"raw,auto,bw180,up2x_auto"}
LINE_TIMEOUT_SEC=${LINE_TIMEOUT_SEC:-"20"}

mkdir -p "$OUT_ROOT"

echo "[pilot] out_root=$OUT_ROOT"
echo "[pilot] sample_per_pdf=$SAMPLE_PER_PDF dpi=$DPI"
echo "[pilot] psm_b_lines=$PSM_B_LINES min_similarity=$MIN_SIMILARITY"
echo "[pilot] crop_variants=$CROP_VARIANTS"
echo "[pilot] line_timeout_sec=$LINE_TIMEOUT_SEC"

python3 scripts/line_anchor_merge_pilot.py \
  "pdfs/WtS 1-34.pdf" \
  --outdir "$OUT_ROOT/WtS_1-34" \
  --sample-count "$SAMPLE_PER_PDF" \
  --dpi "$DPI" \
  --psm-b-lines "$PSM_B_LINES" \
  --min-similarity "$MIN_SIMILARITY" \
  --crop-variants "$CROP_VARIANTS" \
  --line-timeout-sec "$LINE_TIMEOUT_SEC" \
  2>&1 | tee "$OUT_ROOT/WtS_1-34.log"

python3 scripts/line_anchor_merge_pilot.py \
  "pdfs/WtS 35-51.pdf" \
  --outdir "$OUT_ROOT/WtS_35-51" \
  --sample-count "$SAMPLE_PER_PDF" \
  --dpi "$DPI" \
  --psm-b-lines "$PSM_B_LINES" \
  --min-similarity "$MIN_SIMILARITY" \
  --crop-variants "$CROP_VARIANTS" \
  --line-timeout-sec "$LINE_TIMEOUT_SEC" \
  2>&1 | tee "$OUT_ROOT/WtS_35-51.log"

echo "[pilot] complete"
