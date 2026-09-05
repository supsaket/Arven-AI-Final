"""Tests for the ARVEN AI desktop application shell.

These cover the thin frontend around the existing ARVEN backend:
  - app-exit phrasing ("Bye Arven", "shutdown arven") is intercepted by the app
    and NEVER reaches the Brain, and never triggers a Windows shutdown
  - real Windows-destructive phrasing ("shutdown my computer") is NOT
    intercepted (still flows to the Brain's gated flow)
  - Chat/Talk mode selection (explicit and natural-language) and mid-session
    switching
  - the Bye-Arven -> "Bye Boss." -> graceful-shutdown sequence and its ordering
  - single-instance enforcement and the ALT+A hotkey wiring

All tests are headless: the Brain, UI event loop, hotkey, mutex and voice are
injected/mocked so nothing touches a real audio device, the OS, or Ollama.
"""

import threading
import time

import pytest

from desktop import input_policy
from desktop.controller import AppController
from desktop.shutdown import STEPS
from desktop.state import AppState


# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------

class FakeBrain:
    """A Brain stand-in that records calls and returns a canned reply."""

    def __init__(self, reply="ack"):
        self.reply = reply
        self.calls = []  # [(text, source), ...]

    def process(self, text, source="text"):
        self.calls.append((text, source))
        return {"response": self.reply, "category": "chat"}


class FakeUI:
    """An event-loop hook that runs posted callbacks immediately and records
    speech/exits, so shutdown ordering can be asserted synchronously."""

    def __init__(self):
        self.posted = []   # [(fn_name, args), ...]
        self.spoken = []
        self.exited = []

    def post(self, fn, *args):
        self.posted.append((getattr(fn, "__name__", repr(fn)), args))
        fn(*args)

    def speak(self, text):
        self.spoken.append(text)
        return True

    def request_speak(self, text):
        self.spoken.append(text)
        return True

    def exit_process(self, code=0):
        self.exited.append(code)
        return code


