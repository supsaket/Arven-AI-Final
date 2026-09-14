from abc import ABC, abstractmethod


class ModelInterface(ABC):

    @abstractmethod
    def chat(self, messages):
        pass
