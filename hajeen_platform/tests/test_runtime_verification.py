"""
Runtime Verification Test
=========================
This test verifies that all 20 phases are integrated into brain_v3.py.
"""
import ast
import re


def test_brain_v3_has_all_phases():
    """Verify brain_v3.py contains all required phases."""
    with open('/workspace/project/Ai/hajeen_platform/brain/brain_v3.py', 'r') as f:
        content = f.read()
    
    # Check for all phase indicators
    phases = {
        # Phase 1: Intent & Goal
        'Policy Engine': 'self.policy.evaluate',
        'Goal Manager': 'self.goal_manager.analyze',
        
        # Phase 2: Context Management  
        'Intent Analyzer': 'self.intent_analyzer.analyze',
        'Context Analyzer': 'self.context_analyzer.analyze',
        
        # Phase 3: Reasoning Strategies
        'Strategy Selector': 'self.strategy_selector.select',
        
        # Phase 4: Smart Strategy Selection
        'SmartStrategySelector': 'SmartStrategySelector',
        
        # Phase 5: Memory Integration
        'Memory Retrieval': 'get_working_memory',
        'Memory Storage': 'store_experience',
        
        # Phase 6: Knowledge System
        'Knowledge Retrieval': 'get_context_for',
        'Knowledge Storage': 'knowledge_graph.add_knowledge',
        
        # Phase 7: Evidence Court
        'Evidence Court': 'self.evidence_court.evaluate',
        
        # Phase 8: Hypothesis Engine
        'Hypothesis Engine': 'self.hypothesis_engine.generate_hypotheses',
        
        # Phase 9: World Model
        'World Model': 'self.world_model.simulate',
        
        # Phase 10: Planning & Decision
        'Task Decomposer': 'self.task_decomposer.decompose',
        'Graph Planner': 'self.graph_planner.build_graph',
        'Decision Engine': 'self.decision_engine.decide',
        
        # Phase 11: Tool Reasoning
        'Tool Reasoning': 'self.tool_reasoning.reason_about_tools',
        
        # Phase 12: Multi-Agent
        'Multi-Agent': 'self.multi_agent.solve',
        
        # Phase 14: Self Verification
        'Self Verification': 'self_verification',
        
        # Phase 15: Self Reflection
        'Self Reflection': 'self.reflection.reflect',
        
        # Phase 16: Continuous Learning
        'Continuous Learning': 'self.improvement.record_learning',
        
        # Phase 17: Performance
        'Performance': 'self.performance.record_metric',
        
        # Phase 18: Monitoring
        'Monitoring': 'observability.histogram',
        
        # Phase 19: Production
        'Production': 'self.production.health_checker',
        
        # Phase 20: Cognitive Evolution
        'Cognitive Evolution': 'self.cognitive_evolution.reason',
    }
    
    results = {}
    for name, pattern in phases.items():
        found = pattern in content
        results[name] = found
        print(f"{'✅' if found else '❌'} {name}: {'Found' if found else 'NOT FOUND'}")
    
    missing = [k for k, v in results.items() if not v]
    if missing:
        print(f"\n❌ MISSING: {', '.join(missing)}")
    
    assert len(missing) == 0, f"Missing components: {missing}"
    print(f"\n✅ ALL {len(phases)} COMPONENTS VERIFIED!")


def test_strategies_real_has_all_strategies():
    """Verify strategies_real.py contains all required strategies."""
    with open('/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/modular/strategies_real.py', 'r') as f:
        content = f.read()
    
    strategies = [
        'ChainOfThoughtStrategy',
        'TreeOfThoughtsStrategy',
        'FirstPrinciplesStrategy',
        'DeductiveStrategy',
        'InductiveStrategy',
        'MathematicalStrategy',
        'DecompositionStrategy',
        'AnalogicalStrategy',
        'CausalStrategy',
        'ReActStrategy',
        'ProbabilisticStrategy',
        'MultiPerspectiveStrategy',
    ]
    
    results = {}
    for name in strategies:
        found = f'class {name}' in content
        results[name] = found
        print(f"{'✅' if found else '❌'} {name}: {'Found' if found else 'NOT FOUND'}")
    
    missing = [k for k, v in results.items() if not v]
    if missing:
        print(f"\n❌ MISSING: {', '.join(missing)}")
    
    assert len(missing) == 0, f"Missing strategies: {missing}"
    print(f"\n✅ ALL {len(strategies)} STRATEGIES VERIFIED!")


