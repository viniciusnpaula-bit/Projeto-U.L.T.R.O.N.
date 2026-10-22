import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from microphone_devices import resolve_input_device


class MicrophoneIdentityTests(unittest.TestCase):
    def test_removed_device_does_not_resolve_to_another_device_at_old_index(self):
        audio = types.SimpleNamespace(
            query_devices=lambda: [{"name": "USB Headset", "max_input_channels": 1, "hostapi": 0}],
            query_hostapis=lambda: [{"name": "WASAPI"}],
        )
        with patch.dict(sys.modules, {"sounddevice": audio}):
            self.assertIsNone(resolve_input_device('["WASAPI","Webcam Mic",0]'))


if __name__ == "__main__":
    unittest.main()
