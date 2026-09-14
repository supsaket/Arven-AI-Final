from memory.processor import MemoryProcessor
from memory.retriever import MemoryRetriever


class MemorySystem:

    def __init__(self):
        self.processor = MemoryProcessor()
        self.retriever = MemoryRetriever()

    def process_message(self, message):
        return self.processor.process(message)

    def recall(self, query, limit=5):
        return self.retriever.search(query, limit=limit)

    def context_for(self, query, limit=5):

        memories = self.recall(query, limit)

        if not memories:
            return ""

        lines = []

        for memory in memories:
            lines.append(
                f"- {memory['content']}"
            )

        return "\n".join(lines)
