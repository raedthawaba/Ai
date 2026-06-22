"""
cloud_tokenizer_trainer.py — Cloud Tokenizer Trainer
تدريب Tokenizer من datasets سحابية ورفعه تلقائياً إلى HuggingFace
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


class CloudTokenizerTrainer:
    """
    مدرّب Tokenizer السحابي.

    يدرب BPE/WordPiece Tokenizer من:
    - datasets HuggingFace
    - ملفات نصية محلية
    - مزيج من المصدرين

    ثم يرفع تلقائياً:
    - tokenizer.json
    - vocab.json
    - merges.txt
    - tokenizer_config.json
    """

    DEFAULT_SPECIAL_TOKENS = [
        "<pad>", "<unk>", "<bos>", "<eos>",
        "<mask>", "<sep>", "<cls>",
        "<ar>", "<en>", "<code>",
    ]

    def __init__(
        self,
        vocab_size: int = 32_000,
        tokenizer_type: str = "BPE",
        special_tokens: Optional[List[str]] = None,
        output_dir: str = "./tokenizer_output",
        upload_to_hf: bool = True,
        version: str = "v1.0",
    ):
        self.vocab_size = vocab_size
        self.tokenizer_type = tokenizer_type
        self.special_tokens = special_tokens or self.DEFAULT_SPECIAL_TOKENS
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.upload_to_hf = upload_to_hf
        self.version = version
        self._tokenizer = None

    def _text_iterator_from_hub(
        self,
        dataset_name: str,
        text_field: str = "text",
        split: str = "train",
        max_samples: int = 500_000,
    ) -> Iterator[str]:
        """مولّد نصوص من HuggingFace Dataset."""
        from datasets import load_dataset

        logger.info(f"📂 تحميل dataset للـ tokenizer: {dataset_name}")
        hf_token = os.getenv("HF_TOKEN")

        try:
            ds = load_dataset(
                dataset_name,
                split=split,
                streaming=True,
                token=hf_token,
            )
            count = 0
            for record in ds:
                if count >= max_samples:
                    break
                text = record.get(text_field, "") or ""
                if text.strip():
                    yield text
                    count += 1
        except Exception as e:
            logger.warning(f"⚠️  فشل تحميل {dataset_name}: {e} — استخدام نصوص وهمية")
            dummy_texts = [
                "الذكاء الاصطناعي ومعالجة اللغات الطبيعية.",
                "Hajeen model training on Arabic and English data.",
                "تعلم الآلة يتطور بشكل متسارع في العالم العربي.",
            ] * 1000
            for text in dummy_texts:
                yield text

    def _text_iterator_from_files(self, file_paths: List[str]) -> Iterator[str]:
        """مولّد نصوص من ملفات محلية."""
        for path in file_paths:
            p = Path(path)
            if not p.exists():
                continue
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield line

    def train(
        self,
        dataset_name: Optional[str] = None,
        local_files: Optional[List[str]] = None,
        text_field: str = "text",
        max_samples: int = 500_000,
    ) -> Path:
        """
        تدريب الـ Tokenizer.

        Args:
            dataset_name: اسم dataset HuggingFace (افتراضي: hajeen-datasets)
            local_files: ملفات نصية محلية إضافية
            text_field: حقل النص في الـ dataset
            max_samples: أقصى عدد عينات للتدريب

        Returns:
            مسار مجلد الـ tokenizer المدرَّب
        """
        from tokenizers import Tokenizer, trainers, models, pre_tokenizers, decoders, normalizers

        logger.info(f"🔤 بدء تدريب Tokenizer — vocab_size={self.vocab_size}")
        logger.info(f"   النوع: {self.tokenizer_type}")
        logger.info(f"   Tokens خاصة: {self.special_tokens}")

        if self.tokenizer_type == "BPE":
            tokenizer = Tokenizer(models.BPE(unk_token="<unk>"))
            tokenizer.normalizer = normalizers.Sequence([
                normalizers.NFD(),
                normalizers.Lowercase(),
                normalizers.StripAccents(),
            ])
            tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
            tokenizer.decoder = decoders.ByteLevel()
            trainer = trainers.BpeTrainer(
                vocab_size=self.vocab_size,
                special_tokens=self.special_tokens,
                min_frequency=2,
                show_progress=True,
            )
        elif self.tokenizer_type == "WordPiece":
            tokenizer = Tokenizer(models.WordPiece(unk_token="<unk>"))
            tokenizer.normalizer = normalizers.BertNormalizer(lowercase=False)
            tokenizer.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
            tokenizer.decoder = decoders.WordPiece()
            trainer = trainers.WordPieceTrainer(
                vocab_size=self.vocab_size,
                special_tokens=self.special_tokens,
                min_frequency=2,
            )
        else:
            raise ValueError(f"نوع tokenizer غير مدعوم: {self.tokenizer_type}")

        dataset_name = dataset_name or os.getenv(
            "HF_DATASET_REPO", "Raedthawaba/hajeen-datasets"
        )

        def text_generator():
            yield from self._text_iterator_from_hub(
                dataset_name=dataset_name,
                text_field=text_field,
                max_samples=max_samples,
            )
            if local_files:
                yield from self._text_iterator_from_files(local_files)

        logger.info("⚙️  تدريب الـ Tokenizer...")
        tokenizer.train_from_iterator(text_generator(), trainer=trainer)

        output_path = self._save_tokenizer(tokenizer)
        logger.info(f"✅ Tokenizer محفوظ في: {output_path}")

        if self.upload_to_hf:
            self._upload_tokenizer(output_path)

        return output_path

    def _save_tokenizer(self, tokenizer) -> Path:
        """حفظ جميع ملفات الـ Tokenizer."""
        tokenizer.save(str(self.output_dir / "tokenizer.json"))

        vocab = tokenizer.get_vocab()
        with open(self.output_dir / "vocab.json", "w", encoding="utf-8") as f:
            json.dump(vocab, f, ensure_ascii=False, indent=2)

        if hasattr(tokenizer.model, "merges"):
            with open(self.output_dir / "merges.txt", "w", encoding="utf-8") as f:
                f.write("#version: 0.2\n")
                for merge in tokenizer.model.merges:
                    f.write(f"{merge[0]} {merge[1]}\n")

        config = {
            "tokenizer_class": "PreTrainedTokenizerFast",
            "model_type": self.tokenizer_type.lower(),
            "vocab_size": self.vocab_size,
            "bos_token": "<bos>",
            "eos_token": "<eos>",
            "unk_token": "<unk>",
            "pad_token": "<pad>",
            "mask_token": "<mask>",
            "additional_special_tokens": ["<ar>", "<en>", "<code>"],
            "do_lower_case": False,
            "tokenizer_type": self.tokenizer_type,
            "version": self.version,
            "model_name": "hajeen-tokenizer",
        }
        with open(self.output_dir / "tokenizer_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        special_tokens_map = {
            "bos_token": "<bos>",
            "eos_token": "<eos>",
            "unk_token": "<unk>",
            "pad_token": "<pad>",
            "mask_token": "<mask>",
        }
        with open(self.output_dir / "special_tokens_map.json", "w", encoding="utf-8") as f:
            json.dump(special_tokens_map, f, ensure_ascii=False, indent=2)

        logger.info("📁 ملفات Tokenizer المحفوظة:")
        for f in sorted(self.output_dir.iterdir()):
            logger.info(f"   ✓ {f.name} ({f.stat().st_size:,} bytes)")

        return self.output_dir

    def _upload_tokenizer(self, tokenizer_dir: Path) -> Dict[str, str]:
        """رفع الـ Tokenizer إلى HuggingFace."""
        try:
            import sys
            sys.path.insert(0, str(tokenizer_dir.parent.parent.parent.parent.parent))
            from cloud.model_manager import ModelManager
            mm = ModelManager()
            results = mm.upload_tokenizer(
                tokenizer_dir=str(tokenizer_dir),
                version=self.version,
            )
            logger.info(f"⬆️  تم رفع الـ Tokenizer إلى HuggingFace:")
            for fname, url in results.items():
                logger.info(f"   ✓ {fname}")
            return results
        except Exception as e:
            logger.error(f"❌ فشل رفع الـ Tokenizer: {e}")
            return {}

    def load(self, tokenizer_dir: Optional[str] = None) -> Any:
        """تحميل Tokenizer محفوظ."""
        from tokenizers import Tokenizer

        path = Path(tokenizer_dir or str(self.output_dir)) / "tokenizer.json"
        if not path.exists():
            raise FileNotFoundError(f"لم يجد tokenizer.json في {path}")

        self._tokenizer = Tokenizer.from_file(str(path))
        logger.info(f"✅ تم تحميل Tokenizer من {path}")
        return self._tokenizer

    def encode(self, text: str) -> List[int]:
        """ترميز نص."""
        if self._tokenizer is None:
            self.load()
        return self._tokenizer.encode(text).ids

    def decode(self, ids: List[int]) -> str:
        """فك ترميز نص."""
        if self._tokenizer is None:
            self.load()
        return self._tokenizer.decode(ids)
