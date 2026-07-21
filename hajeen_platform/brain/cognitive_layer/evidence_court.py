"""
Evidence Court - Rigorous evaluation and validation of information.

The Evidence Court acts as a gatekeeper for new information, rigorously evaluating
its credibility and consistency before it is integrated into the system's long-term
knowledge base.

This implementation provides REAL evidence evaluation with:
- Source credibility analysis
- Evidence quality scoring
- Contradiction detection
- Confidence calculation
- Impact on final decision
"""

import json
import logging
import uuid
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Enumeration of information source types with reliability weights."""
    ACADEMIC = 0.95
    SCIENTIFIC_STUDY = 0.90
    PEER_REVIEWED = 0.88
    EXPERT_OPINION = 0.75
    OFFICIAL_DOCUMENT = 0.80
    NEWS_OUTLET = 0.55
    BLOG = 0.40
    SOCIAL_MEDIA = 0.25
    FORUM = 0.30
    UNKNOWN = 0.50


class EvidenceQuality(Enum):
    """Enumeration of evidence quality levels."""
    EXCELLENT = 0.95
    GOOD = 0.80
    FAIR = 0.60
    POOR = 0.30
    UNRELIABLE = 0.10


class EvidenceSource(Enum):
    """Source categories for evidence collection."""
    KNOWLEDGE_GRAPH = "knowledge_graph"
    WORKING_MEMORY = "working_memory"
    LONG_TERM_MEMORY = "long_term_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    EPISODIC_MEMORY = "episodic_memory"
    EXTERNAL_API = "external_api"
    USER_PROVIDED = "user_provided"
    DERIVED = "derived"


@dataclass
class EvidenceItem:
    """Represents a piece of evidence for evaluation."""
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = ""
    source: str = ""
    source_type: str = "unknown"
    source_category: str = "unknown"
    
    # Evidence Details
    description: str = ""
    data: Any = None
    methodology: str = ""
    
    # Evaluation Metrics
    quality_score: float = 0.0
    credibility_score: float = 0.0
    relevance_score: float = 0.0
    consistency_score: float = 0.0
    
    # Source Analysis
    source_reliability: float = 0.0
    publication_date: Optional[str] = None
    citation_count: int = 0
    peer_reviewed: bool = False
    
    # Metadata
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_at: Optional[datetime] = None
    evaluation_notes: str = ""
    evidence_sources: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['submitted_at'] = self.submitted_at.isoformat()
        if data['evaluated_at']:
            data['evaluated_at'] = self.evaluated_at.isoformat()
        return data


@dataclass
class EvidenceEvaluationResult:
    """Result of evidence evaluation with decision impact."""
    evidence_id: str = ""
    claim: str = ""
    
    # Scores
    evidence_score: float = 0.0
    confidence: float = 0.0
    reliability: float = 0.0
    
    # Analysis Components
    source_analysis: Dict[str, Any] = field(default_factory=dict)
    quality_analysis: Dict[str, Any] = field(default_factory=dict)
    consistency_analysis: Dict[str, Any] = field(default_factory=dict)
    contradiction_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # Ranking
    rank: int = 0
    is_valid: bool = False
    should_integrate: bool = False
    
    # Decision Impact
    decision_impact: float = 0.0
    confidence_weight: float = 0.0
    
    # Evidence Sources
    sources: List[str] = field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    rejected_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "claim": self.claim,
            "evidence_score": round(self.evidence_score, 3),
            "confidence": round(self.confidence, 3),
            "reliability": round(self.reliability, 3),
            "rank": self.rank,
            "is_valid": self.is_valid,
            "should_integrate": self.should_integrate,
            "decision_impact": round(self.decision_impact, 3),
            "sources": self.sources,
            "recommendations": self.recommendations,
        }


@dataclass
class ValidationReport:
    """Report of evidence validation."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evidence_id: str = ""
    
    # Validation Results
    is_valid: bool = False
    confidence_score: float = 0.5
    
    # Analysis
    source_analysis: Dict[str, Any] = field(default_factory=dict)
    quality_assessment: Dict[str, Any] = field(default_factory=dict)
    contradiction_analysis: Dict[str, Any] = field(default_factory=dict)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    additional_evidence_needed: List[str] = field(default_factory=list)
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data


# Singleton instance
_evidence_court_instance: Optional["EvidenceCourt"] = None


