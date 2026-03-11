# CLAUDE.md — Claude Code 向けプロジェクト情報

このファイルは Claude Code が参照するプロジェクト固有のガイドラインです。

## プロジェクト概要

Python 製の自動化ツールをまとめたリポジトリです。現在は GUI リマインダーアプリ (`reminder.py`) が含まれています。

## 言語・スタイル

- Python 3.x
- コメント・変数名は **日本語または英語** どちらでも可
- インデント: スペース 4 つ
- 既存コードのスタイルに合わせること

## テスト

```bash
python -m pytest tests
```

- テストフレームワーク: `pytest`
- テストファイルは `tests/` ディレクトリに配置
- テストは必ず通過させること

## 依存パッケージ

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 開発・テスト用
```

## 主要ファイル

| ファイル | 説明 |
|---|---|
| `reminder.py` | 時刻指定リマインダー GUI（tkinter） |
| `install_reminder_app.sh` | Linux デスクトップエントリ生成スクリプト |
| `tests/test_reminder.py` | ユニットテスト |
| `assets/reminder_icon.svg` | アプリアイコン |

## PR・実装ガイドライン

- 変更前にテストが通ることを確認
- GUI に関わる変更は tkinter との互換性を維持
- 新機能追加時は対応するテストも追加
- コミットメッセージは変更内容を明確に記述
