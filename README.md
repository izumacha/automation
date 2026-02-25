# automation

自動化ツールをまとめたリポジトリです。

## ツール一覧

### `reminder.py` — 時刻指定リマインダー

メッセージと通知時刻を設定するシンプルな GUI アプリです。

- **起動方法**

  ```bash
  python reminder.py
  ```

- **.svg アイコンから起動できるアプリ化（Linux）**

  ```bash
  ./install_reminder_app.sh
  ```

  実行後、`~/.local/share/applications/reminder.desktop` が生成され、
  `assets/reminder_icon.svg` をアイコンにした「Reminder」アプリとして起動できます。

- **機能**
  - テキストエリアにメッセージを入力
  - 時・分のドロップダウンで通知時刻を指定
  - 指定時刻になるとダイアログと通知音で知らせる
  - リマインダーの設定解除に対応
  - `assets/reminder_icon.svg` をウィンドウアイコンとして表示（`cairosvg` が必要）

---

## セットアップ

```bash
pip install -r requirements.txt
```

`reminder.py` をデスクトップアプリとして使う場合は、上記インストール後に `./install_reminder_app.sh` を実行してください。

| パッケージ | 用途 |
|---|---|
| `cairosvg` | SVG アイコンの PNG 変換（`reminder.py` のウィンドウアイコン表示） |

---

## `reminder.py` をアプリとして使う手順（Linux）

以下の手順で、ターミナルを開かずにランチャーから使えるアプリとして利用できます。

1. 依存パッケージをインストール

   ```bash
   pip install -r requirements.txt
   ```

2. リマインダーアプリをインストール（`.desktop` 作成）

   ```bash
   ./install_reminder_app.sh
   ```

3. アプリ一覧で **Reminder** を検索して起動
   - 作成されるファイル: `~/.local/share/applications/reminder.desktop`
   - アイコン: `assets/reminder_icon.svg`

4. 初回起動後の使い方
   - メッセージを入力
   - 通知したい「時」「分」を選択
   - **リマインダーを設定** を押す
   - 通知時刻になるとダイアログと通知音で知らせる

5. 設定を解除したい場合
   - アプリ上の **設定を解除** を押す

> 補足: `reminder.py` は、ターミナルから `python reminder.py` で直接起動することもできます。

---

## テスト

```bash
python -m pytest tests
```

`tests/test_reminder.py` では以下を検証しています。

- `calculate_delay_ms` — 同分・未来・翌日ロールオーバー・深夜・1時間後の境界値
- `play_notification_sound` — Linux / macOS / Windows 各パスの呼び出しと `TclError` の無視
- `_set_window_icon` — `cairosvg` がない環境でも例外が発生しないこと
- `_coerce_int` — 範囲内・範囲外・非数値・境界値の正規化
- `_normalize_time_inputs` — 上限超過・負値・ゼロパディング・非数値のリセット
- `schedule` — 空メッセージ時の警告・正常系のジョブ登録とボタン状態
- `cancel_schedule` — ジョブなし時の無操作・アクティブジョブの解除
- `show_reminder` / `_schedule_snooze` — スヌーズ選択時の再スケジュール・スヌーズ拒否時のステータス更新

---

## ファイル構成

```
automation/
├── reminder.py              # 時刻指定リマインダー GUI
├── install_reminder_app.sh  # Linux 向けデスクトップエントリ生成
├── requirements.txt
├── requirements-dev.txt     # 開発・テスト用依存
├── assets/
│   └── reminder_icon.svg    # リマインダーアプリ用アイコン
└── tests/
    ├── __init__.py
    └── test_reminder.py
```