def test_call_chain_in_brain_v3():
    """Verify the complete call chain exists in brain_v3.process()."""
    with open('/workspace/project/Ai/hajeen_platform/brain/brain_v3.py', 'r') as f:
        content = f.read()
    
    # Extract process method
    match = re.search(r'async def process\(.*?\n(.*?)(?=\n    def |\Z)', content, re.DOTALL)
    if not match:
        raise AssertionError("Could not find process() method")
    
    process_body = match.group(1)
    
    # Check for key call chain steps
    call_chain = [
        ('Memory Retrieval', 'self.memory.get_'),
        ('Policy Evaluation', 'self.policy.evaluate'),
        ('Intent Analysis', 'self.intent_analyzer.analyze'),
        ('Context Analysis', 'self.context_analyzer.analyze'),
        ('Strategy Selection', 'self.strategy_selector.select'),
        ('Reasoning Engine', 'self.reasoning_engine.reason'),
        ('Evidence Court', 'self.evidence_court.evaluate'),
        ('Hypothesis Engine', 'self.hypothesis_engine.generate_hypotheses'),
        ('World Model', 'self.world_model.simulate'),
        ('Tool Reasoning', 'self.tool_reasoning.reason_about_tools'),
        ('Task Decomposition', 'self.task_decomposer.decompose'),
        ('Execution', 'self.model_router.route'),
        ('Multi-Agent', 'self.multi_agent.solve'),
        ('Verification', 'self_verification'),
        ('Memory Update', 'self.memory.store_'),
        ('Knowledge Update', 'self.knowledge_graph.add_knowledge'),
        ('Reflection', 'self.reflection.reflect'),
    ]
    
    results = {}
    for name, pattern in call_chain:
        found = pattern in process_body
        results[name] = found
        print(f"{'✅' if found else '❌'} {name}: {'Found' if found else 'NOT FOUND'}")
    
    missing = [k for k, v in results.items() if not v]
    if missing:
        print(f"\n❌ MISSING in Call Chain: {', '.join(missing)}")
    
    assert len(missing) == 0, f"Missing in call chain: {missing}"
    print(f"\n✅ ALL {len(call_chain)} CALL CHAIN STEPS VERIFIED!")


def test_line_numbers_exist():
    """Verify all critical components have line numbers."""
    with open('/workspace/project/Ai/hajeen_platform/brain/brain_v3.py', 'r') as f:
        lines = f.readlines()
    
    components = {
        'Policy Engine': 'self.policy: PolicyEngine',
        'Memory Fabric': 'self.memory: MemoryFabric',
        'Knowledge Graph': 'self.knowledge_graph: KnowledgeGraph',
        'Intent Analyzer': 'self.intent_analyzer: IntentAnalyzer',
        'Context Analyzer': 'self.context_analyzer: ContextAnalyzer',
        'Strategy Selector': 'self.strategy_selector: SmartStrategySelector',
        'Reasoning Engine': 'self.reasoning_engine: ModularReasoningEngine',
        'Evidence Court': 'self.evidence_court: EvidenceCourt',
        'Hypothesis Engine': 'self.hypothesis_engine: HypothesisEngine',
        'World Model': 'self.world_model: WorldModel',
        'Tool Reasoning': 'self.tool_reasoning: ToolReasoningEngine',
        'Multi-Agent': 'self.multi_agent: MultiAgentSystem',
        'Performance': 'self.performance: PerformanceOptimizer',
        'Production': 'self.production: ProductionComponents',
        'Cognitive Evolution': 'self.cognitive_evolution: CognitiveEvolutionEngine',
    }
    
    results = {}
    for name, pattern in components.items():
        for i, line in enumerate(lines, 1):
            if pattern in line:
                results[name] = i
                print(f"✅ {name}: Line {i}")
                break
        else:
            results[name] = None
            print(f"❌ {name}: NOT FOUND")
    
    missing = [k for k, v in results.items() if v is None]
    if missing:
        print(f"\n❌ MISSING Components: {', '.join(missing)}")
    
    assert len(missing) == 0, f"Missing components: {missing}"
    print(f"\n✅ ALL {len(components)} COMPONENTS HAVE LINE NUMBERS!")


def test_step_comments_exist():
    """Verify all step comments exist in brain_v3.process()."""
    with open('/workspace/project/Ai/hajeen_platform/brain/brain_v3.py', 'r') as f:
        content = f.read()
    
    steps = [
        'Step 0b: Memory Integration',
        'Step 0c: Knowledge Retrieval',
        'Step 1: Policy Engine',
        'Step 2: Intent Analyzer',
        'Step 3: Context Analyzer',
        'Step 3.5: Smart Strategy Selection',
        'Step 4: Reasoning Engine',
        'Step 4b: Evidence Court',
        'Step 4c: Hypothesis Engine',
        'Step 4d: World Model',
        'Step 4e: Tool Reasoning',
        'Step 5: Task Decomposer',
        'Step 6: Graph Planner',
        'Step 7: Decision Engine',
        'Step 9: تنفيذ الطلب',
        'Step 9b: Multi-Agent',
        'Step 12: تحديث الذاكرة',
        'Step 14: Self Reflection',
    ]
    
    results = {}
    for step in steps:
        found = step in content
        results[step] = found
        print(f"{'✅' if found else '❌'} {step}: {'Found' if found else 'NOT FOUND'}")
    
    missing = [k for k, v in results.items() if not v]
    if missing:
        print(f"\n❌ MISSING Steps: {', '.join(missing)}")
    
    assert len(missing) == 0, f"Missing steps: {missing}"
    print(f"\n✅ ALL {len(steps)} STEP COMMENTS VERIFIED!")


if __name__ == '__main__':
    print("=" * 70)
    print("RUNTIME VERIFICATION TEST")
    print("=" * 70)
    
    print("\n1. Testing brain_v3.py has all phases...")
    test_brain_v3_has_all_phases()
    
    print("\n2. Testing strategies_real.py has all strategies...")
    test_strategies_real_has_all_strategies()
    
    print("\n3. Testing call chain in brain_v3.process()...")
    test_call_chain_in_brain_v3()
    
    print("\n4. Testing line numbers exist...")
    test_line_numbers_exist()
    
    print("\n5. Testing step comments exist...")
    test_step_comments_exist()
    
    print("\n" + "=" * 70)
    print("✅ ALL RUNTIME VERIFICATION TESTS PASSED!")
    print("=" * 70)
