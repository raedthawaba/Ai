from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class K8sPodConfig:
    name: str
    image: str
    replicas: int = 1
    gpu_limit: int = 1
    cpu_limit: str = "4"
    memory_limit: str = "16Gi"
    cpu_request: str = "1"
    memory_request: str = "4Gi"
    env_vars: Dict[str, str] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)
    port: int = 8080


@dataclass
class K8sServiceConfig:
    name: str
    selector: Dict[str, str]
    port: int = 80
    target_port: int = 8080
    service_type: str = "ClusterIP"


class KubernetesRuntimeManager:
    """
    Manager for Kubernetes-native AI runtime.
    Generates K8s manifests and optionally applies them via the kubernetes Python client.
    """

    def __init__(self, namespace: str = "hajeen-ai") -> None:
        self.namespace = namespace
        self._k8s_client: Optional[Any] = None
        self._apps_v1: Optional[Any] = None
        self._core_v1: Optional[Any] = None

    def connect(self, in_cluster: bool = False) -> bool:
        """Connect to the Kubernetes API server."""
        try:
            from kubernetes import client, config as k8s_config
            if in_cluster:
                k8s_config.load_incluster_config()
            else:
                k8s_config.load_kube_config()
            self._k8s_client = client
            self._apps_v1 = client.AppsV1Api()
            self._core_v1 = client.CoreV1Api()
            logger.info("Connected to Kubernetes cluster (in_cluster=%s).", in_cluster)
            return True
        except ImportError:
            logger.warning("kubernetes Python client not installed. Manifest-only mode.")
            return False
        except Exception as exc:
            logger.warning("K8s connection failed: %s. Manifest-only mode.", exc)
            return False

    # ── Manifest Generation ───────────────────────────────────────────────

    def generate_deployment_yaml(self, config: K8sPodConfig) -> str:
        """Generate a K8s Deployment YAML for an AI worker pod."""
        env = [{"name": k, "value": v} for k, v in config.env_vars.items()]
        labels = {"app": config.name, **config.labels}

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": config.name, "namespace": self.namespace, "labels": labels},
            "spec": {
                "replicas": config.replicas,
                "selector": {"matchLabels": {"app": config.name}},
                "template": {
                    "metadata": {"labels": {"app": config.name}},
                    "spec": {
                        "containers": [{
                            "name": "ai-worker",
                            "image": config.image,
                            "ports": [{"containerPort": config.port}],
                            "env": env,
                            "resources": {
                                "requests": {
                                    "cpu": config.cpu_request,
                                    "memory": config.memory_request,
                                },
                                "limits": {
                                    "cpu": config.cpu_limit,
                                    "memory": config.memory_limit,
                                    "nvidia.com/gpu": config.gpu_limit,
                                },
                            },
                        }]
                    },
                },
            },
        }
        return yaml.dump(deployment, default_flow_style=False)

    def generate_service_yaml(self, config: K8sServiceConfig) -> str:
        """Generate a K8s Service YAML."""
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": config.name, "namespace": self.namespace},
            "spec": {
                "type": config.service_type,
                "selector": config.selector,
                "ports": [{
                    "port": config.port,
                    "targetPort": config.target_port,
                    "protocol": "TCP",
                }],
            },
        }
        return yaml.dump(service, default_flow_style=False)

    def generate_hpa_yaml(
        self, deployment_name: str, min_replicas: int = 1, max_replicas: int = 10, cpu_percent: int = 70
    ) -> str:
        """Generate a HorizontalPodAutoscaler YAML."""
        hpa = {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {"name": f"{deployment_name}-hpa", "namespace": self.namespace},
            "spec": {
                "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": deployment_name},
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "metrics": [{
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {"type": "Utilization", "averageUtilization": cpu_percent},
                    },
                }],
            },
        }
        return yaml.dump(hpa, default_flow_style=False)

    # ── Live Cluster Operations (requires kubernetes client) ─────────────

    def deploy_worker(self, config: K8sPodConfig) -> bool:
        """Deploy a pod to the connected K8s cluster."""
        if self._apps_v1 is None:
            yaml_manifest = self.generate_deployment_yaml(config)
            logger.info(
                "K8s client not connected — manifest generated for '%s':\n%s",
                config.name, yaml_manifest[:300],
            )
            return False

        from kubernetes.client import V1Deployment
        manifest_yaml = self.generate_deployment_yaml(config)
        deployment_dict = yaml.safe_load(manifest_yaml)
        try:
            self._apps_v1.create_namespaced_deployment(
                namespace=self.namespace,
                body=deployment_dict,
            )
            logger.info("Deployment '%s' created in namespace '%s'.", config.name, self.namespace)
            return True
        except Exception as exc:
            logger.error("Failed to deploy '%s': %s", config.name, exc)
            return False

    def scale_deployment(self, name: str, replicas: int) -> bool:
        """Scale a deployment to the given number of replicas."""
        if self._apps_v1 is None:
            logger.warning("K8s client not connected — cannot scale '%s'.", name)
            return False
        try:
            self._apps_v1.patch_namespaced_deployment_scale(
                name=name,
                namespace=self.namespace,
                body={"spec": {"replicas": replicas}},
            )
            logger.info("Deployment '%s' scaled to %d replicas.", name, replicas)
            return True
        except Exception as exc:
            logger.error("Scale failed for '%s': %s", name, exc)
            return False

    def list_deployments(self) -> List[str]:
        """List deployment names in the managed namespace."""
        if self._apps_v1 is None:
            return []
        try:
            deps = self._apps_v1.list_namespaced_deployment(namespace=self.namespace)
            return [d.metadata.name for d in deps.items]
        except Exception as exc:
            logger.error("Failed to list deployments: %s", exc)
            return []

    def get_deployment_status(self, name: str) -> Dict[str, Any]:
        """Get ready/desired replicas for a deployment."""
        if self._apps_v1 is None:
            return {"status": "client_not_connected"}
        try:
            dep = self._apps_v1.read_namespaced_deployment_status(name=name, namespace=self.namespace)
            return {
                "name": name,
                "ready": dep.status.ready_replicas or 0,
                "desired": dep.spec.replicas,
                "available": dep.status.available_replicas or 0,
            }
        except Exception as exc:
            return {"name": name, "error": str(exc)}


class DistributedAgentRouter:
    """Routes tasks to agents running on distributed cluster nodes."""

    def __init__(self) -> None:
        self._registry: Dict[str, str] = {}

    def register(self, agent_id: str, address: str) -> None:
        self._registry[agent_id] = address
        logger.info("Agent '%s' registered at %s", agent_id, address)

    def route(self, agent_id: str, task: Any) -> Dict[str, Any]:
        address = self._registry.get(agent_id)
        if not address:
            raise ValueError(f"Agent '{agent_id}' not found in router registry.")
        logger.info("Routing task to agent '%s' at %s", agent_id, address)
        return {"status": "routed", "agent_id": agent_id, "target": address, "task": str(task)[:100]}

    def list_agents(self) -> List[str]:
        return list(self._registry.keys())
