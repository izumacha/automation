import datetime
import unittest
from unittest.mock import Mock

import tkinter as tk

from reminder import calculate_delay_ms, play_notification_sound


class CalculateDelayMsTests(unittest.TestCase):
    def test_same_minute_returns_zero(self):
        now = datetime.datetime(2026, 1, 1, 10, 30, 45)
        target = datetime.time(10, 30)

        self.assertEqual(calculate_delay_ms(now, target), 0)

    def test_future_time_same_day(self):
        now = datetime.datetime(2026, 1, 1, 10, 30, 45)
        target = datetime.time(10, 31)

        self.assertEqual(calculate_delay_ms(now, target), 15_000)

    def test_past_time_rolls_to_next_day(self):
        now = datetime.datetime(2026, 1, 1, 23, 59, 30)
        target = datetime.time(23, 58)

        self.assertEqual(calculate_delay_ms(now, target), 86_310_000)


class PlayNotificationSoundTests(unittest.TestCase):
    def test_calls_root_bell(self):
        root = Mock()

        play_notification_sound(root)

        root.bell.assert_called_once_with()

    def test_ignores_tcl_error(self):
        root = Mock()
        root.bell.side_effect = tk.TclError("bell is not available")

        play_notification_sound(root)

        root.bell.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
