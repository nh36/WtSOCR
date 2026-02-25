#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  run_line_anchor_full_locked.sh [out_root]

Runs full-volume line-anchored heuristic OCR merge for both dictionary PDFs.
This is the locked production profile for transliteration/Tibetan/Sanskrit cleanup.

Arguments:
  out_root                Output root directory (default: work/line_anchor_full_<UTC timestamp>)

Environment overrides:
  PDF_1="pdfs/WtS 1-34.pdf"
  PDF_2="pdfs/WtS 35-51.pdf"
  LABEL_1="WtS_1-34"
  LABEL_2="WtS_35-51"

  V1_START_PAGE=1         Optional resume start page for volume 1
  V1_END_PAGE=0           Optional end page for volume 1 (0 = full to PDF end)
  V2_START_PAGE=1         Optional resume start page for volume 2
  V2_END_PAGE=0           Optional end page for volume 2 (0 = full to PDF end)

  DPI=300
  LANG_A="deu+bod"
  LANG_B="deu+bod+san+script/Latin"
  PSM_A=3
  PSM_B_LINES="7,6"
  PSM_B_LINES_TIB="7,13,6"
  CROP_VARIANTS="raw,auto,bw180,up2x_auto"
  MIN_SIMILARITY=0.85
  MIN_SIMILARITY_DIACRITIC_ONLY=0.78
  MIN_SIMILARITY_TIBETAN_ANCHOR=0.73
  LINE_TIMEOUT_SEC=20
  CANDIDATE_MODE="heuristic"
  PAGE_SEPARATOR="formfeed"
  ANOMALY_REPORT=1        Set to 0 to disable anomaly CSV output
  DEHYPHENATE_WRAP=0      Set to 1 to enable wrapped-word dehyphenation
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing required command: python3" >&2
  exit 1
fi

OUT_ROOT=${1:-"work/line_anchor_full_$(date -u +%Y%m%dT%H%M%SZ)"}
PDF_1=${PDF_1:-"pdfs/WtS 1-34.pdf"}
PDF_2=${PDF_2:-"pdfs/WtS 35-51.pdf"}
LABEL_1=${LABEL_1:-"WtS_1-34"}
LABEL_2=${LABEL_2:-"WtS_35-51"}

V1_START_PAGE=${V1_START_PAGE:-1}
V1_END_PAGE=${V1_END_PAGE:-0}
V2_START_PAGE=${V2_START_PAGE:-1}
V2_END_PAGE=${V2_END_PAGE:-0}

DPI=${DPI:-300}
LANG_A=${LANG_A:-"deu+bod"}
LANG_B=${LANG_B:-"deu+bod+san+script/Latin"}
PSM_A=${PSM_A:-3}
PSM_B_LINES=${PSM_B_LINES:-"7,6"}
PSM_B_LINES_TIB=${PSM_B_LINES_TIB:-"7,13,6"}
CROP_VARIANTS=${CROP_VARIANTS:-"raw,auto,bw180,up2x_auto"}
MIN_SIMILARITY=${MIN_SIMILARITY:-0.85}
MIN_SIMILARITY_DIACRITIC_ONLY=${MIN_SIMILARITY_DIACRITIC_ONLY:-0.78}
MIN_SIMILARITY_TIBETAN_ANCHOR=${MIN_SIMILARITY_TIBETAN_ANCHOR:-0.73}
LINE_TIMEOUT_SEC=${LINE_TIMEOUT_SEC:-20}
CANDIDATE_MODE=${CANDIDATE_MODE:-heuristic}
PAGE_SEPARATOR=${PAGE_SEPARATOR:-formfeed}
ANOMALY_REPORT=${ANOMALY_REPORT:-1}
DEHYPHENATE_WRAP=${DEHYPHENATE_WRAP:-0}

require_pdf() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "Missing input PDF: $p" >&2
    exit 1
  fi
}

