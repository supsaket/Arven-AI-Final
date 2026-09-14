import subprocess
import sys

text = "Hello Boss. This is ARVEN speaking. If you can hear this, voice output is working."

print("Testing Windows PowerShell TTS...")
print()

script = f'''
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Volume = 100
$speaker.Rate = 0
$speaker.Speak("{text}")
$speaker.Dispose()
'''

try:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print("TTS command completed successfully.")
    else:
        print("TTS command failed.")
        print(result.stderr)

except Exception as exc:
    print(f"ERROR: {exc}")

print()
print("Test finished.")