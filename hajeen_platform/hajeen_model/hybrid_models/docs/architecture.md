# Hajeen Foundation Model — Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    Hajeen Foundation Model Architecture                  │
└──────────────────────────────────────────────────────────────────────────┘

INPUT TEXT (Arabic / English / Code / Mixed)
    │
    ▼
┌───────────────────────────────┐
│         BPE Tokenizer         │  ← train_tokenizer.py
│  (Byte-Pair Encoding)         │  ← Arabic + English + Code support
│  vocab_size = 32,000          │
└───────────────────────────────┘
    │  [token_ids: (batch, seq_len)]
    ▼
┌───────────────────────────────┐
│      Token Embeddings         │  ← token_embeddings.py
│  (batch, seq_len) → (batch, seq_len, d_model)
└───────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              Transformer Stack (n_layers blocks)                          │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                   TransformerBlock × n_layers                        │ │
│  │                                                                       │ │
│  │   x ──► RMSNorm ──► Multi-Head Attention ──► + ──► x'               │ │
│  │              │            │                   │                       │ │
│  │              │     ┌──────┴──────┐            │                       │ │
│  │              │     │  Q  K  V   │            │                       │ │
│  │              │     │ proj proj proj           │                       │ │
│  │              │     │             │            │                       │ │
│  │              │     │   RoPE      │            │                       │ │
│  │              │     │ (Rotary PE) │            │                       │ │
│  │              │     │             │            │                       │ │
│  │              │     │  Scaled     │            │                       │ │
│  │              │     │ Dot-Product │            │                       │ │
│  │              │     │ Attention   │            │                       │ │
│  │              │     │ + Causal    │            │                       │ │
│  │              │     │   Mask      │            │                       │ │
│  │              │     └─────────────┘            │                       │ │
│  │                                               │                       │ │
│  │   x' ──► RMSNorm ──► FeedForward (SwiGLU) ──► + ──► x''             │ │
│  │                         gate_proj × silu(up_proj) → down_proj        │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    ×n_layers                              │
└──────────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌───────────────────────────────┐
│        Final RMSNorm          │
└───────────────────────────────┘
    │
    ▼
┌───────────────────────────────┐
│          LM Head              │  ← Linear(d_model → vocab_size)
│   (weight-tied to embeddings) │
└───────────────────────────────┘
    │  logits: (batch, seq_len, vocab_size)
    ▼
┌───────────────────────────────┐
│    Cross-Entropy Loss         │  ← Training
│    or Sampling/Greedy         │  ← Inference
└───────────────────────────────┘
```

---

## Parameter Scaling

| Preset | d_model | n_layers | n_heads | n_kv_heads | d_ff   | Params (approx) |
|--------|---------|----------|---------|------------|--------|-----------------|
| 100M   | 512     | 12       | 8       | 8          | 2,048  | ~100M           |
| 300M   | 1,024   | 16       | 16      | 16         | 4,096  | ~300M           |
| 1B     | 2,048   | 24       | 16      | 8          | 5,632  | ~1B             |
| 3B     | 3,072   | 32       | 24      | 8          | 8,192  | ~3B             |
| 7B     | 4,096   | 32       | 32      | 8          | 11,008 | ~7B             |
| 13B    | 5,120   | 40       | 40      | 8          | 13,824 | ~13B            |
| 70B    | 8,192   | 80       | 64      | 8          | 28,672 | ~70B            |

---

## Attention: Multi-Head vs Grouped-Query

```
Standard MHA (n_kv_heads == n_heads):
    Q: (B, n_heads, T, head_dim)
    K: (B, n_heads, T, head_dim)
    V: (B, n_heads, T, head_dim)

GQA (n_kv_heads < n_heads):
    Q: (B, n_heads,    T, head_dim)   ← full
    K: (B, n_kv_heads, T, head_dim)   ← fewer heads
    V: (B, n_kv_heads, T, head_dim)   ← fewer heads
    → K/V repeated n_heads/n_kv_heads times for dot-product
```

---

## Positional Encoding: RoPE

```
RoPE rotates Q and K vectors in 2D subspaces:
    θ_i = 1 / (10000 ^ (2i / head_dim))
    f(x, m) = x · e^(i·m·θ)     where m = position index

Key properties:
    ✓ Relative position information (not absolute)
    ✓ No trainable parameters
    ✓ Generalizes to longer sequences at inference
    ✓ Applied inside each attention block (not added to embeddings)
```

---

## FeedForward: SwiGLU Gate

```
Standard FFN:
    output = W2 · act(W1 · x)

SwiGLU (Hajeen default):
    gate  = SiLU(W_gate · x)
    up    = W_up · x
    output = W_down · (gate ⊙ up)

SiLU(x) = x · sigmoid(x)
```

---

## Training Pipeline Flow

```
Raw Text Files (.txt / .jsonl)
    │
    ▼  DatasetCleaner
Cleaned Text
    │
    ▼  BPETokenizer
Token IDs
    │
    ▼  DatasetBuilder
Chunked Sequences (max_seq_len)
    │
    ▼  DataLoader (shuffle, batch, pad)
    │
    ▼  HajeenForCausalLM.forward()
Logits + Loss
    │
    ▼  AMP Scaler + Gradient Accumulation
Scaled Gradients
    │
    ▼  Gradient Clipping → AdamW step
Updated Weights
    │
    ▼  CheckpointManager.save()
Checkpoint
```

---

## Inference: KV Cache

```
Without cache (O(n²) per step):
    step 1: attend over [t0]
    step 2: attend over [t0, t1]
    step 3: attend over [t0, t1, t2]
    ...

With KV cache (O(n) per step):
    step 1: compute K1, V1 → cache[0] = [K1, V1]
    step 2: compute K2, V2 → cache[1] = [K1,K2; V1,V2]
    step 3: only attend Q3 over full cached K/V
    → 2–20x faster generation
```

---

## Quantization Overview

```
FP32  → 4 bytes/param  (default training)
FP16  → 2 bytes/param  (2x reduction, fast on modern GPUs)
BF16  → 2 bytes/param  (better range than FP16)
INT8  → 1 byte/param   (4x reduction, per-channel scale)
INT4  → 0.5 byte/param (8x reduction, grouped quantization)

For a 7B model:
    FP32 → ~28 GB
    FP16 → ~14 GB
    INT8 → ~7 GB
    INT4 → ~3.5 GB
```

---

## Directory Structure

```
hajeen_model/
├── config/          ← HajeenConfig (architecture parameters)
├── tokenizer/       ← BPE tokenizer (train, load, validate)
├── datasets/        ← Data loading, cleaning, validation, statistics
├── embeddings/      ← Token embeddings, positional encoding, RoPE
├── attention/       ← Scaled dot-product, multi-head, KV cache
├── layers/          ← RMSNorm, LayerNorm, FeedForward, Residual
├── transformer/     ← TransformerBlock, HajeenModel, HajeenForCausalLM
├── training/        ← Full training pipeline (AMP, accumulation, schedule)
├── inference/       ← Greedy, top-k, top-p, temperature, streaming
├── evaluation/      ← Perplexity, accuracy, BLEU, benchmarks
├── checkpoints/     ← Save/load/resume training checkpoints
├── export/          ← PyTorch TorchScript + ONNX export
├── quantization/    ← FP16, BF16, INT8, INT4 quantization
├── serving/         ← REST API server (Flask)
├── tests/           ← Unit tests for all modules
└── docs/            ← Architecture diagrams, README
```
