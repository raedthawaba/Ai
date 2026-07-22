"""
Mock LLM Manager for Development/Testing
========================================

This module provides a fallback LLM Manager that works without API keys.
Used when real LLM API is not available.

Author: OpenHands AI Agent
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class MockLLMResponse:
    """Mock LLM response for testing."""
    content: str
    model: str = "mock-gpt-4"
    tokens_used: int = 100
    latency_ms: float = 50.0


class MockLLMManager:
    """
    Mock LLM Manager that provides fallback responses.
    Used when real LLM API is not available.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.model = self.config.get("model", "mock-gpt-4")
        self._initialized = True
        
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate a mock response based on the prompt.
        
        This is a deterministic mock that returns structured responses
        based on the input prompt content.
        """
        await asyncio.sleep(0.01)  # Simulate minimal latency
        
        prompt_lower = prompt.lower()
        
        # Intent Analysis Response
        if "intent" in prompt_lower or "primary_intent" in prompt_lower:
            if "code" in prompt_lower or "programming" in prompt_lower or "function" in prompt_lower:
                return json.dumps({
                    "primary_intent": "code_development",
                    "category": "code_development",
                    "secondary_intents": ["explanation", "documentation"],
                    "implicit_requirements": ["working code", "best practices"],
                    "confidence": 0.92,
                    "reasoning": "Prompt contains programming-related keywords",
                    "alternative_interpretations": []
                })
            elif "explain" in prompt_lower or "what is" in prompt_lower or "how does" in prompt_lower:
                return json.dumps({
                    "primary_intent": "explanation",
                    "category": "information_request",
                    "secondary_intents": ["definition", "clarification"],
                    "implicit_requirements": ["clear explanation"],
                    "confidence": 0.95,
                    "reasoning": "Prompt asks for explanation or definition",
                    "alternative_interpretations": []
                })
            elif "build" in prompt_lower or "create" in prompt_lower or "develop" in prompt_lower:
                return json.dumps({
                    "primary_intent": "creation",
                    "category": "task_execution",
                    "secondary_intents": ["planning", "implementation"],
                    "implicit_requirements": ["step-by-step guide"],
                    "confidence": 0.88,
                    "reasoning": "Prompt asks to create or build something",
                    "alternative_interpretations": []
                })
            else:
                return json.dumps({
                    "primary_intent": "general_inquiry",
                    "category": "information_request",
                    "secondary_intents": ["clarification"],
                    "implicit_requirements": ["helpful response"],
                    "confidence": 0.75,
                    "reasoning": "General inquiry detected",
                    "alternative_interpretations": []
                })
        
        # Context Analysis Response
        if "context" in prompt_lower or "domain" in prompt_lower or "complexity" in prompt_lower:
            if "code" in prompt_lower or "programming" in prompt_lower:
                return json.dumps({
                    "detected_domain": "code",
                    "expertise_level": "intermediate",
                    "estimated_complexity": "medium",
                    "confidence": 0.85,
                    "reasoning": "Technical programming context",
                    "required_capabilities": ["code_generation", "debugging"],
                    "constraints": [],
                    "priorities": ["correctness", "performance"],
                    "time_sensitivity": "low",
                    "recommendations": ["provide code examples"]
                })
            elif "business" in prompt_lower or "marketing" in prompt_lower:
                return json.dumps({
                    "detected_domain": "business",
                    "expertise_level": "general",
                    "estimated_complexity": "low",
                    "confidence": 0.80,
                    "reasoning": "Business-related context",
                    "required_capabilities": ["analysis", "writing"],
                    "constraints": [],
                    "priorities": ["clarity", "actionability"],
                    "time_sensitivity": "medium",
                    "recommendations": ["provide examples"]
                })
            else:
                return json.dumps({
                    "detected_domain": "general",
                    "expertise_level": "general",
                    "estimated_complexity": "low",
                    "confidence": 0.70,
                    "reasoning": "General context",
                    "required_capabilities": ["general_knowledge"],
                    "constraints": [],
                    "priorities": ["clarity"],
                    "time_sensitivity": "low",
                    "recommendations": ["provide clear answer"]
                })
        
        # Reasoning Response
        if "reasoning" in prompt_lower or "strategy" in prompt_lower or "solution" in prompt_lower:
            return json.dumps({
                "strategy": "chain_of_thought",
                "steps": [
                    {
                        "description": "Analyze the problem",
                        "reasoning": "Understand what is being asked",
                        "conclusion": "Clear understanding of requirements",
                        "confidence": 0.9,
                        "alternatives": []
                    },
                    {
                        "description": "Generate solution approach",
                        "reasoning": "Determine best approach based on context",
                        "conclusion": "Solution strategy identified",
                        "confidence": 0.85,
                        "alternatives": ["alternative approach 1", "alternative approach 2"]
                    }
                ],
                "missing_information": [],
                "risks": [],
                "solution_options": [
                    {
                        "title": "Standard Solution",
                        "description": "Use standard approach for this problem",
                        "pros": ["Well-tested", "Reliable"],
                        "cons": ["May not be optimal"],
                        "effort_estimate": "low",
                        "time_estimate": "5-10 minutes",
                        "risk_level": "low",
                        "feasibility_score": 0.9,
                        "recommended": True
                    }
                ],
                "recommended_solution_index": 0,
                "confidence": 0.88,
                "summary": "Solution approach determined"
            })
        
        # Default response
        return json.dumps({
            "status": "success",
            "message": "Mock response generated",
            "data": {
                "content": f"Processed: {prompt[:100]}...",
                "confidence": 0.8
            }
        })
    
    async def generate_stream(self, prompt: str, **kwargs):
        """Generate streaming mock response."""
        response = await self.generate(prompt, **kwargs)
        words = response.split()
        for word in words:
            yield word + " "
            await asyncio.sleep(0.001)
    
    async def analyze(self, text: str, **kwargs) -> Dict[str, Any]:
        """Analyze text using mock LLM."""
        return {
            "sentiment": "neutral",
            "entities": [],
            "topics": [],
            "summary": text[:100] if len(text) > 100 else text
        }
    
    def is_available(self) -> bool:
        """Mock is always available."""
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get mock statistics."""
        return {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_tokens": 0
        }


class MockEmbeddingManager:
    """
    Mock Embedding Manager for development/testing.
    Provides simple hash-based embeddings.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.dimension = self.config.get("dimension", 384)
        self._initialized = True
    
    async def get_embedding(self, text: str, **kwargs) -> List[float]:
        """Get mock embedding using simple hash."""
        # Simple deterministic hash-based embedding
        import hashlib
        hash_value = int(hashlib.md5(text.encode()).hexdigest(), 16)
        
        # Generate pseudo-random but deterministic embedding
        embedding = []
        for i in range(self.dimension):
            seed = (hash_value + i) % 10000
            value = (seed / 10000.0) * 2 - 1  # Normalize to [-1, 1]
            embedding.append(value)
        
        # Normalize
        magnitude = sum(x**2 for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        
        return embedding
    
    async def get_embeddings(self, texts: List[str], **kwargs) -> List[List[float]]:
        """Get embeddings for multiple texts."""
        return [await self.get_embedding(text, **kwargs) for text in texts]
    
    def is_available(self) -> bool:
        """Mock is always available."""
        return True


def get_mock_llm_manager(config: Optional[Dict] = None) -> MockLLMManager:
    """Get mock LLM manager instance."""
    return MockLLMManager(config)


def get_mock_embedding_manager(config: Optional[Dict] = None) -> MockEmbeddingManager:
    """Get mock embedding manager instance."""
    return MockEmbeddingManager(config)
