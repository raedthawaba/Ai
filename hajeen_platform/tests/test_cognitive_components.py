"""
Unit Tests for Cognitive Components - Evidence Court, Hypothesis Engine, World Model
"""
import asyncio
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, '/workspace/project/Ai/hajeen_platform')
sys.path.insert(0, '/workspace/project/Ai')

# Import directly from files to avoid full import chain
import importlib.util

def load_module_from_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# Load modules directly
evidence_court = load_module_from_file(
    "evidence_court",
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/evidence_court.py"
)
hypothesis_engine = load_module_from_file(
    "hypothesis_engine",
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/hypothesis_engine.py"
)
world_model = load_module_from_file(
    "world_model",
    "/workspace/project/Ai/hajeen_platform/brain/cognitive_layer/world_model.py"
)

EvidenceCourt = evidence_court.EvidenceCourt
get_evidence_court = evidence_court.get_evidence_court
EvidenceItem = evidence_court.EvidenceItem
EvidenceEvaluationResult = evidence_court.EvidenceEvaluationResult

HypothesisEngine = hypothesis_engine.HypothesisEngine
get_hypothesis_engine = hypothesis_engine.get_hypothesis_engine
HypothesisResult = hypothesis_engine.HypothesisResult
HypothesesGenerationResult = hypothesis_engine.HypothesesGenerationResult

WorldModel = world_model.WorldModel
get_world_model = world_model.get_world_model
SimulationResult = world_model.SimulationResult


class TestEvidenceCourt:
    """Test Evidence Court component."""
    
    def test_singleton(self):
        """Test singleton pattern."""
        court1 = get_evidence_court()
        court2 = get_evidence_court()
        assert court1 is court2
    
    def test_initialization(self):
        """Test EvidenceCourt initialization."""
        court = EvidenceCourt()
        assert court.min_confidence_threshold == 0.5
        assert court.min_quality_threshold == 0.4
        assert court.min_source_reliability == 0.4
    
    @pytest.mark.asyncio
    async def test_evaluate_basic(self):
        """Test basic evidence evaluation."""
        court = EvidenceCourt()
        
        context = {
            "query": "What is the capital of France?",
            "reasoning_result": "Paris is the capital of France",
            "domain": "geography",
        }
        
        result = await court.evaluate(context)
        
        assert isinstance(result, EvidenceEvaluationResult)
        assert result.confidence >= 0
        assert result.confidence <= 1
        assert result.evidence_score >= 0
        assert isinstance(result.recommendations, list)
    
    @pytest.mark.asyncio
    async def test_evaluate_with_evidence(self):
        """Test evidence evaluation with pre-fetched evidence."""
        court = EvidenceCourt()
        
        context = {
            "query": "Is climate change real?",
            "reasoning_result": "Scientific evidence supports climate change",
            "domain": "science",
            "evidence_sources": [
                {
                    "claim": "Global temperature increased 1.1C since 1880",
                    "source": "NASA",
                    "source_type": "SCIENTIFIC_STUDY",
                    "description": "NASA climate data analysis",
                }
            ],
        }
        
        result = await court.evaluate(context)
        
        assert isinstance(result, EvidenceEvaluationResult)
        assert len(result.sources) > 0
        assert "NASA" in str(result.source_analysis) or "nasa" in str(result.source_analysis).lower()
    
    def test_source_analysis(self):
        """Test source credibility analysis."""
        court = EvidenceCourt()
        
        evidence = EvidenceItem(
            claim="Test claim",
            source="NASA",
            source_type="SCIENTIFIC_STUDY",
        )
        
        analysis = court._analyze_source(evidence)
        
        assert "reliability_score" in analysis
        assert analysis["reliability_score"] >= 0.8  # Scientific study should be high


class TestHypothesisEngine:
    """Test Hypothesis Engine component."""
    
    def test_singleton(self):
        """Test singleton pattern."""
        engine1 = get_hypothesis_engine()
        engine2 = get_hypothesis_engine()
        assert engine1 is engine2
    
    def test_initialization(self):
        """Test HypothesisEngine initialization."""
        engine = HypothesisEngine()
        assert engine.min_plausibility == 0.4
        assert engine.min_evidence_score == 0.3
        assert engine.min_consistency == 0.4
    
    @pytest.mark.asyncio
    async def test_generate_hypotheses_basic(self):
        """Test basic hypothesis generation."""
        engine = HypothesisEngine()
        
        context = {
            "problem": "Why is the sky blue?",
            "reasoning": ["Light scattering", "Wavelength dependence"],
        }
        
        result = await engine.generate_hypotheses(context)
        
        assert isinstance(result, HypothesesGenerationResult)
        assert result.total_generated >= 3
        assert result.valid_count >= 0
        assert result.invalid_count >= 0
        assert isinstance(result.hypotheses, list)
    
    @pytest.mark.asyncio
    async def test_generate_hypotheses_with_evidence(self):
        """Test hypothesis generation with evidence."""
        engine = HypothesisEngine()
        
        context = {
            "problem": "What causes obesity?",
            "reasoning": ["Diet affects weight", "Exercise burns calories"],
            "evidence": {
                "confidence": 0.8,
                "sources": ["Medical Journal"],
            },
        }
        
        result = await engine.generate_hypotheses(context)
        
        assert isinstance(result, HypothesesGenerationResult)
        # Best hypothesis should be set if any are valid
        if result.valid_count > 0:
            assert result.best_hypothesis is not None
    
    def test_key_concept_extraction(self):
        """Test key concept extraction."""
        engine = HypothesisEngine()
        
        concepts = engine._extract_key_concepts("The quick brown fox jumps over the lazy dog")
        
        assert isinstance(concepts, list)
        assert len(concepts) > 0


