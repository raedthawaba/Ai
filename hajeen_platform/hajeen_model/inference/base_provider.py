
from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass

    @abstractmethod
    def get_model_info(self) -> dict:
        pass
