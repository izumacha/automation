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

### `browser_automation.py` — ブラウザ自動操作

Playwright を使ってポートフォリオサイトから GitHub プロフィールへ自動で移動するスクリプトです。

- **起動方法**

  ```bash
  python browser_automation.py
  ```

- **動作の流れ**
  1. `https://izumacha.github.io/profile-portfolio/` を開く
  2. ページ内の GitHub リンクを探してクリック（href → テキスト → アイコンの順に試行）
  3. `https://github.com/izumacha` への遷移を確認して終了

---

## セットアップ

```bash
pip install -r requirements.txt
```

`reminder.py` をデスクトップアプリとして使う場合は、上記インストール後に `./install_reminder_app.sh` を実行してください。

| パッケージ | 用途 |
|---|---|
| `playwright` | ブラウザ自動操作 |
| `cairosvg` | SVG アイコンの PNG 変換（`reminder.py` のウィンドウアイコン表示） |

Playwright のブラウザバイナリは初回のみ別途インストールが必要です。

```bash
playwright install chromium
```

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
   - **Set Reminder** を押す
   - 通知時刻になるとダイアログと通知音で知らせる

5. 設定を解除したい場合
   - アプリ上の **Clear Reminder** を押す

> 補足: `reminder.py` は、ターミナルから `python reminder.py` で直接起動することもできます。

---

## テスト

```bash
python -m unittest discover tests
```

`tests/test_reminder.py` では以下を検証しています。

- `calculate_delay_ms` — 同分・未来・翌日ロールオーバーの境界値
- `play_notification_sound` — 通知音の呼び出しと `TclError` の無視
- `_set_window_icon` — `cairosvg` がない環境でも例外が発生しないこと

---

## ファイル構成

```
automation/
├── reminder.py              # 時刻指定リマインダー GUI
├── browser_automation.py    # ブラウザ自動操作スクリプト
├── requirements.txt
├── assets/
│   └── reminder_icon.svg    # リマインダーアプリ用アイコン
└── tests/
    ├── __init__.py
    └── test_reminder.py
```
