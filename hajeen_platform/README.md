# Hajeen AI Platform — Phase 9: AI Core Layer

A production-ready, multi-layer AI platform built with FastAPI, covering the full lifecycle from inference to fine-tuning and autonomous agents.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run tests
pytest tests/ -v --tb=short

# Run AI-specific tests only
pytest tests/ai/ -v

# Type-check
mypy . --ignore-missing-imports
```

---

## Phase 9 Architecture

```
hajeen_platform/
├── core/
│   ├── tokenizer/          # Tokenization pipeline (tiktoken / HF)
│   ├── model/              # Model registry, loader, config
│   ├── prompts/            # PromptBuilder, templates, conversation formatter
│   ├── memory/             # Short-term + long-term session memory
│   ├── utils/              # GPU utils, async helpers, logging
│   ├── inference_engine/   # InferenceConfig, Sampler, StoppingCriteria,
│   │                       # ResponseParser, ContextManager, BatchProcessor
│   ├── embeddings/         # EmbeddingEngine, cache, batch embedder, similarity
│   └── training_engine/    # Trainer, LoRATrainer, FineTuner, DatasetLoader,
│                           # CheckpointManager, TrainingMetrics, Evaluator, Collator
│
├── services/
│   ├── rag/                # SemanticRetriever, CrossEncoderReranker, ContextBuilder,
│   │   │                   # CitationBuilder, HybridSearcher, RAGPipeline
│   ├── agents/             # BaseAgent, PlannerAgent, RetrievalAgent, ExecutionAgent,
│   │   │                   # MemoryAgent, ToolAgent, AgentOrchestrator
│   ├── data_service/       # DatasetBuilder, Cleaner, Formatter, InstructionBuilder,
│   │                       # ConversationBuilder, DatasetExporter
│   ├── inference_service.py    # High-level sync/async inference wrapper
│   ├── completion_service.py   # OpenAI-compatible text completion
│   ├── embedding_service.py    # Embedding generation with usage tracking
│   ├── memory_service.py       # Session memory facade
│   ├── moderation_service.py   # Content safety filtering
│   └── rag_service.py          # Full RAG pipeline orchestrator
│
├── api/v1/ai/
│   ├── chat.py             # POST /ai/chat, /ai/chat/stream
│   ├── completion.py       # POST /ai/completion, /ai/completion/stream
│   ├── embeddings.py       # POST /ai/embeddings
│   ├── rerank.py           # POST /ai/rerank
│   ├── models.py           # GET /ai/models, /ai/models/{id}
│   ├── health.py           # GET /ai/health
│   └── router.py           # Mounts all sub-routers + Phase 8 endpoints
│
├── monitoring/ai/
│   ├── inference_metrics.py    # Per-request inference tracking
│   ├── token_metrics.py        # Token usage by model/session/day
│   ├── latency_tracker.py      # Latency percentiles (p50/p95/p99)
│   ├── gpu_monitor.py          # GPU utilization + memory
│   ├── hallucination_tracker.py # Output quality flags
│   └── evaluation_dashboard.py  # Unified metrics dashboard (singleton)
│
└── tests/ai/
    ├── test_inference.py   # InferenceConfig, Sampler, StoppingCriteria,
    │                       # ResponseParser, ContextManager
    ├── test_embeddings.py  # EmbeddingCache, SimilarityScorer, BatchEmbedder
    ├── test_rag.py         # SemanticRetriever, Reranker, ContextBuilder,
    │                       # CitationBuilder, HybridSearcher
    ├── test_chat.py        # Memory, PromptBuilder, Templates, Moderation
    ├── test_training.py    # DatasetLoader, CheckpointManager, TrainingMetrics,
    │                       # DatasetCleaner, Formatter, Exporter
    └── test_agents.py      # All agent types + orchestrator
```

---

## API Endpoints (Phase 9)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ai/chat` | Chat completion with history |
| POST | `/api/ai/chat/stream` | Streaming chat (SSE) |
| POST | `/api/ai/completion` | Raw text completion |
| POST | `/api/ai/completion/stream` | Streaming completion |
| POST | `/api/ai/embeddings` | Batch text embeddings |
| POST | `/api/ai/rerank` | Document reranking |
| GET  | `/api/ai/models` | List available models |
| GET  | `/api/ai/models/{id}` | Get model info |
| GET  | `/api/ai/health` | AI subsystem health |

---

## Key Components

### Inference Engine (`core/inference_engine/`)
- **InferenceConfig** — typed config with presets: `greedy()`, `creative()`, `precise()`
- **Sampler** — temperature scaling, top-k, top-p, nucleus, repetition penalty
- **StoppingCriteria** — max tokens, stop sequences, EOS token, custom predicates
- **ResponseParser** — clean text, extract JSON/code blocks/lists, structured output
- **ContextManager** — token budget tracking and text truncation
- **BatchInferenceProcessor** — concurrent batch inference with semaphore control

### Embedding Engine (`core/embeddings/`)
- **EmbeddingEngine** — singleton, lazy-loaded sentence-transformers model
- **EmbeddingCache** — LRU cache with hit-rate tracking
- **BatchEmbedder** — chunked batch embedding with document support
- **SimilarityScorer** — cosine similarity, ranking, nearest-neighbor search

