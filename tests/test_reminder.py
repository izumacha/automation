"""tests/test_reminder.py — reminder パッケージのユニットテスト

テスト方針:
- tkinter への依存を排除するため、tests/conftest.py で tkinter をモック化する
- GUI ウィジェットの生成は _build_ui をパッチして省略し、
  ロジック層（スケジューリング・バリデーション・スヌーズ）を直接テストする
- _DummyVar で tk.StringVar を代替し、Tk インスタンスなしで状態変化を検証する

テストクラス一覧:
    CalculateDelayMsTests   : calculate_delay_ms() の単体テスト
    PlayNotificationSoundTests : play_notification_sound() のプラットフォーム別テスト
    PlatformHelperTests     : プラットフォーム別ヘルパーの単体テスト
    SetWindowIconTests      : _set_window_icon() の単体テスト
    CoerceIntTests          : ReminderApp._coerce_int() の単体テスト
    NormalizeTimeInputsTests: _normalize_time_inputs() の単体テスト
    ScheduleTests           : schedule() の動作テスト
    CancelScheduleTests     : cancel_schedule() の動作テスト
    ReminderAppSnoozeTests  : show_reminder() / _schedule_snooze() のテスト
    BuildSectionTests       : _build_*_section() の UI 構築テスト
    FocusNavigationTests    : _focus_next() / _focus_prev() のテスト
    MainTests               : main() のテスト
    SettingsTests           : Settings / load_settings / save_settings のテスト
"""
import datetime
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import types

import tkinter as tk

from reminder import (
    MAX_SNOOZE_COUNT,
    STATUS_IDLE,
    STATUS_NOTIFIED,
    ReminderApp,
    _play_macos_sound,
    _ring_bell,
    _send_linux_notification,
    _set_window_icon,
    calculate_delay_ms,
    play_notification_sound,
)
from reminder.config import Settings, load_settings, save_settings


