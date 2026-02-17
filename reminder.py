import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


def calculate_delay_ms(now: datetime.datetime, target: datetime.time) -> int:
    """現在時刻と目標時刻から、通知までの待機時間（ミリ秒）を返す。"""
    if now.hour == target.hour and now.minute == target.minute:
        return 0

    target_dt = now.replace(hour=target.hour, minute=target.minute, second=0, microsecond=0)

    # すでに過ぎている時刻が指定された場合は翌日に通知
    if target_dt < now:
        target_dt += datetime.timedelta(days=1)

    return int((target_dt - now).total_seconds() * 1000)


def ask_target_time(root: tk.Tk) -> datetime.time | None:
    """時間指定メニュー（時・分）を表示し、選択された時刻を返す。"""
    dialog = tk.Toplevel(root)
    dialog.title("時間指定メニュー")
    dialog.resizable(False, False)
    dialog.grab_set()

    selected = {"time": None}

    now = datetime.datetime.now()
    hour_var = tk.StringVar(value=f"{now.hour:02d}")
    minute_var = tk.StringVar(value=f"{now.minute:02d}")

    ttk.Label(dialog, text="通知時刻を選択してください").grid(
        row=0, column=0, columnspan=3, padx=12, pady=(12, 8)
    )

    hour_menu = ttk.Combobox(
        dialog,
        textvariable=hour_var,
        values=[f"{h:02d}" for h in range(24)],
        state="readonly",
        width=4,
    )
    hour_menu.grid(row=1, column=0, padx=(12, 4), pady=8)

    ttk.Label(dialog, text=":").grid(row=1, column=1, pady=8)

    minute_menu = ttk.Combobox(
        dialog,
        textvariable=minute_var,
        values=[f"{m:02d}" for m in range(60)],
        state="readonly",
        width=4,
    )
    minute_menu.grid(row=1, column=2, padx=(4, 12), pady=8)

    def on_ok() -> None:
        selected["time"] = datetime.time(
            hour=int(hour_var.get()), minute=int(minute_var.get())
        )
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.grid(row=2, column=0, columnspan=3, pady=(0, 12))

    ttk.Button(buttons, text="OK", command=on_ok).pack(side=tk.LEFT, padx=4)
    ttk.Button(buttons, text="キャンセル", command=on_cancel).pack(side=tk.LEFT, padx=4)

    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    root.wait_window(dialog)
    return selected["time"]


def schedule_message(root: tk.Tk, message: str, target: datetime.time) -> None:
    """指定時刻になったらメッセージを表示する。"""
    now = datetime.datetime.now()
    delay_ms = calculate_delay_ms(now, target)

    def show_reminder() -> None:
        messagebox.showinfo("リマインダー", message)
        root.destroy()

    root.after(delay_ms, show_reminder)


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    # ① 入力メッセージボックスを表示
    message = simpledialog.askstring("入力", "表示したいメッセージを入力してください:", parent=root)
    if not message:
        root.destroy()
        return

    # ② 入力後、時間指定メニュー表示
    target_time = ask_target_time(root)
    if target_time is None:
        root.destroy()
        return

    # ③ 時間設定後、現在時刻が同じになったらメッセージボックスで入力内容を表示
    schedule_message(root, message, target_time)

    wait_info = (
        f"{target_time.hour:02d}:{target_time.minute:02d} にメッセージを表示します。\n"
        "このままウィンドウを閉じずにお待ちください。"
    )
    messagebox.showinfo("設定完了", wait_info)

    root.mainloop()


if __name__ == "__main__":
    main()
