import speech_recognition as sr
import sys

if __name__ != "__main__":
    import unittest
    raise unittest.SkipTest("standalone voice diagnostic")

try:
    import speech_recognition as sr
except ImportError:
    sr = None
print('=== VARSHA VOICE SYSTEM DIAGNOSTIC ===')
