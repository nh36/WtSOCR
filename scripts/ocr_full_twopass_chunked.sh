#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ocr_full_twopass_chunked.sh <input.pdf> <output_dir> [chunk_size]

Environment overrides:
  START_PAGE=1      First page to process (default: 1)
  END_PAGE=N        Last page to process (default: PDF page count)
  FORCE_REDO=0      Set to 1 to rerun chunks even if done markers exist

This script runs two OCR passes in resumable page chunks and then merges chunk
sidecars into final outputs.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

PDF_PATH=${1:?"Usage: ocr_full_twopass_chunked.sh <input.pdf> <output_dir> [chunk_size]"}
OUT_DIR=${2:?"Usage: ocr_full_twopass_chunked.sh <input.pdf> <output_dir> [chunk_size]"}
CHUNK_SIZE=${3:-100}

PSM_A=3
PSM_B=4
OVERSAMPLE_A=400
OVERSAMPLE_B=400
LANG_A="deu+bod"
LANG_B="deu+bod+script/Latin"

START_PAGE=${START_PAGE:-1}
FORCE_REDO=${FORCE_REDO:-0}

if ! [[ "$CHUNK_SIZE" =~ ^[0-9]+$ ]] || [ "$CHUNK_SIZE" -lt 1 ]; then
  echo "Invalid chunk size: $CHUNK_SIZE" >&2
  exit 1
fi
if ! [[ "$START_PAGE" =~ ^[0-9]+$ ]] || [ "$START_PAGE" -lt 1 ]; then
  echo "Invalid START_PAGE: $START_PAGE" >&2
  exit 1
fi
if ! command -v ocrmypdf >/dev/null 2>&1; then
  echo "Missing required command: ocrmypdf" >&2
  exit 1
fi
if ! command -v pdfinfo >/dev/null 2>&1; then
  echo "Missing required command: pdfinfo" >&2
  exit 1
fi

TOTAL_PAGES=$(pdfinfo "$PDF_PATH" | awk '/^Pages:/ {print $2}')
if ! [[ "$TOTAL_PAGES" =~ ^[0-9]+$ ]] || [ "$TOTAL_PAGES" -lt 1 ]; then
  echo "Failed to read page count from pdfinfo for: $PDF_PATH" >&2
  exit 1
fi

END_PAGE=${END_PAGE:-$TOTAL_PAGES}
if ! [[ "$END_PAGE" =~ ^[0-9]+$ ]] || [ "$END_PAGE" -lt "$START_PAGE" ]; then
  echo "Invalid END_PAGE: $END_PAGE" >&2
  exit 1
fi
if [ "$END_PAGE" -gt "$TOTAL_PAGES" ]; then
  END_PAGE=$TOTAL_PAGES
fi

mkdir -p "$OUT_DIR"
BASE=$(basename "$PDF_PATH" .pdf)

STATE_DIR="$OUT_DIR/${BASE}_chunk_state"
CHUNK_DIR="$STATE_DIR/chunks"
LOG_DIR="$STATE_DIR/logs"
mkdir -p "$CHUNK_DIR" "$LOG_DIR"

OUT_A="$OUT_DIR/${BASE}_psm${PSM_A}_deu_bod.txt"
OUT_B="$OUT_DIR/${BASE}_psm${PSM_B}_deu_bod_lat.txt"

echo "[chunked] PDF: $PDF_PATH"
echo "[chunked] Pages: $TOTAL_PAGES"
echo "[chunked] Range: $START_PAGE-$END_PAGE (chunk size $CHUNK_SIZE)"
echo "[chunked] Force redo: $FORCE_REDO"
echo "[chunked] State dir: $STATE_DIR"

run_chunk_pass() {
  local chunk_start=$1
  local chunk_end=$2
  local pass=$3
  local lang=$4
  local psm=$5
  local oversample=$6
  local sidecar=$7
  local done_marker=$8
  local log_file=$9

  if [ "$FORCE_REDO" = "0" ] && [ -f "$done_marker" ] && [ -s "$sidecar" ]; then
    echo "[chunked] Skip pass $pass pages $chunk_start-$chunk_end (already done)"
    return 0
  fi

  rm -f "$done_marker"
  echo "[chunked] Pass $pass pages $chunk_start-$chunk_end lang=$lang psm=$psm oversample=$oversample"
  ocrmypdf \
    --language "$lang" \
    --tesseract-pagesegmode "$psm" \
    --oversample "$oversample" \
    --force-ocr \
    --pages "${chunk_start}-${chunk_end}" \
    --output-type none \
    --sidecar "$sidecar" \
    "$PDF_PATH" - 2>&1 | tee -a "$log_file"

  date -u +"%Y-%m-%dT%H:%M:%SZ pass=$pass pages=${chunk_start}-${chunk_end}" > "$done_marker"
}

