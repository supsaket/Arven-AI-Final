from memory.database import MemoryDatabase


class MemoryManager:

    def __init__(self):
        self.database = MemoryDatabase()

    def add_memory(self, content, category="other", importance=5):
        return self.database.add(
            content=content,
            category=category,
            importance=importance
        )

    def update_memory(self, memory_id, content, category=None, importance=None):
        return self.database.update(
            memory_id=memory_id,
            content=content,
            category=category,
            importance=importance
        )

    def delete_memory(self, memory_id):
        return self.database.delete(memory_id)

    def list_memories(self):
        return self.database.get_all()

    def get_memory(self, memory_id):
        return self.database.get_by_id(memory_id)

    def clear_all(self):
        memories = self.database.get_all()

        deleted = 0

        for memory in memories:
            if self.database.delete(memory[0]):
                deleted += 1

        return deleted
