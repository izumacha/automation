from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field

from .time_utils import DEFAULT_SNOOZE_MINUTES

_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "reminder")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "settings.json")


@dataclass
class Settings:
    """永続化するアプリ設定。"""

    message: str = ""
    hour: str = "00"
    minute: str = "00"
    snooze_minutes: str = field(default_factory=lambda: str(DEFAULT_SNOOZE_MINUTES))


def load_settings() -> Settings:
    """設定ファイルを読み込む。存在しない場合はデフォルト値を返す。"""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
    except Exception:
        logging.debug("設定ファイルの読み込みをスキップしました: %s", _CONFIG_PATH)
        return Settings()


def save_settings(settings: Settings) -> None:
    """設定ファイルに書き出す。"""
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning("設定ファイルの保存に失敗しました: %s", e)
