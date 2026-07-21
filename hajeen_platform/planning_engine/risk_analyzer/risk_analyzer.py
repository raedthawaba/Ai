"""
Risk Analyzer - Planning Engine v1.0
====================================

Analyzes and manages risks in execution plans.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Set

from ..core.base import BaseComponent
from ..core.models import (
    Task, TaskGraph, Risk, RiskLevel, RiskAnalysis
)


class RiskAnalyzer(BaseComponent):
    """
    Analyzes risks in planning.
    
    Responsibilities:
    - Identify potential risks
    - Assess risk probability and impact
    - Generate mitigation strategies
    - Create contingency plans
    """
    
    def __init__(self):
        super().__init__()
        self._risk_patterns: Dict[str, Dict[str, Any]] = {}
    
    async def _async_initialize(self) -> None:
        """Initialize the risk analyzer."""
        self._initialize_risk_patterns()
        self.logger.info("RiskAnalyzer initialized")
    
    def _initialize_risk_patterns(self) -> None:
        """Initialize common risk patterns."""
        self._risk_patterns = {
            "resource_shortage": {
                "keywords": ["limited", "scarce", "resource", "allocation"],
                "probability": 0.3,
                "impact": 0.7
            },
            "task_failure": {
                "keywords": ["complex", "uncertain", "unstable"],
                "probability": 0.2,
                "impact": 0.8
            },
            "dependency_delay": {
                "keywords": ["depends", "following", "after"],
                "probability": 0.25,
                "impact": 0.5
            },
            "timeout": {
                "keywords": ["long", "complex", "loop"],
                "probability": 0.15,
                "impact": 0.6
            },
            "quality_issue": {
                "keywords": ["verify", "check", "validate"],
                "probability": 0.1,
                "impact": 0.4
            }
        }
    
    def analyze(
        self,
        task_graph: TaskGraph,
        context: Optional[Dict[str, Any]] = None
    ) -> RiskAnalysis:
        """
        Analyze risks in a task graph.
        
        Args:
            task_graph: Task graph to analyze
            context: Additional context
            
        Returns:
            RiskAnalysis with identified risks
        """
        analysis = RiskAnalysis()
        context = context or {}
        
        # Identify risks from task analysis
        for task in task_graph.tasks.values():
            risks = self._identify_task_risks(task, context)
            for risk in risks:
                analysis.add_risk(risk)
        
        # Identify systemic risks
        systemic_risks = self._identify_systemic_risks(task_graph)
        for risk in systemic_risks:
            analysis.add_risk(risk)
        
        # Generate mitigation strategies
        for risk in analysis.risks:
            self._generate_mitigation(risk, task_graph)
        
        self.logger.info(f"Analyzed {len(analysis.risks)} risks")
        
        return analysis
    
    def _identify_task_risks(
        self,
        task: Task,
        context: Dict[str, Any]
    ) -> List[Risk]:
        """Identify risks for a specific task."""
        risks = []
        desc_lower = task.description.lower()
        
        # Check against patterns
        for pattern_name, pattern in self._risk_patterns.items():
            if any(kw in desc_lower for kw in pattern["keywords"]):
                risk = Risk(
                    risk_id=str(uuid.uuid4()),
                    title=f"{pattern_name.replace('_', ' ').title()} Risk",
                    description=f"Potential {pattern_name} for task: {task.title}",
                    level=self._calculate_risk_level(
                        pattern["probability"],
                        pattern["impact"]
                    ),
                    probability=pattern["probability"],
                    impact=pattern["impact"],
                    affected_tasks=[task.task_id]
                )
                risks.append(risk)
        
        # High duration risk
        if task.estimated_duration > 3600:  # > 1 hour
            risks.append(Risk(
                risk_id=str(uuid.uuid4()),
                title="Long Duration Risk",
                description=f"Task {task.title} has long estimated duration",
                level=RiskLevel.MEDIUM,
                probability=0.2,
                impact=0.6,
                affected_tasks=[task.task_id]
            ))
        
        # Many dependencies risk
        if len(task.dependencies) > 5:
            risks.append(Risk(
                risk_id=str(uuid.uuid4()),
                title="Dependency Complexity Risk",
                description=f"Task {task.title} has many dependencies",
                level=RiskLevel.MEDIUM,
                probability=0.25,
                impact=0.5,
                affected_tasks=[task.task_id]
            ))
        
        return risks
    
    def _identify_systemic_risks(
        self,
        task_graph: TaskGraph
    ) -> List[Risk]:
        """Identify systemic risks across the task graph."""
        risks = []
        
        # Critical path concentration
        if len(task_graph.tasks) > 10:
            risks.append(Risk(
                risk_id=str(uuid.uuid4()),
                title="Critical Path Concentration",
                description="Many tasks depend on single critical path",
                level=RiskLevel.HIGH,
                probability=0.3,
                impact=0.7
            ))
        
        # Resource contention
        total_resources_needed = sum(
            len(t.required_resources) for t in task_graph.tasks.values()
        )
        
        if total_resources_needed > len(task_graph.tasks) * 2:
            risks.append(Risk(
                risk_id=str(uuid.uuid4()),
                title="Resource Contention Risk",
                description="High resource requirements may cause contention",
                level=RiskLevel.MEDIUM,
                probability=0.35,
                impact=0.5
            ))
        
        return risks
    
    def _calculate_risk_level(
        self,
        probability: float,
        impact: float
    ) -> RiskLevel:
        """Calculate risk level from probability and impact."""
        score = probability * impact
        
        if score >= 0.5:
            return RiskLevel.CRITICAL
        elif score >= 0.3:
            return RiskLevel.HIGH
        elif score >= 0.15:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _generate_mitigation(self, risk: Risk, task_graph: TaskGraph) -> None:
        """Generate mitigation strategy for a risk."""
        # Common mitigation strategies
        strategies = {
            RiskLevel.CRITICAL: "Immediate action required. Create fallback plan.",
            RiskLevel.HIGH: "Active monitoring and contingency planning needed.",
            RiskLevel.MEDIUM: "Regular monitoring and proactive measures.",
            RiskLevel.LOW: "Standard monitoring sufficient."
        }
        
        risk.mitigation_strategy = strategies.get(risk.level, "")
        
        # Generate contingency plan
        if risk.level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            risk.contingency_plan = (
                f"If risk materializes: Skip affected task(s) and "
                f"continue with remaining tasks. "
                f"Log issue for manual review."
            )
            
            # Suggest fallback task
            if risk.affected_tasks:
                for task_id in risk.affected_tasks:
                    task = task_graph.tasks.get(task_id)
                    if task and task.dependents:
                        risk.fallback_task_id = task.dependents[0]
    
    def assess_risk_score(self, risk_analysis: RiskAnalysis) -> float:
        """Calculate overall risk score."""
        if not risk_analysis.risks:
            return 0.0
        
        total_score = sum(
            r.probability * r.impact for r in risk_analysis.risks
        )
        
        # Weight by risk level
        weighted_score = 0.0
        for r in risk_analysis.risks:
            weight = {
                RiskLevel.CRITICAL: 1.5,
                RiskLevel.HIGH: 1.2,
                RiskLevel.MEDIUM: 1.0,
                RiskLevel.LOW: 0.8
            }.get(r.level, 1.0)
            
            weighted_score += r.probability * r.impact * weight
        
        return min(1.0, weighted_score)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get risk analyzer statistics."""
        return {
            "patterns_available": len(self._risk_patterns)
        }


_risk_analyzer_instance: Optional[RiskAnalyzer] = None


def get_risk_analyzer() -> RiskAnalyzer:
    """Get singleton instance."""
    global _risk_analyzer_instance
    if _risk_analyzer_instance is None:
        _risk_analyzer_instance = RiskAnalyzer()
    return _risk_analyzer_instance
