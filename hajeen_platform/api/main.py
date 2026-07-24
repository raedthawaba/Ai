"""Hajeen AI Platform — FastAPI Application v1.1.0 (Phase 10 — Production Stable).

Routes:
  GET  /health                       — root health check (شامل)
  GET  /ping                         — pong
  GET  /api/v1/storage/stats         — إحصائيات التخزين
  /api/v1/channels                   — إدارة القنوات
  /api/v1/search                     — Semantic Search
  /api/v1/embeddings                 — Embeddings
  /api/v1/ai                         — AI Runtime
  /ws/chat                           — WebSocket Chat
"""
from __future__ import annotations

import logging
import logging.config
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# ── الديركتوريات الأساسية ──────────────────────────────────────────────────

for _d in [
    "./logs",
    "./storage_data",
    "./storage_data/metadata",
    "./storage_data/vector_index",
    "./storage_data/raw",
    "./storage_data/bronze",
    "./storage_data/silver",
    "./storage_data/gold",
]:
    os.makedirs(_d, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────

_LOGGING_CFG = Path("configs/logging.yaml")
try:
    if _LOGGING_CFG.exists():
        with open(_LOGGING_CFG, encoding="utf-8") as _f:
            logging.config.dictConfig(yaml.safe_load(_f))
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
except Exception as _e:
    logging.basicConfig(level=logging.INFO)
    logging.warning("Failed to load logging config: %s", _e)

logger = logging.getLogger(__name__)

# ── Shared Search State ────────────────────────────────────────────────────
_search_state: Dict[str, Any] = {}

# ── FastAPI ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Hajeen AI Platform API",
    description=(
        "منصة بيانات ذكية — RSS Ingestion + Vector Search + RAG + LLM Inference\n\n"
        "**Phase 10 — Production Stable**: Pipeline Orchestration · Distributed Storage · "
        "Multi-Tenant · Security · AI Inference · CI/CD"
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "https://hajeen.ai",
        "https://app.hajeen.ai",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Session-ID"],
)


# ── Global Exception Handlers ─────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """معالج أخطاء التحقق من الطلبات."""
    errors = []
    for err in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        })
    logger.warning(
        "validation_error: %s %s — %d errors",
        request.method, request.url.path, len(errors),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "بيانات الطلب غير صالحة",
            "details": errors,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """معالج أخطاء HTTP العامة."""
    logger.warning(
        "http_error: %s %s → %d %s",
        request.method, request.url.path, exc.status_code, exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "http_error",
            "status_code": exc.status_code,
            "message": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """معالج الاستثناءات غير المتوقعة — يمنع crash الـ API."""
    error_id = str(uuid.uuid4())[:8]
    logger.error(
        "unhandled_exception [%s]: %s %s — %s\n%s",
        error_id,
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "خطأ داخلي في الخادم",
            "error_id": error_id,
            "path": str(request.url.path),
        },
    )


# ── Middleware: Request timing ─────────────────────────────────────────────

@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """إضافة وقت معالجة الطلب إلى الـ response headers."""
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Process-Time-Ms"] = str(elapsed_ms)
    response.headers["X-Platform"] = "Hajeen-AI/1.1.0"
    return response


# ── Health Endpoint ────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    """فحص صحة شامل للنظام."""
    checks: Dict[str, Any] = {
        "status": "ok",
        "version": "1.1.0",
        "service": "Hajeen AI Platform",
        "phase": "10 — Production Stable",
        "timestamp": time.time(),
    }

    # Search Engine
    search_ready = _search_state.get("engine") is not None
    index_size = 0
    if search_ready:
        try:
            index_size = _search_state["engine"].vector_store.stats().total_vectors
        except Exception:
            pass
    checks["search_engine"] = "ready" if search_ready else "empty_index"
    checks["index_size"] = index_size
    checks["rag_pipeline"] = "ready" if _search_state.get("rag_pipeline") else "unavailable"

    # Channel Registry
    try:
        from data_engine.channels.registry import ChannelRegistry
        checks["channels"] = ChannelRegistry.count()
    except Exception:
        checks["channels"] = "unavailable"

    # Storage
    try:
        from data_engine.storage.storage_manager import get_storage_manager
        sm = get_storage_manager()
        checks["storage"] = "connected" if sm._connected else "ready"
    except Exception:
        checks["storage"] = "unavailable"

    # LLM
    llm_status = "unknown"
    try:
        from core.llm.llm_manager import get_llm_manager
        manager = get_llm_manager()
        llm_status = f"ready ({manager.settings.provider})" if manager._initialized else "not_initialized"
    except Exception:
        llm_status = "unavailable"
    checks["llm_engine"] = llm_status

    # Inference Engine
    inference_status = "unknown"
    try:
        from core.inference_engine.engine import get_inference_engine
        engine = get_inference_engine()
        inference_status = "ready" if engine._initialized else "not_initialized"
    except Exception:
        inference_status = "unavailable"
    checks["inference_engine"] = inference_status

    # تحديد الحالة العامة
    critical_ok = (
        checks.get("storage") in ("connected", "ready")
        and checks.get("channels") != "unavailable"
    )
    checks["status"] = "ok" if critical_ok else "degraded"

    return checks


@app.get("/ping", tags=["Health"])
async def ping():
    return {"message": "pong", "timestamp": time.time()}


# ── Storage Stats ──────────────────────────────────────────────────────────

@app.get("/api/v1/storage/stats", tags=["Storage"])
async def get_storage_stats():
    """إحصائيات التخزين لكل طبقة."""
    try:
        from data_engine.storage.storage_manager import get_storage_manager
        sm = get_storage_manager()
        stats = await sm.get_storage_stats()
        return {"status": "ok", "layers": stats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"خطأ في قراءة إحصائيات التخزين: {exc}")


# ── Index Articles ────────────────────────────────────────────────────────

@app.post("/api/v1/index/articles", tags=["Indexing"], summary="فهرسة مقالات في Vector Store")
async def index_articles(request: dict):
    """يُفهرس قائمة مقالات/نصوص في FAISS Vector Store."""
    articles = request.get("articles", [])
    if not articles:
        return {"indexed": 0, "message": "لا توجد مقالات"}

    engine = _search_state.get("engine")
    if engine is None:
        raise HTTPException(503, "Search engine غير جاهز")

    from core.embeddings.embedding_manager import get_embedding_manager
    from data_engine.storage.vector_store.base_vector_store import VectorEntry

    manager = get_embedding_manager()
    texts = [a.get("text", "") for a in articles]
    embeddings = await manager.embed_batch(texts)

    entries = [
        VectorEntry(
            id=f"art_{a.get('id', i)}",
            vector=emb.vector,
            chunk_id=f"chunk_{a.get('id', i)}_0",
            article_id=str(a.get("id", i)),
            text=a.get("text", ""),
            model_name=emb.model_name,
            metadata={"url": a.get("url", ""), "title": a.get("title", "")},
        )
        for i, (a, emb) in enumerate(zip(articles, embeddings))
    ]
    added = engine.vector_store.add(entries)
    return {
        "indexed": added,
        "total_in_index": engine.vector_store.stats().total_vectors,
        "model": embeddings[0].model_name if embeddings else "",
    }


# ── WebSocket ─────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    from api.v1.ai.websocket import handle_ws_chat
    await handle_ws_chat(websocket)


# ── Startup ───────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    logger.info("Hajeen API v1.1.0 startup — تهيئة النظام …")

    # 1. استعادة القنوات من SQLite
    try:
        from data_engine.channels.registry import ChannelRegistry
        restored = await ChannelRegistry.restore_from_db()
        logger.info("startup: استُعيدت %d قناة", restored)
    except Exception as exc:
        logger.warning("startup: تعذّر استعادة القنوات — %s", exc)

    # 2. تهيئة StorageManager
    try:
        from data_engine.storage.storage_manager import get_storage_manager
        sm = get_storage_manager()
        await sm.connect()
        logger.info("startup: StorageManager جاهز ✓")
    except Exception as exc:
        logger.error("startup: فشل تهيئة StorageManager — %s", exc)

    # 3. تهيئة FAISS + SearchEngine
    try:
        from data_engine.storage.vector_store.faiss_client import FAISSVectorStore
        from services.search.semantic_search import SemanticSearchEngine

        vector_store = FAISSVectorStore(dimensions=384)
        index_path = "storage_data/vector_index/main"
        try:
            vector_store.load(index_path)
            logger.info("startup: FAISS index مُحمَّل — %d vectors", vector_store.stats().total_vectors)
        except (FileNotFoundError, Exception):
            logger.info("startup: FAISS index جديد")

        engine = SemanticSearchEngine(vector_store=vector_store, default_top_k=10, rerank=True)
        _search_state["engine"] = engine
        _search_state["vector_store"] = vector_store
        logger.info("startup: Search Engine جاهز ✓")
    except Exception as exc:
        logger.error("startup: فشل تهيئة Search Engine — %s", exc)

    # 4. تهيئة RAG Pipeline
    try:
        from services.retrieval.vector_retriever import VectorRetriever
        from services.rag.rag_pipeline import RAGPipeline

        retriever = VectorRetriever(_search_state["engine"])
        rag = RAGPipeline(retriever=retriever)
        _search_state["rag_pipeline"] = rag
        app.state.rag_pipeline = rag
        logger.info("startup: RAG Pipeline جاهز ✓")
    except Exception as exc:
        logger.error("startup: فشل تهيئة RAG Pipeline — %s", exc)

    # 5. تهيئة LLM Manager + Mistral Fine-tuned
    try:
        from core.llm.llm_manager import get_llm_manager
        from core.llm.provider_registry import ProviderRegistry
        ProviderRegistry.auto_register_defaults()
        try:
            from core.llm.providers.mistral_finetuned_provider import MistralFinetunedProvider
            ProviderRegistry.register("mistral_finetuned", MistralFinetunedProvider)
            logger.info("startup: Mistral Fine-tuned provider مسجّل ✓")
        except Exception:
            pass
        manager = get_llm_manager()
        await manager.initialize()
        logger.info("startup: LLM Manager جاهز ✓ (provider=%s)", manager.settings.provider)
    except Exception as exc:
        logger.error("startup: فشل تهيئة LLM Manager — %s", exc)

    # 6. تهيئة Inference Engine
    try:
        from core.inference_engine.engine import get_inference_engine
        await get_inference_engine().initialize()
        logger.info("startup: Inference Engine جاهز ✓")
    except Exception as exc:
        logger.error("startup: فشل تهيئة Inference Engine — %s", exc)

    # Chat Service is now an adapter, initialized implicitly when first used via HajeenBrainV3

    # 8. تهيئة AI Metrics
    try:
        from monitoring.ai_metrics.ai_metrics_collector import get_ai_metrics
        get_ai_metrics()
        logger.info("startup: AI Metrics جاهز ✓")
    except Exception as exc:
        logger.warning("startup: فشل تهيئة AI Metrics — %s", exc)

    # 9. تهيئة Redis Service
    try:
        from services.redis.redis_service import get_redis_service
        redis_svc = get_redis_service()
        await redis_svc.connect()
        app.state.redis = redis_svc
        logger.info("startup: Redis Service جاهز ✓")
    except Exception as exc:
        logger.warning("startup: فشل تهيئة Redis — %s", exc)

    # 10. تهيئة PostgreSQL
    try:
        import os as _os
        if _os.getenv("DATABASE_URL", "").startswith("postgresql"):
            from database.models import init_db
            await init_db()
            logger.info("startup: PostgreSQL جاهز ✓")
    except Exception as exc:
        logger.warning("startup: PostgreSQL غير متاح — %s", exc)


    # 11. تهيئة HajeenBrain V3 — العقل الموحّد
    try:
        from brain.brain_v3 import get_brain_v3
        brain = await get_brain_v3()
        app.state.brain = brain
        logger.info("startup: HajeenBrainV3 v%s جاهز ✓", getattr(brain, 'VERSION', 'unknown'))
    except Exception as exc:
        logger.error("startup: فشل تهيئة HajeenBrainV3 — %s", exc)
        # Brain failure is critical but don't crash — lazy init will retry on first request

    logger.info("Hajeen AI Platform v1.1.0 — جاهز بالكامل ✅")


@app.on_event("shutdown")
async def on_shutdown():
    """حفظ FAISS + إغلاق جميع الخدمات بأمان."""
    # حفظ FAISS index
    try:
        vs = _search_state.get("vector_store")
        if vs and vs.stats().total_vectors > 0:
            vs.save("storage_data/vector_index/main")
            logger.info("shutdown: FAISS index حُفظ")
    except Exception as exc:
        logger.warning("shutdown: تعذّر حفظ FAISS — %s", exc)

    # قطع اتصال StorageManager
    try:
        from data_engine.storage.storage_manager import get_storage_manager
        sm = get_storage_manager()
        await sm.disconnect()
        logger.info("shutdown: StorageManager أُغلق")
    except Exception:
        pass

    # إغلاق Inference Engine
    try:
        from core.inference_engine.engine import get_inference_engine
        engine = get_inference_engine()
        if engine._initialized:
            await engine.shutdown()
            logger.info("shutdown: Inference Engine أُغلق")
    except Exception:
        pass

    logger.info("Hajeen AI Platform — أُغلق بأمان")


# ── Routers ──────────────────────────────────────────────────────────────

# ── Auth Middleware (يحمي جميع الـ routes) ────────────────────────────────
import os as _os
if _os.getenv("ENABLE_AUTH", "true").lower() == "true":
    try:
        from security.middleware.auth_middleware import AuthMiddleware
        app.add_middleware(AuthMiddleware, enable_rate_limiting=True)
        logger.info("startup: Auth Middleware مفعّل ✓")
    except Exception as _e:
        logger.warning("Auth Middleware غير متاح: %s", _e)

from api.v1.router import router as v1_router  # noqa: E402
app.include_router(v1_router, prefix="/api/v1")

try:
    from api.v1.tasks.router import router as tasks_router
    app.include_router(tasks_router, prefix="/api/v1")
except Exception as _e:
    logger.warning("tasks router غير متاح: %s", _e)

from api.v1.search.router import router as search_router  # noqa: E402
from api.v1.embeddings.router import router as embeddings_router  # noqa: E402
app.include_router(search_router, prefix="/api/v1")
app.include_router(embeddings_router, prefix="/api/v1")

from api.v1.ai.router import router as ai_router  # noqa: E402
app.include_router(ai_router, prefix="/api/v1/ai")

try:
    from api.v1.hajeen_model_router import router as hajeen_model_router
    app.include_router(hajeen_model_router, prefix="/api/v1")
    logger.info("startup: Hajeen Model v1 router مسجّل ✓")
except Exception as _e:
    logger.warning("Hajeen Model router غير متاح: %s", _e)

# ── Auth Router ────────────────────────────────────────────────────────────
try:
    from api.v1.auth.router import router as auth_router
    app.include_router(auth_router, prefix="/api/v1")
    logger.info("startup: Auth router مسجّل ✓")
except Exception as _e:
    logger.warning("Auth router غير متاح: %s", _e)

logger.info("Hajeen AI Platform API v1.1.0 — تمّ تسجيل جميع الـ routers")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)

    # Hajeen Brain v2 Router is deprecated and removed.
