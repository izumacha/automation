"""GUI（tkinter）非搭載環境でも純粋ロジックが import できることの回帰テスト。

conftest.py は tkinter が無い環境で MagicMock を注入するため、このテストは
モック注入の効かない「素の子プロセス」で import を実行して検証する。
パッケージの __init__ が GUI モジュール（app / notifications / cli）を
eager import してしまうと、契約共有先（Web/スマホ版）やヘッドレス CI が
recurrence / timeline 等の純粋ロジックを再利用できなくなる（CLAUDE.md §10）。
"""

from __future__ import annotations

import subprocess  # 子プロセスで素の Python を起動するために使う
import sys  # 現在のインタープリタのパスを得るために使う
import unittest  # 標準のテストフレームワークを使う
from pathlib import Path  # リポジトリルートのパス計算に使う

# リポジトリのルートディレクトリ（このファイルの親の親）を求める
REPO_ROOT = Path(__file__).resolve().parent.parent

# 子プロセスで実行するスクリプト。tkinter の import を強制的に失敗させた上で、
# パッケージ本体と純粋ロジック一式を import できること、GUI シンボルへの
# アクセスだけが ImportError になることを検証する
_PROBE_SCRIPT = """
import sys
# sys.modules に None を入れると、以後の `import tkinter` は ImportError になる
sys.modules["tkinter"] = None

# パッケージ本体と純粋ロジックの import が tkinter 無しで成立すること
import reminder
import reminder.config
import reminder.recurrence
import reminder.stats
import reminder.task
import reminder.theme
import reminder.time_utils
import reminder.timeline

# 純粋ロジックの公開シンボルがパッケージ属性として参照できること
reminder.free_minutes_today
reminder.next_occurrence
reminder.current_streak

# GUI 依存シンボルへのアクセスは（遅延読み込みの結果）ImportError になること
try:
    reminder.PlannerApp
except ImportError:
    print("OK")
else:
    print("GUI import unexpectedly succeeded")
"""


class PureImportTests(unittest.TestCase):
    """tkinter をブロックした子プロセスで純粋ロジックの import を検証する。"""

    def test_pure_modules_import_without_tkinter(self):
        """tkinter が無くても純粋ロジックの import が成立することを担保する。"""
        # 素の Python 子プロセスで検証スクリプトを実行する（conftest のモック注入を回避）
        result = subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        # import 失敗があれば stderr にトレースバックが出るので、メッセージに含めて報告する
        self.assertEqual(
            result.returncode, 0,
            f"純粋ロジックの import が tkinter 無しで失敗しました:\n{result.stderr}",
        )
        # GUI シンボルへのアクセスだけが ImportError になったことを確認する
        self.assertEqual(result.stdout.strip(), "OK", result.stdout)


if __name__ == "__main__":  # このファイルを直接実行した場合
    unittest.main()  # ユニットテストを起動する
