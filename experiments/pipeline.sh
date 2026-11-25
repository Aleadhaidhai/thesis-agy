#!/bin/zsh
# 实验全流程：等待对话生成完成 → 组装数据集 → 生成问答标注 → 构建索引（含消融变体）→ 各项评测
# 用法：zsh experiments/pipeline.sh  （日志：experiments/runs/pipeline.log）
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)
PY=$ROOT/.venv/bin/python
mkdir -p experiments/runs
LOG=$ROOT/experiments/runs/pipeline.log
log() { echo "[$(date '+%F %T')] $*" | tee -a $LOG; }

log "waiting for chatgen..."
while pgrep -f "chatgen.py" > /dev/null; do sleep 30; done
log "chatgen done"

cd datasets/simeim
$PY chatgen.py >> $LOG 2>&1   # 幂等：补生成失败的种子
log "chatgen retry done"
$PY assemble.py >> $LOG 2>&1
log "assemble done"
[ -f build/qa.json ] || $PY qagen.py >> $LOG 2>&1
log "qagen done"
cd $ROOT/experiments

STAGE=${1:-all}
log "build index: full"
$PY common.py full >> $LOG 2>&1
log "segmentation eval"
$PY eval_segmentation.py --variant full >> $LOG 2>&1
log "retrieval eval (full)"
$PY eval_retrieval.py --variant full >> $LOG 2>&1
for v in fixedwin nosummary noctx; do
  log "build index: $v"
  $PY common.py $v --reuse-parse-from full >> $LOG 2>&1
  $PY eval_retrieval.py --variant $v --configs "Ours(full)" >> $LOG 2>&1
done
log "build index: ocronly"
$PY common.py ocronly >> $LOG 2>&1
$PY eval_retrieval.py --variant ocronly --configs "Ours(full)" >> $LOG 2>&1
log "QA eval (long)"
$PY eval_qa.py --variant full >> $LOG 2>&1
log "ALL DONE"
