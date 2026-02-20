import base64
import datetime
import os
import tkinter as tk
from tkinter import messagebox, ttk


def _set_window_icon(root: tk.Tk) -> None:
    """SVG アイコンをウィンドウに設定する。変換ライブラリが無い場合は無視する。"""
    try:
        import cairosvg  # type: ignore[import]

        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "reminder_icon.svg")
        png_data = cairosvg.svg2png(url=svg_path, output_width=64, output_height=64)
        icon = tk.PhotoImage(data=base64.b64encode(png_data))
        root.iconphoto(True, icon)
    except Exception:
        pass


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

        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="メッセージ").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.message_text = tk.Text(frame, width=36, height=5, wrap="word")
        self.message_text.grid(row=1, column=0, columnspan=4, sticky="ew")

        ttk.Label(frame, text="通知時刻").grid(row=2, column=0, sticky="w", pady=(12, 8))

        self.hour_menu = ttk.Combobox(
            frame,
            textvariable=self.hour_var,
            values=[f"{h:02d}" for h in range(24)],
            state="readonly",
            width=4,
        )
        self.hour_menu.grid(row=2, column=1, sticky="w", pady=(12, 8))

        ttk.Label(frame, text=":").grid(row=2, column=2, sticky="w", pady=(12, 8))

        self.minute_menu = ttk.Combobox(
            frame,
            textvariable=self.minute_var,
            values=[f"{m:02d}" for m in range(60)],
            state="readonly",
            width=4,
        )
        self.minute_menu.grid(row=2, column=3, sticky="w", pady=(12, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=4, sticky="w", pady=(8, 8))
        self.schedule_button = ttk.Button(buttons, text="リマインダーを設定", command=self.schedule)
        self.schedule_button.pack(side=tk.LEFT)
        self.cancel_button = ttk.Button(buttons, text="設定を解除", command=self.cancel_schedule, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="メッセージと通知時刻を設定してください。")
        ttk.Label(frame, textvariable=self.status_var, foreground="#444").grid(
            row=4, column=0, columnspan=4, sticky="w"
        )

    def schedule(self) -> None:
        message = self.message_text.get("1.0", tk.END).strip()
        if not message:
            messagebox.showwarning("入力エラー", "表示したいメッセージを入力してください。")
            return

        target = datetime.time(hour=int(self.hour_var.get()), minute=int(self.minute_var.get()))
        delay_ms = calculate_delay_ms(datetime.datetime.now(), target)

        self.cancel_schedule()
        self.scheduled_job_id = self.root.after(delay_ms, lambda: self.show_reminder(message))

        self.schedule_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.status_var.set(f"{target.hour:02d}:{target.minute:02d} に通知予定です。")

    def cancel_schedule(self) -> None:
        if self.scheduled_job_id is not None:
            self.root.after_cancel(self.scheduled_job_id)
            self.scheduled_job_id = None
            self.status_var.set("リマインダー設定を解除しました。")

        self.schedule_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)

    def show_reminder(self, message: str) -> None:
        self.scheduled_job_id = None
        self.schedule_button.configure(state=tk.NORMAL)
        self.cancel_button.configure(state=tk.DISABLED)
        self.status_var.set("通知を表示しました。次のリマインダーを設定できます。")
        play_notification_sound(self.root)
        messagebox.showinfo("リマインダー", message)


def main() -> None:
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
