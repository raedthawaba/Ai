"""
Hypothesis Engine - Generation and evaluation of multiple hypotheses.

The Hypothesis Engine generates multiple plausible hypotheses for complex problems,
evaluates each one, gathers supporting evidence, simulates outcomes, and selects
the strongest hypothesis based on available evidence.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HypothesisStatus(Enum):
    """Enumeration of hypothesis statuses."""
    PROPOSED = "proposed"
    UNDER_EVALUATION = "under_evaluation"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


@dataclass
class HypothesisResult:
    """Result of hypothesis generation with evaluation."""
    hypothesis_id: str = ""
    problem: str = ""
    hypothesis_text: str = ""
    
    # Evaluation Scores
    plausibility: float = 0.0
    evidence_score: float = 0.0
    consistency: float = 0.0
    overall_score: float = 0.0
    
    # Status
    status: str = "proposed"
    is_valid: bool = False
    should_use: bool = False
    
    # Components
    assumptions: List[str] = field(default_factory=list)
    predictions: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    
    # Decision Impact
    decision_impact: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.hypothesis_id,
            "problem": self.problem,
            "hypothesis_text": self.hypothesis_text,
            "plausibility": round(self.plausibility, 3),
            "evidence_score": round(self.evidence_score, 3),
            "consistency": round(self.consistency, 3),
            "overall_score": round(self.overall_score, 3),
            "status": self.status,
            "is_valid": self.is_valid,
            "should_use": self.should_use,
            "assumptions": self.assumptions,
            "predictions": self.predictions,
            "decision_impact": round(self.decision_impact, 3),
        }


@dataclass
class HypothesesGenerationResult:
    """Result of hypothesis generation process."""
    problem: str = ""
    hypotheses: List[HypothesisResult] = field(default_factory=list)
    best_hypothesis: Optional[HypothesisResult] = None
    rejected_hypotheses: List[HypothesisResult] = field(default_factory=list)
    total_generated: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem": self.problem,
            "total_generated": self.total_generated,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "best_hypothesis": self.best_hypothesis.to_dict() if self.best_hypothesis else None,
            "rejected_count": len(self.rejected_hypotheses),
        }


@dataclass
class Hypothesis:
    """
    Represents a proposed hypothesis with evaluation details.
    """
    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    problem_statement: str = ""
    hypothesis_text: str = ""
    
    # Hypothesis Details
    assumptions: List[str] = field(default_factory=list)
    predictions: List[str] = field(default_factory=list)
    
    # Evaluation
    status: str = HypothesisStatus.PROPOSED.value
    plausibility_score: float = 0.5
    evidence_score: float = 0.0
    consistency_score: float = 0.5
    
    # Evidence
    supporting_evidence: List[Dict[str, Any]] = field(default_factory=list)
    contradicting_evidence: List[Dict[str, Any]] = field(default_factory=list)
    
    # Simulation Results
    simulation_results: List[Dict[str, Any]] = field(default_factory=list)
    predicted_outcomes: List[str] = field(default_factory=list)
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['evaluated_at']:
            data['evaluated_at'] = self.evaluated_at.isoformat()
        return data
    
    def get_overall_score(self) -> float:
        """Calculate overall hypothesis score."""
        # Weighted combination of scores
        overall = (
            self.plausibility_score * 0.3 +
            self.evidence_score * 0.4 +
            self.consistency_score * 0.3
        )
        return overall


# Singleton instance
_hypothesis_engine_instance: Optional["HypothesisEngine"] = None


def get_hypothesis_engine() -> "HypothesisEngine":
    """Get singleton instance of HypothesisEngine."""
    global _hypothesis_engine_instance
    if _hypothesis_engine_instance is None:
        _hypothesis_engine_instance = HypothesisEngine()
    return _hypothesis_engine_instance


class HypothesisEngine:
    """
    Generates and evaluates multiple hypotheses for complex problems.
    
    The Hypothesis Engine moves beyond single-path reasoning to explore a broader
    solution space, leading to more robust and optimal outcomes.
    
    This implementation provides REAL hypothesis generation with:
    - Multiple hypothesis generation
    - Plausibility evaluation
    - Evidence scoring
    - Consistency checking
    - Best hypothesis selection
    - Impact on reasoning flow
    """
    
    def __init__(self):
        """Initialize the Hypothesis Engine."""
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.problem_hypotheses: Dict[str, List[str]] = {}
        self.evaluation_results: List[HypothesesGenerationResult] = []
        self.logger = logging.getLogger(__name__)
        
        # Thresholds
        self.min_plausibility = 0.4
        self.min_evidence_score = 0.3
        self.min_consistency = 0.4
        self.min_overall_score = 0.4
    
    async def generate_hypotheses(self, context: Dict[str, Any]) -> HypothesesGenerationResult:
        """
        Generate multiple hypotheses for a problem.
        
        This is the main entry point called from BrainV3.process().
        
        Args:
            context: {
                "problem": str,              # The problem statement
                "reasoning": List[str],       # Reasoning steps from previous phase
                "evidence": Any,              # Evidence from Evidence Court
            }
        
        Returns:
            HypothesesGenerationResult with all hypotheses and best selection
        """
        problem = context.get("problem", "")
        reasoning_steps = context.get("reasoning", [])
        evidence = context.get("evidence")
        
        self.logger.info(f"Generating hypotheses for: {problem[:50]}...")
        
        # Step 1: Extract key concepts from problem
        key_concepts = self._extract_key_concepts(problem)
        
        # Step 2: Generate multiple hypotheses using different strategies
        hypotheses = []
        hypotheses.extend(self._generate_direct_hypotheses(problem, key_concepts))
        hypotheses.extend(self._generate_alternative_hypotheses(problem, key_concepts))
        hypotheses.extend(self._generate_negation_hypotheses(problem, key_concepts))
        hypotheses.extend(self._generate_comparative_hypotheses(problem, key_concepts))
        
        # Step 3: Evaluate each hypothesis
        evaluated_hypotheses = []
        for hyp_text in hypotheses:
            result = await self._evaluate_hypothesis(problem, hyp_text, reasoning_steps, evidence)
            evaluated_hypotheses.append(result)
        
        # Step 4: Filter weak hypotheses
        valid_hypotheses = [h for h in evaluated_hypotheses if h.is_valid]
        invalid_hypotheses = [h for h in evaluated_hypotheses if not h.is_valid]
        
        # Step 5: Select best hypothesis
        best_hypothesis = None
        if valid_hypotheses:
            best_hypothesis = max(valid_hypotheses, key=lambda x: x.overall_score)
            best_hypothesis.should_use = True
        
        # Step 6: Build result
        result = HypothesesGenerationResult(
            problem=problem,
            hypotheses=evaluated_hypotheses,
            best_hypothesis=best_hypothesis,
            rejected_hypotheses=invalid_hypotheses,
            total_generated=len(hypotheses),
            valid_count=len(valid_hypotheses),
            invalid_count=len(invalid_hypotheses),
        )
        
        self.evaluation_results.append(result)
        
        self.logger.info(
            f"Generated {len(hypotheses)} hypotheses: "
            f"{len(valid_hypotheses)} valid, "
            f"{len(invalid_hypotheses)} rejected"
        )
        
        return result
    
    def _extract_key_concepts(self, problem: str) -> List[str]:
        """Extract key concepts from problem statement."""
        import re
        
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'to', 'of', 'in', 'for', 'on', 'with',
            'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after',
            'above', 'below', 'between', 'under', 'again', 'further', 'then', 'once',
            'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each', 'few',
            'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
            'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now',
        }
        
        # Extract words
        words = re.findall(r'\b[a-zA-Z]{4,}\b', problem.lower())
        concepts = [w for w in words if w not in stop_words]
        
        # Get unique concepts with frequency
        concept_freq = {}
        for word in concepts:
            concept_freq[word] = concept_freq.get(word, 0) + 1
        
        # Sort by frequency and return top concepts
        sorted_concepts = sorted(concept_freq.items(), key=lambda x: x[1], reverse=True)
        return [c[0] for c in sorted_concepts[:10]]
    
    def _generate_direct_hypotheses(self, problem: str, concepts: List[str]) -> List[str]:
        """Generate direct hypotheses based on problem analysis."""
        hypotheses = []
        
        if not concepts:
            concepts = ["solution", "approach"]
        
        # Direct cause-effect hypothesis
        primary_concept = concepts[0] if concepts else "this"
        hypotheses.append(
            f"{primary_concept.title()} is the primary cause or solution to the problem"
        )
        
        # Multiple factor hypothesis
        if len(concepts) >= 2:
            hypotheses.append(
                f"The interaction between {concepts[0]} and {concepts[1]} creates the solution"
            )
        
        # Systematic approach hypothesis
        hypotheses.append(
            f"A systematic approach considering all factors will solve the problem"
        )
        
        return hypotheses
    
    def _generate_alternative_hypotheses(self, problem: str, concepts: List[str]) -> List[str]:
        """Generate alternative perspective hypotheses."""
        hypotheses = []
        
        # Different angle hypothesis
        hypotheses.append(
            "The problem requires an unexpected or unconventional approach"
        )
        
        # External factor hypothesis
        hypotheses.append(
            "External factors beyond the immediate context are the root cause"
        )
        
        # Multiple solutions hypothesis
        hypotheses.append(
            "Multiple parallel solutions exist, not a single best approach"
        )
        
        # Timing hypothesis
        hypotheses.append(
            "The timing and sequence of actions is more important than the actions themselves"
        )
        
        return hypotheses
    
    def _generate_negation_hypotheses(self, problem: str, concepts: List[str]) -> List[str]:
        """Generate hypotheses that negate common assumptions."""
        hypotheses = []
        
        # Reverse assumption
        hypotheses.append(
            "The opposite of what seems obvious is actually true"
        )
        
        # Null hypothesis (no solution needed)
        hypotheses.append(
            "No action is needed - the problem will resolve itself"
        )
        
        # False problem hypothesis
        hypotheses.append(
            "The stated problem is a symptom, not the actual issue"
        )
        
        return hypotheses
    
    def _generate_comparative_hypotheses(self, problem: str, concepts: List[str]) -> List[str]:
        """Generate comparative hypotheses."""
        hypotheses = []
        
        # Comparison with similar problems
        hypotheses.append(
            "This problem can be solved using patterns from similar solved problems"
        )
        
        # Gradual vs dramatic change
        hypotheses.append(
            "Gradual incremental changes will be more effective than dramatic changes"
        )
        
        # Resource-based hypothesis
        hypotheses.append(
            "The solution depends on optimal resource allocation and prioritization"
        )
        
        return hypotheses
    
    async def _evaluate_hypothesis(
        self,
        problem: str,
        hypothesis_text: str,
        reasoning_steps: List[str],
        evidence: Any
    ) -> HypothesisResult:
        """Evaluate a single hypothesis."""
        result = HypothesisResult(
            hypothesis_id=str(uuid.uuid4()),
            problem=problem,
            hypothesis_text=hypothesis_text,
        )
        
        # Step 1: Calculate plausibility
        result.plausibility = self._calculate_plausibility(problem, hypothesis_text, reasoning_steps)
        
        # Step 2: Calculate evidence score
        result.evidence_score = self._evaluate_evidence_support(hypothesis_text, evidence)
        
        # Step 3: Calculate consistency
        result.consistency = self._calculate_consistency(hypothesis_text, reasoning_steps)
        
        # Step 4: Calculate overall score
        result.overall_score = self._calculate_overall_score(
            result.plausibility,
            result.evidence_score,
            result.consistency
        )
        
        # Step 5: Extract assumptions
        result.assumptions = self._extract_assumptions(hypothesis_text)
        
        # Step 6: Generate predictions
        result.predictions = self._generate_predictions(hypothesis_text)
        
        # Step 7: Determine validity
        result.is_valid = self._is_hypothesis_valid(result)
        
        # Step 8: Set status
        if result.is_valid:
            if result.overall_score >= 0.7:
                result.status = "supported"
            else:
                result.status = "under_evaluation"
        else:
            result.status = "rejected"
        
        return result
    
    def _calculate_plausibility(
        self,
        problem: str,
        hypothesis_text: str,
        reasoning_steps: List[str]
    ) -> float:
        """Calculate how plausible the hypothesis is."""
        import re
        
        # Base plausibility
        plausibility = 0.5
        
        # Check alignment with reasoning steps
        hypothesis_words = set(re.findall(r'\w+', hypothesis_text.lower()))
        reasoning_text = ' '.join(reasoning_steps).lower()
        reasoning_words = set(re.findall(r'\w+', reasoning_text))
        
        if hypothesis_words & reasoning_words:
            overlap = len(hypothesis_words & reasoning_words) / len(hypothesis_words | reasoning_words)
            plausibility += overlap * 0.3
        
        # Check for extreme language
        extreme_words = ['always', 'never', 'impossible', 'certain', 'definitely']
        has_extreme = any(word in hypothesis_text.lower() for word in extreme_words)
        if has_extreme:
            plausibility -= 0.15
        
        # Check for qualified language
        qualified_words = ['might', 'could', 'possibly', 'perhaps', 'likely', 'probably']
        has_qualified = any(word in hypothesis_text.lower() for word in qualified_words)
        if has_qualified:
            plausibility += 0.05
        
        # Length check (too short or too long is less plausible)
        if 20 < len(hypothesis_text) < 100:
            plausibility += 0.05
        
        # Check specificity
        if len(hypothesis_words) >= 5:
            plausibility += 0.05
        
        return min(1.0, max(0.0, plausibility))
    
    def _evaluate_evidence_support(self, hypothesis_text: str, evidence: Any) -> float:
        """Calculate evidence support score."""
        score = 0.3  # Base score with no evidence
        
        if evidence is None:
            return score
        
        # Check if evidence is a dict with relevant fields
        if isinstance(evidence, dict):
            # Evidence has confidence/score
            if 'confidence' in evidence:
                score += evidence['confidence'] * 0.4
            elif 'evidence_score' in evidence:
                score += evidence['evidence_score'] * 0.4
            
            # Evidence has sources
            if 'sources' in evidence and evidence['sources']:
                score += 0.1
            
            # Evidence has recommendations
            if 'recommendations' in evidence:
                recs = evidence['recommendations']
                if any('strong' in str(r).lower() for r in recs):
                    score += 0.1
        
        # Check if evidence is from Evidence Court
        if hasattr(evidence, 'confidence'):
            score = min(1.0, score + evidence.confidence * 0.5)
        
        return min(1.0, max(0.0, score))
    
    def _calculate_consistency(self, hypothesis_text: str, reasoning_steps: List[str]) -> float:
        """Calculate consistency with reasoning steps."""
        if not reasoning_steps:
            return 0.5
        
        import re
        
        # Extract words from hypothesis
        hyp_words = set(re.findall(r'\w+', hypothesis_text.lower()))
        
        # Check consistency with each reasoning step
        consistency_scores = []
        for step in reasoning_steps:
            step_words = set(re.findall(r'\w+', step.lower()))
            
            if not hyp_words or not step_words:
                continue
            
            # Check for contradictions
            contradiction_pairs = [
                ('can', 'cannot'), ('is', 'is not'), ('will', 'will not'),
                ('should', 'should not'), ('does', 'does not'),
            ]
            
            has_contradiction = False
            for pos, neg in contradiction_pairs:
                if pos in step.lower() and neg in hypothesis_text.lower():
                    has_contradiction = True
                    break
            
            if has_contradiction:
                consistency_scores.append(0.2)
            else:
                # Calculate word overlap
                overlap = len(hyp_words & step_words) / len(hyp_words | step_words)
                consistency_scores.append(0.5 + overlap * 0.4)
        
        if consistency_scores:
            return sum(consistency_scores) / len(consistency_scores)
        
        return 0.5
    
    def _calculate_overall_score(self, plausibility: float, evidence: float, consistency: float) -> float:
        """Calculate overall hypothesis score."""
        # Weighted combination
        overall = (
            plausibility * 0.35 +
            evidence * 0.40 +
            consistency * 0.25
        )
        
        return min(1.0, max(0.0, overall))
    
    def _extract_assumptions(self, hypothesis_text: str) -> List[str]:
        """Extract underlying assumptions from hypothesis."""
        assumptions = []
        
        # Look for implicit assumptions
        assumption_patterns = [
            (r'if (.+?),', r'Assumes that \1'),
            (r'assuming (.+?)(?:\.|$)', r'\1'),
            (r'given that (.+?)(?:\.|$)', r'\1'),
            (r'on the assumption that (.+?)(?:\.|$)', r'\1'),
        ]
        
        import re
        for pattern, _ in assumption_patterns:
            matches = re.findall(pattern, hypothesis_text, re.IGNORECASE)
            for match in matches:
                assumptions.append(match.strip())
        
        # If no patterns found, create default assumptions
        if not assumptions:
            assumptions.append("The hypothesis applies to the current context")
            assumptions.append("Available information is sufficient to evaluate this hypothesis")
        
        return assumptions[:5]  # Limit to 5 assumptions
    
    def _generate_predictions(self, hypothesis_text: str) -> List[str]:
        """Generate predictions based on hypothesis."""
        predictions = []
        
        # Generate testable predictions
        import re
        
        # Extract key claims
        words = re.findall(r'\b[a-zA-Z]{4,}\b', hypothesis_text.lower())
        
        if words:
            predictions.append(
                f"If the hypothesis is correct, {words[0]} will have measurable impact"
            )
        
        # Action-based prediction
        predictions.append(
            "Taking action based on this hypothesis should produce observable results"
        )
        
        # Verification prediction
        predictions.append(
            "Further evidence should align with the hypothesis over time"
        )
        
        return predictions[:3]  # Limit to 3 predictions
    
    def _is_hypothesis_valid(self, result: HypothesisResult) -> bool:
        """Determine if hypothesis meets validity thresholds."""
        # All conditions must be met
        if result.plausibility < self.min_plausibility:
            return False
        if result.evidence_score < self.min_evidence_score:
            return False
        if result.consistency < self.min_consistency:
            return False
        if result.overall_score < self.min_overall_score:
            return False
        
        return True
    
    def generate_hypothesis(self, problem_statement: str, hypothesis_text: str,
                           assumptions: Optional[List[str]] = None) -> Hypothesis:
        """
        Generate a new hypothesis for a problem.
        
        Args:
            problem_statement: The problem being addressed
            hypothesis_text: The proposed hypothesis
            assumptions: Optional list of assumptions underlying the hypothesis
            
        Returns:
            The created Hypothesis object
        """
        hypothesis = Hypothesis(
            problem_statement=problem_statement,
            hypothesis_text=hypothesis_text,
            assumptions=assumptions or []
        )
        
        self.hypotheses[hypothesis.hypothesis_id] = hypothesis
        
        # Index by problem
        if problem_statement not in self.problem_hypotheses:
            self.problem_hypotheses[problem_statement] = []
        self.problem_hypotheses[problem_statement].append(hypothesis.hypothesis_id)
        
        self.logger.info(f"Generated hypothesis {hypothesis.hypothesis_id} for problem: {problem_statement}")
        return hypothesis
    
    def generate_multiple_hypotheses(self, problem_statement: str, num_hypotheses: int = 3) -> List[Hypothesis]:
        """
        Generate multiple hypotheses for a problem.
        
        Args:
            problem_statement: The problem being addressed
            num_hypotheses: Number of hypotheses to generate
            
        Returns:
            List of generated Hypothesis objects
        """
        hypotheses = []
        
        # Generate diverse hypotheses
        for i in range(num_hypotheses):
            hypothesis_text = self._generate_hypothesis_text(problem_statement, i)
            hypothesis = self.generate_hypothesis(problem_statement, hypothesis_text)
            hypotheses.append(hypothesis)
        
        self.logger.info(f"Generated {num_hypotheses} hypotheses for problem: {problem_statement}")
        return hypotheses
    
    def _generate_hypothesis_text(self, problem_statement: str, variant: int = 0) -> str:
        """Generate hypothesis text (can be enhanced with LLM)."""
        variants = [
            f"Hypothesis {variant + 1}: {problem_statement} may be explained by causal factors.",
            f"Hypothesis {variant + 1}: {problem_statement} could result from systemic interactions.",
            f"Hypothesis {variant + 1}: {problem_statement} might be influenced by external variables.",
            f"Hypothesis {variant + 1}: {problem_statement} could be a consequence of feedback loops.",
        ]
        
        return variants[variant % len(variants)]
    
    def evaluate_hypothesis(self, hypothesis_id: str) -> float:
        """
        Evaluate a hypothesis.
        
        Args:
            hypothesis_id: The ID of the hypothesis to evaluate
            
        Returns:
            The overall evaluation score
        """
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            return 0.0
        
        hypothesis.status = HypothesisStatus.UNDER_EVALUATION.value
        
        # Evaluate plausibility
        hypothesis.plausibility_score = self._evaluate_plausibility(hypothesis)
        
        # Evaluate consistency
        hypothesis.consistency_score = self._evaluate_consistency(hypothesis)
        
        # Calculate evidence score
        hypothesis.evidence_score = self._calculate_evidence_score(hypothesis)
        
        # Determine final status
        overall_score = hypothesis.get_overall_score()
        if overall_score > 0.75:
            hypothesis.status = HypothesisStatus.SUPPORTED.value
        elif overall_score < 0.4:
            hypothesis.status = HypothesisStatus.REJECTED.value
        else:
            hypothesis.status = HypothesisStatus.INCONCLUSIVE.value
        
        hypothesis.evaluated_at = datetime.utcnow()
        
        self.logger.info(f"Evaluated hypothesis {hypothesis_id} with score {overall_score}")
        return overall_score
    
    def _evaluate_plausibility(self, hypothesis: Hypothesis) -> float:
        """Evaluate the plausibility of a hypothesis."""
        plausibility = 0.5
        
        # Check assumptions
        if hypothesis.assumptions:
            plausibility += 0.2
        
        # Check predictions
        if hypothesis.predictions:
            plausibility += 0.2
        
        # Penalize for contradictions
        if hypothesis.contradicting_evidence:
            plausibility -= len(hypothesis.contradicting_evidence) * 0.1
        
        return max(0.0, min(1.0, plausibility))
    
    def _evaluate_consistency(self, hypothesis: Hypothesis) -> float:
        """Evaluate the internal consistency of a hypothesis."""
        consistency = 0.5
        
        # Check for self-contradictions
        if self._has_self_contradictions(hypothesis):
            consistency -= 0.3
        
        # Check for logical coherence
        if self._is_logically_coherent(hypothesis):
            consistency += 0.3
        
        return max(0.0, min(1.0, consistency))
    
    def _has_self_contradictions(self, hypothesis: Hypothesis) -> bool:
        """Check if hypothesis has internal contradictions."""
        # Simple check (can be enhanced with logical analysis)
        return False
    
    def _is_logically_coherent(self, hypothesis: Hypothesis) -> bool:
        """Check if hypothesis is logically coherent."""
        # Simple check (can be enhanced with logical analysis)
        return len(hypothesis.assumptions) > 0 and len(hypothesis.predictions) > 0
    
    def _calculate_evidence_score(self, hypothesis: Hypothesis) -> float:
        """Calculate evidence score based on supporting and contradicting evidence."""
        supporting = len(hypothesis.supporting_evidence)
        contradicting = len(hypothesis.contradicting_evidence)
        
        total = supporting + contradicting
        if total == 0:
            return 0.5
        
        evidence_score = supporting / total
        return evidence_score
    
    def add_supporting_evidence(self, hypothesis_id: str, evidence: Dict[str, Any]) -> bool:
        """
        Add supporting evidence to a hypothesis.
        
        Args:
            hypothesis_id: The ID of the hypothesis
            evidence: The supporting evidence
            
        Returns:
            True if successful, False otherwise
        """
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            return False
        
        hypothesis.supporting_evidence.append(evidence)
        return True
    
    def add_contradicting_evidence(self, hypothesis_id: str, evidence: Dict[str, Any]) -> bool:
        """
        Add contradicting evidence to a hypothesis.
        
        Args:
            hypothesis_id: The ID of the hypothesis
            evidence: The contradicting evidence
            
        Returns:
            True if successful, False otherwise
        """
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            return False
        
        hypothesis.contradicting_evidence.append(evidence)
        return True
    
    def simulate_outcome(self, hypothesis_id: str, simulation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate the outcome of a hypothesis.
        
        Args:
            hypothesis_id: The ID of the hypothesis
            simulation_data: Data for the simulation
            
        Returns:
            Simulation results
        """
        hypothesis = self.hypotheses.get(hypothesis_id)
        if not hypothesis:
            return {}
        
        result = {
            'simulation_id': str(uuid.uuid4()),
            'hypothesis_id': hypothesis_id,
            'timestamp': datetime.utcnow().isoformat(),
            'data': simulation_data,
            'predicted_outcomes': hypothesis.predictions
        }
        
        hypothesis.simulation_results.append(result)
        
        self.logger.info(f"Simulated outcome for hypothesis {hypothesis_id}")
        return result
    
    def select_strongest_hypothesis(self, problem_statement: str) -> Optional[Hypothesis]:
        """
        Select the strongest hypothesis for a problem.
        
        Args:
            problem_statement: The problem statement
            
        Returns:
            The strongest Hypothesis, or None if no hypotheses exist
        """
        hypothesis_ids = self.problem_hypotheses.get(problem_statement, [])
        
        if not hypothesis_ids:
            return None
        
        # Evaluate all hypotheses if not already evaluated
        for hyp_id in hypothesis_ids:
            hypothesis = self.hypotheses[hyp_id]
            if hypothesis.status == HypothesisStatus.PROPOSED.value:
                self.evaluate_hypothesis(hyp_id)
        
        # Find the strongest
        strongest = None
        strongest_score = -1.0
        
        for hyp_id in hypothesis_ids:
            hypothesis = self.hypotheses[hyp_id]
            score = hypothesis.get_overall_score()
            
            if score > strongest_score:
                strongest_score = score
                strongest = hypothesis
        
        self.logger.info(f"Selected strongest hypothesis for problem: {problem_statement}")
        return strongest
    
    def get_hypotheses_for_problem(self, problem_statement: str) -> List[Hypothesis]:
        """
        Get all hypotheses for a problem.
        
        Args:
            problem_statement: The problem statement
            
        Returns:
            List of Hypothesis objects
        """
        hypothesis_ids = self.problem_hypotheses.get(problem_statement, [])
        return [self.hypotheses[hyp_id] for hyp_id in hypothesis_ids if hyp_id in self.hypotheses]
    
    def rank_hypotheses(self, problem_statement: str) -> List[Hypothesis]:
        """
        Rank hypotheses for a problem by their scores.
        
        Args:
            problem_statement: The problem statement
            
        Returns:
            List of Hypothesis objects ranked by score
        """
        hypotheses = self.get_hypotheses_for_problem(problem_statement)
        
        # Sort by overall score
        hypotheses.sort(key=lambda h: h.get_overall_score(), reverse=True)
        
        return hypotheses
    
    def get_hypothesis_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about hypotheses.
        
        Returns:
            Dictionary containing hypothesis statistics
        """
        stats = {
            'total_hypotheses': len(self.hypotheses),
            'supported_hypotheses': 0,
            'rejected_hypotheses': 0,
            'inconclusive_hypotheses': 0,
            'average_score': 0.0,
            'problems_addressed': len(self.problem_hypotheses)
        }
        
        if not self.hypotheses:
            return stats
        
        scores = []
        for hypothesis in self.hypotheses.values():
            if hypothesis.status == HypothesisStatus.SUPPORTED.value:
                stats['supported_hypotheses'] += 1
            elif hypothesis.status == HypothesisStatus.REJECTED.value:
                stats['rejected_hypotheses'] += 1
            elif hypothesis.status == HypothesisStatus.INCONCLUSIVE.value:
                stats['inconclusive_hypotheses'] += 1
            
            scores.append(hypothesis.get_overall_score())
        
        stats['average_score'] = sum(scores) / len(scores) if scores else 0.0
        
        return stats
    
    def export_hypotheses(self, hypothesis_ids: Optional[List[str]] = None) -> str:
        """
        Export hypotheses as JSON.
        
        Args:
            hypothesis_ids: Optional list of specific hypothesis IDs to export
            
        Returns:
            JSON string containing the hypotheses
        """
        if hypothesis_ids:
            hypotheses = [self.hypotheses[hid] for hid in hypothesis_ids if hid in self.hypotheses]
        else:
            hypotheses = list(self.hypotheses.values())
        
        return json.dumps([h.to_dict() for h in hypotheses], indent=2, default=str)
