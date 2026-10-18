"""ComfyUI カスタムノード: 日本語プロンプト -> Anima 用プロンプト整形。

リポジトリルートの `__init__.py` から読み込まれる。ComfyUI はリポジトリを
`<パス由来名>` のパッケージとしてロードし sys.path には足さないため、
パッケージ内の import は必ず相対 import にすること(`import anima_pipeline` の
絶対 import を混ぜると config が二重化する)。
重い依存(ahocorasick / rapidfuzz を要求する service)は generate 内で遅延 import し、
未導入でもノード登録自体は成功させる。
"""
from __future__ import annotations

from pathlib import Path

from ..anima_pipeline import config, settings_store

_REPO_ROOT = Path(__file__).resolve().parent.parent


class AnimaPromptPipeline:
    CATEGORY = "AnimaPrompt"
    DESCRIPTION = (
        "日本語プロンプトを Gemma(llama-server)で英訳し、辞書で補正して "
        "Anima 用のプロンプトとネガティブプロンプトを出力します。"
    )
    FUNCTION = "generate"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("prompt", "negative", "english", "issues")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "ja_prompt": ("STRING", {"multiline": True, "default": "",
                                         "dynamicPrompts": False}),
                "extra_tags": ("STRING", {"default": ""}),
                "translate": ("BOOLEAN", {"default": config.TRANSLATE_FIRST}),
                "temperature": ("FLOAT", {"default": config.GEN_TEMPERATURE,
                                          "min": 0.0, "max": 1.0, "step": 0.05}),
                "max_tokens": ("INT", {"default": config.GEN_MAX_TOKENS,
                                       "min": 256, "max": 4096, "step": 128}),
                "fuzzy_cutoff": ("INT", {"default": config.SNAP_FUZZY_CUTOFF,
                                         "min": 50, "max": 100}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffff,
                                 "control_after_generate": True}),
            },
            "optional": {
                "server_url": ("STRING", {"default": ""}),
                "save_server_url": ("BOOLEAN", {"default": False}),
            },
        }

    def generate(self, ja_prompt, extra_tags, translate, temperature, max_tokens,
                 fuzzy_cutoff, seed, server_url="", save_server_url=False):
        if not (ja_prompt or "").strip():
            raise ValueError("日本語プロンプトを入力してください。")

        # 一般辞書が未作成のときは、長いトレースバックではなく短い案内を出す。
        if not config.ALIAS_MAP.exists():
            raise RuntimeError(
                f"辞書が見つかりません: {config.ALIAS_MAP}\n"
                f"先に一般タグ辞書を作ってください(README の「辞書を作る」)。anima_pipeline/ の中で:\n"
                f"  python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv "
                f"--gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict"
            )

        # server_url が空なら保存済み設定 > config.CHAT_URL を使う。
        server_url = (server_url or "").strip()
        if server_url:
            chat_url = settings_store.normalize_chat_url(server_url)   # 不正なら ValueError
            if save_server_url:
                settings_store.set_chat_url(chat_url)
        else:
            chat_url = settings_store.get_chat_url()

        try:
            from ..anima_pipeline import service
        except ImportError as e:
            raise RuntimeError(
                f"依存パッケージが不足しています({e})。ComfyUI の Python で "
                f"pip install -r {_REPO_ROOT / 'requirements.txt'} を実行してください。"
            ) from e

        import requests

        extra = [t.strip() for t in (extra_tags or "").split(",") if t.strip()]
        try:
            pipe = service.get_pipeline(fuzzy_cutoff)
            res = pipe.run(ja_prompt, extra_tags=extra, temperature=temperature,
                           max_tokens=max_tokens, translate=translate,
                           chat_url=chat_url, seed=seed)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            raise RuntimeError(
                f"Gemma サーバー ({chat_url}) に接続できません。"
                f"llama-server の起動と URL を確認してください。"
            ) from e
        except requests.exceptions.HTTPError as e:
            resp = e.response
            status = resp.status_code if resp is not None else "?"
            body = (resp.text[:200] if resp is not None else "")
            raise RuntimeError(
                f"Gemma サーバー ({chat_url}) がエラーを返しました: HTTP {status} {body}"
            ) from e

        issues = res.get("issues") or []
        issues_text = "; ".join(issues) if issues else "問題なし"
        prompt, negative, english = res["prompt"], res["negative"], res["english"]
        return {"ui": {"text": [prompt, negative, english]},
                "result": (prompt, negative, english, issues_text)}


NODE_CLASS_MAPPINGS = {"AnimaPromptPipeline": AnimaPromptPipeline}
NODE_DISPLAY_NAME_MAPPINGS = {"AnimaPromptPipeline": "Anima Prompt Pipeline (日本語→Anima)"}
