import datetime
import unittest
from unittest.mock import Mock, patch

import tkinter as tk

from reminder import ReminderApp, _set_window_icon, calculate_delay_ms, play_notification_sound


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


class SetWindowIconTests(unittest.TestCase):
    def test_does_not_raise_when_cairosvg_unavailable(self):
        """cairosvg がない環境でもエラーにならないことを確認する。"""
        root = Mock()
        _set_window_icon(root)  # 例外が発生しないこと


class _DummyVar:
    def __init__(self, value: str):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class ReminderAppSnoozeTests(unittest.TestCase):
    def _create_app(self, snooze_value: str = "5"):
        root = Mock()
        root.after.return_value = "job-1"

        app = ReminderApp.__new__(ReminderApp)
        app.root = root
        app.scheduled_job_id = None
        app.schedule_button = Mock()
        app.cancel_button = Mock()
        app.status_var = Mock()
        app.snooze_var = _DummyVar(snooze_value)
        return app, root

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=True)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_schedules_snooze_with_configured_minutes(
        self,
        mock_showinfo,
        mock_askyesno,
        mock_sound,
    ):
        app, root = self._create_app(snooze_value="10")

        app.show_reminder("休憩しましょう")

        mock_sound.assert_called_once_with(root)
        mock_showinfo.assert_called_once_with("リマインダー", "休憩しましょう")
        mock_askyesno.assert_called_once_with("スヌーズ", "10分後に再通知しますか？")
        root.after.assert_called_once()
        app.schedule_button.configure.assert_called_with(state=tk.DISABLED)
        app.cancel_button.configure.assert_called_with(state=tk.NORMAL)
        app.status_var.set.assert_called_with("スヌーズ中です。10分後に再通知します。")

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=False)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_updates_status_when_snooze_not_selected(
        self,
        _mock_showinfo,
        _mock_askyesno,
        _mock_sound,
    ):
        app, root = self._create_app(snooze_value="15")

        app.show_reminder("休憩しましょう")

        root.after.assert_not_called()
        app.status_var.set.assert_called_with("通知を表示しました。次のリマインダーを設定できます。")

    def test_get_snooze_minutes_normalizes_out_of_range_value(self):
        app, _root = self._create_app(snooze_value="999")

        minutes = app._get_snooze_minutes()

        self.assertEqual(minutes, 180)
        self.assertEqual(app.snooze_var.get(), "180")


if __name__ == "__main__":
    unittest.main()
