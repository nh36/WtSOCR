#!/usr/bin/env bash
set -euo pipefail

PDF_PATH=${1:?"Usage: ocr_full.sh <input.pdf> <output_dir> [psm] [oversample]"}
OUT_DIR=${2:?"Usage: ocr_full.sh <input.pdf> <output_dir> [psm] [oversample]"}
PSM=${3:-3}
OVERSAMPLE=${4:-400}

mkdir -p "$OUT_DIR"
BASE=$(basename "$PDF_PATH" .pdf)
OUT_PDF="$OUT_DIR/${BASE}_ocr.pdf"
OUT_TXT="$OUT_DIR/${BASE}_ocr.txt"

ocrmypdf \
  --language deu+bod \
  --deskew \
  --rotate-pages \
  --tesseract-pagesegmode "$PSM" \
  --oversample "$OVERSAMPLE" \
  --force-ocr \
  --sidecar "$OUT_TXT" \
  "$PDF_PATH" "$OUT_PDF"

echo "Full OCR complete:"
echo "  PDF: $OUT_PDF"
echo "  TXT: $OUT_TXT"
