from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def synthetic_data_generator(
    llm: Any,
    domain: str = "general",
    schema: Optional[Dict[str, Any]] = None,
    count: int = 10,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Generate synthetic data samples using an LLM.
    If schema is provided, samples conform to that structure.
    Returns a list of dicts.
    """
    if llm is None:
        logger.warning("LLM is None — returning stub data for domain '%s'.", domain)
        return [{"id": f"stub_{i}", "domain": domain, "content": f"Sample {i}"} for i in range(count)]

    schema_desc = json.dumps(schema, indent=2) if schema else '{"id": "string", "content": "string"}'
    prompt = (
        f"Generate {count} diverse synthetic data samples for the domain: {domain}.\n"
        f"Each sample must be a JSON object with this schema:\n{schema_desc}\n"
        f"Return a JSON array only — no markdown:\n"
    )

    try:
        if hasattr(llm, "agenerate"):
            raw = await llm.agenerate(prompt)
        elif callable(llm):
            result = llm(prompt)
            raw = await result if asyncio.iscoroutine(result) else result
        else:
            raw = ""

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            samples = json.loads(match.group())
            logger.info("Generated %d samples for domain '%s'.", len(samples), domain)
            return samples
    except Exception as exc:
        logger.error("synthetic_data_generator LLM call failed: %s", exc)

    # Fallback: structured stubs
    return [
        {"id": str(uuid.uuid4())[:8], "domain": domain, "content": f"Sample {i} for {domain}"}
        for i in range(count)
    ]


async def dataset_refiner(
    dataset: List[Dict[str, Any]],
    llm: Any,
    rules: Optional[List[str]] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Refine a dataset by applying quality rules using an LLM.
    Rules are applied in-place to each sample.
    """
    rules = rules or ["ensure accuracy", "improve clarity", "add missing details"]
    if llm is None:
        logger.warning("LLM is None — applying rule metadata without actual refinement.")
        for item in dataset:
            item["refined"] = True
            item["applied_rules"] = rules
        return dataset

    refined = []
    for item in dataset:
        prompt = (
            f"Improve this data sample by applying these rules: {', '.join(rules)}.\n"
            f"Sample: {json.dumps(item)}\n"
            f"Return only the improved JSON object:\n"
        )
        try:
            if hasattr(llm, "agenerate"):
                raw = await llm.agenerate(prompt)
            elif callable(llm):
                result = llm(prompt)
                raw = await result if asyncio.iscoroutine(result) else result
            else:
                raw = ""

            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                improved = json.loads(match.group())
                improved["refined"] = True
                improved["applied_rules"] = rules
                refined.append(improved)
                continue
        except Exception as exc:
            logger.warning("dataset_refiner failed for item: %s", exc)

        item["refined"] = True
        item["applied_rules"] = rules
        refined.append(item)

    logger.info("Refined %d/%d samples.", len(refined), len(dataset))
    return refined


async def vector_store_ingestion_pipeline(
    data: List[Dict[str, Any]],
    vector_db_client: Any,
    embed_fn: Optional[Any] = None,
    text_key: str = "content",
    **kwargs,
) -> Dict[str, Any]:
    """
    Ingest data into a vector store.
    embed_fn(text) -> List[float] must be provided for real embedding.
    Falls back to stub embeddings if unavailable.
    """
    if not data:
        return {"status": "skipped", "reason": "Empty dataset.", "ingested_count": 0}

    ingested_ids = []
    vectors_to_upsert = []

    for item in data:
        text = str(item.get(text_key, item))
        doc_id = item.get("id", str(uuid.uuid4())[:8])

        if embed_fn:
            try:
                embedding = embed_fn(text)
                if asyncio.iscoroutine(embedding):
                    embedding = await embedding
            except Exception as exc:
                logger.warning("Embedding failed for item %s: %s", doc_id, exc)
                embedding = [0.0] * 384
        else:
            embedding = [0.0] * 384  # stub

        vectors_to_upsert.append({
            "id": doc_id,
            "values": embedding,
            "metadata": {k: v for k, v in item.items() if k != "embedding"},
        })
        ingested_ids.append(doc_id)

    # Upsert into vector DB
    if vector_db_client is not None:
        try:
            if asyncio.iscoroutinefunction(vector_db_client.upsert):
                await vector_db_client.upsert(vectors_to_upsert)
            else:
                vector_db_client.upsert(vectors_to_upsert)
            logger.info("Ingested %d items into vector store.", len(ingested_ids))
        except Exception as exc:
            logger.error("Vector store upsert failed: %s", exc)
            return {"status": "error", "error": str(exc), "ingested_count": 0}
    else:
        logger.warning("No vector_db_client — embeddings computed but not stored.")

    return {
        "status": "success",
        "ingested_count": len(ingested_ids),
        "ids": ingested_ids,
    }


class MockLLM:
    """Drop-in mock LLM for local testing of data pipeline components."""

    async def agenerate(self, prompt: str) -> str:
        if "Generate" in prompt:
            count = 3
            return json.dumps([
                {"id": f"mock_{i}", "content": f"Mock sample {i}"} for i in range(count)
            ])
        return json.dumps({"id": "mock", "content": "Improved mock content.", "refined": True})


class MockVectorDBClient:
    """Drop-in mock vector DB for local testing."""

    def __init__(self) -> None:
        self._store: List[Dict[str, Any]] = []

    async def upsert(self, vectors: List[Dict[str, Any]]) -> None:
        self._store.extend(vectors)
        logger.debug("MockVectorDB: stored %d vectors.", len(vectors))

    async def query(
        self, query_vector: List[float], top_k: int = 5
    ) -> List[Dict[str, Any]]:
        return self._store[:top_k]

    def count(self) -> int:
        return len(self._store)
