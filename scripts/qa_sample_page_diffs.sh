#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-"work/qa_samples"}
VOL1_PAGES=${2:-"5,400,1200"}
VOL2_PAGES=${3:-"5,400,1100"}
CHUNK_SIZE=${CHUNK_SIZE:-100}

BASE_DIR="work/full_twopass"
VOL1="WtS 1-34"
VOL2="WtS 35-51"

mkdir -p "$OUT_DIR"

extract_page_from_chunk() {
  local chunk_file=$1
  local page_in_chunk=$2
  local out_file=$3
  awk -v n="$page_in_chunk" '
    BEGIN{RS="\f"}
    /^\[OCR skipped on page\(s\) [0-9-]+\]$/ {next}
    {k++; if(k==n) {print; found=1; exit}}
    END{if(!found) exit 2}
  ' "$chunk_file" > "$out_file"
}

emit_one() {
  local vol=$1
  local page=$2
  local state_dir="$BASE_DIR/${vol}_chunk_state/chunks"
  local chunk_start=$(( ((page - 1) / CHUNK_SIZE) * CHUNK_SIZE + 1 ))
  local chunk_end=$(( chunk_start + CHUNK_SIZE - 1 ))
  local page_in_chunk=$(( page - chunk_start + 1 ))

  if [ "$vol" = "$VOL1" ] && [ "$chunk_end" -gt 1352 ]; then
    chunk_end=1352
  fi
  if [ "$vol" = "$VOL2" ] && [ "$chunk_end" -gt 1128 ]; then
    chunk_end=1128
  fi

  local label
  label=$(printf "p%04d-%04d" "$chunk_start" "$chunk_end")
  local file_a="$state_dir/${vol}_${label}_psm3_deu_bod.txt"
  local file_b="$state_dir/${vol}_${label}_psm4_deu_bod_lat.txt"

  if [ ! -f "$file_a" ] || [ ! -f "$file_b" ]; then
    echo "Missing chunk files for $vol page $page ($label)" >&2
    return 1
  fi

  local stem
  stem=$(printf "%s_page_%04d" "$vol" "$page")
  local out_a="$OUT_DIR/${stem}.passA.txt"
  local out_b="$OUT_DIR/${stem}.passB.txt"
  local out_d="$OUT_DIR/${stem}.diff.txt"

  extract_page_from_chunk "$file_a" "$page_in_chunk" "$out_a"
  extract_page_from_chunk "$file_b" "$page_in_chunk" "$out_b"

  if diff -u "$out_a" "$out_b" > "$out_d"; then
    : > "$out_d"
    echo "$stem: identical"
  else
    local adds dels
    adds=$(grep -cE '^\+[^+]' "$out_d" || true)
    dels=$(grep -cE '^\-[^-]' "$out_d" || true)
    echo "$stem: different (+$adds / -$dels)"
  fi
}

split_csv() {
  tr ',' '\n' <<< "$1" | sed '/^[[:space:]]*$/d'
}

echo "[qa] Output dir: $OUT_DIR"
echo "[qa] Volume 1 pages: $VOL1_PAGES"
while IFS= read -r p; do
  emit_one "$VOL1" "$p"
done < <(split_csv "$VOL1_PAGES")

echo "[qa] Volume 2 pages: $VOL2_PAGES"
while IFS= read -r p; do
  emit_one "$VOL2" "$p"
done < <(split_csv "$VOL2_PAGES")

echo "[qa] Done"
