from brain.ollama_model import OllamaModel
from brain.reasoning import ReasoningEngine
from brain.decision import DecisionEngine
from brain.planner import Planner
from core.context import ContextManager
from core.action_engine import ActionEngine
from core.identity import Identity


class Brain:

    def __init__(self):

        self.model = OllamaModel()

        self.reasoning = ReasoningEngine(self.model)
        self.decision = DecisionEngine(self.model)
        self.planner = Planner(self.model)

        self.context = ContextManager()
        self.action = ActionEngine()
        self.identity = Identity()

        self.last_action_target = None

    # =========================================================
    # CLASSIFICATION
    # =========================================================

    def classify(self, request):

        text = request.lower().strip()

        prefixes = [
            "please ",
            "can you ",
            "could you ",
            "would you ",
            "do me a favour, ",
            "do me a favor, ",
"hey arven, ",
            "hey arven ",
            "arven, ",
            "arven ",
            "bhai ",
            "boss, "
        ]

        cleaned = text

        changed = True

        while changed:

            changed = False

            for prefix in prefixes:

                if cleaned.startswith(prefix):

                    cleaned = cleaned[len(prefix):].strip()
                    changed = True
                    break

        # -----------------------------------------------------
        # DIRECT ACTION COMMANDS
        # -----------------------------------------------------

        action_starts = [
            "open ",
            "close ",
            "launch ",
            "start ",
            "search ",
            "run ",
            "execute ",
            "create ",
            "rename ",
            "copy ",
            "move ",
            "volume ",
            "mute",
            "unmute",
            "screenshot",
            "take screenshot",
            "take a screenshot",

            # Hinglish
            "khol",
            "kholo",
            "open kar",
            "chalao",
            "chala",
            "band kar",
            "band karo",
            "close kar",
            "close karo",
            "search kar",
            "dhundho",
            "dhundo"
        ]

        action_exact = [
            "volume up",
            "volume down",
            "mute",
            "unmute",
            "screenshot",
            "take screenshot",
            "take a screenshot",

            "voulme up",
            "voulme down",
            "vol up",
            "vol down",
            "turn volume up",
            "turn volume down",
            "increase volume",
            "decrease volume",

            "take screen shot",
            "take a screen shot"
        ]

        if (
            cleaned in action_exact
            or any(
                cleaned.startswith(x)
                for x in action_starts
            )
            or self._looks_like_hinglish_action(cleaned)
        ):
            return "action"

        # -----------------------------------------------------
        # REASONING
        # -----------------------------------------------------

        if any(x in text for x in [
            "why",
            "how does",
            "explain",
            "calculate",
            "solve",
            "reason",
            "what causes"
        ]):
            return "reason"

        # -----------------------------------------------------
        # DECISION
        # -----------------------------------------------------

        if any(x in text for x in [
            "should i",
            "which should",
            "choose between",
            "compare",
            "better option",
            "pros and cons"
        ]):
            return "decision"

        # -----------------------------------------------------
        # PLANNING
        # -----------------------------------------------------

        if any(x in text for x in [
            "create a plan",
            "make a plan",
            "plan to",
            "how can i achieve",
            "steps to",
            "roadmap"
        ]):
            return "plan"

        return "chat"

    # =========================================================
    # HINGLISH ACTION DETECTION
    # =========================================================

    def _looks_like_hinglish_action(self, text):

        action_words = [
            "khol",
            "kholo",
            "kholna",
            "open kar",
            "open karo",
            "chalao",
            "chala",
            "start kar",
            "start karo",
            "band kar",
            "band karo",
            "close kar",
            "close karo",
            "search kar",
            "search karo",
            "dhundho",
            "dhundo"
        ]

        return any(word in text for word in action_words)

    # =========================================================
    # ACTION NORMALIZATION
    # =========================================================

    def normalize_action_request(self, request):

        text = request.lower().strip()

        replacements = {
            "voulme up": "volume up",
            "voulme down": "volume down",
            "vol up": "volume up",
            "vol down": "volume down",
            "turn volume up": "volume up",
            "turn volume down": "volume down",
            "increase volume": "volume up",
            "decrease volume": "volume down",
            "take screen shot": "screenshot",
            "take a screen shot": "screenshot"
        }

        if text in replacements:
            return replacements[text]

        # -----------------------------------------------------
        # Common Hinglish patterns
        # -----------------------------------------------------

        patterns = [
            ("khol do ", "open "),
            ("kholo ", "open "),
            ("khol ", "open "),

            ("open kar do ", "open "),
            ("open karo ", "open "),
            ("open kar ", "open "),

            ("chala do ", "open "),
            ("chalao ", "open "),
            ("chala ", "open "),

            ("start kar do ", "open "),
            ("start karo ", "open "),
            ("start kar ", "open "),

            ("band kar do ", "close "),
            ("band karo ", "close "),
            ("band kar ", "close "),

            ("close kar do ", "close "),
            ("close karo ", "close "),
            ("close kar ", "close "),

            ("search kar do ", "search "),
            ("search karo ", "search "),
            ("search kar ", "search "),

            ("dhundho ", "search "),
            ("dhundo ", "search ")
        ]

        for wrong, correct in patterns:

            if text.startswith(wrong):
                return correct + text[len(wrong):].strip()

        # -----------------------------------------------------
        # "app open kar" / "app khol" patterns
        # -----------------------------------------------------

        if text.endswith(" open kar"):
            target = text[:-len(" open kar")].strip()

            if target:
                return f"open {target}"

        if text.endswith(" open karo"):
            target = text[:-len(" open karo")].strip()

            if target:
                return f"open {target}"

        if text.endswith(" khol"):
            target = text[:-len(" khol")].strip()

            if target:
                return f"open {target}"

        if text.endswith(" kholo"):
            target = text[:-len(" kholo")].strip()

            if target:
                return f"open {target}"

        if text.endswith(" chalao"):
            target = text[:-len(" chalao")].strip()

            if target:
                return f"open {target}"

        if text.endswith(" band kar"):
            target = text[:-len(" band kar")].strip()

            if target:
                return f"close {target}"

        if text.endswith(" band karo"):
            target = text[:-len(" band karo")].strip()

            if target:
                return f"close {target}"

        return request.strip()

    # =========================================================
    # MULTI ACTION PARSER
    # =========================================================

    def expand_action_request(self, request):

        normalized = self.normalize_action_request(request)

        text = normalized.lower().strip()

        # No multi-command
        if " and " not in text:
            return [normalized]

        # -----------------------------------------------------
        # Same verb repeated implicitly:
        #
        # open notepad and calculator and youtube
        #
        # becomes:
        # open notepad
        # open calculator
        # open youtube
        # -----------------------------------------------------

        verbs = [
            "open",
            "close",
            "launch",
            "start",
            "search",
            "run",
            "execute"
        ]

        first_word = text.split(" ", 1)[0]

        if first_word in verbs:

            remainder = text[len(first_word):].strip()

            parts = [
                part.strip()
                for part in remainder.split(" and ")
                if part.strip()
            ]

            if len(parts) > 1:

                return [
                    f"{first_word} {part}"
                    for part in parts
                ]

        # -----------------------------------------------------
        # Explicit mixed commands:
        #
        # open notepad and close calculator
        # -----------------------------------------------------

        parts = [
            part.strip()
            for part in normalized.split(" and ")
            if part.strip()
        ]

        if len(parts) > 1:
            return parts

        return [normalized]

    # =========================================================
    # ACTION EXECUTION
    # =========================================================

    def execute_actions(self, request):

        commands = self.expand_action_request(request)

        responses = []
        successful_targets = []

        for command in commands:

            cleaned = command.lower().strip()

            # ---------------------------------------------
            # Contextual close
            # ---------------------------------------------

            if cleaned in [
                "close it",
                "close that",
                "band kar",
                "band karo"
            ]:

                if self.last_action_target:

                    command = (
                        f"close {self.last_action_target}"
                    )

                else:

                    responses.append(
                        "Sorry Boss, I don't know what "
                        "'it' refers to."
                    )
                    continue

            # ---------------------------------------------
            # Execute
            # ---------------------------------------------

            result = self.action.execute(command)

            if result["success"]:

                responses.append(result["message"])

                if result["action"] == "open":

                    successful_targets.append(
                        result["target"]
                    )

            else:

                responses.append(
                    f"Sorry Boss, {result['message']}"
                )

        # Remember the most recently opened target

        if successful_targets:

            self.last_action_target = (
                successful_targets[-1]
            )

        return " ".join(responses)

    # =========================================================
    # MAIN PROCESSOR
    # =========================================================

    def process(self, request):

        category = self.classify(request)

        memory_action = (
            self.context.memory.process_message(
                request
            )
        )

        memory_context = (
            self.context.build(request)
        )

        # =====================================================
        # ACTION
        # =====================================================

        if category == "action":

            response_text = self.execute_actions(
                request
            )

            if response_text.startswith("Sorry Boss"):

                response = response_text

            else:

                response = (
                    f"Done, Boss. "
                    f"{response_text}"
                )

        # =====================================================
        # REASONING
        # =====================================================

        elif category == "reason":

            response = self.reasoning.solve(
                request,
                memory_context
            )

        # =====================================================
        # DECISION
        # =====================================================

        elif category == "decision":

            response = self.decision.compare(
                request,
                memory_context
            )

        # =====================================================
        # PLANNING
        # =====================================================

        elif category == "plan":

            response = self.planner.create_plan(
                request,
                memory_context
            )

        # =====================================================
        # NORMAL CHAT
        # =====================================================

        else:

            # -------------------------------------------------
            # Direct identity responses
            # -------------------------------------------------

            text = request.lower().strip()

            if any(x in text for x in [
                "what is my name",
                "what's my name",
                "who am i",
                "my name"
            ]):

                response = (
                    f"Your name is "
                    f"{self.identity.boss}, Boss."
                )

            elif any(x in text for x in [
                "who is your creator",
                "who created you",
                "who made you",
                "who built you",
                "who is your boss"
            ]):

                response = (
                    f"My creator is "
                    f"{self.identity.creator}, Boss."
                )

            elif any(x in text for x in [
                "what is your name",
                "what's your name",
                "who are you"
            ]):

                response = (
                    f"I'm {self.identity.name}, "
                    "your personal AI assistant, Boss."
                )

            elif any(x in text for x in [
                "what is your version",
                "what's your version",
                "which version are you",
                "version"
            ]):

                response = (
                    f"I'm running "
                    f"{self.identity.name} version "
                    f"{self.identity.version}, Boss."
                )

            else:

                system_prompt = (
                    f"You are {self.identity.name}, "
                    "a personal local AI assistant.\n"
                    f"Your name is {self.identity.name}.\n"
                    f"Your Boss is {self.identity.boss}.\n"
                    f"Your creator is {self.identity.creator}.\n"
                    "Address the user naturally as Boss.\n"
                    "Never identify yourself as Qwen or "
                    "another model.\n"
                    "Do not invent personal information.\n"
                    "Be natural, concise and helpful.\n\n"
                )

                if memory_context:

                    system_prompt += (
                        "Relevant information about Boss:\n"
                        f"{memory_context}\n\n"
                        "Use this information when relevant. "
                        "Do not mention the memory system."
                    )

                response = self.model.chat([
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": request
                    }
                ])

        return {
            "category": category,
            "response": response,
            "memory_action": memory_action
        }
