"""
model_server.py — REST API serving layer for Hajeen Foundation Model.

Provides:
    - POST /generate        — Single prompt generation
    - POST /generate/batch  — Batch generation
    - GET  /generate/stream — Server-Sent Events streaming
    - GET  /health          — Health check
    - GET  /model/info      — Model metadata

Built with Flask (lightweight, no extra framework dependencies).
Swap with FastAPI for production-grade async serving.

Usage:
    server = ModelServer.from_directory("outputs/hajeen_model/")
    server.run(host="0.0.0.0", port=8080)

Or CLI:
    python -m hajeen_model.serving.model_server \
        --model_dir outputs/hajeen_model/ \
        --tokenizer_dir tokenizer_model/ \
        --port 8080
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import List, Optional

# ── Flask import (optional at import time) ────────────────────────────────

try:
    from flask import Flask, Response, jsonify, request, stream_with_context
    _FLASK_AVAILABLE = True
except ImportError:
    _FLASK_AVAILABLE = False


@dataclass
class ServerConfig:
    """Configuration for the Hajeen model server."""
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    max_new_tokens: int = 512
    default_temperature: float = 0.8
    default_top_p: float = 0.95
    default_top_k: int = 50
    max_batch_size: int = 8
    cors_enabled: bool = True


class ModelServer:
    """
    HTTP inference server for HajeenForCausalLM.

    Wraps the InferenceEngine behind a REST API.

    Args:
        engine: Initialized InferenceEngine.
        config: ServerConfig.
    """

    def __init__(self, engine, config: Optional[ServerConfig] = None) -> None:
        if not _FLASK_AVAILABLE:
            raise ImportError(
                "Flask is required for the model server. Install with: pip install flask"
            )
        self.engine = engine
        self.config = config or ServerConfig()
        self.app = Flask("HajeenModelServer")
        self._register_routes()
        self._start_time = time.time()

    def _register_routes(self) -> None:
        if self.config.cors_enabled:
            @self.app.after_request
            def add_cors_headers(response):
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                return response

        self.app.route("/health", methods=["GET"])(self._health)
        self.app.route("/model/info", methods=["GET"])(self._model_info)
        self.app.route("/generate", methods=["POST"])(self._generate)
        self.app.route("/generate/batch", methods=["POST"])(self._generate_batch)
        self.app.route("/generate/stream", methods=["POST"])(self._generate_stream)

    # ── Routes ────────────────────────────────────────────────────────────

    def _health(self):
        """GET /health — liveness check."""
        return jsonify({
            "status": "ok",
            "uptime_seconds": round(time.time() - self._start_time, 1),
        })

    def _model_info(self):
        """GET /model/info — model metadata."""
        config = getattr(self.engine.model, "config", None)
        if config:
            info = config.to_dict()
        else:
            info = {}
        info["tokenizer_vocab_size"] = getattr(self.engine.tokenizer, "vocab_size", None)
        return jsonify(info)

    def _parse_gen_config(self, data: dict):
        from hajeen_model.inference.inference_engine import GenerationConfig
        return GenerationConfig(
            do_sample=data.get("do_sample", True),
            temperature=float(data.get("temperature", self.config.default_temperature)),
            top_p=float(data.get("top_p", self.config.default_top_p)),
            top_k=int(data.get("top_k", self.config.default_top_k)),
            max_new_tokens=min(
                int(data.get("max_new_tokens", 256)),
                self.config.max_new_tokens,
            ),
            repetition_penalty=float(data.get("repetition_penalty", 1.0)),
        )

    def _generate(self):
        """
        POST /generate
        Body: {"prompt": str, "temperature": float, "max_new_tokens": int, ...}
        Response: {"text": str, "prompt": str, "time_ms": int}
        """
        data = request.get_json(force=True, silent=True) or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        gen_config = self._parse_gen_config(data)
        t0 = time.time()
        try:
            text = self.engine.generate(prompt, gen_config)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify({
            "prompt": prompt,
            "text": text,
            "time_ms": round((time.time() - t0) * 1000),
        })

    def _generate_batch(self):
        """
        POST /generate/batch
        Body: {"prompts": List[str], ...generation params...}
        Response: {"results": List[str]}
        """
        data = request.get_json(force=True, silent=True) or {}
        prompts = data.get("prompts", [])
        if not prompts or not isinstance(prompts, list):
            return jsonify({"error": "prompts (list) is required"}), 400

        if len(prompts) > self.config.max_batch_size:
            return jsonify({
                "error": f"Batch size {len(prompts)} exceeds max {self.config.max_batch_size}"
            }), 400

        gen_config = self._parse_gen_config(data)
        t0 = time.time()
        try:
            results = self.engine.generate_batch(prompts, gen_config)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify({
            "results": results,
            "time_ms": round((time.time() - t0) * 1000),
        })

    def _generate_stream(self):
        """
        POST /generate/stream
        Body: {"prompt": str, ...generation params...}
        Response: Server-Sent Events stream of text chunks.
        """
        data = request.get_json(force=True, silent=True) or {}
        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        gen_config = self._parse_gen_config(data)

        def _event_stream():
            try:
                for chunk in self.engine.stream(prompt, gen_config):
                    payload = json.dumps({"text": chunk})
                    yield f"data: {payload}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            stream_with_context(_event_stream()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Run ───────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the Flask server."""
        print("=" * 55)
        print("  Hajeen Foundation Model — Inference Server")
        print("=" * 55)
        print(f"  Host   : {self.config.host}")
        print(f"  Port   : {self.config.port}")
        print(f"  Endpoints:")
        print(f"    GET  http://{self.config.host}:{self.config.port}/health")
        print(f"    GET  http://{self.config.host}:{self.config.port}/model/info")
        print(f"    POST http://{self.config.host}:{self.config.port}/generate")
        print(f"    POST http://{self.config.host}:{self.config.port}/generate/batch")
        print(f"    POST http://{self.config.host}:{self.config.port}/generate/stream")
        print()
        self.app.run(
            host=self.config.host,
            port=self.config.port,
            debug=self.config.debug,
            threaded=True,
        )

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def from_directory(
        cls,
        model_dir: str,
        tokenizer_dir: str,
        server_config: Optional[ServerConfig] = None,
    ) -> "ModelServer":
        """
        Build a ModelServer by loading model and tokenizer from directories.

        Args:
            model_dir: Path to directory created by save_pretrained().
            tokenizer_dir: Path to tokenizer directory.
            server_config: Optional server configuration.
        """
        from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
        from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer
        from hajeen_model.inference.inference_engine import InferenceEngine

        print(f"[ModelServer] Loading model from: {model_dir}")
        model = HajeenForCausalLM.from_pretrained(model_dir)

        print(f"[ModelServer] Loading tokenizer from: {tokenizer_dir}")
        tokenizer = HajeenTokenizer.from_pretrained(tokenizer_dir)

        engine = InferenceEngine(model, tokenizer)
        return cls(engine, server_config)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Start the Hajeen Model Server.")
    parser.add_argument("--model_dir", required=True)
    parser.add_argument("--tokenizer_dir", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--max_new_tokens", type=int, default=512)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    server_config = ServerConfig(
        host=args.host,
        port=args.port,
        max_new_tokens=args.max_new_tokens,
        debug=args.debug,
    )
    server = ModelServer.from_directory(
        args.model_dir,
        args.tokenizer_dir,
        server_config,
    )
    server.run()


if __name__ == "__main__":
    main()
