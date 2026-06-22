"""
inference_engine.py — Inference engine for HajeenForCausalLM.

Decoding strategies:
    - Greedy decoding
    - Top-K sampling
    - Top-P (nucleus) sampling
    - Temperature scaling
    - Streaming (token-by-token generator)

Uses KV cache for efficient autoregressive generation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Generator, Iterator, List, Optional, Union

import torch
import torch.nn.functional as F

from hajeen_model.attention.kv_cache import KVCacheList


@dataclass
class GenerationConfig:
    """Parameters controlling text generation."""

    # Strategy
    do_sample: bool = True          # False = greedy
    temperature: float = 1.0       # >1 = more random, <1 = sharper
    top_k: int = 0                  # 0 = disabled
    top_p: float = 1.0              # 1.0 = disabled (nucleus sampling)
    repetition_penalty: float = 1.0 # 1.0 = disabled

    # Length
    max_new_tokens: int = 256
    min_new_tokens: int = 1

    # Stop criteria
    eos_token_id: Optional[int] = None
    stop_sequences: List[str] = field(default_factory=list)

    # Beam search (placeholder — not yet implemented)
    num_beams: int = 1


def _top_k_filter(logits: torch.Tensor, top_k: int) -> torch.Tensor:
    """Zero out all logits except the top-k."""
    if top_k == 0:
        return logits
    values, _ = torch.topk(logits, top_k, dim=-1)
    min_val = values[:, -1].unsqueeze(-1)
    return logits.masked_fill(logits < min_val, float("-inf"))


def _top_p_filter(logits: torch.Tensor, top_p: float) -> torch.Tensor:
    """Zero out tokens whose cumulative probability exceeds top_p."""
    if top_p >= 1.0:
        return logits
    sorted_logits, sorted_indices = torch.sort(logits, descending=True)
    cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)

    # Shift to remove token that pushes over threshold
    sorted_indices_to_remove = cumulative_probs - F.softmax(sorted_logits, dim=-1) > top_p
    sorted_logits[sorted_indices_to_remove] = float("-inf")

    # Scatter back to original ordering
    logits = torch.zeros_like(logits).scatter_(1, sorted_indices, sorted_logits)
    return logits


def _apply_repetition_penalty(
    logits: torch.Tensor,
    input_ids: torch.Tensor,
    penalty: float,
) -> torch.Tensor:
    """Apply repetition penalty to reduce probability of already-generated tokens."""
    if penalty == 1.0:
        return logits
    for i in range(logits.size(0)):
        for token_id in input_ids[i].tolist():
            if logits[i, token_id] < 0:
                logits[i, token_id] *= penalty
            else:
                logits[i, token_id] /= penalty
    return logits


class InferenceEngine:
    """
    Inference engine for HajeenForCausalLM.

    Handles KV-cache management and all decoding strategies.

    Usage:
        engine = InferenceEngine(model, tokenizer)

        # Standard generation
        text = engine.generate("مرحباً، كيف يمكنني مساعدتك؟")

        # Streaming
        for token in engine.stream("Tell me about AI:"):
            print(token, end="", flush=True)
    """

    def __init__(
        self,
        model,
        tokenizer,
        device: Optional[Union[str, torch.device]] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer

        if device is None:
            self.device = (
                torch.device("cuda") if torch.cuda.is_available()
                else torch.device("mps") if torch.backends.mps.is_available()
                else torch.device("cpu")
            )
        else:
            self.device = torch.device(device)

        self.model.to(self.device)
        self.model.eval()

    # ── Internal token sampling ───────────────────────────────────────────

    def _sample_next_token(
        self,
        logits: torch.Tensor,  # (batch, vocab_size)
        input_ids: torch.Tensor,
        config: GenerationConfig,
    ) -> torch.Tensor:
        """Sample (or greedily select) the next token ids."""
        # Repetition penalty
        logits = _apply_repetition_penalty(logits, input_ids, config.repetition_penalty)

        if not config.do_sample:
            # Greedy
            return logits.argmax(dim=-1, keepdim=True)

        # Temperature
        if config.temperature != 1.0:
            logits = logits / max(config.temperature, 1e-8)

        # Top-K filter
        logits = _top_k_filter(logits, config.top_k)

        # Top-P filter
        logits = _top_p_filter(logits, config.top_p)

        probs = F.softmax(logits, dim=-1)
        return torch.multinomial(probs, num_samples=1)

    # ── KV-cache pass ─────────────────────────────────────────────────────

    @torch.no_grad()
    def _prefill(
        self,
        input_ids: torch.Tensor,
        kv_cache: KVCacheList,
    ) -> torch.Tensor:
        """Run model on the prompt and populate the KV cache."""
        out = self.model(
            input_ids=input_ids,
            kv_cache_list=kv_cache,
            start_pos=0,
        )
        return out["logits"][:, -1, :]  # (batch, vocab_size) — last token logits

    @torch.no_grad()
    def _decode_step(
        self,
        token_ids: torch.Tensor,
        kv_cache: KVCacheList,
        start_pos: int,
    ) -> torch.Tensor:
        """Run one auto-regressive step using the KV cache."""
        out = self.model(
            input_ids=token_ids,
            kv_cache_list=kv_cache,
            start_pos=start_pos,
        )
        return out["logits"][:, -1, :]  # (batch, vocab_size)

    # ── Public API ────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: Input text (Arabic, English, code, mixed).
            config: GenerationConfig (uses defaults if None).

        Returns:
            Generated text (excluding the prompt).
        """
        tokens = list(self._generate_tokens(prompt, config))
        return self.tokenizer.decode(tokens)

    def generate_with_prompt(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> str:
        """Generate text and return prompt + generation."""
        tokens = list(self._generate_tokens(prompt, config))
        return prompt + self.tokenizer.decode(tokens)

    def stream(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> Generator[str, None, None]:
        """
        Streaming generation — yields one decoded token string at a time.

        Usage:
            for chunk in engine.stream("مرحباً"):
                print(chunk, end="", flush=True)
        """
        for token_id in self._generate_tokens(prompt, config):
            yield self.tokenizer.decode([token_id])

    # ── Internal generation loop ──────────────────────────────────────────

    def _generate_tokens(
        self,
        prompt: str,
        config: Optional[GenerationConfig] = None,
    ) -> Iterator[int]:
        """Core auto-regressive token generation loop."""
        if config is None:
            config = GenerationConfig()

        eos_id = config.eos_token_id or self.tokenizer.eos_token_id

        # Encode prompt
        input_ids = self.tokenizer.encode(prompt, add_bos=True, return_tensors="pt")
        input_ids = input_ids.to(self.device)
        prompt_len = input_ids.size(1)

        # Build KV cache
        kv_cache = KVCacheList.build(
            self.model.config,
            max_batch_size=1,
            device=self.device,
        )

        # Prefill
        logits = self._prefill(input_ids, kv_cache)

        generated = []

        for step in range(config.max_new_tokens):
            next_token = self._sample_next_token(
                logits,
                input_ids if not generated else torch.tensor([generated], device=self.device),
                config,
            )
            token_id = next_token[0, 0].item()

            if token_id == eos_id and step >= config.min_new_tokens - 1:
                break

            generated.append(token_id)
            yield token_id

            # Decode step
            logits = self._decode_step(
                next_token,
                kv_cache,
                start_pos=prompt_len + step,
            )

    # ── Batch generation ──────────────────────────────────────────────────

    def generate_batch(
        self,
        prompts: List[str],
        config: Optional[GenerationConfig] = None,
    ) -> List[str]:
        """Generate text for multiple prompts (simple loop, not parallelized)."""
        return [self.generate(p, config) for p in prompts]
