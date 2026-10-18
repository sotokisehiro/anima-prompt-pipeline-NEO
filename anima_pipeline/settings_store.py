"""ユーザー設定(Gemma サーバー URL)のサーバーサイド永続化モジュール。

Web GUI / Forge NEO 拡張 / CLI の 3 つの入口で同じ設定を共有するため、
リポジトリルート直下の `user_data/settings.json` に保存する(gitignore 済み)。
標準ライブラリと `config` のみに依存する軽量モジュール。

接続先の優先順位: 呼び出しごとの明示指定 > 保存済み設定 > `config.CHAT_URL`(既定値)
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from . import config

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "user_data" / "settings.json"

_lock = threading.Lock()


def normalize_chat_url(raw: str) -> str:
    """URL を正規化する。スキーム省略時は http:// を補い、末尾の / と /v1 を落とす。

    不正な値なら ValueError(日本語メッセージ)。
    """
    url = (raw or "").strip()
    if not url:
        raise ValueError("サーバー URL を入力してください。")
    if "://" not in url:
        url = "http://" + url
    url = url.rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3].rstrip("/")
    try:
        parts = urlsplit(url)
        _ = parts.port  # 不正なポート番号はここで ValueError になる
    except ValueError:
        raise ValueError(f"サーバー URL の形式が正しくありません: {raw}")
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(
            f"サーバー URL は http:// または https:// で始まる形式で入力してください: {raw}"
        )
    return url


def _load() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def get_chat_url() -> str:
    """保存済みの URL を返す。無い・壊れている場合は config.CHAT_URL。"""
    with _lock:
        saved = _load().get("chat_url")
    if isinstance(saved, str) and saved.strip():
        try:
            return normalize_chat_url(saved)
        except ValueError:
            pass
    return config.CHAT_URL


def set_chat_url(raw: str | None) -> str:
    """URL を保存し、実際に使う URL を返す。空/None なら保存値を消して既定に戻す。"""
    text = (raw or "").strip()
    with _lock:
        data = _load()
        if not text:
            data.pop("chat_url", None)
        else:
            data["chat_url"] = normalize_chat_url(text)
        _save(data)
    return get_chat_url()
