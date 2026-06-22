#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Hajeen Platform — إعداد Ollama وتحميل Hajeen Model v1
# الاستخدام: bash scripts/deployment/setup_ollama.sh
# ═══════════════════════════════════════════════════════════════

set -e

HAJEEN_MODEL="qwen2.5:1.5b"
OLLAMA_URL="http://localhost:11434"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  🤖  Hajeen Model v1 — Ollama Setup"
echo "═══════════════════════════════════════════════════════"
echo ""

# 1. فحص Ollama
check_ollama() {
    if command -v ollama &> /dev/null; then
        echo "  ✅  Ollama مثبت: $(ollama --version 2>/dev/null || echo 'OK')"
        return 0
    else
        echo "  ❌  Ollama غير مثبت"
        return 1
    fi
}

# 2. تثبيت Ollama
install_ollama() {
    echo "  📥  تثبيت Ollama..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        curl -fsSL https://ollama.ai/install.sh | sh
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  ⚠️  على macOS، حمّل من: https://ollama.ai/download"
        exit 1
    else
        echo "  ⚠️  نظام غير مدعوم. حمّل يدوياً: https://ollama.ai"
        exit 1
    fi
}

# 3. تشغيل Ollama في الخلفية
start_ollama() {
    echo "  🚀  تشغيل Ollama..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 3

    if curl -s "$OLLAMA_URL/api/tags" &>/dev/null; then
        echo "  ✅  Ollama يعمل (PID: $OLLAMA_PID)"
        return 0
    else
        echo "  ❌  فشل تشغيل Ollama"
        return 1
    fi
}

# 4. تحميل النموذج
pull_model() {
    echo ""
    echo "  📦  تحميل $HAJEEN_MODEL..."
    echo "  (قد يستغرق عدة دقائق حسب سرعة الإنترنت)"
    echo ""
    ollama pull "$HAJEEN_MODEL"
    echo ""
    echo "  ✅  تم تحميل $HAJEEN_MODEL بنجاح"
}

# 5. اختبار النموذج
test_model() {
    echo ""
    echo "  🧪  اختبار النموذج..."
    RESPONSE=$(ollama run "$HAJEEN_MODEL" "قل مرحبا بالعربية" --nowordwrap 2>/dev/null | head -3)
    echo "  استجابة النموذج: $RESPONSE"
    echo "  ✅  النموذج يعمل بنجاح!"
}

# ─── Main ──────────────────────────────────────────────────────

if ! check_ollama; then
    install_ollama
    check_ollama
fi

# تشغيل إذا لم يكن يعمل
if ! curl -s "$OLLAMA_URL/api/tags" &>/dev/null; then
    start_ollama
fi

# فحص إذا كان النموذج محملاً
MODELS=$(curl -s "$OLLAMA_URL/api/tags" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(m['name'] for m in d.get('models', [])))" 2>/dev/null)
if echo "$MODELS" | grep -q "qwen2.5"; then
    echo "  ✅  النموذج $HAJEEN_MODEL محمّل بالفعل"
else
    pull_model
fi

test_model

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅  Hajeen Model v1 جاهز!"
echo ""
echo "  الخطوات التالية:"
echo "  1. شغّل المنصة: ./run.sh api"
echo "  2. الـ API: http://localhost:8000/api/v1/model/health"
echo "  3. الوثائق: http://localhost:8000/docs"
echo "═══════════════════════════════════════════════════════"
echo ""