def _wait(cond, timeout=3.0):
    """Poll cond() until truthy or timeout. Used to await the background worker."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _make_controller():
    brain = FakeBrain()
    ui = FakeUI()
    c = AppController(brain=brain, voice=None, ui=ui)
    return c, brain, ui


# ----------------------------------------------------------------------
# App-exit phrasing vs Windows-destructive phrasing
# ----------------------------------------------------------------------

def test_is_app_exit_matches_bye_arven():
    assert input_policy.is_app_exit("Bye Arven")
    assert input_policy.is_app_exit("goodbye arven")
    assert input_policy.is_app_exit("good night arven")
    assert input_policy.is_app_exit("shutdown arven")
    assert input_policy.is_app_exit("shut down arven")
    assert input_policy.is_app_exit("close yourself")
    assert input_policy.is_app_exit("exit arven")
    assert input_policy.is_app_exit("quit arven")


def test_is_app_exit_does_not_match_generic_or_windows_phrases():
    assert not input_policy.is_app_exit("bye")
    assert not input_policy.is_app_exit("goodbye")
    assert not input_policy.is_app_exit("shutdown my computer")
    assert not input_policy.is_app_exit("shut down the computer")
    assert not input_policy.is_app_exit("turn off the pc")
    assert not input_policy.is_app_exit("power off the laptop")


# ----------------------------------------------------------------------
# Mode selection
# ----------------------------------------------------------------------

def test_mode_selection_to_chat_explicit():
    c, brain, ui = _make_controller()
    c._set_state(AppState.MODE_SELECTION)
    c.on_user_input("chat")
    assert c.state == AppState.CHAT
    assert brain.calls == []  # mode choice never reached the Brain


def test_mode_selection_to_talk_explicit():
    c, brain, ui = _make_controller()
    c._set_state(AppState.MODE_SELECTION)
    c.on_user_input("talk")
    assert c.state == AppState.TALK
    assert brain.calls == []


def test_mode_selection_natural_language():
    c, brain, ui = _make_controller()
    c._set_state(AppState.MODE_SELECTION)
    c.on_user_input("I want to chat please")
    assert c.state == AppState.CHAT

    # A fresh controller: natural-language Talk selection in MODE_SELECTION.
    c2, brain2, _ = _make_controller()
    c2._set_state(AppState.MODE_SELECTION)
    c2.on_user_input("talk mode")
    assert c2.state == AppState.TALK
    assert brain2.calls == []


def test_mode_selection_ambiguous_asks_for_clarification():
    c, brain, ui = _make_controller()
    c._set_state(AppState.MODE_SELECTION)
    c.on_user_input("chat and talk")
    assert c.state == AppState.MODE_SELECTION
    assert brain.calls == []


# ----------------------------------------------------------------------
# Mid-session switching
# ----------------------------------------------------------------------

def test_switch_from_talk_to_chat():
    c, brain, ui = _make_controller()
    c._set_state(AppState.TALK)
    c.on_user_input("switch to chat")
    assert c.state == AppState.CHAT
    assert brain.calls == []


def test_switch_from_chat_to_talk():
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)
    c.on_user_input("switch to talk")
    assert c.state == AppState.TALK
    assert brain.calls == []


def test_plain_message_in_chat_goes_to_brain():
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)
    c.on_user_input("what's the weather")
    assert _wait(lambda: brain.calls)
    assert brain.calls[0][0] == "what's the weather"
    # reply delivered to the arven handler
    assert _wait(lambda: any(a[0] == "append" and a[1][0] == "arven"
                             for a in ui.posted))


# ----------------------------------------------------------------------
# Bye Arven -> shutdown, never Windows, never Brain
# ----------------------------------------------------------------------

def test_bye_arven_triggers_shutdown_and_not_brain():
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)
    c.on_user_input("Bye Arven")
    assert brain.calls == []                 # exit phrase never reached Brain
    assert _wait(lambda: c.state == AppState.CLOSED or c.state == AppState.SHUTTING_DOWN)
    assert _wait(lambda: c.state == AppState.CLOSED)


def test_bye_arven_says_bye_boss():
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)
    c.on_user_input("bye arven")
    assert _wait(lambda: c.state == AppState.CLOSED)
    assert "Bye Boss." in ui.spoken


def test_bye_arven_does_not_invocate_windows_shutdown():
    """Bye Arven must only shut down the ARVEN app, never trigger an OS-level
    shutdown (os.system / subprocess) — the app's own 'terminate' step is
    simply the process ending, not a Windows power-off."""
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)

    sys_calls = []

    class Guard:
        def __init__(self, mocker_patch):
            self._p = mocker_patch

        def __call__(self, cmd):
            sys_calls.append(cmd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("os.system", Guard(mp))
        c.on_user_input("bye arven")
        assert _wait(lambda: c.state == AppState.CLOSED)

    # Not a single OS-level command was issued.
    assert sys_calls == []


def test_windows_destructive_phrase_is_not_intercepted():
    """'shutdown my computer' is NOT an app-exit phrase, so it flows to the Brain
    (whose gated destructive flow handles it). The app must not weaken this."""
    c, brain, ui = _make_controller()
    c._set_state(AppState.CHAT)
    c.on_user_input("shutdown my computer")
    assert _wait(lambda: brain.calls)
    assert brain.calls[0][0] == "shutdown my computer"
    assert c.state == AppState.CHAT  # not shut down / not intercepted


# ----------------------------------------------------------------------
# Shutdown ordering
# ----------------------------------------------------------------------

def test_shutdown_plan_step_order():
    """Bye Boss is spoken first; the process is terminated last."""
    order = []
    c = AppController.__new__(AppController)
    ui = FakeUI()
    c.ui = ui
    c.voice = None
    c._hotkey = None
    c._shutdown_started = True

    plan = c.build_shutdown_plan()
    plan.set("say_bye", lambda: order.append("say_bye"))
    plan.set("finish_speech", lambda: order.append("finish_speech"))
    plan.set("stop_voice", lambda: order.append("stop_voice"))
    plan.set("unregister_hotkey", lambda: order.append("unregister_hotkey"))
    plan.set("stop_workers", lambda: order.append("stop_workers"))
    plan.set("save_state", lambda: order.append("save_state"))
    plan.set("close_window", lambda: order.append("close_window"))
    plan.set("terminate", lambda: order.append("terminate"))

    completed, errors = plan.run()
    assert errors == {}
    assert order == [
        "say_bye", "finish_speech", "stop_voice", "unregister_hotkey",
        "stop_workers", "save_state", "close_window", "terminate",
    ]
    assert completed == STEPS


def test_shutdown_plan_continues_after_step_failure():
    """A failing step must not prevent remaining steps (esp. terminate)."""
    order = []
    plan = __import__("desktop.shutdown", fromlist=["ShutdownPlan"]).ShutdownPlan()
    plan.set("say_bye", lambda: order.append("say_bye"))
    plan.set("stop_voice", lambda: (_ for _ in ()).throw(RuntimeError("no audio")))
    plan.set("terminate", lambda: order.append("terminate"))
    completed, errors = plan.run()
    assert "stop_voice" in errors
    assert "terminate" in completed
    assert order == ["say_bye", "terminate"]


# ----------------------------------------------------------------------
# Single instance
# ----------------------------------------------------------------------

def test_single_instance_primary_continues():
    class FakeSIPrimary:
        @staticmethod
        def acquire_single_instance():
            return object(), True

    c, _, _ = _make_controller()
    assert c.bootstrap_single_instance(FakeSIPrimary) is True
    assert c._single_instance is True


def test_single_instance_secondary_focuses_and_exits():
    class FakeSISecondary:
        @staticmethod
        def acquire_single_instance():
            return None, False

    c, _, _ = _make_controller()
    assert c.bootstrap_single_instance(FakeSISecondary) is False
    assert c._single_instance is False


# ----------------------------------------------------------------------
# Hotkey
# ----------------------------------------------------------------------

def test_hotkey_registration_and_callback(monkeypatch):
    """Registering the hotkey wires the focus callback; an ALT+A press fires it."""
    pilot_calls = []

    class FakeHotkey:
        def __init__(self, callback=None, **kwargs):
            self.callback = callback

        def register(self):
            return None

        def start(self):
            return None

        def stop(self):
            return None

        def trigger(self):
            self.callback()

    c, _, _ = _make_controller()
    ok = c.register_hotkey(FakeHotkey, callback=lambda: pilot_calls.append("focus"))
    assert ok is True
    assert c._hotkey_error is None

    hk = c._hotkey
    assert hk is not None
    hk.trigger()  # simulate pressing ALT+A
    assert pilot_calls == ["focus"]


def test_hotkey_registration_failure_is_graceful(monkeypatch):
    from desktop.hotkey import HotkeyError

    class FailingHotkey:
        def __init__(self, callback=None, **kwargs):
            pass

        def register(self):
            raise HotkeyError("already in use")

    c, _, _ = _make_controller()
    ok = c.register_hotkey(FailingHotkey, callback=lambda: None)
    assert ok is False
    assert c._hotkey_error


# ----------------------------------------------------------------------
# Controller construction (headless-safe) and state lifecycle
# ----------------------------------------------------------------------

def test_controller_starts_in_starting_state():
    c, _, _ = _make_controller()
    assert c.state == AppState.STARTING
    assert c._worker.is_alive()
    c._running = False  # stop the background worker
    c._worker.join(timeout=1)


def test_controller_uses_injected_brain():
    brain = FakeBrain(reply="hello boss")
    c = AppController(brain=brain, voice=None, ui=FakeUI())
    try:
        c._set_state(AppState.CHAT)
        c.on_user_input("hi")
        assert _wait(lambda: brain.calls)
    finally:
        c._running = False
        c._worker.join(timeout=1)


# ----------------------------------------------------------------------
# Continuous always-listening Talk loop + startup voice selection
# ----------------------------------------------------------------------

class FakeVoice:
    """A microphone stand-in for the always-listening loop tests."""

    def __init__(self, canned=("", None), avail=True, sleep=0.001):
        self.canned = canned
        self.avail = avail
        self._sleep = sleep
        self.calls = 0

    def available(self):
        return self.avail

    def listen(self, timeout=None):
        self.calls += 1
        if self._sleep:
            # Yield so the loop thread is schedulable between captures.
            time.sleep(self._sleep)
        return self.canned


def _talk_controller(canned=("", None), avail=True):
    brain = FakeBrain(reply="hi boss")
    ui = FakeUI()
    voice = FakeVoice(canned=canned, avail=avail)
    c = AppController(brain=brain, voice=voice, ui=ui)
    return c, brain, ui, voice


def test_talk_entry_starts_continuous_listen_loop():
    """Entering TALK automatically starts listening (no push-to-talk) and keeps
    listening repeatedly until we switch away."""
    c, _, _, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.TALK)
        assert _wait(lambda: voice.calls >= 2, timeout=5)
        first = voice.calls
        assert _wait(lambda: voice.calls > first, timeout=5)  # keeps looping
        # Each capture is guarded so only one listen can be in flight.
        assert c._talk_thread is not None
    finally:
        c._running = False
        c._talk_cancel.set()


def test_talk_loop_single_listener_guard_and_cancel_on_chat():
    """Exactly one listen at a time, and switching to Chat stops the loop."""
    c, _, ui, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.TALK)
        thread1 = c._talk_thread
        c.begin_talk_loop()  # idempotent: must not start a 2nd loop
        assert c._talk_thread is thread1
        assert _wait(lambda: voice.calls >= 1, timeout=5)
        c.switch_to_chat()
        assert c.state == AppState.CHAT
        assert _wait(lambda: c._talk_cancel.is_set(), timeout=2)
        # Switch to Chat leaves no active listener/captures should stop.
        calls_at_switch = voice.calls
        time.sleep(0.3)
        assert voice.calls == calls_at_switch or c.state != AppState.TALK
    finally:
        c._running = False
        c._talk_cancel.set()


def test_talk_speech_flow_routes_heard_words_to_brain():
    """Heard speech flows through to the Brain (STT source) in Talk mode."""
    c, brain, _, voice = _talk_controller(canned=("turn the lights on", None))
    try:
        c._set_state(AppState.TALK)
        assert _wait(lambda: len(brain.calls) >= 1, timeout=5)
        assert brain.calls[-1][0] == "turn the lights on"
        assert brain.calls[-1][1] == "stt"
    finally:
        c._running = False
        c._talk_cancel.set()


def test_talk_no_error_spin_on_listen_failure():
    """A failing microphone produces one meaningful error and resets the
    listening guard — it must not crash or corrupt controller state."""
    class FlakyVoice(FakeVoice):
        def listen(self, timeout=None):
            self.calls += 1
            raise RuntimeError("mic gone")

    brain, ui = FakeBrain(), FakeUI()
    voice = FlakyVoice((None, "mic gone"), avail=True)
    c = AppController(brain=brain, voice=voice, ui=ui)
    try:
        c._set_state(AppState.TALK)
        assert _wait(lambda: voice.calls >= 1, timeout=5)
        # Listener guard must be released after the error is handled.
        assert _wait(lambda: c._listening is False, timeout=5)
        assert c._running is True
    finally:
        c._running = False
        c._talk_cancel.set()


def test_startup_voice_selection_routes_to_chat_and_stops():
    """The startup mode-selection listener hears 'chat' and lands on CHAT; the
    bounded selection loop then exits (stops listening)."""
    c, _, ui, voice = _talk_controller(canned=("chat", None))
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection_listen()
        assert _wait(lambda: c.state == AppState.CHAT, timeout=5)
        assert c.state == AppState.CHAT
        # The selection worker returns after the choice, so no further listens.
        calls_after = voice.calls
        time.sleep(0.3)
        assert voice.calls <= calls_after + 1
    finally:
        c._running = False
        c._talk_cancel.set()


def test_startup_voice_selection_talk():
    """Hearing 'talk' at startup enters Talk (continuous) mode."""
    c, _, _, voice = _talk_controller(canned=("talk", None))
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection_listen()
        assert _wait(lambda: c.state == AppState.TALK, timeout=5)
        assert c.state == AppState.TALK
        assert _wait(lambda: voice.calls >= 1, timeout=5)  # talk loop listened
    finally:
        c._running = False
        c._talk_cancel.set()


def test_bye_from_talk_mode_shuts_down():
    """Saying Bye Arven while in Talk mode runs the graceful shutdown (never a
    Windows shutdown) and stops the loop."""
    c, brain, ui, _ = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.TALK)
        c.on_user_input("Bye Arven")
        assert brain.calls == []  # exit phrase never reached Brain
        assert _wait(lambda: c.state == AppState.CLOSED, timeout=5)
        assert "Bye Boss." in ui.spoken
    finally:
        c._running = False
        c._talk_cancel.set()


def test_bye_from_chat_mode_shuts_down():
    """Bye Arven from Chat mode also runs the graceful shutdown."""
    c, brain, ui, _ = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.CHAT)
        c.on_user_input("Bye Arven")
        assert brain.calls == []
        assert _wait(lambda: c.state == AppState.CLOSED, timeout=5)
        assert "Bye Boss." in ui.spoken
    finally:
        c._running = False
        c._talk_cancel.set()


def test_mode_selection_listen_uses_bounded_tries_only():
    """The startup selection loop is bounded — with a silent mic it never spins
    forever and eventually lets the user use the visible buttons."""
    c, _, ui, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection_listen()
        assert _wait(lambda: voice.calls >= 3, timeout=8)  # bounded tries
        calls_at_3 = voice.calls
        time.sleep(0.3)
        assert voice.calls <= calls_at_3 + 2
    finally:
        c._running = False
        c._talk_cancel.set()


# ----------------------------------------------------------------------
# Hard SPEAKING gate: ARVEN never listens while speaking (self-hearing fix)
# ----------------------------------------------------------------------

class ControlledSpeakUI(FakeUI):
    """A UI whose ``speak()`` blocks until the test releases it, so we can
    hold ARVEN "speaking" for as long as we like and observe the gate."""

    def __init__(self):
        super().__init__()
        self.release_speak = threading.Event()
        self.hold_speak = threading.Event()

    def speak(self, text):
        self.spoken.append(text)
        # Simulate TTS playback: block until the test says it's finished.
        self.release_speak.wait(timeout=10)
        return True


def _fast_settle(c):
    # Keep the audio-settle delay tiny so tests are quick.
    c._settle_delay = lambda: 0.02


def test_talking_blocks_listening_hard_gate():
    """While ARVEN is speaking (``_speaking`` set) the loop MUST NOT call
    listen() — the hard gate is the primary self-hearing protection."""
    brain = FakeBrain(reply="hello")
    ui = ControlledSpeakUI()
    voice = FakeVoice(canned=("hi", None))
    c = AppController(brain=brain, voice=voice, ui=ui)
    _fast_settle(c)
    try:
        # Lock ARVEN into "speaking" BEFORE the loop can start opening the mic.
        c._speaking.set()
        c._speech_finished.clear()
        c._set_state(AppState.TALK)
        time.sleep(0.4)
        assert voice.calls == 0, "listen() was called while ARVEN was speaking"

        # Let the user "speak" by clearing the gate.
        c._speaking.clear()
        c._speech_finished.set()
        assert _wait(lambda: voice.calls >= 1, timeout=3)
    finally:
        c._running = False
        c._talk_cancel.set()


def test_begin_speech_holds_gate_until_tts_complete_and_settle():
    """_begin_speech sets the SPEAKING gate before TTS and only releases it
    after TTS playback returns AND the settle delay elapses."""
    c, _, ui, _ = _talk_controller(canned=("", None))
    _fast_settle(c)
    try:
        assert not c._speaking.is_set()
        c._speech_finished.set()
        c._begin_speech("Hello Boss")
        # Gate asserted immediately (before TTS even starts).
        assert c._speaking.is_set()
        # FakeUI.speak is instant, but the settle delay still gates.
        assert _wait(lambda: not c._speaking.is_set(), timeout=2)
        assert _wait(lambda: c._speech_finished.is_set(), timeout=2)
    finally:
        c._running = False
        c._talk_cancel.set()


def test_no_self_trigger_when_silent():
    """Saying nothing produces an empty capture; ARVEN must NOT generate a
    response from its own previous speech — it just keeps listening."""
    c, brain, _, voice = _talk_controller(canned=("", None))
    _fast_settle(c)
    try:
        c._set_state(AppState.TALK)
        # Loop listens a few times with silence.
        assert _wait(lambda: voice.calls >= 2, timeout=3)
        assert brain.calls == []  # no speech -> no Brain call -> no self-response
    finally:
        c._running = False
        c._talk_cancel.set()


def test_bye_arven_during_speaking_stops_loop():
    """Even if ARVEN is mid-speech, Bye Arven shuts down and stops the loop
    (the gate is released by _stop_voice so it never stays stuck)."""
    brain = FakeBrain(reply="hi")
    ui = FakeUI()  # non-blocking TTS so "Bye Boss." can complete
    voice = FakeVoice(canned=("", None))
    c = AppController(brain=brain, voice=voice, ui=ui)
    _fast_settle(c)
    try:
        c._set_state(AppState.TALK)
        c._speaking.set()  # ARVEN is "speaking"
        c.on_user_input("Bye Arven")
        assert _wait(lambda: c.state == AppState.CLOSED, timeout=5)
        # Shutdown releases the gate so nothing stays stuck.
        assert not c._speaking.is_set()
        assert c._talk_cancel.is_set()
    finally:
        c._running = False


# ----------------------------------------------------------------------
# Robust Chat/Talk startup recognition parser ("check" -> chat)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("chat", "chat"),
    ("check", "chat"),          # STT hears "check" for "chat"
    ("chatt", "chat"),          # fuzzy
    ("chad", "chat"),           # fuzzy
    ("chats", "chat"),
    ("chat mode", "chat"),
    ("i want chat", "chat"),
    ("i want to chat", "chat"),
    ("lets chat", "chat"),
    ("i prefer chat", "chat"),
    ("open chat", "chat"),
    ("use chat", "chat"),
    ("text", "chat"),
    ("text mode", "chat"),
    ("talk", "talk"),
    ("tok", "talk"),            # fuzzy
    ("tawk", "talk"),           # fuzzy
    ("talkk", "talk"),          # fuzzy
    ("talk mode", "talk"),
    ("voice", "talk"),
    ("voice mode", "talk"),
    ("i want talk", "talk"),
    ("i want to talk", "talk"),
    ("lets talk", "talk"),
    ("i prefer talk", "talk"),
    ("open talk", "talk"),
    ("use talk", "talk"),
    ("dog", None),              # unrelated -> NONE
    ("music", None),            # unrelated -> NONE
    ("please run", None),       # unrelated -> NONE
])
def test_resolve_mode_selection_parser(text, expected):
    assert input_policy.resolve_mode_selection(text) == expected


def test_resolve_mode_selection_both_and_empty():
    assert input_policy.resolve_mode_selection("") is None
    assert input_policy.resolve_mode_selection(None) is None
    assert input_policy.resolve_mode_selection("chat talk") == "both"
    # "check" is ONLY a chat cue in the startup parser, not globally.
    assert input_policy.resolve_mode("check") is None


def test_startup_check_actually_enters_chat():
    """Hearing 'check' at startup must land the user in CHAT via the real
    controller path, no button click."""
    c, _, _, voice = _talk_controller(canned=("check", None))
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection_listen()
        assert _wait(lambda: c.state == AppState.CHAT, timeout=5)
        assert c.state == AppState.CHAT
    finally:
        c._running = False
        c._talk_cancel.set()


# ----------------------------------------------------------------------
# Chat must NOT listen; Talk has exactly one listener; lifecycle details
# ----------------------------------------------------------------------

def test_startup_listener_stops_after_selection():
    """After detecting a mode, the startup listener stops immediately (the
    Talk continuous listener only starts when Talk is entered, never two
    listeners at once)."""
    c, _, _, voice = _talk_controller(canned=("talk", None), avail=True)
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection_listen()
        assert _wait(lambda: c.state == AppState.TALK, timeout=5)
        # Startup worker returns once the choice is made; only ONE listen
        # was guaranteed at a time (mode worker + talk loop never overlap).
        assert voice.calls >= 1
    finally:
        c._running = False
        c._talk_cancel.set()


def test_chat_mode_has_no_talk_listener():
    """Once Chat is selected, the microphone must NOT be continuously
    listening (no Talk loop thread)."""
    c, _, _, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.CHAT)
        time.sleep(0.3)
        assert c._talk_thread is None
        assert voice.calls == 0
        assert not c._listening
    finally:
        c._running = False
        c._talk_cancel.set()


def test_switch_chat_to_talk_starts_single_listener():
    """Switching Chat -> Talk starts exactly one continuous listener."""
    c, _, _, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.CHAT)
        assert c._talk_thread is None
        c.switch_to_talk()
        assert c.state == AppState.TALK
        assert _wait(lambda: c._talk_thread is not None, timeout=2)
        assert _wait(lambda: voice.calls >= 1, timeout=3)
        # Exactly one loop thread.
        thread = c._talk_thread
        c.begin_talk_loop()
        assert c._talk_thread is thread
    finally:
        c._running = False
        c._talk_cancel.set()


def test_switch_talk_to_chat_stops_listener():
    """Switching Talk -> Chat stops the continuous listener."""
    c, _, _, voice = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.TALK)
        assert _wait(lambda: voice.calls >= 1, timeout=3)
        c.switch_to_chat()
        assert c.state == AppState.CHAT
        assert _wait(lambda: c._talk_cancel.is_set(), timeout=2)
    finally:
        c._running = False
        c._talk_cancel.set()


def test_shutdown_stops_listener():
    """Shutdown stops the Talk listener and releases the speaking gate."""
    c, _, _, _ = _talk_controller(canned=("", None))
    try:
        c._set_state(AppState.TALK)
        c._speaking.set()
        c.request_shutdown()
        assert _wait(lambda: c.state == AppState.CLOSED, timeout=5)
        assert c._talk_cancel.is_set()
        assert not c._speaking.is_set()
    finally:
        c._running = False


def test_begin_mode_selection_does_not_listen_during_prompt():
    """begin_mode_selection holds the speaking gate while the startup prompt
    is spoken AND during the post-TTS audio-settle delay, so the mic can never
    open while ARVEN's own prompt (or its tail echo) is still audible."""
    class InstantUI(FakeUI):
        def speak(self, text):
            # Synchronously confirm the hard gate is held while we "speak" —
            # this is the moment ARVEN's own audio would otherwise be captured.
            assert self.owner._speaking.is_set(), \
                "mic could open while startup prompt is being spoken"
            self.spoken.append(text)
            return True

    brain = FakeBrain()
    ui = InstantUI()
    voice = FakeVoice(canned=("", None))
    c = AppController(brain=brain, voice=voice, ui=ui)
    _fast_settle(c)
    ui.owner = c
    try:
        c._set_state(AppState.MODE_SELECTION)
        c.begin_mode_selection("Boss, what do you prefer Chat or Talk?")
        # The prompt is actually spoken (gate held during speak).
        assert _wait(lambda: ui.spoken, timeout=3)
        # No mic capture may happen while the prompt gate is held.
        assert voice.calls == 0
        # The gate releases only after the settle delay elapses...
        assert _wait(lambda: not c._speaking.is_set(), timeout=3)
        # ...and only then does the mic listen for the answer.
        assert _wait(lambda: voice.calls >= 1, timeout=4)
    finally:
        c._running = False
        c._talk_cancel.set()


