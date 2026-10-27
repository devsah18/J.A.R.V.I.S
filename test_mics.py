try:
    import speech_recognition as sr
except ImportError:
    sr = None
import time

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone microphone diagnostic")

print("Testing different microphone devices...")
try:
    if sr is None:
        raise RuntimeError("SpeechRecognition is not installed; run: python -m pip install -r requirements.txt")
    # List microphones
    mics = sr.Microphone.list_microphone_names()
    print(f"Found {len(mics)} microphone devices:")
    for i, name in enumerate(mics):
        print(f"  {i}: {name}")
    
    # Test some likely microphone candidates
    test_indices = [0, 1, 4, 5, 23]  # Based on common patterns and what we see
    
    for device_index in test_indices:
        if device_index >= len(mics):
            continue
            
        print(f"\n{'='*50}")
        print(f"Testing device index {device_index}: {mics[device_index]}")
        print('='*50)
        
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 150
            recognizer.dynamic_energy_threshold = True
            
            with sr.Microphone(device_index=device_index) as source:
                print("Adjusting for ambient noise (be quiet for 1 second)...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                print(f"Energy threshold: {recognizer.energy_threshold}")
                
                print("Say 'hello' loudly and clearly (3 seconds)...")
                audio = recognizer.listen(source, timeout=3, phrase_time_limit=3)
                print("Audio captured!")
                
                text = recognizer.recognize_google(audio)
                print(f"SUCCESS! Recognized: '{text}'")
                print(f"Device {device_index} ({mics[device_index]}) WORKS!")
                break  # Found a working mic, stop testing
                
        except sr.WaitTimeoutError:
            print("TIMEOUT: No speech detected")
        except sr.UnknownValueError:
            print("UNKNOWN: Speech detected but couldn't understand")
        except Exception as e:
            print(f"ERROR with device {device_index}: {e}")
            
except Exception as e:
    print(f"Setup error: {e}")
    import traceback
    traceback.print_exc()
