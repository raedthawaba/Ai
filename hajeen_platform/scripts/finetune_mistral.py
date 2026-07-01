"""Fine-tuning Script — Mistral-7B على بياناتك الخاصة.

طريقة الاستخدام:
    python scripts/finetune_mistral.py --data_path ./my_data.jsonl --output_dir ./models/hajeen_model

متطلبات:
    pip install transformers peft trl bitsandbytes accelerate datasets

بيانات الإدخال (JSONL):
    {"instruction": "ما هو ...", "output": "الجواب هو ..."}
    {"instruction": "اشرح لي ...", "output": "..."}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Dict, List

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_dataset_from_jsonl(path: str) -> List[Dict]:
    """تحميل البيانات من ملف JSONL."""
    data = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    logger.info("Loaded %d examples from %s", len(data), path)
    return data


def format_mistral_prompt(example: Dict) -> str:
    """تنسيق المثال بصيغة Mistral Instruct."""
    instruction = example.get("instruction", example.get("input", ""))
    output = example.get("output", example.get("response", ""))
    system = example.get("system", "أنت مساعد ذكاء اصطناعي متخصص ومفيد.")

    return (
        f"<s>[INST] <<SYS>>\n{system}\n<</SYS>>\n\n"
        f"{instruction} [/INST] {output} </s>"
    )


def train(
    data_path: str,
    output_dir: str,
    base_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
    max_steps: int = 500,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
) -> None:
    logger.info("Starting fine-tuning: model=%s, data=%s", base_model, data_path)

    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
        )
        from peft import LoraConfig, TaskType, get_peft_model
        from trl import SFTTrainer
        from datasets import Dataset
        from transformers import BitsAndBytesConfig
    except ImportError as e:
        logger.error("Missing dependency: %s\nRun: pip install transformers peft trl bitsandbytes accelerate datasets", e)
        raise

    # ── 1. تحميل البيانات ────────────────────────────────────────────────────
    raw_data = load_dataset_from_jsonl(data_path)
    formatted = [{"text": format_mistral_prompt(ex)} for ex in raw_data]
    dataset = Dataset.from_list(formatted)
    logger.info("Dataset ready: %d examples", len(dataset))

    # ── 2. إعداد Quantization (4-bit) ────────────────────────────────────────
    use_gpu = torch.cuda.is_available()
    logger.info("GPU available: %s", use_gpu)

    bnb_config = None
    if use_gpu:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

    # ── 3. تحميل النموذج الأساسي ─────────────────────────────────────────────
    logger.info("Loading base model: %s", base_model)
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if not tokenizer.pad_token:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto" if use_gpu else "cpu",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if use_gpu else torch.float32,
    )
    model.config.use_cache = False
    logger.info("Base model loaded")

    # ── 4. إعداد LoRA ────────────────────────────────────────────────────────
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── 5. إعداد التدريب ─────────────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=output_dir,
        max_steps=max_steps,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=learning_rate,
        fp16=use_gpu,
        bf16=False,
        logging_steps=50,
        save_steps=250,
        save_total_limit=2,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        optim="paged_adamw_32bit" if use_gpu else "adamw_torch",
        report_to="none",
        remove_unused_columns=False,
    )

    # ── 6. التدريب ──────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        tokenizer=tokenizer,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=2048,
        packing=False,
    )

    logger.info("Starting training for %d steps...", max_steps)
    trainer.train()

    # ── 7. حفظ النموذج ──────────────────────────────────────────────────────
    logger.info("Saving model to: %s", output_dir)
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # حفظ معلومات النموذج
    model_info = {
        "base_model": base_model,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "max_steps": max_steps,
        "training_examples": len(raw_data),
        "output_dir": output_dir,
    }
    with open(os.path.join(output_dir, "training_info.json"), "w", encoding="utf-8") as f:
        json.dump(model_info, f, ensure_ascii=False, indent=2)

    logger.info("Training complete! Model saved to: %s", output_dir)
    logger.info("To use: set FINETUNED_MODEL_PATH=%s and USE_FINETUNED_MODEL=true", output_dir)


def merge_adapter(adapter_path: str, output_path: str) -> None:
    """دمج LoRA adapter مع النموذج الأساسي."""
    try:
        from peft import AutoPeftModelForCausalLM
        from transformers import AutoTokenizer
        import torch
    except ImportError:
        logger.error("Run: pip install peft transformers")
        return

    logger.info("Merging adapter: %s → %s", adapter_path, output_path)
    model = AutoPeftModelForCausalLM.from_pretrained(
        adapter_path,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    model = model.merge_and_unload()
    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)
    logger.info("Merged model saved to: %s", output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune Mistral-7B on custom data")
    parser.add_argument("--data_path",   required=True, help="Path to JSONL training data")
    parser.add_argument("--output_dir",  default="./models/hajeen_finetuned", help="Output directory")
    parser.add_argument("--base_model",  default="mistralai/Mistral-7B-Instruct-v0.2")
    parser.add_argument("--max_steps",   type=int, default=500)
    parser.add_argument("--batch_size",  type=int, default=4)
    parser.add_argument("--lr",          type=float, default=2e-4)
    parser.add_argument("--lora_r",      type=int, default=16)
    parser.add_argument("--merge",       action="store_true", help="Merge adapter after training")
    args = parser.parse_args()

    train(
        data_path=args.data_path,
        output_dir=args.output_dir,
        base_model=args.base_model,
        max_steps=args.max_steps,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        lora_r=args.lora_r,
    )

    if args.merge:
        merged_path = args.output_dir + "_merged"
        merge_adapter(args.output_dir, merged_path)
