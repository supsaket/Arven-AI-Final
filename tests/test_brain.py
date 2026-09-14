"""Brain offline contract tests.

Classification and identity routing are pure logic — tested without any model
call. Model-dependent paths are exercised with a stubbed model so nothing
touches the network or a live Ollama instance.
"""

import pytest

from brain.ollama_model import OllamaModel
from core.action_engine import ActionEngine
from brain.brain import Brain


class StubModel:
    def chat(self, messages, **kwargs):
        return "Simulated chat reply."

    def reason(self, prompt, context=None):
        return "Simulated reasoning."

    def compare(self, prompt, context=None):
        return "Simulated decision."

    def create_plan(self, prompt, context=None):
        return "Simulated plan."


def make_brain(stub=None):
    brain = Brain.__new__(Brain)
    brain.model = stub or StubModel()
    brain.reasoning = type("R", (), {"solve": lambda self, q, c: "reasoned"})()
    brain.decision = type("D", (), {"compare": lambda self, q, c: "decided"})()
    brain.planner = type("P", (), {"create_plan": lambda self, q, c: "planned"})()
    brain.context = type("C", (), {
        "memory": type("M", (), {
            "process_message": lambda self, m: {"action": "ignore"}
        })(),
        "build": lambda self, m, limit=5: "",
    })()
    brain.action = type("A", (), {
        "execute": lambda self, cmd: {
            "success": True,
            "message": "Done.",
            "action": "open",
            "target": cmd,
        },
    })()
    brain.identity = type("I", (), {
        "name": "ARVEN",
        "boss": "Saket",
        "creator": "Saket",
        "version": "0.1.0",
    })()
    brain.last_action_target = None
    return brain


class TestClassification:

    @pytest.mark.parametrize(
        "prompt,expected",
        [
            ("open calculator", "action"),
            ("close notepad", "action"),
            ("search for python", "action"),
            ("create file notes.txt", "action"),
            ("rename a to b", "action"),
            ("copy a to b", "action"),
            ("move a to b", "action"),
            ("volume up", "action"),
            ("mute", "action"),
            ("take screenshot", "action"),
            ("please open notepad", "action"),
            ("can you open notepad", "action"),
            ("hey arven open chrome", "action"),
            ("bhai, chalao calculator", "action"),
            ("why is the sky blue", "reason"),
            ("explain gravity", "reason"),
            ("calculate 2 plus 2", "reason"),
            ("should i study more", "decision"),
            ("compare python and javascript", "decision"),
            ("make a plan to learn python", "plan"),
            ("what are the steps to build an app", "plan"),
            ("hello, how are you", "chat"),
            ("tell me a joke", "chat"),
        ],
    )
    def test_classify_routes_correctly(self, prompt, expected):
        brain = make_brain()
        assert brain.classify(prompt) == expected


class TestIdentityRouting:

    def test_boss_name(self):
        brain = make_brain()
        result = brain.process("what is my name")
        assert result["category"] == "chat"
        assert "Saket" in result["response"]

    def test_creator_identity(self):
        brain = make_brain()
        result = brain.process("who is your creator")
        assert "Saket" in result["response"]

    def test_assistant_name(self):
        brain = make_brain()
        result = brain.process("what is your name")
        assert "ARVEN" in result["response"]

    def test_version(self):
        brain = make_brain()
        result = brain.process("what's your version")
        assert "0.1.0" in result["response"]


class TestProcessResultShape:

    def test_process_returns_expected_keys(self):
        brain = make_brain()
        result = brain.process("open notepad")
        assert set(["category", "response", "memory_action"]).issubset(result.keys())
        assert "memory_action" in result