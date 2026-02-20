#!/usr/bin/env bash
set -euo pipefail

PDF_PATH=${1:?"Usage: ocr_full_twopass.sh <input.pdf> <output_dir>"}
OUT_DIR=${2:?"Usage: ocr_full_twopass.sh <input.pdf> <output_dir>"}

PSM_A=3
PSM_B=4
OVERSAMPLE_A=400
OVERSAMPLE_B=400
LANG_A="deu+bod"
LANG_B="deu+bod+script/Latin"

mkdir -p "$OUT_DIR"
BASE=$(basename "$PDF_PATH" .pdf)
OUT_A="$OUT_DIR/${BASE}_psm${PSM_A}_deu_bod.txt"
OUT_B="$OUT_DIR/${BASE}_psm${PSM_B}_deu_bod_lat.txt"

echo "[twopass] Pass A: $LANG_A psm=$PSM_A oversample=$OVERSAMPLE_A"
ocrmypdf \
  --language "$LANG_A" \
  --tesseract-pagesegmode "$PSM_A" \
  --oversample "$OVERSAMPLE_A" \
  --force-ocr \
  --output-type none \
  --sidecar "$OUT_A" \
  "$PDF_PATH" -

echo "[twopass] Pass B: $LANG_B psm=$PSM_B oversample=$OVERSAMPLE_B"
ocrmypdf \
  --language "$LANG_B" \
  --tesseract-pagesegmode "$PSM_B" \
  --oversample "$OVERSAMPLE_B" \
  --force-ocr \
  --output-type none \
  --sidecar "$OUT_B" \
  "$PDF_PATH" -

echo "[twopass] IPA scan (no filtering)"
/Users/nathanhill/WtSOCR/scripts/ipa_scan.py "$OUT_A" "$OUT_B"

echo "[twopass] Done"
echo "  Pass A: $OUT_A"
echo "  Pass B: $OUT_B"
