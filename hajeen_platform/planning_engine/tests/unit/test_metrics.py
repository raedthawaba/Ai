"""Unit tests for Metrics Collector."""
import pytest
import time

from planning_engine.metrics.collector import (
    MetricsCollector,
    MetricType,
    Metric,
    MetricValue,
    BusinessMetrics,
    PerformanceMetrics,
    get_metrics_collector,
)


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def collector(self):
        """Create collector instance."""
        return MetricsCollector()

    def test_register_metric(self, collector):
        """Test registering a metric."""
        collector.register_metric(
            "test_counter",
            MetricType.COUNTER,
            description="Test counter",
            unit="requests",
        )
        
        assert "test_counter" in collector._metrics
        metric = collector._metrics["test_counter"]
        assert metric.metric_type == MetricType.COUNTER
        assert metric.description == "Test counter"

    def test_counter(self, collector):
        """Test counter increment."""
        collector.register_metric("my_counter", MetricType.COUNTER)
        
        collector.counter("my_counter", 1)
        collector.counter("my_counter", 5)
        
        assert collector.get("my_counter") == 6

    def test_gauge(self, collector):
        """Test gauge setting."""
        collector.register_metric("my_gauge", MetricType.GAUGE)
        
        collector.gauge("my_gauge", 100)
        collector.gauge("my_gauge", 150)
        
        assert collector.get("my_gauge") == 150

    def test_histogram(self, collector):
        """Test histogram recording."""
        collector.register_metric("my_histogram", MetricType.HISTOGRAM)
        
        collector.histogram("my_histogram", 0.5)
        collector.histogram("my_histogram", 1.5)
        collector.histogram("my_histogram", 2.5)
        
        metric = collector._metrics["my_histogram"]
        assert metric.count == 3
        assert metric.sum == 4.5

    def test_timer(self, collector):
        """Test timer."""
        collector.register_metric("operation_duration", MetricType.HISTOGRAM)
        
        stop_timer = collector.timer("operation_duration")
        time.sleep(0.01)
        stop_timer()
        
        metric = collector._metrics["operation_duration"]
        assert metric.count == 1
        assert metric.sum > 0

    def test_timed_context(self, collector):
        """Test timed context manager."""
        collector.register_metric("timed_operation", MetricType.HISTOGRAM)
        
        with collector.timed("timed_operation"):
            time.sleep(0.01)
        
        metric = collector._metrics["timed_operation"]
        assert metric.count == 1

    def test_get_all(self, collector):
        """Test getting all metrics."""
        collector.register_metric("counter1", MetricType.COUNTER)
        collector.register_metric("gauge1", MetricType.GAUGE)
        
        collector.counter("counter1", 10)
        collector.gauge("gauge1", 50)
        
        all_metrics = collector.get_all()
        
        assert "counter1" in all_metrics
        assert "gauge1" in all_metrics
        assert all_metrics["counter1"]["value"] == 10
        assert all_metrics["gauge1"]["value"] == 50

    def test_get_history(self, collector):
        """Test getting metric history."""
        collector.register_metric("tracked", MetricType.COUNTER)
        
        collector.counter("tracked", 1)
        collector.counter("tracked", 2)
        
        history = collector.get_history("tracked")
        
        assert len(history) == 2

    def test_reset(self, collector):
        """Test resetting metrics."""
        collector.register_metric("to_reset", MetricType.COUNTER)
        
        collector.counter("to_reset", 100)
        collector.reset("to_reset")
        
        metric = collector._metrics["to_reset"]
        assert metric.value == 0

    def test_reset_all(self, collector):
        """Test resetting all metrics."""
        collector.register_metric("metric1", MetricType.COUNTER)
        collector.register_metric("metric2", MetricType.GAUGE)
        
        collector.counter("metric1", 100)
        collector.gauge("metric2", 200)
        
        collector.reset()
        
        assert collector._metrics["metric1"].value == 0
        assert collector._metrics["metric2"].last_value == 0

    def test_export_prometheus(self, collector):
        """Test Prometheus export format."""
        collector.register_metric("prom_counter", MetricType.COUNTER)
        collector.register_metric("prom_gauge", MetricType.GAUGE)
        
        collector.counter("prom_counter", 10)
        collector.gauge("prom_gauge", 25)
        
        output = collector.export_prometheus()
        
        assert "prom_counter" in output
        assert "prom_gauge" in output
        assert "counter" in output
        assert "gauge" in output

    def test_callback(self, collector):
        """Test metric callbacks."""
        updates = []
        
        def callback(name, value, labels):
            updates.append((name, value))
        
        collector.add_callback(callback)
        collector.register_metric("callback_test", MetricType.COUNTER)
        collector.counter("callback_test", 5)
        
        assert len(updates) == 1
        assert updates[0] == ("callback_test", 5)

    def test_statistics(self, collector):
        """Test getting statistics."""
        stats = collector.get_statistics()
        
        assert "total_metrics" in stats
        assert "metrics_by_type" in stats


