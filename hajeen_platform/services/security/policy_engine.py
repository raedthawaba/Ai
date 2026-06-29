from __future__ import annotations
import logging
from typing import Dict, Any, Callable, List

logger = logging.getLogger(__name__)

class PolicyEngine:
    """Enforces security and safety policies across the AI platform."""

    def __init__(self):
        self._policies: Dict[str, Callable] = {}
        logger.info("PolicyEngine initialized.")

    def register_policy(self, name: str, policy_fn: Callable) -> None:
        """Registers a new policy function."""
        self._policies[name] = policy_fn
        logger.debug(f"Policy \'{name}\' registered.")

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates the given context against all registered policies."""
        results = {}
        for name, policy_fn in self._policies.items():
            try:
                decision = policy_fn(context)
                results[name] = {"decision": decision, "status": "evaluated"}
                if not decision.get("allowed", True):
                    logger.warning(f"Policy \'{name}\' denied action: {decision.get("reason", "No reason provided")}")
            except Exception as e:
                logger.error(f"Error evaluating policy \'{name}\' : {e}")
                results[name] = {"decision": {"allowed": False, "reason": f"Policy evaluation error: {e}"}, "status": "error"}
        return results

    def enforce(self, context: Dict[str, Any]) -> bool:
        """Enforces policies, returning True if all policies allow the action, False otherwise."""
        evaluation_results = self.evaluate(context)
        for policy_name, result in evaluation_results.items():
            if not result["decision"].get("allowed", True):
                logger.warning(f"Action denied by policy: {policy_name}. Reason: {result["decision"].get("reason", "")}")
                return False
        return True

# Example policies
def prompt_injection_policy(context: Dict[str, Any]) -> Dict[str, Any]:
    prompt = context.get("prompt", "").lower()
    if "ignore previous instructions" in prompt or "disregard all rules" in prompt:
        return {"allowed": False, "reason": "Potential prompt injection detected."}
    return {"allowed": True}

def tool_permission_policy(context: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = context.get("agent_id")
    tool_name = context.get("tool_name")
    
    # Example: Only 'admin_agent' can use 'dangerous_tool'
    if tool_name == "dangerous_tool" and agent_id != "admin_agent":
        return {"allowed": False, "reason": f"Agent {agent_id} is not authorized to use {tool_name}."}
    return {"allowed": True}

def content_moderation_policy(context: Dict[str, Any]) -> Dict[str, Any]:
    content = context.get("content", "").lower()
    if "hate speech" in content or "illegal activity" in content:
        return {"allowed": False, "reason": "Content violates moderation guidelines."}
    return {"allowed": True}
