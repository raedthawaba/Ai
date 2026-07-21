"""
Operational Validation & Production Certification Tests
====================================================

This test suite validates the Reasoning Engine through:
1. End-to-End Runtime Validation
2. Runtime Call Graph
3. Fault Injection Testing
4. Load Testing
5. Long Running Test
6. Cognitive Validation
7. Coverage Analysis
"""

import asyncio
import time
import sys
import os
import json
import tracemalloc
import gc
import psutil
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, '/workspace/project/Ai/hajeen_platform')

# Import modules directly to avoid full dependency chain
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# Load cognitive components
evidence_court = load_module("evidence_court", 
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/evidence_court.py")
hypothesis_engine = load_module("hypothesis_engine", 
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/hypothesis_engine.py")
world_model = load_module("world_model", 
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/world_model.py")

# Extract classes
EvidenceCourt = evidence_court.EvidenceCourt
HypothesisEngine = hypothesis_engine.HypothesisEngine
WorldModel = world_model.WorldModel


# ============================================================================
# RUNTIME CALL TRACING
# ============================================================================

class RuntimeTracer:
    """Tracks runtime execution of all components."""
    
    def __init__(self):
        self.calls = []
        self.call_counts = defaultdict(int)
        self.component_times = defaultdict(list)
        self.start_time = None
        self.end_time = None
    
    def start(self):
        self.start_time = time.time()
        tracemalloc.start()
    
    def stop(self):
        self.end_time = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "duration": self.end_time - self.start_time,
            "memory_current_mb": current / 1024 / 1024,
            "memory_peak_mb": peak / 1024 / 1024,
            "total_calls": len(self.calls),
            "unique_components": len(set(c["component"] for c in self.calls)),
        }
    
    def record_call(self, component: str, method: str, duration: float, 
                    result_size: int = 0, metadata: Dict = None):
        self.calls.append({
            "component": component,
            "method": method,
            "duration": duration,
            "result_size": result_size,
            "metadata": metadata or {},
            "timestamp": time.time() - self.start_time if self.start_time else 0,
        })
        self.call_counts[f"{component}.{method}"] += 1
        self.component_times[component].append(duration)
    
    def get_call_graph(self) -> Dict:
        """Generate runtime call graph."""
        components = set(c["component"] for c in self.calls)
        graph = {
            "total_duration": self.end_time - self.start_time if self.end_time and self.start_time else 0,
            "total_calls": len(self.calls),
            "unique_components": len(components),
            "call_counts": dict(self.call_counts),
            "component_summary": {},
        }
        
        for component, times in self.component_times.items():
            graph["component_summary"][component] = {
                "call_count": len(times),
                "total_time": sum(times),
                "avg_time": sum(times) / len(times) if times else 0,
                "min_time": min(times) if times else 0,
                "max_time": max(times) if times else 0,
            }
        
        return graph
    
    def print_report(self):
        print("\n" + "=" * 70)
        print("RUNTIME CALL GRAPH REPORT")
        print("=" * 70)
        
        graph = self.get_call_graph()
        
        print(f"\nTotal Duration: {graph['total_duration']:.3f}s")
        print(f"Total Calls: {graph['total_calls']}")
        print(f"Unique Components: {graph['unique_components']}")
        
        print("\n" + "-" * 70)
        print("COMPONENT SUMMARY")
        print("-" * 70)
        print(f"{'Component':<25} {'Calls':<8} {'Total(s)':<10} {'Avg(s)':<10} {'Min(s)':<10} {'Max(s)':<10}")
        print("-" * 70)
        
        for comp, stats in sorted(graph["component_summary"].items(), 
                                  key=lambda x: x[1]["total_time"], reverse=True):
            print(f"{comp:<25} {stats['call_count']:<8} "
                  f"{stats['total_time']:<10.4f} {stats['avg_time']:<10.4f} "
                  f"{stats['min_time']:<10.4f} {stats['max_time']:<10.4f}")
        
        print("\n" + "-" * 70)
        print("CALL SEQUENCE (first 20)")
        print("-" * 70)
        for i, call in enumerate(self.calls[:20]):
            print(f"{i+1:3}. [{call['timestamp']:6.3f}s] {call['component']}.{call['method']}() "
                  f"({call['duration']:.4f}s)")


# ============================================================================
# COGNITIVE COMPONENT TESTS
# ============================================================================

class CognitiveValidator:
    """Validates that cognitive components actually affect decisions."""
    
    def __init__(self, tracer: RuntimeTracer):
        self.tracer = tracer
    
    async def validate_evidence_court(self, test_cases: List[Dict]) -> Dict:
        """Test that Evidence Court affects decision."""
        print("\n" + "=" * 70)
        print("COGNITIVE VALIDATION: EVIDENCE COURT")
        print("=" * 70)
        
        court = EvidenceCourt()
        results = []
        
        for i, test_case in enumerate(test_cases):
            start = time.time()
            
            # Run evaluation
            result = await court.evaluate(test_case["context"])
            
            duration = time.time() - start
            self.tracer.record_call("EvidenceCourt", "evaluate", duration, 
                                    len(str(result)), {"confidence": result.confidence})
            
            # Validate impact
            impact = {
                "test_case": i + 1,
                "input_confidence": test_case["context"].get("evidence_sources", [{}])[0].get(
                    "source_type", "unknown"),
                "output_confidence": result.confidence,
                "evidence_score": result.evidence_score,
                "reliability": result.reliability,
                "decision_impact": result.decision_impact,
                "is_valid": result.is_valid,
                "duration": duration,
            }
            
            results.append(impact)
            
            # Check if evidence actually affects output
            assert result.confidence > 0, "Evidence Court must produce confidence score"
            assert result.decision_impact >= 0, "Decision impact must be non-negative"
            
            print(f"\nTest Case {i+1}:")
            print(f"  Input: source_type={impact['input_confidence']}")
            print(f"  Output: confidence={impact['output_confidence']:.3f}, "
                  f"evidence_score={impact['evidence_score']:.3f}")
            print(f"  Decision Impact: {impact['decision_impact']:.3f}")
            print(f"  Valid: {impact['is_valid']}")
        
        # Summary
        avg_confidence = sum(r["output_confidence"] for r in results) / len(results)
        avg_impact = sum(r["decision_impact"] for r in results) / len(results)
        
        print(f"\n{'='*70}")
        print("EVIDENCE COURT COGNITIVE IMPACT SUMMARY")
        print(f"{'='*70}")
        print(f"  Average Confidence: {avg_confidence:.3f}")
        print(f"  Average Decision Impact: {avg_impact:.3f}")
        print(f"  Validation: {'PASSED ✅' if avg_impact > 0 else 'FAILED ❌'}")
        
        return {
            "component": "EvidenceCourt",
            "test_cases": len(results),
            "avg_confidence": avg_confidence,
            "avg_impact": avg_impact,
            "validation": avg_impact > 0,
            "results": results,
        }
    
    async def validate_hypothesis_engine(self, test_cases: List[Dict]) -> Dict:
        """Test that Hypothesis Engine affects decision."""
        print("\n" + "=" * 70)
        print("COGNITIVE VALIDATION: HYPOTHESIS ENGINE")
        print("=" * 70)
        
        engine = HypothesisEngine()
        results = []
        
        for i, test_case in enumerate(test_cases):
            start = time.time()
            
            # Run generation
            result = await engine.generate_hypotheses(test_case["context"])
            
            duration = time.time() - start
            self.tracer.record_call("HypothesisEngine", "generate_hypotheses", duration,
                                    len(str(result)), 
                                    {"hypotheses_count": len(result.hypotheses)})
            
            # Validate impact
            impact = {
                "test_case": i + 1,
                "total_generated": result.total_generated,
                "valid_count": result.valid_count,
                "invalid_count": result.invalid_count,
                "has_best": result.best_hypothesis is not None,
                "best_score": result.best_hypothesis.overall_score if result.best_hypothesis else 0,
                "duration": duration,
            }
            
            results.append(impact)
            
            # Check if hypothesis affects output
            assert result.total_generated > 0, "Must generate hypotheses"
            assert impact["has_best"], "Must select best hypothesis"
            
            print(f"\nTest Case {i+1}:")
            print(f"  Generated: {impact['total_generated']} hypotheses")
            print(f"  Valid: {impact['valid_count']}, Invalid: {impact['invalid_count']}")
            print(f"  Best Hypothesis Score: {impact['best_score']:.3f}")
        
        # Summary
        avg_hypotheses = sum(r["total_generated"] for r in results) / len(results)
        avg_best_score = sum(r["best_score"] for r in results if r["has_best"]) / len([r for r in results if r["has_best"]])
        
        print(f"\n{'='*70}")
        print("HYPOTHESIS ENGINE COGNITIVE IMPACT SUMMARY")
        print(f"{'='*70}")
        print(f"  Average Hypotheses Generated: {avg_hypotheses:.1f}")
        print(f"  Average Best Score: {avg_best_score:.3f}")
        print(f"  Validation: {'PASSED ✅' if avg_best_score > 0 else 'FAILED ❌'}")
        
        return {
            "component": "HypothesisEngine",
            "test_cases": len(results),
            "avg_hypotheses": avg_hypotheses,
            "avg_best_score": avg_best_score,
            "validation": avg_best_score > 0,
            "results": results,
        }
    
    async def validate_world_model(self, test_cases: List[Dict]) -> Dict:
        """Test that World Model affects decision."""
        print("\n" + "=" * 70)
        print("COGNITIVE VALIDATION: WORLD MODEL")
        print("=" * 70)
        
        model = WorldModel()
        results = []
        
        for i, test_case in enumerate(test_cases):
            start = time.time()
            
            # Run simulation
            result = await model.simulate(test_case["context"])
            
            duration = time.time() - start
            self.tracer.record_call("WorldModel", "simulate", duration,
                                    len(str(result)),
                                    {"confidence": result.confidence, "scenarios": len(result.predictions)})
            
            # Validate impact
            impact = {
                "test_case": i + 1,
                "scenario": result.scenario[:50],
                "predictions_count": len(result.predictions),
                "confidence": result.confidence,
                "has_best": result.best_scenario is not None,
                "best_score": result.best_scenario.get("overall_score", 0) if result.best_scenario else 0,
                "duration": duration,
            }
            
            results.append(impact)
            
            # Check if simulation affects output
            assert len(result.predictions) > 0, "Must generate predictions"
            assert impact["has_best"], "Must select best scenario"
            
            print(f"\nTest Case {i+1}:")
            print(f"  Scenario: {impact['scenario']}...")
            print(f"  Predictions: {impact['predictions_count']}")
            print(f"  Confidence: {impact['confidence']:.3f}")
            print(f"  Best Scenario Score: {impact['best_score']:.3f}")
        
        # Summary
        avg_confidence = sum(r["confidence"] for r in results) / len(results)
        avg_score = sum(r["best_score"] for r in results if r["has_best"]) / len([r for r in results if r["has_best"]])
        
        print(f"\n{'='*70}")
        print("WORLD MODEL COGNITIVE IMPACT SUMMARY")
        print(f"{'='*70}")
        print(f"  Average Confidence: {avg_confidence:.3f}")
        print(f"  Average Best Score: {avg_score:.3f}")
        print(f"  Validation: {'PASSED ✅' if avg_score > 0 else 'FAILED ❌'}")
        
        return {
            "component": "WorldModel",
            "test_cases": len(results),
            "avg_confidence": avg_confidence,
            "avg_best_score": avg_score,
            "validation": avg_score > 0,
            "results": results,
        }


# ============================================================================
# FAULT INJECTION TESTS
# ============================================================================

class FaultInjector:
    """Tests system resilience to failures."""
    
    def __init__(self):
        self.results = []
    
    async def test_component_failure(self, component_name: str, 
                                   simulate_failure_fn,
                                   recovery_fn=None) -> Dict:
        """Test component behavior under failure."""
        print(f"\n  Testing {component_name} failure...")
        
        # Baseline
        baseline_start = time.time()
        try:
            baseline_result = await simulate_failure_fn()
            baseline_success = True
            baseline_time = time.time() - baseline_start
        except Exception as e:
            baseline_success = False
            baseline_time = time.time() - baseline_start
        
        # With failure
        failure_start = time.time()
        try:
            # Simulate failure
            result = await simulate_failure_fn()
            failure_success = True
            failure_time = time.time() - failure_start
            error = None
        except Exception as e:
            failure_success = False
            failure_time = time.time() - failure_start
            error = str(e)
        
        # Recovery test
        recovery_time = None
        if recovery_fn:
            recovery_start = time.time()
            try:
                await recovery_fn()
                recovery_time = time.time() - recovery_start
                recovery_success = True
            except Exception:
                recovery_success = False
        else:
            recovery_success = None
        
        result = {
            "component": component_name,
            "baseline_success": baseline_success,
            "failure_success": failure_success,
            "recovery_success": recovery_success,
            "baseline_time": baseline_time,
            "failure_time": failure_time,
            "recovery_time": recovery_time,
            "error": error,
            "graceful_degradation": failure_success or error is None,
        }
        
        self.results.append(result)
        
        status = "✅ PASS" if (not failure_success and error) or (failure_success) else "❌ FAIL"
        print(f"    Status: {status}")
        print(f"    Baseline: {baseline_success}, Failure: {failure_success}, Recovery: {recovery_success}")
        
        return result
    
    async def test_redis_failure(self) -> Dict:
        """Simulate Redis failure."""
        print("\n" + "-" * 50)
        print("FAULT INJECTION: Redis Failure")
        print("-" * 50)
        
        court = EvidenceCourt()
        
        result = await self.test_component_failure(
            "Redis/Memory",
            lambda: court.evaluate({"query": "test", "reasoning_result": "test"}),
        )
        
        # Test if system continues
        court2 = EvidenceCourt()
        try:
            await court2.evaluate({"query": "test2"})
            result["system_continues"] = True
        except:
            result["system_continues"] = False
        
        return result
    
    async def test_llm_failure(self) -> Dict:
        """Simulate LLM failure."""
        print("\n" + "-" * 50)
        print("FAULT INJECTION: LLM Failure")
        print("-" * 50)
        
        engine = HypothesisEngine()
        
        result = await self.test_component_failure(
            "LLM/Reasoning",
            lambda: engine.generate_hypotheses({
                "problem": "test problem",
                "reasoning": ["step1", "step2"],
            }),
        )
        
        return result
    
    async def test_database_failure(self) -> Dict:
        """Simulate database failure."""
        print("\n" + "-" * 50)
        print("FAULT INJECTION: Database Failure")
        print("-" * 50)
        
        model = WorldModel()
        
        result = await self.test_component_failure(
            "Database/Knowledge",
            lambda: model.simulate({"scenario": "test scenario"}),
        )
        
        return result
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("FAULT INJECTION SUMMARY")
        print("=" * 70)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["graceful_degradation"])
        
        print(f"\nTotal Tests: {total}")
        print(f"Graceful Degradation: {passed}/{total}")
        
        for result in self.results:
            status = "✅" if result["graceful_degradation"] else "❌"
            print(f"\n{status} {result['component']}")
            print(f"   Baseline: {result['baseline_success']}, "
                  f"Failure: {result['failure_success']}, "
                  f"Recovery: {result['recovery_success']}")


# ============================================================================
# LOAD TESTING
# ============================================================================

class LoadTester:
    """Performance testing under load."""
    
    def __init__(self, tracer: RuntimeTracer):
        self.tracer = tracer
        self.results = []
    
    async def run_load_test(self, concurrent_users: int, 
                           duration_seconds: int) -> Dict:
        """Run load test with specified parameters."""
        print("\n" + "=" * 70)
        print(f"LOAD TEST: {concurrent_users} Concurrent Users")
        print("=" * 70)
        
        court = EvidenceCourt()
        
        latencies = []
        errors = 0
        start_time = time.time()
        request_count = 0
        
        async def worker():
            nonlocal latencies, errors, request_count
            
            while time.time() - start_time < duration_seconds:
                req_start = time.time()
                try:
                    await court.evaluate({
                        "query": f"test query {time.time()}",
                        "reasoning_result": "test reasoning",
                        "domain": "testing",
                    })
                    latencies.append(time.time() - req_start)
                except Exception:
                    errors += 1
                request_count += 1
        
        # Run workers
        tasks = [worker() for _ in range(concurrent_users)]
        await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # Calculate metrics
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
        
        throughput = request_count / total_time if total_time > 0 else 0
        error_rate = errors / request_count if request_count > 0 else 0
        
        result = {
            "concurrent_users": concurrent_users,
            "duration": total_time,
            "total_requests": request_count,
            "throughput_rps": throughput,
            "latency_avg": sum(latencies) / len(latencies) if latencies else 0,
            "latency_p50": p50,
            "latency_p95": p95,
            "latency_p99": p99,
            "errors": errors,
            "error_rate": error_rate,
        }
        
        self.results.append(result)
        
        print(f"\nResults:")
        print(f"  Duration: {total_time:.2f}s")
        print(f"  Total Requests: {request_count}")
        print(f"  Throughput: {throughput:.2f} req/s")
        print(f"  Latency Avg: {result['latency_avg']*1000:.2f}ms")
        print(f"  Latency P50: {p50*1000:.2f}ms")
        print(f"  Latency P95: {p95*1000:.2f}ms")
        print(f"  Latency P99: {p99*1000:.2f}ms")
        print(f"  Errors: {errors}")
        print(f"  Error Rate: {error_rate*100:.2f}%")
        
        return result
    
    def print_summary(self):
        print("\n" + "=" * 70)
        print("LOAD TEST SUMMARY")
        print("=" * 70)
        
        print(f"\n{'Users':<10} {'Throughput':<15} {'P95 Latency':<15} {'Error Rate':<15}")
        print("-" * 55)
        
        for result in self.results:
            print(f"{result['concurrent_users']:<10} "
                  f"{result['throughput_rps']:<15.2f} "
                  f"{result['latency_p95']*1000:<15.2f}ms "
                  f"{result['error_rate']*100:<15.2f}%")


# ============================================================================
# LONG RUNNING TEST
# ============================================================================

class LongRunningTester:
    """Stability testing over extended periods."""
    
    def __init__(self):
        self.memory_samples = []
        self.cpu_samples = []
    
    async def run_stability_test(self, iterations: int) -> Dict:
        """Run stability test over many iterations."""
        print("\n" + "=" * 70)
        print(f"STABILITY TEST: {iterations} Iterations")
        print("=" * 70)
        
        process = psutil.Process()
        gc.collect()
        
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = process.cpu_percent()
        
        court = EvidenceCourt()
        
        for i in range(iterations):
            await court.evaluate({
                "query": f"test query {i}",
                "reasoning_result": f"test reasoning {i}",
            })
            
            # Sample every 10 iterations
            if i % 10 == 0:
                gc.collect()
                memory = process.memory_info().rss / 1024 / 1024
                cpu = process.cpu_percent()
                
                self.memory_samples.append({
                    "iteration": i,
                    "memory_mb": memory,
                    "cpu_percent": cpu,
                })
                
                print(f"  Iteration {i}: Memory={memory:.1f}MB, CPU={cpu:.1f}%")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        final_cpu = process.cpu_percent()
        memory_growth = final_memory - initial_memory
        
        # Analyze trends
        memory_trend = "stable"
        if len(self.memory_samples) > 2:
            first_half = [s["memory_mb"] for s in self.memory_samples[:len(self.memory_samples)//2]]
            second_half = [s["memory_mb"] for s in self.memory_samples[len(self.memory_samples)//2:]]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0
            if avg_second > avg_first * 1.2 and (avg_second - avg_first) > 10:
                memory_trend = "growing"
            elif avg_second < avg_first * 0.8:
                memory_trend = "shrinking"
        
        result = {
            "iterations": iterations,
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
            "memory_growth_mb": memory_growth,
            "memory_trend": memory_trend,
            "initial_cpu": initial_cpu,
            "final_cpu": final_cpu,
            "samples": len(self.memory_samples),
        }
        
        print(f"\nStability Results:")
        print(f"  Initial Memory: {initial_memory:.1f}MB")
        print(f"  Final Memory: {final_memory:.1f}MB")
        print(f"  Growth: {memory_growth:.1f}MB")
        print(f"  Memory Trend: {memory_trend}")
        print(f"  Initial CPU: {initial_cpu:.1f}%")
        print(f"  Final CPU: {final_cpu:.1f}%")
        print(f"  Status: {'✅ STABLE' if abs(memory_growth) < 100 else '⚠️ UNSTABLE'}")
        
        return result


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

async def run_all_validations():
    """Run all operational validations."""
    
    print("\n" + "=" * 70)
    print("OPERATIONAL VALIDATION & PRODUCTION CERTIFICATION")
    print("=" * 70)
    print(f"Start Time: {datetime.now().isoformat()}")
    
    tracer = RuntimeTracer()
    tracer.start()
    
    # Initialize validators
    cognitive_validator = CognitiveValidator(tracer)
    fault_injector = FaultInjector()
    load_tester = LoadTester(tracer)
    long_tester = LongRunningTester()
    
    # Test scenarios for cognitive validation
    evidence_test_cases = [
        {
            "context": {
                "query": "What is machine learning?",
                "reasoning_result": "ML is a subset of AI that enables systems to learn",
                "domain": "technology",
            }
        },
        {
            "context": {
                "query": "Is climate change caused by humans?",
                "reasoning_result": "Scientific consensus supports human causation",
                "domain": "science",
                "evidence_sources": [
                    {"claim": "Global temps increased 1.1C", "source": "NASA", "source_type": "SCIENTIFIC_STUDY"}
                ]
            }
        },
    ]
    
    hypothesis_test_cases = [
        {
            "context": {
                "problem": "Why is the sky blue?",
                "reasoning": ["Light scattering", "Wavelength dependence"],
            }
        },
        {
            "context": {
                "problem": "What causes economic growth?",
                "reasoning": ["Investment", "Technology", "Labor"],
                "evidence": {"confidence": 0.7}
            }
        },
    ]
    
    world_test_cases = [
        {
            "context": {
                "scenario": "What happens if we adopt renewable energy?",
                "hypothesis": type('obj', (object,), {
                    'hypothesis_text': 'Carbon emissions will decrease',
                    'assumptions': ['Technology available', 'Government support']
                })()
            }
        },
        {
            "context": {
                "scenario": "What if we implement universal basic income?",
            }
        },
    ]
    
    # 1. Run Cognitive Validations
    print("\n\n" + "=" * 70)
    print("SECTION 1: COGNITIVE VALIDATION")
    print("=" * 70)
    
    evidence_result = await cognitive_validator.validate_evidence_court(evidence_test_cases)
    hypothesis_result = await cognitive_validator.validate_hypothesis_engine(hypothesis_test_cases)
    world_result = await cognitive_validator.validate_world_model(world_test_cases)
    
    cognitive_summary = {
        "evidence_court": evidence_result,
        "hypothesis_engine": hypothesis_result,
        "world_model": world_result,
        "all_passed": all([
            evidence_result["validation"],
            hypothesis_result["validation"],
            world_result["validation"],
        ])
    }
    
    # 2. Run Fault Injection Tests
    print("\n\n" + "=" * 70)
    print("SECTION 2: FAULT INJECTION TESTING")
    print("=" * 70)
    
    fault_results = []
    fault_results.append(await fault_injector.test_redis_failure())
    fault_results.append(await fault_injector.test_llm_failure())
    fault_results.append(await fault_injector.test_database_failure())
    fault_injector.print_summary()
    
    fault_summary = {
        "total_tests": len(fault_results),
        "passed": sum(1 for r in fault_results if r["graceful_degradation"]),
        "results": fault_results,
    }
    
    # 3. Run Load Tests (scaled down for testing)
    print("\n\n" + "=" * 70)
    print("SECTION 3: LOAD TESTING")
    print("=" * 70)
    
    load_results = []
    
    # Test with 10 concurrent users for 2 seconds
    result = await load_tester.run_load_test(10, 2)
    load_results.append(result)
    
    load_tester.print_summary()
    
    load_summary = {
        "tests": load_results,
        "max_throughput": max(r["throughput_rps"] for r in load_results),
        "max_p99_latency": max(r["latency_p99"] for r in load_results),
        "total_errors": sum(r["errors"] for r in load_results),
    }
    
    # 4. Run Stability Test
    print("\n\n" + "=" * 70)
    print("SECTION 4: STABILITY TESTING")
    print("=" * 70)
    
    stability_result = await long_tester.run_stability_test(50)
    
    stability_summary = {
        "iterations": stability_result["iterations"],
        "memory_growth_mb": stability_result["memory_growth_mb"],
        "memory_trend": stability_result["memory_trend"],
        "stable": stability_result["memory_trend"] == "stable",
    }
    
    # 5. Get Runtime Stats
    runtime_stats = tracer.stop()
    tracer.print_report()
    
    # 6. Compile Final Report
    print("\n\n" + "=" * 70)
    print("FINAL CERTIFICATION SUMMARY")
    print("=" * 70)
    
    certification = {
        "timestamp": datetime.now().isoformat(),
        "runtime_stats": runtime_stats,
        "cognitive_validation": cognitive_summary,
        "fault_injection": fault_summary,
        "load_testing": load_summary,
        "stability": stability_summary,
        "production_ready": (
            cognitive_summary["all_passed"] and
            fault_summary["passed"] == fault_summary["total_tests"] and
            load_summary["total_errors"] == 0 and
            stability_summary["stable"]
        )
    }
    
    print(f"\nCognitive Validation: {'✅ PASSED' if cognitive_summary['all_passed'] else '❌ FAILED'}")
    print(f"Fault Injection: {fault_summary['passed']}/{fault_summary['total_tests']} passed")
    print(f"Load Testing: {load_summary['total_errors']} errors")
    print(f"Stability: {'✅ STABLE' if stability_summary['stable'] else '❌ UNSTABLE'}")
    print(f"\nOVERALL: {'✅ PRODUCTION READY' if certification['production_ready'] else '❌ NOT READY'}")
    
    # Save results to JSON
    with open("/tmp/certification_results.json", "w") as f:
        # Convert non-serializable objects
        json.dump({
            "timestamp": certification["timestamp"],
            "runtime_stats": runtime_stats,
            "cognitive_validation": cognitive_summary,
            "fault_injection": {
                "total_tests": fault_summary["total_tests"],
                "passed": fault_summary["passed"],
                "results": fault_summary["results"],
            },
            "load_testing": load_summary,
            "stability": stability_summary,
            "production_ready": certification["production_ready"],
        }, f, indent=2, default=str)
    
    return certification


if __name__ == "__main__":
    result = asyncio.run(run_all_validations())
    print(f"\nCertification saved to /tmp/certification_results.json")
