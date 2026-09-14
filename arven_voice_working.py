import re
import subprocess
import time

from brain.brain import Brain
from voice.input import VoiceInput


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
    text = normalize_text(text)

    # Common Whisper variations for Notepad.
    text = re.sub(
        r"\b(node\s+pad|note\s+pad|notepad)\b",
        "notepad",
        text,
    )

    return text


def is_exit_command(text):
    return normalize_text(text) in EXIT_PHRASES


def speak(text):
    """Reliable Windows TTS using System.Speech."""
    text = str(text or "").strip()

    if not text:
        return

    # Escape characters that could break PowerShell string.
    safe_text = (
        text
        .replace("`", "``")
        .replace('"', '`"')
        .replace("$", "`$")
    )

    script = f'''
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Volume = 100
$speaker.Rate = 0
$speaker.Speak("{safe_text}")
$speaker.Dispose()
'''

    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    except Exception as exc:
        print(f"TTS error: {exc}")


def clean_response(text):
    if not text:
        return "I'm here, Boss."

    return str(text).strip()


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

        # Exit before sending anything to the Brain.
        if is_exit_command(raw_text):
            response = "Goodbye, Boss."

            print(f"ARVEN: {response}")
            speak(response)

            print()
            print("ARVEN voice mode stopped.")
            break

        command = normalize_voice_command(raw_text)

        if not command:
            continue

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

        speak(response)

        print()


if __name__ == "__main__":
    main()