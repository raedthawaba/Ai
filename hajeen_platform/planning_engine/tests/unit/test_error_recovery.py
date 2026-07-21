"""Unit tests for Error Recovery and Circuit Breaker."""
import asyncio
import pytest
import time

from planning_engine.error_recovery.recovery import (
    ErrorRecoveryManager,
    RecoveryPolicy,
    ErrorContext,
    RecoveryResult,
    RecoveryAction,
    ErrorSeverity,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    RetryStrategy,
)


class TestRetryStrategy:
    """Tests for RetryStrategy class."""

    def test_exponential_backoff(self):
        """Test exponential backoff calculation."""
        delay = RetryStrategy.exponential_backoff(
            attempt=0,
            base_delay=1.0,
            max_delay=60.0,
            jitter=False,
        )
        assert delay == 1.0
        
        delay = RetryStrategy.exponential_backoff(
            attempt=2,
            base_delay=1.0,
            max_delay=60.0,
            jitter=False,
        )
        assert delay == 4.0

    def test_exponential_backoff_with_max(self):
        """Test exponential backoff with max limit."""
        delay = RetryStrategy.exponential_backoff(
            attempt=10,
            base_delay=1.0,
            max_delay=60.0,
            jitter=False,
        )
        assert delay == 60.0

    def test_linear_backoff(self):
        """Test linear backoff."""
        delay = RetryStrategy.linear_backoff(
            attempt=0,
            base_delay=1.0,
            max_delay=10.0,
        )
        assert delay == 1.0
        
        delay = RetryStrategy.linear_backoff(
            attempt=5,
            base_delay=1.0,
            max_delay=10.0,
        )
        assert delay == 6.0

    def test_constant_backoff(self):
        """Test constant backoff."""
        delay = RetryStrategy.constant_backoff(
            attempt=5,
            delay=2.0,
        )
        assert delay == 2.0


class TestErrorRecoveryManager:
    """Tests for ErrorRecoveryManager class."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        policy = RecoveryPolicy(
            max_retries=2,
            retry_delay_seconds=0.01,
            exponential_backoff=False,
        )
        return ErrorRecoveryManager(policy)

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self, manager):
        """Test successful execution."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await manager.execute_with_retry(operation, "test_error")
        
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_failure(self, manager):
        """Test retry on failure."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            await manager.execute_with_retry(operation, "test_error")
        
        # Should have tried max_retries + 1 times
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_safe(self, manager):
        """Test safe execution."""
        def failing_operation():
            raise ValueError("Error")
        
        result = await manager.execute_safe(
            failing_operation,
            fallback_value="fallback",
        )
        
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_register_fallback(self, manager):
        """Test registering fallback."""
        def fallback(ctx):
            return "fallback_result"
        
        manager.register_fallback("test_error", fallback)
        
        assert "test_error" in manager._fallback_handlers

    def test_get_policy(self, manager):
        """Test getting policy."""
        policy = manager.get_policy("custom_error")
        
        assert policy.max_retries == 2

    def test_set_policy(self, manager):
        """Test setting policy."""
        new_policy = RecoveryPolicy(max_retries=5)
        manager.set_policy("custom_error", new_policy)
        
        policy = manager.get_policy("custom_error")
        assert policy.max_retries == 5

    @pytest.mark.asyncio
    async def test_error_history(self, manager):
        """Test error history tracking."""
        def operation():
            raise ValueError("Test error")
        
        try:
            await manager.execute_with_retry(operation, "history_error")
        except ValueError:
            pass
        
        history = manager.get_error_history()
        assert len(history) >= 1

    def test_error_statistics(self, manager):
        """Test error statistics."""
        stats = manager.get_error_statistics()
        
        assert "total_errors" in stats
        assert "errors_by_type" in stats


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def breaker(self):
        """Create circuit breaker instance."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=0.5,
        )
        return CircuitBreaker("test_breaker", config)

    def test_initial_state(self, breaker):
        """Test initial state is CLOSED."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.is_available() is True

    @pytest.mark.asyncio
    async def test_open_on_failures(self, breaker):
        """Test circuit opens after failures."""
        async def failing_operation():
            raise ValueError("Fail")
        
        for _ in range(3):
            try:
                await breaker.call(failing_operation)
            except ValueError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.is_available() is False

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, breaker):
        """Test circuit goes to HALF_OPEN after timeout."""
        async def failing_operation():
            raise ValueError("Fail")
        
        for _ in range(3):
            try:
                await breaker.call(failing_operation)
            except ValueError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(0.6)
        
        # Should transition to HALF_OPEN on next availability check
        is_available = breaker.is_available()
        assert is_available is True
        # State might be HALF_OPEN now

    @pytest.mark.asyncio
    async def test_close_after_successes(self, breaker):
        """Test circuit closes after successes in HALF_OPEN."""
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count = 0
        
        async def success_operation():
            return "success"
        
        for _ in range(2):
            await breaker._on_success()
        
        assert breaker.state == CircuitState.CLOSED

    def test_get_stats(self, breaker):
        """Test getting stats."""
        stats = breaker.get_stats()
        
        assert stats["name"] == "test_breaker"
        assert "state" in stats

    @pytest.mark.asyncio
    async def test_reset(self, breaker):
        """Test resetting breaker."""
        breaker._state = CircuitState.OPEN
        breaker._failure_count = 5
        
        await breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_call_when_open(self, breaker):
        """Test calling when circuit is open."""
        breaker._state = CircuitState.OPEN
        breaker._last_failure_time = time.time()
        
        async def operation():
            return "success"
        
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(operation)


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry class."""

    def test_get_or_create(self):
        """Test getting or creating breaker."""
        registry = CircuitBreakerRegistry()
        
        breaker1 = registry.get_or_create("test")
        breaker2 = registry.get_or_create("test")
        
        assert breaker1 is breaker2
        
        breaker3 = registry.get_or_create("another")
        assert breaker3 is not breaker1

    def test_get_all(self):
        """Test getting all breakers."""
        registry = CircuitBreakerRegistry()
        
        registry.get_or_create("breaker1")
        registry.get_or_create("breaker2")
        
        all_breakers = registry.get_all()
        
        assert len(all_breakers) == 2
        assert "breaker1" in all_breakers
        assert "breaker2" in all_breakers
