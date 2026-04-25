"""リマインダーアプリケーションパッケージ。"""

from .app import ReminderApp
from .config import Settings, load_settings, save_settings
from .notifications import (
    _play_macos_sound,
    _ring_bell,
    _send_linux_notification,
    _set_window_icon,
    play_notification_sound,
)
from .time_utils import (
    DEFAULT_SNOOZE_MINUTES,
    MAX_SNOOZE_COUNT,
    SNOOZE_MAX_MINUTES,
    SNOOZE_MIN_MINUTES,
    STATUS_IDLE,
    STATUS_NOTIFIED,
    calculate_delay_ms,
)

__all__ = [
    "ReminderApp",
    "Settings",
    "calculate_delay_ms",
    "load_settings",
    "play_notification_sound",
    "save_settings",
    "DEFAULT_SNOOZE_MINUTES",
    "MAX_SNOOZE_COUNT",
    "SNOOZE_MIN_MINUTES",
    "SNOOZE_MAX_MINUTES",
    "STATUS_IDLE",
    "STATUS_NOTIFIED",
    "_play_macos_sound",
    "_ring_bell",
    "_send_linux_notification",
    "_set_window_icon",
]
