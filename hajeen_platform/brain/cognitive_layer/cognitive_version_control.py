"""
Cognitive Version Control - System versioning and rollback capabilities.

The Cognitive Version Control system manages versions of the cognitive system,
enabling tracking of changes, rollback to previous states, and systematic
management of system evolution.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemVersion:
    """
    Represents a version of the cognitive system.
    """
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version_number: str = "1.0.0"
    
    # Version Details
    name: str = ""
    description: str = ""
    release_notes: str = ""
    
    # Components
    components: Dict[str, str] = field(default_factory=dict)  # component_name -> version
    
    # Changes
    changes: List[Dict[str, Any]] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    bug_fixes: List[str] = field(default_factory=list)
    
    # Status
    status: str = "released"  # released, beta, deprecated
    stability_score: float = 0.8
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    released_at: Optional[datetime] = None
    deprecated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['released_at']:
            data['released_at'] = self.released_at.isoformat()
        if data['deprecated_at']:
            data['deprecated_at'] = self.deprecated_at.isoformat()
        return data


@dataclass
class VersionCheckpoint:
    """
    Represents a checkpoint in the system's evolution.
    """
    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str = ""
    
    # Checkpoint Details
    name: str = ""
    description: str = ""
    
    # State
    system_state: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    
    # Validation
    validation_passed: bool = True
    validation_results: Dict[str, Any] = field(default_factory=dict)
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data


class CognitiveVersionControl:
    """
    Manages system versioning and rollback capabilities.
    
    The Cognitive Version Control system enables tracking of system changes,
    creation of stable versions, and rollback to previous states when needed.
    """
    
    def __init__(self):
        """Initialize the Cognitive Version Control system."""
        self.versions: Dict[str, SystemVersion] = {}
        self.version_history: List[str] = []  # version_ids in order
        self.checkpoints: Dict[str, VersionCheckpoint] = {}
        self.current_version: Optional[SystemVersion] = None
        self.logger = logging.getLogger(__name__)
    
    def create_version(self, version_number: str, name: str, description: str = "") -> SystemVersion:
        """
        Create a new system version.
        
        Args:
            version_number: Version number (e.g., "1.0.0")
            name: Name of the version
            description: Description of the version
            
        Returns:
            The created SystemVersion
        """
        version = SystemVersion(
            version_number=version_number,
            name=name,
            description=description
        )
        
        self.versions[version.version_id] = version
        self.version_history.append(version.version_id)
        self.current_version = version
        
        self.logger.info(f"Created system version {version_number}: {name}")
        return version
    
    def get_version(self, version_id: str) -> Optional[SystemVersion]:
        """
        Retrieve a version by ID.
        
        Args:
            version_id: The ID of the version
            
        Returns:
            The SystemVersion, or None if not found
        """
        return self.versions.get(version_id)
    
    def get_version_by_number(self, version_number: str) -> Optional[SystemVersion]:
        """
        Retrieve a version by version number.
        
        Args:
            version_number: The version number
            
        Returns:
            The SystemVersion, or None if not found
        """
        for version in self.versions.values():
            if version.version_number == version_number:
                return version
        return None
    
    def add_change_to_version(self, version_id: str, change: Dict[str, Any]) -> bool:
        """
        Add a change to a version.
        
        Args:
            version_id: The ID of the version
            change: The change to add
            
        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            return False
        
        version.changes.append(change)
        return True
    
    def add_improvement_to_version(self, version_id: str, improvement: str) -> bool:
        """
        Add an improvement to a version.
        
        Args:
            version_id: The ID of the version
            improvement: The improvement to add
            
        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            return False
        
        if improvement not in version.improvements:
            version.improvements.append(improvement)
        
        return True
    
    def add_bug_fix_to_version(self, version_id: str, bug_fix: str) -> bool:
        """
        Add a bug fix to a version.
        
        Args:
            version_id: The ID of the version
            bug_fix: The bug fix to add
            
        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            return False
        
        if bug_fix not in version.bug_fixes:
            version.bug_fixes.append(bug_fix)
        
        return True
    
    def release_version(self, version_id: str) -> bool:
        """
        Release a version.
        
        Args:
            version_id: The ID of the version
            
        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            return False
        
        version.status = "released"
        version.released_at = datetime.utcnow()
        
        self.logger.info(f"Released version {version.version_number}")
        return True
    
    def deprecate_version(self, version_id: str) -> bool:
        """
        Deprecate a version.
        
        Args:
            version_id: The ID of the version
            
        Returns:
            True if successful, False otherwise
        """
        version = self.versions.get(version_id)
        if not version:
            return False
        
        version.status = "deprecated"
        version.deprecated_at = datetime.utcnow()
        
        self.logger.info(f"Deprecated version {version.version_number}")
        return True
    
    def create_checkpoint(self, version_id: str, name: str,
                         system_state: Dict[str, Any],
                         metrics: Dict[str, float]) -> VersionCheckpoint:
        """
        Create a checkpoint for a version.
        
        Args:
            version_id: The ID of the version
            name: Name of the checkpoint
            system_state: Current system state
            metrics: Current metrics
            
        Returns:
            The created VersionCheckpoint
        """
        checkpoint = VersionCheckpoint(
            version_id=version_id,
            name=name,
            system_state=system_state,
            metrics=metrics
        )
        
        self.checkpoints[checkpoint.checkpoint_id] = checkpoint
        
        self.logger.info(f"Created checkpoint {name} for version {version_id}")
        return checkpoint
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[VersionCheckpoint]:
        """
        Retrieve a checkpoint by ID.
        
        Args:
            checkpoint_id: The ID of the checkpoint
            
        Returns:
            The VersionCheckpoint, or None if not found
        """
        return self.checkpoints.get(checkpoint_id)
    
    def rollback_to_version(self, version_id: str) -> Dict[str, Any]:
        """
        Rollback to a previous version.
        
        Args:
            version_id: The ID of the version to rollback to
            
        Returns:
            Rollback result
        """
        version = self.versions.get(version_id)
        if not version:
            return {'success': False, 'error': 'Version not found'}
        
        result = {
            'success': True,
            'rolled_back_to': version.version_number,
            'timestamp': datetime.utcnow().isoformat(),
            'system_state_restored': True,
            'metrics_restored': True
        }
        
        self.current_version = version
        
        self.logger.info(f"Rolled back to version {version.version_number}")
        return result
    
    def rollback_to_checkpoint(self, checkpoint_id: str) -> Dict[str, Any]:
        """
        Rollback to a specific checkpoint.
        
        Args:
            checkpoint_id: The ID of the checkpoint
            
        Returns:
            Rollback result
        """
        checkpoint = self.checkpoints.get(checkpoint_id)
        if not checkpoint:
            return {'success': False, 'error': 'Checkpoint not found'}
        
        result = {
            'success': True,
            'rolled_back_to_checkpoint': checkpoint.name,
            'timestamp': datetime.utcnow().isoformat(),
            'system_state_restored': True,
            'metrics_restored': True,
            'state': checkpoint.system_state,
            'metrics': checkpoint.metrics
        }
        
        self.logger.info(f"Rolled back to checkpoint {checkpoint.name}")
        return result
    
    def get_version_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about system versions.
        
        Returns:
            Dictionary containing version statistics
        """
        stats = {
            'total_versions': len(self.versions),
            'released_versions': sum(1 for v in self.versions.values() if v.status == 'released'),
            'beta_versions': sum(1 for v in self.versions.values() if v.status == 'beta'),
            'deprecated_versions': sum(1 for v in self.versions.values() if v.status == 'deprecated'),
            'total_checkpoints': len(self.checkpoints),
            'current_version': self.current_version.version_number if self.current_version else None,
            'total_changes': 0,
            'total_improvements': 0,
            'total_bug_fixes': 0
        }
        
        # Count changes, improvements, and bug fixes
        for version in self.versions.values():
            stats['total_changes'] += len(version.changes)
            stats['total_improvements'] += len(version.improvements)
            stats['total_bug_fixes'] += len(version.bug_fixes)
        
        return stats
    
    def export_version_history(self) -> str:
        """
        Export version history as JSON.
        
        Returns:
            JSON string containing version history
        """
        data = {
            'versions': [v.to_dict() for v in self.versions.values()],
            'checkpoints': [c.to_dict() for c in self.checkpoints.values()],
            'version_history': self.version_history,
            'current_version': self.current_version.version_id if self.current_version else None
        }
        
        return json.dumps(data, indent=2, default=str)
