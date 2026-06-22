"""9.11 — Training Engine Tests."""
from __future__ import annotations

import json
import os
import tempfile
import pytest
from pathlib import Path

from core.training_engine.dataset_loader import DatasetLoader
from core.training_engine.checkpoint_manager import CheckpointManager
from core.training_engine.metrics import TrainingMetrics
from core.training_engine.evaluator import Evaluator
from core.training_engine.lora_trainer import LoRAConfig
from core.training_engine.trainer import TrainingConfig
from services.data_service.dataset_builder import DatasetBuilder
from services.data_service.dataset_cleaner import DatasetCleaner
from services.data_service.dataset_formatter import DatasetFormatter
from services.data_service.instruction_builder import InstructionBuilder
from services.data_service.conversation_builder import ConversationBuilder
from services.data_service.dataset_exporter import DatasetExporter


class TestDatasetLoader:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.loader = DatasetLoader()

    def test_load_jsonl(self):
        path = os.path.join(self.tmpdir, "test.jsonl")
        with open(path, "w") as f:
            for i in range(5):
                f.write(json.dumps({"text": f"sample {i}", "label": i}) + "\n")
        records = self.loader.load_jsonl(path)
        assert len(records) == 5
        assert records[0]["label"] == 0

    def test_load_json(self):
        path = os.path.join(self.tmpdir, "test.json")
        data = [{"id": 1, "text": "hello"}, {"id": 2, "text": "world"}]
        with open(path, "w") as f:
            json.dump(data, f)
        result = self.loader.load_json(path)
        assert len(result) == 2

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            self.loader.load_jsonl("/nonexistent/path/file.jsonl")

    def test_split_train_eval(self):
        records = [{"id": i} for i in range(100)]
        train, eval_data = self.loader.split_train_eval(records, eval_ratio=0.1)
        assert len(train) == 90
        assert len(eval_data) == 10


class TestCheckpointManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = CheckpointManager(checkpoint_dir=self.tmpdir)

    def test_list_empty(self):
        checkpoints = self.manager.list_checkpoints()
        assert isinstance(checkpoints, list)

    def test_save_creates_directory(self):
        mock_model = type("Model", (), {"save_pretrained": lambda self, p: None})()
        self.manager.save(mock_model, None, step=100, metrics={"loss": 0.5})
        checkpoints = self.manager.list_checkpoints()
        assert len(checkpoints) >= 1

    def test_step_from_name(self):
        assert CheckpointManager._step_from_name("checkpoint-step-100") == 100
        assert CheckpointManager._step_from_name("checkpoint-200") == 200

    def test_load_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            self.manager.load("/nonexistent/checkpoint")


class TestTrainingMetrics:
    def test_record_step(self):
        m = TrainingMetrics()
        m.start()
        m.record_step(step=10, loss=2.5, lr=1e-4, epoch=0.5)
        assert m.current_loss() == pytest.approx(2.5)

    def test_perplexity(self):
        import math
        m = TrainingMetrics()
        m.record_step(1, 1.0, 1e-4, 0.1)
        ppl = m.perplexity()
        assert ppl is not None
        assert abs(ppl - math.exp(1.0)) < 0.1

    def test_summary_keys(self):
        m = TrainingMetrics()
        m.start()
        summary = m.summary()
        assert "total_steps" in summary
        assert "elapsed_seconds" in summary

    def test_history(self):
        m = TrainingMetrics()
        m.record_step(1, 2.0, 1e-4, 0.1)
        m.record_step(2, 1.8, 1e-4, 0.2)
        history = m.to_history()
        assert len(history) == 2


class TestLoRAConfig:
    def test_defaults(self):
        cfg = LoRAConfig()
        assert cfg.r == 16
        assert cfg.lora_alpha == 32
        assert "q_proj" in cfg.target_modules

    def test_custom_config(self):
        cfg = LoRAConfig(r=8, lora_alpha=16)
        assert cfg.r == 8


