"""
Test for Modular Reasoning Engine Architecture
"""

import asyncio
import sys

sys.path.insert(0, '/workspace/project/Ai/hajeen_platform')

from unittest.mock import MagicMock


async def test_layers():
    """Test all modular layers."""
    print("\n" + "="*60)
    print("🧪 MODULAR ARCHITECTURE TESTS")
    print("="*60)
    
    from brain.cognitive_layer.modular.strategy import StrategySelector, ReasoningStrategy
    from brain.cognitive_layer.modular.context import ContextManager
    from brain.cognitive_layer.modular.session import SessionManager
    from brain.cognitive_layer.modular.state import ReasoningStateMachine, ReasoningState
    from brain.cognitive_layer.modular.confidence import ConfidenceEngine
    from brain.cognitive_layer.modular.verification import VerificationLayer
    from brain.cognitive_layer.modular.reflection import ReflectionLayer
    from brain.cognitive_layer.modular.orchestrator import ModularReasoningEngine
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Strategy Selector
    try:
        selector = StrategySelector()
        await selector.initialize()
        result = await selector.execute({
            "problem": "Explain how the internet works",
            "context": {},
        })
        assert result.success, f"Strategy selector failed: {result.error}"
        print(f"   ✅ Strategy Selector: {result.data['selected_strategy']}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Strategy Selector: {e}")
        tests_failed += 1
    
    # Test 2: Context Manager
    try:
        manager = ContextManager()
        await manager.initialize()
        result = await manager.execute({
            "reasoning_id": "test-123",
            "problem": "What is the capital of France?",
            "strategy": "chain_of_thought",
            "context": {},
        })
        assert result.success
        print(f"   ✅ Context Manager: built context")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Context Manager: {e}")
        tests_failed += 1
    
    # Test 3: State Machine
    try:
        machine = ReasoningStateMachine("test")
        assert machine.current_state == ReasoningState.INITIAL
        success = machine.transition(ReasoningState.CONTEXT_BUILT, "Context built")
        assert success
        print(f"   ✅ State Machine: transitions work")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ State Machine: {e}")
        tests_failed += 1
    
    # Test 4: Confidence Engine
    try:
        engine = ConfidenceEngine()
        await engine.initialize()
        result = await engine.execute({
            "reasoning_steps": [
                {"description": "Step 1", "confidence": 0.8},
            ],
            "solutions": [],
            "risks": [],
        })
        assert result.success
        print(f"   ✅ Confidence Engine: {result.data['overall_confidence']:.2f}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Confidence Engine: {e}")
        tests_failed += 1
    
    # Test 5: Verification Layer
    try:
        layer = VerificationLayer()
        await layer.initialize()
        result = await layer.execute({
            "reasoning_steps": [{"description": "Step"}],
            "confidence": 0.75,
        })
        assert result.success
        print(f"   ✅ Verification Layer: score={result.data['score']:.2f}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Verification Layer: {e}")
        tests_failed += 1
    
    # Test 6: Reflection Layer
    try:
        layer = ReflectionLayer()
        await layer.initialize()
        result = await layer.execute({
            "reasoning_steps": [{"description": "Step 1"}, {"description": "Step 2"}],
            "confidence": 0.8,
        })
        assert result.success
        print(f"   ✅ Reflection Layer: quality={result.data['quality_assessment']}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Reflection Layer: {e}")
        tests_failed += 1
    
    # Test 7: Modular Reasoning Engine
    try:
        mock_llm = MagicMock()
        mock_llm.generate = MagicMock(return_value="test response")
        
        engine = ModularReasoningEngine(llm_manager=mock_llm)
        result = await engine.reason("What is 2+2?", {}, ReasoningStrategy.CHAIN_OF_THOUGHT)
        
        assert result.reasoning_id is not None
        assert result.overall_confidence > 0
        print(f"   ✅ Modular Engine: id={result.reasoning_id[:8]}, confidence={result.overall_confidence:.2f}")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Modular Engine: {e}")
        tests_failed += 1
    
    print("\n" + "="*60)
    print(f"📊 Results: {tests_passed} passed, {tests_failed} failed")
    print("="*60)
    
    return tests_failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_layers())
    sys.exit(0 if success else 1)
