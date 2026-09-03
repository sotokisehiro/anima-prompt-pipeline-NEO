"""Stable Diffusion WebUI Forge NEO 拡張機能としてのエントリーポイント。

`anima_pipeline/` パッケージ(日本語 -> Anima プロンプト変換パイプライン)を、
Forge NEO の UI タブとして呼び出せるようにする。処理の本体はすべて
`anima_pipeline` パッケージ側にあり、ここでは Gradio の画面組み立てと
イベント配線のみを行う。

依存(`pyahocorasick` / `rapidfuzz`)のインストールは `install.py` が Forge 起動時に
1 度だけ行う。ここではそれらに依存する `anima_pipeline.service` / `pipeline` の
import を、タブ描画時ではなく生成ボタンのハンドラ内まで遅延させる。これにより、
万一インストールに失敗していても、タブ自体は表示され、生成時にのみ分かりやすい
エラーを出せるようにしている。
"""
import os
import sys

# 拡張機能ローダーがルートを sys.path に入れない万一のケースに備えた保険
# (通常は Forge がリポジトリルートを自動で追加するため、多くの場合は素通りする)。
_EXT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)

import gradio as gr
import requests

from modules import script_callbacks

from anima_pipeline import config
from anima_pipeline.history_store import HistoryStore

# 履歴ストアは標準ライブラリのみで完結する軽量オブジェクトなので、モジュール読み込み時
# (= Forge 起動時)に構築してしまって問題ない。
_history = HistoryStore()


def _allow_javascript_dir():
    """ジャンクション先が Forge 配外に resolve されると `/file=` が 403 になる。"""
    js_dir = os.path.realpath(os.path.join(_EXT_ROOT, "javascript"))
    if not os.path.isdir(js_dir):
        return
    from modules.shared_cmd_options import cmd_opts
    paths = cmd_opts.gradio_allowed_path
    if not isinstance(paths, list):
        return
    normalized = os.path.normcase(js_dir)
    if any(os.path.normcase(os.path.realpath(p)) == normalized for p in paths):
        return
    paths.append(js_dir)


def _history_choices() -> list[tuple[str, str]]:
    """履歴ドロップダウンの choices を組み立てる。表示ラベルは「名前 (日時)」。"""
    return [
        (f"{item.get('name', '')} ({item.get('datetime', '')})", item.get("id"))
        for item in _history.list()
    ]


def _status_text(check_server: bool) -> str:
    """辞書 / Gemma サーバーの状態を表す短い Markdown を返す。

    `check_server` が False のときはネットワーク I/O を一切行わない
    (Blocks 組み立て時に呼んでもブロックしないようにするため)。
    """
    dict_ok = config.ALIAS_MAP.exists()
    dict_line = "✅ 辞書: 読み込み可能" if dict_ok else "❌ 辞書: 見つかりません(README の手順で作成してください)"

    if check_server:
        try:
            res = requests.get(f"{config.CHAT_URL}/v1/models", timeout=1.0)
            server_ok = res.ok
        except Exception:
            server_ok = False
        if server_ok:
            server_line = f"✅ Gemma サーバー ({config.CHAT_URL}): 接続OK"
        else:
            server_line = f"❌ Gemma サーバー ({config.CHAT_URL}): 接続できません(llama-server を起動してください)"
    else:
        server_line = f"⏳ Gemma サーバー ({config.CHAT_URL}): 未確認"

    return f"{dict_line}  \n{server_line}"