class CalculateDelayMsTests(unittest.TestCase):
    """calculate_delay_ms() の計算結果と翌日ロールオーバーを検証する。"""

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
    """play_notification_sound() のプラットフォーム別フォールバックを検証する。"""

    @patch("reminder.notifications.subprocess.Popen")
    @patch("reminder.notifications.platform.system", return_value="Linux")
    def test_calls_root_bell_on_linux(self, _mock_system, _mock_popen):
        root = Mock()
        play_notification_sound(root)
        root.bell.assert_called_once_with()

    @patch("reminder.notifications.subprocess.Popen")
    @patch("reminder.notifications.platform.system", return_value="Linux")
    def test_ignores_tcl_error(self, _mock_system, _mock_popen):
        root = Mock()
        root.bell.side_effect = tk.TclError("bell is not available")
        play_notification_sound(root)
        root.bell.assert_called_once_with()

    @patch("reminder.notifications.subprocess.Popen")
    @patch("reminder.notifications.platform.system", return_value="Linux")
    def test_sends_notify_send_on_linux(self, _mock_system, mock_popen):
        root = Mock()
        play_notification_sound(root)
        mock_popen.assert_called_once_with(
            ["notify-send", "--urgency=normal", "リマインダー"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @patch("reminder.notifications.subprocess.Popen", side_effect=FileNotFoundError)
    @patch("reminder.notifications.platform.system", return_value="Linux")
    def test_notify_send_not_found_still_rings_bell(self, _mock_system, _mock_popen):
        root = Mock()
        play_notification_sound(root)
        root.bell.assert_called_once_with()

    @patch("reminder.notifications.threading.Thread")
    @patch("reminder.notifications.platform.system", return_value="Darwin")
    def test_plays_afplay_on_darwin(self, _mock_system, mock_thread_cls):
        root = Mock()
        play_notification_sound(root)
        mock_thread_cls.assert_called_once()
        mock_thread_cls.return_value.start.assert_called_once()
        root.bell.assert_not_called()

    @patch("reminder.notifications.platform.system", return_value="Windows")
    def test_falls_back_to_bell_when_winsound_unavailable(self, _mock_system):
        root = Mock()
        play_notification_sound(root)
        root.bell.assert_called_once_with()


class PlatformHelperTests(unittest.TestCase):
    """プラットフォーム別ヘルパーの単体テスト。"""

    @patch("reminder.notifications.threading.Thread")
    def test_play_macos_sound_starts_daemon_thread(self, mock_thread_cls):
        _play_macos_sound()
        mock_thread_cls.assert_called_once()
        kwargs = mock_thread_cls.call_args.kwargs
        self.assertTrue(kwargs.get("daemon"))
        mock_thread_cls.return_value.start.assert_called_once()

    @patch("reminder.notifications.subprocess.Popen")
    def test_send_linux_notification_invokes_notify_send(self, mock_popen):
        _send_linux_notification()
        mock_popen.assert_called_once_with(
            ["notify-send", "--urgency=normal", "リマインダー"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @patch("reminder.notifications.subprocess.Popen", side_effect=FileNotFoundError)
    def test_send_linux_notification_swallows_missing_command(self, _mock_popen):
        _send_linux_notification()

    def test_ring_bell_invokes_root_bell(self):
        root = Mock()
        _ring_bell(root)
        root.bell.assert_called_once_with()

    def test_ring_bell_swallows_tcl_error(self):
        root = Mock()
        root.bell.side_effect = tk.TclError("bell unavailable")
        _ring_bell(root)


class SetWindowIconTests(unittest.TestCase):
    """_set_window_icon() の挙動を検証する。"""

    def test_does_not_raise_when_cairosvg_unavailable(self):
        root = Mock()
        _set_window_icon(root)

    @patch("reminder.notifications.tk.PhotoImage")
    @patch.dict("sys.modules", {"cairosvg": types.SimpleNamespace(svg2png=Mock(return_value=b"png-data"))})
    def test_keeps_icon_reference_on_root(self, mock_photo_image):
        root = Mock()
        icon = Mock()
        mock_photo_image.return_value = icon
        _set_window_icon(root)
        self.assertIs(root._icon_image, icon)
        root.iconphoto.assert_called_once_with(True, icon)


class CoerceIntTests(unittest.TestCase):
    """_coerce_int() の変換・クランプ動作を検証する。"""

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


def _create_app(snooze_value="5", hour_value="10", minute_value="30"):
    root = Mock()
    root.after.return_value = "job-1"

    with patch.object(ReminderApp, "_build_ui"), \
         patch("reminder.app.load_settings", return_value=Settings()), \
         patch("reminder.app.tk.StringVar", side_effect=lambda value="": _DummyVar(value)):
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
    @patch("reminder.app.messagebox.showwarning")
    def test_empty_message_shows_warning(self, mock_warning):
        app, root = _create_app()
        app.message_text.get.return_value = "   \n"
        app.schedule()
        mock_warning.assert_called_once_with("入力エラー", "表示したいメッセージを入力してください。")
        root.after.assert_not_called()

    @patch("reminder.app.save_settings")
    @patch("reminder.app.calculate_delay_ms", return_value=60_000)
    def test_schedule_sets_job_and_disables_button(self, _mock_delay, mock_save):
        app, root = _create_app(snooze_value="5", hour_value="10", minute_value="30")
        app.message_text.get.return_value = "テストメッセージ"
        app.schedule()
        root.after.assert_called_once()
        app.schedule_button.configure.assert_called_with(state=tk.DISABLED)
        app.cancel_button.configure.assert_called_with(state=tk.NORMAL)
        self.assertIsNotNone(app.scheduled_job_id)
        mock_save.assert_called_once()

    @patch("reminder.app.calculate_delay_ms", return_value=60_000)
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
    @patch("reminder.app.play_notification_sound")
    @patch("reminder.app.messagebox.askyesno", return_value=True)
    @patch("reminder.app.messagebox.showinfo")
    def test_show_reminder_schedules_snooze_with_explicit_minutes(self, mock_showinfo, mock_askyesno, mock_sound):
        app, root = _create_app(snooze_value="10")
        app.show_reminder("休憩しましょう", snooze_minutes=10)
        mock_sound.assert_called_once_with(root)
        mock_showinfo.assert_called_once_with("リマインダー", "休憩しましょう")
        mock_askyesno.assert_called_once_with("スヌーズ", "10分後に再通知しますか？")
        root.after.assert_called_once()
        app.schedule_button.configure.assert_called_with(state=tk.DISABLED)
        app.cancel_button.configure.assert_called_with(state=tk.NORMAL)
        app.status_var.set.assert_called_with("スヌーズ中です。10分後に再通知します。")

    @patch("reminder.app.play_notification_sound")
    @patch("reminder.app.messagebox.askyesno", return_value=True)
    @patch("reminder.app.messagebox.showinfo")
    def test_show_reminder_falls_back_to_snooze_var_when_not_passed(self, mock_showinfo, mock_askyesno, mock_sound):
        app, root = _create_app(snooze_value="7")
        app.show_reminder("テスト")
        mock_askyesno.assert_called_once_with("スヌーズ", "7分後に再通知しますか？")

    @patch("reminder.app.play_notification_sound")
    @patch("reminder.app.messagebox.askyesno", return_value=False)
    @patch("reminder.app.messagebox.showinfo")
    def test_show_reminder_updates_status_when_snooze_not_selected(self, _mock_showinfo, _mock_askyesno, _mock_sound):
        app, root = _create_app(snooze_value="15")
        app.show_reminder("休憩しましょう", snooze_minutes=15)
        root.after.assert_not_called()
        app.status_var.set.assert_called_with(STATUS_NOTIFIED)

    def test_normalize_snooze_input_clamps_out_of_range_value(self):
        app, _root = _create_app(snooze_value="999")
        minutes = app._normalize_snooze_input()
        self.assertEqual(minutes, 180)
        self.assertEqual(app.snooze_var.get(), "180")

    @patch("reminder.app.play_notification_sound")
    @patch("reminder.app.messagebox.showinfo")
    def test_show_reminder_skips_snooze_dialog_at_max_snooze_count(self, _mock_showinfo, _mock_sound):
        app, root = _create_app(snooze_value="5")
        with patch("reminder.app.messagebox.askyesno") as mock_askyesno:
            app.show_reminder("テスト", snooze_minutes=5, snooze_count=MAX_SNOOZE_COUNT)
        mock_askyesno.assert_not_called()
        root.after.assert_not_called()
        app.status_var.set.assert_called_with(STATUS_NOTIFIED)

    @patch("reminder.app.play_notification_sound")
    @patch("reminder.app.messagebox.askyesno", return_value=True)
    @patch("reminder.app.messagebox.showinfo")
    def test_show_reminder_allows_snooze_below_max_snooze_count(self, _mock_showinfo, _mock_askyesno, _mock_sound):
        app, root = _create_app(snooze_value="5")
        app.show_reminder("テスト", snooze_minutes=5, snooze_count=MAX_SNOOZE_COUNT - 1)
        _mock_askyesno.assert_called_once_with("スヌーズ", "5分後に再通知しますか？")
        root.after.assert_called_once()

    def test_schedule_snooze_resets_ui_when_root_after_raises(self):
        app, root = _create_app()
        root.after.side_effect = RuntimeError("after failed")
        with self.assertRaises(RuntimeError):
            app._schedule_snooze("テスト", 5, 0)
        self.assertIsNone(app.scheduled_job_id)
        app.schedule_button.configure.assert_called_with(state=tk.NORMAL)
        app.cancel_button.configure.assert_called_with(state=tk.DISABLED)


class BuildSectionTests(unittest.TestCase):
    def setUp(self):
        root = Mock()
        with patch.object(ReminderApp, "_build_ui"), \
             patch("reminder.app.load_settings", return_value=Settings()), \
             patch("reminder.app.tk.StringVar", side_effect=lambda value="": _DummyVar(value)):
            self.app = ReminderApp(root)
        self.frame = Mock()
        self._widget_patchers = [
            patch("reminder.app.ttk.Label", side_effect=lambda *args, **kwargs: Mock()),
            patch("reminder.app.tk.Text", side_effect=lambda *args, **kwargs: Mock()),
            patch("reminder.app.ttk.Spinbox", side_effect=lambda *args, **kwargs: Mock()),
            patch("reminder.app.ttk.Frame", side_effect=lambda *args, **kwargs: Mock()),
            patch("reminder.app.ttk.Button", side_effect=lambda *args, **kwargs: Mock()),
        ]
        for patcher in self._widget_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_build_message_section_creates_message_text(self):
        self.app._build_message_section(self.frame)
        self.assertTrue(hasattr(self.app, "message_text"))

    def test_build_message_section_binds_tab_keys(self):
        self.app._build_message_section(self.frame)
        bound_events = [call.args[0] for call in self.app.message_text.bind.call_args_list]
        self.assertIn("<Tab>", bound_events)
        self.assertIn("<Shift-Tab>", bound_events)

    def test_build_time_section_creates_hour_and_minute_menus(self):
        self.app._build_time_section(self.frame)
        self.assertTrue(hasattr(self.app, "hour_menu"))
        self.assertTrue(hasattr(self.app, "minute_menu"))

    def test_build_snooze_section_creates_snooze_menu(self):
        self.app._build_snooze_section(self.frame)
        self.assertTrue(hasattr(self.app, "snooze_menu"))

    def test_build_buttons_section_creates_both_buttons(self):
        self.app._build_buttons_section(self.frame)
        self.assertTrue(hasattr(self.app, "schedule_button"))
        self.assertTrue(hasattr(self.app, "cancel_button"))

    def test_build_status_section_sets_initial_message(self):
        with patch("reminder.app.tk.StringVar", side_effect=lambda value="": _DummyVar(value)):
            self.app._build_status_section(self.frame)
        self.assertEqual(self.app.status_var.get(), STATUS_IDLE)


class FocusNavigationTests(unittest.TestCase):
    def test_focus_next_moves_to_next_widget(self):
        app, root = _create_app()
        next_widget = Mock()
        current_widget = Mock()
        current_widget.tk_focusNext.return_value = next_widget
        root.focus_get.return_value = current_widget
        result = app._focus_next(Mock())
        next_widget.focus_set.assert_called_once()
        self.assertEqual(result, "break")

    def test_focus_next_returns_break_when_no_focused_widget(self):
        app, root = _create_app()
        root.focus_get.return_value = None
        result = app._focus_next(Mock())
        self.assertEqual(result, "break")

    def test_focus_prev_moves_to_prev_widget(self):
        app, root = _create_app()
        prev_widget = Mock()
        current_widget = Mock()
        current_widget.tk_focusPrev.return_value = prev_widget
        root.focus_get.return_value = current_widget
        result = app._focus_prev(Mock())
        prev_widget.focus_set.assert_called_once()
        self.assertEqual(result, "break")

    def test_focus_prev_returns_break_when_no_focused_widget(self):
        app, root = _create_app()
        root.focus_get.return_value = None
        result = app._focus_prev(Mock())
        self.assertEqual(result, "break")


class MainTests(unittest.TestCase):
    @patch("reminder.__main__.ReminderApp")
    @patch("reminder.__main__.tk.Tk")
    def test_main_creates_reminder_app_and_starts_mainloop(self, mock_tk_cls, mock_app_cls):
        mock_root = Mock()
        mock_tk_cls.return_value = mock_root
        from reminder.__main__ import main
        main()
        mock_tk_cls.assert_called_once()
        mock_app_cls.assert_called_once_with(mock_root)
        mock_root.mainloop.assert_called_once()


class SettingsTests(unittest.TestCase):
    def test_default_settings(self):
        s = Settings()
        self.assertEqual(s.message, "")
        self.assertEqual(s.hour, "00")
        self.assertEqual(s.minute, "00")
        self.assertEqual(s.snooze_minutes, "5")

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "settings.json")
            original = Settings(message="テスト", hour="14", minute="30", snooze_minutes="10")
            with patch("reminder.config._CONFIG_PATH", config_path), \
                 patch("reminder.config._CONFIG_DIR", tmpdir):
                save_settings(original)
                loaded = load_settings()
            self.assertEqual(loaded.message, "テスト")
            self.assertEqual(loaded.hour, "14")
            self.assertEqual(loaded.minute, "30")
            self.assertEqual(loaded.snooze_minutes, "10")

    def test_load_returns_default_when_file_missing(self):
        with patch("reminder.config._CONFIG_PATH", "/nonexistent/path.json"):
            s = load_settings()
        self.assertEqual(s.message, "")

    def test_load_ignores_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "settings.json")
            with open(config_path, "w") as f:
                json.dump({"message": "hello", "unknown_key": "value"}, f)
            with patch("reminder.config._CONFIG_PATH", config_path):
                s = load_settings()
            self.assertEqual(s.message, "hello")


if __name__ == "__main__":
    unittest.main()
