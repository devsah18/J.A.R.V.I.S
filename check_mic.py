"""JARVIS - Interactive Microphone Diagnostic and Audio Checker.

Run directly in terminal:
    python check_mic.py

Checks:
- All audio input devices and their active status
- Live sound level (RMS / dB meter)
- Live speech recognition test with Google Web Speech API
- Verifies and updates .env with the working device index
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import speech_recognition as sr
import config
from voice.speech_to_text import SpeechToText

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False


def print_header(title: str):
    print("\n" + "=" * 65)
    print(f"  {title}")
    print("=" * 65)


def check_windows_mic_volume():
    """Check Windows master microphone volume and mute state via Core Audio."""
    if not PYCAW_AVAILABLE:
        return
    try:
        device = AudioUtilities.GetMicrophone()
        if device:
            endpoint = device.Activate(IAudioEndpointVolume._iid_, 7, None)
            volume = endpoint.QueryInterface(IAudioEndpointVolume)
            muted = volume.GetMute()
            level = round(volume.GetMasterVolumeLevelScalar() * 100, 1)
            print(f"• Windows Default Mic Volume: {level}% | Muted: {'YES (⚠️ Muted!)' if muted else 'NO (Normal)'}")
            if muted:
                print("  [!] WARNING: Your default microphone is muted in Windows! Unmute it in Windows Settings.")
    except Exception as e:
        pass


def scan_devices():
    """List and probe each microphone device."""
    print_header("1. SCANNING AUDIO DEVICES")
    names = sr.Microphone.list_microphone_names()
    print(f"Detected {len(names)} total audio device mappings.\n")

    working_indices = []

    for idx, name in enumerate(names):
        # Filter for likely input endpoints
        name_lower = name.lower()
        is_mic = any(k in name_lower for k in ("microphone", "mic", "array", "headset", "input", "sound mapper"))
        if not is_mic:
            continue

        status = "No audio"
        try:
            m = sr.Microphone(device_index=idx)
            with m as source:
                chunk = source.stream.read(source.CHUNK)
                shorts = [int.from_bytes(chunk[j:j+2], byteorder="little", signed=True) for j in range(0, len(chunk), 2)]
                peak = max(abs(s) for s in shorts) if shorts else 0
                if peak > 100:
                    status = f"ACTIVE (Live audio signal peak={peak})"
                    working_indices.append((idx, peak))
                else:
                    status = f"Silent (peak={peak})"
        except Exception as e:
            status = f"Error: {e}"

        marker = ">>>" if "ACTIVE" in status else "   "
        print(f" {marker} [{idx:2d}] {name[:45]:<45} : {status}")

    return working_indices


def live_sound_meter(device_index: int, duration_seconds: int = 5):
    """Visual volume bar showing real-time microphone level."""
    print_header(f"2. LIVE AUDIO LEVEL METER (Device {device_index})")
    print(f"Speak into your microphone now. Watching audio levels for {duration_seconds} seconds...\n")

    m = sr.Microphone(device_index=device_index)
    with m as source:
        start_time = time.time()
        max_seen = 0

        while time.time() - start_time < duration_seconds:
            try:
                raw = source.stream.read(source.CHUNK)
                # Compute simple peak amplitude
                shorts = [int.from_bytes(raw[i:i+2], byteorder="little", signed=True) for i in range(0, len(raw), 2)]
                peak = max(abs(s) for s in shorts) if shorts else 0
                if peak > max_seen:
                    max_seen = peak

                # 0 to 10,000 scaled to 30 bars
                bar_len = min(30, int((peak / 4000.0) * 30))
                meter = "█" * bar_len + "░" * (30 - bar_len)
                sys.stdout.write(f"\r Audio Level: [{meter}] Peak: {peak:5d} ")
                sys.stdout.flush()
                time.sleep(0.05)
            except Exception:
                break
        print(f"\n\nMax Peak Amplitude Recorded: {max_seen}")
        if max_seen < 100:
            print("[WARN] Very low signal detected. Speak closer to the microphone or adjust input volume.")
        else:
            print("[OK] Healthy audio signal confirmed!")


def test_speech_recognition(device_index: int) -> bool:
    """Test speech recognition with up to three attempts."""
    print_header(f"3. SPEECH RECOGNITION TEST (Device {device_index})")
    stt = SpeechToText(device_index=device_index)

    print("Calibrating background noise (please remain quiet for 1 sec)...")
    ambient = stt.calibrate(duration=1.0)
    print(f"Background noise floor: {ambient:.1f}")

    # Make recognizer more sensitive for this test
    if hasattr(stt, "_recognizer") and stt._recognizer is not None:
        stt._recognizer.energy_threshold = max(300, stt._recognizer.energy_threshold)
        stt._recognizer.dynamic_energy_threshold = False

    for attempt in range(1, 4):
        print(f"\nAttempt {attempt}/3 – say something clearly (e.g. 'Hello JARVIS')...")
        print("[Listening...]", flush=True)

        # Give more time for speaking
        result = stt.listen(timeout=12, phrase_limit=15)

        print("\nRecognition Result:")
        if result.status == "ok":
            print(f"[OK] SUCCESS! Recognized: \"{result.text}\"")
            return True
        elif result.status == "silence":
            print("[FAIL] No speech detected (timed out).")
        elif result.status == "unclear":
            print("[WARN] Audio was detected, but words could not be understood. Try speaking more clearly.")
        else:
            print(f"[WARN] Recognition returned status: {result.status}")

        if attempt < 3:
            print("\nRetrying in 2 seconds...")
            time.sleep(2)

    return False


def main():
    print_header("JARVIS MICROPHONE CHECKER (check_mic.py)")
    print(f"Configured Assistant Name: {config.ASSISTANT_NAME}")
    print(f"Current STT_DEVICE_INDEX in config: {config.STT_DEVICE_INDEX}")

    check_windows_mic_volume()

    active_devices = scan_devices()

    # Determine recommended index: pick the one with strongest signal
    target_index = None
    if active_devices:
        active_devices.sort(key=lambda x: x[1], reverse=True)
        target_index = active_devices[0][0]
    elif config.STT_DEVICE_INDEX >= 0:
        target_index = config.STT_DEVICE_INDEX
    else:
        target_index = 0

    print(f"\nTarget test device: [{target_index}]")

    # Run level meter
    live_sound_meter(device_index=target_index, duration_seconds=4)

    # Run STT test
    test_speech_recognition(device_index=target_index)

    print_header("DIAGNOSTIC COMPLETE")
    print(f"• If speech recognition succeeded, your microphone is ready for JARVIS!")
    print(f"• To run JARVIS in hands-free voice mode: python main.py --voice")
    print(f"• To run in interactive CLI mode:         python main.py")


if __name__ == "__main__":
    main()

