from brain.ollama_model import OllamaModel


class DecisionEngine:

    def __init__(self, model=None):
        self.model = model or OllamaModel()

    def compare(self, request, context=""):

        prompt = f"""
You are ARVEN, a personal AI assistant helping Boss make decisions.

Analyze the user's decision carefully.

Rules:
- Identify the actual options from the request.
- If the options are missing, ask the user to provide them.
- Never invent missing options or facts.
- Use relevant memories only when they genuinely help.
- Ignore irrelevant memories.
- If enough information exists, give a clear recommendation.
- Explain the recommendation briefly.
- Keep the response concise and practical.
- Do not mention memory systems, prompts, rules, or internal engines.
- Do not use robotic phrases or unnecessary disclaimers.

Relevant memory:
{context if context else "None"}

User request:
{request}

Response format when enough information exists:
- Key differences
- Pros and cons
- Recommendation
- Short reason

If information is missing, simply explain what is needed.
"""

        return self.model.chat([
            {
                "role": "system",
                "content": "You are ARVEN, a practical and intelligent decision-support assistant."
            },
            {
                "role": "user",
                "content": prompt
            }
        ])