require_int_ge() {
  local name="$1"
  local value="$2"
  local min="$3"
  if ! [[ "$value" =~ ^[0-9]+$ ]]; then
    echo "Invalid $name: $value (must be integer >= $min)" >&2
    exit 1
  fi
  if (( value < min )); then
    echo "Invalid $name: $value (must be >= $min)" >&2
    exit 1
  fi
}

require_pdf "$PDF_1"
require_pdf "$PDF_2"
require_int_ge "V1_START_PAGE" "$V1_START_PAGE" 1
require_int_ge "V1_END_PAGE" "$V1_END_PAGE" 0
require_int_ge "V2_START_PAGE" "$V2_START_PAGE" 1
require_int_ge "V2_END_PAGE" "$V2_END_PAGE" 0

mkdir -p "$OUT_ROOT"

echo "[line-anchor-full] out_root=$OUT_ROOT"
echo "[line-anchor-full] profile: lang_b=$LANG_B psm_b_lines=$PSM_B_LINES psm_b_lines_tib=$PSM_B_LINES_TIB"
echo "[line-anchor-full] profile: crop_variants=$CROP_VARIANTS min_similarity=$MIN_SIMILARITY min_similarity_diacritic_only=$MIN_SIMILARITY_DIACRITIC_ONLY min_similarity_tibetan_anchor=$MIN_SIMILARITY_TIBETAN_ANCHOR"
echo "[line-anchor-full] profile: line_timeout_sec=$LINE_TIMEOUT_SEC anomaly_report=$ANOMALY_REPORT dehyphenate_wrap=$DEHYPHENATE_WRAP"

run_volume() {
  local pdf="$1"
  local label="$2"
  local start_page="$3"
  local end_page="$4"
  local outdir="$OUT_ROOT/$label"
  local log="$OUT_ROOT/${label}.log"

  mkdir -p "$outdir"

  local -a cmd=(
    python3 scripts/line_anchor_merge_pilot.py
    "$pdf"
    --outdir "$outdir"
    --all-pages
    --start-page "$start_page"
    --dpi "$DPI"
    --lang-a "$LANG_A"
    --lang-b "$LANG_B"
    --psm-a "$PSM_A"
    --psm-b-lines "$PSM_B_LINES"
    --psm-b-lines-tib "$PSM_B_LINES_TIB"
    --crop-variants "$CROP_VARIANTS"
    --min-similarity "$MIN_SIMILARITY"
    --min-similarity-diacritic-only "$MIN_SIMILARITY_DIACRITIC_ONLY"
    --min-similarity-tibetan-anchor "$MIN_SIMILARITY_TIBETAN_ANCHOR"
    --line-timeout-sec "$LINE_TIMEOUT_SEC"
    --candidate-mode "$CANDIDATE_MODE"
    --page-separator "$PAGE_SEPARATOR"
  )

  if (( end_page > 0 )); then
    cmd+=(--end-page "$end_page")
  fi
  if [[ "$ANOMALY_REPORT" == "1" ]]; then
    cmd+=(--anomaly-report)
  fi
  if [[ "$DEHYPHENATE_WRAP" == "1" ]]; then
    cmd+=(--dehyphenate-wrap)
  fi

  echo "[line-anchor-full] start volume=$label pdf=$pdf start_page=$start_page end_page=$end_page" | tee -a "$log"
  printf "[line-anchor-full] cmd=%q " "${cmd[@]}" | tee -a "$log"
  echo | tee -a "$log"
  "${cmd[@]}" 2>&1 | tee -a "$log"
  echo "[line-anchor-full] done volume=$label" | tee -a "$log"
}

run_volume "$PDF_1" "$LABEL_1" "$V1_START_PAGE" "$V1_END_PAGE"
run_volume "$PDF_2" "$LABEL_2" "$V2_START_PAGE" "$V2_END_PAGE"

echo "[line-anchor-full] complete out_root=$OUT_ROOT"