class TestBusinessMetrics:
    """Tests for BusinessMetrics class."""

    @pytest.fixture
    def business_metrics(self):
        """Create business metrics instance."""
        collector = MetricsCollector()
        return BusinessMetrics(collector)

    def test_plan_created(self, business_metrics):
        """Test plan created metric."""
        business_metrics.plan_created()
        business_metrics.plan_created()
        
        value = business_metrics._collector.get("plans_created_total")
        assert value == 2

    def test_plan_completed(self, business_metrics):
        """Test plan completed metric."""
        business_metrics.plan_completed(duration_ms=100.0)
        
        completed = business_metrics._collector.get("plans_completed_total")
        assert completed == 1

    def test_plan_failed(self, business_metrics):
        """Test plan failed metric."""
        business_metrics.plan_failed()
        
        failed = business_metrics._collector.get("plans_failed_total")
        assert failed == 1

    def test_step_executed(self, business_metrics):
        """Test step executed metric."""
        business_metrics.step_executed(duration_ms=50.0, success=True)
        
        executed = business_metrics._collector.get("steps_executed_total")
        assert executed == 1

    def test_set_active_plans(self, business_metrics):
        """Test active plans gauge."""
        business_metrics.set_active_plans(5)
        
        value = business_metrics._collector.get("active_plans")
        assert value == 5.0


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics class."""

    @pytest.fixture
    def perf_metrics(self):
        """Create performance metrics instance."""
        collector = MetricsCollector()
        return PerformanceMetrics(collector)

    def test_set_cpu_usage(self, perf_metrics):
        """Test CPU usage metric."""
        perf_metrics.set_cpu_usage(75.5)
        
        value = perf_metrics._collector.get("engine_cpu_usage_percent")
        assert value == 75.5

    def test_set_memory_usage(self, perf_metrics):
        """Test memory usage metric."""
        perf_metrics.set_memory_usage(1024000)
        
        value = perf_metrics._collector.get("engine_memory_usage_bytes")
        assert value == 1024000

    def test_set_concurrent_plans(self, perf_metrics):
        """Test concurrent plans metric."""
        perf_metrics.set_concurrent_plans(10)
        
        value = perf_metrics._collector.get("concurrent_plans")
        assert value == 10.0

    def test_set_queue_depth(self, perf_metrics):
        """Test queue depth metric."""
        perf_metrics.set_queue_depth(25)
        
        value = perf_metrics._collector.get("queue_depth")
        assert value == 25.0

    def test_set_cache_hit_ratio(self, perf_metrics):
        """Test cache hit ratio."""
        perf_metrics.set_cache_hit_ratio(0.85)
        
        value = perf_metrics._collector.get("cache_hit_ratio")
        assert value == 0.85

    def test_record_api_request(self, perf_metrics):
        """Test API request recording."""
        perf_metrics.record_api_request(duration_ms=150.0, status_code=200)
        
        metric = perf_metrics._collector._metrics.get("api_request_duration_ms")
        assert metric is not None
        assert metric.count >= 1
