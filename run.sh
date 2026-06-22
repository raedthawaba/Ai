#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Hajeen AI Platform — سكريبت التشغيل السريع
# الاستخدام: ./run.sh [api|worker|trigger|demo]
# ═══════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"

# إعداد متغيرات البيئة
export CELERY_USE_MEMORY=1
export PYTHONPATH="$(pwd):$PYTHONPATH"

# إنشاء المجلدات الضرورية
mkdir -p storage_data/{raw,bronze,silver,gold,metadata}
mkdir -p logs

ACTION="${1:-help}"

case "$ACTION" in
  api)
    echo "═══ تشغيل FastAPI ═══"
    echo "  URL: http://localhost:8000"
    echo "  Docs: http://localhost:8000/docs"
    echo ""
    python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
    ;;

  worker)
    echo "═══ تشغيل Celery Worker (in-memory) ═══"
    python -m celery -A workers.celery_app worker \
      --loglevel=info \
      --concurrency=2 \
      --pool=threads
    ;;

  demo)
    echo "═══ تشغيل Demo: إنشاء قناة TechCrunch ومعالجتها ═══"
    python demo_pipeline.py
    ;;

  trigger)
    CHANNEL_ID="${2:-}"
    if [ -z "$CHANNEL_ID" ]; then
      echo "الاستخدام: ./run.sh trigger CHANNEL_ID"
      python -m data_engine.cli list-channels
      exit 1
    fi
    python -m data_engine.cli trigger "$CHANNEL_ID"
    ;;

  install)
    echo "═══ تثبيت المتطلبات ═══"
    pip install -r requirements/api.txt
    pip install -r requirements/worker.txt
    pip install -r requirements/dev.txt
    ;;

  check)
    echo "═══ فحص المشروع ═══"
    python -c "
import sys
sys.path.insert(0, '.')
print('▶ فحص الاستيراد...')

# فحص جميع الوحدات الأساسية
modules = [
    'shared.schemas.article',
    'shared.schemas.channel',
    'shared.exceptions',
    'data_engine.channels.base',
    'data_engine.channels.registry',
    'data_engine.channels.builder',
    'data_engine.ingestion.crawlers.rss_parser',
    'data_engine.processing.cleaning.html_cleaner',
    'data_engine.processing.filtering.deduplicator',
    'data_engine.pipelines.pipeline_orchestrator',
    'data_engine.storage.storage_manager',
    'api.main',
]

ok = 0
fail = 0
for mod in modules:
    try:
        __import__(mod)
        print(f'  ✓ {mod}')
        ok += 1
    except Exception as e:
        print(f'  ✗ {mod} — {e}')
        fail += 1

print(f'\nنتيجة: {ok} ناجح، {fail} فاشل')
sys.exit(0 if fail == 0 else 1)
"
    ;;

  *)
    echo "══════════════════════════════════════════"
    echo "  Hajeen AI Platform — أوامر التشغيل"
    echo "══════════════════════════════════════════"
    echo ""
    echo "  ./run.sh api           — تشغيل FastAPI"
    echo "  ./run.sh worker        — تشغيل Celery Worker"
    echo "  ./run.sh demo          — تشغيل Demo Pipeline"
    echo "  ./run.sh trigger ID    — تشغيل قناة محددة"
    echo "  ./run.sh install       — تثبيت المتطلبات"
    echo "  ./run.sh check         — فحص الاستيراد"
    echo ""
    echo "  python -m data_engine.cli create-channel --name 'TechCrunch' --type rss --url 'https://techcrunch.com/feed/'"
    echo "  python -m data_engine.cli list-channels"
    echo "  python -m data_engine.cli trigger CHANNEL_ID"
    echo ""
    ;;
esac
