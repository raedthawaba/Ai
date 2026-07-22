"""
End-to-End Pipeline Test - Phase 2
===================================

This test validates the complete pipeline execution and extracts the Runtime Call Graph.
"""

import asyncio
import sys
import os
import time
import traceback
from typing import List, Dict, Any

# Add hajeen_platform to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from hajeen_platform.brain.contracts import BrainRequest, BrainResponse, ResponseStatus
from hajeen_platform.brain.hajeen_brain import HajeenBrain


class PipelineTracer:
    """Captures execution flow for Call Graph generation."""
    
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []
        self.current_depth = 0
    
    def record(self, stage: str, engine: str, duration_ms: float, metadata: Dict = None):
        self.calls.append({
            "stage": stage,
            "engine": engine,
            "duration_ms": duration_ms,
            "depth": self.current_depth,
            "metadata": metadata or {}
        })


async def run_e2e_test():
    """Run end-to-end pipeline test with tracing."""
    
    tracer = PipelineTracer()
    
    print("=" * 100)
    print("END-TO-END PIPELINE TEST - PHASE 2")
    print("=" * 100)
    
    # Initialize brain
    brain = HajeenBrain()
    
    # Create test request
    request = BrainRequest(
        user_message="ما هو الذكاء الاصطناعي؟",
        session_id="test-session-001",
        request_type="chat",
    )
    
    print(f"\n📋 Request: {request.user_message}")
    print(f"📋 Session: {request.session_id}")
    
    # Execute pipeline
    t_start = time.perf_counter()
    errors = []
    
    try:
        # Initialize brain
        await brain.initialize()
        tracer.record("init", "HajeenBrain", 0, {"status": "initialized"})
        
        # Process request
        response = await brain.process(request)
        
        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000
        
        print(f"\n✅ Pipeline completed in {total_ms:.2f}ms")
        print(f"📊 Response: {response.content[:100]}...")
        print(f"📊 Status: {response.status}")
        
        # Extract timing data
        if response.execution_metadata:
            print("\n📊 ENGINE LATENCIES:")
            print("-" * 60)
            latencies = response.execution_metadata.engine_latencies
            for stage, ms in sorted(latencies.items(), key=lambda x: x[1], reverse=True):
                bar = "█" * min(int(ms / 5), 20)
                print(f"  {stage:20} {ms:8.2f}ms {bar}")
            
            # Record all stages
            for stage, ms in latencies.items():
                tracer.record(stage, "pipeline", ms)
        
        # Record learning signals
        if response.extra_data and "learning_signals" in response.extra_data:
            print("\n📊 LEARNING SIGNALS:")
            for signal in response.extra_data["learning_signals"]:
                stage = signal.get("stage", "unknown")
                print(f"  ✅ {stage}: {list(signal.keys())}")
        
        # Success
        tracer.record("complete", "HajeenBrain", total_ms, {
            "status": "success",
            "content_length": len(response.content)
        })
        
        return True, tracer
        
    except Exception as e:
        t_end = time.perf_counter()
        errors.append(str(e))
        print(f"\n❌ Pipeline failed: {e}")
        traceback.print_exc()
        
        tracer.record("error", "HajeenBrain", (t_end - t_start) * 1000, {
            "error": str(e)
        })
        
        return False, tracer


async def run_multi_request_test():
    """Simulate multiple concurrent requests."""
    
    print("\n" + "=" * 100)
    print("MULTI-REQUEST SIMULATION")
    print("=" * 100)
    
    brain = HajeenBrain()
    await brain.initialize()
    
    requests = [
        BrainRequest(user_message="مرحبا", session_id="session-1"),
        BrainRequest(user_message="كيف حالك؟", session_id="session-2"),
        BrainRequest(user_message="ما هو الذكاء الاصطناعي؟", session_id="session-3"),
    ]
    
    print(f"\n📋 Running {len(requests)} concurrent requests...")
    
    t_start = time.perf_counter()
    
    # Run concurrently
    responses = await asyncio.gather(*[
        brain.process(req) for req in requests
    ], return_exceptions=True)
    
    t_end = time.perf_counter()
    total_ms = (t_end - t_start) * 1000
    
    # Analyze results
    successful = sum(1 for r in responses if isinstance(r, BrainResponse) and r.status == ResponseStatus.SUCCESS)
    failed = len(responses) - successful
    
    print(f"\n✅ Results: {successful} successful, {failed} failed")
    print(f"⏱️ Total time: {total_ms:.2f}ms")
    print(f"⏱️ Average per request: {total_ms / len(requests):.2f}ms")
    
    return successful, failed


