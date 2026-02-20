#!/usr/bin/env bash
set -euo pipefail

PDF_PATH=${1:-"pdfs/WtS 1-34.pdf"}
PAGES=${2:-"5,200,400,800,1200"}
OUT_DIR=${3:-"work/pilot"}
FORCE_OCR=${FORCE_OCR:-1}

mkdir -p "$OUT_DIR"
BASE=$(basename "$PDF_PATH" .pdf)
OUT_PDF="$OUT_DIR/${BASE}_pilot.pdf"
OUT_TXT="$OUT_DIR/${BASE}_pilot.txt"

OCR_FLAGS=()
if [ "$FORCE_OCR" = "1" ]; then
  OCR_FLAGS+=(--force-ocr)
fi

ocrmypdf \
  --language deu+bod \
  --deskew \
  --rotate-pages \
  "${OCR_FLAGS[@]}" \
  --pages "$PAGES" \
  --sidecar "$OUT_TXT" \
  "$PDF_PATH" "$OUT_PDF"

echo "Pilot OCR complete:"
echo "  PDF: $OUT_PDF"
echo "  TXT: $OUT_TXT"
