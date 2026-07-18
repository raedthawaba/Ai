"""
Experience Memory - Storage and retrieval of experiences for learning.

The Experience Memory stores experiences and learned lessons, enabling the system
to learn from past interactions and improve future decision-making.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ExperienceType(Enum):
    """Enumeration of experience types."""
    SUCCESS = "success"
    FAILURE = "failure"
    LEARNING = "learning"
    DISCOVERY = "discovery"
    CHALLENGE = "challenge"


@dataclass
class Experience:
    """
    Represents a stored experience with context and lessons learned.
    """
    experience_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    experience_type: str = ExperienceType.LEARNING.value
    
    # Experience Details
    description: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Situation
    situation: str = ""
    action_taken: str = ""
    outcome: str = ""
    
    # Evaluation
    success_level: float = 0.5  # 0.0 to 1.0
    impact: float = 0.5  # 0.0 to 1.0
    
    # Lessons
    lessons_learned: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    # Related Entities
    related_concepts: List[str] = field(default_factory=list)
    related_hypotheses: List[str] = field(default_factory=list)
    related_experiments: List[str] = field(default_factory=list)
    
    # Timeline
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None
    review_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        if data['reviewed_at']:
            data['reviewed_at'] = self.reviewed_at.isoformat()
        return data


@dataclass
class LearnedLesson:
    """
    Represents a generalized lesson learned from experiences.
    """
    lesson_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Lesson Details
    title: str = ""
    description: str = ""
    category: str = ""
    
    # Content
    principle: str = ""
    conditions: List[str] = field(default_factory=list)
    applications: List[str] = field(default_factory=list)
    
    # Evidence
    supporting_experiences: List[str] = field(default_factory=list)  # experience_ids
    confidence: float = 0.5
    
    # Impact
    times_applied: int = 0
    success_rate: float = 0.5
    
    # Timeline
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_applied: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        if data['last_applied']:
            data['last_applied'] = self.last_applied.isoformat()
        return data


class ExperienceMemory:
    """
    Stores and retrieves experiences for learning and improvement.
    
    The Experience Memory enables the system to learn from past interactions,
    extract generalizable lessons, and apply them to future situations.
    """
    
    def __init__(self):
        """Initialize the Experience Memory."""
        self.experiences: Dict[str, Experience] = {}
        self.experiences_by_type: Dict[str, List[str]] = {}  # type -> [experience_ids]
        self.experiences_by_concept: Dict[str, List[str]] = {}  # concept_id -> [experience_ids]
        self.learned_lessons: Dict[str, LearnedLesson] = {}
        self.logger = logging.getLogger(__name__)
    
    def store_experience(self, experience_type: str, description: str,
                        situation: str, action_taken: str, outcome: str,
                        success_level: float = 0.5) -> Experience:
        """
        Store a new experience.
        
        Args:
            experience_type: Type of experience
            description: Description of the experience
            situation: The situation encountered
            action_taken: The action taken
            outcome: The outcome of the action
            success_level: Level of success (0.0 to 1.0)
            
        Returns:
            The stored Experience
        """
        experience = Experience(
            experience_type=experience_type,
            description=description,
            situation=situation,
            action_taken=action_taken,
            outcome=outcome,
            success_level=success_level
        )
        
        self.experiences[experience.experience_id] = experience
        
        # Index by type
        if experience_type not in self.experiences_by_type:
            self.experiences_by_type[experience_type] = []
        self.experiences_by_type[experience_type].append(experience.experience_id)
        
        self.logger.info(f"Stored experience {experience.experience_id} of type {experience_type}")
        return experience
    
    def get_experience(self, experience_id: str) -> Optional[Experience]:
        """
        Retrieve an experience by ID.
        
        Args:
            experience_id: The ID of the experience
            
        Returns:
            The Experience, or None if not found
        """
        return self.experiences.get(experience_id)
    
    def get_experiences_by_type(self, experience_type: str) -> List[Experience]:
        """
        Get all experiences of a specific type.
        
        Args:
            experience_type: The type of experiences
            
        Returns:
            List of Experience objects
        """
        experience_ids = self.experiences_by_type.get(experience_type, [])
        return [self.experiences[eid] for eid in experience_ids if eid in self.experiences]
    
    def add_lesson_to_experience(self, experience_id: str, lesson: str) -> bool:
        """
        Add a lesson learned to an experience.
        
        Args:
            experience_id: The ID of the experience
            lesson: The lesson to add
            
        Returns:
            True if successful, False otherwise
        """
        experience = self.experiences.get(experience_id)
        if not experience:
            return False
        
        if lesson not in experience.lessons_learned:
            experience.lessons_learned.append(lesson)
        
        return True
    
    def add_insight_to_experience(self, experience_id: str, insight: str) -> bool:
        """
        Add an insight to an experience.
        
        Args:
            experience_id: The ID of the experience
            insight: The insight to add
            
        Returns:
            True if successful, False otherwise
        """
        experience = self.experiences.get(experience_id)
        if not experience:
            return False
        
        if insight not in experience.insights:
            experience.insights.append(insight)
        
        return True
    
    def add_recommendation_to_experience(self, experience_id: str, recommendation: str) -> bool:
        """
        Add a recommendation to an experience.
        
        Args:
            experience_id: The ID of the experience
            recommendation: The recommendation to add
            
        Returns:
            True if successful, False otherwise
        """
        experience = self.experiences.get(experience_id)
        if not experience:
            return False
        
        if recommendation not in experience.recommendations:
            experience.recommendations.append(recommendation)
        
        return True
    
    def link_experience_to_concept(self, experience_id: str, concept_id: str) -> bool:
        """
        Link an experience to a concept.
        
        Args:
            experience_id: The ID of the experience
            concept_id: The ID of the concept
            
        Returns:
            True if successful, False otherwise
        """
        experience = self.experiences.get(experience_id)
        if not experience:
            return False
        
        if concept_id not in experience.related_concepts:
            experience.related_concepts.append(concept_id)
        
        # Index by concept
        if concept_id not in self.experiences_by_concept:
            self.experiences_by_concept[concept_id] = []
        if experience_id not in self.experiences_by_concept[concept_id]:
            self.experiences_by_concept[concept_id].append(experience_id)
        
        return True
    
    def get_experiences_for_concept(self, concept_id: str) -> List[Experience]:
        """
        Get all experiences related to a concept.
        
        Args:
            concept_id: The ID of the concept
            
        Returns:
            List of Experience objects
        """
        experience_ids = self.experiences_by_concept.get(concept_id, [])
        return [self.experiences[eid] for eid in experience_ids if eid in self.experiences]
    
    def extract_lesson(self, title: str, principle: str, 
                      supporting_experiences: List[str]) -> LearnedLesson:
        """
        Extract a generalized lesson from experiences.
        
        Args:
            title: Title of the lesson
            principle: The principle or rule
            supporting_experiences: List of experience IDs supporting the lesson
            
        Returns:
            The extracted LearnedLesson
        """
        lesson = LearnedLesson(
            title=title,
            principle=principle,
            supporting_experiences=supporting_experiences
        )
        
        # Calculate confidence based on supporting experiences
        if supporting_experiences:
            experiences = [self.experiences[eid] for eid in supporting_experiences if eid in self.experiences]
            if experiences:
                success_levels = [e.success_level for e in experiences]
                lesson.confidence = sum(success_levels) / len(success_levels)
        
        self.learned_lessons[lesson.lesson_id] = lesson
        self.logger.info(f"Extracted lesson: {title}")
        return lesson
    
    def apply_lesson(self, lesson_id: str, success: bool) -> bool:
        """
        Record the application of a lesson.
        
        Args:
            lesson_id: The ID of the lesson
            success: Whether the application was successful
            
        Returns:
            True if successful, False otherwise
        """
        lesson = self.learned_lessons.get(lesson_id)
        if not lesson:
            return False
        
        lesson.times_applied += 1
        lesson.last_applied = datetime.utcnow()
        
        # Update success rate
        if lesson.times_applied > 0:
            old_success_rate = lesson.success_rate
            lesson.success_rate = (old_success_rate * (lesson.times_applied - 1) + (1.0 if success else 0.0)) / lesson.times_applied
        
        return True
    
    def search_experiences(self, query: Dict[str, Any]) -> List[Experience]:
        """
        Search for experiences based on criteria.
        
        Args:
            query: Search criteria
            
        Returns:
            List of matching Experience objects
        """
        results = []
        
        for experience in self.experiences.values():
            match = True
            
            # Check type
            if 'type' in query and experience.experience_type != query['type']:
                match = False
            
            # Check success level
            if 'min_success' in query and experience.success_level < query['min_success']:
                match = False
            
            # Check keywords
            if 'keywords' in query:
                keywords = query['keywords']
                text = (experience.description + experience.situation + experience.outcome).lower()
                if not any(kw.lower() in text for kw in keywords):
                    match = False
            
            if match:
                results.append(experience)
        
        return results
    
    def review_experience(self, experience_id: str) -> bool:
        """
        Mark an experience as reviewed.
        
        Args:
            experience_id: The ID of the experience
            
        Returns:
            True if successful, False otherwise
        """
        experience = self.experiences.get(experience_id)
        if not experience:
            return False
        
        experience.reviewed_at = datetime.utcnow()
        experience.review_count += 1
        
        return True
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the experience memory.
        
        Returns:
            Dictionary containing memory statistics
        """
        stats = {
            'total_experiences': len(self.experiences),
            'total_lessons': len(self.learned_lessons),
            'experiences_by_type': {},
            'average_success_level': 0.0,
            'average_impact': 0.0,
            'reviewed_experiences': 0
        }
        
        if not self.experiences:
            return stats
        
        # Count by type
        for exp_type in self.experiences_by_type:
            stats['experiences_by_type'][exp_type] = len(self.experiences_by_type[exp_type])
        
        # Calculate averages
        success_levels = [e.success_level for e in self.experiences.values()]
        impacts = [e.impact for e in self.experiences.values()]
        
        stats['average_success_level'] = sum(success_levels) / len(success_levels) if success_levels else 0.0
        stats['average_impact'] = sum(impacts) / len(impacts) if impacts else 0.0
        stats['reviewed_experiences'] = sum(1 for e in self.experiences.values() if e.reviewed_at)
        
        return stats
    
    def export_experiences(self, experience_ids: Optional[List[str]] = None) -> str:
        """
        Export experiences as JSON.
        
        Args:
            experience_ids: Optional list of specific experience IDs to export
            
        Returns:
            JSON string containing the experiences
        """
        if experience_ids:
            experiences = [self.experiences[eid] for eid in experience_ids if eid in self.experiences]
        else:
            experiences = list(self.experiences.values())
        
        return json.dumps([e.to_dict() for e in experiences], indent=2, default=str)
