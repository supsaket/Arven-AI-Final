from memory.database import MemoryDatabase
from memory.understanding import MemoryUnderstanding


class MemoryProcessor:

    def __init__(self):
        self.database = MemoryDatabase()
        self.understanding = MemoryUnderstanding()

    def process(self, user_message):

        analysis = self.understanding.analyze(user_message)

        if not analysis.get("should_remember"):
            return {"action": "ignore", "analysis": analysis}

        memory_text = analysis.get("memory_text")
        category = analysis.get("category") or "other"
        memory_type = analysis.get("memory_type") or "fact"
        value = analysis.get("value")
        importance = analysis.get("importance", 5)

        if not memory_text or not value:
            return {"action": "ignore", "analysis": analysis}

        existing_memories = self.database.get_all()

        new_value = value.lower().strip()

        # Exact value duplicate check
        for memory in existing_memories:

            memory_id = memory[0]
            existing_value = memory[4]

            if not existing_value:
                continue

            old_value = existing_value.lower().strip()

            if old_value == new_value:
                return {
                    "action": "duplicate",
                    "memory_id": memory_id,
                    "analysis": analysis
                }

        # Same category + type ? update existing memory
        for memory in existing_memories:

            memory_id = memory[0]
            existing_category = memory[2]
            existing_type = memory[3]

            if (
                existing_category == category
                and existing_type == memory_type
            ):
                self.database.update(
                    memory_id,
                    memory_text,
                    category,
                    importance,
                    memory_type,
                    value
                )

                return {
                    "action": "updated",
                    "memory_id": memory_id,
                    "analysis": analysis
                }

        memory_id = self.database.add(
            content=memory_text,
            category=category,
            memory_type=memory_type,
            value=value,
            importance=importance
        )

        return {
            "action": "added",
            "memory_id": memory_id,
            "analysis": analysis
        }
