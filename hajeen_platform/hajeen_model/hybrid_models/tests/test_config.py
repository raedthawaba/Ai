"""
test_config.py — Unit tests for HajeenConfig.
"""

import json
import os
import tempfile
import pytest
from hajeen_model.config.hajeen_config import HajeenConfig


class TestHajeenConfig:

    def test_defaults(self):
        cfg = HajeenConfig()
        assert cfg.vocab_size == 32_000
        assert cfg.d_model == 512
        assert cfg.n_layers == 6
        assert cfg.n_heads == 8
        assert cfg.max_seq_len == 2048

    def test_head_dim(self):
        cfg = HajeenConfig(d_model=512, n_heads=8)
        assert cfg.head_dim == 64

    def test_effective_kv_heads_default(self):
        cfg = HajeenConfig(n_heads=8, n_kv_heads=None)
        assert cfg.effective_kv_heads == 8

    def test_effective_kv_heads_gqa(self):
        cfg = HajeenConfig(n_heads=8, n_kv_heads=2)
        assert cfg.effective_kv_heads == 2

    def test_validate_ok(self):
        cfg = HajeenConfig(d_model=512, n_heads=8)
        cfg.validate()  # should not raise

    def test_validate_bad_head_split(self):
        cfg = HajeenConfig(d_model=512, n_heads=7)  # 512 not divisible by 7
        with pytest.raises(ValueError, match="divisible"):
            cfg.validate()

    def test_validate_bad_kv_heads(self):
        cfg = HajeenConfig(n_heads=8, n_kv_heads=3)  # 8 not divisible by 3
        with pytest.raises(ValueError, match="divisible"):
            cfg.validate()

    def test_to_dict(self):
        cfg = HajeenConfig()
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert d["vocab_size"] == 32_000
        assert d["d_model"] == 512

    def test_from_dict(self):
        original = HajeenConfig(d_model=1024, n_heads=16, n_layers=12)
        restored = HajeenConfig.from_dict(original.to_dict())
        assert restored.d_model == 1024
        assert restored.n_heads == 16
        assert restored.n_layers == 12

    def test_json_roundtrip(self):
        cfg = HajeenConfig(d_model=768, n_layers=10, vocab_size=50_000)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.json")
            cfg.to_json(path)
            assert os.path.exists(path)
            restored = HajeenConfig.from_json(path)
        assert restored.d_model == 768
        assert restored.n_layers == 10
        assert restored.vocab_size == 50_000

    def test_preset_100m(self):
        cfg = HajeenConfig.from_preset("100M")
        assert cfg.d_model == 512
        assert cfg.n_layers == 12
        assert cfg.model_name == "hajeen-100m"

    def test_preset_7b(self):
        cfg = HajeenConfig.from_preset("7B")
        assert cfg.d_model == 4096
        assert cfg.n_heads == 32
        assert cfg.n_kv_heads == 8

    def test_preset_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            HajeenConfig.from_preset("999B")

    def test_repr(self):
        cfg = HajeenConfig()
        s = repr(cfg)
        assert "HajeenConfig" in s
        assert "512" in s

    @pytest.mark.parametrize("preset", ["100M", "300M", "1B", "3B", "7B"])
    def test_all_presets_valid(self, preset):
        cfg = HajeenConfig.from_preset(preset)
        cfg.validate()  # should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
