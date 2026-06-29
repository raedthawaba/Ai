from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from hajeen_platform.core.context_intelligence.context_scoring import ContextScoringSystem, DynamicContextRanker
from hajeen_platform.core.context_intelligence.semantic_memory import SemanticMemoryRetrieval

logger = logging.getLogger(__name__)

class ContextIntelligenceEngine:
    """
    Orchestrates advanced context management, including scoring, ranking, semantic retrieval,
    compression, and prompt assembly.
    """
    def __init__(self, embedding_model: Any) -> None:
        self.scoring_system = ContextScoringSystem()
        self.ranker = DynamicContextRanker(self.scoring_system)
        self.semantic_memory = SemanticMemoryRetrieval(embedding_model) # Pass a real embedding model
        self.persistent_context: List[Dict[str, Any]] = []

    def add_to_persistent_context(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Adds content to the persistent context and semantic memory.
        """
        entry = self.semantic_memory.add_memory(content, metadata)
        self.persistent_context.append({"id": entry.id, "content": content, "metadata": metadata})
        logger.info(f"Added content to persistent context: {content[:50]}...")

    def retrieve_and_rank_context(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves relevant context from semantic memory and ranks it.
        """
        retrieved_memories = self.semantic_memory.retrieve_similar(query, top_k=top_k)
        # Convert SemanticMemoryEntry back to dict for ranking
        context_chunks = [{
            "id": mem.id,
            "content": mem.content,
            "metadata": mem.metadata
        } for mem in retrieved_memories]
        
        ranked_context = self.ranker.rank_contexts(context_chunks, query)
        logger.info(f"Retrieved and ranked {len(ranked_context)} context chunks for query: {query}")
        return ranked_context

    def compress_long_conversation(self, conversation_history: List[str], max_tokens: int) -> str:
        """
        Compresses a long conversation history to fit within a token limit.
        Placeholder for actual summarization/compression logic (e.g., using LLM).
        """
        # In a real scenario, this would use an LLM to summarize or select key turns
        logger.info(f"Compressing conversation history to {max_tokens} tokens (placeholder).")
        compressed_text = "...".join(conversation_history[-2:]) # Dummy compression
        return compressed_text

    def assemble_prompt(self, query: str, retrieved_context: List[Dict[str, Any]], system_prompt: str = "") -> str:
        """
        Assembles a final prompt for the LLM, injecting relevant context.
        """
        context_str = "\n".join([chunk["content"] for chunk in retrieved_context])
        
        final_prompt = f"""
{system_prompt}

Relevant Context:
{context_str}

User Query: {query}
"""
        logger.info("Prompt assembled with context.")
        return final_prompt

    def get_retrieval_aware_context(self, query: str, conversation_history: List[str], max_tokens: int = 2048) -> Dict[str, Any]:
        """
        Combines semantic retrieval, conversation compression, and prompt assembly.
        """
        # 1. Retrieve relevant context
        retrieved_context = self.retrieve_and_rank_context(query)

        # 2. Compress conversation history if needed
        compressed_history = self.compress_long_conversation(conversation_history, max_tokens)

        # 3. Assemble the final prompt
        final_prompt = self.assemble_prompt(query, retrieved_context, system_prompt="You are a helpful AI assistant.")

        return {
            "retrieved_context": retrieved_context,
            "compressed_history": compressed_history,
            "final_prompt": final_prompt
        }
