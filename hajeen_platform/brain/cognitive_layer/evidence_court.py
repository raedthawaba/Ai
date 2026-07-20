"""
Evidence Court - Rigorous evaluation and validation of information.

The Evidence Court acts as a gatekeeper for new information, rigorously evaluating
its credibility and consistency before it is integrated into the system's long-term
knowledge base.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Enumeration of information source types."""
    ACADEMIC = 0.9
    SCIENTIFIC_STUDY = 0.85
    EXPERT_OPINION = 0.8
    NEWS_OUTLET = 0.6
    SOCIAL_MEDIA = 0.3
    UNKNOWN = 0.5


class EvidenceQuality(Enum):
    """Enumeration of evidence quality levels."""
    EXCELLENT = 0.95
    GOOD = 0.8
    FAIR = 0.6
    POOR = 0.3
    UNRELIABLE = 0.1


@dataclass
class EvidenceItem:
    """
    Represents a piece of evidence for evaluation.
    """
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    claim: str = ""
    source: str = ""
    source_type: str = "unknown"
    
    # Evidence Details
    description: str = ""
    data: Any = None
    methodology: str = ""
    
    # Evaluation
    quality_score: float = 0.5
    credibility_score: float = 0.5
    relevance_score: float = 0.5
    
    # Metadata
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    evaluated_at: Optional[datetime] = None
    evaluation_notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['submitted_at'] = self.submitted_at.isoformat()
        if data['evaluated_at']:
            data['evaluated_at'] = self.evaluated_at.isoformat()
        return data


@dataclass
class ValidationReport:
    """
    Report of evidence validation.
    """
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