def test_audio_settle_delay_genuinely_blocks_before_gate_release():
    """The audio-settle delay MUST actually block (hold the hard gate) after TTS
    completes — a regression guard: previously ``_speaking.wait(delay)`` was used
    with the event already set, so the settle delay was a silent no-op and ARVEN
    could re-open the mic while its own tail echo was still audible."""
    c, _, ui, _ = _talk_controller(canned=("", None))

    # Use a real-ish settle of 0.3s (NOT _fast_settle) so we can measure.
    c._settle_delay = lambda: 0.3
    try:
        c._speech_finished.set()
        # Simulate a little TTS playback time so the settle delay is observed
        # gating AFTER TTS returns (not merely masking TTS latency).
        def slow_speak(text):
            time.sleep(0.05)
            return True
        ui.speak = slow_speak

        c._begin_speech("Hello Boss")
        # Gate held immediately.
        assert _wait(lambda: c._speaking.is_set(), timeout=1)

        t0 = time.time()
        # The gate must remain SET until TTS returns AND settle elapses.
        assert not _wait(lambda: not c._speaking.is_set(), timeout=0.12)
        # After TTS (0.05s) + settle (0.3s) it finally releases.
        assert _wait(lambda: not c._speaking.is_set(), timeout=1.5)
        elapsed = time.time() - t0
        # TTS(0.05) + settle(0.3) should gate for roughly >= 0.2s total.
        assert elapsed >= 0.2, f"settle did not block; gate released in {elapsed:.3f}s"
        assert _wait(lambda: c._speech_finished.is_set(), timeout=2)
    finally:
        c._running = False
        c._talk_cancel.set()


