#!/bin/zsh
# 阶段 B（问答标注校验后执行）：检索评测 → 知识构建消融变体 → 端到端问答评测
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd); PY=$ROOT/.venv/bin/python; LOG=$ROOT/experiments/runs/pipeline.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }
cd $ROOT/experiments
log "retrieval eval (full)"; $PY eval_retrieval.py --variant full >> $LOG 2>&1
for v in fixedwin nosummary noctx; do
  log "build index: $v"; $PY common.py $v --reuse-parse-from full >> $LOG 2>&1
  $PY eval_retrieval.py --variant $v --configs "Ours(full)" >> $LOG 2>&1
done
log "build index: ocronly"; $PY common.py ocronly --reuse-parse-from full >> $LOG 2>&1
$PY eval_retrieval.py --variant ocronly --configs "Ours(full)" >> $LOG 2>&1
log "QA eval (long)"; $PY eval_qa.py --variant full >> $LOG 2>&1
log "STAGE B DONE"
