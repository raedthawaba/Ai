"""
Production Validation Script for Phase 1 - Hajeen Brain v2
Tests the ReasoningEngine integration with Hajeen Brain V3
"""

import asyncio
import time
import sys
import os
import json
import psutil
import threading
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass, field
from collections import defaultdict

sys.path.insert(0, 'hajeen_platform')

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    name: str
    status: str
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

@dataclass
class StressTestResult:
    concurrent_requests: int
    total_requests: int
    successful: int
    failed: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_rps: float
    memory_mb: float
    cpu_percent: float
    error_rate: float

class ProductionValidator:
    def __init__(self):
        self.results: List[ValidationResult] = []
        
    def log_result(self, result: ValidationResult):
        self.results.append(result)
        status_icon = "✅" if result.status == "PASS" else "❌" if result.status == "FAIL" else "⏭️"
        print(f"{status_icon} {result.name}: {result.status} ({result.duration_ms:.2f}ms)")
        if result.error:
            print(f"   Error: {result.error}")
        if result.details:
            for k, v in result.details.items():
                print(f"   {k}: {v}")
    
    async def test_e2e_flow(self) -> ValidationResult:
        """End-to-End test"""
        start = time.time()
        try:
            from brain import get_brain
            from brain.brain import BrainRequest
            from unittest.mock import MagicMock
            
            print("\n" + "="*60)
            print("END-TO-END VALIDATION")
            print("="*60)
            
            # Get brain instance
            brain = get_brain()
            
            request = BrainRequest(
                request_id="e2e-test-001",
                user_message="ما هي عاصمة فرنسا؟",
                session_id="test-session-001",
                conversation_history=[],
                user_context={}
            )
            
            print("\n📋 Test Request:")
            print(f"   Request ID: {request.request_id}")
            print(f"   Message: {request.user_message}")
            
            response = await brain.process_request(request)
            
            print("\n📤 Response:")
            print(f"   Content: {response.content[:100]}...")
            print(f"   Model: {response.model}")
            print(f"   Latency: {response.latency_ms}ms")
            
            return ValidationResult(
                name="E2E Flow - Full Request Pipeline",
                status="PASS",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "request_id": response.request_id,
                    "model_used": response.model,
                    "latency_ms": response.latency_ms
                }
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return ValidationResult(
                name="E2E Flow - Full Request Pipeline",
                status="FAIL",
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            )
    
    async def test_all_reasoning_strategies(self) -> List[ValidationResult]:
        """Test all reasoning strategies"""
        print("\n" + "="*60)
        print("TESTING ALL REASONING STRATEGIES")
        print("="*60)
        
        results = []
        from brain.config import ReasoningEngineConfig, ReasoningStrategyConfig, ReasoningStrategyType
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        from unittest.mock import MagicMock
        
        strategies_to_test = [
            ("chain_of_thought", ReasoningStrategyType.CHAIN_OF_THOUGHT),
            ("first_principles", ReasoningStrategyType.FIRST_PRINCIPLES),
            ("multi_perspective", ReasoningStrategyType.MULTI_PERSPECTIVE),
            ("analogy", ReasoningStrategyType.ANALOGY),
            ("tree_of_thought", ReasoningStrategyType.TREE_OF_THOUGHT),
            ("decomposition", ReasoningStrategyType.DECOMPOSITION),
        ]
        
        mock_llm = MagicMock()
        
        async def mock_generate(*args, **kwargs):
            return MagicMock(
                content="Test response",
                model="test",
                tokens_used=10,
                latency_ms=10
            )
        mock_llm.generate = mock_generate
        
        test_problem = "اشرح كيف يعمل الإنترنت بطريقة بسيطة."
        
        for strategy_name, strategy_type in strategies_to_test:
            start = time.time()
            try:
                config = ReasoningEngineConfig(
                    reasoning_strategy=ReasoningStrategyConfig(
                        default_strategy=strategy_type
                    )
                )
                engine = ReasoningEngine(llm_manager=mock_llm, config=config)
                
                result = await engine.reason(test_problem, context={"test": True})
                
                status = "PASS" if result else "FAIL"
                details = {
                    "strategy": strategy_name,
                    "steps_count": len(result.reasoning_steps) if result else 0,
                    "confidence": result.overall_confidence if result else 0
                }
                
                print(f"\n📌 Strategy: {strategy_name} - {status}")
                
                results.append(ValidationResult(
                    name=f"Strategy: {strategy_name}",
                    status=status,
                    duration_ms=(time.time() - start) * 1000,
                    details=details
                ))
                
            except Exception as e:
                print(f"\n📌 Strategy: {strategy_name} - FAIL: {str(e)}")
                results.append(ValidationResult(
                    name=f"Strategy: {strategy_name}",
                    status="FAIL",
                    duration_ms=(time.time() - start) * 1000,
                    error=str(e)
                ))
        
        return results
    
    async def stress_test(self, concurrent: int, total: int) -> StressTestResult:
        """Stress test"""
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        from unittest.mock import MagicMock
        
        print(f"\n🔴 Stress Test: {concurrent} concurrent, {total} total")
        
        mock_llm = MagicMock()
        
        async def mock_generate(*args, **kwargs):
            return MagicMock(
                content="Test response",
                model="test",
                tokens_used=10,
                latency_ms=5
            )
        mock_llm.generate = mock_generate
        
        engine = ReasoningEngine(llm_manager=mock_llm)
        
        latencies = []
        errors = 0
        lock = threading.Lock()
        
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024
        
        async def single_request(req_id: int):
            nonlocal errors
            req_start = time.time()
            try:
                await engine.reason(f"Test request {req_id}")
                latency = (time.time() - req_start) * 1000
                with lock:
                    latencies.append(latency)
            except Exception as e:
                with lock:
                    errors += 1
        
        start_time = time.time()
        tasks = []
        for i in range(total):
            task = asyncio.create_task(single_request(i))
            tasks.append(task)
            if len(tasks) >= concurrent:
                await asyncio.gather(*tasks)
                tasks = []
        
        if tasks:
            await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        end_memory = process.memory_info().rss / 1024 / 1024
        
        latencies.sort()
        p50 = latencies[len(latencies)//2] if latencies else 0
        p95 = latencies[int(len(latencies)*0.95)] if latencies else 0
        p99 = latencies[int(len(latencies)*0.99)] if latencies else 0
        
        result = StressTestResult(
            concurrent_requests=concurrent,
            total_requests=total,
            successful=total - errors,
            failed=errors,
            avg_latency_ms=sum(latencies)/len(latencies) if latencies else 0,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            throughput_rps=total/total_time if total_time > 0 else 0,
            memory_mb=end_memory - start_memory,
            cpu_percent=0,
            error_rate=errors/total if total > 0 else 0
        )
        
        print(f"   ✅ Successful: {result.successful}")
        print(f"   ⏱️  Avg Latency: {result.avg_latency_ms:.2f}ms")
        print(f"   📊 P50: {result.p50_latency_ms:.2f}ms")
        print(f"   📊 P95: {result.p95_latency_ms:.2f}ms")
        print(f"   📊 P99: {result.p99_latency_ms:.2f}ms")
        print(f"   🚀 Throughput: {result.throughput_rps:.2f} req/s")
        print(f"   💾 Memory Δ: {result.memory_mb:.2f}MB")
        print(f"   ⚠️  Error Rate: {result.error_rate*100:.2f}%")
        
        return result
    
    async def test_error_recovery(self) -> List[ValidationResult]:
        """Error recovery tests"""
        print("\n" + "="*60)
        print("ERROR RECOVERY TESTING")
        print("="*60)
        
        results = []
        from brain.cognitive_layer.reasoning_engine import ReasoningEngine
        from brain.config import ReasoningEngineConfig
        from unittest.mock import MagicMock
        
        # Test 1: LLM Failure with Fallback
        start = time.time()
        try:
            mock_llm = MagicMock()
            
            async def failing_call(*args, **kwargs):
                raise Exception("LLM API Error")
            
            mock_llm.generate = failing_call
            
            config = ReasoningEngineConfig()
            engine = ReasoningEngine(llm_manager=mock_llm, config=config)
            
            try:
                result = await engine.reason("Test")
                # If fallback works, we should get a result
                has_fallback = result is not None
            except:
                has_fallback = False
            
            results.append(ValidationResult(
                name="Error Recovery - LLM Failure",
                status="PASS" if has_fallback else "FAIL",
                duration_ms=(time.time() - start) * 1000,
                details={"fallback_used": has_fallback}
            ))
            print(f"\n🔴 LLM Failure Test: {'PASS (Fallback worked)' if has_fallback else 'FAIL'}")
            
        except Exception as e:
            results.append(ValidationResult(
                name="Error Recovery - LLM Failure",
                status="FAIL",
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            ))
        
        # Test 2: Cache Working
        start = time.time()
        try:
            mock_llm = MagicMock()
            call_count = 0
            
            async def counting_call(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                return MagicMock(content=f"response {call_count}", model="test", tokens_used=1, latency_ms=10)
            
            mock_llm.generate = counting_call
            
            engine = ReasoningEngine(llm_manager=mock_llm)
            
            await engine.reason("cache test")
            await engine.reason("cache test")
            
            cache_working = call_count == 1
            
            results.append(ValidationResult(
                name="Error Recovery - Cache",
                status="PASS" if cache_working else "FAIL",
                duration_ms=(time.time() - start) * 1000,
                details={"cache_working": cache_working, "llm_calls": call_count}
            ))
            print(f"💾 Cache Test: {'PASS (Cache working)' if cache_working else 'FAIL'}")
            
        except Exception as e:
            results.append(ValidationResult(
                name="Error Recovery - Cache",
                status="FAIL",
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            ))
        
        return results
    
    async def architecture_review(self) -> List[ValidationResult]:
        """Architecture review"""
        print("\n" + "="*60)
        print("ARCHITECTURE REVIEW")
        print("="*60)
        
        results = []
        
        # Test 1: Memory Leak Check
        start = time.time()
        try:
            import gc
            from brain.cognitive_layer.reasoning_engine import ReasoningEngine
            from unittest.mock import MagicMock
            
            gc.collect()
            initial_objects = len(gc.get_objects())
            
            mock_llm = MagicMock()
            
            async def mock_gen(*args, **kwargs):
                return MagicMock(content="test", model="test", tokens_used=1, latency_ms=1)
            
            mock_llm.generate = mock_gen
            
            engine = ReasoningEngine(llm_manager=mock_llm)
            
            for i in range(100):
                await engine.reason(f"test {i}")
            
            gc.collect()
            final_objects = len(gc.get_objects())
            object_growth = final_objects - initial_objects
            
            memory_leak = object_growth > 1000
            
            results.append(ValidationResult(
                name="Architecture - Memory Leak",
                status="PASS" if not memory_leak else "FAIL",
                duration_ms=(time.time() - start) * 1000,
                details={
                    "initial_objects": initial_objects,
                    "final_objects": final_objects,
                    "growth": object_growth
                }
            ))
            print(f"\n🧠 Memory Leak: {'PASS' if not memory_leak else 'FAIL'}")
            print(f"   Object Growth: {object_growth}")
            
        except Exception as e:
            results.append(ValidationResult(
                name="Architecture - Memory Leak",
                status="FAIL",
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            ))
        
        # Test 2: Circular Dependency
        start = time.time()
        try:
            import brain
            import brain.cognitive_layer
            import brain.config
            import brain.execution_trace
            import brain.metrics_engine
            
            results.append(ValidationResult(
                name="Architecture - Circular Dependency",
                status="PASS",
                duration_ms=(time.time() - start) * 1000,
                details={"modules_loaded": 5}
            ))
            print(f"🔄 Circular Dependency: PASS")
            
        except ImportError as e:
            results.append(ValidationResult(
                name="Architecture - Circular Dependency",
                status="FAIL",
                duration_ms=(time.time() - start) * 1000,
                error=str(e)
            ))
        
        return results
    
    async def run_all_validations(self):
        """Run all validations"""
        print("\n" + "="*80)
        print("🚀 PRODUCTION VALIDATION - HAJEEN BRAIN V2 - PHASE 1")
        print("="*80)
        print(f"Started at: {datetime.now().isoformat()}")
        
        all_results = []
        stress_results = []
        
        # 1. E2E Test
        print("\n\n" + "🔷"*30)
        e2e_result = await self.test_e2e_flow()
        self.log_result(e2e_result)
        all_results.append(e2e_result)
        
        # 2. Strategies Test
        print("\n\n" + "🔷"*30)
        strategy_results = await self.test_all_reasoning_strategies()
        for r in strategy_results:
            self.log_result(r)
        all_results.extend(strategy_results)
        
        # 3. Stress Tests
        print("\n\n" + "🔷"*30)
        print("STRESS TESTS")
        print("-"*40)
        
        for concurrent in [100, 500, 1000]:
            result = await self.stress_test(concurrent, concurrent)
            stress_results.append(result)
        
        # 4. Error Recovery
        print("\n\n" + "🔷"*30)
        error_results = await self.test_error_recovery()
        for r in error_results:
            self.log_result(r)
        all_results.extend(error_results)
        
        # 5. Architecture
        print("\n\n" + "🔷"*30)
        arch_results = await self.architecture_review()
        for r in arch_results:
            self.log_result(r)
        all_results.extend(arch_results)
        
        # Summary
        print("\n\n" + "="*80)
        print("📊 VALIDATION SUMMARY")
        print("="*80)
        
        passed = sum(1 for r in all_results if r.status == "PASS")
        failed = sum(1 for r in all_results if r.status == "FAIL")
        total = len(all_results)
        
        print(f"\nTotal Tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%")
        
        print("\n" + "-"*40)
        print("STRESS TEST RESULTS")
        print("-"*40)
        for r in stress_results:
            print(f"\n📊 {r.concurrent_requests} Concurrent:")
            print(f"   Throughput: {r.throughput_rps:.2f} req/s")
            print(f"   Avg Latency: {r.avg_latency_ms:.2f}ms")
            print(f"   P95: {r.p95_latency_ms:.2f}ms")
            print(f"   P99: {r.p99_latency_ms:.2f}ms")
            print(f"   Error Rate: {r.error_rate*100:.2f}%")
        
        # Save report
        validation_report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "success_rate": passed/total*100
            },
            "test_results": [
                {
                    "name": r.name,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                    "error": r.error
                } for r in all_results
            ],
            "stress_test_results": [
                {
                    "concurrent": r.concurrent_requests,
                    "total": r.total_requests,
                    "successful": r.successful,
                    "failed": r.failed,
                    "avg_latency_ms": r.avg_latency_ms,
                    "p50": r.p50_latency_ms,
                    "p95": r.p95_latency_ms,
                    "p99": r.p99_latency_ms,
                    "throughput_rps": r.throughput_rps,
                    "memory_mb": r.memory_mb,
                    "error_rate": r.error_rate
                } for r in stress_results
            ]
        }
        
        with open('production_validation_report.json', 'w', encoding='utf-8') as f:
            json.dump(validation_report, f, indent=2, ensure_ascii=False)
        
        print(f"\n📄 Report saved to: production_validation_report.json")
        
        return all_results, stress_results

async def main():
    validator = ProductionValidator()
    results, stress_results = await validator.run_all_validations()
    failed = sum(1 for r in results if r.status == "FAIL")
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
