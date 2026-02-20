#!/usr/bin/env bash
set -euo pipefail

PDF_PATH=${1:-"pdfs/WtS 1-34.pdf"}
PAGES=${2:-"200,800,1200"}
OUT_DIR=${3:-"work/pilot_compare"}

mkdir -p "$OUT_DIR"
BASE=$(basename "$PDF_PATH" .pdf)

run_cfg() {
  local label=$1
  local psm=$2
  local oversample=$3
  local out_txt="$OUT_DIR/${BASE}_${label}.txt"

  ocrmypdf \
    --language deu+bod \
    --deskew \
    --rotate-pages \
    --tesseract-pagesegmode "$psm" \
    --oversample "$oversample" \
    --force-ocr \
    --pages "$PAGES" \
    --output-type none \
    --sidecar "$out_txt" \
    "$PDF_PATH" -

  echo "Done: $label -> $out_txt"
}

run_cfg "psm3_os400" 3 400
run_cfg "psm6_os400" 6 400
