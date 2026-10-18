"""日本語 -> Anima プロンプトパイプラインの CLI エントリポイント。

  # 日本語プロンプトを変換する:
  python run.py "茶髪の少女が教室の窓辺に立っている"

  # 一般辞書の外にあるキャラ / アーティストタグを注入する:
  python run.py --tags "fern,@kantoku" "二人の少女が公園のベンチに座っている"

  # サーバー URL を 1 回だけ指定する(保存はしない):
  python run.py --server http://192.168.1.10:8088 "茶髪の少女"

サーバーは Gemma だけを使う。接続先は --server > 保存済み設定(user_data/settings.json)
> config.CHAT_URL(既定 127.0.0.1:8088)の順で決まる。
起動方法は README.md を参照。
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from anima_pipeline import config


def cmd_run(ja_prompt: str, extra_tags: list[str], server: str | None = None) -> None:
    # 一般辞書が未作成のときは、長いトレースバックではなく短い案内を出す。
    if not config.ALIAS_MAP.exists():
        print(
            f"辞書が見つかりません: {config.ALIAS_MAP}\n"
            f"先に一般タグ辞書を作ってください(README の「辞書を作る」)。anima_pipeline/ の中で:\n"
            f"  python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv "
            f"--gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict",
            file=sys.stderr,
        )
        sys.exit(1)

    import requests
    from anima_pipeline import settings_store
    from anima_pipeline.pipeline import AnimaPipeline

    try:
        chat_url = (settings_store.normalize_chat_url(server) if server
                    else settings_store.get_chat_url())
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    try:
        pipe = AnimaPipeline()
        res = pipe.run(ja_prompt, extra_tags=extra_tags, chat_url=chat_url)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print(
            f"Gemma サーバーに接続できません({chat_url})。\n"
            f"別のターミナルで llama-server を起動してから、もう一度実行してください"
            f"(README の「サーバーの起動」を参照)。",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n--- English ---")
    print(res["english"])
    print("\n--- Anima prompt ---")
    print(res["prompt"])
    if res.get("negative"):
        print("\n--- Negative prompt ---")
        print(res["negative"])
    if res["issues"]:
        print("\n[!] validation issues: " + "; ".join(res["issues"]), file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Japanese -> Anima prompt pipeline "
                    "(translate -> generate -> dictionary snap-correction)")
    ap.add_argument("input", nargs="?", help="Japanese prompt to convert")
    ap.add_argument("--tags", default="",
                    help="comma-separated extra tags to inject (characters, "
                         "@artists) that are not in the general dictionary")
    ap.add_argument("--server", default=None,
                    help="Gemma(llama-server)の URL。例: http://127.0.0.1:8088 "
                         "(1 回限り。省略時は保存済み設定 > config.CHAT_URL)")
    args = ap.parse_args()

    if not args.input:
        ap.print_help()
        return

    extra = [t.strip() for t in args.tags.split(",") if t.strip()]
    cmd_run(args.input, extra_tags=extra, server=args.server)


if __name__ == "__main__":
    main()
