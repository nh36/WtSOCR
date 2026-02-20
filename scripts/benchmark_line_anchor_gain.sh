#!/usr/bin/env bash
set -euo pipefail

PDF=${1:-"pdfs/WtS 1-34.pdf"}
PAGES=${2:-"34,57,114,301,451,601,752,902,1052,1202"}
OUT_ROOT=${3:-"work/line_anchor_benchmark_$(date +%Y%m%d_%H%M%S)"}

mkdir -p "$OUT_ROOT"

BASE="$OUT_ROOT/baseline"
ENH="$OUT_ROOT/enhanced"

echo "[bench] pdf=$PDF"
echo "[bench] pages=$PAGES"
echo "[bench] out=$OUT_ROOT"

python3 scripts/line_anchor_merge_pilot.py \
  "$PDF" \
  --outdir "$BASE" \
  --pages "$PAGES" \
  --crop-variants "raw" \
  --psm-b-lines "7,6" \
  --min-similarity 0.85 \
  2>&1 | tee "$OUT_ROOT/baseline.log"

python3 scripts/line_anchor_merge_pilot.py \
  "$PDF" \
  --outdir "$ENH" \
  --pages "$PAGES" \
  --crop-variants "raw,auto,bw180,up2x_auto" \
  --psm-b-lines "7,6" \
  --min-similarity 0.85 \
  2>&1 | tee "$OUT_ROOT/enhanced.log"

python3 - <<'PY' "$BASE" "$ENH"
import csv, sys
from pathlib import Path
base = Path(sys.argv[1])
enh = Path(sys.argv[2])

def totals(dirpath: Path):
    audit = next(dirpath.glob("*_lineanchored_audit.csv"))
    cand = rep = 0
    reasons = {}
    sources = {}
    with audit.open(newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row["candidate"] == "1":
                cand += 1
                reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
            if row["replaced"] == "1":
                rep += 1
                src = row.get("b_source", "")
                sources[src] = sources.get(src, 0) + 1
    return cand, rep, reasons, sources

b_c, b_r, b_reasons, b_sources = totals(base)
e_c, e_r, e_reasons, e_sources = totals(enh)
print(f"baseline candidates={b_c} replaced={b_r} rate={(b_r/b_c if b_c else 0):.4f}")
print(f"enhanced candidates={e_c} replaced={e_r} rate={(e_r/e_c if e_c else 0):.4f}")
print(f"delta_replaced={e_r-b_r}")
print("enhanced replacement sources:")
for k,v in sorted(e_sources.items(), key=lambda kv: (-kv[1], kv[0])):
    print(f"  {k}: {v}")
print("enhanced top reasons:")
for k,v in sorted(e_reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:8]:
    print(f"  {k}: {v}")
PY

echo "[bench] complete"