### RAG Engine (`services/rag/`)
- **SemanticRetriever** — FAISS-backed dense vector retrieval
- **CrossEncoderReranker** — cross-encoder reranking with keyword fallback
- **HybridSearcher** — RRF fusion of dense + sparse retrieval
- **CitationBuilder** — inline citations and reference list generation
- **RAGService** — full orchestration: retrieve → rerank → build → generate

### Training Engine (`core/training_engine/`)
- **Trainer** — HuggingFace Trainer wrapper with configurable args
- **LoRATrainer** — PEFT LoRA fine-tuning with merge support
- **FineTuner** — end-to-end fine-tuning orchestrator
- **DatasetLoader** — JSONL, JSON, Parquet, HuggingFace Hub
- **CheckpointManager** — save, load, list, delete model checkpoints
- **TrainingMetrics** — loss tracking, perplexity, eval history
- **Evaluator** — perplexity, BLEU, generation benchmarks
- **InstructionDataCollator** — response masking for instruction tuning

### Agent System (`services/agents/`)
- **PlannerAgent** — LLM or heuristic goal decomposition
- **RetrievalAgent** — RAG-backed information gathering
- **ExecutionAgent** — step-by-step plan execution with tool calls
- **MemoryAgent** — persistent cross-session memory management
- **ToolAgent** — autonomous LLM-driven tool selection and invocation
- **AgentOrchestrator** — configurable multi-agent pipelines

### Dataset Builder (`services/data_service/`)
- **DatasetBuilder** — instruction + chat dataset construction
- **DatasetCleaner** — text normalization, deduplication, language filtering
- **DatasetFormatter** — Alpaca, ChatML, Llama-3, Mistral, ShareGPT formats
- **InstructionBuilder** — Q/A pairs, summaries, augmentation
- **ConversationBuilder** — multi-turn conversations, sliding windows
- **DatasetExporter** — JSONL, JSON, Parquet, HuggingFace Dataset export

### AI Monitoring (`monitoring/ai/`)
- **AIEvaluationDashboard** — unified singleton for all metrics
- **InferenceMetrics** — request-level success/error/latency tracking
- **TokenMetrics** — token usage by model, session, and day
- **LatencyTracker** — windowed percentile computation (p50/p95/p99)
- **GPUMonitor** — device-level utilization and memory
- **HallucinationTracker** — rule-based output quality scoring

---

## Environment Variables

```env
# Required
DATABASE_URL=postgresql://user:pass@localhost:5432/hajeen_db
SECRET_KEY=your-secret-key-here

# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
GOOGLE_API_KEY=...

# Optional
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4o-mini
MAX_CONTEXT_TOKENS=8192
VECTOR_STORE_PATH=storage_data/vector_store
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Pydantic v2 |
| LLM | OpenAI / Anthropic / Groq / HuggingFace |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS |
| Database | PostgreSQL + Drizzle ORM |
| Fine-tuning | HuggingFace Transformers + PEFT (LoRA) |
| Task Queue | Celery + Redis |
| Monitoring | Custom metrics + optional Prometheus |
| Tests | pytest + pytest-asyncio |

---

## Phase History

| Phase | Description |
|-------|-------------|
| 1–3 | Foundation: FastAPI scaffold, Auth, User management |
| 4–5 | Database layer: PostgreSQL, Drizzle ORM, migrations |
| 6–7 | Knowledge base: FAISS vector store, document ingestion |
| 8 | LLM integration: multi-provider inference engine, RAG pipeline |
| **9** | **AI Core: Inference engine, Embeddings, Training, Agents, Monitoring** |

---

## Phase 10 — Production Infrastructure

This phase adds enterprise-grade production infrastructure:

### What's Included

| Section | Description |
|---------|-------------|
| **10.1 Docker** | Multi-stage production Dockerfiles (API, Worker, Inference, Training, CUDA) |
| **10.2 Kubernetes** | Full K8s manifests: Deployments, Services, HPA, PVC, Ingress |
| **10.3 Distributed Workers** | GPU/CPU workers, queue routing, retry manager, scheduler |
| **10.4 Inference Serving** | vLLM, llama.cpp, batching engine, streaming, model pool |
| **10.5 CI/CD** | GitHub Actions: test, lint, docker, deploy, security, release |
| **10.6 Monitoring** | Prometheus, Grafana, Loki, Tempo, alert rules, dashboards |
| **10.7 Security** | JWT, API keys (hashed), RBAC, rate limiting, audit log, IP filter |
| **10.8 Multi-Tenant** | Tenant manager, quotas, isolation, billing tracker |
| **10.9 Distributed Storage** | Shard manager, replication, backup, DR, distributed cache |
| **10.10 AI Optimization** | Quantization (GPTQ/AWQ/INT4), KV cache, speculative decoding, tensor parallel |
| **10.11 Production Tests** | Load tests (locust), stress tests, failover tests, security tests, GPU tests |
| **10.12 Deployment** | Helm charts, deployment guide, DR guide, performance benchmarks |

### Quick Start (Production)

```bash
# 1. Deploy to Kubernetes
helm upgrade --install hajeen ./helm/hajeen-platform \
  --namespace hajeen-platform \
  --values helm/hajeen-platform/values.yaml

# 2. Verify deployment
kubectl get pods -n hajeen-platform

# 3. Run production tests
pytest tests/production/ -v

# 4. Run load test
locust -f tests/production/load/test_api_load.py \
  --users 1000 --spawn-rate 50 \
  --host http://api.hajeen.ai
```