class TestWorldModel:
    """Test World Model component."""
    
    def test_singleton(self):
        """Test singleton pattern."""
        model1 = get_world_model()
        model2 = get_world_model()
        assert model1 is model2
    
    def test_initialization(self):
        """Test WorldModel initialization."""
        model = WorldModel()
        assert model.dynamics is not None
        assert isinstance(model.simulation_results, list)
    
    @pytest.mark.asyncio
    async def test_simulate_basic(self):
        """Test basic world simulation."""
        model = WorldModel()
        
        context = {
            "scenario": "What happens if we increase taxes on carbon emissions?",
        }
        
        result = await model.simulate(context)
        
        assert isinstance(result, SimulationResult)
        assert result.confidence >= 0
        assert result.confidence <= 1
        assert isinstance(result.predictions, list)
    
    @pytest.mark.asyncio
    async def test_simulate_with_hypothesis(self):
        """Test world simulation with hypothesis."""
        model = WorldModel()
        
        context = {
            "scenario": "What if we switch to renewable energy?",
            "hypothesis": type('obj', (object,), {
                'hypothesis_text': 'Renewable energy reduces carbon emissions',
                'assumptions': ['Technology is available', 'Government supports it']
            })(),
        }
        
        result = await model.simulate(context)
        
        assert isinstance(result, SimulationResult)
        assert len(result.predictions) > 0
        # Best scenario should be selected
        assert result.best_scenario is not None
    
    def test_scenario_generation(self):
        """Test scenario generation."""
        model = WorldModel()
        
        scenarios = model._generate_scenarios(
            "Test scenario",
            {"entities": ["Entity1", "Entity2"]}
        )
        
        assert len(scenarios) >= 4  # baseline, optimistic, pessimistic, + actions
        assert any(s["scenario_name"] == "baseline" for s in scenarios)
        assert any(s["scenario_name"] == "optimistic" for s in scenarios)


class TestIntegration:
    """Integration tests for cognitive components."""
    
    @pytest.mark.asyncio
    async def test_evidence_to_hypothesis_flow(self):
        """Test flow from Evidence Court to Hypothesis Engine."""
        court = EvidenceCourt()
        engine = HypothesisEngine()
        
        # Step 1: Evaluate evidence
        evidence_context = {
            "query": "Should we invest in AI?",
            "reasoning_result": "AI has potential benefits",
            "domain": "technology",
        }
        evidence_result = await court.evaluate(evidence_context)
        
        # Step 2: Generate hypotheses using evidence
        hypothesis_context = {
            "problem": "Should we invest in AI?",
            "reasoning": ["AI has potential benefits"],
            "evidence": evidence_result,
        }
        hypothesis_result = await engine.generate_hypotheses(hypothesis_context)
        
        assert isinstance(evidence_result, EvidenceEvaluationResult)
        assert isinstance(hypothesis_result, HypothesesGenerationResult)
    
    @pytest.mark.asyncio
    async def test_hypothesis_to_world_flow(self):
        """Test flow from Hypothesis Engine to World Model."""
        engine = HypothesisEngine()
        model = WorldModel()
        
        # Step 1: Generate hypothesis
        hypothesis_context = {
            "problem": "What happens with renewable energy adoption?",
            "reasoning": ["Carbon emissions reduce", "Jobs created"],
        }
        hypothesis_result = await engine.generate_hypotheses(hypothesis_context)
        
        # Step 2: Simulate world using best hypothesis
        world_context = {
            "scenario": "Renewable energy adoption in 2030",
            "hypothesis": hypothesis_result.best_hypothesis,
        }
        world_result = await model.simulate(world_context)
        
        assert isinstance(hypothesis_result, HypothesesGenerationResult)
        assert isinstance(world_result, SimulationResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
