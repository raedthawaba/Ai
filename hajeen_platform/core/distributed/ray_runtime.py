from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RayConfig:
    address: str = "auto"
    namespace: str = "hajeen"
    num_cpus: Optional[int] = None
    num_gpus: Optional[int] = None
    resources: Optional[Dict[str, float]] = None
    dashboard_host: str = "0.0.0.0"
    log_to_driver: bool = True


@dataclass
class DistributedInferenceConfig:
    model_id: str
    num_replicas: int = 1
    gpus_per_replica: float = 1.0
    cpus_per_replica: float = 2.0
    max_concurrent_queries: int = 100
    route_prefix: str = "/infer"


class RayDistributedRuntime:
    """
    Distributed AI Runtime using Ray for multi-node inference, task distribution,
    and cluster management.  Falls back gracefully if Ray is not installed.
    """

    def __init__(self, config: RayConfig) -> None:
        self.config = config
        self.initialized = False
        self._ray: Optional[Any] = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Connect to or start a Ray cluster."""
        try:
            import ray as _ray
            self._ray = _ray
            if not _ray.is_initialized():
                _ray.init(
                    address=self.config.address if self.config.address != "local" else None,
                    namespace=self.config.namespace,
                    num_cpus=self.config.num_cpus,
                    num_gpus=self.config.num_gpus,
                    resources=self.config.resources,
                    dashboard_host=self.config.dashboard_host,
                    log_to_driver=self.config.log_to_driver,
                    ignore_reinit_error=True,
                )
            self.initialized = True
            logger.info(
                "Ray runtime initialised — address=%s namespace=%s",
                self.config.address,
                self.config.namespace,
            )
        except ImportError:
            logger.error("Ray not installed.  Run: pip install 'ray[default]'")
            raise

    def shutdown(self) -> None:
        """Disconnect from the Ray cluster."""
        if self._ray and self._ray.is_initialized():
            self._ray.shutdown()
            self.initialized = False
            logger.info("Ray runtime shut down.")

    # ── Cluster Status ────────────────────────────────────────────────────

    def get_cluster_status(self) -> Dict[str, Any]:
        """Return a snapshot of cluster resources and node count."""
        if not self.initialized or not self._ray:
            return {"status": "not_initialized"}
        try:
            total = self._ray.cluster_resources()
            available = self._ray.available_resources()
            nodes = self._ray.nodes()
            return {
                "status": "running",
                "nodes": len([n for n in nodes if n.get("Alive")]),
                "total_gpus": total.get("GPU", 0),
                "available_gpus": available.get("GPU", 0),
                "total_cpus": total.get("CPU", 0),
                "available_cpus": available.get("CPU", 0),
                "total_memory_gb": round(total.get("memory", 0) / 1e9, 2),
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ── Remote Tasks ──────────────────────────────────────────────────────

    def submit_task(self, fn: Callable, *args, **kwargs) -> Any:
        """Submit a function as a Ray remote task and return a future."""
        if not self.initialized or not self._ray:
            raise RuntimeError("Ray not initialised. Call initialize() first.")
        remote_fn = self._ray.remote(fn)
        return remote_fn.remote(*args, **kwargs)

    def get_result(self, future: Any, timeout: Optional[float] = None) -> Any:
        """Block and retrieve the result of a Ray future."""
        return self._ray.get(future, timeout=timeout)

    def submit_batch(self, fn: Callable, items: List[Any]) -> List[Any]:
        """Submit a batch of tasks and collect all results."""
        if not self.initialized or not self._ray:
            raise RuntimeError("Ray not initialised.")
        remote_fn = self._ray.remote(fn)
        futures = [remote_fn.remote(item) for item in items]
        return self._ray.get(futures)

    # ── Actor Pool ────────────────────────────────────────────────────────

    def create_actor_pool(self, actor_class: Any, num_actors: int, **actor_kwargs) -> Any:
        """Create a pool of Ray actors for stateful distributed processing."""
        if not self.initialized or not self._ray:
            raise RuntimeError("Ray not initialised.")
        from ray.util import ActorPool
        remote_cls = self._ray.remote(actor_class)
        actors = [remote_cls.remote(**actor_kwargs) for _ in range(num_actors)]
        return ActorPool(actors)


class RayInferenceManager:
    """
    Manages Ray Serve deployments for distributed model inference.
    """

    def __init__(self, runtime: RayDistributedRuntime) -> None:
        self.runtime = runtime
        self._serve = None

    def start_serve(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Start Ray Serve on the connected cluster."""
        if not self.runtime.initialized:
            self.runtime.initialize()
        from ray import serve
        self._serve = serve
        serve.start(http_options={"host": host, "port": port})
        logger.info("Ray Serve started on %s:%d", host, port)

    def deploy_model(self, config: DistributedInferenceConfig, model_class: Any) -> str:
        """Deploy a model class to Ray Serve with the given config."""
        if self._serve is None:
            raise RuntimeError("Ray Serve not started. Call start_serve() first.")

        @self._serve.deployment(
            num_replicas=config.num_replicas,
            ray_actor_options={
                "num_gpus": config.gpus_per_replica,
                "num_cpus": config.cpus_per_replica,
            },
            max_concurrent_queries=config.max_concurrent_queries,
            route_prefix=config.route_prefix,
        )
        class InferenceDeployment:
            def __init__(self):
                self.model = model_class()

            async def __call__(self, request):
                body = await request.json()
                return await self.model.generate(body)

        self._serve.run(InferenceDeployment.bind(), name=config.model_id)
        logger.info(
            "Model '%s' deployed with %d replicas at %s",
            config.model_id, config.num_replicas, config.route_prefix,
        )
        return config.model_id

    def list_deployments(self) -> List[str]:
        if self._serve is None:
            return []
        try:
            return list(self._serve.status().applications.keys())
        except Exception:
            return []

    def delete_deployment(self, name: str) -> None:
        if self._serve:
            self._serve.delete(name)
            logger.info("Deployment '%s' deleted.", name)
