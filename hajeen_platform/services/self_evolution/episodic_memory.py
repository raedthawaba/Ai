from __future__ import annotations
import logging
import json
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

class EpisodicMemory:
    """Stores and manages episodic memories (experiences) of agent interactions and outcomes."""

    def __init__(self, storage_path: str = "./agent_experiences.jsonl"):
        self.storage_path = storage_path
        self.experiences: List[Dict[str, Any]] = self._load_experiences()
        logger.info(f"EpisodicMemory initialized. Loaded {len(self.experiences)} experiences from {storage_path}")

    def _load_experiences(self) -> List[Dict[str, Any]]:
        """Loads experiences from a JSONL file."""
        if not os.path.exists(self.storage_path):
            return []
        
        loaded_data = []
        with open(self.storage_path, "r") as f:
            for line in f:
                try:
                    loaded_data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON from memory file: {e} in line: {line.strip()}")
        return loaded_data

    def _save_experiences(self) -> None:
        """Saves current experiences to a JSONL file."""
        with open(self.storage_path, "w") as f:
            for exp in self.experiences:
                f.write(json.dumps(exp) + "\n")
        logger.debug(f"Saved {len(self.experiences)} experiences to {self.storage_path}")

    def add_experience(self, 
                       prompt: str, 
                       actions: List[str], 
                       outcome: str, 
                       success: bool, 
                       reflection: Optional[Dict[str, Any]] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> None:
        """Adds a new experience to the memory."""
        experience = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "actions": actions,
            "outcome": outcome,
            "success": success,
            "reflection": reflection,
            "metadata": metadata if metadata is not None else {}
        }
        self.experiences.append(experience)
        self._save_experiences() # Save immediately for persistence
        logger.info(f"Added new experience (success={success}). Total experiences: {len(self.experiences)}")

    def retrieve_experiences(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Retrieves relevant experiences based on a query."""
        # This is a placeholder for a more sophisticated retrieval mechanism (e.g., vector search)
        # For now, it's a simple keyword-based search.
        query_lower = query.lower()
        relevant_experiences = []
        for exp in self.experiences:
            if query_lower in exp["prompt"].lower() or query_lower in exp["outcome"].lower():
                relevant_experiences.append(exp)
        
        # Sort by recency for now, more advanced would be by relevance score
        relevant_experiences.sort(key=lambda x: x["timestamp"], reverse=True)
        logger.debug(f"Retrieved {len(relevant_experiences)} relevant experiences for query: '{query}'")
        return relevant_experiences[:top_k]

    def get_successful_experiences(self, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns successful experiences, optionally limited by top_k."""
        successful = [exp for exp in self.experiences if exp["success"]]
        successful.sort(key=lambda x: x["timestamp"], reverse=True)
        return successful[:top_k] if top_k else successful

    def get_failed_experiences(self, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns failed experiences, optionally limited by top_k."""
        failed = [exp for exp in self.experiences if not exp["success"]]
        failed.sort(key=lambda x: x["timestamp"], reverse=True)
        return failed[:top_k] if top_k else failed

import os

print("Episodic memory component created.")
