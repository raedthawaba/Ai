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


class HypothesisEngine:
    """
    Generates and evaluates multiple hypotheses for complex problems.
    
    The Hypothesis Engine moves beyond single-path reasoning to explore a broader
    solution space, leading to more robust and optimal outcomes.
    """
    
    def __init__(self):
        """Initialize the Hypothesis Engine."""
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.problem_hypotheses: Dict[str, List[str]] = {}  # problem -> [hypothesis_ids]
        self.logger = logging.getLogger(__name__)
    
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
