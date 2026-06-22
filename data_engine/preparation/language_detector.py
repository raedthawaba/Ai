
from langdetect import detect, DetectorFactory
from typing import List, Dict

# Ensure consistent results
DetectorFactory.seed = 0

class LanguageDetector:
    def __init__(self, supported_languages: List[str] = ["ar", "en"]):
        self.supported_languages = supported_languages

    def detect_language(self, text: str) -> str:
        try:
            return detect(text)
        except:
            return "unknown"

    def filter_unsupported_languages(self, dataset: List[Dict]) -> List[Dict]:
        filtered_dataset = []
        for sample in dataset:
            instruction = sample.get("instruction", "")
            output = sample.get("output", "")
            
            # Detect language of instruction and output
            instruction_lang = self.detect_language(instruction)
            output_lang = self.detect_language(output)
            
            # Check if both instruction and output are in supported languages
            if instruction_lang in self.supported_languages and output_lang in self.supported_languages:
                sample["instruction_lang"] = instruction_lang
                sample["output_lang"] = output_lang
                filtered_dataset.append(sample)
        return filtered_dataset
