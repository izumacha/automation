from __future__ import annotations

import datetime

# スヌーズのデフォルト間隔（分）
DEFAULT_SNOOZE_MINUTES = 5
# スヌーズを許可する最大回数。上限到達時はスヌーズダイアログを表示しない
MAX_SNOOZE_COUNT = 10
# スヌーズ間隔の最小・最大値（分）。UI の Spinbox 範囲と正規化ロジックで共有する
SNOOZE_MIN_MINUTES = 1
SNOOZE_MAX_MINUTES = 180

# ステータスラベルの定型メッセージ。複数箇所で参照するため定数化する
STATUS_IDLE = "メッセージと通知時刻を設定してください。"
STATUS_NOTIFIED = "通知を表示しました。次のリマインダーを設定できます。"


def calculate_delay_ms(now: datetime.datetime, target: datetime.time) -> int:
    """現在時刻と目標時刻から、通知までの待機時間（ミリ秒）を返す。

    Args:
        now: 現在日時。
        target: 通知したい時刻（時・分のみ使用）。

    Returns:
        通知まで待機すべきミリ秒数。同分の場合は 0、過去時刻の場合は翌日分を返す。
    """
    if now.hour == target.hour and now.minute == target.minute:
        return 0

    target_dt = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)

    # すでに過ぎている時刻が指定された場合は翌日に通知
    if target_dt < now:
        target_dt += datetime.timedelta(days=1)

    return int((target_dt - now).total_seconds() * 1000)
