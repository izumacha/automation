"""reminder.py — 時刻指定リマインダー GUI アプリ

ユーザーが指定した時刻にダイアログで通知し、スヌーズ機能を提供する。
tkinter を使用したシングルウィンドウ構成。

主要な状態遷移:
    [アイドル] → schedule() → [スケジュール済み]
                                    ↓ 時刻到達
                              show_reminder() → [通知表示中]
                                    ↓ スヌーズ選択
                             _schedule_snooze() → [スケジュール済み]
                                    ↓ スヌーズ拒否 / 上限到達
                                  [アイドル]
"""
from __future__ import annotations

import base64
import datetime
import logging
import os
import platform
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

# スヌーズのデフォルト間隔（分）
DEFAULT_SNOOZE_MINUTES = 5
# スヌーズを許可する最大回数。上限到達時はスヌーズダイアログを表示しない
MAX_SNOOZE_COUNT = 10


def _set_window_icon(root: tk.Tk) -> None:
    """SVG アイコンをウィンドウに設定する。変換ライブラリが無い場合は無視する。"""
    try:
        import cairosvg  # type: ignore[import]

        # このファイルと同階層の assets/ ディレクトリにある SVG を使用する
        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "reminder_icon.svg")
        png_data = cairosvg.svg2png(url=svg_path, output_width=64, output_height=64)
        icon = tk.PhotoImage(data=base64.b64encode(png_data))
        # Tk 側で画像が解放されないように参照を保持する。
        root._icon_image = icon  # type: ignore[attr-defined]
        root.iconphoto(True, icon)
    except Exception as e:
        logging.debug("ウィンドウアイコンの設定をスキップしました: %s", e)


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


