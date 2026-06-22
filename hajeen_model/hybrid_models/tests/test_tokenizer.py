"""
test_tokenizer.py — Unit tests for BPETokenizer and HajeenTokenizer.
"""

import os
import tempfile
import pytest
from hajeen_model.tokenizer.bpe_tokenizer import BPETokenizer
from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer


SAMPLE_CORPUS = [
    "مرحباً بكم في نموذج Hajeen",
    "الذكاء الاصطناعي هو محاكاة للعقل البشري",
    "Hello, this is a test sentence for the tokenizer.",
    "def train_model(data, epochs=10): return model",
    "Large language models use transformer architectures.",
    "نموذج لغوي كبير يدعم اللغة العربية والإنجليزية",
    "class HajeenModel(nn.Module): pass",
    "The quick brown fox jumps over the lazy dog.",
    "الخوارزميات والبيانات هي أساس التعلم الآلي",
    "import torch; import torch.nn as nn",
]


@pytest.fixture(scope="module")
def trained_tokenizer():
    """Train a small tokenizer for testing."""
    tok = BPETokenizer()
    tok.train(
        texts=SAMPLE_CORPUS * 20,  # Repeat to get enough pair frequency
        vocab_size=500,
        min_frequency=1,
        show_progress=False,
    )
    return tok


class TestBPETokenizer:

    def test_train_produces_vocab(self, trained_tokenizer):
        assert trained_tokenizer.vocab_size >= 4  # at least special tokens
        assert trained_tokenizer._trained is True

    def test_special_tokens_present(self, trained_tokenizer):
        assert "<pad>" in trained_tokenizer.vocab
        assert "<bos>" in trained_tokenizer.vocab
        assert "<eos>" in trained_tokenizer.vocab
        assert "<unk>" in trained_tokenizer.vocab

    def test_special_token_ids(self, trained_tokenizer):
        assert trained_tokenizer.pad_token_id == 0
        assert trained_tokenizer.bos_token_id == 1
        assert trained_tokenizer.eos_token_id == 2
        assert trained_tokenizer.unk_token_id == 3

    def test_encode_returns_ints(self, trained_tokenizer):
        ids = trained_tokenizer.encode("Hello world")
        assert isinstance(ids, list)
        assert all(isinstance(i, int) for i in ids)

    def test_encode_bos_eos(self, trained_tokenizer):
        ids = trained_tokenizer.encode("Hello", add_bos=True, add_eos=True)
        assert ids[0] == trained_tokenizer.bos_token_id
        assert ids[-1] == trained_tokenizer.eos_token_id

    def test_encode_arabic(self, trained_tokenizer):
        ids = trained_tokenizer.encode("مرحباً")
        assert len(ids) > 0
        assert all(isinstance(i, int) for i in ids)

    def test_encode_empty(self, trained_tokenizer):
        ids = trained_tokenizer.encode("")
        assert isinstance(ids, list)

    def test_decode_not_crash(self, trained_tokenizer):
        ids = trained_tokenizer.encode("Hello world", add_bos=True, add_eos=True)
        decoded = trained_tokenizer.decode(ids)
        assert isinstance(decoded, str)

    def test_decode_skip_special(self, trained_tokenizer):
        ids = trained_tokenizer.encode("Hello", add_bos=True, add_eos=True)
        decoded_skip = trained_tokenizer.decode(ids, skip_special_tokens=True)
        decoded_keep = trained_tokenizer.decode(ids, skip_special_tokens=False)
        assert "<bos>" not in decoded_skip
        assert "<bos>" in decoded_keep

    def test_save_and_load(self, trained_tokenizer):
        with tempfile.TemporaryDirectory() as d:
            trained_tokenizer.save(d)
            assert os.path.exists(os.path.join(d, "vocab.json"))
            assert os.path.exists(os.path.join(d, "merges.txt"))

            loaded = BPETokenizer.load(d)
            assert loaded.vocab_size == trained_tokenizer.vocab_size
            assert loaded._trained is True

            # Encoding should match
            ids1 = trained_tokenizer.encode("Hello")
            ids2 = loaded.encode("Hello")
            assert ids1 == ids2

    def test_encode_batch(self, trained_tokenizer):
        texts = ["Hello", "مرحبا", "test code"]
        results = trained_tokenizer.encode_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, list) for r in results)

    def test_untrained_raises(self):
        tok = BPETokenizer()
        with pytest.raises(RuntimeError, match="not trained"):
            tok.encode("test")


class TestHajeenTokenizer:

    @pytest.fixture
    def wrapper(self, trained_tokenizer):
        return HajeenTokenizer(trained_tokenizer)

    def test_encode(self, wrapper):
        ids = wrapper.encode("Hello world")
        assert isinstance(ids, list)

    def test_encode_batch_padding(self, wrapper):
        texts = ["Hello", "Hello world foo bar"]
        batch = wrapper.encode_batch(texts, max_length=20, padding=True)
        assert len(batch) == 2
        # All rows should have same length
        assert len(batch[0]) == len(batch[1])

    def test_encode_batch_truncation(self, wrapper):
        texts = ["Hello world foo bar baz qux"]
        batch = wrapper.encode_batch(texts, max_length=3, truncation=True, padding=False)
        assert len(batch[0]) <= 3

    def test_decode_tensor(self, wrapper):
        import torch
        ids = wrapper.encode("Hello", return_tensors="pt")
        assert ids.shape[0] == 1
        decoded = wrapper.decode(ids)
        assert isinstance(decoded, str)

    def test_vocab_size(self, wrapper):
        assert wrapper.vocab_size > 0

    def test_repr(self, wrapper):
        assert "HajeenTokenizer" in repr(wrapper)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
