"""リマインダーアプリ GUI クラス。

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

import datetime
import logging
import tkinter as tk
from tkinter import messagebox, ttk

from .config import Settings, load_settings, save_settings
from .notifications import _set_window_icon, play_notification_sound
from .time_utils import (
    DEFAULT_SNOOZE_MINUTES,
    MAX_SNOOZE_COUNT,
    SNOOZE_MAX_MINUTES,
    SNOOZE_MIN_MINUTES,
    STATUS_IDLE,
    STATUS_NOTIFIED,
    calculate_delay_ms,
)


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

        saved = load_settings()
        # 入力欄の初期値: 保存済み設定があればそれを使用、なければ現在時刻
        now = datetime.datetime.now()
        self.hour_var = tk.StringVar(value=saved.hour if saved.hour != "00" or saved.minute != "00" else f"{now.hour:02d}")
        self.minute_var = tk.StringVar(value=saved.minute if saved.hour != "00" or saved.minute != "00" else f"{now.minute:02d}")
        self.snooze_var = tk.StringVar(value=saved.snooze_minutes)

        self._build_ui()

        if saved.message:
            self.message_text.insert("1.0", saved.message)

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

        # OS ネイティブに近いテーマを選択
        style = ttk.Style()
        available = style.theme_names()
        for theme in ("aqua", "clam", "vista"):
            if theme in available:
                style.theme_use(theme)
                break

        style.configure("TLabel", font=("system", 11))
        style.configure("TButton", font=("system", 11), padding=6)
        style.configure("TSpinbox", font=("system", 11))
        style.configure("Status.TLabel", font=("system", 10), foreground="#666")

        frame = ttk.Frame(self.root, padding=20)
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
        ttk.Label(frame, text="メッセージ").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.message_text = tk.Text(frame, width=38, height=5, wrap="word",
                                    font=("system", 11), relief="flat",
                                    highlightthickness=1, highlightcolor="#0078d4",
                                    highlightbackground="#ccc", padx=6, pady=6)
        self.message_text.grid(row=1, column=0, columnspan=4, sticky="ew")
        # tk.Text は既定で Tab がフォーカス移動せずタブ文字を挿入するため上書きする
        self.message_text.bind("<Tab>", self._focus_next)
        self.message_text.bind("<Shift-Tab>", self._focus_prev)

    def _build_time_section(self, frame: ttk.Frame) -> None:
        """通知時刻（時・分）の Spinbox を生成する（row 2）。

        フォーカスが外れた時点で入力値を正規化し、2 桁ゼロ埋め表示に統一する。
        """
        ttk.Label(frame, text="通知時刻").grid(row=2, column=0, sticky="w", pady=(14, 6))
        self.hour_menu = ttk.Spinbox(
            frame,
            textvariable=self.hour_var,
            from_=0,
            to=23,
            wrap=True,   # 23 → 0 のラップアラウンドを有効にする
            width=4,
            format="%02.0f",
        )
        self.hour_menu.grid(row=2, column=1, sticky="w", pady=(14, 6))
        self.hour_menu.bind("<FocusOut>", lambda _event: self._normalize_time_inputs())

        ttk.Label(frame, text=":", font=("system", 14, "bold")).grid(
            row=2, column=2, sticky="w", pady=(14, 6), padx=(2, 2))

        self.minute_menu = ttk.Spinbox(
            frame,
            textvariable=self.minute_var,
            from_=0,
            to=59,
            wrap=True,   # 59 → 0 のラップアラウンドを有効にする
            width=4,
            format="%02.0f",
        )
        self.minute_menu.grid(row=2, column=3, sticky="w", pady=(14, 6))
        self.minute_menu.bind("<FocusOut>", lambda _event: self._normalize_time_inputs())

    def _build_snooze_section(self, frame: ttk.Frame) -> None:
        """スヌーズ間隔（分）の Spinbox を生成する（row 3）。

        フォーカスが外れた時点で SNOOZE_MIN_MINUTES〜SNOOZE_MAX_MINUTES の範囲内に正規化する。
        """
        ttk.Label(frame, text="スヌーズ間隔（分）").grid(row=3, column=0, sticky="w", pady=(4, 6))
        self.snooze_menu = ttk.Spinbox(
            frame,
            textvariable=self.snooze_var,
            from_=SNOOZE_MIN_MINUTES,
            to=SNOOZE_MAX_MINUTES,
            wrap=True,
            width=6,
        )
        self.snooze_menu.grid(row=3, column=1, sticky="w", pady=(4, 6))
        self.snooze_menu.bind("<FocusOut>", lambda _event: self._normalize_snooze_input())

    def _build_buttons_section(self, frame: ttk.Frame) -> None:
        """「リマインダーを設定」「設定を解除」ボタンを生成する（row 4）。

        初期状態では cancel_button を無効化し、スケジュール後に有効化する。
        """
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(12, 8))
        self.schedule_button = ttk.Button(buttons, text="リマインダーを設定", command=self.schedule)
        self.schedule_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(buttons, text="設定を解除", command=self.cancel_schedule, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

    def _build_status_section(self, frame: ttk.Frame) -> None:
        """ステータスメッセージを表示するラベルを生成する（row 5）。

        status_var の内容が変わると自動的に再描画される。
        """
        self.status_var = tk.StringVar(value=STATUS_IDLE)
        ttk.Label(frame, textvariable=self.status_var, style="Status.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(4, 0)
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
        """スヌーズ間隔を SNOOZE_MIN_MINUTES〜SNOOZE_MAX_MINUTES に正規化し、正規化後の値を返す。"""
        value = self._coerce_int(self.snooze_var.get(), SNOOZE_MIN_MINUTES, SNOOZE_MAX_MINUTES)
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
        logging.info("リマインダーを設定: %02d:%02d（スヌーズ: %d 分）", target.hour, target.minute, snooze_minutes)

        save_settings(Settings(
            message=message,
            hour=self.hour_var.get(),
            minute=self.minute_var.get(),
            snooze_minutes=self.snooze_var.get(),
        ))

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
        self.status_var.set(STATUS_IDLE)

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
        logging.info("リマインダーの設定を解除しました。")

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
        logging.info("リマインダーを通知: スヌーズ回数 %d", snooze_count)
        self._show_notification(message)

        # スヌーズ上限未満の場合のみ継続スヌーズを提案する
        if snooze_count < MAX_SNOOZE_COUNT and messagebox.askyesno("スヌーズ", f"{snooze_minutes}分後に再通知しますか？"):
            self._schedule_snooze(message, snooze_minutes, snooze_count + 1)
            return

        self.status_var.set(STATUS_NOTIFIED)

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
        logging.info("スヌーズを設定: %d 分後に再通知（回数: %d）", snooze_minutes, snooze_count)
