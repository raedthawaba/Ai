from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Evaluator:
    """Evaluate LLM quality: perplexity, BLEU, and generation benchmarks."""

    def __init__(self, model: Optional[Any] = None, tokenizer: Optional[Any] = None) -> None:
        self.model = model
        self.tokenizer = tokenizer

    def perplexity(self, texts: List[str], batch_size: int = 4) -> float:
        """Compute average perplexity on a text list."""
        try:
            import torch  # type: ignore
            if self.model is None or self.tokenizer is None:
                raise RuntimeError("model and tokenizer must be set")
            self.model.eval()
            total_loss = 0.0
            total_tokens = 0
            for i in range(0, len(texts), batch_size):
                batch = texts[i: i + batch_size]
                encoded = self.tokenizer(
                    batch,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                )
                with torch.no_grad():
                    outputs = self.model(**encoded, labels=encoded["input_ids"])
                loss = outputs.loss.item()
                n_tokens = encoded["input_ids"].ne(self.tokenizer.pad_token_id).sum().item()
                total_loss += loss * n_tokens
                total_tokens += n_tokens
            avg_loss = total_loss / max(1, total_tokens)
            return round(math.exp(avg_loss), 4)
        except ImportError as exc:
            raise RuntimeError("PyTorch + transformers required") from exc

    def bleu(self, references: List[str], hypotheses: List[str]) -> float:
        """Compute corpus-level BLEU score."""
        try:
            from nltk.translate.bleu_score import corpus_bleu  # type: ignore
            import nltk  # type: ignore
            refs = [[r.split()] for r in references]
            hyps = [h.split() for h in hypotheses]
            return round(corpus_bleu(refs, hyps), 4)
        except ImportError:
            return self._simple_bleu(references, hypotheses)

    def _simple_bleu(self, references: List[str], hypotheses: List[str]) -> float:
        total = 0.0
        for ref, hyp in zip(references, hypotheses):
            ref_tokens = set(ref.lower().split())
            hyp_tokens = hyp.lower().split()
            if not hyp_tokens:
                continue
            overlap = sum(1 for t in hyp_tokens if t in ref_tokens)
            total += overlap / len(hyp_tokens)
        return round(total / max(1, len(references)), 4)

    def generation_benchmark(
        self,
        prompts: List[str],
        expected: Optional[List[str]] = None,
        max_new_tokens: int = 64,
    ) -> Dict:
        results: List[Dict] = []
        for i, prompt in enumerate(prompts):
            entry: Dict = {"prompt": prompt, "generated": "", "error": None}
            try:
                import torch  # type: ignore
                inputs = self.tokenizer(prompt, return_tensors="pt")
                with torch.no_grad():
                    output = self.model.generate(
                        **inputs, max_new_tokens=max_new_tokens, do_sample=False
                    )
                gen = self.tokenizer.decode(
                    output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True
                )
                entry["generated"] = gen
                if expected and i < len(expected):
                    entry["bleu"] = self._simple_bleu([expected[i]], [gen])
            except Exception as exc:
                entry["error"] = str(exc)
            results.append(entry)
        avg_bleu = sum(r.get("bleu", 0.0) for r in results) / max(1, len(results))
        return {"results": results, "avg_bleu": round(avg_bleu, 4)}
