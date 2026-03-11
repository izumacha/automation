"""tkinter が利用できない環境でテストを実行できるようにするモック設定。"""
import sys
from unittest.mock import MagicMock

try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    mock_tk = MagicMock()
    mock_tk.DISABLED = "disabled"
    mock_tk.NORMAL = "normal"
    mock_tk.END = "end"
    mock_tk.TclError = type("TclError", (Exception,), {})

    sys.modules["tkinter"] = mock_tk
    sys.modules["tkinter.ttk"] = MagicMock()
    sys.modules["tkinter.messagebox"] = MagicMock()
