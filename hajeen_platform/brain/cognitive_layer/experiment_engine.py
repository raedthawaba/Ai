"""
Experiment Engine - Design, execution, and analysis of experiments.

The Experiment Engine designs and executes experiments to test hypotheses,
validate theories, and gather evidence for knowledge refinement.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    """Enumeration of experiment statuses."""
    DESIGNED = "designed"
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    ANALYZED = "analyzed"
    FAILED = "failed"


class ExperimentType(Enum):
    """Enumeration of experiment types."""
    HYPOTHESIS_TEST = "hypothesis_test"
    THEORY_VALIDATION = "theory_validation"
    PARAMETER_OPTIMIZATION = "parameter_optimization"
    EDGE_CASE_EXPLORATION = "edge_case_exploration"
    COMPARATIVE_ANALYSIS = "comparative_analysis"


@dataclass
class ExperimentDesign:
    """
    Represents the design of an experiment.
    """
    design_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experiment_type: str = ExperimentType.HYPOTHESIS_TEST.value
    
    # Objectives
    hypothesis: str = ""
    research_question: str = ""
    objectives: List[str] = field(default_factory=list)
    
    # Variables
    independent_variables: List[Dict[str, Any]] = field(default_factory=list)
    dependent_variables: List[Dict[str, Any]] = field(default_factory=list)
    control_variables: List[Dict[str, Any]] = field(default_factory=list)
    
    # Methods
    methodology: str = ""
    sample_size: int = 0
    duration: float = 0.0  # hours
    
    # Success Criteria
    success_criteria: List[str] = field(default_factory=list)
    expected_outcomes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)


@dataclass
class Experiment:
    """
    Represents an experiment with its execution and results.
    """
    experiment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    design_id: str = ""
    
    # Experiment Details
    name: str = ""
    description: str = ""
    status: str = ExperimentStatus.DESIGNED.value
    
    # Execution
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: float = 0.0  # seconds
    
    # Data
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)
    
    # Results
    results: Dict[str, Any] = field(default_factory=dict)
    success: bool = False
    confidence: float = 0.5
    
    # Analysis
    analysis: Dict[str, Any] = field(default_factory=dict)
    conclusions: List[str] = field(default_factory=list)
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['start_time']:
            data['start_time'] = self.start_time.isoformat()
        if data['end_time']:
            data['end_time'] = self.end_time.isoformat()
        return data


class ExperimentEngine:
    """
    Designs and executes experiments to test hypotheses and validate theories.
    
    The Experiment Engine enables systematic testing of hypotheses through
    carefully designed experiments, providing a rigorous approach to knowledge
    refinement and theory validation.
    """
    
    def __init__(self):
        """Initialize the Experiment Engine."""
        self.designs: Dict[str, ExperimentDesign] = {}
        self.experiments: Dict[str, Experiment] = {}
        self.experiments_by_design: Dict[str, List[str]] = {}  # design_id -> [experiment_ids]
        self.logger = logging.getLogger(__name__)
    
    def design_experiment(self, hypothesis: str, experiment_type: str = ExperimentType.HYPOTHESIS_TEST.value,
                         objectives: Optional[List[str]] = None) -> ExperimentDesign:
        """
        Design a new experiment.
        
        Args:
            hypothesis: The hypothesis to test
            experiment_type: Type of experiment
            objectives: Optional list of objectives
            
        Returns:
            The created ExperimentDesign
        """
        design = ExperimentDesign(
            experiment_type=experiment_type,
            hypothesis=hypothesis,
            objectives=objectives or []
        )
        
        self.designs[design.design_id] = design
        self.logger.info(f"Designed experiment for hypothesis: {hypothesis}")
        return design
    
    def add_independent_variable(self, design_id: str, variable_name: str,
                                 values: List[Any], description: str = "") -> bool:
        """
        Add an independent variable to an experiment design.
        
        Args:
            design_id: The ID of the design
            variable_name: Name of the variable
            values: Possible values for the variable
            description: Description of the variable
            
        Returns:
            True if successful, False otherwise
        """
        design = self.designs.get(design_id)
        if not design:
            return False
        
        variable = {
            'name': variable_name,
            'values': values,
            'description': description
        }
        
        design.independent_variables.append(variable)
        return True
    
    def add_dependent_variable(self, design_id: str, variable_name: str,
                              measurement_type: str = "numeric", description: str = "") -> bool:
        """
        Add a dependent variable to an experiment design.
        
        Args:
            design_id: The ID of the design
            variable_name: Name of the variable
            measurement_type: Type of measurement
            description: Description of the variable
            
        Returns:
            True if successful, False otherwise
        """
        design = self.designs.get(design_id)
        if not design:
            return False
        
        variable = {
            'name': variable_name,
            'measurement_type': measurement_type,
            'description': description
        }
        
        design.dependent_variables.append(variable)
        return True
    
    def add_control_variable(self, design_id: str, variable_name: str,
                            fixed_value: Any, description: str = "") -> bool:
        """
        Add a control variable to an experiment design.
        
        Args:
            design_id: The ID of the design
            variable_name: Name of the variable
            fixed_value: Fixed value for the variable
            description: Description of the variable
            
        Returns:
            True if successful, False otherwise
        """
        design = self.designs.get(design_id)
        if not design:
            return False
        
        variable = {
            'name': variable_name,
            'fixed_value': fixed_value,
            'description': description
        }
        
        design.control_variables.append(variable)
        return True
    
    def set_success_criteria(self, design_id: str, criteria: List[str]) -> bool:
        """
        Set success criteria for an experiment design.
        
        Args:
            design_id: The ID of the design
            criteria: List of success criteria
            
        Returns:
            True if successful, False otherwise
        """
        design = self.designs.get(design_id)
        if not design:
            return False
        
        design.success_criteria = criteria
        return True
    
    def create_experiment(self, design_id: str, name: str, description: str = "") -> Experiment:
        """
        Create an experiment from a design.
        
        Args:
            design_id: The ID of the design
            name: Name of the experiment
            description: Description of the experiment
            
        Returns:
            The created Experiment
        """
        design = self.designs.get(design_id)
        if not design:
            self.logger.error(f"Design {design_id} not found")
            return None
        
        experiment = Experiment(
            design_id=design_id,
            name=name,
            description=description,
            status=ExperimentStatus.PLANNED.value
        )
        
        self.experiments[experiment.experiment_id] = experiment
        
        # Index by design
        if design_id not in self.experiments_by_design:
            self.experiments_by_design[design_id] = []
        self.experiments_by_design[design_id].append(experiment.experiment_id)
        
        self.logger.info(f"Created experiment {name} from design {design_id}")
        return experiment
    
    def run_experiment(self, experiment_id: str, input_data: Dict[str, Any]) -> bool:
        """
        Run an experiment.
        
        Args:
            experiment_id: The ID of the experiment
            input_data: Input data for the experiment
            
        Returns:
            True if successful, False otherwise
        """
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return False
        
        experiment.status = ExperimentStatus.RUNNING.value
        experiment.start_time = datetime.utcnow()
        experiment.input_data = input_data
        
        # Simulate experiment execution
        self._execute_experiment(experiment)
        
        experiment.end_time = datetime.utcnow()
        experiment.duration = (experiment.end_time - experiment.start_time).total_seconds()
        experiment.status = ExperimentStatus.COMPLETED.value
        
        self.logger.info(f"Completed experiment {experiment.name}")
        return True
    
    def _execute_experiment(self, experiment: Experiment) -> None:
        """Execute the experiment (simulation)."""
        # Simulate experiment execution
        experiment.output_data = {
            'measurement_1': 42,
            'measurement_2': 3.14,
            'measurement_3': 'success'
        }
        
        experiment.observations = [
            "Observation 1: System behaved as expected",
            "Observation 2: No anomalies detected",
            "Observation 3: Results consistent with hypothesis"
        ]
        
        experiment.success = True
        experiment.confidence = 0.85
    
    def analyze_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """
        Analyze the results of an experiment.
        
        Args:
            experiment_id: The ID of the experiment
            
        Returns:
            Analysis results
        """
        experiment = self.experiments.get(experiment_id)
        if not experiment:
            return {}
        
        # Perform analysis
        analysis = {
            'analysis_id': str(uuid.uuid4()),
            'experiment_id': experiment_id,
            'status': experiment.status,
            'success': experiment.success,
            'confidence': experiment.confidence,
            'observations_count': len(experiment.observations),
            'key_findings': self._extract_key_findings(experiment),
            'statistical_summary': self._calculate_statistics(experiment),
            'hypothesis_validation': self._validate_hypothesis(experiment)
        }
        
        experiment.analysis = analysis
        experiment.status = ExperimentStatus.ANALYZED.value
        
        # Generate conclusions
        experiment.conclusions = self._generate_conclusions(experiment, analysis)
        
        self.logger.info(f"Analyzed experiment {experiment.name}")
        return analysis
    
    def _extract_key_findings(self, experiment: Experiment) -> List[str]:
        """Extract key findings from experiment."""
        findings = []
        
        if experiment.success:
            findings.append("Experiment was successful")
        
        if experiment.confidence > 0.8:
            findings.append("High confidence in results")
        
        if experiment.observations:
            findings.append(f"Recorded {len(experiment.observations)} observations")
        
        return findings
    
    def _calculate_statistics(self, experiment: Experiment) -> Dict[str, Any]:
        """Calculate statistical summary."""
        return {
            'total_observations': len(experiment.observations),
            'success_rate': 1.0 if experiment.success else 0.0,
            'confidence_level': experiment.confidence,
            'duration_seconds': experiment.duration
        }
    
    def _validate_hypothesis(self, experiment: Experiment) -> Dict[str, Any]:
        """Validate hypothesis based on results."""
        design = self.designs.get(experiment.design_id)
        if not design:
            return {}
        
        return {
            'hypothesis': design.hypothesis,
            'supported': experiment.success,
            'confidence': experiment.confidence,
            'evidence_strength': 'strong' if experiment.confidence > 0.8 else 'moderate'
        }
    
    def _generate_conclusions(self, experiment: Experiment, analysis: Dict[str, Any]) -> List[str]:
        """Generate conclusions from analysis."""
        conclusions = []
        
        if analysis.get('hypothesis_validation', {}).get('supported'):
            conclusions.append("Hypothesis is supported by experimental evidence")
        else:
            conclusions.append("Hypothesis requires further investigation")
        
        if analysis.get('confidence_level', 0) > 0.8:
            conclusions.append("Results are reliable and reproducible")
        
        conclusions.append("Experiment provides valuable insights for knowledge refinement")
        
        return conclusions
    
    def get_experiment_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about experiments.
        
        Returns:
            Dictionary containing experiment statistics
        """
        stats = {
            'total_designs': len(self.designs),
            'total_experiments': len(self.experiments),
            'completed_experiments': 0,
            'successful_experiments': 0,
            'average_confidence': 0.0,
            'average_duration': 0.0
        }
        
        if not self.experiments:
            return stats
        
        completed = [e for e in self.experiments.values() if e.status == ExperimentStatus.COMPLETED.value]
        stats['completed_experiments'] = len(completed)
        stats['successful_experiments'] = sum(1 for e in completed if e.success)
        
        if completed:
            confidences = [e.confidence for e in completed]
            durations = [e.duration for e in completed]
            stats['average_confidence'] = sum(confidences) / len(confidences)
            stats['average_duration'] = sum(durations) / len(durations)
        
        return stats
    
    def export_experiments(self, experiment_ids: Optional[List[str]] = None) -> str:
        """
        Export experiments as JSON.
        
        Args:
            experiment_ids: Optional list of specific experiment IDs to export
            
        Returns:
            JSON string containing the experiments
        """
        if experiment_ids:
            experiments = [self.experiments[eid] for eid in experiment_ids if eid in self.experiments]
        else:
            experiments = list(self.experiments.values())
        
        return json.dumps([e.to_dict() for e in experiments], indent=2, default=str)
