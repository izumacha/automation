# automation

自動化ツールをまとめたリポジトリです。

## ツール一覧

### `reminder.py` — 時刻指定リマインダー

メッセージと通知時刻を設定するシンプルな GUI アプリです。

- **起動方法**

  ```bash
  python reminder.py
  ```

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

| パッケージ | 用途 |
|---|---|
| `playwright` | ブラウザ自動操作 |
| `cairosvg` | SVG アイコンの PNG 変換（`reminder.py` のウィンドウアイコン表示） |

Playwright のブラウザバイナリは初回のみ別途インストールが必要です。

```bash
playwright install chromium
```

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
