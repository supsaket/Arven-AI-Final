import re
import time

from brain.brain import Brain
from voice.input import VoiceInput
from voice.output import voice_output


EXIT_PHRASES = {
    "bye",
    "goodbye",
    "exit",
    "quit",
    "stop",
    "shutdown",
    "shut down",
    "close arven",
    "close yourself",
    "terminate",
    "terminate arven",
    "end",
    "end conversation",
    "stop listening",
    "go to sleep",
}


def normalize_text(text):
    text = str(text or "").strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_voice_command(text):
    normalized = normalize_text(text)

    normalized = re.sub(
        r"\b(node\s+pad|note\s+pad|notepad)\b",
        "notepad",
        normalized,
    )

    return normalized


def is_exit_command(text):
    normalized = normalize_text(text)
    return normalized in EXIT_PHRASES


def clean_response(text):
    if not text:
        return "I'm here, Boss."
    return str(text).strip()


def speak(text):
    try:
        voice_output.speak(text, async_mode=False)
    except Exception as exc:
        print(f"TTS warning: {exc}")


def main():
    print()
    print("========================================")
    print("              ARVEN")
    print("       Voice Conversation Mode")
    print("========================================")
    print()

    brain = Brain()
    stt = VoiceInput()

    try:
        if not stt.microphone_available():
            print("ERROR: No microphone available.")
            return
    except Exception as exc:
        print(f"ERROR: Microphone check failed: {exc}")
        return

    try:
        if not voice_output.available():
            print("TTS warning: Voice output may not be available.")
    except Exception:
        pass

    greeting = "Hello Boss. I'm listening."

    print(f"ARVEN: {greeting}")
    speak(greeting)
    print()

    while True:
        print("🎙 Listening...", flush=True)

        try:
            result = stt.transcribe(duration=5)

        except KeyboardInterrupt:
            print("\nARVEN: Goodbye, Boss.")
            speak("Goodbye, Boss.")
            break

        except Exception as exc:
            print(f"Voice input error: {exc}")
            time.sleep(1)
            continue

        if not result:
            continue

        if not result.get("success", False):
            error = result.get(
                "error",
                "I couldn't understand that."
            )

            print(f"ARVEN: {error}")
            speak(error)
            continue

        raw_text = str(result.get("text", "")).strip()

        if not raw_text:
            continue

        print(f"You: {raw_text}")

        # Exit voice mode
        if is_exit_command(raw_text):
            response = "Goodbye, Boss."

            print(f"ARVEN: {response}")
            speak(response)

            print()
            print("ARVEN voice mode stopped.")
            break

        # Normalize common Whisper mistakes
        command = normalize_voice_command(raw_text)

        if not command:
            continue

        # Process through ARVEN Brain
        try:
            result = brain.process(command)

            response = clean_response(
                result.get("response", "")
            )

        except Exception as exc:
            response = (
                f"Sorry Boss, I encountered an error: {exc}"
            )

        print(f"ARVEN: {response}")

        # Speak response
        speak(response)

        print()


if __name__ == "__main__":
    main()