def _generate(ja, tags_str, temp, max_tok, cutoff, translate):
    """生成ボタンのハンドラ。日本語プロンプト -> Anima プロンプトへ変換する。"""
    ja = (ja or "").strip()
    if not ja:
        raise gr.Error("日本語プロンプトを入力してください。")
    if not config.ALIAS_MAP.exists():
        raise gr.Error("辞書ファイルが見つかりません。README の手順で辞書を作成してください。")

    try:
        from anima_pipeline import service
    except ImportError as e:
        raise gr.Error(f"依存パッケージが不足しています: {e}")

    extra = [t.strip() for t in (tags_str or "").split(",") if t.strip()]
    try:
        pipe = service.get_pipeline(int(cutoff))
        res = pipe.run(
            ja,
            extra_tags=extra,
            temperature=float(temp),
            max_tokens=int(max_tok),
            translate=bool(translate),
        )
    except requests.exceptions.RequestException:
        raise gr.Error(f"Gemma サーバー ({config.CHAT_URL}) に接続できません。llama-server を起動してください。")

    issues = res.get("issues") or []
    issues_text = "; ".join(issues) if issues else "問題なし"
    return res["english"], res["prompt"], res["negative"], issues_text


def _save_history(name, ja, tags_str, english, anima, negative, issues_text,
                   temp, max_tok, cutoff, translate):
    """現在の入出力内容を1件、履歴として保存する。"""
    ja = ja or ""
    name = (name or "").strip() or ja[:15].strip() or "無題のプロンプト"
    if issues_text and issues_text != "問題なし":
        issues_list = [s.strip() for s in issues_text.split(";") if s.strip()]
    else:
        issues_list = []
    _history.add(
        name=name,
        ja_prompt=ja,
        extra_tags=tags_str or "",
        english=english or "",
        anima=anima or "",
        negative=negative or "",
        issues=issues_list,
        settings={
            "temperature": float(temp),
            "maxTokens": int(max_tok),
            "fuzzyCutoff": int(cutoff),
            "translateFirst": bool(translate),
        },
    )
    return gr.update(choices=_history_choices())


def _load_history(item_id):
    """選択した履歴を各入出力欄・設定へ復元する。"""
    if not item_id:
        raise gr.Error("履歴を選択してください。")
    item = _history.get(item_id)
    if not item:
        raise gr.Error("選択した履歴が見つかりません。")

    settings = item.get("settings") or {}

    def _upd(key):
        # 旧形式などで欠けている項目があっても落ちないよう、no-op の gr.update() にする。
        if key in settings and settings[key] is not None:
            return gr.update(value=settings[key])
        return gr.update()

    return (
        item.get("jaPrompt", ""),
        item.get("extraTags", ""),
        item.get("english", ""),
        item.get("anima", ""),
        item.get("negative", ""),
        _upd("temperature"),
        _upd("maxTokens"),
        _upd("fuzzyCutoff"),
        _upd("translateFirst"),
    )


def _delete_history(item_id):
    """選択した履歴を削除する。"""
    if not item_id:
        raise gr.Error("履歴を選択してください。")
    _history.delete(item_id)
    return gr.update(choices=_history_choices(), value=None)


def _export_history():
    """全履歴を CSV へエクスポートし、ダウンロード用の File コンポーネントを表示する。"""
    path = _history.export_csv()
    return gr.update(value=str(path), visible=True)


def _import_history(file_path):
    """アップロードされた CSV を履歴へ取り込む。"""
    if not file_path:
        raise gr.Error("CSVファイルを選択してください。")
    try:
        count = _history.import_csv(file_path)
    except ValueError as e:
        raise gr.Error(str(e))
    if count == 0:
        raise gr.Error("インポート可能なデータがありませんでした。")
    return gr.update(choices=_history_choices())


