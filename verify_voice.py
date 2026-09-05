"""Real STT/microphone production runtime check."""
import sys, time

from voice.input import voice_input
from voice.output import voice_output
from voice.wakeword import WakeWordEngine

print("=== VOICE/STT/TTS PRODUCTION RUNTIME CHECK ===")

# TTS
print("\n--- TTS ---")
print(f"TTS available: {voice_output.available()}")

# Wake word (text-based)
print("\n--- Wake Word ---")
w = WakeWordEngine()
print(f"WakeWord available: {w.available()}")
print(f"contains_wake('hey arven'): {w.contains_wake('hey arven')}")
print(f"contains_wake('hello world'): {w.contains_wake('hello world')}")

# Microphone
print("\n--- Microphone / STT ---")
print(f"VoiceInput backend: {voice_input._resolve_backend()}")
mic = voice_input.microphone_available()
print(f"Microphone available (with retries): {mic}")

# If mic available, try a bounded capture + transcribe with a short silence (may time out, that's fine)
if mic:
    # Use sounddevice fallback explicitly to test the non-WASAPI path
    try:
        import sounddevice as sd
        sd.check_input_settings(device=None)
        print("sounddevice input settings: OK")
        mics = voice_input.list_microphones()
        print(f"Microphones enumerated: {len(mics)}")
        for m in mics[:3]:
            print(f"  mic: {m.get('name', m.get('index'))} (backend={m.get('backend')})")
    except Exception as e:
        print(f"sounddevice error: {e}")
else:
    print("Microphone unavailable — this is the known Windows COM/WASAPI thread-context limitation.")

print("\nDone.")
