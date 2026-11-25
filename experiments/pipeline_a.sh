#!/bin/zsh
# 阶段 A：问答标注生成 → 构建完整索引 → 话题切分评测
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd); PY=$ROOT/.venv/bin/python; LOG=$ROOT/experiments/runs/pipeline.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }
[ -f datasets/simeim/build/qa.json ] || (cd datasets/simeim && $PY qagen.py >> $LOG 2>&1)
cd $ROOT/experiments
log "build index: full"; $PY common.py full >> $LOG 2>&1
log "segmentation eval"; $PY eval_segmentation.py --variant full >> $LOG 2>&1
log "STAGE A DONE"
