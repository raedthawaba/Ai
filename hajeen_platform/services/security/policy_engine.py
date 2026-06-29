from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Policy result type ───────────────────────────────────────────────────────
PolicyDecision = Dict[str, Any]  # {"allowed": bool, "reason": str, "severity": str}


def _allow(reason: str = "OK") -> PolicyDecision:
    return {"allowed": True, "reason": reason, "severity": "none"}


def _deny(reason: str, severity: str = "high") -> PolicyDecision:
    return {"allowed": False, "reason": reason, "severity": severity}


# ── Built-in policies ────────────────────────────────────────────────────────

def prompt_injection_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Detect common prompt injection patterns."""
    text = (context.get("prompt", "") + " " + context.get("content", "")).lower()
    INJECTION_PATTERNS = [
        r"ignore\s+(previous|all|prior)\s+(instructions?|rules?|prompts?)",
        r"disregard\s+(all|previous)\s+rules",
        r"you\s+are\s+now\s+(dan|jailbreak)",
        r"act\s+as\s+(if\s+you\s+(have\s+no|are\s+without)\s+restrictions?)",
        r"forget\s+(your\s+)?(instructions?|training|guidelines?)",
        r"override\s+(system|safety)\s+(prompt|instructions?)",
    ]
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text):
            return _deny(f"Prompt injection pattern detected: '{pattern}'", severity="critical")
    return _allow("No injection detected.")


def pii_protection_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Block output containing obvious PII."""
    text = context.get("output", context.get("content", ""))
    PII_PATTERNS = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
        (r"\b4[0-9]{12}(?:[0-9]{3})?\b", "Credit card (Visa)"),
        (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b", "Phone number"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", "Email address"),
    ]
    for pattern, pii_type in PII_PATTERNS:
        if re.search(pattern, text):
            return _deny(f"PII detected in output: {pii_type}", severity="high")
    return _allow("No PII detected.")


def tool_permission_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Enforce per-agent tool access control."""
    agent_id = context.get("agent_id", "")
    tool_name = context.get("tool_name", "")
    # Define restricted tools and their allowed agents
    RESTRICTED: Dict[str, List[str]] = {
        "shell_exec": ["admin_agent", "system_agent"],
        "file_delete": ["admin_agent"],
        "db_write": ["admin_agent", "data_agent"],
        "network_request": ["admin_agent", "retrieval_agent"],
    }
    allowed_agents = RESTRICTED.get(tool_name)
    if allowed_agents is not None and agent_id not in allowed_agents:
        return _deny(
            f"Agent '{agent_id}' is not authorised to use tool '{tool_name}'.",
            severity="high",
        )
    return _allow(f"Tool '{tool_name}' permitted for agent '{agent_id}'.")


def content_moderation_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Block clearly harmful content."""
    text = (context.get("prompt", "") + " " + context.get("content", "")).lower()
    HARMFUL = [
        "synthesize illegal drugs",
        "build a bomb",
        "create malware",
        "child exploitation",
        "how to hack into",
    ]
    for phrase in HARMFUL:
        if phrase in text:
            return _deny(f"Harmful content detected: '{phrase}'", severity="critical")
    return _allow("Content moderation passed.")


def rate_limit_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Simple per-agent request rate check (expects 'request_count' in context)."""
    agent_id = context.get("agent_id", "unknown")
    request_count = context.get("request_count", 0)
    max_requests = context.get("max_requests", 1000)
    if request_count >= max_requests:
        return _deny(
            f"Agent '{agent_id}' exceeded rate limit ({request_count}/{max_requests}).",
            severity="medium",
        )
    return _allow(f"Rate OK ({request_count}/{max_requests}).")


def agent_sandbox_policy(context: Dict[str, Any]) -> PolicyDecision:
    """Verify agent is running within its declared execution scope."""
    agent_id = context.get("agent_id", "")
    scope = context.get("execution_scope", "")
    declared_scope = context.get("declared_scope", "")
    if declared_scope and scope and scope != declared_scope:
        return _deny(
            f"Agent '{agent_id}' attempted to run in scope '{scope}' "
            f"but is declared for '{declared_scope}'.",
            severity="high",
        )
    return _allow("Scope check passed.")


# ── Policy Engine ────────────────────────────────────────────────────────────

class PolicyEngine:
    """
    Runtime policy enforcement for the Hajeen AI platform.
    Built-in policies are registered automatically; custom policies can be added.
    """

    BUILTIN_POLICIES: Dict[str, Callable] = {
        "prompt_injection": prompt_injection_policy,
        "pii_protection": pii_protection_policy,
        "tool_permission": tool_permission_policy,
        "content_moderation": content_moderation_policy,
        "rate_limit": rate_limit_policy,
        "agent_sandbox": agent_sandbox_policy,
    }

    def __init__(self, enable_builtins: bool = True) -> None:
        self._policies: Dict[str, Callable] = {}
        self._disabled: set = set()
        if enable_builtins:
            self._policies.update(self.BUILTIN_POLICIES)
        logger.info(
            "PolicyEngine initialised with %d policies (%s built-in).",
            len(self._policies),
            "all" if enable_builtins else "none",
        )

    # ── Policy management ────────────────────────────────────────────────

    def register_policy(self, name: str, policy_fn: Callable) -> None:
        self._policies[name] = policy_fn
        logger.debug("Policy '%s' registered.", name)

    def disable_policy(self, name: str) -> None:
        self._disabled.add(name)
        logger.info("Policy '%s' disabled.", name)

    def enable_policy(self, name: str) -> None:
        self._disabled.discard(name)

    def list_policies(self) -> List[str]:
        return [p for p in self._policies if p not in self._disabled]

    # ── Evaluation ───────────────────────────────────────────────────────

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, PolicyDecision]:
        """Run all active policies and return per-policy decisions."""
        results: Dict[str, PolicyDecision] = {}
        for name, fn in self._policies.items():
            if name in self._disabled:
                continue
            try:
                decision = fn(context)
                results[name] = decision
                if not decision.get("allowed", True):
                    logger.warning(
                        "Policy '%s' DENIED — reason: %s (severity: %s)",
                        name,
                        decision.get("reason"),
                        decision.get("severity"),
                    )
            except Exception as exc:
                results[name] = _deny(f"Policy evaluation error: {exc}", severity="low")
                logger.error("Error evaluating policy '%s': %s", name, exc)
        return results

    def enforce(self, context: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Enforce all policies.
        Returns (allowed, denial_reason) where denial_reason is None if allowed.
        """
        results = self.evaluate(context)
        for name, decision in results.items():
            if not decision.get("allowed", True):
                return False, f"[{name}] {decision.get('reason', 'Denied')}"
        return True, None

    def enforce_or_raise(self, context: Dict[str, Any]) -> None:
        """Enforce all policies and raise PolicyViolationError if denied."""
        allowed, reason = self.enforce(context)
        if not allowed:
            raise PolicyViolationError(reason or "Policy denied the action.")


class PolicyViolationError(Exception):
    """Raised when an action is blocked by the policy engine."""
