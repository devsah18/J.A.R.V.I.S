import speech_recognition as sr

r = sr.Recognizer()

print("Available microphones:")

for i, name in enumerate(sr.Microphone.list_microphone_names()):
    print(i, name)

try:
    with sr.Microphone() as source:
        print("\nStay quiet for 2 seconds...")
        r.adjust_for_ambient_noise(source, duration=2)

        print("Speak now for up to 8 seconds!")

        audio = r.listen(
            source,
            timeout=8,
            phrase_time_limit=8
        )

    print("Audio recorded successfully!")
    print("Sending audio to Google Speech Recognition...")

    text = r.recognize_google(audio)
    print("YOUR WORDS:", text)

except sr.WaitTimeoutError:
    print("ERROR: No speech detected.")

except sr.UnknownValueError:
    print("ERROR: Audio recorded, but speech was not understood.")

except sr.RequestError as e:
    print("GOOGLE SPEECH ERROR:", e)

except Exception as e:
    print("MICROPHONE ERROR:", repr(e))