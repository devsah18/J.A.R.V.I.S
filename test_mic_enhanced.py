try:
    import speech_recognition as sr
except ImportError:
    sr = None
import time

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone microphone diagnostic")

print("Enhanced microphone test with feedback...")
try:
    if sr is None:
        raise RuntimeError("SpeechRecognition is not installed; run: python -m pip install -r requirements.txt")
    # List microphones
    mics = sr.Microphone.list_microphone_names()
    print(f"Found {len(mics)} microphone devices")
    
    # Test with explicit device index from config
    device_index = 7  # From .env STT_DEVICE_INDEX
    print(f"Testing with device index {device_index}: {mics[device_index] if device_index < len(mics) else 'OUT OF RANGE'}")
    
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 150  # From config
    recognizer.dynamic_energy_threshold = True
    recognizer.dynamic_energy_adjustment_damping = 0.15
    recognizer.dynamic_energy_ratio = 1.5
    recognizer.pause_threshold = 0.8
    recognizer.non_speaking_duration = 0.5
    
    print("\n=== Microphone Signal Test ===")
    with sr.Microphone(device_index=device_index) as source:
        print("Adjusting for ambient noise (please be quiet for 2 seconds)...")
        recognizer.adjust_for_ambient_noise(source, duration=2)
        print(f"Energy threshold after calibration: {recognizer.energy_threshold}")
        print(f"Dynamic energy threshold: {recognizer.dynamic_energy_threshold}")
        
        print("\n=== Listening Test ===")
        print("Say something loudly and clearly (you have 5 seconds)...")
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
            print("Audio captured!")
            
            # Check audio properties
            import io
            wav_data = audio.get_wav_data()
            print(f"Audio size: {len(wav_data)} bytes")
            
            print("Attempting Google Speech Recognition...")
            text = recognizer.recognize_google(audio)
            print(f"SUCCESS: You said: '{text}'")
            
        except sr.WaitTimeoutError:
            print("TIMEOUT: No speech detected within 5 seconds")
        except sr.UnknownValueError:
            print("UNKNOWN: Speech detected but could not understand audio")
            print("Try speaking more clearly, closer to microphone, or in quieter environment")
        except sr.RequestError as e:
            print(f"REQUEST ERROR: Could not request results from Google Speech Recognition service; {e}")
        except Exception as e:
            print(f"OTHER ERROR: {e}")
            import traceback
            traceback.print_exc()
            
except Exception as e:
    print(f"Setup error: {e}")
    import traceback
    traceback.print_exc()
