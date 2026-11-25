#!/bin/zsh
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd); PY=$ROOT/.venv/bin/python; LOG=$ROOT/experiments/runs/pipeline.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }
cd $ROOT/experiments
log "rebuild full with tuned segmentation"; $PY common.py full --reuse-parse-from full_v0 >> $LOG 2>&1
log "segmentation eval (all convs, tuned defaults)"; $PY eval_segmentation.py --variant full >> $LOG 2>&1
zsh $ROOT/experiments/pipeline_b.sh
log "public T2Retrieval eval"; $PY eval_public.py >> $LOG 2>&1
log "STAGE C DONE"
