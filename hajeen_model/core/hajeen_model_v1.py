"""
Hajeen Model v1 — الواجهة الرئيسية للنموذج المحلي.

يدير هذا الملف:
- تشغيل Hajeen Foundation Model محلياً بالأوزان المدرَّبة (LOCAL FIRST)
- فصل وتعطيل Ollama / Qwen / OpenAI / Cohere عند تفعيل LOCAL_ONLY
- الاستدلال (Inference) المتزامن وغير المتزامن
- Streaming
- إحصائيات الاستخدام

المزودون المدعومون (بالأولوية):
  1. local_weights  — Hajeen Foundation Model + Local Weights (الرئيسي)
  2. ollama         — Ollama (معطَّل في LOCAL_ONLY mode)
  3. mock           — استجابات وهمية (fallback أخير)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator, Dict, List, Optional

import httpx
import yaml
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "config" / "model_config.yaml"

LOCAL_ONLY_MODE: bool = os.getenv("HAJEEN_LOCAL_ONLY", "false").lower() == "true"
DISABLE_OLLAMA: bool = os.getenv("HAJEEN_DISABLE_OLLAMA", "false").lower() == "true"
DISABLE_QWEN: bool = os.getenv("HAJEEN_DISABLE_QWEN", "false").lower() == "true"

DISABLED_PROVIDERS: List[str] = []
if LOCAL_ONLY_MODE or DISABLE_OLLAMA:
    DISABLED_PROVIDERS.append("ollama")
if LOCAL_ONLY_MODE or DISABLE_QWEN:
    DISABLED_PROVIDERS.append("qwen")
if os.getenv("HAJEEN_DISABLE_OPENAI", "false").lower() == "true":
    DISABLED_PROVIDERS.append("openai")
if os.getenv("HAJEEN_DISABLE_COHERE", "false").lower() == "true":
    DISABLED_PROVIDERS.append("cohere")


def _load_config() -> Dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


CONFIG = _load_config()
_INF = CONFIG.get("inference", {})

MODEL_NAME = CONFIG.get("model", {}).get("name", "Hajeen Foundation Model v1")
OLLAMA_BASE_URL = _INF.get("ollama_base_url", "http://localhost:11434")
OLLAMA_MODEL = _INF.get("ollama_model", "qwen2.5:1.5b")
SYSTEM_PROMPT = CONFIG.get("system_prompt", "أنت مساعد ذكي اسمك حاجين.")

# مسارات الأوزان المحلية
LOCAL_MODEL_WEIGHTS = os.getenv("MODEL_WEIGHTS_DIR", "./model_weights")
LOCAL_TOKENIZER_PATH = os.getenv("TOKENIZER_OUTPUT_DIR", "./tokenizer_output")

if LOCAL_ONLY_MODE:
    logger.info(
        "🔒 Hajeen LOCAL ONLY Mode — "
        f"معطَّل: {', '.join(DISABLED_PROVIDERS) or 'لا شيء'}"
    )

# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class HajeenMessage:
    role: str  # system | user | assistant
    content: str

    def to_dict(self) -> Dict:
        return {"role": self.role, "content": self.content}


@dataclass
class HajeenRequest:
    messages: List[HajeenMessage]
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = False
    session_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class HajeenResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    request_id: Optional[str] = None
    is_mock: bool = False
    is_local: bool = False

    def to_dict(self) -> Dict:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "is_mock": self.is_mock,
            "is_local": self.is_local,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "latency_ms": round(self.latency_ms, 2),
            "finish_reason": self.finish_reason,
            "request_id": self.request_id,
        }


# ─── Local Model Provider (PRIMARY) ──────────────────────────────────────────

_local_inference_engine = None


def _get_local_engine():
    """الحصول على محرك الاستدلال المحلي (lazy init)."""
    global _local_inference_engine
    if _local_inference_engine is None:
        try:
            from hajeen_model.core.local_inference_engine import (
                LocalInferenceEngine, LocalInferenceConfig,
            )
            config = LocalInferenceConfig(
                model_path=LOCAL_MODEL_WEIGHTS,
                tokenizer_path=LOCAL_TOKENIZER_PATH,
                device="auto",
            )
            _local_inference_engine = LocalInferenceEngine(config=config)
            if LOCAL_ONLY_MODE:
                _local_inference_engine.load_model()
        except Exception as e:
            logger.warning(f"⚠️  لم يتم تحميل Local Engine: {e}")
            _local_inference_engine = None
    return _local_inference_engine


def _is_local_model_available() -> bool:
    """التحقق من توفر أوزان النموذج المحلي."""
    weights_dir = Path(LOCAL_MODEL_WEIGHTS)
    tokenizer_dir = Path(LOCAL_TOKENIZER_PATH)
    has_weights = any(
        weights_dir.glob("**/*.pt") if weights_dir.exists() else []
    )
    has_tokenizer = (tokenizer_dir / "tokenizer.json").exists() if tokenizer_dir.exists() else False
    return has_weights or has_tokenizer


async def _local_complete(request: "HajeenRequest") -> "HajeenResponse":
    """استدلال عبر النموذج المحلي فقط."""
    engine = _get_local_engine()
    if engine is None:
        raise RuntimeError("Local inference engine غير متاح")

    user_text = ""
    for m in reversed(request.messages):
        if m.role == "user":
            user_text = m.content
            break

    loop = asyncio.get_event_loop()
    local_resp = await loop.run_in_executor(
        None,
        lambda: engine.generate(
            prompt=f"{SYSTEM_PROMPT}\n\nالمستخدم: {user_text}\nحاجين:",
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
        ),
    )

    return HajeenResponse(
        content=local_resp.content,
        model="HajeenFoundationModel",
        provider="local_weights",
        prompt_tokens=local_resp.prompt_tokens,
        completion_tokens=local_resp.completion_tokens,
        total_tokens=local_resp.total_tokens,
        latency_ms=local_resp.latency_ms,
        finish_reason=local_resp.finish_reason,
        request_id=request.request_id,
        is_mock=False,
        is_local=True,
    )


# ─── Mock Provider ────────────────────────────────────────────────────────────

_MOCK_RESPONSES = [
    "هذه استجابة من Hajeen Foundation Model. درِّب النموذج أولاً باستخدام train_hajeen_cloud.py",
    "Hajeen Foundation Model هو نموذج لغوي مستقل يدعم اللغتين العربية والإنجليزية.",
    "لتشغيل النموذج المحلي: شغّل train_hajeen_cloud.py ثم ضع الأوزان في model_weights/",
    "يمكن تحميل أوزان النموذج من HuggingFace: Raedthawaba/hajeen-model",
    "Hajeen runs fully locally — no Ollama, no Qwen, no external APIs required.",
]
_mock_idx = 0


def _mock_response(request: HajeenRequest) -> HajeenResponse:
    global _mock_idx
    user_content = ""
    for m in reversed(request.messages):
        if m.role == "user":
            user_content = m.content[:60]
            break
    text = _MOCK_RESPONSES[_mock_idx % len(_MOCK_RESPONSES)]
    _mock_idx += 1
    return HajeenResponse(
        content=f"[Hajeen Mock] {text}\n\nسؤالك: '{user_content}'",
        model=OLLAMA_MODEL,
        provider="mock",
        prompt_tokens=len(user_content.split()),
        completion_tokens=len(text.split()),
        total_tokens=len(user_content.split()) + len(text.split()),
        latency_ms=50.0,
        finish_reason="stop",
        request_id=request.request_id,
        is_mock=True,
    )


# ─── Ollama Provider ──────────────────────────────────────────────────────────


async def _ollama_check() -> bool:
    """تحقق من توفر Ollama."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def _ollama_complete(request: HajeenRequest) -> HajeenResponse:
    """استدلال عبر Ollama."""
    t0 = time.perf_counter()
    messages = [HajeenMessage("system", SYSTEM_PROMPT).to_dict()] + [
        m.to_dict() for m in request.messages
    ]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
        },
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    latency = (time.perf_counter() - t0) * 1000
    content = data.get("message", {}).get("content", "")
    prompt_t = data.get("prompt_eval_count", 0)
    comp_t = data.get("eval_count", 0)

    return HajeenResponse(
        content=content,
        model=data.get("model", OLLAMA_MODEL),
        provider="ollama",
        prompt_tokens=prompt_t,
        completion_tokens=comp_t,
        total_tokens=prompt_t + comp_t,
        latency_ms=latency,
        finish_reason="stop",
        request_id=request.request_id,
        is_mock=False,
    )


