"""
Policy Engine — محرك السياسات
================================
يحكم على كل طلب قبل تنفيذه بناءً على السياسات:
- اختيار النماذج
- حماية البيانات
- الخصوصية
- الميزانية
- الصلاحيات
- أخلاقيات التنفيذ
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    MODIFY = "modify"
    WARN = "warn"


class PolicyCategory(str, Enum):
    SAFETY = "safety"
    PRIVACY = "privacy"
    BUDGET = "budget"
    ETHICS = "ethics"
    MODEL_SELECTION = "model_selection"
    DATA_PROTECTION = "data_protection"
    PERMISSIONS = "permissions"


@dataclass
class PolicyRule:
    rule_id: str
    category: PolicyCategory
    name: str
    description: str
    is_active: bool = True
    priority: int = 5  # 1=أعلى

    def evaluate(self, context: Dict[str, Any]) -> "PolicyResult":
        raise NotImplementedError


@dataclass
class PolicyResult:
    rule_id: str
    decision: PolicyDecision
    reason: str
    modifications: Optional[Dict] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class NoHarmfulContentRule(PolicyRule):
    """لا محتوى ضار أو إرشادات خطيرة."""
    HARMFUL_KEYWORDS = [
        "قنبلة", "سلاح", "مخدرات", "bomb", "weapon", "explosive",
        "hack system", "اختراق", "malware", "virus code",
    ]

    def evaluate(self, ctx: Dict) -> PolicyResult:
        text = ctx.get("query", "").lower() + " " + ctx.get("response", "").lower()
        for kw in self.HARMFUL_KEYWORDS:
            if kw in text:
                return PolicyResult(
                    rule_id=self.rule_id,
                    decision=PolicyDecision.BLOCK,
                    reason=f"محتوى ضار محتمل: تم اكتشاف '{kw}'",
                )
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="اجتاز فحص الأمان")


class PrivacyProtectionRule(PolicyRule):
    """حماية البيانات الشخصية."""
    PII_PATTERNS = [
        "رقم الهوية", "رقم الجواز", "كلمة المرور", "password", "secret key",
        "api_key", "credit card", "بطاقة ائتمان",
    ]

    def evaluate(self, ctx: Dict) -> PolicyResult:
        text = ctx.get("query", "").lower()
        for pattern in self.PII_PATTERNS:
            if pattern in text:
                return PolicyResult(
                    rule_id=self.rule_id,
                    decision=PolicyDecision.WARN,
                    reason=f"تحذير: قد تحتوي على بيانات شخصية ({pattern})",
                    modifications={"add_privacy_notice": True},
                )
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="لا بيانات شخصية")


class BudgetRule(PolicyRule):
    """التحكم في تكلفة التوكنز."""
    def __init__(self, *args, daily_limit: int = 100000, current_usage: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self._daily_limit = daily_limit
        self._current_usage = current_usage

    def evaluate(self, ctx: Dict) -> PolicyResult:
        requested = ctx.get("estimated_tokens", 500)
        if self._current_usage + requested > self._daily_limit:
            return PolicyResult(
                rule_id=self.rule_id,
                decision=PolicyDecision.BLOCK,
                reason=f"تجاوز الحد اليومي: {self._current_usage}/{self._daily_limit}",
            )
        if self._current_usage + requested > self._daily_limit * 0.8:
            return PolicyResult(
                rule_id=self.rule_id,
                decision=PolicyDecision.WARN,
                reason=f"80% من الحد اليومي مستهلك: {self._current_usage}/{self._daily_limit}",
                modifications={"prefer_local_model": True},
            )
        self._current_usage += requested
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="ضمن الميزانية")


class LocalFirstRule(PolicyRule):
    """تفضيل النماذج المحلية على السحابية."""
    def evaluate(self, ctx: Dict) -> PolicyResult:
        model = ctx.get("selected_model", "")
        complexity = ctx.get("complexity", "simple")

        if "openai" in model.lower() and complexity in ("simple", "medium"):
            return PolicyResult(
                rule_id=self.rule_id,
                decision=PolicyDecision.MODIFY,
                reason="مهمة بسيطة/متوسطة — جرّب النموذج المحلي أولاً",
                modifications={"prefer_model": "ollama/llama3"},
            )
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="الاختيار مناسب")


@dataclass
class DynamicPolicyRule(PolicyRule):
    rules: Dict[str, Any] = field(default_factory=dict)
    action: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    priority: int = 5  # 1=أعلى


    def evaluate(self, ctx: Dict) -> PolicyResult:
        # Simplified evaluation for demonstration
        # In a real scenario, this would involve complex logic to evaluate the 'rules' against the 'context'
        # and apply the 'action' if rules are met.
        # For now, we'll just check if the model in context matches a rule.
        model_in_context = ctx.get("model", "")
        if "model" in self.rules and self.rules["model"] == model_in_context:
            if self.action.get("type") == "reduce_max_tokens":
                return PolicyResult(
                    rule_id=self.rule_id,
                    decision=PolicyDecision.MODIFY,
                    reason=f"Applying dynamic policy: {self.name}",
                    modifications={"max_tokens_factor": self.action["factor"]}
                )
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="No dynamic policy match")


class EthicsRule(PolicyRule):
    """أخلاقيات التنفيذ — لا تمييز، لا محتوى مضلّل."""
    UNETHICAL_PATTERNS = [
        "اكذب", "اختلق", "ضلّل", "lie", "fake news", "fabricate",
        "تمييز", "discrimination", "racist",
    ]

    def evaluate(self, ctx: Dict) -> PolicyResult:
        text = ctx.get("query", "").lower()
        for pattern in self.UNETHICAL_PATTERNS:
            if pattern in text:
                return PolicyResult(
                    rule_id=self.rule_id,
                    decision=PolicyDecision.BLOCK,
                    reason=f"يتعارض مع أخلاقيات التنفيذ: '{pattern}'",
                )
        return PolicyResult(rule_id=self.rule_id, decision=PolicyDecision.ALLOW, reason="اجتاز الفحص الأخلاقي")


@dataclass
class PolicyEvaluation:
    """نتيجة تقييم جميع السياسات."""
    final_decision: PolicyDecision
    blocked: bool
    warnings: List[str]
    modifications: Dict[str, Any]
    rule_results: List[PolicyResult]
    evaluated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "final_decision": self.final_decision,
            "blocked": self.blocked,
            "warnings": self.warnings,
            "modifications": self.modifications,
            "rules_evaluated": len(self.rule_results),
        }


class PolicyEngine:
    """
    محرك السياسات المركزي.
    يقيّم كل طلب عبر جميع القواعد النشطة قبل التنفيذ.
    """

    def __init__(self) -> None:
        self._rules: List[PolicyRule] = self._build_default_rules()
        self._evaluation_log: List[PolicyEvaluation] = []

    def _build_default_rules(self) -> List[PolicyRule]:
        return [
            NoHarmfulContentRule(
                rule_id="safety-001", category=PolicyCategory.SAFETY,
                name="No Harmful Content", description="منع المحتوى الضار", priority=1
            ),
            EthicsRule(
                rule_id="ethics-001", category=PolicyCategory.ETHICS,
                name="Ethics Check", description="فحص أخلاقيات التنفيذ", priority=2
            ),
            PrivacyProtectionRule(
                rule_id="privacy-001", category=PolicyCategory.PRIVACY,
                name="Privacy Protection", description="حماية البيانات الشخصية", priority=3
            ),
            BudgetRule(
                rule_id="budget-001", category=PolicyCategory.BUDGET,
                name="Token Budget", description="إدارة ميزانية التوكنز",
                priority=4, daily_limit=500000,
            ),
            LocalFirstRule(
                rule_id="model-001", category=PolicyCategory.MODEL_SELECTION,
                name="Local First", description="تفضيل النماذج المحلية", priority=5
            ),
        ]

    async def evaluate(self, context: Dict[str, Any]) -> PolicyEvaluation:
        """تقييم الطلب عبر جميع السياسات."""
        active_rules = sorted(
            [r for r in self._rules if r.is_active],
            key=lambda r: r.priority
        )

        results: List[PolicyResult] = []
        final_decision = PolicyDecision.ALLOW
        warnings: List[str] = []
        modifications: Dict[str, Any] = {}
        blocked = False

        for rule in active_rules:
            try:
                result = rule.evaluate(context)
                results.append(result)

                if result.decision == PolicyDecision.BLOCK:
                    final_decision = PolicyDecision.BLOCK
                    blocked = True
                    break  # توقف فوراً عند الحجب
                elif result.decision == PolicyDecision.WARN:
                    warnings.append(result.reason)
                    if final_decision != PolicyDecision.BLOCK:
                        final_decision = PolicyDecision.WARN
                elif result.decision == PolicyDecision.MODIFY:
                    if result.modifications:
                        modifications.update(result.modifications)
                    if final_decision not in (PolicyDecision.BLOCK, PolicyDecision.WARN):
                        final_decision = PolicyDecision.MODIFY

            except Exception as e:
                logger.error("policy_engine: rule %s error: %s", rule.rule_id, e)

        evaluation = PolicyEvaluation(
            final_decision=final_decision,
            blocked=blocked,
            warnings=warnings,
            modifications=modifications,
            rule_results=results,
            evaluated_at=time.time(),
        )
        self._evaluation_log.append(evaluation)

        logger.info(
            "policy_engine: decision=%s warnings=%d modifications=%d",
            final_decision, len(warnings), len(modifications)
        )
        return evaluation

    async def add_policy(self, name: str, description: str, rules: Dict[str, Any], action: Dict[str, Any]) -> None:
        rule_id = f"dynamic-{uuid.uuid4().hex[:8]}"
        dynamic_rule = DynamicPolicyRule(
            rule_id=rule_id,
            category=PolicyCategory.MODEL_SELECTION, # Or a more appropriate category
            name=name,
            description=description,
            rules=rules,
            action=action
        )
        self._rules.append(dynamic_rule)
        logger.info("policy_engine: added dynamic policy '%s'", name)

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)
        logger.info("policy_engine: added rule '%s'", rule.name)

    def toggle_rule(self, rule_id: str, active: bool) -> bool:
        for rule in self._rules:
            if rule.rule_id == rule_id:
                rule.is_active = active
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._evaluation_log)
        blocked = sum(1 for e in self._evaluation_log if e.blocked)
        return {
            "total_evaluations": total,
            "blocked": blocked,
            "block_rate": round(blocked / total, 3) if total else 0,
            "active_rules": sum(1 for r in self._rules if r.is_active),
            "total_rules": len(self._rules),
        }


# Singleton
_policy_engine: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    global _policy_engine
    if _policy_engine is None:
        _policy_engine = PolicyEngine()
    return _policy_engine
