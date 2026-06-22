
from .base_provider import BaseProvider
from .ollama_provider import OllamaProvider
from .hajeen_provider import HajeenProvider

class InferenceEngine:
    def __init__(self, provider_type: str = "ollama", **kwargs):
        """
        Initialize the Inference Engine with a specific provider.
        :param provider_type: 'ollama' or 'hajeen'
        :param kwargs: arguments for the provider initialization
        """
        self.providers = {
            "ollama": OllamaProvider,
            "hajeen": HajeenProvider
        }
        self.current_provider_name = provider_type
        self.provider = self._create_provider(provider_type, **kwargs)

    def _create_provider(self, provider_type: str, **kwargs) -> BaseProvider:
        provider_class = self.providers.get(provider_type.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider type: {provider_type}")
        return provider_class(**kwargs)

    def switch_provider(self, provider_type: str, **kwargs):
        """Switch the active inference provider at runtime."""
        self.provider = self._create_provider(provider_type, **kwargs)
        self.current_provider_name = provider_type

    def infer(self, prompt: str, **kwargs) -> str:
        """Generate a response using the active provider."""
        try:
            return self.provider.generate(prompt, **kwargs)
        except Exception as e:
            return f"Inference Error ({self.current_provider_name}): {str(e)}"

    def get_status(self) -> dict:
        """Get information about the current provider and its status."""
        status = self.provider.get_model_info()
        status["engine_active_provider"] = self.current_provider_name
        return status