class TestTrainingConfig:
    def test_defaults(self):
        cfg = TrainingConfig()
        assert cfg.num_epochs == 3
        assert cfg.learning_rate == pytest.approx(2e-4)
        assert cfg.gradient_accumulation_steps == 4


class TestDatasetCleaner:
    def test_clean_text(self):
        cleaner = DatasetCleaner()
        text = "  Hello  \n\n\n  world  \r\n  "
        cleaned = cleaner.clean_text(text)
        assert cleaned == "Hello\n\nworld"

    def test_deduplicate(self):
        cleaner = DatasetCleaner()
        records = [{"text": "duplicate"}, {"text": "duplicate"}, {"text": "unique"}]
        result = cleaner.deduplicate(records)
        assert len(result) == 2

    def test_skip_short_records(self):
        cleaner = DatasetCleaner(min_length=20)
        record = {"text": "short"}
        assert cleaner.clean_record(record) is None

    def test_process_pipeline(self):
        cleaner = DatasetCleaner(min_length=5, remove_duplicates=True)
        records = [
            {"text": "Hello world this is a test"},
            {"text": "Hi"},
            {"text": "Hello world this is a test"},
        ]
        result = cleaner.process(records)
        assert len(result) == 1


class TestDatasetFormatter:
    def test_to_alpaca(self):
        rec = {"instruction": "Explain AI", "input": "", "response": "AI is..."}
        result = DatasetFormatter.to_alpaca(rec)
        assert result["instruction"] == "Explain AI"

    def test_to_alpaca_text_with_input(self):
        rec = {"instruction": "Translate", "input": "Hello", "response": "Hola"}
        text = DatasetFormatter.to_alpaca_text(rec)
        assert "### Instruction:" in text
        assert "### Input:" in text

    def test_to_chatml_from_messages(self):
        rec = {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}
        text = DatasetFormatter.to_chatml(rec)
        assert "<|im_start|>" in text

    def test_batch_format(self):
        formatter = DatasetFormatter()
        records = [{"instruction": f"task {i}", "response": f"answer {i}"} for i in range(3)]
        results = formatter.batch_format(records, fmt="alpaca_text")
        assert len(results) == 3
        assert "text" in results[0]


class TestInstructionBuilder:
    def test_build_qa_pairs(self):
        builder = InstructionBuilder()
        pairs = builder.build_qa_pairs(
            "Python is a language.",
            ["What is Python?"],
            ["Python is a programming language."],
        )
        assert len(pairs) == 1
        assert pairs[0]["instruction"] == "What is Python?"

    def test_build_summary_pairs(self):
        builder = InstructionBuilder()
        docs = ["Long document text here."]
        summaries = ["Short summary."]
        pairs = builder.build_summary_pairs(docs, summaries)
        assert len(pairs) == 1


class TestConversationBuilder:
    def test_from_qa_pairs(self):
        pairs = [{"question": "What is AI?", "answer": "Artificial intelligence."}]
        convos = ConversationBuilder.from_qa_pairs(pairs)
        assert len(convos) == 1
        assert convos[0]["messages"][0]["role"] == "user"

    def test_build_multi_turn(self):
        turns = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        convo = ConversationBuilder.build_multi_turn(turns, system_prompt="Be helpful")
        assert convo["turn_count"] == 2
        assert convo["messages"][0]["role"] == "system"

    def test_to_sharegpt_format(self):
        convos = [
            {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]}
        ]
        result = ConversationBuilder.to_sharegpt_format(convos)
        assert result[0]["conversations"][0]["from"] == "human"


class TestDatasetExporter:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.exporter = DatasetExporter(export_dir=self.tmpdir)

    def test_to_jsonl(self):
        records = [{"text": "hello", "label": 1}]
        path = self.exporter.to_jsonl(records, "test_export")
        assert Path(path).exists()
        with open(path) as f:
            loaded = json.loads(f.readline())
        assert loaded["text"] == "hello"

    def test_to_json(self):
        records = [{"text": "world"}]
        path = self.exporter.to_json(records, "test_json")
        assert Path(path).exists()
