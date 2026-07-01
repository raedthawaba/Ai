"""Mistral Fine-tuned Local Provider — تشغيل نموذج Mistral المدرَّب على بياناتك.

الأولوية: Fine-tuned model → Base Mistral via Ollama → Mock fallback

يدعم:
  - تحميل نموذج QLoRA / LoRA adapter
  - تحميل نموذج كامل (merged)
  - تشغيل عبر Ollama إذا لم يكن النموذج المدرَّب موجوداً
  - Streaming
  - تشغيل محلي 100% بدون API خارجي
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncIterator, Dict, List, Optional

from core.llm.base import BaseLLMProvider, LLMConfig, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)

MODEL_PATH   = os.getenv("FINETUNED_MODEL_PATH", "")
MODEL_NAME   = os.getenv("FINETUNED_MODEL_NAME", "hajeen-mistral-7b")
BASE_MODEL   = os.getenv("BASE_MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.2")
USE_FINETUNED = os.getenv("USE_FINETUNED_MODEL", "false").lower() == "true"
OLLAMA_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class MistralFinetunedProvider(BaseLLMProvider):
    """Provider لتشغيل نموذج Mistral المدرَّب محلياً."""

    provider_name = "mistral_finetuned"

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig()
        self._pipeline = None
        self._tokenizer = None
        self._loaded = False
        self._use_ollama_fallback = False

    async def initialize(self) -> None:
        if USE_FINETUNED and MODEL_PATH and os.path.isdir(MODEL_PATH):
            await self._load_local_model()
        else:
            logger.info("Fine-tuned model not configured — using Ollama fallback (mistral:7b)")
            self._use_ollama_fallback = True
            self._loaded = True

    async def _load_local_model(self) -> None:
        """تحميل النموذج المدرَّب من القرص."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

            logger.info("Loading fine-tuned model from: %s", MODEL_PATH)
            self._tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)

            device_map = "auto" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32

            model = AutoModelForCausalLM.from_pretrained(
                MODEL_PATH,
                torch_dtype=dtype,
                device_map=device_map,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )

            self._pipeline = pipeline(
                "text-generation",
                model=model,
                tokenizer=self._tokenizer,
                torch_dtype=dtype,
                device_map=device_map,
                max_new_tokens=1024,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.1,
                pad_token_id=self._tokenizer.eos_token_id,
            )
            self._loaded = True
            logger.info("Fine-tuned model loaded successfully: %s", MODEL_NAME)

        except ImportError:
            logger.warning("transformers not installed — falling back to Ollama")
            self._use_ollama_fallback = True
            self._loaded = True
        except Exception as e:
            logger.error("Failed to load fine-tuned model: %s — falling back to Ollama", e)
            self._use_ollama_fallback = True
            self._loaded = True

    def _format_prompt(self, messages: List[LLMMessage]) -> str:
        """تنسيق الرسائل بصيغة Mistral Instruct."""
        prompt = ""
        for msg in messages:
            if msg.role == "system":
                prompt += f"<s>[INST] <<SYS>>\n{msg.content}\n<</SYS>>\n\n"
            elif msg.role == "user":
                if prompt:
                    prompt += f"{msg.content} [/INST]"
                else:
                    prompt += f"<s>[INST] {msg.content} [/INST]"
            elif msg.role == "assistant":
                prompt += f" {msg.content} </s><s>[INST] "
        return prompt.strip()

    async def generate(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
        **kwargs,
    ) -> LLMResponse:
        if not self._loaded:
            await self.initialize()

        cfg = config or self.config
        start = time.perf_counter()

        if self._use_ollama_fallback:
            return await self._ollama_generate(messages, cfg)

        prompt = self._format_prompt(messages)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._inference_sync, prompt, cfg)
        latency = (time.perf_counter() - start) * 1000

        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(result.split())

        return LLMResponse(
            content=result,
            model=MODEL_NAME,
            provider=self.provider_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency,
        )

    def _inference_sync(self, prompt: str, config: LLMConfig) -> str:
        outputs = self._pipeline(
            prompt,
            max_new_tokens=config.max_tokens or 512,
            temperature=config.temperature or 0.7,
            top_p=config.top_p or 0.9,
            do_sample=True,
        )
        generated = outputs[0]["generated_text"]
        if "[/INST]" in generated:
            return generated.split("[/INST]")[-1].strip()
        return generated[len(prompt):].strip()

    async def _ollama_generate(self, messages: List[LLMMessage], config: LLMConfig) -> LLMResponse:
        """Fallback: توليد النص عبر Ollama."""
        import httpx
        start = time.perf_counter()

        payload = {
            "model": "mistral:7b",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": config.temperature or 0.7,
                "top_p": config.top_p or 0.9,
                "num_predict": config.max_tokens or 512,
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        latency = (time.perf_counter() - start) * 1000

        return LLMResponse(
            content=content,
            model="mistral:7b",
            provider="ollama",
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=latency,
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMConfig] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        if not self._loaded:
            await self.initialize()

        cfg = config or self.config

        if self._use_ollama_fallback:
            async for chunk in self._ollama_stream(messages, cfg):
                yield chunk
            return

        prompt = self._format_prompt(messages)
        full = await asyncio.get_event_loop().run_in_executor(
            None, self._inference_sync, prompt, cfg
        )
        words = full.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.01)

    async def _ollama_stream(self, messages: List[LLMMessage], config: LLMConfig) -> AsyncIterator[str]:
        import httpx
        payload = {
            "model": "mistral:7b",
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": config.temperature or 0.7},
        }
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

    async def health_check(self) -> Dict[str, str]:
        if self._use_ollama_fallback:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{OLLAMA_URL}/api/version")
                return {"status": "healthy", "backend": "ollama", "model": "mistral:7b"}
            except Exception as e:
                return {"status": "unhealthy", "error": str(e)}

        if self._pipeline:
            return {"status": "healthy", "backend": "local", "model": MODEL_NAME}
        return {"status": "not_loaded", "model": MODEL_NAME}
