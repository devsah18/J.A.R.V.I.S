import importlib
import sys
# Force reload of config module
if 'config' in sys.modules:
    importlib.reload(sys.modules['config'])
import config
print('STT_DEVICE_INDEX:', repr(config.STT_DEVICE_INDEX))
print('Type:', type(config.STT_DEVICE_INDEX))
