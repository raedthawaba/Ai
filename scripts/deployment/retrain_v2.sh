#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Hajeen Model v2 — سكريبت إعادة التدريب
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")/../.."

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  🚀  Hajeen Model v2 — Training Pipeline"
echo "═══════════════════════════════════════════════════════"

BASE_MODEL="${1:-Qwen/Qwen2.5-1.5B}"
EPOCHS="${2:-3}"
VERSION="${3:-v2}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXP_DIR="hajeen_model/checkpoints/hajeen_${VERSION}_${TIMESTAMP}"

echo ""
echo "  النموذج الأساسي: $BASE_MODEL"
echo "  Epochs:          $EPOCHS"
echo "  الإصدار:         Hajeen Model $VERSION"
echo "  المسار:          $EXP_DIR"
echo ""

# 1. بناء Dataset
echo "  📊  الخطوة 1: بناء Dataset..."
python3 scripts/training/run_training.py \
    --build-dataset-only \
    --synthetic 200 \
    --storage-dir storage_data/gold \
    --processed-dir data/processed/pipeline

# 2. فحص المتطلبات
echo ""
echo "  🔍  الخطوة 2: فحص المتطلبات..."
python3 scripts/training/run_training.py --check-only

# 3. التدريب
echo ""
echo "  🏋️  الخطوة 3: التدريب..."
python3 scripts/training/run_training.py \
    --base-model "$BASE_MODEL" \
    --epochs "$EPOCHS" \
    2>&1 | tee "hajeen_model/logs/training_${VERSION}_${TIMESTAMP}.log"

# 4. التقييم
echo ""
echo "  🧪  الخطوة 4: التقييم..."
python3 scripts/evaluation/run_evaluation.py \
    2>&1 | tee "hajeen_model/logs/eval_${VERSION}_${TIMESTAMP}.log"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅  Hajeen Model $VERSION — اكتمل التدريب"
echo ""
echo "  السجلات:      hajeen_model/logs/"
echo "  Checkpoints:  hajeen_model/checkpoints/"
echo "  التقييم:      hajeen_model/evaluation/"
echo "═══════════════════════════════════════════════════════"
echo ""
