# Hajeen Foundation Model

> نموذج لغوي كبير مستقل مبني من الصفر — يدعم العربية والإنجليزية والأكواد البرمجية والنصوص المختلطة.

A fully independent Large Language Model framework built from scratch using PyTorch only.
No Llama, Qwen, Mistral, or any other pretrained weights are used.

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Train a tokenizer

```bash
python -m hajeen_model.tokenizer.train_tokenizer \
    --input_files data/arabic.txt data/english.txt data/code.txt \
    --output_dir tokenizer_model/ \
    --vocab_size 32000
```

### 3. Build and train a model

```python
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer
from hajeen_model.datasets.dataset_builder import DatasetBuilder
from hajeen_model.training.training_pipeline import TrainingPipeline, TrainingConfig

# Load tokenizer
tokenizer = HajeenTokenizer.from_pretrained("tokenizer_model/")

# Choose a model scale
config = HajeenConfig.from_preset("1B")   # or "100M", "7B", etc.

# Build model
model = HajeenForCausalLM(config)
print(model)  # HajeenForCausalLM(params=1.00B, ...)

# Build dataset
builder = DatasetBuilder(tokenizer, max_seq_len=config.max_seq_len)
train_ds, val_ds = builder.build(["data/arabic.txt", "data/english.txt"])

# Train
train_config = TrainingConfig(
    output_dir="outputs/hajeen_1b/",
    batch_size=4,
    gradient_accumulation_steps=8,
    max_steps=100_000,
    learning_rate=3e-4,
)
pipeline = TrainingPipeline(model, tokenizer, train_ds, val_ds, train_config)
pipeline.train()
```

### 4. Run inference

```python
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer
from hajeen_model.inference.inference_engine import InferenceEngine, GenerationConfig

model = HajeenForCausalLM.from_pretrained("outputs/hajeen_1b/")
tokenizer = HajeenTokenizer.from_pretrained("tokenizer_model/")
engine = InferenceEngine(model, tokenizer)

# Generate text
text = engine.generate(
    "الذكاء الاصطناعي هو",
    GenerationConfig(do_sample=True, temperature=0.8, max_new_tokens=100)
)
print(text)

# Streaming generation
for chunk in engine.stream("Explain transformers:", GenerationConfig(max_new_tokens=200)):
    print(chunk, end="", flush=True)
```

### 5. Quantize for deployment

```python
from hajeen_model.quantization.quantizer import HajeenQuantizer, QuantizationConfig

quantizer = HajeenQuantizer(QuantizationConfig(dtype="int8"))
quantized_model = quantizer.quantize(model)
quantizer.print_memory_usage(model, quantized_model)
```

### 6. Export to ONNX

```python
from hajeen_model.export.exporter import HajeenExporter, ExportConfig

exporter = HajeenExporter(model, tokenizer, ExportConfig(output_dir="exports/"))
exporter.export_onnx("exports/hajeen.onnx")
exporter.export_full("exports/hajeen_full/")
```

### 7. Serve via REST API

```bash
python -m hajeen_model.serving.model_server \
    --model_dir outputs/hajeen_1b/ \
    --tokenizer_dir tokenizer_model/ \
    --host 0.0.0.0 \
    --port 8080
```

Endpoints:
- `GET  /health`
- `GET  /model/info`
- `POST /generate`           — `{"prompt": "...", "max_new_tokens": 200}`
- `POST /generate/batch`     — `{"prompts": ["...", "..."]}`
- `POST /generate/stream`    — Server-Sent Events

### 8. Run tests

```bash
# All tests
pytest hajeen_model/tests/ -v

# Specific module
pytest hajeen_model/tests/test_model.py -v
pytest hajeen_model/tests/test_tokenizer.py -v
```

---

## Model Presets

