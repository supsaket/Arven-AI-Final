import ollama

from brain.model_interface import ModelInterface
from core.config import MODEL_NAME


class OllamaModel(ModelInterface):

    def __init__(self, model=MODEL_NAME):
        self.model = model

    def chat(self, messages):

        response = ollama.chat(
            model=self.model,
            messages=messages,
            think=False
        )

        return response["message"]["content"]

    def generate(self, prompt):

        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            think=False
        )

        return response["response"]

    def health(self):

        try:
            ollama.show(self.model)
            return True

        except Exception:
            return False
