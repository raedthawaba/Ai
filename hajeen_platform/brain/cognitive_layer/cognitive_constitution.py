"""
Cognitive Constitution - Ethical guidelines and governance rules.

The Cognitive Constitution defines the ethical principles, values, and governance
rules that guide the system's behavior and decision-making.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PrincipleCategory(Enum):
    """Enumeration of principle categories."""
    ETHICS = "ethics"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    SAFETY = "safety"
    FAIRNESS = "fairness"
    PRIVACY = "privacy"


@dataclass
class Principle:
    """
    Represents a principle in the cognitive constitution.
    """
    principle_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = PrincipleCategory.ETHICS.value
    
    # Principle Details
    title: str = ""
    description: str = ""
    rationale: str = ""
    
    # Guidelines
    guidelines: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    
    # Enforcement
    enforcement_level: str = "strict"  # strict, moderate, advisory
    violation_consequence: str = ""
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_reviewed: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['last_reviewed'] = self.last_reviewed.isoformat()
        return data


@dataclass
class GovernanceRule:
    """
    Represents a governance rule.
    """
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Rule Details
    title: str = ""
    description: str = ""
    
    # Scope
    applicable_domains: List[str] = field(default_factory=list)
    applicable_scenarios: List[str] = field(default_factory=list)
    
    # Requirements
    requirements: List[str] = field(default_factory=list)
    prohibitions: List[str] = field(default_factory=list)
    
    # Monitoring
    monitoring_enabled: bool = True
    violation_threshold: float = 0.5
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    effective_date: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        data['effective_date'] = self.effective_date.isoformat()
        return data


@dataclass
class ConstitutionalViolation:
    """
    Records a violation of the constitution.
    """
    violation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Violation Details
    principle_id: Optional[str] = None
    rule_id: Optional[str] = None
    
    # Context
    description: str = ""
    severity: float = 0.5  # 0.0 to 1.0
    
    # Action
    action_taken: str = ""
    resolution: str = ""
    
    # Timeline
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['detected_at'] = self.detected_at.isoformat()
        if data['resolved_at']:
            data['resolved_at'] = self.resolved_at.isoformat()
        return data


class CognitiveConstitution:
    """
    Defines ethical principles and governance rules for the cognitive system.
    
    The Cognitive Constitution ensures that the system operates within ethical
    boundaries and maintains accountability for its actions.
    """
    
    def __init__(self):
        """Initialize the Cognitive Constitution."""
        self.principles: Dict[str, Principle] = {}
        self.principles_by_category: Dict[str, List[str]] = {}  # category -> [principle_ids]
        self.governance_rules: Dict[str, GovernanceRule] = {}
        self.violations: Dict[str, ConstitutionalViolation] = {}
        self.logger = logging.getLogger(__name__)
        
        # Initialize default principles
        self._initialize_default_principles()
    
    def _initialize_default_principles(self) -> None:
        """Initialize default constitutional principles."""
        default_principles = [
            {
                'category': PrincipleCategory.ETHICS.value,
                'title': 'Respect for Autonomy',
                'description': 'Respect the autonomy and agency of all stakeholders',
                'guidelines': [
                    'Do not override user decisions without consent',
                    'Provide transparent information for decision-making',
                    'Allow users to understand and challenge decisions'
                ]
            },
            {
                'category': PrincipleCategory.TRANSPARENCY.value,
                'title': 'Transparency in Operations',
                'description': 'Operate transparently and explain decisions',
                'guidelines': [
                    'Document all significant decisions',
                    'Provide explanations for recommendations',
                    'Disclose limitations and uncertainties'
                ]
            },
            {
                'category': PrincipleCategory.SAFETY.value,
                'title': 'Safety and Security',
                'description': 'Prioritize safety and security in all operations',
                'guidelines': [
                    'Implement robust error handling',
                    'Protect sensitive data',
                    'Prevent harmful outcomes'
                ]
            },
            {
                'category': PrincipleCategory.FAIRNESS.value,
                'title': 'Fairness and Non-Discrimination',
                'description': 'Treat all stakeholders fairly and avoid discrimination',
                'guidelines': [
                    'Avoid biased decision-making',
                    'Ensure equal treatment',
                    'Monitor for discriminatory outcomes'
                ]
            },
            {
                'category': PrincipleCategory.PRIVACY.value,
                'title': 'Privacy Protection',
                'description': 'Protect privacy and personal information',
                'guidelines': [
                    'Minimize data collection',
                    'Secure personal information',
                    'Respect user privacy preferences'
                ]
            }
        ]
        
        for principle_data in default_principles:
            self.add_principle(
                category=principle_data['category'],
                title=principle_data['title'],
                description=principle_data['description'],
                guidelines=principle_data['guidelines']
            )
    
    def add_principle(self, category: str, title: str, description: str,
                     guidelines: Optional[List[str]] = None) -> Principle:
        """
        Add a principle to the constitution.
        
        Args:
            category: Category of the principle
            title: Title of the principle
            description: Description of the principle
            guidelines: Optional list of guidelines
            
        Returns:
            The added Principle
        """
        principle = Principle(
            category=category,
            title=title,
            description=description,
            guidelines=guidelines or []
        )
        
        self.principles[principle.principle_id] = principle
        
        # Index by category
        if category not in self.principles_by_category:
            self.principles_by_category[category] = []
        self.principles_by_category[category].append(principle.principle_id)
        
        self.logger.info(f"Added principle: {title}")
        return principle
    
    def get_principle(self, principle_id: str) -> Optional[Principle]:
        """
        Retrieve a principle by ID.
        
        Args:
            principle_id: The ID of the principle
            
        Returns:
            The Principle, or None if not found
        """
        return self.principles.get(principle_id)
    
    def get_principles_by_category(self, category: str) -> List[Principle]:
        """
        Get all principles in a category.
        
        Args:
            category: The category
            
        Returns:
            List of Principle objects
        """
        principle_ids = self.principles_by_category.get(category, [])
        return [self.principles[pid] for pid in principle_ids if pid in self.principles]
    
    def add_governance_rule(self, title: str, description: str,
                           requirements: Optional[List[str]] = None) -> GovernanceRule:
        """
        Add a governance rule.
        
        Args:
            title: Title of the rule
            description: Description of the rule
            requirements: Optional list of requirements
            
        Returns:
            The added GovernanceRule
        """
        rule = GovernanceRule(
            title=title,
            description=description,
            requirements=requirements or []
        )
        
        self.governance_rules[rule.rule_id] = rule
        
        self.logger.info(f"Added governance rule: {title}")
        return rule
    
    def get_governance_rule(self, rule_id: str) -> Optional[GovernanceRule]:
        """
        Retrieve a governance rule by ID.
        
        Args:
            rule_id: The ID of the rule
            
        Returns:
            The GovernanceRule, or None if not found
        """
        return self.governance_rules.get(rule_id)
    
    def check_action_compliance(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if an action complies with the constitution.
        
        Args:
            action: The action to check
            context: Context of the action
            
        Returns:
            Compliance check result
        """
        result = {
            'action': action,
            'compliant': True,
            'violations': [],
            'warnings': [],
            'recommendations': []
        }
        
        # Check against principles
        for principle in self.principles.values():
            if self._violates_principle(action, principle, context):
                result['compliant'] = False
                result['violations'].append(f"Violates principle: {principle.title}")
        
        # Check against governance rules
        for rule in self.governance_rules.values():
            if self._violates_rule(action, rule, context):
                result['compliant'] = False
                result['violations'].append(f"Violates rule: {rule.title}")
        
        return result
    
    def _violates_principle(self, action: str, principle: Principle, context: Dict[str, Any]) -> bool:
        """Check if an action violates a principle."""
        # Simulate principle checking
        return False
    
    def _violates_rule(self, action: str, rule: GovernanceRule, context: Dict[str, Any]) -> bool:
        """Check if an action violates a rule."""
        # Simulate rule checking
        return False
    
    def record_violation(self, principle_id: Optional[str] = None,
                        rule_id: Optional[str] = None,
                        description: str = "",
                        severity: float = 0.5) -> ConstitutionalViolation:
        """
        Record a constitutional violation.
        
        Args:
            principle_id: Optional ID of violated principle
            rule_id: Optional ID of violated rule
            description: Description of the violation
            severity: Severity of the violation
            
        Returns:
            The recorded ConstitutionalViolation
        """
        violation = ConstitutionalViolation(
            principle_id=principle_id,
            rule_id=rule_id,
            description=description,
            severity=severity
        )
        
        self.violations[violation.violation_id] = violation
        
        self.logger.warning(f"Recorded constitutional violation: {description}")
        return violation
    
    def resolve_violation(self, violation_id: str, resolution: str) -> bool:
        """
        Resolve a constitutional violation.
        
        Args:
            violation_id: The ID of the violation
            resolution: Description of the resolution
            
        Returns:
            True if successful, False otherwise
        """
        violation = self.violations.get(violation_id)
        if not violation:
            return False
        
        violation.resolution = resolution
        violation.resolved_at = datetime.utcnow()
        
        self.logger.info(f"Resolved constitutional violation: {violation_id}")
        return True
    
    def get_constitution_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the constitution.
        
        Returns:
            Dictionary containing constitution statistics
        """
        stats = {
            'total_principles': len(self.principles),
            'principles_by_category': {},
            'total_governance_rules': len(self.governance_rules),
            'total_violations': len(self.violations),
            'unresolved_violations': 0,
            'average_violation_severity': 0.0
        }
        
        # Count by category
        for category in self.principles_by_category:
            stats['principles_by_category'][category] = len(self.principles_by_category[category])
        
        # Count unresolved violations
        unresolved = [v for v in self.violations.values() if v.resolved_at is None]
        stats['unresolved_violations'] = len(unresolved)
        
        # Calculate average severity
        if self.violations:
            severities = [v.severity for v in self.violations.values()]
            stats['average_violation_severity'] = sum(severities) / len(severities)
        
        return stats
    
    def export_constitution(self) -> str:
        """
        Export the constitution as JSON.
        
        Returns:
            JSON string containing the constitution
        """
        data = {
            'principles': [p.to_dict() for p in self.principles.values()],
            'governance_rules': [r.to_dict() for r in self.governance_rules.values()],
            'violations': [v.to_dict() for v in self.violations.values()]
        }
        
        return json.dumps(data, indent=2, default=str)