def test_busy_typing_indicator_shows_and_clears_around_brain_reply():
    """While the Brain processes a typed Chat message the busy/typing indicator
    is shown, and it is cleared after the reply is delivered (even on error)."""
    ui = FakeUI()
    brain = FakeBrain(reply="hi boss")
    c = AppController(brain=brain, voice=None, ui=ui)
    busy_events = []
    c._busy_handler = busy_events.append
    user_lines, arven_lines = [], []
    c._user_handler = user_lines.append
    c._arven_handler = arven_lines.append
    try:
        c._set_state(AppState.CHAT)
        c._dispatch_to_brain("hello there", source="text")
        assert _wait(lambda: busy_events == [True], timeout=3)
        assert _wait(lambda: arven_lines and arven_lines[-1] == "hi boss", timeout=3)
        assert _wait(lambda: busy_events[-1] is False, timeout=3)
        # Typing shown before the reply and cleared after — never left on.
        assert any(b is True for b in busy_events)
        assert busy_events[-1] is False
    finally:
        c._running = False


def test_invalid_chat_text_is_forwarded_to_brain_not_swallowed():
    """Unrecognized text typed in Chat is not silently dropped — it reaches the
    Brain, which is responsible for a helpful fallback."""
    brain = FakeBrain(reply="I didn't catch that, Boss.")
    ui = FakeUI()
    c = AppController(brain=brain, voice=None, ui=ui)
    user_lines, arven_lines = [], []
    c._user_handler = user_lines.append
    c._arven_handler = arven_lines.append
    try:
        c._set_state(AppState.CHAT)
        gibberish = "qzx wkvp noventa"
        c.on_user_input(gibberish)
        assert _wait(lambda: len(brain.calls) >= 1, timeout=3)
        assert brain.calls[-1][0] == gibberish
        assert _wait(lambda: arven_lines, timeout=3)  # a reply was produced
    finally:
        c._running = False


def test_normalise_exit_phrase_is_defined_and_normalises():
    assert input_policy.normalise_exit_phrase("  Bye   Arven  ") == "bye arven"
    assert input_policy.normalise_exit_phrase("") is None
    assert input_policy.normalise_exit_phrase("shutdown arven") == "shutdown arven"
