#!/usr/bin/env bash
set -euo pipefail

WORKDIR=${1:-"/Users/nathanhill/WtSOCR"}
cd "$WORKDIR"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] queue watcher started"

while pgrep -f "ocr_full_twopass_chunked.sh pdfs/WtS 1-34.pdf work/full_twopass 100" >/dev/null; do
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] waiting for WtS 1-34 to finish"
  sleep 60
done

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] starting WtS 35-51"
scripts/ocr_full_twopass_chunked.sh "pdfs/WtS 35-51.pdf" "work/full_twopass" 100 2>&1 | tee -a "work/full_twopass/run_35_51_chunked.log"
rc=${PIPESTATUS[0]}
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WtS 35-51 finished rc=$rc"
exit "$rc"
