"""アプリケーションのエントリーポイント。Tk ウィンドウを生成してイベントループを起動する。"""
import logging
import tkinter as tk

from .app import ReminderApp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
