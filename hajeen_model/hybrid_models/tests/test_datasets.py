"""
test_datasets.py — Unit tests for dataset utilities.
"""

import os
import tempfile
import pytest
from hajeen_model.datasets.dataset_cleaner import DatasetCleaner
from hajeen_model.datasets.dataset_validator import DatasetValidator, DatasetReport
from hajeen_model.datasets.dataset_statistics import DatasetStatistics
from hajeen_model.datasets.dataset_builder import HajeenDataset, DatasetBuilder


class TestDatasetCleaner:

    def test_remove_html(self):
        cleaner = DatasetCleaner(min_chars=1, remove_html=True)
        text = "<p>Hello <b>world</b>!</p>"
        result = cleaner.clean(text)
        assert result is not None
        assert "<p>" not in result
        assert "Hello" in result

    def test_remove_diacritics(self):
        cleaner = DatasetCleaner(min_chars=1, remove_diacritics=True)
        text = "مَرْحَباً"
        result = cleaner.clean(text)
        assert result is not None
        # Diacritics should be removed
        assert "َ" not in result

    def test_length_filter_short(self):
        cleaner = DatasetCleaner(min_chars=50)
        result = cleaner.clean("short")
        assert result is None

    def test_length_filter_long(self):
        cleaner = DatasetCleaner(max_chars=10)
        result = cleaner.clean("This is a long enough text to be filtered out by max length")
        assert result is None

    def test_clean_batch(self):
        cleaner = DatasetCleaner(min_chars=5)
        texts = ["Hello world!", "", "ab", "A longer valid text for testing."]
        cleaned = cleaner.clean_batch(texts)
        assert "Hello world!" in cleaned
        assert "" not in cleaned
        assert "ab" not in cleaned

    def test_deduplicate(self):
        cleaner = DatasetCleaner(min_chars=1, deduplicate=True)
        texts = ["Hello world"] * 10
        cleaned = cleaner.clean_batch(texts)
        assert len(cleaned) == 1

    def test_clean_file(self):
        cleaner = DatasetCleaner(min_chars=5)
        with tempfile.TemporaryDirectory() as d:
            inp = os.path.join(d, "input.txt")
            out = os.path.join(d, "output.txt")
            with open(inp, "w") as f:
                f.write("Hello world!\n")
                f.write("ab\n")
                f.write("A valid longer text.\n")
            cleaner.clean_file(inp, out)
            with open(out) as f:
                lines = f.readlines()
            assert len(lines) >= 1


class TestDatasetValidator:

    def test_valid_file(self):
        validator = DatasetValidator(min_lines=3)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "data.txt")
            with open(path, "w") as f:
                for i in range(20):
                    f.write(f"This is line number {i} with enough content.\n")
            report = validator.validate_file(path)
        assert report.valid_lines >= 20

    def test_missing_file(self):
        validator = DatasetValidator()
        report = validator.validate_file("/nonexistent/path.txt")
        assert not report.ok
        assert len(report.issues) > 0

    def test_empty_file(self):
        validator = DatasetValidator()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "empty.txt")
            open(path, "w").close()
            report = validator.validate_file(path)
        assert not report.ok


class TestDatasetStatistics:

    def test_compute(self):
        seqs = [[1, 2, 3, 4, 5], [1, 2], [3, 4, 5, 6, 7, 8]]
        stats = DatasetStatistics()
        stats.compute(seqs)
        assert stats.total_sequences == 3
        assert stats.total_tokens == 13

    def test_avg_len(self):
        seqs = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
        stats = DatasetStatistics()
        stats.compute(seqs)
        assert abs(stats.avg_seq_len - 3.0) < 1e-5

    def test_to_dict(self):
        seqs = [[1, 2, 3], [4, 5]]
        stats = DatasetStatistics().compute(seqs)
        d = stats.to_dict()
        assert "total_tokens" in d
        assert "perplexity" not in d

    def test_gpu_hours(self):
        seqs = [[i for i in range(100)] for _ in range(100)]
        stats = DatasetStatistics().compute(seqs)
        hours = stats.estimated_gpu_hours(tokens_per_second_per_gpu=1000)
        assert hours > 0


class TestHajeenDataset:

    def test_len(self):
        samples = [([1, 2, 3], [1, 2, 3]), ([4, 5], [4, 5])]
        ds = HajeenDataset(samples)
        assert len(ds) == 2

    def test_getitem(self):
        samples = [([1, 2, 3], [1, 2, 3])]
        ds = HajeenDataset(samples)
        item = ds[0]
        assert "input_ids" in item
        assert "labels" in item
        assert item["input_ids"].tolist() == [1, 2, 3]

    def test_collate_fn(self):
        import torch
        samples = [([1, 2, 3], [1, 2, 3]), ([4, 5], [4, 5])]
        ds = HajeenDataset(samples)
        batch = [ds[0], ds[1]]
        collated = HajeenDataset.collate_fn(batch, pad_token_id=0)
        assert collated["input_ids"].shape == (2, 3)  # padded to max len
        assert collated["input_ids"][1, 2].item() == 0  # padding


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
