from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from hajeen_platform.services.distributed_messaging.celery_config import celery_app
from hajeen_platform.brain.decision_engine import get_decision_engine
from hajeen_platform.brain.goal_manager import Goal, IntentType, ComplexityLevel

logger = logging.getLogger(__name__)

@celery_app.task(name="hajeen.llm_inference_task", bind=True)
def llm_inference_task(self, task_id: str, goal_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Celery task to perform LLM inference via the DecisionEngine."""
    logger.info(f"[Celery Task] Starting LLM inference for task_id: {task_id}")
    
    # Re-initialize async event loop for Celery worker
    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run_inference():
        decision_engine = await get_decision_engine()
        goal = Goal(**goal_data)
        
        try:
            decision = await decision_engine.decide(
                task_id=task_id,
                goal=goal,
                task_name="llm_inference_task",
                context=context
            )
            if decision and decision.llm_response:
                return {
                    "status": "success",
                    "content": decision.llm_response.content,
                    "model": decision.llm_response.model,
                    "provider": decision.llm_response.provider,
                    "latency_ms": decision.llm_response.latency_ms,
                    "tokens_used": decision.llm_response.tokens_used,
                    "cost_usd": decision.llm_response.cost_usd,
                }
            else:
                logger.warning(f"[Celery Task] DecisionEngine returned no valid response for task_id: {task_id}")
                return {"status": "failed", "error": "No valid LLM response"}
        except Exception as e:
            logger.error(f"[Celery Task] Error during LLM inference for task_id {task_id}: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    result = loop.run_until_complete(_run_inference())
    logger.info(f"[Celery Task] Finished LLM inference for task_id: {task_id} with status: {result.get('status')}")
    return result

@celery_app.task(name="hajeen.reflection_task", bind=True)
def reflection_task(self, task_id: str, goal_id: str, model_used: str, actual_latency_ms: float, actual_tokens: int, estimated_tokens: int, response_quality: float, plan_steps: int, actual_steps: int, context: Dict[str, Any]) -> Dict[str, Any]:
    """Celery task to perform self-reflection."""
    logger.info(f"[Celery Task] Starting self-reflection for task_id: {task_id}")

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run_reflection():
        from hajeen_platform.brain.reflection.self_reflection import get_self_reflection
        reflector = await get_self_reflection()
        report = await reflector.reflect(
            task_id=task_id,
            goal_id=goal_id,
            model_used=model_used,
            actual_latency_ms=actual_latency_ms,
            actual_tokens=actual_tokens,
            estimated_tokens=estimated_tokens,
            response_quality=response_quality,
            plan_steps=plan_steps,
            actual_steps=actual_steps,
            context=context
        )
        return report.to_dict()

    result = loop.run_until_complete(_run_reflection())
    logger.info(f"[Celery Task] Finished self-reflection for task_id: {task_id}")
    return result

@celery_app.task(name="hajeen.evolution_proposal_task", bind=True)
def evolution_proposal_task(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
    """Celery task to generate an evolution proposal from a reflection report."""
    logger.info(f"[Celery Task] Starting evolution proposal generation for report: {report_data.get('report_id')}")

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run_proposal_generation():
        from hajeen_platform.brain.evolution.self_evolution import get_self_evolution_engine, ReflectionReport
        evolution_engine = await get_self_evolution_engine()
        report = ReflectionReport(**report_data)
        proposal = await evolution_engine.analyze_and_propose(report)
        return proposal.to_dict() if proposal else {"status": "failed", "error": "No proposal generated"}

    result = loop.run_until_complete(_run_proposal_generation())
    logger.info(f"[Celery Task] Finished evolution proposal generation for report: {report_data.get('report_id')}")
    return result

@celery_app.task(name="hajeen.evolution_evaluation_task", bind=True)
def evolution_evaluation_task(self, proposal_data: Dict[str, Any]) -> Dict[str, Any]:
    """Celery task to evaluate and implement an evolution proposal."""
    logger.info(f"[Celery Task] Starting evolution proposal evaluation for proposal: {proposal_data.get('proposal_id')}")

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async def _run_proposal_evaluation():
        from hajeen_platform.brain.evolution.self_evolution import get_self_evolution_engine, EvolutionProposal
        evolution_engine = await get_self_evolution_engine()
        proposal = EvolutionProposal(**proposal_data)
        implemented = await evolution_engine.evaluate_and_implement(proposal)
        return {"status": "success" if implemented else "failed", "proposal": proposal.to_dict()}

    result = loop.run_until_complete(_run_proposal_evaluation())
    logger.info(f"[Celery Task] Finished evolution proposal evaluation for proposal: {proposal_data.get('proposal_id')}")
    return result
