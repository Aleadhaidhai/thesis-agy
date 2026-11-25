#!/bin/zsh
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd); PY=$ROOT/.venv/bin/python; LOG=$ROOT/experiments/runs/step2.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }

cd $ROOT/experiments
for v in nosummary fixedwin noctx ocronly; do
  rm -rf runs/index/$v
  log "build index: $v"
  $PY common.py $v --reuse-parse-from full 2>&1 | tee -a $LOG
  $PY -c "import json; bs=json.load(open('runs/index/$v/build_stats.json')); assert bs['visual']>0, bs; print('OK $v build_stats:', bs)" | tee -a $LOG
  log "eval retrieval: $v"
  $PY eval_retrieval.py --variant $v --configs "Ours(full)" 2>&1 | tee -a $LOG
done

log "eval public T2Retrieval (300 queries, 10000 distractors)"
$PY eval_public.py --n-queries 300 --n-distractors 10000 2>&1 | tee -a $LOG
log "STEP 2 DONE"