chunk_start=$START_PAGE
while [ "$chunk_start" -le "$END_PAGE" ]; do
  chunk_end=$((chunk_start + CHUNK_SIZE - 1))
  if [ "$chunk_end" -gt "$END_PAGE" ]; then
    chunk_end=$END_PAGE
  fi

  label=$(printf "p%04d-%04d" "$chunk_start" "$chunk_end")
  chunk_a="$CHUNK_DIR/${BASE}_${label}_psm${PSM_A}_deu_bod.txt"
  chunk_b="$CHUNK_DIR/${BASE}_${label}_psm${PSM_B}_deu_bod_lat.txt"
  done_a="$CHUNK_DIR/${BASE}_${label}.passA.done"
  done_b="$CHUNK_DIR/${BASE}_${label}.passB.done"
  log_a="$LOG_DIR/${BASE}_${label}.passA.log"
  log_b="$LOG_DIR/${BASE}_${label}.passB.log"

  run_chunk_pass "$chunk_start" "$chunk_end" "A" "$LANG_A" "$PSM_A" "$OVERSAMPLE_A" "$chunk_a" "$done_a" "$log_a"
  run_chunk_pass "$chunk_start" "$chunk_end" "B" "$LANG_B" "$PSM_B" "$OVERSAMPLE_B" "$chunk_b" "$done_b" "$log_b"

  chunk_start=$((chunk_end + 1))
done

echo "[chunked] Verifying chunk completeness before merge"
chunk_start=$START_PAGE
while [ "$chunk_start" -le "$END_PAGE" ]; do
  chunk_end=$((chunk_start + CHUNK_SIZE - 1))
  if [ "$chunk_end" -gt "$END_PAGE" ]; then
    chunk_end=$END_PAGE
  fi
  label=$(printf "p%04d-%04d" "$chunk_start" "$chunk_end")

  done_a="$CHUNK_DIR/${BASE}_${label}.passA.done"
  done_b="$CHUNK_DIR/${BASE}_${label}.passB.done"
  chunk_a="$CHUNK_DIR/${BASE}_${label}_psm${PSM_A}_deu_bod.txt"
  chunk_b="$CHUNK_DIR/${BASE}_${label}_psm${PSM_B}_deu_bod_lat.txt"

  if [ ! -f "$done_a" ] || [ ! -s "$chunk_a" ]; then
    echo "Missing Pass A chunk for $label; aborting merge." >&2
    exit 1
  fi
  if [ ! -f "$done_b" ] || [ ! -s "$chunk_b" ]; then
    echo "Missing Pass B chunk for $label; aborting merge." >&2
    exit 1
  fi

  expected_pages=$((chunk_end - chunk_start + 1))
  actual_a=$(awk 'BEGIN{RS="\f"} !/^\[OCR skipped on page\(s\) [0-9-]+\]$/ {n++} END{print n+0}' "$chunk_a")
  actual_b=$(awk 'BEGIN{RS="\f"} !/^\[OCR skipped on page\(s\) [0-9-]+\]$/ {n++} END{print n+0}' "$chunk_b")
  if [ "$actual_a" -ne "$expected_pages" ]; then
    echo "Pass A chunk $label page-count mismatch: expected $expected_pages, got $actual_a" >&2
    exit 1
  fi
  if [ "$actual_b" -ne "$expected_pages" ]; then
    echo "Pass B chunk $label page-count mismatch: expected $expected_pages, got $actual_b" >&2
    exit 1
  fi
  chunk_start=$((chunk_end + 1))
done

echo "[chunked] Merging chunk outputs"
a_files=()
b_files=()
chunk_start=$START_PAGE
while [ "$chunk_start" -le "$END_PAGE" ]; do
  chunk_end=$((chunk_start + CHUNK_SIZE - 1))
  if [ "$chunk_end" -gt "$END_PAGE" ]; then
    chunk_end=$END_PAGE
  fi
  label=$(printf "p%04d-%04d" "$chunk_start" "$chunk_end")
  a_files+=("$CHUNK_DIR/${BASE}_${label}_psm${PSM_A}_deu_bod.txt")
  b_files+=("$CHUNK_DIR/${BASE}_${label}_psm${PSM_B}_deu_bod_lat.txt")
  chunk_start=$((chunk_end + 1))
done

awk 'BEGIN{RS="\f"; ORS=""} !/^\[OCR skipped on page\(s\) [0-9-]+\]$/ {if (seen) printf "\f"; printf "%s", $0; seen=1}' "${a_files[@]}" > "$OUT_A"
awk 'BEGIN{RS="\f"; ORS=""} !/^\[OCR skipped on page\(s\) [0-9-]+\]$/ {if (seen) printf "\f"; printf "%s", $0; seen=1}' "${b_files[@]}" > "$OUT_B"

echo "[chunked] IPA scan (no filtering)"
/Users/nathanhill/WtSOCR/scripts/ipa_scan.py "$OUT_A" "$OUT_B"

echo "[chunked] Done"
echo "  Pass A: $OUT_A"
echo "  Pass B: $OUT_B"
echo "  Chunk logs: $LOG_DIR"
