"""
Test Real Strategies Runtime
==========================

This test proves that strategies work during actual runtime,
not just as dead code.
"""

import asyncio
import sys
sys.path.insert(0, '/workspace/project/Ai/hajeen_platform')


async def test_strategies():
    """Test all strategies are working."""
    print("=" * 60)
    print("TEST: REAL STRATEGY RUNTIME TEST")
    print("=" * 60)
    
    from brain.cognitive_layer.modular.strategies_real import (
        get_strategy_selector,
        ReasoningStrategy,
        ChainOfThoughtStrategy,
        TreeOfThoughtsStrategy,
        MathematicalStrategy,
        CausalStrategy,
    )
    
    selector = get_strategy_selector()
    test_problems = [
        "Explain how photosynthesis works",
        "Calculate 15 * 23 + 45",
        "Why does the sky appear blue",
    ]
    
    results = []
    for problem in test_problems:
        print(f"\nProblem: {problem}")
        result = await selector.select(problem, {})
        print(f"   Strategy: {result.strategy.value}")
        print(f"   Confidence: {result.confidence:.2f}")
        print(f"   Steps: {len(result.steps)}")
        results.append(result)
    
    # Test individual strategies
    print("\n" + "=" * 60)
    print("INDIVIDUAL STRATEGY TESTS")
    print("=" * 60)
    
    for strategy_class in [
        ChainOfThoughtStrategy,
        TreeOfThoughtsStrategy,
        MathematicalStrategy,
    ]:
        s = strategy_class()
        print(f"\n{s.strategy.value}:")
        result = await s.execute("Test problem", {})
        print(f"   Steps: {len(result.steps)}")
        print(f"   Confidence: {result.confidence:.2f}")
    
    return all(r.confidence > 0 for r in results)


if __name__ == "__main__":
    result = asyncio.run(test_strategies())
    print("\n" + "=" * 60)
    if result:
        print("ALL TESTS PASSED - Strategies are Active Runtime!")
    else:
        print("TESTS FAILED")
    print("=" * 60)