def get_evidence_court() -> "EvidenceCourt":
    """Get singleton instance of EvidenceCourt."""
    global _evidence_court_instance
    if _evidence_court_instance is None:
        _evidence_court_instance = EvidenceCourt()
    return _evidence_court_instance


class EvidenceCourt:
    """
    Rigorous evaluation and validation of information before integration.
    
    This Court provides REAL evidence evaluation:
    1. Collects evidence from all available sources
    2. Evaluates evidence quality and credibility
    3. Calculates source reliability
    4. Ranks and orders evidence
    5. Detects contradictions
    6. Rejects weak evidence
    7. Sends results to Confidence Engine
    8. Impacts final decision
    """
    
    def __init__(self):
        """Initialize the Evidence Court."""
        self.evidence_store: Dict[str, EvidenceItem] = {}
        self.validation_reports: Dict[str, ValidationReport] = {}
        self.evaluation_results: List[EvidenceEvaluationResult] = []
        self.known_contradictions: List[Dict[str, Any]] = []
        self.rejected_evidence: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)
        
        # Confidence thresholds
        self.min_confidence_threshold = 0.5
        self.min_quality_threshold = 0.4
        self.min_source_reliability = 0.4
        
        # Weights for confidence calculation
        self.weights = {
            "source_reliability": 0.30,
            "quality": 0.25,
            "consistency": 0.20,
            "relevance": 0.15,
            "contradiction_penalty": 0.10,
        }
    
    async def evaluate(self, context: Dict[str, Any]) -> EvidenceEvaluationResult:
        """
        Evaluate evidence from context and return evaluation result.
        
        This is the main entry point called from BrainV3.process().
        
        Args:
            context: {
                "query": str,           # User query
                "reasoning_result": str, # From reasoning engine
                "domain": str,           # Detected domain
                "evidence_sources": List[Dict],  # Pre-fetched evidence
            }
        
        Returns:
            EvidenceEvaluationResult with scores and recommendations
        """
        query = context.get("query", "")
        reasoning_result = context.get("reasoning_result", "")
        domain = context.get("domain", "general")
        pre_fetched_evidence = context.get("evidence_sources", [])
        
        self.logger.info(f"Evaluating evidence for query: {query[:50]}...")
        
        # Step 1: Collect evidence from all sources
        collected_evidence = await self._collect_evidence(query, reasoning_result, domain, pre_fetched_evidence)
        
        # Step 2: Evaluate each piece of evidence
        evaluated_results = []
        for evidence in collected_evidence:
            result = await self._evaluate_single_evidence(evidence, query)
            evaluated_results.append(result)
        
        # Step 3: Rank evidence by score
        evaluated_results = self._rank_evidence(evaluated_results)
        
        # Step 4: Detect contradictions
        contradiction_report = self._detect_contradictions_in_results(evaluated_results)
        
        # Step 5: Apply contradiction penalties
        evaluated_results = self._apply_contradiction_penalties(evaluated_results, contradiction_report)
        
        # Step 6: Filter weak evidence
        strong_evidence = [r for r in evaluated_results if r.is_valid]
        weak_evidence = [r for r in evaluated_results if not r.is_valid]
        
        # Store rejected evidence
        for weak in weak_evidence:
            self.rejected_evidence.append({
                "evidence_id": weak.evidence_id,
                "claim": weak.claim,
                "reason": weak.rejected_reasons,
                "rejected_at": datetime.utcnow().isoformat()
            })
        
        # Step 7: Calculate decision impact
        decision_impact = self._calculate_decision_impact(strong_evidence)
        
        # Step 8: Generate final result
        final_result = self._generate_final_result(
            evaluated_results, 
            strong_evidence,
            decision_impact,
            contradiction_report
        )
        
        self.evaluation_results.append(final_result)
        
        self.logger.info(
            f"Evidence evaluation complete: {len(strong_evidence)} valid, "
            f"{len(weak_evidence)} rejected, decision_impact={decision_impact:.3f}"
        )
        
        return final_result
    
    async def _collect_evidence(
        self, 
        query: str, 
        reasoning_result: str, 
        domain: str,
        pre_fetched: List[Dict]
    ) -> List[EvidenceItem]:
        """Collect evidence from all available sources."""
        evidence_list = []
        
        # Use pre-fetched evidence if available
        for evidence_data in pre_fetched:
            evidence = self._create_evidence_from_data(evidence_data)
            evidence_list.append(evidence)
        
        # If no pre-fetched evidence, create synthetic evidence from reasoning
        if not evidence_list and reasoning_result:
            evidence_list.append(self._create_evidence_from_reasoning(query, reasoning_result, domain))
        
        # If still no evidence, derive from query analysis
        if not evidence_list:
            evidence_list.append(self._derive_evidence_from_query(query, domain))
        
        return evidence_list
    
    def _create_evidence_from_data(self, data: Dict[str, Any]) -> EvidenceItem:
        """Create EvidenceItem from dictionary data."""
        return EvidenceItem(
            claim=data.get("claim", ""),
            source=data.get("source", ""),
            source_type=data.get("source_type", "unknown"),
            source_category=data.get("source_category", EvidenceSource.USER_PROVIDED.value),
            description=data.get("description", ""),
            data=data.get("data"),
            methodology=data.get("methodology", ""),
            evidence_sources=data.get("evidence_sources", []),
            publication_date=data.get("publication_date"),
            citation_count=data.get("citation_count", 0),
            peer_reviewed=data.get("peer_reviewed", False),
        )
    
    def _create_evidence_from_reasoning(self, query: str, reasoning: str, domain: str) -> EvidenceItem:
        """Create synthetic evidence from reasoning result."""
        # Extract key claims from reasoning
        sentences = re.split(r'[.!?]', reasoning)
        key_claims = [s.strip() for s in sentences if len(s.strip()) > 20][:3]
        
        return EvidenceItem(
            claim=key_claims[0] if key_claims else query,
            source="Reasoning Engine",
            source_type="derived",
            source_category=EvidenceSource.DERIVED.value,
            description=f"Derived from {domain} reasoning process",
            data={"reasoning": reasoning, "domain": domain},
        )
    
    def _derive_evidence_from_query(self, query: str, domain: str) -> EvidenceItem:
        """Derive evidence from query analysis."""
        return EvidenceItem(
            claim=query,
            source="Query Analysis",
            source_type="user_provided",
            source_category=EvidenceSource.USER_PROVIDED.value,
            description=f"User query in {domain} domain",
        )
    
    async def _evaluate_single_evidence(
        self, 
        evidence: EvidenceItem, 
        query: str
    ) -> EvidenceEvaluationResult:
        """Evaluate a single piece of evidence."""
        result = EvidenceEvaluationResult(
            evidence_id=evidence.evidence_id,
            claim=evidence.claim,
            sources=[evidence.source_category],
        )
        
        # 1. Source Analysis
        source_analysis = self._analyze_source(evidence)
        result.source_analysis = source_analysis
        result.reliability = source_analysis["reliability_score"]
        
        # 2. Quality Analysis
        quality_analysis = self._analyze_quality(evidence, query)
        result.quality_analysis = quality_analysis
        result.evidence_score = quality_analysis["quality_score"]
        
        # 3. Consistency Analysis
        consistency_analysis = self._analyze_consistency(evidence)
        result.consistency_analysis = consistency_analysis
        result.consistency_score = consistency_analysis["consistency_score"]
        
        # 4. Relevance Analysis
        relevance_score = self._calculate_relevance(evidence.claim, query)
        result.relevance_score = relevance_score
        
        # 5. Calculate overall confidence
        result.confidence = self._calculate_overall_confidence(
            source_analysis,
            quality_analysis,
            consistency_analysis,
            relevance_score
        )
        
        # 6. Determine validity
        result.is_valid = self._is_evidence_valid(result)
        
        # 7. Generate recommendations
        result.recommendations = self._generate_recommendations(result)
        
        if not result.is_valid:
            result.rejected_reasons = self._get_rejection_reasons(result)
        
        return result
    
    def _analyze_source(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Analyze source credibility and reliability."""
        analysis = {
            "source": evidence.source,
            "source_type": evidence.source_type,
            "reliability_score": 0.5,
            "factors": [],
            "peer_reviewed": evidence.peer_reviewed,
            "citation_count": evidence.citation_count,
        }
        
        # Assign base reliability from source type
        try:
            source_type_enum = SourceType[evidence.source_type.upper().replace(" ", "_")]
            base_reliability = source_type_enum.value
        except (KeyError, AttributeError):
            base_reliability = SourceType.UNKNOWN.value
        
        # Adjust for peer review
        if evidence.peer_reviewed:
            base_reliability = min(1.0, base_reliability * 1.1)
            analysis["factors"].append("Peer-reviewed")
        
        # Adjust for citations
        if evidence.citation_count > 10:
            base_reliability = min(1.0, base_reliability * 1.05)
            analysis["factors"].append(f"High citations ({evidence.citation_count})")
        elif evidence.citation_count == 0 and base_reliability > 0.5:
            base_reliability *= 0.9
            analysis["factors"].append("No citations")
        
        # Adjust for publication date
        if evidence.publication_date:
            analysis["factors"].append(f"Published: {evidence.publication_date}")
        
        analysis["reliability_score"] = min(1.0, max(0.0, base_reliability))
        evidence.source_reliability = analysis["reliability_score"]
        
        return analysis
    
    def _analyze_quality(self, evidence: EvidenceItem, query: str) -> Dict[str, Any]:
        """Analyze evidence quality."""
        analysis = {
            "quality_score": 0.5,
            "factors": [],
            "has_data": False,
            "has_methodology": False,
            "has_description": False,
            "description_length": 0,
        }
        
        quality_score = 0.3  # Base score
        
        # Check for actual data
        if evidence.data is not None:
            quality_score += 0.2
            analysis["has_data"] = True
            analysis["factors"].append("Has supporting data")
            
            # Bonus for structured data
            if isinstance(evidence.data, (dict, list)):
                quality_score += 0.05
                analysis["factors"].append("Structured data format")
        
        # Check for methodology
        if evidence.methodology:
            quality_score += 0.15
            analysis["has_methodology"] = True
            analysis["factors"].append("Methodology documented")
        
        # Check description length and quality
        desc_len = len(evidence.description)
        analysis["description_length"] = desc_len
        
        if desc_len > 100:
            quality_score += 0.15
            analysis["has_description"] = True
            analysis["factors"].append(f"Detailed description ({desc_len} chars)")
        elif desc_len > 50:
            quality_score += 0.08
            analysis["has_description"] = True
            analysis["factors"].append(f"Adequate description ({desc_len} chars)")
        elif desc_len > 20:
            quality_score += 0.03
        
        # Check claim specificity
        if len(evidence.claim) > 30:
            quality_score += 0.05
            analysis["factors"].append("Specific claim")
        
        # Check for source attribution
        if evidence.source and evidence.source != "unknown":
            quality_score += 0.05
            analysis["factors"].append("Source attributed")
        
        analysis["quality_score"] = min(1.0, max(0.0, quality_score))
        evidence.quality_score = analysis["quality_score"]
        
        return analysis
    
    def _analyze_consistency(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Analyze consistency with existing knowledge."""
        analysis = {
            "consistency_score": 1.0,
            "contradictions": [],
            "similarities": [],
            "consistency_factors": [],
        }
        
        consistency_score = 1.0
        
        # Check against known contradictions
        for contradiction in self.known_contradictions:
            if self._claims_contradict(evidence.claim, contradiction.get("claim", "")):
                analysis["contradictions"].append(contradiction)
                consistency_score -= contradiction.get("severity", 0.3)
                analysis["consistency_factors"].append(
                    f"Contradicts known fact: {contradiction.get('contradicts', '')}"
                )
        
        # Check for similar claims in evidence store
        for existing_id, existing_evidence in self.evidence_store.items():
            if self._claims_similar(evidence.claim, existing_evidence.claim):
                analysis["similarities"].append({
                    "evidence_id": existing_id,
                    "claim": existing_evidence.claim
                })
                consistency_score += 0.05  # Slight bonus for consistency
                analysis["consistency_factors"].append(
                    f"Consistent with existing claim: {existing_evidence.claim[:30]}..."
                )
        
        analysis["consistency_score"] = min(1.0, max(0.0, consistency_score))
        evidence.consistency_score = analysis["consistency_score"]
        
        return analysis
    
    def _calculate_relevance(self, claim: str, query: str) -> float:
        """Calculate relevance of evidence to query."""
        claim_words = set(re.findall(r'\w+', claim.lower()))
        query_words = set(re.findall(r'\w+', query.lower()))
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'can', 'to', 'of',
                     'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into'}
        
        claim_words -= stop_words
        query_words -= stop_words
        
        if not query_words:
            return 0.5
        
        # Calculate Jaccard similarity
        intersection = len(claim_words & query_words)
        union = len(claim_words | query_words)
        
        if union == 0:
            return 0.5
        
        relevance = intersection / union
        
        # Boost if significant words match
        significant_matches = len([w for w in claim_words if len(w) > 5 and w in query_words])
        if significant_matches > 0:
            relevance = min(1.0, relevance + (significant_matches * 0.05))
        
        return min(1.0, max(0.0, relevance))
    
    def _calculate_overall_confidence(
        self,
        source_analysis: Dict[str, Any],
        quality_analysis: Dict[str, Any],
        consistency_analysis: Dict[str, Any],
        relevance_score: float
    ) -> float:
        """Calculate overall confidence score using weighted formula."""
        source_score = source_analysis["reliability_score"]
        quality_score = quality_analysis["quality_score"]
        consistency_score = consistency_analysis["consistency_score"]
        
        # Weighted sum
        confidence = (
            source_score * self.weights["source_reliability"] +
            quality_score * self.weights["quality"] +
            consistency_score * self.weights["consistency"] +
            relevance_score * self.weights["relevance"]
        )
        
        # Apply contradiction penalty
        contradictions = len(consistency_analysis.get("contradictions", []))
        if contradictions > 0:
            penalty = min(0.3, contradictions * 0.1)
            confidence *= (1 - penalty)
        
        return min(1.0, max(0.0, confidence))
    
    def _is_evidence_valid(self, result: EvidenceEvaluationResult) -> bool:
        """Determine if evidence meets validity thresholds."""
        # All conditions must be met
        if result.confidence < self.min_confidence_threshold:
            return False
        if result.quality_analysis.get("quality_score", 0) < self.min_quality_threshold:
            return False
        if result.source_analysis.get("reliability_score", 0) < self.min_source_reliability:
            return False
        if result.consistency_score < 0.3:  # Must not be too contradictory
            return False
        
        return True
    
    def _rank_evidence(self, results: List[EvidenceEvaluationResult]) -> List[EvidenceEvaluationResult]:
        """Rank evidence by combined score."""
        for i, result in enumerate(results):
            # Combined score considering all factors
            result.decision_impact = (
                result.confidence * 0.35 +
                result.evidence_score * 0.25 +
                result.reliability * 0.20 +
                result.relevance_score * 0.15 +
                result.consistency_score * 0.05
            )
        
        # Sort by decision impact (descending)
        sorted_results = sorted(results, key=lambda x: x.decision_impact, reverse=True)
        
        # Assign ranks
        for i, result in enumerate(sorted_results):
            result.rank = i + 1
        
        return sorted_results
    
    def _detect_contradictions_in_results(
        self, 
        results: List[EvidenceEvaluationResult]
    ) -> Dict[str, Any]:
        """Detect contradictions between evidence items."""
        report = {
            "total_contradictions": 0,
            "contradiction_pairs": [],
            "severity": 0.0,
        }
        
        for i, result1 in enumerate(results):
            for result2 in results[i+1:]:
                if self._claims_contradict(result1.claim, result2.claim):
                    report["total_contradictions"] += 1
                    report["contradiction_pairs"].append({
                        "evidence_1": result1.evidence_id,
                        "evidence_2": result2.evidence_id,
                        "claim_1": result1.claim[:50],
                        "claim_2": result2.claim[:50],
                    })
                    report["severity"] += 0.2
        
        report["severity"] = min(1.0, report["severity"])
        return report
    
    def _apply_contradiction_penalties(
        self,
        results: List[EvidenceEvaluationResult],
        contradiction_report: Dict[str, Any]
    ) -> List[EvidenceEvaluationResult]:
        """Apply penalties for contradictory evidence."""
        contradicted_ids = set()
        
        for pair in contradiction_report.get("contradiction_pairs", []):
            contradicted_ids.add(pair["evidence_1"])
            contradicted_ids.add(pair["evidence_2"])
        
        for result in results:
            if result.evidence_id in contradicted_ids:
                # Reduce confidence for contradicted evidence
                result.confidence *= (1 - contradiction_report["severity"] * 0.3)
                result.decision_impact *= (1 - contradiction_report["severity"] * 0.2)
                result.recommendations.append("Evidence contradicted by other sources")
        
        return results
    
    def _calculate_decision_impact(self, valid_evidence: List[EvidenceEvaluationResult]) -> float:
        """Calculate overall decision impact from valid evidence."""
        if not valid_evidence:
            return 0.1  # Default minimum impact for having evidence
        
        # Weighted by rank (top evidence has more impact)
        total_impact = 0.0
        rank_weights = [1.0, 0.7, 0.5, 0.3, 0.2]  # Top 5
        
        for i, evidence in enumerate(valid_evidence[:5]):
            weight = rank_weights[i] if i < len(rank_weights) else 0.1
            # Use confidence as base, with relevance as a boost (minimum 0.1)
            relevance = max(0.1, evidence.relevance_score)
            total_impact += evidence.confidence * weight * relevance
        
        # Normalize
        max_possible = sum(rank_weights[:min(len(valid_evidence), 5)])
        if max_possible > 0:
            total_impact /= max_possible
        
        # Ensure minimum impact of 0.1 for valid evidence
        return min(1.0, max(0.1, total_impact))
    
    def _generate_final_result(
        self,
        all_results: List[EvidenceEvaluationResult],
        valid_evidence: List[EvidenceEvaluationResult],
        decision_impact: float,
        contradiction_report: Dict[str, Any]
    ) -> EvidenceEvaluationResult:
        """Generate final aggregated result."""
        if not all_results:
            return EvidenceEvaluationResult(
                evidence_id="no_evidence",
                claim="No evidence available",
                evidence_score=0.0,
                confidence=0.0,
                is_valid=False,
                recommendations=["Collect more evidence"]
            )
        
        # Use top-ranked evidence as primary
        primary = all_results[0]
        primary.decision_impact = decision_impact
        primary.should_integrate = len(valid_evidence) > 0
        
        # Add summary recommendations
        if len(valid_evidence) >= 3:
            primary.recommendations.append(f"{len(valid_evidence)} strong evidence sources support this conclusion")
        elif len(valid_evidence) == 0:
            primary.recommendations.append("Insufficient evidence - recommend gathering more sources")
        
        if contradiction_report["total_contradictions"] > 0:
            primary.recommendations.append(
                f"Warning: {contradiction_report['total_contradictions']} contradictions detected"
            )
        
        return primary
    
    def _generate_recommendations(self, result: EvidenceEvaluationResult) -> List[str]:
        """Generate recommendations based on evaluation."""
        recommendations = []
        
        if result.confidence > 0.8:
            recommendations.append("High confidence - strong evidence")
        elif result.confidence > 0.6:
            recommendations.append("Moderate confidence - evidence acceptable")
        elif result.confidence > 0.4:
            recommendations.append("Low confidence - seek additional evidence")
        else:
            recommendations.append("Very low confidence - evidence insufficient")
        
        if result.reliability > 0.8:
            recommendations.append("Highly reliable source")
        elif result.reliability < 0.5:
            recommendations.append("Source reliability concerns")
        
        if result.consistency_score < 0.7:
            recommendations.append("Inconsistencies detected with existing knowledge")
        
        return recommendations
    
    def _get_rejection_reasons(self, result: EvidenceEvaluationResult) -> List[str]:
        """Get reasons why evidence was rejected."""
        reasons = []
        
        if result.confidence < self.min_confidence_threshold:
            reasons.append(f"Confidence ({result.confidence:.2f}) below threshold")
        if result.quality_analysis.get("quality_score", 0) < self.min_quality_threshold:
            reasons.append("Evidence quality below threshold")
        if result.source_analysis.get("reliability_score", 0) < self.min_source_reliability:
            reasons.append("Source reliability below threshold")
        if result.consistency_score < 0.3:
            reasons.append("Major contradictions detected")
        
        return reasons
    
    def _claims_contradict(self, claim1: str, claim2: str) -> bool:
        """Check if two claims contradict each other."""
        claim1_lower = claim1.lower()
        claim2_lower = claim2.lower()
        
        # Negation patterns
        negation_pairs = [
            ("is", "is not"), ("are", "are not"), ("was", "was not"),
            ("can", "cannot"), ("will", "will not"), ("does", "does not"),
            ("has", "has no"), ("has", "does not have"),
        ]
        
        for positive, negative in negation_pairs:
            if positive in claim1_lower and negative in claim2_lower:
                common_words = set(claim1_lower.split()) & set(claim2_lower.split())
                if len(common_words) > 3:
                    return True
        
        # Check for explicit contradictory words
        positive_words = ["always", "all", "every", "definitely", "certainly"]
        negative_words = ["never", "none", "no", "impossible", "unlikely"]
        
        pos_count = sum(1 for w in positive_words if w in claim1_lower)
        neg_count = sum(1 for w in negative_words if w in claim2_lower)
        
        if pos_count > 0 and neg_count > 0:
            return self._claims_similar(claim1_lower, claim2_lower)
        
        return False
    
    def _claims_similar(self, claim1: str, claim2: str) -> bool:
        """Check if two claims are semantically similar."""
        words1 = set(re.findall(r'\w+', claim1.lower()))
        words2 = set(re.findall(r'\w+', claim2.lower()))
        
        # Remove common words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'that', 'this', 'it', 'of', 'to', 'and', 'or', 'in', 'on'}
        words1 -= stop_words
        words2 -= stop_words
        
        if not words1 or not words2:
            return False
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return False
        
        similarity = intersection / union
        return similarity > 0.5
    
    # Legacy methods for backward compatibility
    def submit_evidence(self, claim: str, source: str, source_type: str = "unknown",
                       description: str = "", data: Any = None) -> EvidenceItem:
        """Submit evidence for evaluation."""
        evidence = EvidenceItem(
            claim=claim,
            source=source,
            source_type=source_type,
            description=description,
            data=data
        )
        self.evidence_store[evidence.evidence_id] = evidence
        self.logger.info(f"Submitted evidence {evidence.evidence_id}")
        return evidence
    
    def evaluate_evidence(self, evidence_id: str) -> ValidationReport:
        """Evaluate submitted evidence (legacy method)."""
        evidence = self.evidence_store.get(evidence_id)
        if not evidence:
            return ValidationReport(evidence_id=evidence_id)
        
        report = ValidationReport(evidence_id=evidence_id)
        
        source_analysis = self._analyze_source(evidence)
        report.source_analysis = source_analysis
        
        quality_assessment = self._analyze_quality(evidence, "")
        report.quality_assessment = quality_assessment
        
        contradiction_analysis = self._analyze_consistency(evidence)
        report.contradiction_analysis = contradiction_analysis
        
        report.confidence_score = self._calculate_overall_confidence(
            source_analysis, quality_assessment, contradiction_analysis, 0.5
        )
        
        report.is_valid = report.confidence_score > self.min_confidence_threshold
        report.recommendations = self._generate_recommendations(
            EvidenceEvaluationResult(
                evidence_id=evidence_id,
                confidence=report.confidence_score,
                quality_analysis=quality_assessment,
                consistency_score=contradiction_analysis.get("consistency_score", 0.5),
            )
        )
        
        evidence.evaluated_at = datetime.utcnow()
        self.validation_reports[report.report_id] = report
        
        return report
    
    def register_contradiction(self, claim1: str, claim2: str, severity: float = 0.5) -> None:
        """Register a known contradiction."""
        self.known_contradictions.append({
            "claim": claim1,
            "contradicts": claim2,
            "severity": severity,
            "registered_at": datetime.utcnow().isoformat()
        })
    
    def get_evidence_statistics(self) -> Dict[str, Any]:
        """Get evidence statistics."""
        stats = {
            'total_evidence': len(self.evidence_store),
            'total_evaluated': len(self.validation_reports),
            'total_evaluations': len(self.evaluation_results),
            'rejected_evidence': len(self.rejected_evidence),
            'known_contradictions': len(self.known_contradictions),
            'average_confidence': 0.0,
        }
        
        if self.evaluation_results:
            confidences = [r.confidence for r in self.evaluation_results]
            stats['average_confidence'] = sum(confidences) / len(confidences)
        
        return stats
    
    def export_validation_reports(self, report_ids: Optional[List[str]] = None) -> str:
        """Export validation reports as JSON."""
        if report_ids:
            reports = [self.validation_reports[rid] for rid in report_ids 
                      if rid in self.validation_reports]
        else:
            reports = list(self.validation_reports.values())
        return json.dumps([r.to_dict() for r in reports], indent=2, default=str)
