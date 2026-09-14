import time

from brain.brain import Brain
from voice.input import VoiceInput
from voice.output import voice_output


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

    # Microphone check
    try:
        if not stt.microphone_available():
            print("ERROR: No microphone available.")
            return
    except Exception as exc:
        print(f"ERROR: Microphone check failed: {exc}")
        return

    # Startup
    greeting = "Hello Boss. I'm listening."

    print(f"ARVEN: {greeting}")

    try:
        voice_output.speak(greeting, async_mode=False)
    except Exception as exc:
        print(f"TTS warning: {exc}")

    print()

    while True:

        print("🎙 Listening...", flush=True)

        try:
            result = stt.transcribe(duration=5)
        except KeyboardInterrupt:
            print("\nARVEN: Goodbye, Boss.")
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
            continue

        text = str(
            result.get("text", "")
        ).strip()

        if not text:
            continue

        print(f"You: {text}")

        # Exit commands
        if text.lower() in {
            "exit",
            "quit",
            "bye",
            "goodbye"
        }:

            response = "Goodbye, Boss."

            print(f"ARVEN: {response}")

            try:
                voice_output.speak(
                    response,
                    async_mode=False
                )
            except Exception:
                pass

            break

        # ==========================================
        # EXISTING ARVEN BRAIN
        # ==========================================

        try:

            result = brain.process(text)

            response = clean_response(
                result.get("response", "")
            )

        except Exception as exc:

            response = (
                f"Sorry Boss, "
                f"I encountered an error: {exc}"
            )

        # ==========================================
        # DISPLAY
        # ==========================================

        print(f"ARVEN: {response}")

        # ==========================================
        # SPEAK
        # ==========================================

        try:

            voice_output.speak(
                response,
                async_mode=False
            )

        except Exception as exc:

            print(
                f"TTS warning: {exc}"
            )

        print()


if __name__ == "__main__":
    main()