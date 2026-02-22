import base64
import datetime
import logging
import os
import platform
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

DEFAULT_SNOOZE_MINUTES = 5


def _set_window_icon(root: tk.Tk) -> None:
    """SVG アイコンをウィンドウに設定する。変換ライブラリが無い場合は無視する。"""
    try:
        import cairosvg  # type: ignore[import]

        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "reminder_icon.svg")
        png_data = cairosvg.svg2png(url=svg_path, output_width=64, output_height=64)
        icon = tk.PhotoImage(data=base64.b64encode(png_data))
        root.iconphoto(True, icon)
    except Exception as e:
        logging.debug("ウィンドウアイコンの設定をスキップしました: %s", e)


def calculate_delay_ms(now: datetime.datetime, target: datetime.time) -> int:
    """現在時刻と目標時刻から、通知までの待機時間（ミリ秒）を返す。"""
    if now.hour == target.hour and now.minute == target.minute:
        return 0

    target_dt = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)

    # すでに過ぎている時刻が指定された場合は翌日に通知
    if target_dt < now:
        target_dt += datetime.timedelta(days=1)

    return int((target_dt - now).total_seconds() * 1000)


def play_notification_sound(root: tk.Tk) -> None:
    """通知音を再生する。"""
    system_name = platform.system()
    try:
        if system_name == "Darwin":
            # macOS 標準の通知音ファイルを優先して再生
            subprocess.Popen(
                ["/usr/bin/afplay", "/System/Library/Sounds/Glass.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        if system_name == "Windows":
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
    except Exception:
        # OS 固有の再生に失敗した場合は bell にフォールバック
        pass

    try:
        root.bell()
    except tk.TclError:
        # 実行環境によっては bell が利用できないことがあるため無視する。
        pass


class ReminderApp:
    """リマインダー設定用のシンプルなGUIアプリ。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("リマインダー")
        _set_window_icon(self.root)
        self.root.resizable(False, False)
        self.root.columnconfigure(0, weight=1)

        self.scheduled_job_id: str | None = None

        now = datetime.datetime.now()
        self.hour_var = tk.StringVar(value=f"{now.hour:02d}")
        self.minute_var = tk.StringVar(value=f"{now.minute:02d}")
        self.snooze_var = tk.StringVar(value=str(DEFAULT_SNOOZE_MINUTES))

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="メッセージ").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.message_text = tk.Text(frame, width=36, height=5, wrap="word")
        self.message_text.grid(row=1, column=0, columnspan=4, sticky="ew")
        self.message_text.bind("<Tab>", self._focus_next)
        self.message_text.bind("<Shift-Tab>", self._focus_prev)

        ttk.Label(frame, text="通知時刻").grid(row=2, column=0, sticky="w", pady=(12, 8))

        self.hour_menu = ttk.Spinbox(
            frame,
            textvariable=self.hour_var,
            from_=0,
            to=23,
            wrap=True,
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
            wrap=True,
            width=4,
            format="%02.0f",
        )
        self.minute_menu.grid(row=2, column=3, sticky="w", pady=(12, 8))
        self.minute_menu.bind("<FocusOut>", lambda _event: self._normalize_time_inputs())

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

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=4, sticky="w", pady=(8, 8))
        self.schedule_button = ttk.Button(buttons, text="リマインダーを設定", command=self.schedule)
        self.schedule_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(buttons, text="設定を解除", command=self.cancel_schedule, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="メッセージと通知時刻を設定してください。")
        ttk.Label(frame, textvariable=self.status_var, foreground="#444").grid(
            row=5, column=0, columnspan=4, sticky="w"
        )
        self.root.bind("<Return>", lambda _event: self.schedule())
        self.message_text.focus_set()

    def _focus_next(self, _event: tk.Event) -> str:
        self.root.focus_get().tk_focusNext().focus_set()
        return "break"

    def _focus_prev(self, _event: tk.Event) -> str:
        self.root.focus_get().tk_focusPrev().focus_set()
        return "break"

    def _normalize_time_inputs(self) -> None:
        """時刻入力値を範囲内に正規化して 2 桁表示にそろえる。"""
        self.hour_var.set(f"{self._coerce_int(self.hour_var.get(), 0, 23):02d}")
        self.minute_var.set(f"{self._coerce_int(self.minute_var.get(), 0, 59):02d}")

    def _normalize_snooze_input(self) -> None:
        """スヌーズ間隔を 1〜180 分に正規化する。"""
        self.snooze_var.set(str(self._coerce_int(self.snooze_var.get(), 1, 180)))

    @staticmethod
    def _coerce_int(raw: str, min_value: int, max_value: int) -> int:
        try:
            value = int(raw)
        except ValueError:
            return min_value
        return max(min_value, min(max_value, value))

    def _get_snooze_minutes(self) -> int:
        self._normalize_snooze_input()
        return int(self.snooze_var.get())

    def schedule(self) -> None:
        message = self.message_text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("入力エラー", "表示したいメッセージを入力してください。")
            return

        self._normalize_time_inputs()
        target = datetime.time(hour=int(self.hour_var.get()), minute=int(self.minute_var.get()))
        delay_ms = calculate_delay_ms(datetime.datetime.now(), target)

        self._cancel_job()
        self.scheduled_job_id = self.root.after(delay_ms, lambda: self.show_reminder(message))

        snooze_minutes = self._get_snooze_minutes()
        self.schedule_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.status_var.set(f"{target.hour:02d}:{target.minute:02d} に通知予定です（スヌーズ: {snooze_minutes}分）。")

    def _cancel_job(self) -> None:
        """スケジュール済みジョブをキャンセルする（UI 状態は変更しない）。"""
        if self.scheduled_job_id is not None:
            self.root.after_cancel(self.scheduled_job_id)
            self.scheduled_job_id = None

    def cancel_schedule(self) -> None:
        if self.scheduled_job_id is None:
            return
        self._cancel_job()
        self.status_var.set("リマインダー設定を解除しました。")
        self.schedule_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)

    def show_reminder(self, message: str) -> None:
        self.scheduled_job_id = None
        self.schedule_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        play_notification_sound(self.root)
        messagebox.showinfo("リマインダー", message)

        snooze_minutes = self._get_snooze_minutes()
        if messagebox.askyesno("スヌーズ", f"{snooze_minutes}分後に再通知しますか？"):
            self._schedule_snooze(message, snooze_minutes)
            return

        self.status_var.set("通知を表示しました。次のリマインダーを設定できます。")

    def _schedule_snooze(self, message: str, snooze_minutes: int) -> None:
        self._cancel_job()
        delay_ms = int(datetime.timedelta(minutes=snooze_minutes).total_seconds() * 1000)
        self.scheduled_job_id = self.root.after(delay_ms, lambda: self.show_reminder(message))
        self.schedule_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.status_var.set(f"スヌーズ中です。{snooze_minutes}分後に再通知します。")


def main() -> None:
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
