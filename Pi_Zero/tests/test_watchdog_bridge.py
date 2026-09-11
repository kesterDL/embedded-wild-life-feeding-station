import time
import unittest
from unittest.mock import patch, MagicMock
from Pi_Zero.src.watchdog_bridge import WatchdogBridge


class TestWatchdogBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = WatchdogBridge(gpio_pin=25)

    @patch("time.sleep")
    def test_signal_shutdown_ack_success(self, mock_sleep):
        mock_gpio = MagicMock()
        with patch.object(self.bridge, "_get_gpio", return_value=mock_gpio):
            result = self.bridge.signal_shutdown_ack(pulse_duration_s=0.5)
            self.assertTrue(result)
            mock_gpio.setup.assert_called_with(25, mock_gpio.OUT, initial=mock_gpio.LOW)
            mock_gpio.output.assert_called_with(25, mock_gpio.HIGH)
            mock_sleep.assert_called_with(0.5)

    def test_signal_shutdown_ack_no_hardware_fallback(self):
        with patch.object(self.bridge, "_get_gpio", return_value=None):
            result = self.bridge.signal_shutdown_ack(pulse_duration_s=0.1)
            # Should fall back cleanly without raising unhandled exceptions
            self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
