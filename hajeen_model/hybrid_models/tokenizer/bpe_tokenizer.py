"""
BPETokenizer — Byte-Pair Encoding tokenizer built from scratch.

Supports Arabic, English, code, and mixed-language text.
No dependency on HuggingFace or SentencePiece internals — pure Python.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Dict, Iterator, List, Optional, Tuple


class BPETokenizer:
    """
    Byte-Pair Encoding tokenizer.

    Training steps:
        1. Pre-tokenize text into words (unicode-aware, handles Arabic & code).
        2. Represent each word as a sequence of characters + </w> end-of-word marker.
        3. Iteratively merge the most frequent adjacent pair.
        4. Repeat until vocab_size is reached or no pairs remain.

    Special tokens:
        <pad>  id=0
        <bos>  id=1
        <eos>  id=2
        <unk>  id=3
    """

    SPECIAL_TOKENS = ["<pad>", "<bos>", "<eos>", "<unk>"]
    END_OF_WORD = "</w>"

    def __init__(self) -> None:
        self.vocab: Dict[str, int] = {}
        self.inv_vocab: Dict[int, str] = {}
        self.merges: List[Tuple[str, str]] = []
        self._merge_ranks: Dict[Tuple[str, str], int] = {}
        self._trained = False

    # ── Pre-tokenization ──────────────────────────────────────────────────

    _PATTERN = re.compile(
        r"""'s|'t|'re|'ve|'m|'ll|'d"""
        r"""|[\u0600-\u06FF]+"""        # Arabic block
        r"""|[A-Za-z]+"""
        r"""|[0-9]+"""
        r"""|[^\s]""",
        re.UNICODE,
    )

    def _pre_tokenize(self, text: str) -> List[str]:
        """Split text into raw word tokens."""
        return self._PATTERN.findall(text)

    def _word_to_chars(self, word: str) -> Tuple[str, ...]:
        """Convert a word string to a tuple of BPE symbols (chars + end marker)."""
        chars = list(word)
        chars[-1] = chars[-1] + self.END_OF_WORD
        return tuple(chars)

    # ── Training ─────────────────────────────────────────────────────────

    def _get_stats(
        self, vocab: Dict[Tuple[str, ...], int]
    ) -> Dict[Tuple[str, str], int]:
        """Count adjacent symbol pairs across the vocabulary."""
        pairs: Dict[Tuple[str, str], int] = Counter()
        for symbols, freq in vocab.items():
            for i in range(len(symbols) - 1):
                pairs[(symbols[i], symbols[i + 1])] += freq
        return pairs

    def _merge_vocab(
        self,
        pair: Tuple[str, str],
        vocab: Dict[Tuple[str, ...], int],
    ) -> Dict[Tuple[str, ...], int]:
        """Apply one merge step to all entries in the working vocabulary."""
        new_vocab: Dict[Tuple[str, ...], int] = {}
        bigram = pair
        for symbols, freq in vocab.items():
            new_symbols: List[str] = []
            i = 0
            while i < len(symbols):
                if (
                    i < len(symbols) - 1
                    and symbols[i] == bigram[0]
                    and symbols[i + 1] == bigram[1]
                ):
                    new_symbols.append(bigram[0] + bigram[1])
                    i += 2
                else:
                    new_symbols.append(symbols[i])
                    i += 1
            new_vocab[tuple(new_symbols)] = freq
        return new_vocab

    def train(
        self,
        texts: List[str],
        vocab_size: int = 32_000,
        min_frequency: int = 2,
        show_progress: bool = True,
    ) -> None:
        """
        Train the BPE tokenizer on a list of texts.

        Args:
            texts: Training corpus (list of strings).
            vocab_size: Target vocabulary size (including special tokens).
            min_frequency: Pairs appearing fewer times are skipped.
            show_progress: Print progress every 1000 merges.
        """
        # Build working vocabulary: {char_sequence: frequency}
        word_freq: Counter = Counter()
        for text in texts:
            for word in self._pre_tokenize(text):
                word_freq[word] += 1

        # Convert to char-level representation
        working_vocab: Dict[Tuple[str, ...], int] = {
            self._word_to_chars(w): freq
            for w, freq in word_freq.items()
            if freq >= min_frequency
        }

        # Collect initial character vocabulary
        char_vocab: set = set()
        for symbols in working_vocab:
            char_vocab.update(symbols)

        # Build token → id mapping
        all_tokens = self.SPECIAL_TOKENS + sorted(char_vocab)
        self.vocab = {tok: i for i, tok in enumerate(all_tokens)}

        num_merges = vocab_size - len(self.vocab)
        self.merges = []

        for step in range(num_merges):
            pairs = self._get_stats(working_vocab)
            if not pairs:
                break

            best_pair = max(pairs, key=lambda p: (pairs[p], p))
            if pairs[best_pair] < min_frequency:
                break

            working_vocab = self._merge_vocab(best_pair, working_vocab)
            merged_token = best_pair[0] + best_pair[1]
            self.merges.append(best_pair)
            self._merge_ranks[best_pair] = step

            if merged_token not in self.vocab:
                self.vocab[merged_token] = len(self.vocab)

            if show_progress and (step + 1) % 1000 == 0:
                print(f"  BPE merge step {step + 1}/{num_merges}, vocab={len(self.vocab)}")

        self.inv_vocab = {v: k for k, v in self.vocab.items()}
        self._trained = True
        print(f"[BPETokenizer] Training complete. Vocab size: {len(self.vocab)}")

    # ── Encoding ─────────────────────────────────────────────────────────

    def _bpe_encode_word(self, word: str) -> List[str]:
        """Apply learned BPE merges to a single word."""
        symbols = list(self._word_to_chars(word))
        if len(symbols) == 1:
            return symbols

        while True:
            pairs = [
                (symbols[i], symbols[i + 1]) for i in range(len(symbols) - 1)
            ]
            best = min(
                (p for p in pairs if p in self._merge_ranks),
                key=lambda p: self._merge_ranks[p],
                default=None,
            )
            if best is None:
                break
            merged = best[0] + best[1]
            new_symbols: List[str] = []
            i = 0
            while i < len(symbols):
                if (
                    i < len(symbols) - 1
                    and symbols[i] == best[0]
                    and symbols[i + 1] == best[1]
                ):
                    new_symbols.append(merged)
                    i += 2
                else:
                    new_symbols.append(symbols[i])
                    i += 1
            symbols = new_symbols
        return symbols

    def encode(
        self,
        text: str,
        add_bos: bool = False,
        add_eos: bool = False,
    ) -> List[int]:
        """
        Encode a string into a list of token ids.

        Args:
            text: Input string (Arabic, English, code, mixed).
            add_bos: Prepend <bos> token.
            add_eos: Append <eos> token.

        Returns:
            List of integer token ids.
        """
        if not self._trained:
            raise RuntimeError("Tokenizer is not trained. Call train() or load() first.")

        ids: List[int] = []
        if add_bos:
            ids.append(self.vocab["<bos>"])

        for word in self._pre_tokenize(text):
            for token in self._bpe_encode_word(word):
                ids.append(self.vocab.get(token, self.vocab["<unk>"]))

        if add_eos:
            ids.append(self.vocab["<eos>"])

        return ids

    def encode_batch(self, texts: List[str], **kwargs) -> List[List[int]]:
        """Encode a batch of strings."""
        return [self.encode(t, **kwargs) for t in texts]

    # ── Decoding ─────────────────────────────────────────────────────────

    def decode(self, ids: List[int], skip_special_tokens: bool = True) -> str:
        """
        Decode token ids back to a string.

        Args:
            ids: List of integer token ids.
            skip_special_tokens: If True, drop <pad>, <bos>, <eos>, <unk>.

        Returns:
            Decoded string.
        """
        tokens = []
        for i in ids:
            tok = self.inv_vocab.get(i, "<unk>")
            if skip_special_tokens and tok in self.SPECIAL_TOKENS:
                continue
            tokens.append(tok)

        # Re-assemble: END_OF_WORD marks word boundaries
        text = "".join(tokens).replace(self.END_OF_WORD, " ")
        return text.strip()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    @property
    def pad_token_id(self) -> int:
        return self.vocab["<pad>"]

    @property
    def bos_token_id(self) -> int:
        return self.vocab["<bos>"]

    @property
    def eos_token_id(self) -> int:
        return self.vocab["<eos>"]

    @property
    def unk_token_id(self) -> int:
        return self.vocab["<unk>"]

    # ── Serialization ────────────────────────────────────────────────────

    def save(self, directory: str) -> None:
        """Save tokenizer vocab and merges to directory."""
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "vocab.json"), "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, ensure_ascii=False, indent=2)
        with open(os.path.join(directory, "merges.txt"), "w", encoding="utf-8") as f:
            for a, b in self.merges:
                f.write(f"{a} {b}\n")
        print(f"[BPETokenizer] Saved to {directory}/")

    @classmethod
    def load(cls, directory: str) -> "BPETokenizer":
        """Load a previously saved tokenizer."""
        tok = cls()
        with open(os.path.join(directory, "vocab.json"), "r", encoding="utf-8") as f:
            tok.vocab = json.load(f)
        tok.inv_vocab = {v: k for k, v in tok.vocab.items()}
        merges_path = os.path.join(directory, "merges.txt")
        tok.merges = []
        with open(merges_path, "r", encoding="utf-8") as f:
            for rank, line in enumerate(f):
                parts = line.rstrip("\n").split(" ", 1)
                if len(parts) == 2:
                    pair = (parts[0], parts[1])
                    tok.merges.append(pair)
                    tok._merge_ranks[pair] = rank
        tok._trained = True
        return tok
