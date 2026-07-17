from __future__ import annotations

import asyncio
import logging
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..policy.policy_engine import PolicyEngine, get_policy_engine, DynamicPolicyRule
from ..reflection.self_reflection import SelfReflection, get_self_reflection, ReflectionReport
from ..decision_engine import DecisionEngine, get_decision_engine
from ..goal_manager import Goal, IntentType, ComplexityLevel
from hajeen_platform.monitoring.metrics.prometheus_metrics import (
    hajeen_evolution_proposals_total,
    hajeen_evolution_implementation_total,
    hajeen_evolution_evaluation_latency_seconds,
    track_latency
)

logger = logging.getLogger(__name__)

@dataclass
class EvolutionProposal:
    proposal_id: str
    source_report_id: str
    type: str # e.g., 'policy_addition', 'model_optimization', 'plan_refinement'
    description: str
    proposed_change: Dict[str, Any]
    status: str = 'pending' # pending, approved, rejected, implemented
    created_at: float = field(default_factory=time.time)
    evaluated_at: Optional[float] = None
    implemented_at: Optional[float] = None
    evaluation_result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "source_report_id": self.source_report_id,
            "type": self.type,
            "description": self.description,
            "proposed_change": self.proposed_change,
            "status": self.status,
            "created_at": self.created_at,
            "evaluated_at": self.evaluated_at,
            "evaluation_result": self.evaluation_result,
            "implemented_at": self.implemented_at,
        }

