"""
Load Tests — validates API performance under sustained concurrent load.
Uses locust for distributed load generation.
"""
import json
import os
import random
import time

from locust import HttpUser, between, events, task
from locust.runners import MasterRunner


class InferenceUser(HttpUser):
    """Simulates a user making inference requests."""
    wait_time = between(0.1, 1.0)
    host = os.environ.get("LOAD_TEST_HOST", "http://localhost:8000")

    def on_start(self) -> None:
        self.auth_token = self._get_auth_token()
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
            "X-Tenant-ID": "test-tenant",
        }

    def _get_auth_token(self) -> str:
        resp = self.client.post("/api/v1/auth/login", json={
            "email": os.environ.get("TEST_USER_EMAIL", "loadtest@hajeen.ai"),
            "password": os.environ.get("TEST_USER_PASSWORD", "test_password"),
        })
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
        return ""

    @task(10)
    def chat_inference(self) -> None:
        prompts = [
            "What is machine learning?",
            "Explain neural networks briefly.",
            "What is the difference between AI and ML?",
            "How does gradient descent work?",
            "What is a transformer model?",
        ]
        payload = {
            "messages": [{"role": "user", "content": random.choice(prompts)}],
            "model": "default",
            "max_tokens": 256,
            "temperature": 0.7,
        }
        with self.client.post(
            "/api/v1/chat/completions",
            json=payload,
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")

    @task(3)
    def rag_query(self) -> None:
        questions = [
            "How do I integrate the API?",
            "What models are available?",
            "What are the rate limits?",
        ]
        with self.client.post(
            "/api/v1/rag/query",
            json={"query": random.choice(questions), "collection": "docs", "top_k": 5},
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(2)
    def list_models(self) -> None:
        with self.client.get("/api/v1/models", headers=self.headers, catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"HTTP {resp.status_code}")

    @task(1)
    def health_check(self) -> None:
        with self.client.get("/api/v1/health", catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure("Health check failed")


class HeavyInferenceUser(HttpUser):
    """Simulates a power user making large generation requests."""
    wait_time = between(2.0, 5.0)
    host = os.environ.get("LOAD_TEST_HOST", "http://localhost:8000")
    weight = 1

    def on_start(self) -> None:
        self.headers = {"Content-Type": "application/json", "X-Tenant-ID": "test-tenant"}

    @task
    def large_generation(self) -> None:
        with self.client.post(
            "/api/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Write a detailed essay on the history of artificial intelligence spanning 2000 words."}],
                "model": "default",
                "max_tokens": 2048,
            },
            headers=self.headers,
            catch_response=True,
            timeout=120,
        ) as resp:
            if resp.status_code in (200, 429, 503):
                resp.success()
            else:
                resp.failure(f"Large generation failed: {resp.status_code}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    if isinstance(environment.runner, MasterRunner):
        print(f"\n{'='*60}")
        print("LOAD TEST STARTED")
        print(f"Target: {os.environ.get('LOAD_TEST_HOST', 'localhost')}")
        print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    stats = environment.stats
    total = stats.total
    print(f"\n{'='*60}")
    print("LOAD TEST COMPLETE")
    print(f"Total Requests: {total.num_requests}")
    print(f"Failures: {total.num_failures}")
    print(f"Avg Response Time: {total.avg_response_time:.0f}ms")
    print(f"P95 Response Time: {total.get_response_time_percentile(0.95):.0f}ms")
    print(f"P99 Response Time: {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"RPS: {total.current_rps:.1f}")
    print(f"{'='*60}\n")

    if total.fail_ratio > 0.05:
        print(f"FAIL: Error rate {total.fail_ratio:.1%} exceeds 5% threshold")
        raise SystemExit(1)
    if total.get_response_time_percentile(0.99) > 5000:
        print(f"FAIL: P99 latency {total.get_response_time_percentile(0.99):.0f}ms exceeds 5000ms")
        raise SystemExit(1)
    print("PASS: All load test thresholds met")
