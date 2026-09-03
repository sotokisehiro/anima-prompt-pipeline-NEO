"""拡張機能・Web GUI などから共有される、キャッシュ付きパイプライン取得。

AnimaPipeline() の構築は辞書ロード + Aho-Corasick 自動オートマトン構築を伴い重いため、
fuzzy_cutoff が変わらない限り使い回す。他のパラメータ(temperature/max_tokens/translate)は
run() の引数として都度渡せるため、キャッシュキーには含めない。
"""
from __future__ import annotations
import threading

from . import config
from .pipeline import AnimaPipeline

_lock = threading.Lock()
_pipe: AnimaPipeline | None = None


def get_pipeline(fuzzy_cutoff: int | None = None) -> AnimaPipeline:
    global _pipe
    effective = fuzzy_cutoff if fuzzy_cutoff is not None else getattr(config, "SNAP_FUZZY_CUTOFF", 90)
    with _lock:
        if _pipe is None or _pipe.fuzzy_cutoff != effective:
            _pipe = AnimaPipeline(fuzzy_cutoff=effective)
        return _pipe
