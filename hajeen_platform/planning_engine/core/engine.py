"""Planning Engine Core - Main Engine Implementation."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar

from .types import (
    ExecutionResult,
    ExecutionState,
    ExecutionStep,
    Plan,
    PlanContext,
    PlanPriority,
    PlanStatus,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class StepHandler:
    """معالج لخطوة تنفيذ واحدة."""
    name: str
    handler: Callable[[Plan, ExecutionStep], Any]
    timeout_seconds: float = 60.0
    retry_on_failure: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineConfig:
    """إعدادات المحرك."""
    max_concurrent_steps: int = 10
    default_timeout_seconds: float = 60.0
    default_max_retries: int = 3
    enable_parallel_execution: bool = True
    enable_step_caching: bool = False
    cache_ttl_seconds: float = 300.0


class PlanningEngine:
    """
    محرك التخطيط الأساسي - يدير دورة حياة الخطط والتنفيذ.
    
    الميزات:
    - إدارة حالاتPlans
    - تنفيذ الخطوات بشكل متوازٍ أو متسلسل
    - إعادة المحاولة التلقائية
    - تتبع التنفيذ
    - إيقاف/استئناف الخطط
    """

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self._config = config or EngineConfig()
        self._plans: Dict[str, Plan] = {}
        self._step_handlers: Dict[str, StepHandler] = {}
        self._executor = ThreadPoolExecutor(max_workers=self._config.max_concurrent_steps)
        self._running_plans: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._started = False
        self._stopped = False
        
        logger.info(
            "planning_engine: initialized config=%s",
            {
                "max_concurrent": self._config.max_concurrent_steps,
                "parallel_enabled": self._config.enable_parallel_execution,
            }
        )

    async def start(self) -> None:
        """بدء المحرك."""
        if self._started:
            return
        self._started = True
        self._stopped = False
        logger.info("planning_engine: started")

    async def stop(self) -> None:
        """إيقاف المحرك."""
        if self._stopped:
            return
        self._stopped = True
        
        # إلغاء الخطط الجارية
        for plan_id, task in list(self._running_plans.items()):
            if not task.done():
                task.cancel()
                logger.info("planning_engine: cancelled plan=%s", plan_id)
        
        self._running_plans.clear()
        self._executor.shutdown(wait=True)
        logger.info("planning_engine: stopped")

    def register_step_handler(self, handler: StepHandler) -> None:
        """تسجيل معالج لخطوة."""
        self._step_handlers[handler.name] = handler
        logger.debug("planning_engine: registered handler=%s", handler.name)

    def unregister_step_handler(self, name: str) -> None:
        """إلغاء تسجيل معالج."""
        if name in self._step_handlers:
            del self._step_handlers[name]
            logger.debug("planning_engine: unregistered handler=%s", name)

    def create_plan(
        self,
        name: str,
        description: str = "",
        priority: PlanPriority = PlanPriority.MEDIUM,
        context: Optional[PlanContext] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Plan:
        """إنشاء خطة جديدة."""
        plan_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        plan = Plan(
            plan_id=plan_id,
            name=name,
            description=description,
            status=PlanStatus.PENDING,
            priority=priority,
            created_at=now,
            updated_at=now,
            context=context or PlanContext(),
        )
        
        # إضافة الخطوات المحددة
        if steps:
            for step_def in steps:
                step = ExecutionStep(
                    step_id=step_def.get("step_id", str(uuid.uuid4())),
                    name=step_def["name"],
                    description=step_def.get("description", ""),
                    state=ExecutionState.IDLE,
                    max_retries=step_def.get("max_retries", self._config.default_max_retries),
                    metadata=step_def.get("metadata", {}),
                )
                plan.add_step(step)
        
        self._plans[plan_id] = plan
        logger.info(
            "planning_engine: created plan=%s name=%s steps=%d priority=%s",
            plan_id, name, len(plan.steps), priority.name
        )
        return plan

    async def execute(
        self,
        context: PlanContext,
        steps: List[Dict[str, Any]],
    ) -> ExecutionResult:
        """إنشاء وتنفيذ خطة وإرجاع النتيجة."""
        plan = self.create_plan(
            name=f"plan_{context.goal[:50]}",
            description=f"Execution plan for: {context.goal}",
            priority=context.priority,
            context=context,
            steps=steps,
        )
        
        result = await self.execute_plan(plan.plan_id)
        
        # إضافة معلومات السياق إلى النتيجة
        result.context = context
        result.priority = context.priority
        
        return result

    async def execute_plan(self, plan_id: str) -> ExecutionResult:
        """تنفيذ خطة معينة."""
        async with self._lock:
            if plan_id not in self._plans:
                raise ValueError(f"Plan not found: {plan_id}")
            plan = self._plans[plan_id]
            
            if plan.status == PlanStatus.RUNNING:
                raise ValueError(f"Plan already running: {plan_id}")
            
            plan.status = PlanStatus.RUNNING
            plan.updated_at = datetime.utcnow()
        
        start_time = time.time()
        errors: List[str] = []
        results: Dict[str, Any] = {}
        
        try:
            for step in plan.steps:
                step.state = ExecutionState.PREPARING
                step.started_at = datetime.utcnow()
                
                try:
                    result = await self._execute_step(plan, step)
                    plan.complete_step(step.step_id, result)
                    results[step.step_id] = result
                    
                except Exception as e:
                    error_msg = f"Step {step.name} failed: {str(e)}"
                    logger.error("planning_engine: step_failed plan=%s step=%s error=%s", 
                                plan_id, step.name, str(e))
                    plan.fail_step(step.step_id, str(e))
                    errors.append(error_msg)
                    
                    # إعادة المحاولة إذا كان مفعلاً
                    step_handler = self._step_handlers.get(step.name)
                    if step_handler and step_handler.retry_on_failure:
                        if plan.retry_step(step.step_id):
                            try:
                                result = await self._execute_step(plan, step)
                                plan.complete_step(step.step_id, result)
                                results[step.step_id] = result
                                if step.step_id in errors:
                                    errors.remove(error_msg)
                            except Exception as retry_error:
                                errors.append(f"Retry failed: {str(retry_error)}")
            
            # تحديث حالة الخطة
            async with self._lock:
                plan.status = PlanStatus.COMPLETED if not errors else PlanStatus.FAILED
                plan.updated_at = datetime.utcnow()
                plan.total_duration_ms = (time.time() - start_time) * 1000
            
        except asyncio.CancelledError:
            async with self._lock:
                plan.status = PlanStatus.CANCELLED
                plan.updated_at = datetime.utcnow()
            raise
        
        total_duration = (time.time() - start_time) * 1000
        
        return ExecutionResult(
            plan_id=plan_id,
            success=len(errors) == 0,
            completed_steps=len(plan.completed_steps),
            failed_steps=len(plan.failed_steps),
            total_duration_ms=total_duration,
            errors=errors,
            results=results,
        )

    async def _execute_step(self, plan: Plan, step: ExecutionStep) -> Any:
        """تنفيذ خطوة واحدة."""
        step.state = ExecutionState.EXECUTING
        step.started_at = datetime.utcnow()
        
        handler = self._step_handlers.get(step.name)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler.handler):
                    result = await asyncio.wait_for(
                        handler.handler(plan, step),
                        timeout=handler.timeout_seconds
                    )
                else:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(self._executor, handler.handler, plan, step),
                        timeout=handler.timeout_seconds
                    )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Step {step.name} timed out after {handler.timeout_seconds}s")
        else:
            # محاكاة التنفيذ إذا لم يكن هناك معالج
            await asyncio.sleep(0.1)
            result = {"status": "simulated", "step": step.name}
        
        return result

    async def execute_plan_async(self, plan_id: str) -> asyncio.Task:
        """تنفيذ خطة بشكل غير متزامن وإرجاع المهمة."""
        async with self._lock:
            if plan_id in self._running_plans:
                raise ValueError(f"Plan already running: {plan_id}")
        
        task = asyncio.create_task(self.execute_plan(plan_id))
        self._running_plans[plan_id] = task
        
        def cleanup(t: asyncio.Task) -> None:
            self._running_plans.pop(plan_id, None)
        
        task.add_done_callback(cleanup)
        return task

    async def cancel_plan(self, plan_id: str) -> bool:
        """إلغاء خطة."""
        if plan_id in self._running_plans:
            self._running_plans[plan_id].cancel()
            return True
        
        if plan_id in self._plans:
            self._plans[plan_id].status = PlanStatus.CANCELLED
            self._plans[plan_id].updated_at = datetime.utcnow()
            return True
        
        return False

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        """الحصول على خطة."""
        return self._plans.get(plan_id)

    def list_plans(self, status: Optional[PlanStatus] = None) -> List[Plan]:
        """قائمة الخطط."""
        plans = list(self._plans.values())
        if status:
            plans = [p for p in plans if p.status == status]
        return sorted(plans, key=lambda p: (p.priority.value, p.created_at))

    def delete_plan(self, plan_id: str) -> bool:
        """حذف خطة."""
        if plan_id in self._plans:
            del self._plans[plan_id]
            logger.info("planning_engine: deleted plan=%s", plan_id)
            return True
        return False

    def get_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات المحرك."""
        total = len(self._plans)
        by_status = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
        }
        for plan in self._plans.values():
            by_status[plan.status.value] = by_status.get(plan.status.value, 0) + 1
        
        return {
            "total_plans": total,
            "by_status": by_status,
            "running_plans": len(self._running_plans),
            "registered_handlers": len(self._step_handlers),
            "config": {
                "max_concurrent": self._config.max_concurrent_steps,
                "parallel_enabled": self._config.enable_parallel_execution,
            },
        }


# Singleton instance
_engine: Optional[PlanningEngine] = None
_engine_lock = asyncio.Lock()


async def get_engine() -> PlanningEngine:
    """الحصول على مثيل المحرك الوحيد."""
    global _engine
    if _engine is None:
        async with _engine_lock:
            if _engine is None:
                _engine = PlanningEngine()
                await _engine.start()
    return _engine


async def shutdown_engine() -> None:
    """إيقاف المحرك."""
    global _engine
    if _engine is not None:
        await _engine.stop()
        _engine = None