async def run_failure_injection_test():
    """Test failure handling."""
    
    print("\n" + "=" * 100)
    print("FAILURE INJECTION TEST")
    print("=" * 100)
    
    brain = HajeenBrain()
    await brain.initialize()
    
    # Test with invalid session
    request = BrainRequest(
        user_message="test",
        session_id="",  # Empty session should be handled
    )
    
    try:
        response = await brain.process(request)
        print(f"\n✅ Empty session handled: {response.status}")
    except Exception as e:
        print(f"\n❌ Empty session error: {e}")


def extract_call_graph(tracer: PipelineTracer) -> str:
    """Extract and format the Call Graph."""
    
    print("\n" + "=" * 100)
    print("RUNTIME CALL GRAPH (Phase 2 - Corrected Order)")
    print("=" * 100)
    
    # Expected order
    expected_order = [
        ("policy", "Policy Check"),
        ("intent", "Intent Analysis"),
        ("context", "Context Analysis"),
        ("memory_retrieval", "Memory Retrieval (EARLY)"),
        ("knowledge_retrieval", "Knowledge Retrieval (EARLY)"),
        ("reasoning", "Reasoning (with Memory + Knowledge)"),
        ("planning", "Planning (Task Decomposition + Graph)"),
        ("decision", "Decision"),
        ("execution", "Model Router + Execution"),
        ("reflection", "Self Reflection"),
        ("learning", "Final Learning"),
    ]
    
    # Print corrected order
    print("\n📊 CORRECTED PIPELINE ORDER:")
    print("-" * 60)
    print("""
    ╔════════════════════════════════════════════════════════════════════════╗
    ║  PHASE 1: ANALYSIS                                                  ║
    ║  Policy → Intent → Context                                          ║
    ╠════════════════════════════════════════════════════════════════════════╣
    ║  PHASE 2: RETRIEVAL (BEFORE Reasoning)                              ║
    ║  Memory → Knowledge                                                 ║
    ╠════════════════════════════════════════════════════════════════════════╣
    ║  PHASE 3: COGNITIVE                                                 ║
    ║  Reasoning → Planning → Decision                                    ║
    ╠════════════════════════════════════════════════════════════════════════╣
    ║  PHASE 4: EXECUTION                                                 ║
    ║  Model Router → Execution                                           ║
    ╠════════════════════════════════════════════════════════════════════════╣
    ║  PHASE 5: POST-EXECUTION                                            ║
    ║  Reflection → Learning (Incremental)                                ║
    ╚════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Print execution table
    print("\n📊 EXECUTION FLOW:")
    print("-" * 80)
    print(f"{'#':3} {'STAGE':25} {'ENGINE':20} {'TIME (ms)':12}")
    print("-" * 80)
    
    latencies = {c["stage"]: c["duration_ms"] for c in tracer.calls}
    
    for i, (stage_key, stage_name) in enumerate(expected_order, 1):
        ms = latencies.get(stage_key, 0)
        engine = "Pipeline" if stage_key not in ["reasoning", "planning", "decision"] else "Brain"
        bar = "█" * min(int(ms / 2), 20) if ms > 0 else "(not executed)"
        print(f"{i:3} {stage_name:25} {engine:20} {ms:8.2f}ms {bar}")
    
    # Return formatted graph
    graph = "Pipeline Flow:\n"
    for i, (stage_key, stage_name) in enumerate(expected_order, 1):
        ms = latencies.get(stage_key, 0)
        graph += f"{i}. {stage_name} → {ms:.2f}ms\n"
    
    return graph


async def main():
    """Run all tests."""
    
    # Test 1: End-to-End
    success, tracer = await run_e2e_test()
    
    if success:
        # Extract call graph
        extract_call_graph(tracer)
        
        # Test 2: Multi-request
        await run_multi_request_test()
        
        # Test 3: Failure injection
        await run_failure_injection_test()
    
    print("\n" + "=" * 100)
    print("TEST COMPLETE")
    print("=" * 100)
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
