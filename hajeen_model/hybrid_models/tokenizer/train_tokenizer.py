"""
train_tokenizer.py — CLI script to train the Hajeen BPE tokenizer.

Usage:
    python -m hajeen_model.tokenizer.train_tokenizer \
        --input_files data/corpus_ar.txt data/corpus_en.txt \
        --output_dir tokenizer_model/ \
        --vocab_size 32000 \
        --min_frequency 2

Supports plain text files (one document per line or free-form).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List

from hajeen_model.tokenizer.bpe_tokenizer import BPETokenizer


def read_texts(file_paths: List[str], encoding: str = "utf-8") -> List[str]:
    """Read all texts from a list of file paths."""
    texts: List[str] = []
    for path in file_paths:
        p = Path(path)
        if not p.exists():
            print(f"[WARNING] File not found: {path}", file=sys.stderr)
            continue
        with open(p, "r", encoding=encoding, errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    texts.append(line)
        print(f"  Loaded {path}: {len(texts)} lines so far")
    return texts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the Hajeen BPE tokenizer from scratch.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input_files",
        nargs="+",
        required=True,
        help="Paths to training text files (UTF-8).",
    )
    parser.add_argument(
        "--output_dir",
        default="tokenizer_model",
        help="Directory to save the trained tokenizer.",
    )
    parser.add_argument(
        "--vocab_size",
        type=int,
        default=32_000,
        help="Target vocabulary size.",
    )
    parser.add_argument(
        "--min_frequency",
        type=int,
        default=2,
        help="Minimum pair frequency to consider for merging.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="File encoding.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Hajeen Foundation Model — Tokenizer Training")
    print("=" * 60)
    print(f"Input files   : {args.input_files}")
    print(f"Output dir    : {args.output_dir}")
    print(f"Vocab size    : {args.vocab_size}")
    print(f"Min frequency : {args.min_frequency}")
    print()

    # Load texts
    print("[1/3] Loading training texts...")
    texts = read_texts(args.input_files, encoding=args.encoding)
    if not texts:
        print("[ERROR] No texts loaded. Exiting.", file=sys.stderr)
        sys.exit(1)
    print(f"  Total lines: {len(texts):,}")
    print()

    # Train
    print("[2/3] Training BPE tokenizer...")
    t0 = time.time()
    tokenizer = BPETokenizer()
    tokenizer.train(
        texts=texts,
        vocab_size=args.vocab_size,
        min_frequency=args.min_frequency,
        show_progress=True,
    )
    elapsed = time.time() - t0
    print(f"  Training time: {elapsed:.1f}s")
    print()

    # Save
    print("[3/3] Saving tokenizer...")
    tokenizer.save(args.output_dir)
    print()

    # Quick validation
    sample_texts = [
        "مرحباً بكم في نموذج Hajeen للذكاء الاصطناعي",
        "Hello, this is a test sentence.",
        "def main(): print('Hajeen')",
    ]
    print("Quick encode/decode validation:")
    for text in sample_texts:
        ids = tokenizer.encode(text, add_bos=True, add_eos=True)
        decoded = tokenizer.decode(ids)
        print(f"  Input  : {text}")
        print(f"  IDs    : {ids[:10]}{'...' if len(ids) > 10 else ''}")
        print(f"  Decoded: {decoded}")
        print()

    print(f"Done! Tokenizer saved to: {os.path.abspath(args.output_dir)}")


if __name__ == "__main__":
    main()
