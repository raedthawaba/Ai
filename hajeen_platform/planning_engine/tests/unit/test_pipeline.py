"""Unit tests for Pipeline Orchestrator."""
import asyncio
import pytest

from planning_engine.pipeline.orchestrator import (
    PipelineOrchestrator,
    PipelineStage,
    PipelineState,
    PipelineContext,
    StageType,
    StageResult,
    PipelineFactory,
)


class TestPipelineOrchestrator:
    """Tests for PipelineOrchestrator class."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance."""
        return PipelineOrchestrator("test_pipeline")

    @pytest.mark.asyncio
    async def test_create_pipeline(self, pipeline):
        """Test pipeline creation."""
        assert pipeline._name == "test_pipeline"
        assert len(pipeline._stages) == 0

    @pytest.mark.asyncio
    async def test_add_stage(self, pipeline):
        """Test adding stages."""
        async def handler(data, ctx):
            return data
        
        stage = PipelineStage(
            stage_id="stage-1",
            name="Test Stage",
            stage_type=StageType.PROCESSING,
            handler=handler,
        )
        
        pipeline.add_stage(stage)
        
        assert len(pipeline._stages) == 1
        assert pipeline._stages[0].name == "Test Stage"

    @pytest.mark.asyncio
    async def test_execute_simple(self, pipeline):
        """Test simple pipeline execution."""
        async def transform_handler(data, ctx):
            return {"transformed": True, "data": data}
        
        async def process_handler(data, ctx):
            return {"processed": True}
        
        pipeline.create_stage(
            name="transform",
            stage_type=StageType.TRANSFORMATION,
            handler=transform_handler,
        )
        
        pipeline.create_stage(
            name="process",
            stage_type=StageType.PROCESSING,
            handler=process_handler,
        )
        
        result = await pipeline.execute({"input": "test"})
        
        assert result is not None
        assert result.shared_data.get("output") is not None

    @pytest.mark.asyncio
    async def test_execute_with_condition(self, pipeline):
        """Test execution with condition."""
        async def handler1(data, ctx):
            return {"step": 1}
        
        async def handler2(data, ctx):
            return {"step": 2}
        
        pipeline.create_stage(
            name="always",
            stage_type=StageType.PROCESSING,
            handler=handler1,
        )
        
        pipeline.create_stage(
            name="conditional",
            stage_type=StageType.PROCESSING,
            handler=handler2,
            condition=lambda data: data.get("skip") is not True,
        )
        
        # Without skip
        result = await pipeline.execute({"test": True})
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_stage_failure(self, pipeline):
        """Test handling stage failure."""
        async def failing_handler(data, ctx):
            raise ValueError("Handler failed")
        
        pipeline.create_stage(
            name="failing",
            stage_type=StageType.PROCESSING,
            handler=failing_handler,
        )
        
        result = await pipeline.execute({})
        
        # Pipeline should complete but with errors
        assert result.metadata.get("error") is not None

    @pytest.mark.asyncio
    async def test_stage_timeout(self, pipeline):
        """Test stage timeout handling."""
        async def slow_handler(data, ctx):
            await asyncio.sleep(10)
            return data
        
        pipeline.create_stage(
            name="slow",
            stage_type=StageType.PROCESSING,
            handler=slow_handler,
            timeout_seconds=0.1,
        )
        
        result = await pipeline.execute({})
        
        # Should timeout
        last_result = result.results[-1]
        assert last_result.success is False
        assert "Timeout" in (last_result.error or "")

    @pytest.mark.asyncio
    async def test_get_statistics(self, pipeline):
        """Test getting pipeline statistics."""
        stats = pipeline.get_statistics()
        
        assert stats["name"] == "test_pipeline"
        assert stats["stages_count"] == 0
        assert stats["running_count"] == 0

    def test_pipeline_factory_validation(self):
        """Test validation pipeline factory."""
        pipeline = PipelineFactory.create_validation_pipeline()
        
        assert pipeline._name == "validation"
        assert len(pipeline._stages) >= 1

    def test_pipeline_factory_processing(self):
        """Test processing pipeline factory."""
        pipeline = PipelineFactory.create_processing_pipeline()
        
        assert pipeline._name == "processing"
        assert len(pipeline._stages) >= 3


class TestPipelineContext:
    """Tests for PipelineContext class."""

    def test_create_context(self):
        """Test context creation."""
        ctx = PipelineContext(
            pipeline_id="pipe-1",
            plan_id="plan-1",
        )
        
        assert ctx.pipeline_id == "pipe-1"
        assert ctx.plan_id == "plan-1"
        assert len(ctx.results) == 0

    def test_get_result(self):
        """Test getting stage result."""
        ctx = PipelineContext(pipeline_id="pipe-1")
        
        ctx.results.append(StageResult(
            stage_id="s1",
            stage_name="stage1",
            success=True,
            started_at=None,
            data={"key": "value"},
        ))
        
        result = ctx.get_result("stage1")
        assert result == {"key": "value"}
        
        none_result = ctx.get_result("nonexistent")
        assert none_result is None

    def test_has_error(self):
        """Test error detection."""
        ctx = PipelineContext(pipeline_id="pipe-1")
        
        assert ctx.has_error() is False
        
        ctx.results.append(StageResult(
            stage_id="s1",
            stage_name="stage1",
            success=False,
            started_at=None,
            error="Failed",
        ))
        
        assert ctx.has_error() is True
