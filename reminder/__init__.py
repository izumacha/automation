"""Any Planner 風タスクプランナーアプリケーションパッケージ。

GUI（tkinter）に依存するシンボル（PlannerApp / ReminderApp / main /
play_notification_sound / _set_window_icon）は、パッケージ import 時には読み込まず
PEP 562 の ``__getattr__`` で初回アクセス時に遅延読み込みする。こうしないと
``import reminder.recurrence`` のような純粋ロジックだけの利用でも tkinter が必須になり、
tkinter を含まない Python（ヘッドレスサーバー・slim コンテナ・CI）で契約共有先の
Web/スマホ版がロジックを再利用できなくなるため（CLAUDE.md §10 ロジックと UI の分離）。
"""

from __future__ import annotations

from .config import Prefs, load_prefs, load_tasks, save_prefs, save_tasks
from .recurrence import (
    MAX_INTERVAL,
    MIN_INTERVAL,
    RECUR_DAILY,
    RECUR_LABELS,
    RECUR_MONTHLY,
    RECUR_NONE,
    RECUR_UNITS,
    RECUR_WEEKLY,
    RECUR_YEARLY,
    add_period,
    label_for_unit,
    next_occurrence,
    unit_for_label,
)
from .stats import completed_count_on, current_streak, total_completed
from .task import Task, build_next_task, make_due
from .time_utils import (
    STATUS_IDLE,
    delay_ms_until,
)
from .timeline import (
    ScheduledRow,
    TimelineRow,
    backlog_tasks,
    build_day_timeline,
    carry_over_overdue,
    format_duration,
    free_minutes_today,
    prune_old_completed,
    scheduled_rows,
    suggest_for_free_time,
)

# GUI（tkinter）依存のシンボル名と「定義元モジュール名」の対応表。
# ここに載せた名前は下の __getattr__ が初回アクセス時にだけ import する。
# main は cli モジュールに定義（pyproject の scripts エントリ reminder:main から参照される。
# __main__ ではなく cli から import することで、python -m reminder 実行時に
# __main__ が二重ロードされる RuntimeWarning を避ける）。
_LAZY_GUI_EXPORTS = {
    "PlannerApp": "app",              # アプリ本体（tkinter ウィジェットを構築する）
    "ReminderApp": "app",             # 旧名の別名（後方互換のため公開を維持する）
    "main": "cli",                    # CLI エントリーポイント（tk.Tk() を生成する）
    "play_notification_sound": "notifications",  # 通知音の再生（tk.bell フォールバックあり）
    "_set_window_icon": "notifications",         # ウィンドウアイコン設定（tkinter 必須）
}


def __getattr__(name: str):
    """GUI 依存シンボルへの初回アクセス時にだけ定義元モジュールを読み込む（PEP 562）。

    tkinter を持たない環境でも純粋ロジック（recurrence / timeline / stats 等）の
    import を成立させるための遅延読み込み。対応表に無い名前は通常どおり
    AttributeError にする（存在しない属性を静かに握り潰さない）。
    """
    # 対応表に載っている GUI 依存シンボルかどうかを調べる
    module_name = _LAZY_GUI_EXPORTS.get(name)
    # 対応表に無い名前は通常の属性エラーとして報告する
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # 定義元モジュールをこのタイミングで初めて import する（ここで tkinter が読み込まれる）
    module = __import__(f"{__name__}.{module_name}", fromlist=[name])
    # モジュールから目的のシンボルを取り出す
    value = getattr(module, name)
    # 次回以降は __getattr__ を通らないよう、パッケージ属性としてキャッシュする
    globals()[name] = value
    # 取り出したシンボルを返す
    return value


__all__ = [
    "PlannerApp",
    "ReminderApp",
    "Task",
    "build_next_task",
    "make_due",
    "load_tasks",
    "save_tasks",
    "Prefs",
    "load_prefs",
    "save_prefs",
    "build_day_timeline",
    "carry_over_overdue",
    "prune_old_completed",
    "backlog_tasks",
    "suggest_for_free_time",
    "free_minutes_today",
    "scheduled_rows",
    "ScheduledRow",
    "TimelineRow",
    "format_duration",
    "completed_count_on",
    "current_streak",
    "total_completed",
    "play_notification_sound",
    "delay_ms_until",
    "add_period",
    "next_occurrence",
    "label_for_unit",
    "unit_for_label",
    "main",
    "RECUR_NONE",
    "RECUR_DAILY",
    "RECUR_WEEKLY",
    "RECUR_MONTHLY",
    "RECUR_YEARLY",
    "RECUR_UNITS",
    "RECUR_LABELS",
    "MIN_INTERVAL",
    "MAX_INTERVAL",
    "STATUS_IDLE",
    "_set_window_icon",
]
