# VARSHA Wake Word Detection Test
try:
    import speech_recognition as sr
except ImportError:
    sr = None
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from voice import speech_to_text as stt_module
from voice.speech_to_text import SpeechToText
import config

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone wake-word diagnostic")

print('=== VARSHA Wake Word Detection Test ===')
print('Configuration:')
print(f'  Assistant name: {config.ASSISTANT_NAME}')
print(f'  Wake word: {config.WAKE_WORD}')
print(f'      STT device index: {config.STT_DEVICE_INDEX}')
print(f'  STT energy threshold: {config.STT_ENERGY_THRESHOLD}')
print()

print('Creating SpeechToText instance...')
engine = SpeechToText(
    language=config.STT_LANGUAGE,
    energy_threshold=config.STT_ENERGY_THRESHOLD,
    pause_threshold=config.STT_PAUSE_THRESHOLD,
    listen_timeout=config.STT_LISTEN_TIMEOUT,
    phrase_time_limit=config.STT_PHRASE_TIME_LIMIT,
    enabled=config.STT_ENABLED,
    device_index=config.STT_DEVICE_INDEX
)

print(f'STT available: {engine.available}')
print(f'Device index: {engine.device_index}')
print()

if engine.available:
    print('  SPEECH TEST')
    print('Say "HELLO" loudly and clearly (you have 4 seconds)...')
    print()

    result = engine.listen(timeout=4, phrase_limit=4)

    print(f'Result status: {result.status}')
    if hasattr(result, 'text') and result.text:
        print(f'Recognized text: "{result.text}"')

    if result.status == stt_module.OK:
        print()
        print('  SPEECH RECOGNITION WORKING!')
        print(f'   You said: "{result.text}"')
        print()
        print('  NOW TESTING WAKE WORD DETECTION')
        print('   Say "JARVIS" loudly and clearly...')
        print()

        # Import wake word detector
        from voice.wake_word import WakeWordDetector
        wake_word = WakeWordDetector(engine, config.WAKE_WORD)

        detected, remainder = wake_word.detect()
        if detected:
            print(f'  SUCCESS! Wake word detected!')
            print(f'   Command heard: "{remainder}"')
        else:
            print('  Wake word not detected')
            print('   Try:')
            print('   - Saying "JARVIS" LOUDER (like calling someone)')
            print('   - Saying it CLEARLY (JA-RVIS, distinct syllables)')
            print('   - Getting closer to the microphone')
    elif result.status == stt_module.UNCLEAR:
        print()
        print('    AUDIO DETECTED BUT NOT UNDERSTOOD')
        print('   This means your microphone works, but:')
        print('   - You need to speak MORE CLEARLY')
        print('   - Or REDUCE background noise')
        print('   - Or SPEAK LOUDER and more distinctly')
        print()
        print('  SUGGESTED FIXES:')
        print('   1. Speak like you\'re announcing news on TV')
        print('   2. Enunciate each word: "HELLO... JARVIS..."')
        print('   3. Get within 6 inches of microphone')
        print('   4. Try in a quieter room')
    elif result.status == stt_module.SILENCE:
        print()
        print('    NO SPEECH DETECTED')
        print('   Try:')
        print('   - Speaking MUCH LOUDER than normal')
        print('   - Checking if microphone is muted')
        print('   - Ensuring correct microphone is selected')
    else:
        print()
        print(f'  ERROR: {result.status}')
else:
    print('  STT not available - check microphone setup')
