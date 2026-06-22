import os
import logging
from typing import List, Dict, Any
from datasets import load_dataset, concatenate_datasets, Dataset
from core.hf_integration.hub_manager import HFHubManager
from core.hf_integration.data_cleaner import DataCleaner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# قائمة بمصادر البيانات العربية الضخمة المقترحة
ARABIC_SOURCES = [
    {"repo": "Jr23xd23/ArabicText-Large", "column": "text", "limit": 50000}, # عينة من مجموعة ضخمة
    {"repo": "wikimedia/wikipedia", "subset": "20231101.ar", "column": "text", "limit": 20000}, # ويكيبيديا العربية الحديثة
    {"repo": "M-A-D/Mixed-Arabic-Datasets", "column": "text", "limit": 10000}, # بيانات متنوعة
    {"repo": "ARBML/CIDAR", "column": "output", "limit": 10000}, # بيانات تعليمات (Instruction)
]

def expand_dataset(target_repo: str, hf_token: str):
    hub = HFHubManager(token=hf_token)
    cleaner = DataCleaner()
    
    all_datasets = []
    
    # 1. سحب البيانات الحالية من مستودع المستخدم (إذا وجدت)
    try:
        current_ds = hub.fetch_dataset(target_repo)
        all_datasets.append(current_ds)
        logger.info(f"Loaded existing dataset from {target_repo}")
    except Exception:
        logger.info(f"Target repo {target_repo} not found or empty, starting fresh.")

    # 2. سحب ودمج البيانات من المصادر الجديدة
    for source in ARABIC_SOURCES:
        try:
            logger.info(f"Fetching from source: {source['repo']}...")
            if "subset" in source:
                ds = load_dataset(source["repo"], source["subset"], split="train", token=hf_token, trust_remote_code=True)
            else:
                ds = load_dataset(source["repo"], split="train", token=hf_token, trust_remote_code=True)
            
            # اختيار عينة إذا كانت المجموعة ضخمة جداً للنموذج الأولي
            if len(ds) > source["limit"]:
                ds = ds.select(range(source["limit"]))
            
            # توحيد اسم العمود إلى 'text'
            if source["column"] != "text":
                ds = ds.rename_column(source["column"], "text")
            
            # الاحتفاظ بعمود النص فقط لتوحيد التنسيق
            ds = ds.remove_columns([c for c in ds.column_names if c != "text"])
            
            # تنظيف البيانات قبل الدمج
            logger.info(f"Cleaning data from {source['repo']}...")
            ds = cleaner.clean_dataset(ds, text_column="text")
            
            all_datasets.append(ds)
            logger.info(f"Successfully added {len(ds)} records from {source['repo']}")
            
        except Exception as e:
            logger.error(f"Failed to fetch from {source['repo']}: {str(e)}")

    if not all_datasets:
        logger.error("No data collected.")
        return

    # 3. دمج كافة المجموعات
    final_ds = concatenate_datasets(all_datasets)
    logger.info(f"Final dataset size: {len(final_ds)} records.")

    # 4. الرفع إلى HuggingFace
    logger.info(f"Pushing expanded dataset to {target_repo}...")
    final_ds.push_to_hub(target_repo, token=hf_token)
    logger.info("Expansion and upload complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Raedthawaba/hajeen-datasets")
    parser.add_argument("--token", required=True)
    args = parser.parse_args()
    
    expand_dataset(args.repo, args.token)
