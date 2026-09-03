"""Forge NEO 拡張機能としてロードされたときに1度だけ実行されるインストーラ。

パイプライン本体が使う `pyahocorasick`(import 名 `ahocorasick`)と `rapidfuzz` を
Forge の venv へインストールする。FastAPI 版 Web GUI や辞書ビルダー CLI が使う
fastapi/uvicorn/pandas/rank-bm25/numpy はここではインストールしない(拡張機能の
タブ機能には不要なため)。`requests` は Forge 本体が既に依存として持っている。

一方のインストールに失敗しても Forge の起動自体は止めたくないので、依存ごとに
try/except で囲み、失敗時はメッセージを出すだけにする。
"""
import launch

_DEPS = [("ahocorasick", "pyahocorasick"), ("rapidfuzz", "rapidfuzz")]

for import_name, pip_name in _DEPS:
    try:
        if not launch.is_installed(import_name):
            launch.run_pip(f"install {pip_name}", f"anima-prompt-pipeline: {pip_name}")
    except Exception as e:
        print(f"[anima-prompt-pipeline] Failed to install {pip_name}: {e}")
