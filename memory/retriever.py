from memory.database import MemoryDatabase
from sentence_transformers import SentenceTransformer


class MemoryRetriever:

    def __init__(self):

        self.database = MemoryDatabase()

        self.model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2"
        )

        self._embedding_cache = {}

    def _detect_intent(self, query):

        query_lower = query.lower()

        if any(phrase in query_lower for phrase in [
            "what do you remember about me",
            "what do you remember about boss",
            "what do you know about me",
            "what do you know about boss",
            "tell me about myself",
            "tell me what you remember",
            "what are my memories",
            "show my memories"
        ]):
            return "memory"

        if any(word in query_lower for word in [
            "game",
            "games",
            "play",
            "favorite game"
        ]):
            return "game"

        if any(word in query_lower for word in [
            "color",
            "colors",
            "colour",
            "colours"
        ]):
            return "color"

        if any(word in query_lower for word in [
            "python",
            "coding",
            "programming"
        ]):
            return "python"

        if any(word in query_lower for word in [
            "goal",
            "goals",
            "plan",
            "plans",
            "future",
            "settle",
            "settlement",
            "move",
            "live"
        ]):
            return "goal"

        return None

    def _matches_intent(self, memory, intent):

        if intent == "memory":
            return True

        if intent is None:
            return False

        content = memory[1].lower()
        category = memory[2]
        memory_type = memory[3]

        if intent == "game":

            return (
                category == "preference"
                and memory_type == "favorite"
                and any(word in content for word in [
                    "game",
                    "ghost of tsushima",
                    "play"
                ])
            )

        if intent == "color":

            return (
                category == "preference"
                and memory_type == "favorite"
                and any(color in content for color in [
                    "red",
                    "white",
                    "black",
                    "purple",
                    "blue",
                    "green",
                    "yellow",
                    "orange",
                    "pink"
                ])
            )

        if intent == "python":

            return "python" in content

        if intent == "goal":

            return category in [
                "goal",
                "goals",
                "plan",
                "plans"
            ]

        return False

    def search(self, query, limit=5):

        memories = self.database.get_all()

        if not memories:
            return []

        intent = self._detect_intent(query)

        if intent is None:
            return []

        filtered_memories = [
            memory
            for memory in memories
            if self._matches_intent(memory, intent)
        ]

        if not filtered_memories:
            return []

        # For a general memory request, importance is the
        # strongest signal. There is no specific topic to compare.
        if intent == "memory":

            results = []

            for memory in filtered_memories:

                memory_id = memory[0]
                content = memory[1]
                category = memory[2]
                memory_type = memory[3]
                value = memory[4]
                importance = memory[5]

                results.append({
                    "id": memory_id,
                    "content": content,
                    "category": category,
                    "memory_type": memory_type,
                    "value": value,
                    "importance": importance,
                    "semantic_score": 0.0,
                    "keyword_score": 0.0,
                    "score": importance / 10.0
                })

            results.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            return results[:limit]

        query_embedding = self.model.encode(
            query,
            normalize_embeddings=True
        )

        query_lower = query.lower()

        results = []

        for memory in filtered_memories:

            memory_id = memory[0]
            content = memory[1]
            category = memory[2]
            memory_type = memory[3]
            value = memory[4]
            importance = memory[5]

            if memory_id not in self._embedding_cache:

                self._embedding_cache[memory_id] = self.model.encode(
                    content,
                    normalize_embeddings=True
                )

            memory_embedding = self._embedding_cache[memory_id]

            semantic_score = float(
                query_embedding @ memory_embedding
            )

            query_words = set(query_lower.split())
            content_words = set(content.lower().split())

            keyword_score = 0.0

            if query_words:

                keyword_score = len(
                    query_words & content_words
                ) / len(query_words)

            intent_bonus = 0.25

            final_score = (
                semantic_score * 0.6
                + keyword_score * 0.2
                + (importance / 10.0) * 0.1
                + intent_bonus
            )

            results.append({
                "id": memory_id,
                "content": content,
                "category": category,
                "memory_type": memory_type,
                "value": value,
                "importance": importance,
                "semantic_score": semantic_score,
                "keyword_score": keyword_score,
                "score": final_score
            })

        results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return results[:limit]