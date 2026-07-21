"""Unit tests for Planning Engine Core."""
import asyncio
import pytest
from datetime import datetime

from planning_engine.core.types import (
    Plan,
    PlanStatus,
    PlanPriority,
    PlanContext,
    ExecutionStep,
    ExecutionState,
    ExecutionResult,
)
from planning_engine.core.engine import (
    PlanningEngine,
    EngineConfig,
    StepHandler,
)


class TestPlan:
    """Tests for Plan class."""

    def test_create_plan(self):
        """Test plan creation."""
        plan = Plan(
            plan_id="test-1",
            name="Test Plan",
            description="A test plan",
            status=PlanStatus.PENDING,
            priority=PlanPriority.MEDIUM,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        assert plan.plan_id == "test-1"
        assert plan.name == "Test Plan"
        assert plan.status == PlanStatus.PENDING
        assert plan.priority == PlanPriority.MEDIUM
        assert len(plan.steps) == 0

    def test_add_step(self):
        """Test adding steps to plan."""
        plan = Plan(
            plan_id="test-2",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.LOW,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        step = ExecutionStep(
            step_id="step-1",
            name="Step 1",
            description="First step",
            state=ExecutionState.IDLE,
        )
        
        plan.add_step(step)
        
        assert len(plan.steps) == 1
        assert plan.steps[0].name == "Step 1"

    def test_complete_step(self):
        """Test completing a step."""
        plan = Plan(
            plan_id="test-3",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.HIGH,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        step = ExecutionStep(
            step_id="step-1",
            name="Step 1",
            description="",
            state=ExecutionState.IDLE,
            started_at=datetime.utcnow(),
        )
        plan.add_step(step)
        
        plan.complete_step("step-1", {"result": "success"})
        
        assert plan.steps[0].state == ExecutionState.COMPLETED
        assert plan.steps[0].result == {"result": "success"}
        assert "step-1" in plan.completed_steps

    def test_fail_step(self):
        """Test failing a step."""
        plan = Plan(
            plan_id="test-4",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.MEDIUM,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        step = ExecutionStep(
            step_id="step-1",
            name="Step 1",
            description="",
            state=ExecutionState.IDLE,
        )
        plan.add_step(step)
        
        plan.fail_step("step-1", "Something went wrong")
        
        assert plan.steps[0].state == ExecutionState.FAILED
        assert plan.steps[0].error == "Something went wrong"
        assert "step-1" in plan.failed_steps

    def test_retry_step(self):
        """Test retrying a step."""
        plan = Plan(
            plan_id="test-5",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.MEDIUM,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        step = ExecutionStep(
            step_id="step-1",
            name="Step 1",
            description="",
            state=ExecutionState.FAILED,
            max_retries=3,
            retry_count=1,
        )
        plan.add_step(step)
        plan.failed_steps.append("step-1")
        
        result = plan.retry_step("step-1")
        
        assert result is True
        assert plan.steps[0].state == ExecutionState.IDLE
        assert plan.steps[0].retry_count == 2
        assert "step-1" not in plan.failed_steps

    def test_progress(self):
        """Test progress calculation."""
        plan = Plan(
            plan_id="test-6",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.MEDIUM,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        for i in range(4):
            step = ExecutionStep(
                step_id=f"step-{i}",
                name=f"Step {i}",
                description="",
                state=ExecutionState.IDLE,
            )
            plan.add_step(step)
        
        assert plan.get_progress() == 0.0
        
        plan.complete_step("step-0")
        plan.complete_step("step-1")
        
        assert plan.get_progress() == 50.0

    def test_is_complete(self):
        """Test is_complete check."""
        plan = Plan(
            plan_id="test-7",
            name="Test Plan",
            description="",
            status=PlanStatus.PENDING,
            priority=PlanPriority.MEDIUM,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            context=PlanContext(),
        )
        
        step1 = ExecutionStep(step_id="s1", name="S1", description="", state=ExecutionState.COMPLETED)
        step2 = ExecutionStep(step_id="s2", name="S2", description="", state=ExecutionState.COMPLETED)
        plan.steps = [step1, step2]
        
        assert plan.is_complete() is True
        
        step3 = ExecutionStep(step_id="s3", name="S3", description="", state=ExecutionState.IDLE)
        plan.steps.append(step3)
        
        assert plan.is_complete() is False


class TestPlanningEngine:
    """Tests for PlanningEngine class."""

    @pytest.fixture
    def engine(self):
        """Create engine instance."""
        config = EngineConfig(
            max_concurrent_steps=5,
            default_timeout_seconds=1.0,
            enable_parallel_execution=False,
        )
        return PlanningEngine(config)

    @pytest.mark.asyncio
    async def test_engine_lifecycle(self, engine):
        """Test engine start and stop."""
        await engine.start()
        assert engine._started is True
        assert engine._stopped is False
        
        await engine.stop()
        assert engine._stopped is True

    @pytest.mark.asyncio
    async def test_create_plan(self, engine):
        """Test plan creation through engine."""
        await engine.start()
        
        plan = engine.create_plan(
            name="My Plan",
            description="Test plan",
            priority=PlanPriority.HIGH,
        )
        
        assert plan is not None
        assert plan.name == "My Plan"
        assert plan.status == PlanStatus.PENDING
        assert len(engine._plans) == 1
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_register_handler(self, engine):
        """Test step handler registration."""
        async def handler(plan, step):
            return {"processed": True}
        
        handler_obj = StepHandler(
            name="test_handler",
            handler=handler,
            timeout_seconds=5.0,
        )
        
        engine.register_step_handler(handler_obj)
        
        assert "test_handler" in engine._step_handlers

    @pytest.mark.asyncio
    async def test_execute_plan(self, engine):
        """Test plan execution."""
        await engine.start()
        
        # Register a simple handler
        async def simple_handler(plan, step):
            await asyncio.sleep(0.01)
            return {"step": step.name, "done": True}
        
        engine.register_step_handler(StepHandler(
            name="process",
            handler=simple_handler,
        ))
        
        # Create plan with steps
        plan = engine.create_plan(
            name="Execution Test",
            steps=[
                {"name": "process", "description": "Process something"},
            ],
        )
        
        # Execute
        result = await engine.execute_plan(plan.plan_id)
        
        assert result is not None
        assert result.plan_id == plan.plan_id
        assert result.completed_steps == 1
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_get_plan(self, engine):
        """Test getting a plan."""
        await engine.start()
        
        plan = engine.create_plan(name="Find Me")
        retrieved = engine.get_plan(plan.plan_id)
        
        assert retrieved is not None
        assert retrieved.plan_id == plan.plan_id
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_list_plans(self, engine):
        """Test listing plans."""
        await engine.start()
        
        engine.create_plan(name="Plan 1")
        engine.create_plan(name="Plan 2", priority=PlanPriority.HIGH)
        
        plans = engine.list_plans()
        assert len(plans) == 2
        
        high_priority = engine.list_plans(status=PlanStatus.PENDING)
        assert len(high_priority) == 2
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_delete_plan(self, engine):
        """Test deleting a plan."""
        await engine.start()
        
        plan = engine.create_plan(name="Delete Me")
        result = engine.delete_plan(plan.plan_id)
        
        assert result is True
        assert plan.plan_id not in engine._plans
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_statistics(self, engine):
        """Test getting engine statistics."""
        await engine.start()
        
        engine.create_plan(name="Plan 1")
        engine.create_plan(name="Plan 2")
        
        stats = engine.get_statistics()
        
        assert stats["total_plans"] == 2
        assert stats["registered_handlers"] == 0
        
        await engine.stop()