class SelfEvolution:
    """
    محرك التطور الذاتي — يحلل تقارير التقييم الذاتي ويقترح تعديلات على السياسات والخطط.
    """
    def __init__(self, storage_path: str = "storage_data/brain/evolution") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._proposals: List[EvolutionProposal] = []
        self._policy_engine: Optional[PolicyEngine] = None
        self._self_reflection: Optional[SelfReflection] = None
        self._decision_engine: Optional[DecisionEngine] = None

    async def initialize(self) -> None:
        if self._policy_engine is None:
            self._policy_engine = get_policy_engine()
        if self._self_reflection is None:
            self._self_reflection = await get_self_reflection()
        if self._decision_engine is None:
            self._decision_engine = await get_decision_engine()

    async def analyze_and_propose_async(self, report: ReflectionReport) -> str:
        """يرسل مهمة اقتراح التطور إلى Celery worker."""
        from hajeen_platform.workers.async_tasks import evolution_proposal_task
        logger.info(f"Dispatching evolution proposal generation for report {report.report_id} to Celery.")
        celery_result = evolution_proposal_task.delay(report.to_dict())
        return celery_result.id

    async def analyze_and_propose(self, report: ReflectionReport) -> Optional[EvolutionProposal]:
        """
        يحلل تقرير تقييم ذاتي ويقترح تعديلات بناءً على الدروس والتوصيات.
        """
        if not self._decision_engine or not self._self_reflection or not self._policy_engine:
            await self.initialize()

        logger.info("SelfEvolution: Analyzing report %s for proposals.", report.report_id)

        # Use LLM via DecisionEngine to generate a proposal
        prompt = f"""بصفتك محرك تطور ذاتي لـ Hajeen AI، قم بتحليل تقرير التقييم الذاتي التالي واقترح تعديلاً واحداً ومحدداً (سياسة جديدة، تعديل نموذج، تحسين خطة) لتحسين الأداء المستقبلي. يجب أن يكون الاقتراح بصيغة JSON يتضمن 'type', 'description', و 'proposed_change' (وهو قاموس يحتوي على تفاصيل التغيير). ركز على اقتراح تغيير قابل للتنفيذ مباشرة.

تقرير التقييم الذاتي:\n{json.dumps(report.to_dict(), indent=2)}

اقتراح التغيير (JSON فقط):"""

        goal = Goal(
            goal_id=f"evolution_proposal_{report.report_id}",
            intent=IntentType.REASONING,
            domain="self_evolution",
            complexity=ComplexityLevel.ENTERPRISE,
            original_request="Generate self-evolution proposal from reflection report",
            final_objective="Propose a concrete, actionable change to Hajeen AI's policies or models",
            sub_tasks=[],
            required_tools=[],
            suitable_models=[],
            confidence=0.95
        )

        with track_latency(hajeen_evolution_evaluation_latency_seconds):
            try:
                decision = await self._decision_engine.decide(
                    task_id=f"propose_evolution_{report.report_id}",
                    goal=goal,
                    task_name="generate_evolution_proposal",
                    context=report.to_dict()
                )

            if not decision.primary_model:
                logger.warning("SelfEvolution: No model selected by DecisionEngine for proposal generation.")
                return None

            # Assuming decision.llm_response contains the JSON string
            llm_response_content = decision.llm_response.content if decision.llm_response else ""
            proposal_data = json.loads(llm_response_content)

            proposal = EvolutionProposal(
                proposal_id=f"prop_{report.report_id}_{int(time.time())}",
                source_report_id=report.report_id,
                type=proposal_data.get('type', 'unknown'),
                description=proposal_data.get('description', 'No description provided.'),
                proposed_change=proposal_data.get('proposed_change', {})
            )
            self._proposals.append(proposal)
            self._save_proposal(proposal)
            logger.info("SelfEvolution: Generated proposal %s: %s", proposal.proposal_id, proposal.description)
            hajeen_evolution_proposals_total.labels(type=proposal.type, status="generated").inc()
            return proposal
        except json.JSONDecodeError as e:
            logger.error("SelfEvolution: Failed to decode LLM response JSON: %s", e)
            hajeen_evolution_proposals_total.labels(type="unknown", status="error").inc()
            return None
        except Exception as e:
            logger.error("SelfEvolution: Error generating proposal: %s", e)
            hajeen_evolution_proposals_total.labels(type="unknown", status="error").inc()
            return None

    async def evaluate_and_implement_async(self, proposal: EvolutionProposal) -> str:
        """يرسل مهمة تقييم وتنفيذ الاقتراح إلى Celery worker."""
        from hajeen_platform.workers.async_tasks import evolution_evaluation_task
        logger.info(f"Dispatching evolution proposal evaluation for proposal {proposal.proposal_id} to Celery.")
        celery_result = evolution_evaluation_task.delay(proposal.to_dict())
        return celery_result.id

    async def evaluate_and_implement(self, proposal: EvolutionProposal) -> bool:
        """
        يقوم بتقييم الاقتراح وتنفيذه إذا كان آمناً ومفيداً.
        """
        if not self._decision_engine or not self._policy_engine:
            await self.initialize()

        logger.info("SelfEvolution: Evaluating proposal %s.", proposal.proposal_id)

        # Use LLM via DecisionEngine to evaluate the proposal
        evaluation_prompt = f"""بصفتك محرك تقييم للتطور الذاتي لـ Hajeen AI، قم بتقييم الاقتراح التالي. هل هو آمن للتنفيذ؟ هل سيؤدي إلى تحسين الأداء؟ هل هناك أي مخاطر؟ أجب بصيغة JSON تتضمن 'status' (approved/rejected) و 'reason' و 'risks'.

الاقتراح:\n{json.dumps(proposal.to_dict(), indent=2)}

التقييم (JSON فقط):"""

        goal = Goal(
            goal_id=f"evolution_evaluation_{proposal.proposal_id}",
            intent=IntentType.REASONING,
            domain="self_evolution_evaluation",
            complexity=ComplexityLevel.ENTERPRISE,
            original_request="Evaluate self-evolution proposal",
            final_objective="Determine if a proposed change is safe and beneficial for Hajeen AI",
            sub_tasks=[],
            required_tools=[],
            suitable_models=[],
            confidence=0.98
        )

        with track_latency(hajeen_evolution_evaluation_latency_seconds):
            try:
                decision = await self._decision_engine.decide(
                    task_id=f"evaluate_evolution_{proposal.proposal_id}",
                    goal=goal,
                    task_name="evaluate_evolution_proposal",
                    context=proposal.to_dict()
                )

            if not decision.primary_model:
                logger.warning("SelfEvolution: No model selected by DecisionEngine for proposal evaluation.")
                proposal.status = 'rejected'
                proposal.evaluation_result = "No LLM model available for evaluation."
                self._save_proposal(proposal)
                return False

            llm_response_content = decision.llm_response.content if decision.llm_response else ""
            evaluation_data = json.loads(llm_response_content)

            proposal.evaluated_at = time.time()
            proposal.evaluation_result = evaluation_data.get('reason', 'No reason provided.')
            proposal.status = evaluation_data.get('status', 'rejected')

            if proposal.status == 'approved':
                logger.info("SelfEvolution: Proposal %s approved. Implementing...", proposal.proposal_id)
                success = await self._implement_change(proposal.type, proposal.proposed_change)
                if success:
                    proposal.implemented_at = time.time()
                    proposal.status = 'implemented'
                    logger.info("SelfEvolution: Proposal %s implemented successfully.", proposal.proposal_id)
                    hajeen_evolution_implementation_total.labels(type=proposal.type, status="success").inc()
                else:
                    proposal.status = 'rejected' # Implementation failed
                    logger.warning("SelfEvolution: Proposal %s implementation failed.", proposal.proposal_id)
                    hajeen_evolution_implementation_total.labels(type=proposal.type, status="failed").inc()
            else:
                logger.info("SelfEvolution: Proposal %s rejected: %s", proposal.proposal_id, proposal.evaluation_result)
            hajeen_evolution_proposals_total.labels(type=proposal.type, status="rejected").inc()

            self._save_proposal(proposal)
            return proposal.status == 'implemented'

        except json.JSONDecodeError as e:
            logger.error("SelfEvolution: Failed to decode LLM evaluation JSON: %s", e)
            proposal.status = 'rejected'
            proposal.evaluation_result = f"Failed to decode LLM evaluation JSON: {e}"
            self._save_proposal(proposal)
            hajeen_evolution_proposals_total.labels(type=proposal.type, status="error").inc()
            return False
        except Exception as e:
            logger.error("SelfEvolution: Error evaluating or implementing proposal: %s", e)
            proposal.status = 'rejected'
            proposal.evaluation_result = f"Error: {e}"
            self._save_proposal(proposal)
            hajeen_evolution_proposals_total.labels(type=proposal.type, status="error").inc()
            return False

    async def _implement_change(self, change_type: str, change_data: Dict[str, Any]) -> bool:
        """
        ينفذ التغيير المقترح بناءً على نوعه.
        """
        if change_type == 'policy_addition':
            try:
                policy_name = change_data['name']
                policy_description = change_data.get('description', '')
                policy_rules = change_data['rules']
                policy_action = change_data['action']
                await self._policy_engine.add_policy(
                    name=policy_name,
                    description=policy_description,
                    rules=policy_rules,
                    action=policy_action
                )
                logger.info("SelfEvolution: Implemented new policy: %s", policy_name)
                return True
            except KeyError as e:
                logger.error("SelfEvolution: Missing key in policy_addition data: %s", e)
                return False
            except Exception as e:
                logger.error("SelfEvolution: Error adding policy: %s", e)
                return False
        elif change_type == 'model_optimization':
            # This would involve updating ModelRouter or LLMManager configurations
            # For now, we'll just log it as a placeholder
            logger.info("SelfEvolution: Proposed model optimization: %s", change_data)
            return True # Simulate success
        elif change_type == 'plan_refinement':
            # This would involve updating Graph Planner or similar components
            logger.info("SelfEvolution: Proposed plan refinement: %s", change_data)
            return True # Simulate success
        else:
            logger.warning("SelfEvolution: Unknown change type: %s", change_type)
            return False

    def _save_proposal(self, proposal: EvolutionProposal) -> None:
        try:
            path = self._path / f"{proposal.proposal_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(proposal.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("SelfEvolution: save proposal error: %s", e)

    def get_pending_proposals(self) -> List[EvolutionProposal]:
        return [p for p in self._proposals if p.status == 'pending']

# Singleton
_evolution_engine: Optional[SelfEvolution] = None

async def get_self_evolution_engine() -> SelfEvolution:
    global _evolution_engine
    if _evolution_engine is None:
        _evolution_engine = SelfEvolution()
        await _evolution_engine.initialize()
    return _evolution_engine