def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as anima_tab:
        gr.Markdown("## Anima Prompt Pipeline")

        with gr.Row():
            with gr.Column(scale=1):
                ja_prompt = gr.Textbox(
                    label="日本語プロンプト", lines=4,
                    placeholder="例: 茶髪の少女が教室の窓辺に立っている",
                )
                extra_tags = gr.Textbox(
                    label="追加タグ(手動指定・カンマ区切り)",
                    placeholder="fern,@kantoku",
                )
                with gr.Accordion("詳細設定", open=False):
                    temperature = gr.Slider(
                        0.0, 1.0, value=config.GEN_TEMPERATURE, step=0.05,
                        label="Temperature(生成度合い)",
                    )
                    max_tokens = gr.Slider(
                        256, 4096, value=config.GEN_MAX_TOKENS, step=128,
                        label="Max New Tokens",
                    )
                    fuzzy_cutoff = gr.Slider(
                        50, 100, value=config.SNAP_FUZZY_CUTOFF, step=1,
                        label="Fuzzy Snap Cutoff(スナップ類似閾値)",
                    )
                    translate_first = gr.Checkbox(
                        value=config.TRANSLATE_FIRST,
                        label="翻訳ファースト(JP → EN)",
                    )
                generate_btn = gr.Button("生成", variant="primary")
                status_md = gr.Markdown(_status_text(False))
                refresh_btn = gr.Button("状態を再確認", size="sm")

            with gr.Column(scale=1):
                english_out = gr.Textbox(
                    label="英訳", interactive=False, show_copy_button=True, lines=3,
                )
                prompt_out = gr.Textbox(
                    label="Anima プロンプト", interactive=False, show_copy_button=True, lines=6,
                    elem_id="anima_prompt_out",
                )
                negative_out = gr.Textbox(
                    label="ネガティブプロンプト", interactive=False, show_copy_button=True, lines=3,
                    elem_id="anima_negative_out",
                )
                issues_out = gr.Textbox(label="検証結果", interactive=False)
                with gr.Row():
                    send_t2i = gr.Button("txt2img へ送る", elem_id="anima_send_txt2img")
                    send_i2i = gr.Button("img2img へ送る", elem_id="anima_send_img2img")

        with gr.Accordion("履歴", open=False):
            with gr.Row():
                save_name = gr.Textbox(label="保存名", placeholder="例: キャラ設定A")
                save_btn = gr.Button("保存")
            hist_dropdown = gr.Dropdown(
                label="保存済み履歴", choices=_history_choices(), value=None,
            )
            with gr.Row():
                load_btn = gr.Button("ロード")
                delete_btn = gr.Button("削除")
            with gr.Row():
                export_btn = gr.Button("CSVエクスポート")
                export_file = gr.File(label="エクスポートしたCSV", visible=False)
            import_btn = gr.UploadButton("CSVインポート", file_types=[".csv"])

        # -- イベント配線 -----------------------------------------------------
        anima_tab.load(fn=lambda: _status_text(True), outputs=[status_md])
        refresh_btn.click(fn=lambda: _status_text(True), outputs=[status_md])

        generate_btn.click(
            fn=_generate,
            inputs=[ja_prompt, extra_tags, temperature, max_tokens, fuzzy_cutoff, translate_first],
            outputs=[english_out, prompt_out, negative_out, issues_out],
        )

        send_t2i.click(fn=None, _js="() => {}")
        send_i2i.click(fn=None, _js="() => {}")

        save_btn.click(
            fn=_save_history,
            inputs=[save_name, ja_prompt, extra_tags, english_out, prompt_out, negative_out,
                    issues_out, temperature, max_tokens, fuzzy_cutoff, translate_first],
            outputs=[hist_dropdown],
        )
        load_btn.click(
            fn=_load_history,
            inputs=[hist_dropdown],
            outputs=[ja_prompt, extra_tags, english_out, prompt_out, negative_out,
                     temperature, max_tokens, fuzzy_cutoff, translate_first],
        )
        delete_btn.click(fn=_delete_history, inputs=[hist_dropdown], outputs=[hist_dropdown])
        export_btn.click(fn=_export_history, outputs=[export_file])
        import_btn.upload(fn=_import_history, inputs=[import_btn], outputs=[hist_dropdown])

    return [(anima_tab, "Anima Prompt", "anima_prompt_pipeline_tab")]


script_callbacks.on_before_ui(_allow_javascript_dir)
script_callbacks.on_ui_tabs(on_ui_tabs)
