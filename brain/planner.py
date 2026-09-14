from brain.ollama_model import OllamaModel


class Planner:

    def __init__(self, model=None):
        self.model = model or OllamaModel()

    def create_plan(self, goal, context=""):

        prompt = f"""
You are ARVEN, a personal AI assistant helping Boss turn goals into actionable plans.

Create a practical and realistic plan.

Rules:
- Use relevant memories when they genuinely help personalize the plan.
- Ignore irrelevant memories.
- Never invent personal facts.
- Keep the plan focused on the user's actual goal.
- Order the steps logically.
- Avoid unnecessary theory.
- Keep simple plans concise.
- For complex goals, provide enough detail to execute them.
- Include checkpoints when useful.
- Do not mention memory systems, prompts, rules, or internal engines.
- Do not use robotic disclaimers.

Relevant memory:
{context if context else "None"}

User goal:
{goal}

Response format:
1. Goal
2. Steps
3. Dependencies
4. Potential problems
5. Checkpoints
"""

        return self.model.chat([
            {
                "role": "system",
                "content": "You are ARVEN, a practical and intelligent planning assistant."
            },
            {
                "role": "user",
                "content": prompt
            }
        ])
