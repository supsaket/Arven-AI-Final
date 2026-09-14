"""ARVEN AI application controller.

The controller is the thin *shell* between the UI and the existing ARVEN
backend. It owns:
  - the single shared Brain (reused, never re-implemented)
  - a background worker that calls Brain.process without blocking the UI
  - application state (AppState) and mode selection / switching
  - Bye-Arven detection and the graceful shutdown sequence
  - the global hotkey and single-instance lock (when the real OS is in play)

Everything here is dependency-injected so the unit tests can run headless with
fakes (no tkinter, no microphone, no hotkey, no Windows shutdown).
"""

import logging
import queue
import threading
import time

from config import get_settings
from desktop import input_policy
from desktop.shutdown import ShutdownPlan
from desktop.state import AppState

log = logging.getLogger("arven.desktop.controller")


class _UIHook:
    """Abstract the UI event loop so the controller stays testable."""

    def post(self, fn, *args):
        """Schedule fn(*args) on the UI/main thread. Defaults to "immediate"."""
        fn(*args)

    def speak(self, text):
        """Speak text (best-effort, non-fatal if unavailable)."""
        return False

    def request_speak(self, text):
        """Speak text on a background thread (non-blocking)."""
        return False

    def exit_process(self, code=0):
        return code


class AppController:
    """State machine + Brain dispatch for the desktop app."""

    def __init__(self, brain=None, voice=None, ui=None):
        s = get_settings()
        from brain.brain import Brain
        self.brain = brain if brain is not None else Brain()
        self.voice = voice  # existing voice/input.VoiceInput (reused)
        self.ui = ui if ui is not None else _UIHook()

        self.state = AppState.STARTING
        self._queue = queue.Queue()
        self._running = True
        self._worker = threading.Thread(target=self._work, daemon=True,
                                        name="arven-brain-worker")
        self._worker.start()

        self._hotkey = None
        self._hotkey_error = None
        self._instance_handle = None
        self._single_instance = True

        # Welcome prompt (actual ARVEN voice greeting, best-effort).
        self._mode_prompt = s.APP_MODE_PROMPT
        self._bye_message = s.APP_BYE_MESSAGE

        # UI handler slots (bound via bind_ui once the window exists).
        self._state_handler = None
        self._user_handler = None
        self._arven_handler = None
        self._system_handler = None
        self._busy_handler = None
        self._status_handler = None
        self._close_handler = None
        self._shutdown_started = False
        self._listening = False
        # Continuous always-listening Talk loop state.
        self._talk_cancel = threading.Event()
        self._talk_thread = None
        # HARD SPEAKING GATE: set True while ARVEN is playing TTS (and during the
        # post-TTS audio-settle delay). The talk loop MUST NOT call voice.listen()
        # while this is set — this is what stops ARVEN from hearing its own voice.
        self._speaking = threading.Event()
        # Set only after TTS playback has fully completed AND the settle delay has
        # elapsed. Starts CLEARED so the loop always waits for (at least) one
        # speech cycle before it may open the microphone again after a dispatch.
        self._speech_finished = threading.Event()

    # ------------------------------------------------------------------
    # Startup / single-instance / hotkey
    # ------------------------------------------------------------------

    def bootstrap_single_instance(self, single_instance_module):
        """Acquire the single-instance lock. Returns True if this process is the
        primary instance and should continue; False if another is running."""
        handle, is_primary = single_instance_module.acquire_single_instance()
        self._instance_handle = handle
        self._single_instance = is_primary
        return is_primary

    def register_hotkey(self, hotkey_class, callback):
        """Register the global hotkey. Stores any error rather than crashing."""
        try:
            hk = hotkey_class(callback=callback)
            hk.register()
            hk.start()
            self._hotkey = hk
            self._hotkey_error = None
        except Exception as exc:
            log.error("hotkey registration failed: %s", exc)
            self._hotkey_error = str(exc)
        return self._hotkey_error is None and self._hotkey is not None

    # ------------------------------------------------------------------
    # Input routing
    # ------------------------------------------------------------------

    def on_user_input(self, text):
        """Route a single user message (typed or spoken) appropriately."""
        text = (text or "").strip()
        if not text:
            return

        if input_policy.is_app_exit(text):
            self.ui.post(self._append_system, "Bye Arven — closing ARVEN…")
            self.request_shutdown()
            return

        if self.state == AppState.MODE_SELECTION:
            self._handle_mode_selection(text)
            return

        if self.state == AppState.CHAT:
            mode = input_policy.resolve_switch(text)
            if mode == "talk":
                self._set_state(AppState.TALK)
                return
            if mode == "chat":
                return  # already in chat
            self._dispatch_to_brain(text)
            return

        if self.state == AppState.TALK:
            mode = input_policy.resolve_switch(text)
            if mode == "chat":
                self._set_state(AppState.CHAT)
                return
            if mode == "talk":
                return  # already in talk
            self._dispatch_to_brain(text, source="stt")
            return

    def _handle_mode_selection(self, text):
        # Startup-only, STT-tolerant parsing ("check" -> chat). Uses the
        # explicit-phrase + bounded-fuzzy parser; unrelated words are ignored.
        choice = input_policy.resolve_mode_selection(text)
        log.debug("MODE_SELECTION: raw=%r detected=%r", text, choice)
        if choice == "chat":
            self._set_state(AppState.CHAT)
        elif choice == "talk":
            self._set_state(AppState.TALK)
        elif choice == "both":
            self.ui.post(self._append_system,
                         "I caught both — please say just Chat or just Talk.")
        else:
            self.ui.post(self._append_system,
                         "Boss, did you say Chat or Talk? Just say one of them.")

    def select_chat(self):
        self._set_state(AppState.CHAT)

    def select_talk(self):
        if self._voice_can_listen():
            self._set_state(AppState.TALK)
        else:
            self.ui.post(self._append_system,
                         "I couldn't access the microphone. Voice mode is "
                         "unavailable — you can still use Chat below.")
            self._set_state(AppState.CHAT)

    def switch_to_chat(self):
        if self.state != AppState.CHAT:
            self._set_state(AppState.CHAT)

    def switch_to_talk(self):
        if self.state != AppState.TALK:
            if self._voice_can_listen():
                self._set_state(AppState.TALK)
            else:
                self.ui.post(self._append_system,
                             "I couldn't access the microphone. Voice mode is "
                             "unavailable — staying in Chat.")
                self._set_state(AppState.CHAT)

    # ------------------------------------------------------------------
    # Voice availability / listening
    # ------------------------------------------------------------------

    def voice_ready(self):
        """Best-effort check that a voice input object is wired up."""
        return self.voice is not None

    def begin_listen(self):
        """Begin a single voice listen (push-to-talk). Runs on a background
        thread; the result is routed through on_user_input. Uses a guard so
        overlapping listens never run (no runaway worker / no error spam)."""
        if not self.voice_ready():
            self.ui.post(self._set_status, "Voice input is unavailable.", "err")
            return
        if self._listening:
            return
        self._listening = True
        threading.Thread(target=self._listen_worker, daemon=True,
                         name="arven-voice-listen").start()

    def begin_mode_selection(self, prompt):
        """Speak the startup prompt, and only open the microphone AFTER the
        prompt TTS has completely finished (plus a short audio-settle delay).

        This prevents ARVEN's own "Chat or Talk?" question from being captured
        as a mode choice (part of the self-hearing/timing fix). The hard
        ``_speaking`` gate is asserted while the prompt plays so no listener
        can open while the startup prompt is audible.
        """
        settle = self._settle_delay()

        def _run():
            self._speaking.set()
            try:
                log.debug("MODE_SELECTION: speaking prompt")
                try:
                    self.ui.speak(prompt)
                except Exception as exc:
                    log.warning("mode prompt TTS raised: %s", exc)
                finally:
                    # Allow speaker tail / echo to settle before listening.
                    # NOTE: must be time.sleep, not _speaking.wait(settle) —
                    # Event.wait() returns immediately when already SET.
                    if settle > 0:
                        time.sleep(settle)
                    log.debug("MODE_SELECTION: prompt finished; starting listen")
            finally:
                self._speaking.clear()
            self.begin_mode_selection_listen()

        threading.Thread(target=_run, daemon=True,
                         name="arven-mode-prompt").start()

    def begin_mode_selection_listen(self):
        """After speaking the startup prompt, actually LISTEN for the answer.

        Runs a small bounded set of pushes (not an infinite loop) and routes
        each transcript through on_user_input -> mode selection. If the mic is
        unavailable, it falls back gracefully to the visible Chat/Talk buttons
        instead of spamming errors.
        """
        if not self.voice_ready():
            log.info("mode selection: no voice wired; using visible buttons")
            return
        if not self._voice_can_listen():
            log.info("mode selection: microphone unavailable; using buttons")
            self.ui.post(self._append_system,
                         "I couldn't access the microphone. You can choose "
                         "Chat or Talk below.")
            return
        threading.Thread(target=self._mode_selection_listen_worker,
                         daemon=True, name="arven-mode-listen").start()

    def _voice_can_listen(self):
        if not self.voice_ready():
            return False
        try:
            return bool(self.voice.available())
        except Exception as exc:
            log.warning("voice availability probe failed: %s", exc)
            return False

    def _mode_selection_listen_worker(self):
        # A short, one-shot, bounded loop: genuinely listen for the answer, but
        # never spin forever. Stops as soon as the user chooses a mode or we
        # exhaust tries. Never runs while the Talk loop is capturing (the
        # ``_listening`` guard makes mode-selection and Talk mutually exclusive).
        tries = 0
        while (self._running and self.state == AppState.MODE_SELECTION
               and tries < 3 and not self._listening and not self._speaking.is_set()):
            self._listening = True
            self.ui.post(self._set_status, "Listening for your choice…", "doing")
            try:
                text, error = self.voice.listen(timeout=6)
            except Exception as exc:
                log.warning("mode-selection listen error: %s", exc)
                self._listening = False
                break
            self._listening = False
            if text:
                normalized = " ".join((text or "").lower().strip().split())
                detected = input_policy.resolve_mode_selection(text)
                log.debug("MODE_SELECTION: raw=%r normalized=%r detected=%r",
                          text, normalized, detected)
                self.ui.post(self.append, "user", text)
                self.ui.post(self._set_status, "", "info")
                self.on_user_input(text)
                if self.state != AppState.MODE_SELECTION:
                    return  # one-shot: stop immediately once a mode is chosen
            tries += 1
        if self.state == AppState.MODE_SELECTION:
            self.ui.post(self._set_status,
                         "Choose Chat or Talk using the buttons below.", "info")

    def _listen_worker(self):
        # A single push-to-talk capture; never recurses and never loops for
        # errors — one failed attempt yields exactly one meaningful status.
        self.ui.post(self._set_status, "Listening… speak now.", "doing")
        try:
            text, error = self.voice.listen(timeout=8)
        except Exception as exc:
            log.exception("voice listen raised")
            self._listening = False
            self.ui.post(self._set_status,
                         f"Voice error: {type(exc).__name__}: {exc}", "err")
            return
        self._listening = False
        if text:
            self.ui.post(self._set_status, "Processing…", "doing")
            self.ui.post(self.append, "user", text)
            self.on_user_input(text)
        elif error:
            self.ui.post(self._set_status,
                         f"Couldn't hear you: {error}", "err")
        else:
            self.ui.post(self._set_status,
                         "I didn't catch that. Hold the mic to talk.", "info")

    # ------------------------------------------------------------------
    # Continuous always-listening Talk loop (no push-to-talk)
    # ------------------------------------------------------------------

    def begin_talk_loop(self):
        """Start the continuous Talk voice loop (idempotent).

        Exactly ONE talk loop and at most ONE active listen may exist at a time
        (the ``_listening`` guard plus the single ``_talk_thread`` guarantee this).
        """
        if not self._voice_can_listen():
            log.info("talk: no usable mic; running in chat-only mode")
            return
        if self._talk_thread is not None and self._talk_thread.is_alive():
            return  # already running
        self._talk_cancel.clear()
        self._talk_thread = threading.Thread(
            target=self._talk_loop_worker, daemon=True,
            name="arven-talk-loop")
        self._talk_thread.start()
        log.debug("TALK: listener started")

    def stop_talk_loop(self):
        """Request the continuous Talk loop to stop (non-blocking)."""
        self._talk_cancel.set()
        log.debug("TALK: listener stopped")

    def _settle_delay(self):
        s = get_settings()
        return float(getattr(s, "AUDIO_SETTLE_DELAY", 0.5))

    def _talk_loop_worker(self):
        # Continuous listen -> think -> speak -> wait-for-tts+settle -> listen.
        #
        # HARD GATE (self-hearing protection): the loop never calls listen()
        # while ``_speaking`` is set. ``_speaking`` is asserted by _begin_speech
        # BEFORE TTS starts and held until TTS fully returns AND the audio-settle
        # delay elapses. So the microphone is physically not listening while
        # ARVEN (or speaker tail) is audible -> ARVEN cannot hear itself.
        while (self._running and self.state == AppState.TALK
               and not self._talk_cancel.is_set()):
            # 1) Never open the mic while ARVEN is speaking or settling.
            if self._speaking.is_set():
                self._speaking.wait(timeout=0.1)
                continue
            if self._listening:
                # Shouldn't happen (single loop), but never double-capture.
                self._talk_cancel.wait(0.2)
                continue
            # 2) Open the mic and capture one utterance.
            self._listening = True
            self.ui.post(self._set_status, "LISTENING")
            try:
                text, error = self.voice.listen(timeout=8)
            except Exception as exc:
                log.warning("talk listen error: %s", exc)
                self._listening = False
                self.ui.post(self._set_status,
                             f"Voice error: {type(exc).__name__}", "err")
                self._talk_cancel.wait(1.0)
                continue
            self._listening = False
            if self._talk_cancel.is_set() or self.state != AppState.TALK:
                return
            if text:
                log.debug("TALK: heard %r -> brain", text)
                self.ui.post(self._set_status, "PROCESSING")
                self.ui.post(self.append, "user", text)
                self.ui.post(self._set_busy, True)
                self._queue.put((text, "stt"))
                # 3) Wait until ARVEN has fully spoken THIS reply (and phone rest
                #    settles) before we may consider another capture.
                self._speech_finished.wait(timeout=45)
            elif error:
                self.ui.post(self._set_status,
                             f"Couldn't hear you: {error}", "err")
            else:
                # Nothing understood in the window: keep listening.
                self.ui.post(self._set_status, "LISTENING")
        self._talk_thread = None

    def _begin_speech(self, response):
        # Speak a TALK reply while holding the HARD speaking gate.
        #
        #   _speaking.set()   -> microphone must not open (self-hearing guard)
        #   ui.speak()        -> BLOCKING Windows TTS; returns only after the
        #                        synthesized audio finishes playing
        #   settle_delay      -> let speaker tail / room echo decay
        #   _speaking.clear() -> microphone may open again
        #   _speech_finished.set() -> wake the talk loop
        self._speaking.set()
        self._speech_finished.clear()
        settle = self._settle_delay()

        def _run_speak():
            try:
                log.debug("TTS: started speaking %r", response[:40])
                try:
                    self.ui.speak(response)
                except Exception as exc:
                    log.warning("TTS speak raised: %s", exc)
                finally:
                    log.debug("TTS: finished speaking")
                    delay = settle
                    if delay > 0:
                        log.debug("TTS: audio-settle %.2fs", delay)
                        # Hold the hard gate (still SET here) while the speaker
                        # tail / room echo decays BEFORE the mic may reopen.
                        # NOTE: must be time.sleep, not _speaking.wait(delay) —
                        # Event.wait() returns IMMEDIATELY when the event is
                        # already set, which would make the settle delay a no-op
                        # and let ARVEN re-open the mic while its own tail echo
                        # is still audible (self-hearing).
                        time.sleep(delay)
            finally:
                self._speaking.clear()
                self._speech_finished.set()

        threading.Thread(target=_run_speak, daemon=True,
                         name="arven-talk-tts").start()

    # ------------------------------------------------------------------
    # Brain dispatch (background, non-blocking)
    # ------------------------------------------------------------------

    def _dispatch_to_brain(self, text, source="text"):
        self.ui.post(self.append, "user", text)
        self.ui.post(self._set_busy, True)
        self._queue.put((text, source))

    def _work(self):
        while self._running:
            try:
                text, source = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            try:
                result = self.brain.process(text, source=source)
                response = result.get("response", "") or ""
                if not response:
                    response = "I didn't catch that, Boss."
                self.ui.post(self._deliver_reply, response)
            except Exception as exc:
                log.exception("brain processing failed for %r", text)
                self.ui.post(
                    self._deliver_reply,
                    f"Sorry Boss, something went wrong: {type(exc).__name__}: {exc}")
            finally:
                self.ui.post(self._set_busy, False)

    def _deliver_reply(self, response):
        self.ui.post(self.append, "arven", response)
        if self.state == AppState.TALK:
            self._begin_speech(response)

    def send_typing(self):
        # A hook for future "user is typing" indicator; currently a no-op.
        pass

    # ------------------------------------------------------------------
    # UI-facing state helpers (called via ui.post on the main thread)
    # ------------------------------------------------------------------

    def _set_state(self, state):
        self.state = state
        self.ui.post(self._on_state_changed, state)

    def _on_state_changed(self, state):
        # Entering TALK starts the always-listening continuous voice loop;
        # leaving TALK (to Chat, shutdown, etc.) stops it cleanly.
        if state == AppState.TALK:
            self.begin_talk_loop()
        else:
            self.stop_talk_loop()
        # Bound by the window/controller wiring (set via on_state_change).
        if self._state_handler:
            self._state_handler(state)

    def _set_status(self, text, kind="info"):
        if self._status_handler:
            self._status_handler(text, kind)

    def _append_system(self, text):
        if self._system_handler:
            self._system_handler(text)

    def append(self, role, text):
        if role == "user":
            if self._user_handler:
                self._user_handler(text)
        else:
            if self._arven_handler:
                self._arven_handler(text)

    def _set_busy(self, busy):
        if self._busy_handler:
            self._busy_handler(busy)

    # ------------------------------------------------------------------
    # UI handler binding (wired by the app when the window exists)
    # ------------------------------------------------------------------

    def bind_ui(self, *, state_handler=None, user_handler=None,
                arven_handler=None, system_handler=None, busy_handler=None,
                status_handler=None, close_handler=None):
        self._state_handler = state_handler
        self._user_handler = user_handler
        self._arven_handler = arven_handler
        self._system_handler = system_handler
        self._busy_handler = busy_handler
        self._status_handler = status_handler
        self._close_handler = close_handler

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def build_shutdown_plan(self):
        plan = ShutdownPlan()
        plan.set("say_bye", lambda: self.ui.speak(self._bye_message))
        plan.set("finish_speech", lambda: None)
        plan.set("stop_voice", lambda: self._stop_voice())
        plan.set("unregister_hotkey", lambda: self._unregister_hotkey())
        plan.set("stop_workers", lambda: self._stop_workers())
        plan.set("save_state", lambda: self._save_state())
        plan.set("close_window", lambda: self.ui.post(self._close_window))
        plan.set("terminate", lambda: self.ui.exit_process(0))
        return plan

    def request_shutdown(self):
        """Start a graceful shutdown on a dedicated thread (never blocks UI)."""
        if getattr(self, "_shutdown_started", False):
            return
        self._shutdown_started = True
        threading.Thread(target=self._do_shutdown, daemon=True, name="arven-shutdown").start()

    def _do_shutdown(self):
        self._set_state(AppState.SHUTTING_DOWN)
        plan = self.build_shutdown_plan()
        completed, errors = plan.run()
        if errors:
            log.error("shutdown errors: %s", errors)
        self._running = False
        self.state = AppState.CLOSED

    def _stop_voice(self):
        # Release the hard speaking gate so any TTS thread can never leave
        # ARVEN "stuck speaking" (which would block future Talk listening).
        self._speaking.clear()
        self._speech_finished.set()
        self._talk_cancel.set()
        try:
            if self.voice is not None and hasattr(self.voice, "close"):
                self.voice.close()
        except Exception as exc:
            log.warning("voice stop failed: %s", exc)

    def _unregister_hotkey(self):
        try:
            if self._hotkey is not None:
                self._hotkey.stop()
                self._hotkey = None
        except Exception as exc:
            log.warning("hotkey stop failed: %s", exc)

    def _stop_workers(self):
        self._running = False
        # The worker polls the queue every 0.3s and exits once _running is
        # False, so a short join is enough (no sentinel unpacking needed).
        if self._worker.is_alive():
            self._worker.join(timeout=1)

    def _save_state(self):
        # Memory is persisted by the Brain/MemorySystem automatically; nothing
        # extra to flush here, but the hook exists for future needs.
        return

    def _close_window(self):
        if self._close_handler:
            self._close_handler()

    def release_single_instance(self):
        if self._instance_handle is not None:
            try:
                from desktop.single_instance import release_single_instance as _rel
                _rel(self._instance_handle)
            except Exception as exc:
                log.warning("single-instance release failed: %s", exc)
            self._instance_handle = None
