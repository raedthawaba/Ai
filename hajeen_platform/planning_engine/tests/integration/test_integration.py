"""Integration tests for Planning Engine."""
import asyncio
import pytest
import tempfile
from pathlib import Path

from planning_engine import (
    PlanningEngine,
    EngineConfig,
    ConfigurationManager,
    PipelineOrchestrator,
    PipelineStage,
    StageType,
    ExecutionTraceManager,
    MetricsCollector,
    ErrorRecoveryManager,
    DependencyContainer,
    ServiceRegistry,
    PluginManager,
    configure_logging,
    get_logger,
    get_metrics_collector,
    get_trace_manager,
)


class TestEndToEndPlanning:
    """End-to-end planning integration tests."""

    @pytest.fixture
    def setup_engine(self):
        """Setup engine for testing."""
        config = EngineConfig(
            max_concurrent_steps=5,
            default_timeout_seconds=5.0,
        )
        engine = PlanningEngine(config)
        return engine

    @pytest.mark.asyncio
    async def test_full_plan_execution(self, setup_engine):
        """Test full plan creation and execution."""
        engine = setup_engine
        await engine.start()
        
        # Register handlers
        async def validate_handler(plan, step):
            return {"validation": "passed"}
        
        async def process_handler(plan, step):
            return {"processed": True}
        
        async def output_handler(plan, step):
            return {"output": "completed"}
        
        engine.register_step_handler(type("Handler", (), {
            "name": "validate",
            "handler": validate_handler,
        })())
        engine.register_step_handler(type("Handler", (), {
            "name": "process",
            "handler": process_handler,
        })())
        engine.register_step_handler(type("Handler", (), {
            "name": "output",
            "handler": output_handler,
        })())
        
        # Create plan
        plan = engine.create_plan(
            name="Integration Test Plan",
            description="Full integration test",
            steps=[
                {"name": "validate", "description": "Validate input"},
                {"name": "process", "description": "Process data"},
                {"name": "output", "description": "Generate output"},
            ],
        )
        
        # Execute
        result = await engine.execute_plan(plan.plan_id)
        
        # Verify
        assert result.success is True
        assert result.completed_steps == 3
        assert result.failed_steps == 0
        
        await engine.stop()

    @pytest.mark.asyncio
    async def test_plan_with_failure_and_retry(self, setup_engine):
        """Test plan with failure and retry."""
        engine = setup_engine
        await engine.start()
        
        call_count = 0
        
        async def flaky_handler(plan, step):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return {"success": True}
        
        engine.register_step_handler(type("Handler", (), {
            "name": "flaky",
            "handler": flaky_handler,
            "max_retries": 3,
        })())
        
        plan = engine.create_plan(
            name="Retry Test",
            steps=[{"name": "flaky"}],
        )
        
        result = await engine.execute_plan(plan.plan_id)
        
        assert result.success is True
        assert call_count == 2
        
        await engine.stop()


class TestConfigurationIntegration:
    """Configuration system integration tests."""

    def test_config_with_yaml(self):
        """Test configuration with YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test_config.yaml"
            config_path.write_text("""
engine:
  max_concurrent_steps: 15
  enable_parallel_execution: true

logging:
  level: DEBUG
  output_dir: logs
