from __future__ import annotations

import re
from typing import Any, Dict

from hajeen_platform.services.agents.base_agent import AgentResult


def hallucination_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """
    Lightweight hallucination detection.
    Checks for self-contradiction signals and known hallucination markers.
    Returns a score from 0 (certain hallucination) to 1 (likely grounded).
    """
    text = (agent_result.output or "").lower()
    if not text:
        return {"score": 0.0, "detected": True, "reason": "Empty output."}

    HALLUCINATION_SIGNALS = [
        r"\bi (cannot|can't) (actually|really|truly)\b",
        r"\bas of my (knowledge cutoff|last update)\b",
        r"\bi (made up|fabricated|invented) this\b",
        r"\bthis (may|might) not be (accurate|correct|true)\b",
        r"\bi am not (sure|certain|confident) (about|if)\b",
    ]
    for pattern in HALLUCINATION_SIGNALS:
        if re.search(pattern, text):
            return {"score": 0.3, "detected": True, "reason": f"Pattern: {pattern}"}

    # Check for excessively vague output
    if len(text.split()) < 5:
        return {"score": 0.5, "detected": False, "reason": "Very short output — low confidence."}

    return {"score": 0.9, "detected": False, "reason": "No hallucination markers found."}


def agent_success_rate_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Binary success/failure metric based on AgentResult.success."""
    return {
        "score": 1.0 if agent_result.success else 0.0,
        "success": agent_result.success,
        "error": agent_result.error,
    }


def latency_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Latency classification: excellent < 500 ms, good < 2s, slow >= 2s."""
    ms = agent_result.total_duration_ms
    if ms < 500:
        grade = "excellent"
    elif ms < 2000:
        grade = "good"
    elif ms < 5000:
        grade = "slow"
    else:
        grade = "very_slow"
    return {
        "latency_ms": ms,
        "grade": grade,
        "score": max(0.0, 1.0 - ms / 10000),  # normalised 0-1, degrades after 10s
    }


def tool_accuracy_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Ratio of successful tool calls to total tool calls across all steps."""
    total = sum(1 for s in agent_result.steps if s.tool_used)
    succeeded = sum(1 for s in agent_result.steps if s.tool_used and not s.error)
    if total == 0:
        return {"score": 1.0, "total_tool_calls": 0, "succeeded": 0, "note": "No tools used."}
    accuracy = succeeded / total
    return {
        "score": round(accuracy, 4),
        "total_tool_calls": total,
        "succeeded": succeeded,
        "failed": total - succeeded,
    }


def reasoning_depth_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """
    Proxy for reasoning depth: counts reasoning keywords and output length.
    Not a substitute for LLM-based evaluation but useful as a quick signal.
    """
    text = agent_result.output or ""
    REASONING_KEYWORDS = [
        "because", "therefore", "however", "although", "since",
        "as a result", "consequently", "on the other hand", "furthermore",
        "in conclusion", "thus", "given that",
    ]
    keyword_count = sum(1 for kw in REASONING_KEYWORDS if kw in text.lower())
    word_count = len(text.split())
    score = min(1.0, (keyword_count * 0.1) + (word_count / 500) * 0.5)
    return {
        "score": round(score, 4),
        "reasoning_keywords": keyword_count,
        "word_count": word_count,
    }


def step_efficiency_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """
    Ratio of successful steps to total steps.
    Penalises agents that take many failed steps before succeeding.
    """
    total = len(agent_result.steps)
    failed = sum(1 for s in agent_result.steps if s.error)
    if total == 0:
        return {"score": 1.0, "total_steps": 0, "failed_steps": 0}
    efficiency = (total - failed) / total
    return {
        "score": round(efficiency, 4),
        "total_steps": total,
        "failed_steps": failed,
        "succeeded_steps": total - failed,
    }