async def _ollama_stream(request: HajeenRequest) -> AsyncGenerator[str, None]:
    """Streaming عبر Ollama."""
    messages = [HajeenMessage("system", SYSTEM_PROMPT).to_dict()] + [
        m.to_dict() for m in request.messages
    ]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {"temperature": request.temperature},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue


# ─── Public API ───────────────────────────────────────────────────────────────


class HajeenModelV1:
    """
    الواجهة الرئيسية لـ Hajeen Foundation Model v1.

    الأولوية (LOCAL FIRST):
      1. local_weights  — Hajeen Foundation Model + أوزان محلية (أولوية قصوى)
      2. ollama         — Ollama/Qwen (معطَّل إذا LOCAL_ONLY=true)
      3. mock           — fallback أخير

    الاستخدام:
        model = HajeenModelV1()
        response = await model.chat("ما هو الذكاء الاصطناعي؟")
        print(response.content)
    """

    def __init__(self):
        self._ollama_available: Optional[bool] = None
        self._local_available: Optional[bool] = None
        self._stats = {
            "total_requests": 0,
            "local_requests": 0,
            "ollama_requests": 0,
            "mock_requests": 0,
            "errors": 0,
        }
        if LOCAL_ONLY_MODE:
            logger.info(
                "🔒 LOCAL ONLY مُفعَّل — Ollama/Qwen/OpenAI/Cohere معطَّلة. "
                "جميع الردود من Hajeen Foundation Model فقط."
            )

    def _check_local_available(self) -> bool:
        if self._local_available is None:
            self._local_available = _is_local_model_available()
        return self._local_available

    async def _is_ollama_up(self) -> bool:
        if "ollama" in DISABLED_PROVIDERS:
            return False
        if self._ollama_available is None:
            self._ollama_available = await _ollama_check()
        return self._ollama_available

    async def chat(
        self,
        user_message: str,
        history: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> HajeenResponse:
        """دردشة مع النموذج."""
        messages = []
        for h in (history or []):
            messages.append(HajeenMessage(h.get("role", "user"), h.get("content", "")))
        messages.append(HajeenMessage("user", user_message))
        request = HajeenRequest(messages=messages, temperature=temperature, max_tokens=max_tokens)
        return await self.complete(request)

    async def complete(self, request: HajeenRequest) -> HajeenResponse:
        """
        استدلال كامل — الأولوية:
          1. Local Weights (دائماً أول إذا كانت متاحة أو LOCAL_ONLY مفعَّل)
          2. Ollama (إذا لم يكن LOCAL_ONLY مفعَّلاً)
          3. Mock (fallback أخير)
        """
        self._stats["total_requests"] += 1
        try:
            if self._check_local_available() or LOCAL_ONLY_MODE:
                try:
                    resp = await _local_complete(request)
                    self._stats["local_requests"] += 1
                    logger.info(
                        "Hajeen[LocalWeights] tokens=%d latency=%.0fms",
                        resp.total_tokens, resp.latency_ms,
                    )
                    return resp
                except Exception as local_err:
                    if LOCAL_ONLY_MODE:
                        logger.warning("Local engine خطأ (LOCAL_ONLY): %s — mock", local_err)
                        resp = _mock_response(request)
                        self._stats["mock_requests"] += 1
                        return resp
                    logger.warning("Local engine غير متاح: %s — محاولة Ollama", local_err)

            if not LOCAL_ONLY_MODE and await self._is_ollama_up():
                resp = await _ollama_complete(request)
                self._stats["ollama_requests"] += 1
                logger.info("Hajeen[Ollama] tokens=%d latency=%.0fms", resp.total_tokens, resp.latency_ms)
                return resp

            logger.warning("كل المزودين غير متاحين — mock fallback")
            resp = _mock_response(request)
            self._stats["mock_requests"] += 1
            return resp

        except Exception as exc:
            self._stats["errors"] += 1
            logger.error("HajeenModelV1 error: %s — fallback to mock", exc)
            return _mock_response(request)

    async def stream(
        self, user_message: str, history: Optional[List[Dict]] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming response."""
        if self._check_local_available() or LOCAL_ONLY_MODE:
            engine = _get_local_engine()
            if engine:
                messages = []
                for h in (history or []):
                    messages.append(HajeenMessage(h.get("role", "user"), h.get("content", "")))
                messages.append(HajeenMessage("user", user_message))
                request = HajeenRequest(messages=messages, stream=True)
                async for token in engine.stream_generate(
                    f"{SYSTEM_PROMPT}\n\nالمستخدم: {user_message}\nحاجين:"
                ):
                    yield token
                return

        if not LOCAL_ONLY_MODE and await self._is_ollama_up():
            messages = []
            for h in (history or []):
                messages.append(HajeenMessage(h.get("role", "user"), h.get("content", "")))
            messages.append(HajeenMessage("user", user_message))
            request = HajeenRequest(messages=messages, stream=True)
            async for token in _ollama_stream(request):
                yield token
        else:
            mock = _mock_response(HajeenRequest(messages=[HajeenMessage("user", user_message)]))
            for word in mock.content.split():
                yield word + " "
                await asyncio.sleep(0.02)

    async def health(self) -> Dict:
        """فحص حالة النموذج والمزودين."""
        local_avail = _is_local_model_available()
        ollama_up = False if LOCAL_ONLY_MODE else await _ollama_check()
        self._ollama_available = ollama_up
        self._local_available = local_avail

        if local_avail:
            active = "local_weights"
        elif ollama_up:
            active = "ollama"
        else:
            active = "mock"

        return {
            "model": MODEL_NAME,
            "version": "1.0.0",
            "architecture": "HajeenFoundationModel",
            "local_only_mode": LOCAL_ONLY_MODE,
            "disabled_providers": DISABLED_PROVIDERS,
            "local_weights_available": local_avail,
            "local_weights_path": LOCAL_MODEL_WEIGHTS,
            "ollama_available": ollama_up,
            "ollama_url": OLLAMA_BASE_URL if not LOCAL_ONLY_MODE else "DISABLED",
            "active_provider": active,
            "hf_model_repo": "Raedthawaba/hajeen-model",
            "hf_dataset_repo": "Raedthawaba/hajeen-datasets",
            "stats": self._stats,
            "status": "ready",
        }

    def reset_cache(self):
        """إعادة فحص المزودين عند الاستدعاء القادم."""
        self._ollama_available = None
        self._local_available = None

    def reset_ollama_cache(self):
        """للتوافق مع الإصدارات السابقة."""
        self.reset_cache()


# ─── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[HajeenModelV1] = None


def get_hajeen_model() -> HajeenModelV1:
    global _instance
    if _instance is None:
        _instance = HajeenModelV1()
    return _instance