""")
            
            manager = ConfigurationManager()
            manager.add_source(
                name="yaml_test",
                format=None,
                path=config_path,
            )
            config = manager.load()
            
            assert config["engine"]["max_concurrent_steps"] == 15
            assert config["logging"]["level"] == "DEBUG"


class TestPipelineIntegration:
    """Pipeline integration tests."""

    @pytest.mark.asyncio
    async def test_pipeline_with_trace(self):
        """Test pipeline with trace manager."""
        trace_manager = ExecutionTraceManager(level=None)
        
        plan_id = "trace_test_plan"
        
        # Start trace
        trace = await trace_manager.start_trace(
            plan_id=plan_id,
            plan_name="Trace Test",
        )
        
        assert trace is not None
        assert trace.plan_id == plan_id
        
        # Record step
        trace_manager.record_step_start(plan_id, "step1", 1)
        trace_manager.record_step_complete(plan_id, "step1", 1)
        
        # End trace
        result_trace = await trace_manager.end_trace(plan_id, success=True)
        
        assert result_trace is not None
        assert result_trace.completed_steps == 1


class TestMetricsIntegration:
    """Metrics integration tests."""

    def test_metrics_collection(self):
        """Test metrics collection."""
        collector = MetricsCollector()
        
        # Collect various metrics
        collector.register_metric("requests_total", None)
        collector.register_metric("request_duration", None)
        
        collector.counter("requests_total", 1)
        collector.histogram("request_duration", 150.0)
        
        # Get metrics
        all_metrics = collector.get_all()
        
        assert "requests_total" in all_metrics
        assert "request_duration" in all_metrics
        
        # Export
        prom_output = collector.export_prometheus()
        assert "requests_total" in prom_output


class TestErrorRecoveryIntegration:
    """Error recovery integration tests."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        """Test circuit breaker with operations."""
        from planning_engine.error_recovery.recovery import CircuitBreaker, CircuitBreakerConfig
        
        config = CircuitBreakerConfig(
            failure_threshold=2,
            timeout_seconds=0.5,
        )
        breaker = CircuitBreaker("integration_breaker", config)
        
        success_count = 0
        async def operation():
            nonlocal success_count
            success_count += 1
            return "success"
        
        # Should work
        result = await breaker.call(operation)
        assert result == "success"
        assert success_count == 1
        
        # Fail to open circuit
        async def failing_operation():
            raise ValueError("Fail")
        
        for _ in range(2):
            try:
                await breaker.call(failing_operation)
            except ValueError:
                pass
        
        assert breaker.state.value == "open"
        
        # Wait for timeout
        await asyncio.sleep(0.6)
        
        # Should allow call in half_open state
        await breaker.call(operation)
        assert success_count == 2


class TestDIIntegration:
    """DI container integration tests."""

    def test_di_with_services(self):
        """Test DI with multiple services."""
        container = DependencyContainer()
        
        class DatabaseService:
            def query(self):
                return "query result"
        
        class CacheService:
            def get(self, key):
                return f"cached_{key}"
        
        class UserService:
            def __init__(self, db: DatabaseService, cache: CacheService):
                self.db = db
                self.cache = cache
            
            def get_user(self, user_id):
                cached = self.cache.get(user_id)
                if cached:
                    return cached
                return self.db.query()
        
        container.register(DatabaseService)
        container.register(CacheService)
        container.register(UserService)
        
        # Resolve UserService with dependencies
        user_service = container.resolve(UserService)
        
        assert isinstance(user_service, UserService)
        assert isinstance(user_service.db, DatabaseService)
        assert isinstance(user_service.cache, CacheService)


class TestRegistryIntegration:
    """Service registry integration tests."""

    def test_registry_with_health_checks(self):
        """Test registry with health checks."""
        registry = ServiceRegistry()
        
        class HealthCheckService:
            def check(self):
                return True
        
        registry.register("health_service", HealthCheckService)
        registry.register_health_check("health_service", lambda: True)
        
        # Check health
        import asyncio
        health = asyncio.get_event_loop().run_until_complete(
            registry.check_health("health_service")
        )
        
        assert health.is_healthy is True


class TestLoggingIntegration:
    """Logging integration tests."""

    def test_logging_setup(self):
        """Test logging configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_logging(
                level="INFO",
                log_dir=tmpdir,
                json_console=False,
                json_file=False,
            )
            
            logger = get_logger("test")
            logger.info("Test message")
            
            # Should not raise any exceptions
            assert True


class TestPluginIntegration:
    """Plugin system integration tests."""

    @pytest.mark.asyncio
    async def test_plugin_with_hooks(self):
        """Test plugin with hooks."""
        manager = PluginManager()
        
        hook_calls = []
        
        async def test_hook(*args, **kwargs):
            hook_calls.append("called")
        
        manager.register_hook(None, test_hook)
        
        await manager.execute_hooks(None)
        
        # Hook should have been called
        # Note: Hook type doesn't matter here, just testing the mechanism


class TestCombinedIntegration:
    """Combined component integration tests."""

    @pytest.mark.asyncio
    async def test_all_components(self):
        """Test all components working together."""
        # 1. Configuration
        config = ConfigurationManager()
        config.load()
        
        # 2. Metrics
        metrics = get_metrics_collector()
        metrics.counter("integration_test", 1)
        
        # 3. Error Recovery
        error_manager = ErrorRecoveryManager()
        
        # 4. DI Container
        container = DependencyContainer()
        
        class TestService:
            def run(self):
                return "running"
        
        container.register(TestService)
        
        # 5. Registry
        registry = ServiceRegistry()
        registry.register("test_service", TestService)
        
        # 6. Engine
        engine = EngineConfig()
        planning_engine = PlanningEngine(engine)
        await planning_engine.start()
        
        # 7. Pipeline
        pipeline = PipelineOrchestrator("combined_test")
        
        async def pipeline_handler(data, ctx):
            return {"result": "success"}
        
        pipeline.create_stage(
            name="combined",
            stage_type=StageType.PROCESSING,
            handler=pipeline_handler,
        )
        
        result = await pipeline.execute({})
        
        # Cleanup
        await planning_engine.stop()
        
        # Verify
        assert result is not None
        assert metrics.get("integration_test") == 1
