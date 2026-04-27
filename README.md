# automation

自動化ツールをまとめたリポジトリです。

## ツール一覧

### リマインダーアプリ — 時刻指定リマインダー

メッセージと通知時刻を設定するシンプルな GUI アプリです。

- **起動方法**

  ```bash
  python -m reminder
  ```

- **pipx でインストールして起動（推奨）**

  ```bash
  pipx install git+https://github.com/izumacha/automation.git
  reminder
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
  - スヌーズ機能（1〜180分、最大10回まで）
  - リマインダーの設定解除に対応
  - 設定の自動保存・復元（`~/.config/reminder/settings.json`）
  - OS ネイティブテーマによるモダンな UI
  - `assets/reminder_icon.svg` をウィンドウアイコンとして表示（`cairosvg` が必要）

---

## セットアップ

```bash
pip install -r requirements.txt
```

デスクトップアプリとして使う場合は、上記インストール後に `./install_reminder_app.sh` を実行してください。

| パッケージ | 用途 |
|---|---|
| `cairosvg` | SVG アイコンの PNG 変換（ウィンドウアイコン表示） |

---

## リマインダーアプリをデスクトップアプリとして使う手順（Linux）

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

> 補足: ターミナルから `python -m reminder` で直接起動することもできます。

---

## 設定ファイル（自動保存）

設定は自動的に保存/復元されます。

- **Linux**: `~/.config/reminder/settings.json`
- **macOS / Windows**: アプリ内で利用するユーザーディレクトリ配下に保存します（詳細は `reminder/config.py` を参照）

### バックアップ

設定を退避したい場合は `settings.json` をコピーしてください。

```bash
cp ~/.config/reminder/settings.json ~/.config/reminder/settings.json.bak
```

### 互換性

将来キーが増えても、未知のキーは無視されるため、古い設定ファイルでも起動できる想定です。

---

## 配布（ワンクリック起動）案

GUI アプリとして「配布してダブルクリックで起動したい」場合は、`pyinstaller` を使う案があります。

- メリット: Python 未導入の環境でも配布しやすい
- デメリット: バイナリが大きくなる、OSごとにビルドが必要

例（macOS / Linux のイメージ）:

```bash
pip install pyinstaller
pyinstaller -F -w -n reminder reminder/__main__.py
```

> 将来的に GitHub Actions で各OS向けにビルドして Release に添付する運用も可能です。

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
- `schedule` — 空メッセージ時の警告・正常系のジョブ登録とボタン状態・設定保存
- `cancel_schedule` — ジョブなし時の無操作・アクティブジョブの解除
- `show_reminder` / `_schedule_snooze` — スヌーズ選択時の再スケジュール・スヌーズ拒否時のステータス更新・上限チェック
- `Settings` / `load_settings` / `save_settings` — 設定の永続化・読み込み・不明キーの無視

---

## ファイル構成

```
automation/
├── reminder/                       # リマインダーアプリ パッケージ
│   ├── __init__.py                 # パッケージ公開 API
│   ├── __main__.py                 # エントリーポイント (python -m reminder)
│   ├── app.py                      # ReminderApp GUI クラス
│   ├── config.py                   # 設定の永続化 (JSON)
│   ├── notifications.py            # 通知音・アイコン設定
│   └── time_utils.py               # 遅延時間計算・定数
├── install_reminder_app.sh         # Linux 向けデスクトップエントリ生成
├── requirements.txt
├── requirements-dev.txt            # 開発・テスト用依存
├── assets/
│   └── reminder_icon.svg           # リマインダーアプリ用アイコン
└── tests/
    ├── __init__.py
    ├── conftest.py                 # tkinter モック設定
    └── test_reminder.py
```
