"""Check STT backend and faster-whisper configuration."""
from voice.input import voice_input, create_stt_backend

backend = create_stt_backend(provider=None)
print(f"create_stt_backend() -> {backend}")
print(f"Backend type: {type(backend).__name__ if backend else 'None'}")

# Try loading the model (faster-whisper base)
if backend is not None:
    try:
        ok = voice_input.load_model()
        print(f"load_model() -> {ok}")
    except Exception as e:
        print(f"load_model error: {e}")
