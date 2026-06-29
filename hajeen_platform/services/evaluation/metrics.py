from __future__ import annotations
from typing import Dict, Any
from hajeen_platform.services.agents.base_agent import AgentResult

def hallucination_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Simulates a hallucination detection metric."""
    # In a real scenario, this would involve comparing output to ground truth or using an LLM to detect hallucinations.
    # For now, we'll simulate a simple check.
    if "hallucination" in agent_result.output.lower():
        return {"score": 0.1, "detected": True, "reason": "Keyword 'hallucination' found"}
    return {"score": 0.9, "detected": False}

def agent_success_rate_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Calculates agent success rate based on AgentResult."""
    return {"score": 1.0 if agent_result.success else 0.0, "success": agent_result.success}

def latency_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Measures the latency of the agent's execution."""
    return {"latency_ms": agent_result.total_duration_ms}

def tool_accuracy_metric(agent_result: AgentResult) -> Dict[str, Any]:
    """Simulates tool accuracy scoring based on agent steps."""
    successful_tool_calls = 0
    total_tool_calls = 0
    for step in agent_result.steps:
        if step.tool_used:
            total_tool_calls += 1
            if not step.error:
                successful_tool_calls += 1
    
    if total_tool_calls == 0:
        return {"score": 1.0, "total_tool_calls": 0, "successful_tool_calls": 0}
    
    accuracy = successful_tool_calls / total_tool_calls
    return {"score": accuracy, "total_tool_calls": total_tool_calls, "successful_tool_calls": successful_tool_calls}
