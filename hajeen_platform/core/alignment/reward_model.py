from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union
import torch
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RewardScore:
    score: float
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class RewardModelPipeline:
    """Pipeline for scoring responses based on a reward model."""

    def __init__(self, model_name_or_path: Optional[str] = None, device: str = "cuda") -> None:
        self.model_name_or_path = model_name_or_path
        self.device = device if torch.cuda.is_available() else "cpu"
        self.model = None
        self.tokenizer = None

    def load_model(self) -> None:
        """Load the reward model and tokenizer."""
        if not self.model_name_or_path:
            logger.warning("No model path provided for RewardModelPipeline")
            return

        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name_or_path)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name_or_path,
                num_labels=1
            ).to(self.device)
            logger.info(f"Reward model loaded from {self.model_name_or_path}")
        except Exception as e:
            logger.error(f"Failed to load reward model: {e}")
            raise

    def score_response(self, prompt: str, response: str) -> RewardScore:
        """Score a single response given a prompt."""
        if self.model is None or self.tokenizer is None:
            # Fallback or dummy scoring if no model is loaded
            return RewardScore(score=0.5, metadata={"status": "dummy_score"})

        inputs = self.tokenizer(prompt, response, return_tensors="pt", truncation=True).to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            score = outputs.logits[0].item()
        
        return RewardScore(score=score)

    def rank_responses(self, prompt: str, responses: List[str]) -> List[Dict[str, Any]]:
        """Rank multiple responses for a single prompt."""
        scored_responses = []
        for resp in responses:
            score_obj = self.score_response(prompt, resp)
            scored_responses.append({
                "response": resp,
                "score": score_obj.score,
                "metadata": score_obj.metadata
            })
        
        # Sort by score descending
        return sorted(scored_responses, key=lambda x: x["score"], reverse=True)
