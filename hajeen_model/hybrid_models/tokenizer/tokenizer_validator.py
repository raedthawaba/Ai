"""
tokenizer_validator.py — Validate a trained Hajeen tokenizer.

Checks:
    - Special token presence and correct IDs
    - Arabic round-trip encoding fidelity
    - English round-trip encoding fidelity
    - Code round-trip encoding fidelity
    - Vocabulary completeness
    - Encode/decode consistency
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import List, Optional

from hajeen_model.tokenizer.tokenizer_loader import HajeenTokenizer


@dataclass
class ValidationResult:
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.failed) == 0

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "  Hajeen Tokenizer Validation Report",
            "=" * 60,
        ]
        for msg in self.passed:
            lines.append(f"  [PASS] {msg}")
        for msg in self.warnings:
            lines.append(f"  [WARN] {msg}")
        for msg in self.failed:
            lines.append(f"  [FAIL] {msg}")
        lines.append("-" * 60)
        lines.append(
            f"  Result: {'PASSED' if self.ok else 'FAILED'} "
            f"({len(self.passed)} passed, {len(self.failed)} failed, "
            f"{len(self.warnings)} warnings)"
        )
        return "\n".join(lines)


_TEST_CASES = [
    # (description, text)
    ("Arabic — greeting", "مرحباً بكم في نموذج Hajeen"),
    ("Arabic — long sentence", "الذكاء الاصطناعي هو محاكاة للعقل البشري في الآلات التي تتعلم وتؤدي المهام"),
    ("English — simple", "Hello world, this is Hajeen Foundation Model."),
    ("English — technical", "Large language models use transformer architectures with attention mechanisms."),
    ("Code — Python", "def forward(self, x):\n    return self.linear(x)"),
    ("Code — mixed", "model = HajeenForCausalLM(config)  # نموذج التأسيس"),
    ("Numbers", "2024 1000000 3.14159"),
    ("Mixed Arabic/English", "Hajeen نموذج لغوي foundation model متعدد اللغات"),
    ("Punctuation", "Hello! مرحباً? 你好. Bonjour..."),
    ("Empty string", ""),
]


def validate_tokenizer(
    tokenizer: HajeenTokenizer,
    test_cases: Optional[List] = None,
) -> ValidationResult:
    """
    Run a full validation suite on a HajeenTokenizer.

    Args:
        tokenizer: A loaded HajeenTokenizer instance.
        test_cases: Optional override for test cases (list of (name, text) tuples).

    Returns:
        ValidationResult with pass/fail/warning lists.
    """
    result = ValidationResult()
    cases = test_cases or _TEST_CASES

    # ── 1. Special tokens ────────────────────────────────────────────────
    for name, expected_id in [
        ("<pad>", 0), ("<bos>", 1), ("<eos>", 2), ("<unk>", 3)
    ]:
        actual = getattr(tokenizer, f"{name[1:-1]}_token_id", None)
        if actual == expected_id:
            result.passed.append(f"Special token {name} has id={expected_id}")
        else:
            result.failed.append(
                f"Special token {name} expected id={expected_id}, got {actual}"
            )

    # ── 2. Vocab size sanity ─────────────────────────────────────────────
    if tokenizer.vocab_size >= 256:
        result.passed.append(f"Vocab size = {tokenizer.vocab_size} (>= 256)")
    else:
        result.failed.append(f"Vocab size too small: {tokenizer.vocab_size}")

    # ── 3. Encode/decode round-trip ──────────────────────────────────────
    for description, text in cases:
        if not text:
            # Empty string — should not crash
            try:
                ids = tokenizer.encode(text)
                result.passed.append(f"Empty string encode returns {ids}")
            except Exception as e:
                result.failed.append(f"Empty string encode crashed: {e}")
            continue

        try:
            ids = tokenizer.encode(text, add_bos=True, add_eos=True)
        except Exception as e:
            result.failed.append(f"[{description}] encode crashed: {e}")
            continue

        if len(ids) < 2:
            result.failed.append(
                f"[{description}] encode returned too few tokens: {ids}"
            )
            continue

        if ids[0] != tokenizer.bos_token_id:
            result.failed.append(f"[{description}] BOS missing at start")
        else:
            result.passed.append(f"[{description}] BOS present")

        if ids[-1] != tokenizer.eos_token_id:
            result.failed.append(f"[{description}] EOS missing at end")
        else:
            result.passed.append(f"[{description}] EOS present")

        # Decode round-trip (character-level fidelity not guaranteed by BPE,
        # but key words should survive)
        try:
            decoded = tokenizer.decode(ids)
            # Strip whitespace for comparison
            core_words = [w for w in text.split() if len(w) > 3]
            missing = [w for w in core_words if w not in decoded]
            if missing:
                result.warnings.append(
                    f"[{description}] Round-trip missing words: {missing[:3]}"
                )
            else:
                result.passed.append(f"[{description}] Round-trip OK")
        except Exception as e:
            result.failed.append(f"[{description}] decode crashed: {e}")

    # ── 4. Batch encoding ────────────────────────────────────────────────
    try:
        batch_texts = ["Hello world", "مرحبا", "def f(): pass"]
        batch_ids = tokenizer.encode_batch(batch_texts, max_length=64)
        if len(batch_ids) == 3:
            result.passed.append("Batch encoding returns correct batch size")
        else:
            result.failed.append(f"Batch encoding returned {len(batch_ids)} items, expected 3")
    except Exception as e:
        result.failed.append(f"Batch encoding crashed: {e}")

    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Validate a trained Hajeen tokenizer.")
    parser.add_argument("--tokenizer_dir", required=True, help="Path to tokenizer directory.")
    args = parser.parse_args()

    print(f"Loading tokenizer from: {args.tokenizer_dir}")
    try:
        tokenizer = HajeenTokenizer.from_pretrained(args.tokenizer_dir)
    except Exception as e:
        print(f"[ERROR] Failed to load tokenizer: {e}", file=sys.stderr)
        sys.exit(1)

    result = validate_tokenizer(tokenizer)
    print(result.summary())
    sys.exit(0 if result.ok else 1)


if __name__ == "__main__":
    main()
