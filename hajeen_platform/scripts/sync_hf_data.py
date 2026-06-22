import sys
import os
import argparse
import logging

# إضافة مسار المشروع للـ PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.hf_integration.hub_manager import HFHubManager
from core.hf_integration.data_cleaner import DataCleaner

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Sync and Clean data from HuggingFace Hub')
    parser.add_argument('--repo', type=str, default='Raedthawaba/hajeen-datasets', help='HF Dataset Repo ID')
    parser.add_argument('--token', type=str, help='HF Token')
    parser.add_argument('--output', type=str, default='data/cleaned_data', help='Local output path')
    
    args = parser.parse_args()
    
    hub = HFHubManager(token=args.token)
    cleaner = DataCleaner()
    
    try:
        # 1. سحب البيانات
        logger.info(f"Fetching data from {args.repo}...")
        dataset = hub.fetch_dataset(args.repo)
        
        # 2. تنظيف البيانات
        logger.info("Cleaning data...")
        cleaned_dataset = cleaner.clean_dataset(dataset)
        
        # 3. حفظ البيانات محلياً
        os.makedirs(args.output, exist_ok=True)
        cleaned_dataset.save_to_disk(args.output)
        logger.info(f"Successfully synced and cleaned data to {args.output}")
        
    except Exception as e:
        logger.error(f"Failed to sync data: {str(e)}")

if __name__ == "__main__":
    main()
