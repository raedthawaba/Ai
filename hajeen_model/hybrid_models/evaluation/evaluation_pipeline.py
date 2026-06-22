"""
evaluation_pipeline.py — Evaluation framework for Hajeen Foundation Model.

Metrics:
    - Perplexity (primary language modeling metric)
    - Cross-entropy loss
    - Token-level accuracy
    - Benchmark testing (custom tasks)
    - Response quality evaluation (BLEU-like)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader


@dataclass
class EvaluationConfig:
    """Configuration for the evaluation pipeline."""
    batch_size: int = 8
    max_batches: Optional[int] = None     # None = evaluate full dataset
    device: Optional[str] = None
    output_file: Optional[str] = None


@dataclass
class EvaluationResult:
    """Container for evaluation metrics."""
    loss: float = 0.0
    perplexity: float = 0.0
    accuracy: float = 0.0
    n_tokens: int = 0
    n_batches: int = 0
    elapsed_seconds: float = 0.0
    benchmark_scores: Dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            "=" * 55,
            "  Hajeen Evaluation Results",
            "=" * 55,
            f"  Loss        : {self.loss:.4f}",
            f"  Perplexity  : {self.perplexity:.2f}",
            f"  Accuracy    : {self.accuracy * 100:.2f}%",
            f"  Tokens eval : {self.n_tokens:,}",
            f"  Batches     : {self.n_batches}",
            f"  Time        : {self.elapsed_seconds:.1f}s",
        ]
        if self.benchmark_scores:
            lines.append("  Benchmarks:")
            for name, score in self.benchmark_scores.items():
                lines.append(f"    {name:30s}: {score:.4f}")
        lines.append("=" * 55)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "loss": self.loss,
            "perplexity": self.perplexity,
            "accuracy": self.accuracy,
            "n_tokens": self.n_tokens,
            "n_batches": self.n_batches,
            "elapsed_seconds": self.elapsed_seconds,
            "benchmark_scores": self.benchmark_scores,
        }


# ── BLEU-like n-gram precision ─────────────────────────────────────────────

def _ngram_counts(tokens: List[int], n: int) -> Dict[Tuple, int]:
    counts: Dict[Tuple, int] = {}
    for i in range(len(tokens) - n + 1):
        gram = tuple(tokens[i: i + n])
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def compute_bleu(
    references: List[List[int]],
    hypotheses: List[List[int]],
    max_n: int = 4,
) -> float:
    """
    Compute corpus-level BLEU score (simplified, no brevity penalty).

    Args:
        references: List of reference token id sequences.
        hypotheses: List of hypothesis token id sequences.
        max_n: Maximum n-gram order.

    Returns:
        BLEU score in [0, 1].
    """
    precisions = []
    for n in range(1, max_n + 1):
        clipped = 0
        total = 0
        for ref, hyp in zip(references, hypotheses):
            ref_counts = _ngram_counts(ref, n)
            hyp_counts = _ngram_counts(hyp, n)
            for gram, cnt in hyp_counts.items():
                clipped += min(cnt, ref_counts.get(gram, 0))
            total += max(len(hyp) - n + 1, 0)
        if total == 0:
            precisions.append(0.0)
        else:
            precisions.append(clipped / total)

    if any(p == 0 for p in precisions):
        return 0.0

    log_bleu = sum(math.log(p) for p in precisions) / max_n
    return math.exp(log_bleu)


# ── Main evaluation pipeline ───────────────────────────────────────────────

class EvaluationPipeline:
    """
    Full evaluation pipeline for HajeenForCausalLM.

    Computes perplexity, accuracy, and optional benchmark scores.

    Usage:
        pipeline = EvaluationPipeline(model, tokenizer, config)
        result = pipeline.evaluate(val_dataset)
        print(result.summary())
    """

    def __init__(
        self,
        model,
        tokenizer,
        config: Optional[EvaluationConfig] = None,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.config = config or EvaluationConfig()

        if self.config.device:
            self.device = torch.device(self.config.device)
        else:
            self.device = (
                torch.device("cuda") if torch.cuda.is_available()
                else torch.device("cpu")
            )
        self.model.to(self.device)

    @torch.no_grad()
    def evaluate(self, dataset, pad_token_id: int = 0) -> EvaluationResult:
        """
        Run evaluation on a dataset.

        Args:
            dataset: HajeenDataset (or any Dataset with 'input_ids' / 'labels').
            pad_token_id: Padding token id (skipped in metrics).

        Returns:
            EvaluationResult with all metrics.
        """
        from hajeen_model.datasets.dataset_builder import HajeenDataset

        self.model.eval()
        loader = DataLoader(
            dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            collate_fn=lambda b: HajeenDataset.collate_fn(b, pad_token_id=pad_token_id),
        )

        total_loss = 0.0
        total_correct = 0
        total_tokens = 0
        n_batches = 0
        t0 = time.time()

        for batch in loader:
            if self.config.max_batches and n_batches >= self.config.max_batches:
                break

            input_ids = batch["input_ids"].to(self.device)
            labels    = batch["labels"].to(self.device)

            out = self.model(input_ids=input_ids, labels=labels)
            logits = out["logits"]

            # Per-token loss (excluding padding and ignore=-100)
            shift_logits = logits[:, :-1, :].contiguous()
            shift_labels  = labels[:, 1:].contiguous()
            flat_logits   = shift_logits.view(-1, logits.size(-1))
            flat_labels   = shift_labels.view(-1)

            mask = (flat_labels != -100) & (flat_labels != pad_token_id)
            if mask.sum() == 0:
                continue

            active_logits = flat_logits[mask]
            active_labels  = flat_labels[mask]

            token_loss = F.cross_entropy(active_logits, active_labels, reduction="sum")
            total_loss += token_loss.item()

            # Accuracy
            preds = active_logits.argmax(dim=-1)
            total_correct += (preds == active_labels).sum().item()
            total_tokens += mask.sum().item()
            n_batches += 1

        elapsed = time.time() - t0

        if total_tokens == 0:
            return EvaluationResult(elapsed_seconds=elapsed)

        avg_loss = total_loss / total_tokens
        ppl = math.exp(min(avg_loss, 20))
        acc = total_correct / total_tokens

        result = EvaluationResult(
            loss=avg_loss,
            perplexity=ppl,
            accuracy=acc,
            n_tokens=total_tokens,
            n_batches=n_batches,
            elapsed_seconds=elapsed,
        )

        return result

    def run_benchmarks(self, tasks: List[Dict]) -> Dict[str, float]:
        """
        Run custom benchmark tasks.

        Each task is a dict:
            {"name": str, "prompts": List[str], "references": List[str]}

        Returns:
            Dict mapping task name → BLEU score.
        """
        from hajeen_model.inference.inference_engine import InferenceEngine, GenerationConfig

        engine = InferenceEngine(self.model, self.tokenizer, device=str(self.device))
        gen_config = GenerationConfig(do_sample=False, max_new_tokens=128)
        scores = {}

        for task in tasks:
            name = task["name"]
            prompts = task["prompts"]
            references = task.get("references", [])

            hypotheses = [engine.generate(p, gen_config) for p in prompts]

            if references:
                ref_ids = [self.tokenizer.encode(r) for r in references]
                hyp_ids = [self.tokenizer.encode(h) for h in hypotheses]
                bleu = compute_bleu(ref_ids, hyp_ids)
                scores[name] = bleu
            else:
                # Just return average generation length as proxy
                avg_len = sum(len(h.split()) for h in hypotheses) / max(1, len(hypotheses))
                scores[name] = avg_len

        return scores

    def perplexity_on_texts(self, texts: List[str]) -> float:
        """
        Compute perplexity directly on a list of raw texts.

        Useful for quick evaluation without building a full dataset.
        """
        total_nll = 0.0
        total_tokens = 0

        self.model.eval()
        with torch.no_grad():
            for text in texts:
                ids = self.tokenizer.encode(text, add_bos=True, add_eos=True)
                if len(ids) < 2:
                    continue
                t = torch.tensor([ids], dtype=torch.long, device=self.device)
                out = self.model(input_ids=t, labels=t)
                n = len(ids) - 1
                total_nll += out["loss"].item() * n
                total_tokens += n

        if total_tokens == 0:
            return float("inf")

        return math.exp(total_nll / total_tokens)
