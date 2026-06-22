"""
GPU Tests — validates GPU detection, inference correctness, and performance.
"""
import os
import time
from typing import Any, Dict, List

import pytest


def has_gpu() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


@pytest.mark.skipif(not has_gpu(), reason="No GPU available")
def test_gpu_available() -> None:
    import torch
    device_count = torch.cuda.device_count()
    assert device_count > 0, "No CUDA devices found"
    for i in range(device_count):
        props = torch.cuda.get_device_properties(i)
        print(f"\nGPU {i}: {props.name}, {props.total_memory / 1024**3:.1f}GB")
        assert props.total_memory > 2 * 1024**3, f"GPU {i} has insufficient memory"


@pytest.mark.skipif(not has_gpu(), reason="No GPU available")
def test_tensor_operations() -> None:
    import torch
    device = torch.device("cuda:0")

    a = torch.randn(1024, 1024, device=device, dtype=torch.float16)
    b = torch.randn(1024, 1024, device=device, dtype=torch.float16)

    torch.cuda.synchronize()
    start = time.perf_counter()
    c = torch.matmul(a, b)
    torch.cuda.synchronize()
    duration_ms = (time.perf_counter() - start) * 1000

    assert c.shape == (1024, 1024)
    assert not torch.isnan(c).any(), "NaN values in GPU computation"
    print(f"\nMatrix multiply 1024x1024 (fp16): {duration_ms:.2f}ms")
    assert duration_ms < 100, f"GPU matrix multiply too slow: {duration_ms:.2f}ms"


@pytest.mark.skipif(not has_gpu(), reason="No GPU available")
def test_gpu_memory_management() -> None:
    import gc
    import torch

    device = torch.device("cuda:0")
    initial_allocated = torch.cuda.memory_allocated(device)

    tensors = [torch.randn(256, 256, 256, device=device, dtype=torch.float32) for _ in range(10)]
    peak_allocated = torch.cuda.memory_allocated(device)

    del tensors
    gc.collect()
    torch.cuda.empty_cache()

    final_allocated = torch.cuda.memory_allocated(device)
    leaked_mb = (final_allocated - initial_allocated) / 1024**2

    print(f"\nMemory: peak={peak_allocated/1024**2:.0f}MB, final={final_allocated/1024**2:.0f}MB, leaked={leaked_mb:.1f}MB")
    assert leaked_mb < 10, f"GPU memory leak detected: {leaked_mb:.1f}MB"


@pytest.mark.skipif(not has_gpu(), reason="No GPU available")
def test_inference_throughput() -> None:
    import torch
    device = torch.device("cuda:0")
    N = 100
    batch_size = 8
    seq_len = 512

    dummy_input = torch.randint(0, 32000, (batch_size, seq_len), device=device)
    emb = torch.nn.Embedding(32000, 512).to(device).half()

    torch.cuda.synchronize()
    start = time.perf_counter()
    with torch.no_grad():
        for _ in range(N):
            out = emb(dummy_input)
    torch.cuda.synchronize()
    total_s = time.perf_counter() - start

    tokens_per_second = (N * batch_size * seq_len) / total_s
    print(f"\nEmbedding throughput: {tokens_per_second:.0f} tokens/sec")
    assert tokens_per_second > 100_000, f"Insufficient GPU throughput: {tokens_per_second:.0f} tok/s"
