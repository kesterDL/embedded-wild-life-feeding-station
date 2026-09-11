"""Watchdog Bridge for Raspberry Pi Zero W.

Controls GPIO 25 (Pin 22) to send active-HIGH shutdown acknowledgment
pulses to the Arduino Nano watchdog node before system halt.
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger("WatchdogBridge")


class WatchdogBridge:
    def __init__(self, gpio_pin: int = 25):
        self.gpio_pin = gpio_pin

    def _get_gpio(self) -> Optional[Any]:
        """Attempts to dynamically import RPi.GPIO or gpiod."""
        try:
            import RPi.GPIO as GPIO
            return GPIO
        except (ImportError, RuntimeError):
            return None

    def signal_shutdown_ack(self, pulse_duration_s: float = 0.5) -> bool:
        """Asserts GPIO active-HIGH to signal the Arduino Nano that recording

        is complete and OS shutdown is in progress.
        """
        gpio = self._get_gpio()
        if gpio:
            try:
                gpio.setwarnings(False)
                gpio.setmode(gpio.BCM)
                gpio.setup(self.gpio_pin, gpio.OUT, initial=gpio.LOW)
                logger.info(f"Asserting GPIO {self.gpio_pin} HIGH (Shutdown ACK)...")
                gpio.output(self.gpio_pin, gpio.HIGH)
                time.sleep(pulse_duration_s)
                return True
            except Exception as e:
                logger.error(f"Failed to toggle GPIO {self.gpio_pin}: {e}")
                return False
        else:
            logger.warning(
                f"[SIMULATION] RPi.GPIO not available. Simulated GPIO {self.gpio_pin} ACK pulse ({pulse_duration_s}s)."
            )
            time.sleep(pulse_duration_s)
            return True
