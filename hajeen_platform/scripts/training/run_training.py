#!/usr/bin/env python3
"""
سكريبت تدريب Hajeen Model v1.

الاستخدام:
    python scripts/training/run_training.py [--simulate] [--base-model MODEL] [--epochs N]

مثال:
    # محاكاة (بدون GPU):
    python scripts/training/run_training.py --simulate

    # بناء dataset فقط:
    python scripts/training/run_training.py --build-dataset-only

    # تدريب فعلي (يتطلب GPU):
    python scripts/training/run_training.py --base-model Qwen/Qwen2.5-1.5B --epochs 3
"""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

# إضافة المسار الرئيسي
sys.path.insert(0, str(Path(__file__).parents[2]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hajeen.training")


def build_dataset(storage_dir: str = "storage_data/gold",
                  processed_dir: str = "data/processed/pipeline",
                  synthetic: int = 100) -> int:
    """بناء Dataset التدريب."""
    from hajeen_model.dataset_builder import DatasetBuilder
    builder = DatasetBuilder()
    n1 = builder.load_from_storage(storage_dir)
    n2 = builder.load_from_processed(processed_dir)
    n3 = builder.add_synthetic_examples(synthetic)
    dataset = builder.build()
    stats = builder.stats()
    result = builder.save(dataset, "hajeen_model/data/dataset.jsonl", format="alpaca")

    print("\n" + "═" * 60)
    print("  Dataset Statistics")
    print("═" * 60)
    print(f"  من Storage:       {n1} مثال")
    print(f"  من Processed:     {n2} مثال")
    print(f"  اصطناعي:           {n3} مثال")
    print(f"  المجموع:           {result['total']} مثال")
    print(f"  تدريب:            {result['train']} | تقييم: {result['eval']}")
    print(f"  عربي:             {stats.arabic} | إنجليزي: {stats.english}")
    print(f"  Tokens تقريبي:    {stats.total_tokens_estimate:,}")
    print("═" * 60)
    if result["total"] < 100:
        print(f"  ⚠️  البيانات غير كافية ({result['total']} < 100).")
        print(f"  ابدأ جمع البيانات أولاً: ./run.sh demo")
    elif result["total"] < 1000:
        print(f"  ⚠️  يُنصح بـ 1000+ مثال للتدريب الجيد.")
    else:
        print(f"  ✅ البيانات كافية للتدريب!")
    print("═" * 60 + "\n")

    return result["total"]


def check_requirements():
    """فحص متطلبات التدريب."""
    from hajeen_model.training_pipeline import TrainingPipeline
    pipeline = TrainingPipeline()
    reqs = pipeline.check_requirements()
    print("\n" + "═" * 60)
    print("  متطلبات التدريب")
    print("═" * 60)
    for key, val in reqs.items():
        if key == "blockers":
            continue
        icon = "✅" if val is True else ("❌" if val is False else "ℹ️")
        print(f"  {icon}  {key}: {val}")
    if reqs.get("blockers"):
        print("\n  ❌ العوائق:")
        for b in reqs["blockers"]:
            print(f"     • {b}")
    print("═" * 60 + "\n")
    return reqs["can_train"]


def run_simulation():
    """محاكاة التدريب."""
    from hajeen_model.training_pipeline import TrainingPipeline, ExperimentConfig
    config = ExperimentConfig()
    pipeline = TrainingPipeline(config)
    print(f"\n  بدء محاكاة التدريب (ID: {config.experiment_id})...")
    result = pipeline.run_simulation()
    print("\n" + "═" * 60)
    print("  نتائج المحاكاة")
    print("═" * 60)
    print(f"  الخطوات: {result['total_steps']}")
    print(f"  الوقت:   {result['elapsed_sec']} ثانية")
    print(f"  Train Loss: {result.get('final_train_loss', 'N/A')}")
    print(f"  Eval Loss:  {result.get('final_eval_loss', 'N/A')}")
    print(f"  Checkpoints: {len(result.get('checkpoints', []))}")
    print("═" * 60 + "\n")
    return result


def run_actual_training(base_model: str, epochs: int, batch_size: int, lr: float):
    """التدريب الفعلي."""
    from hajeen_model.training_pipeline import TrainingPipeline, ExperimentConfig
    config = ExperimentConfig(
        base_model=base_model,
        num_epochs=epochs,
        batch_size=batch_size,
        learning_rate=lr,
    )
    pipeline = TrainingPipeline(config)
    reqs = pipeline.check_requirements()
    if not reqs["can_train"]:
        print("\n  ❌ لا يمكن التدريب:")
        for b in reqs["blockers"]:
            print(f"     • {b}")
        print("\n  استخدم --simulate للمحاكاة\n")
        sys.exit(1)

    print(f"\n  بدء التدريب الفعلي (ID: {config.experiment_id})...")
    result = pipeline.run_training()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description="Hajeen Model v1 Training Script")
    parser.add_argument("--simulate", action="store_true", help="محاكاة التدريب")
    parser.add_argument("--build-dataset-only", action="store_true", help="بناء Dataset فقط")
    parser.add_argument("--check-only", action="store_true", help="فحص المتطلبات فقط")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B", help="النموذج الأساسي")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--synthetic", type=int, default=100, help="عدد الأمثلة الاصطناعية")
    parser.add_argument("--storage-dir", default="storage_data/gold")
    parser.add_argument("--processed-dir", default="data/processed/pipeline")
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  🤖  Hajeen Model v1 — Training Script")
    print("═" * 60 + "\n")

    if args.check_only:
        check_requirements()
        return

    if args.build_dataset_only:
        build_dataset(args.storage_dir, args.processed_dir, args.synthetic)
        return

    # خطوة 1: بناء Dataset
    count = build_dataset(args.storage_dir, args.processed_dir, args.synthetic)

    if args.simulate or count < 100:
        if count < 100 and not args.simulate:
            print("  ⚠️  البيانات غير كافية — التشغيل في وضع المحاكاة تلقائياً\n")
        run_simulation()
    else:
        check_requirements()
        run_actual_training(args.base_model, args.epochs, args.batch_size, args.lr)

    print("  ✅ اكتمل بنجاح!\n")


if __name__ == "__main__":
    main()
