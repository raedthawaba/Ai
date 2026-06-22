"""
test_quantization.py — Unit tests for Hajeen quantization.
"""

import pytest
import torch
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.quantization.quantizer import HajeenQuantizer, QuantizationConfig


@pytest.fixture
def tiny_model():
    cfg = HajeenConfig(
        vocab_size=256, d_model=64, n_layers=2, n_heads=4,
        d_ff=128, max_seq_len=32, dropout=0.0,
    )
    return HajeenForCausalLM(cfg)


class TestHajeenQuantizer:

    def test_fp32(self, tiny_model):
        q = HajeenQuantizer(QuantizationConfig(dtype="float32"))
        qm = q.quantize(tiny_model)
        ids = torch.randint(0, 256, (1, 8))
        out = qm(ids)
        assert out["logits"].shape == (1, 8, 256)

    def test_fp16(self, tiny_model):
        q = HajeenQuantizer(QuantizationConfig(dtype="float16"))
        qm = q.quantize(tiny_model)
        # Model should be in half precision
        param = next(qm.parameters())
        assert param.dtype == torch.float16

    def test_int8_forward(self, tiny_model):
        q = HajeenQuantizer(QuantizationConfig(dtype="int8"))
        qm = q.quantize(tiny_model)
        ids = torch.randint(0, 256, (1, 4))
        out = qm(ids)
        assert out["logits"].shape == (1, 4, 256)
        assert not torch.isnan(out["logits"]).any()

    def test_int4_forward(self, tiny_model):
        q = HajeenQuantizer(QuantizationConfig(dtype="int4", group_size=16))
        qm = q.quantize(tiny_model)
        ids = torch.randint(0, 256, (1, 4))
        out = qm(ids)
        assert out["logits"].shape == (1, 4, 256)
        assert not torch.isnan(out["logits"]).any()

    def test_unknown_dtype_raises(self, tiny_model):
        q = HajeenQuantizer(QuantizationConfig(dtype="int3"))
        with pytest.raises(ValueError, match="Unknown dtype"):
            q.quantize(tiny_model)

    def test_memory_usage_positive(self, tiny_model):
        q = HajeenQuantizer()
        mb = q.memory_usage_mb(tiny_model)
        assert mb > 0

    def test_int8_smaller_than_fp32(self, tiny_model):
        import copy
        q8 = HajeenQuantizer(QuantizationConfig(dtype="int8"))
        q_model = q8.quantize(copy.deepcopy(tiny_model))
        fp32_mb = q8.memory_usage_mb(tiny_model)
        int8_mb = q8.memory_usage_mb(q_model)
        # INT8 should use less memory
        assert int8_mb < fp32_mb


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