```python
config = HajeenConfig.from_preset("100M")  # Development / testing
config = HajeenConfig.from_preset("300M")  # Small production model
config = HajeenConfig.from_preset("1B")    # Recommended starting point
config = HajeenConfig.from_preset("3B")    # Higher quality
config = HajeenConfig.from_preset("7B")    # State-of-the-art range
config = HajeenConfig.from_preset("13B")   # Large model
config = HajeenConfig.from_preset("70B")   # Very large model
```

---

## Architecture Highlights

| Feature | Choice | Reason |
|---------|--------|--------|
| Positional encoding | RoPE | Better length generalization |
| Normalization | RMSNorm | Faster than LayerNorm |
| FFN type | SwiGLU | Higher quality than standard FFN |
| Attention | GQA support | Reduces KV memory in large models |
| Weight tying | Yes | LM head = embedding matrix |
| Causal mask | Upper-triangular | Autoregressive generation |

---

## File Structure

```
hajeen_model/
├── config/
│   └── hajeen_config.py      ← HajeenConfig (all architecture params)
├── tokenizer/
│   ├── bpe_tokenizer.py      ← BPE training from scratch
│   ├── tokenizer_loader.py   ← HajeenTokenizer (unified API)
│   ├── train_tokenizer.py    ← CLI training script
│   └── tokenizer_validator.py
├── embeddings/
│   ├── token_embeddings.py
│   ├── position_embeddings.py
│   └── rope.py               ← Rotary Position Embedding
├── attention/
│   ├── scaled_dot_product.py ← Core attention + causal mask
│   ├── multi_head_attention.py
│   └── kv_cache.py           ← KV cache for inference
├── layers/
│   ├── normalization.py      ← RMSNorm + LayerNorm
│   ├── feed_forward.py       ← SwiGLU FFN
│   └── residual.py           ← Pre-norm residual connection
├── transformer/
│   ├── transformer_block.py  ← Single decoder block
│   └── hajeen_model.py       ← HajeenModel + HajeenForCausalLM
├── datasets/
│   ├── dataset_builder.py    ← Load, tokenize, chunk, split
│   ├── dataset_cleaner.py    ← Arabic/English text cleaning
│   ├── dataset_validator.py  ← Quality checks
│   └── dataset_statistics.py ← Token counts, perplexity estimates
├── training/
│   └── training_pipeline.py  ← Full training loop (AMP, schedule, etc.)
├── inference/
│   └── inference_engine.py   ← All decoding strategies + streaming
├── evaluation/
│   └── evaluation_pipeline.py ← Perplexity, accuracy, BLEU
├── checkpoints/
│   └── checkpoint_manager.py ← Save/load/resume checkpoints
├── export/
│   └── exporter.py           ← TorchScript + ONNX export
├── quantization/
│   └── quantizer.py          ← FP16, BF16, INT8, INT4
├── serving/
│   └── model_server.py       ← Flask REST API
├── tests/
│   ├── test_config.py
│   ├── test_tokenizer.py
│   ├── test_model.py
│   ├── test_attention.py
│   ├── test_layers.py
│   ├── test_inference.py
│   ├── test_quantization.py
│   ├── test_checkpoint.py
│   └── test_datasets.py
└── docs/
    ├── README.md             ← This file
    └── architecture.md       ← Architecture diagrams
```

---

## Engineering Rules Compliance

1. ✅ **No pretrained weights** — zero dependency on Llama, Qwen, Mistral, or Gemma
2. ✅ **PyTorch only** — no HuggingFace Transformers, no SentencePiece required
3. ✅ **Fully documented** — every class and function has docstrings
4. ✅ **Unit tests** — 9 test files covering all modules
5. ✅ **Scalable** — 100M → 70B via `HajeenConfig.from_preset()`
6. ✅ **Hajeen platform ready** — `HajeenForCausalLM.from_pretrained()` for easy loading
7. ✅ **Production ready** — checkpoint management, quantization, ONNX export, REST API

---

## License

MIT © Hajeen Team