class EvidenceCourt:
    """
    Rigorous evaluation and validation of information before integration into knowledge.
    
    The Evidence Court ensures that only high-quality, credible, and consistent
    information is integrated into the system's long-term knowledge base.
    """
    
    def __init__(self):
        """Initialize the Evidence Court."""
        self.evidence_store: Dict[str, EvidenceItem] = {}
        self.validation_reports: Dict[str, ValidationReport] = {}
        self.known_contradictions: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)
    
    def submit_evidence(self, claim: str, source: str, source_type: str = "unknown",
                       description: str = "", data: Any = None) -> EvidenceItem:
        """
        Submit evidence for evaluation.
        
        Args:
            claim: The claim being made
            source: The source of the evidence
            source_type: The type of source
            description: Description of the evidence
            data: The actual data or evidence
            
        Returns:
            The submitted EvidenceItem
        """
        evidence = EvidenceItem(
            claim=claim,
            source=source,
            source_type=source_type,
            description=description,
            data=data
        )
        
        self.evidence_store[evidence.evidence_id] = evidence
        self.logger.info(f"Submitted evidence {evidence.evidence_id}: {claim}")
        return evidence
    
    def evaluate_evidence(self, evidence_id: str) -> ValidationReport:
        """
        Evaluate submitted evidence.
        
        Args:
            evidence_id: The ID of the evidence to evaluate
            
        Returns:
            A ValidationReport with evaluation results
        """
        evidence = self.evidence_store.get(evidence_id)
        if not evidence:
            self.logger.warning(f"Evidence {evidence_id} not found")
            return ValidationReport(evidence_id=evidence_id)
        
        report = ValidationReport(evidence_id=evidence_id)
        
        # Analyze source
        source_analysis = self._analyze_source(evidence)
        report.source_analysis = source_analysis
        
        # Assess quality
        quality_assessment = self._assess_quality(evidence)
        report.quality_assessment = quality_assessment
        
        # Check for contradictions
        contradiction_analysis = self._check_contradictions(evidence)
        report.contradiction_analysis = contradiction_analysis
        
        # Calculate overall confidence
        report.confidence_score = self._calculate_confidence(
            source_analysis,
            quality_assessment,
            contradiction_analysis
        )
        
        # Determine validity
        report.is_valid = report.confidence_score > 0.6
        
        # Generate recommendations
        report.recommendations = self._generate_recommendations(report)
        
        # Mark evidence as evaluated
        evidence.evaluated_at = datetime.utcnow()
        evidence.evaluation_notes = f"Evaluated with confidence {report.confidence_score}"
        
        self.validation_reports[report.report_id] = report
        self.logger.info(f"Evaluated evidence {evidence_id} with confidence {report.confidence_score}")
        
        return report
    
    def _analyze_source(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Analyze the credibility of the evidence source."""
        analysis = {
            'source': evidence.source,
            'source_type': evidence.source_type,
            'credibility_score': 0.5
        }
        
        # Assign credibility based on source type
        try:
            source_enum = SourceType[evidence.source_type.upper()]
            analysis['credibility_score'] = source_enum.value
        except KeyError:
            analysis['credibility_score'] = SourceType.UNKNOWN.value
        
        # Additional checks
        if len(evidence.source) > 5:
            analysis['has_detailed_source'] = True
        
        return analysis
    
    def _assess_quality(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Assess the quality of the evidence."""
        assessment = {
            'quality_score': 0.5,
            'factors': []
        }
        
        quality_score = 0.5
        
        # Check if methodology is provided
        if evidence.methodology:
            quality_score += 0.2
            assessment['factors'].append('Methodology provided')
        
        # Check if data is provided
        if evidence.data is not None:
            quality_score += 0.15
            assessment['factors'].append('Data provided')
        
        # Check description length
        if len(evidence.description) > 50:
            quality_score += 0.15
            assessment['factors'].append('Detailed description')
        
        assessment['quality_score'] = min(1.0, quality_score)
        return assessment
    
    def _check_contradictions(self, evidence: EvidenceItem) -> Dict[str, Any]:
        """Check for contradictions with existing knowledge."""
        analysis = {
            'contradictions_found': False,
            'contradicting_claims': [],
            'contradiction_severity': 0.0
        }
        
        # Check against known contradictions
        for known_contradiction in self.known_contradictions:
            if self._claims_contradict(evidence.claim, known_contradiction['claim']):
                analysis['contradictions_found'] = True
                analysis['contradicting_claims'].append(known_contradiction['claim'])
                analysis['contradiction_severity'] += 0.1
        
        analysis['contradiction_severity'] = min(1.0, analysis['contradiction_severity'])
        return analysis
    
    def _claims_contradict(self, claim1: str, claim2: str) -> bool:
        """Check if two claims contradict each other."""
        # Simple contradiction check (can be enhanced with NLP)
        contradiction_words = ['not', 'never', 'always', 'impossible', 'false']
        
        claim1_lower = claim1.lower()
        claim2_lower = claim2.lower()
        
        # Check for explicit negation
        if any(word in claim1_lower for word in contradiction_words):
            if any(word in claim2_lower for word in contradiction_words):
                return False
            # Check if the non-negated parts are similar
            return self._claims_similar(claim1_lower, claim2_lower)
        
        return False
    
    def _claims_similar(self, claim1: str, claim2: str) -> bool:
        """Check if two claims are similar."""
        # Simple similarity check (can be enhanced with semantic analysis)
        words1 = set(claim1.split())
        words2 = set(claim2.split())
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return False
        
        similarity = intersection / union
        return similarity > 0.6
    
    def _calculate_confidence(self, source_analysis: Dict[str, Any],
                             quality_assessment: Dict[str, Any],
                             contradiction_analysis: Dict[str, Any]) -> float:
        """Calculate overall confidence score."""
        source_credibility = source_analysis.get('credibility_score', 0.5)
        quality_score = quality_assessment.get('quality_score', 0.5)
        contradiction_severity = contradiction_analysis.get('contradiction_severity', 0.0)
        
        # Weighted average
        confidence = (source_credibility * 0.4 + quality_score * 0.4) * (1 - contradiction_severity * 0.2)
        
        return max(0.0, min(1.0, confidence))
    
    def _generate_recommendations(self, report: ValidationReport) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []
        
        if report.confidence_score < 0.5:
            recommendations.append("Request additional evidence before integration")
        
        if report.contradiction_analysis.get('contradictions_found'):
            recommendations.append("Investigate contradictions with existing knowledge")
        
        if report.source_analysis.get('credibility_score', 0.5) < 0.6:
            recommendations.append("Verify source credibility")
        
        if report.quality_assessment.get('quality_score', 0.5) < 0.6:
            recommendations.append("Request more detailed information")
        
        if not recommendations:
            recommendations.append("Evidence is acceptable for integration")
        
        return recommendations
    
    def request_additional_evidence(self, evidence_id: str, required_info: List[str]) -> Dict[str, Any]:
        """
        Request additional evidence for a claim.
        
        Args:
            evidence_id: The ID of the evidence
            required_info: List of required information
            
        Returns:
            A request object
        """
        request = {
            'request_id': str(uuid.uuid4()),
            'evidence_id': evidence_id,
            'required_information': required_info,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'pending'
        }
        
        self.logger.info(f"Requested additional evidence for {evidence_id}")
        return request
    
    def register_contradiction(self, claim1: str, claim2: str, severity: float = 0.5) -> None:
        """
        Register a known contradiction between two claims.
        
        Args:
            claim1: First contradicting claim
            claim2: Second contradicting claim
            severity: Severity of the contradiction (0.0 to 1.0)
        """
        contradiction = {
            'claim': claim1,
            'contradicts': claim2,
            'severity': severity,
            'registered_at': datetime.utcnow().isoformat()
        }
        
        self.known_contradictions.append(contradiction)
        self.logger.info("Registered contradiction between claims")
    
    def get_validation_report(self, report_id: str) -> Optional[ValidationReport]:
        """
        Retrieve a validation report.
        
        Args:
            report_id: The ID of the report
            
        Returns:
            The ValidationReport, or None if not found
        """
        return self.validation_reports.get(report_id)
    
    def get_evidence_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about evaluated evidence.
        
        Returns:
            Dictionary containing evidence statistics
        """
        stats = {
            'total_evidence_submitted': len(self.evidence_store),
            'total_evidence_evaluated': len(self.validation_reports),
            'average_confidence': 0.0,
            'valid_evidence_count': 0,
            'invalid_evidence_count': 0,
            'known_contradictions': len(self.known_contradictions)
        }
        
        if not self.validation_reports:
            return stats
        
        confidence_scores = [report.confidence_score for report in self.validation_reports.values()]
        stats['average_confidence'] = sum(confidence_scores) / len(confidence_scores)
        
        stats['valid_evidence_count'] = sum(1 for report in self.validation_reports.values() if report.is_valid)
        stats['invalid_evidence_count'] = len(self.validation_reports) - stats['valid_evidence_count']
        
        return stats
    
    def export_validation_reports(self, report_ids: Optional[List[str]] = None) -> str:
        """
        Export validation reports as JSON.
        
        Args:
            report_ids: Optional list of specific report IDs to export
            
        Returns:
            JSON string containing the reports
        """
        if report_ids:
            reports = [self.validation_reports[rid] for rid in report_ids if rid in self.validation_reports]
        else:
            reports = list(self.validation_reports.values())
        
        return json.dumps([report.to_dict() for report in reports], indent=2, default=str)