def play_notification_sound(root: tk.Tk) -> None:
    """通知音を再生する。

    プラットフォームごとに最適な方法を試み、失敗時は tkinter の bell() にフォールバックする。
    - macOS: afplay コマンドで Glass.aiff を再生（別スレッド）
    - Windows: winsound.MessageBeep で警告音を再生
    - Linux: notify-send でデスクトップ通知を送信（失敗時は bell）
    - その他 / 上記失敗時: root.bell()
    """
    system_name = platform.system()
    try:
        if system_name == "Darwin":
            def _play_and_wait() -> None:
                proc = subprocess.Popen(
                    ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                proc.wait()

            # UI スレッドをブロックしないよう別スレッドで再生する
            threading.Thread(target=_play_and_wait, daemon=True).start()
            return
        if system_name == "Windows":
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        if system_name == "Linux":
            try:
                subprocess.Popen(
                    ["notify-send", "--urgency=normal", "リマインダー"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                # notify-send が利用できない場合は bell にフォールバック
                logging.debug("notify-send の送信に失敗しました: %s", e)
    except Exception:
        # OS 固有の再生に失敗した場合は bell にフォールバック
        pass

    try:
        root.bell()
    except tk.TclError:
        # 実行環境によっては bell が利用できないことがあるため無視する。
        pass


class ReminderApp:
    """リマインダー設定用のシンプルなGUIアプリ。

    Attributes:
        root: tkinter のルートウィンドウ。
        scheduled_job_id: root.after() が返すジョブ ID。未スケジュール時は None。
        hour_var: 通知時刻の「時」を保持する StringVar。
        minute_var: 通知時刻の「分」を保持する StringVar。
        snooze_var: スヌーズ間隔（分）を保持する StringVar。
    """

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        # root.after() が返すジョブ ID。None はスケジュールなしを意味する
        self.scheduled_job_id: str | None = None

        # 入力欄の初期値を現在時刻に設定する
        now = datetime.datetime.now()
        self.hour_var = tk.StringVar(value=f"{now.hour:02d}")
        self.minute_var = tk.StringVar(value=f"{now.minute:02d}")
        self.snooze_var = tk.StringVar(value=str(DEFAULT_SNOOZE_MINUTES))

        self._build_ui()

    # ------------------------------------------------------------------ UI 構築

    def _build_ui(self) -> None:
        """ウィンドウとすべての UI コンポーネントを構築する。

        各セクションを専用メソッドに委譲し、ウィンドウレベルのバインドを設定する。
        レイアウトは単一カラムの ttk.Frame で、行ごとにセクションが並ぶ。
        """
        self.root.title("リマインダー")
        _set_window_icon(self.root)
        self.root.resizable(False, False)
        self.root.columnconfigure(0, weight=1)

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        self._build_message_section(frame)   # row 0-1: メッセージ入力
        self._build_time_section(frame)      # row 2:   通知時刻
        self._build_snooze_section(frame)    # row 3:   スヌーズ間隔
        self._build_buttons_section(frame)   # row 4:   設定・解除ボタン
        self._build_status_section(frame)    # row 5:   ステータスラベル

        # Enter キーでリマインダーを設定できるようにする
        self.root.bind("<Return>", lambda _event: self.schedule())
        self.message_text.focus_set()

    def _build_message_section(self, frame: ttk.Frame) -> None:
        """メッセージ入力テキストエリアを生成する（row 0-1）。

        Tab / Shift-Tab でフォームの前後ウィジェットにフォーカスを移動できる。
        """
        ttk.Label(frame, text="メッセージ").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.message_text = tk.Text(frame, width=36, height=5, wrap="word")
        self.message_text.grid(row=1, column=0, columnspan=4, sticky="ew")
        # tk.Text は既定で Tab がフォーカス移動せずタブ文字を挿入するため上書きする
        self.message_text.bind("<Tab>", self._focus_next)
        self.message_text.bind("<Shift-Tab>", self._focus_prev)

    def _build_time_section(self, frame: ttk.Frame) -> None:
        """通知時刻（時・分）の Spinbox を生成する（row 2）。

        フォーカスが外れた時点で入力値を正規化し、2 桁ゼロ埋め表示に統一する。
        """
        ttk.Label(frame, text="通知時刻").grid(row=2, column=0, sticky="w", pady=(12, 8))
        self.hour_menu = ttk.Spinbox(
            frame,
            textvariable=self.hour_var,
            from_=0,
            to=23,
            wrap=True,   # 23 → 0 のラップアラウンドを有効にする
            width=4,
            format="%02.0f",
        )
        self.hour_menu.grid(row=2, column=1, sticky="w", pady=(12, 8))
        self.hour_menu.bind("<FocusOut>", lambda _event: self._normalize_time_inputs())

        ttk.Label(frame, text=":").grid(row=2, column=2, sticky="w", pady=(12, 8))

        self.minute_menu = ttk.Spinbox(
            frame,
            textvariable=self.minute_var,
            from_=0,
            to=59,
            wrap=True,   # 59 → 0 のラップアラウンドを有効にする
            width=4,
            format="%02.0f",
        )
        self.minute_menu.grid(row=2, column=3, sticky="w", pady=(12, 8))
        self.minute_menu.bind("<FocusOut>", lambda _event: self._normalize_time_inputs())

    def _build_snooze_section(self, frame: ttk.Frame) -> None:
        """スヌーズ間隔（分）の Spinbox を生成する（row 3）。

        フォーカスが外れた時点で 1〜180 の範囲内に正規化する。
        """
        ttk.Label(frame, text="スヌーズ間隔（分）").grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.snooze_menu = ttk.Spinbox(
            frame,
            textvariable=self.snooze_var,
            from_=1,
            to=180,
            wrap=True,
            width=6,
        )
        self.snooze_menu.grid(row=3, column=1, sticky="w", pady=(0, 8))
        self.snooze_menu.bind("<FocusOut>", lambda _event: self._normalize_snooze_input())

    def _build_buttons_section(self, frame: ttk.Frame) -> None:
        """「リマインダーを設定」「設定を解除」ボタンを生成する（row 4）。

        初期状態では cancel_button を無効化し、スケジュール後に有効化する。
        """
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 8))
        self.schedule_button = ttk.Button(buttons, text="リマインダーを設定", command=self.schedule)
        self.schedule_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(buttons, text="設定を解除", command=self.cancel_schedule, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

    def _build_status_section(self, frame: ttk.Frame) -> None:
        """ステータスメッセージを表示するラベルを生成する（row 5）。

        status_var の内容が変わると自動的に再描画される。
        """
        self.status_var = tk.StringVar(value="メッセージと通知時刻を設定してください。")
        ttk.Label(frame, textvariable=self.status_var, foreground="#444").grid(
            row=5, column=0, columnspan=4, sticky="w"
        )

    # ------------------------------------------------------------ フォーカス制御

    def _focus_next(self, _event: tk.Event) -> str:
        """Tab キーで次のウィジェットにフォーカスを移す。

        Returns:
            "break": tkinter のデフォルト Tab 処理（タブ文字挿入）を抑制する。
        """
        widget = self.root.focus_get()
        if widget is not None:
            widget.tk_focusNext().focus_set()
        return "break"

    def _focus_prev(self, _event: tk.Event) -> str:
        """Shift-Tab キーで前のウィジェットにフォーカスを移す。

        Returns:
            "break": tkinter のデフォルト Shift-Tab 処理を抑制する。
        """
        widget = self.root.focus_get()
        if widget is not None:
            widget.tk_focusPrev().focus_set()
        return "break"

    # ------------------------------------------------------------ 入力正規化

    def _normalize_time_inputs(self) -> None:
        """時刻入力値を範囲内に正規化して 2 桁表示にそろえる。"""
        self.hour_var.set(f"{self._coerce_int(self.hour_var.get(), 0, 23):02d}")
        self.minute_var.set(f"{self._coerce_int(self.minute_var.get(), 0, 59):02d}")

    def _normalize_snooze_input(self) -> int:
        """スヌーズ間隔を 1〜180 分に正規化し、正規化後の値を返す。"""
        value = self._coerce_int(self.snooze_var.get(), 1, 180)
        self.snooze_var.set(str(value))
        return value

    @staticmethod
    def _coerce_int(raw: str, min_value: int, max_value: int) -> int:
        """文字列を整数に変換し、[min_value, max_value] の範囲にクランプして返す。

        Args:
            raw: 変換対象の文字列。数値以外・空文字は min_value として扱う。
            min_value: 返値の最小値（変換失敗時のフォールバック値にもなる）。
            max_value: 返値の最大値。

        Returns:
            範囲内にクランプされた整数値。
        """
        try:
            value = int(raw)
        except ValueError:
            return min_value
        return max(min_value, min(max_value, value))

    # ------------------------------------------------------------ スケジュール

    def schedule(self) -> None:
        """入力内容を検証し、指定時刻に通知をスケジュールする。

        メッセージが空の場合は警告ダイアログを表示して処理を中断する。
        既存のジョブがあればキャンセルしてから新規スケジュールを登録する。
        root.after() の呼び出しに失敗した場合は UI をアイドル状態にリセットして例外を再送出する。
        """
        message = self.message_text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("入力エラー", "表示したいメッセージを入力してください。")
            return

        self._normalize_time_inputs()
        target = datetime.time(hour=int(self.hour_var.get()), minute=int(self.minute_var.get()))
        delay_ms = calculate_delay_ms(datetime.datetime.now(), target)

        snooze_minutes = self._normalize_snooze_input()

        self._cancel_job()
        try:
            self.scheduled_job_id = self.root.after(
                delay_ms, lambda: self.show_reminder(message, snooze_minutes)
            )
        except Exception:
            # after() が失敗した場合、ジョブ ID は None のままなのでボタン状態だけリセットする
            self._reset_to_idle()
            raise

        self._set_active_state(f"{target.hour:02d}:{target.minute:02d} に通知予定です（スヌーズ: {snooze_minutes}分）。")

    def _cancel_job(self) -> None:
        """スケジュール済みジョブをキャンセルする（UI 状態は変更しない）。"""
        if self.scheduled_job_id is not None:
            self.root.after_cancel(self.scheduled_job_id)
            self.scheduled_job_id = None

    def _reset_to_idle(self) -> None:
        """ジョブをキャンセルし、UI をアイドル状態に戻す。

        例外ハンドラや中断パスから呼び出すことで、
        ボタン状態と scheduled_job_id を常に整合させる。
        """
        self._cancel_job()
        self.schedule_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_var.set("メッセージと通知時刻を設定してください。")

    def _set_active_state(self, status_msg: str) -> None:
        """UI をスケジュール済み状態（キャンセル可能）に設定する。"""
        self.schedule_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.status_var.set(status_msg)

    def cancel_schedule(self) -> None:
        """スケジュール済みの通知をユーザー操作でキャンセルする。"""
        if self.scheduled_job_id is None:
            return
        self._reset_to_idle()
        self.status_var.set("リマインダー設定を解除しました。")

    # ------------------------------------------------------------ 通知・スヌーズ

    def _show_notification(self, message: str) -> None:
        """通知音を再生し、メッセージダイアログを表示する。"""
        play_notification_sound(self.root)
        messagebox.showinfo("リマインダー", message)

    def show_reminder(self, message: str, snooze_minutes: int | None = None, snooze_count: int = 0) -> None:
        """通知ダイアログを表示し、スヌーズ有無を確認する。

        Args:
            message: 通知に表示するメッセージ。
            snooze_minutes: スヌーズ間隔（分）。None の場合は snooze_var から正規化して取得する。
            snooze_count: 現在のスヌーズ回数。MAX_SNOOZE_COUNT に達した場合はダイアログを省略する。
        """
        if snooze_minutes is None:
            snooze_minutes = self._normalize_snooze_input()

        # 通知ダイアログ表示前に UI をアイドル状態に戻す（キャンセルボタンを無効化）
        self._reset_to_idle()
        self._show_notification(message)

        # スヌーズ上限未満の場合のみ継続スヌーズを提案する
        if snooze_count < MAX_SNOOZE_COUNT and messagebox.askyesno("スヌーズ", f"{snooze_minutes}分後に再通知しますか？"):
            self._schedule_snooze(message, snooze_minutes, snooze_count + 1)
            return

        self.status_var.set("通知を表示しました。次のリマインダーを設定できます。")

    def _schedule_snooze(self, message: str, snooze_minutes: int, snooze_count: int) -> None:
        """指定間隔後に show_reminder を再呼び出しするスヌーズジョブを登録する。

        Args:
            message: 再通知するメッセージ。
            snooze_minutes: 次の通知までの待機時間（分）。
            snooze_count: 累積スヌーズ回数。show_reminder に引き継ぎ上限チェックに使用する。
        """
        delay_ms = int(datetime.timedelta(minutes=snooze_minutes).total_seconds() * 1000)
        try:
            self.scheduled_job_id = self.root.after(
                delay_ms, lambda: self.show_reminder(message, snooze_minutes, snooze_count)
            )
        except Exception:
            # after() が失敗した場合は UI をアイドル状態にリセットして例外を再送出する
            self._reset_to_idle()
            raise
        self._set_active_state(f"スヌーズ中です。{snooze_minutes}分後に再通知します。")


def main() -> None:
    """アプリケーションのエントリーポイント。Tk ウィンドウを生成してイベントループを起動する。"""
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
