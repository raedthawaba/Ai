import sys
import os
import argparse
import logging

# إضافة مسار المشروع للـ PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.hf_integration.hub_manager import HFHubManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Sync Model Weights from HuggingFace Hub')
    parser.add_argument('--repo', type=str, default='Raedthawaba/hajeen-model', help='HF Model Repo ID')
    parser.add_argument('--token', type=str, help='HF Token')
    parser.add_argument('--dest', type=str, default='hajeen_model/weights', help='Local destination path')
    
    args = parser.parse_args()
    
    hub = HFHubManager(token=args.token)
    
    try:
        # تحميل أوزان النموذج
        logger.info(f"Downloading model weights from {args.repo} to {args.dest}...")
        hub.download_model(args.repo, args.dest)
        logger.info(f"Successfully synced model weights to {args.dest}")
        
    except Exception as e:
        logger.error(f"Failed to sync model: {str(e)}")

if __name__ == "__main__":
    main()
