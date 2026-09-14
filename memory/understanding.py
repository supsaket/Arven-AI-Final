import json

from brain.ollama_model import OllamaModel


class MemoryUnderstanding:

    def __init__(self):
        self.model = OllamaModel()

    def analyze(self, user_message):

        prompt = f"""
Analyze this user message for long-term memory.

Remember:
- favorite things
- preferences
- goals
- plans
- identity
- stable personal facts
- habits

If the user states a favorite thing, remember it.
If the user changes a favorite thing, remember the new value.

Do NOT remember:
- greetings
- questions
- temporary casual conversation

Return ONLY JSON.

Use EXACTLY these keys:

should_remember
category
memory_type
value
importance
memory_text

Example:

{{
    "should_remember": true,
    "category": "preference",
    "memory_type": "favorite",
    "value": "Minecraft",
    "importance": 8,
    "memory_text": "Saket's favorite game is Minecraft."
}}

User message:
{user_message}
"""

        response = self.model.chat([
            {
                "role": "system",
                "content": (
                    "You are ARVEN's memory extraction engine. "
                    "Return only JSON."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ])

        response = response.strip()

        try:
            data = json.loads(response)

        except json.JSONDecodeError:

            start = response.find("{")
            end = response.rfind("}")

            if start == -1 or end == -1:
                return self._empty()

            try:
                data = json.loads(response[start:end + 1])
            except json.JSONDecodeError:
                return self._empty()

        # Normalize common model mistakes
        if "should_remember" not in data:

            if "should_reremember" in data:
                data["should_remember"] = data.pop(
                    "should_reremember"
                )

            elif "should_remember_this" in data:
                data["should_remember"] = data.pop(
                    "should_remember_this"
                )

        # Normalize value
        value = data.get("value")

        if isinstance(value, list):
            value = ", ".join(str(x) for x in value)

        data["value"] = value

        # Ensure required fields exist
        data.setdefault("should_remember", False)
        data.setdefault("category", None)
        data.setdefault("memory_type", None)
        data.setdefault("importance", 0)
        data.setdefault("memory_text", None)

        return data

    def _empty(self):

        return {
            "should_remember": False,
            "category": None,
            "memory_type": None,
            "value": None,
            "importance": 0,
            "memory_text": None
        }
