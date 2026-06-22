"""
test_checkpoint.py — Unit tests for CheckpointManager.
"""

import os
import tempfile
import pytest
import torch
from hajeen_model.config.hajeen_config import HajeenConfig
from hajeen_model.transformer.hajeen_model import HajeenForCausalLM
from hajeen_model.checkpoints.checkpoint_manager import CheckpointManager


@pytest.fixture
def tiny_model():
    cfg = HajeenConfig(
        vocab_size=256, d_model=64, n_layers=2, n_heads=4,
        d_ff=128, max_seq_len=32,
    )
    return HajeenForCausalLM(cfg)


class TestCheckpointManager:

    def test_save_creates_directory(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=3)
            mgr.save(tiny_model, step=100)
            assert os.path.exists(os.path.join(d, "checkpoints", "step_000000100"))

    def test_save_creates_model_pt(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=3)
            mgr.save(tiny_model, step=200)
            ckpt_dir = os.path.join(d, "checkpoints", "step_000000200")
            assert os.path.exists(os.path.join(ckpt_dir, "model.pt"))
            assert os.path.exists(os.path.join(ckpt_dir, "meta.json"))

    def test_load_restores_weights(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=3)
            mgr.save(tiny_model, step=300)

            # Modify the model
            for p in tiny_model.parameters():
                p.data.fill_(999.0)

            # Load should restore original weights
            meta = mgr.load(tiny_model, step=300)
            assert meta is not None
            assert meta["step"] == 300

            # Weights should not be 999.0 anymore
            first_param = next(tiny_model.parameters())
            assert not (first_param == 999.0).all()

    def test_load_latest(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=5)
            mgr.save(tiny_model, step=100)
            mgr.save(tiny_model, step=200)
            mgr.save(tiny_model, step=300)

            meta = mgr.load_latest(tiny_model)
            assert meta["step"] == 300

    def test_keep_n_removes_old(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=2)
            mgr.save(tiny_model, step=100)
            mgr.save(tiny_model, step=200)
            mgr.save(tiny_model, step=300)

            # Only 2 most recent should remain
            steps = mgr._saved_steps()
            assert 100 not in steps
            assert 200 in steps
            assert 300 in steps

    def test_list_checkpoints(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=10)
            mgr.save(tiny_model, step=100)
            mgr.save(tiny_model, step=200)
            ckpts = mgr.list_checkpoints()
            assert len(ckpts) == 2
            steps = [c["step"] for c in ckpts]
            assert 100 in steps
            assert 200 in steps

    def test_load_missing_returns_none(self, tiny_model):
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=3)
            meta = mgr.load_latest(tiny_model)
            assert meta is None

    def test_save_with_optimizer(self, tiny_model):
        from torch.optim import AdamW
        opt = AdamW(tiny_model.parameters(), lr=1e-4)
        with tempfile.TemporaryDirectory() as d:
            mgr = CheckpointManager(d, keep_n=3)
            mgr.save(tiny_model, optimizer=opt, step=500)
            ckpt_dir = os.path.join(d, "checkpoints", "step_000000500")
            assert os.path.exists(os.path.join(ckpt_dir, "optimizer.pt"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
