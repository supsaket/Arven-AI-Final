from memory.system import MemorySystem


class ContextManager:

    def __init__(self):
        self.memory = MemorySystem()

    def build(self, user_message, limit=5):

        text = user_message.lower()

        # Memory recall queries
        memory_query_words = [
            "what do you remember",
            "what do you know about me",
            "what do you know about boss",
            "show my memories",
            "show what you remember",
            "my memories",
            "remember about me"
        ]

        if any(word in text for word in memory_query_words):

            context = self.memory.context_for(
                user_message,
                limit=limit
            )

            if not context:
                return ""

            return (
                "Relevant memories about Boss:\n"
                + context
            )

        categories = {
            "game": [
                "game",
                "games",
                "ghost of tsushima"
            ],

            "color": [
                "color",
                "colors",
                "colour",
                "colours",
                "red",
                "white",
                "black",
                "purple"
            ],

            "python": [
                "python",
                "programming",
                "coding"
            ],

            "germany": [
                "germany",
                "german",
                "settle",
                "settling",
                "relocate",
                "relocation",
                "move to germany"
            ]
        }

        selected_category = None

        for category, words in categories.items():

            if any(word in text for word in words):
                selected_category = category
                break

        if selected_category is None:
            return ""

        context = self.memory.context_for(
            user_message,
            limit=limit
        )

        if not context:
            return ""

        lines = context.splitlines()

        relevant = []

        for line in lines:

            line_lower = line.lower()

            if any(
                word in line_lower
                for word in categories[selected_category]
            ):
                relevant.append(line)

        if not relevant:
            return ""

        return (
            "Relevant memories about Boss:\n"
            + "\n".join(relevant[:limit])
        )