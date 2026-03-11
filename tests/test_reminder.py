import datetime
import subprocess
import unittest
from unittest.mock import Mock, patch

import tkinter as tk

from reminder import MAX_SNOOZE_COUNT, ReminderApp, _set_window_icon, calculate_delay_ms, play_notification_sound


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

    def test_midnight_target_from_late_evening(self):
        now = datetime.datetime(2026, 1, 1, 23, 0, 0)
        target = datetime.time(0, 0)

        expected_ms = int(datetime.timedelta(hours=1).total_seconds() * 1000)
        self.assertEqual(calculate_delay_ms(now, target), expected_ms)

    def test_target_exactly_one_hour_ahead(self):
        now = datetime.datetime(2026, 6, 15, 14, 0, 0)
        target = datetime.time(15, 0)

        self.assertEqual(calculate_delay_ms(now, target), 3_600_000)


class PlayNotificationSoundTests(unittest.TestCase):
    @patch("reminder.subprocess.Popen")
    @patch("reminder.platform.system", return_value="Linux")
    def test_calls_root_bell_on_linux(self, _mock_system, _mock_popen):
        root = Mock()

        play_notification_sound(root)

        root.bell.assert_called_once_with()

    @patch("reminder.subprocess.Popen")
    @patch("reminder.platform.system", return_value="Linux")
    def test_ignores_tcl_error(self, _mock_system, _mock_popen):
        root = Mock()
        root.bell.side_effect = tk.TclError("bell is not available")

        play_notification_sound(root)

        root.bell.assert_called_once_with()

    @patch("reminder.subprocess.Popen")
    @patch("reminder.platform.system", return_value="Linux")
    def test_sends_notify_send_on_linux(self, _mock_system, mock_popen):
        root = Mock()

        play_notification_sound(root)

        mock_popen.assert_called_once_with(
            ["notify-send", "--urgency=normal", "リマインダー"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @patch("reminder.subprocess.Popen", side_effect=FileNotFoundError)
    @patch("reminder.platform.system", return_value="Linux")
    def test_notify_send_not_found_still_rings_bell(self, _mock_system, _mock_popen):
        root = Mock()

        play_notification_sound(root)

        root.bell.assert_called_once_with()

    @patch("reminder.threading.Thread")
    @patch("reminder.platform.system", return_value="Darwin")
    def test_plays_afplay_on_darwin(self, _mock_system, mock_thread_cls):
        root = Mock()

        play_notification_sound(root)

        mock_thread_cls.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()
        root.bell.assert_not_called()

    @patch("reminder.platform.system", return_value="Windows")
    def test_falls_back_to_bell_when_winsound_unavailable(self, _mock_system):
        root = Mock()

        play_notification_sound(root)

        root.bell.assert_called_once_with()


class SetWindowIconTests(unittest.TestCase):
    def test_does_not_raise_when_cairosvg_unavailable(self):
        """cairosvg がない環境でもエラーにならないことを確認する。"""
        root = Mock()
        _set_window_icon(root)


class CoerceIntTests(unittest.TestCase):
    def test_value_within_range(self):
        self.assertEqual(ReminderApp._coerce_int("10", 0, 23), 10)

    def test_value_below_min(self):
        self.assertEqual(ReminderApp._coerce_int("-5", 0, 23), 0)

    def test_value_above_max(self):
        self.assertEqual(ReminderApp._coerce_int("99", 0, 23), 23)

    def test_non_numeric_returns_min(self):
        self.assertEqual(ReminderApp._coerce_int("abc", 0, 23), 0)

    def test_empty_string_returns_min(self):
        self.assertEqual(ReminderApp._coerce_int("", 1, 180), 1)

    def test_boundary_min(self):
        self.assertEqual(ReminderApp._coerce_int("0", 0, 59), 0)

    def test_boundary_max(self):
        self.assertEqual(ReminderApp._coerce_int("59", 0, 59), 59)


class _DummyVar:
    """tk.StringVar のテスト用代替。Tk インスタンスなしで動作する。"""

    def __init__(self, value: str = ""):
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def _create_app(
    snooze_value: str = "5",
    hour_value: str = "10",
    minute_value: str = "30",
):
    root = Mock()
    root.after.return_value = "job-1"

    with patch.object(ReminderApp, "_build_ui"), \
         patch("reminder.tk.StringVar", side_effect=lambda value="": _DummyVar(value)):
        app = ReminderApp(root)

    app.snooze_var.set(snooze_value)
    app.hour_var.set(hour_value)
    app.minute_var.set(minute_value)

    app.schedule_button = Mock()
    app.cancel_button = Mock()
    app.status_var = Mock()
    app.message_text = Mock()
    return app, root


class NormalizeTimeInputsTests(unittest.TestCase):
    def test_normalizes_hour_above_23(self):
        app, _ = _create_app(hour_value="30", minute_value="05")

        app._normalize_time_inputs()

        self.assertEqual(app.hour_var.get(), "23")
        self.assertEqual(app.minute_var.get(), "05")

    def test_normalizes_negative_minute(self):
        app, _ = _create_app(hour_value="10", minute_value="-1")

        app._normalize_time_inputs()

        self.assertEqual(app.minute_var.get(), "00")

    def test_pads_single_digit_values(self):
        app, _ = _create_app(hour_value="5", minute_value="3")

        app._normalize_time_inputs()

        self.assertEqual(app.hour_var.get(), "05")
        self.assertEqual(app.minute_var.get(), "03")

    def test_non_numeric_resets_to_zero(self):
        app, _ = _create_app(hour_value="abc", minute_value="xyz")

        app._normalize_time_inputs()

        self.assertEqual(app.hour_var.get(), "00")
        self.assertEqual(app.minute_var.get(), "00")


class ScheduleTests(unittest.TestCase):
    @patch("reminder.messagebox.showwarning")
    def test_empty_message_shows_warning(self, mock_warning):
        app, root = _create_app()
        app.message_text.get.return_value = "   \n"

        app.schedule()

        mock_warning.assert_called_once_with("入力エラー", "表示したいメッセージを入力してください。")
        root.after.assert_not_called()

    @patch("reminder.calculate_delay_ms", return_value=60_000)
    def test_schedule_sets_job_and_disables_button(self, _mock_delay):
        app, root = _create_app(snooze_value="5", hour_value="10", minute_value="30")
        app.message_text.get.return_value = "テストメッセージ"

        app.schedule()

        root.after.assert_called_once()
        app.schedule_button.configure.assert_called_with(state=tk.DISABLED)
        app.cancel_button.configure.assert_called_with(state=tk.NORMAL)
        self.assertIsNotNone(app.scheduled_job_id)

    @patch("reminder.calculate_delay_ms", return_value=60_000)
    def test_schedule_resets_ui_when_root_after_raises(self, _mock_delay):
        app, root = _create_app()
        app.message_text.get.return_value = "テストメッセージ"
        root.after.side_effect = RuntimeError("after failed")

        with self.assertRaises(RuntimeError):
            app.schedule()

        self.assertIsNone(app.scheduled_job_id)
        app.schedule_button.configure.assert_called_with(state=tk.NORMAL)
        app.cancel_button.configure.assert_called_with(state=tk.DISABLED)


class CancelScheduleTests(unittest.TestCase):
    def test_cancel_when_no_job_does_nothing(self):
        app, root = _create_app()
        app.scheduled_job_id = None

        app.cancel_schedule()

        root.after_cancel.assert_not_called()
        app.schedule_button.configure.assert_not_called()

    def test_cancel_active_job(self):
        app, root = _create_app()
        app.scheduled_job_id = "job-1"

        app.cancel_schedule()

        root.after_cancel.assert_called_once_with("job-1")
        self.assertIsNone(app.scheduled_job_id)
        app.schedule_button.configure.assert_called_with(state=tk.NORMAL)
        app.cancel_button.configure.assert_called_with(state=tk.DISABLED)
        app.status_var.set.assert_called_with("リマインダー設定を解除しました。")


class ReminderAppSnoozeTests(unittest.TestCase):
    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=True)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_schedules_snooze_with_explicit_minutes(
        self,
        mock_showinfo,
        mock_askyesno,
        mock_sound,
    ):
        app, root = _create_app(snooze_value="10")

        app.show_reminder("休憩しましょう", snooze_minutes=10)

        mock_sound.assert_called_once_with(root)
        mock_showinfo.assert_called_once_with("リマインダー", "休憩しましょう")
        mock_askyesno.assert_called_once_with("スヌーズ", "10分後に再通知しますか？")
        root.after.assert_called_once()
        app.schedule_button.configure.assert_called_with(state=tk.DISABLED)
        app.cancel_button.configure.assert_called_with(state=tk.NORMAL)
        app.status_var.set.assert_called_with("スヌーズ中です。10分後に再通知します。")

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=True)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_falls_back_to_snooze_var_when_not_passed(
        self,
        mock_showinfo,
        mock_askyesno,
        mock_sound,
    ):
        app, root = _create_app(snooze_value="7")

        app.show_reminder("テスト")

        mock_askyesno.assert_called_once_with("スヌーズ", "7分後に再通知しますか？")

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=False)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_updates_status_when_snooze_not_selected(
        self,
        _mock_showinfo,
        _mock_askyesno,
        _mock_sound,
    ):
        app, root = _create_app(snooze_value="15")

        app.show_reminder("休憩しましょう", snooze_minutes=15)

        root.after.assert_not_called()
        app.status_var.set.assert_called_with("通知を表示しました。次のリマインダーを設定できます。")

    def test_get_snooze_minutes_normalizes_out_of_range_value(self):
        app, _root = _create_app(snooze_value="999")

        minutes = app._get_snooze_minutes()

        self.assertEqual(minutes, 180)
        self.assertEqual(app.snooze_var.get(), "180")

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_skips_snooze_dialog_at_max_snooze_count(self, _mock_showinfo, _mock_sound):
        app, root = _create_app(snooze_value="5")

        with patch("reminder.messagebox.askyesno") as mock_askyesno:
            app.show_reminder("テスト", snooze_minutes=5, snooze_count=MAX_SNOOZE_COUNT)

        mock_askyesno.assert_not_called()
        root.after.assert_not_called()
        app.status_var.set.assert_called_with("通知を表示しました。次のリマインダーを設定できます。")

    @patch("reminder.play_notification_sound")
    @patch("reminder.messagebox.askyesno", return_value=True)
    @patch("reminder.messagebox.showinfo")
    def test_show_reminder_allows_snooze_below_max_snooze_count(
        self, _mock_showinfo, _mock_askyesno, _mock_sound
    ):
        app, root = _create_app(snooze_value="5")

        app.show_reminder("テスト", snooze_minutes=5, snooze_count=MAX_SNOOZE_COUNT - 1)

        _mock_askyesno.assert_called_once_with("スヌーズ", "5分後に再通知しますか？")
        root.after.assert_called_once()


if __name__ == "__main__":
    unittest.main()
