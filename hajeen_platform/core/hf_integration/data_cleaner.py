import re
import logging
from typing import Dict, Any, List
from datasets import Dataset

logger = logging.getLogger(__name__)

class DataCleaner:
    """
    أداة لتنظيف ومعالجة النصوص المسحوبة من HuggingFace.
    """
    
    @staticmethod
    def clean_text(text: str) -> str:
        """
        تنظيف النص العربي من الرموز غير المرغوب فيها والتنسيقات الزائدة.
        """
        if not text:
            return ""
        
        # إزالة الروابط
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
        
        # إزالة وسوم HTML
        text = re.sub(r'<.*?>', '', text)
        
        # إزالة المسافات الزائدة
        text = re.sub(r'\s+', ' ', text).strip()
        
        # إزالة التشكيل (اختياري حسب الحاجة، هنا سنتركه لجودة اللغة)
        # text = re.sub(r'[\u064B-\u0652]', '', text)
        
        return text

    def clean_dataset(self, dataset: Dataset, text_column: str = "text") -> Dataset:
        """
        تنظيف مجموعة بيانات كاملة.
        """
        logger.info(f"Cleaning dataset column: {text_column}...")
        
        def processing_func(examples):
            return {text_column: [self.clean_text(t) for t in examples[text_column]]}
        
        cleaned_ds = dataset.map(processing_func, batched=True)
        logger.info("Dataset cleaning complete.")
        return cleaned_ds
