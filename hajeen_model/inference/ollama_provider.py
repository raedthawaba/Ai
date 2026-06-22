
from .base_provider import BaseProvider
import requests

class OllamaProvider(BaseProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "hajeen-v1"):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, **kwargs) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            **kwargs
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Error connecting to Ollama: {str(e)}"

    def get_model_info(self) -> dict:
        return {
            "provider": "Ollama",
            "model": self.model,
            "base_url": self.base_url
        }
