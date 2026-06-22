from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base_agent import AgentContext, AgentResult, AgentStep, BaseAgent

logger = logging.getLogger(__name__)


class RetrievalAgent(BaseAgent):
    """Retrieves relevant context from a knowledge base for a given query."""

    def __init__(
        self,
        rag_service: Optional[Any] = None,
        top_k: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name="retrieval",
            description="Retrieves relevant documents from knowledge base",
            **kwargs,
        )
        self._rag = rag_service
        self.top_k = top_k

    async def _execute(self, context: AgentContext) -> AgentResult:
        steps: List[AgentStep] = []

        query = context.goal
        retrieved: List[Dict] = []

        if self._rag is not None:
            try:
                rag_result = await self._rag.query(query, top_k=self.top_k)
                retrieved = rag_result.get("sources", [])
                steps.append(
                    AgentStep(
                        action="semantic_retrieval",
                        observation=f"Retrieved {len(retrieved)} documents",
                        result=rag_result,
                    )
                )
                context.memory["retrieved_docs"] = retrieved
                context.memory["context"] = rag_result.get("context", "")
                context.memory["rag_answer"] = rag_result.get("answer", "")
            except Exception as exc:
                logger.error("RAG retrieval failed: %s", exc)
                steps.append(
                    AgentStep(action="semantic_retrieval", error=str(exc), observation="Failed")
                )
        else:
            logger.warning("No RAG service configured for RetrievalAgent")

        output = self._format_output(retrieved, context.memory.get("rag_answer", ""))
        return AgentResult(
            success=True,
            output=output,
            steps=steps,
            context=context,
        )

    @staticmethod
    def _format_output(docs: List[Dict], answer: str) -> str:
        if answer:
            return answer
        if not docs:
            return "No relevant documents found."
        parts = ["**Retrieved Documents:**"]
        for i, doc in enumerate(docs[:5], 1):
            parts.append(f"{i}. {doc.get('title', doc.get('doc_id', 'Document'))}")
            snippet = doc.get("snippet", "")
            if snippet:
                parts.append(f"   {snippet[:150]}...")
        return "\n".join(parts)
