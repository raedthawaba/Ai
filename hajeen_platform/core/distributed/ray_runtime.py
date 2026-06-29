from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RayConfig:
    address: str = "auto"
    namespace: str = "hajeen"
    num_cpus: Optional[int] = None
    num_gpus: Optional[int] = None
    resources: Optional[Dict[str, float]] = None

class RayDistributedRuntime:
    """
    Distributed AI Runtime using Ray for multi-node inference and task routing.
    """
    def __init__(self, config: RayConfig) -> None:
        self.config = config
        self.initialized = False

    def initialize(self) -> None:
        """Initialize the Ray cluster connection."""
        try:
            import ray
            if not ray.is_initialized():
                ray.init(
                    address=self.config.address,
                    namespace=self.config.namespace,
                    num_cpus=self.config.num_cpus,
                    num_gpus=self.config.num_gpus,
                    resources=self.config.resources
                )
            self.initialized = True
            logger.info(f"Ray distributed runtime initialized at {self.config.address}")
        except ImportError:
            logger.error("Ray is not installed. Please install ray[default] to use distributed features.")
            raise

    def shutdown(self) -> None:
        """Shutdown the Ray connection."""
        import ray
        if ray.is_initialized():
            ray.shutdown()
            self.initialized = False
            logger.info("Ray distributed runtime shut down.")

    def get_gpu_status(self) -> Dict[str, Any]:
        """Get status of distributed GPUs."""
        import ray
        if not self.initialized:
            return {"status": "not_initialized"}
        
        resources = ray.cluster_resources()
        available = ray.available_resources()
        
        return {
            "total_gpus": resources.get("GPU", 0),
            "available_gpus": available.get("GPU", 0),
            "total_cpus": resources.get("CPU", 0),
            "available_cpus": available.get("CPU", 0),
            "nodes": len(ray.nodes())
        }

@dataclass
class DistributedInferenceConfig:
    model_id: str
    num_replicas: int = 1
    gpus_per_replica: float = 1.0
    cpus_per_replica: float = 2.0
    max_concurrent_queries: int = 100

class RayInferenceManager:
    """Manager for distributed inference using Ray Serve."""
    def __init__(self, runtime: RayDistributedRuntime) -> None:
        self.runtime = runtime
        self.serve_client = None

    def start_serve(self, http_options: Optional[Dict] = None) -> None:
        """Start Ray Serve."""
        from ray import serve
        if not self.runtime.initialized:
            self.runtime.initialize()
        
        serve.start(http_options=http_options or {"host": "0.0.0.0", "port": 8000})
        logger.info("Ray Serve started.")

    def deploy_model(self, config: DistributedInferenceConfig, model_class: Any) -> str:
        """Deploy a model to the Ray cluster."""
        from ray import serve
        
        @serve.deployment(
            num_replicas=config.num_replicas,
            ray_actor_options={
                "num_gpus": config.gpus_per_replica,
                "num_cpus": config.cpus_per_replica
            },
            max_concurrent_queries=config.max_concurrent_queries
        )
        class InferenceDeployment:
            def __init__(self):
                self.model = model_class()
            
            async def __call__(self, request: Any):
                return await self.model.generate(request)

        serve.run(InferenceDeployment.bind(), name=config.model_id)
        logger.info(f"Model {config.model_id} deployed with {config.num_replicas} replicas.")
        return config.model_id
