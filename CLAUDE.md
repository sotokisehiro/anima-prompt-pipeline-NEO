# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日本語で書いたプロンプトを、ローカルの Gemma(llama.cpp 経由)で英語に翻訳し、Danbooru/Gelbooru 由来の辞書と Anima 用ルールを使って、画像生成モデル [Anima](https://huggingface.co/circlestone-labs/Anima) 向けのプロンプトへ整形するツール。画像生成そのものは ComfyUI / Forge 側で行い、このツールが出すのは「整形済みのプロンプト文字列 + ネガティブプロンプト」のみ。

入口は3つ(いずれも同じ `anima_pipeline` パッケージを呼ぶ):

- CLI: `anima_pipeline/run.py`
- FastAPI Web GUI: `anima_pipeline/app_web.py` + `anima_pipeline/web/`
- Stable Diffusion WebUI **Forge NEO** 拡張: リポジトリルートを `extensions/` にジャンクションし、`scripts/anima_prompt_pipeline.py` が「Anima Prompt」タブを追加

- `main` ブランチ: CLI 版のみ
- `gui_dev` ブランチ(現在の作業ブランチ): Web GUI + Forge 拡張

ライセンス上の注意(`NOTICE.md` 参照): このリポジトリのコードは MIT だが、Anima 本体は非商用ライセンス、タグ CSV は HDiffusion 由来で本リポジトリには同梱していない。Gemma は公式 instruct を推奨(`NOTICE.md`)。`run_llm.bat` の Huihui/abliterated ファイル名は手順の手本にしない。

初心者向けのインストール正本は `BIGNNER.md`(ファイル名はユーザー指定。`BEGINNER.md` ではない)。範囲は機能概要+インストールのみ。

## よく使うコマンド

```bash
# LLM サーバー起動(別ターミナルで起動したままにする。ポート 8088)
anima_pipeline\run_llm.bat

# Web GUI 起動(依存インストール → uvicorn 起動 → http://127.0.0.1:7865 を自動オープン)
# カレントは anima_pipeline/ であること(Explorer のダブルクリックなら bat の場所が cwd になる)
anima_pipeline\run_web.bat

# CLI 実行
cd anima_pipeline
python run.py "茶髪の少女が教室の窓辺に立っている"
python run.py --tags "fern,@kantoku" "本を読む少女"   # 一般辞書に無いキャラ/アーティストを手動注入

# 辞書ビルド(anima_pipeline/ 内で実行。一般・アーティスト・キャラの3種を別々に作る)
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 1 --min-count 50 --out-dir data/dict_artist
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 3,4 --min-count 100 --out-dir data/dict_char

# Forge NEO へジャンクション(管理者 cmd。開発用)
mklink /J C:\aiwork\sd-webui-forge-neo\extensions\anima-prompt-pipeline C:\aiwork2\anima-prompt-pipeline
```

- Windows の venv はリポジトリルートの `winvenv\`(git 管理外)。`run_web.bat` はこの venv の pip/python を直接呼ぶ(`..\winvenv\Scripts\pip.exe` / `python.exe`)。PowerShell では `Activate.ps1`(実行ポリシーで落ちやすい)
- 実依存は `anima_pipeline/requirements.txt`(numpy, requests, pyahocorasick, rapidfuzz, rank-bm25, pandas, fastapi, uvicorn)。ルート直下の `requirements.txt` は `requests` のみの最小構成。Forge の `install.py` は `pyahocorasick`/`rapidfuzz` だけ入れる
- テスト・リンタ・CI は存在しない。Forge 拡張の送信 JS はジャンクション時に `javascript/` の realpath を `gradio_allowed_path` へ足さないと `/file=` が 403 になる

## アーキテクチャ

```
anima_pipeline/          # パイプライン本体パッケージ
  pipeline.py            # AnimaPipeline.run() — 6段階の中心
  generate.py            # ChatClient(llama-server /v1/chat/completions)
  postprocess.py         # Normalizer(スナップ補正)
  constrain.py           # render / validate
  config.py              # 全設定。パスはこのファイルからの相対解決。.env 無し
  service.py             # スレッドセーフな AnimaPipeline キャッシュ(キーは fuzzy_cutoff)
  history_store.py       # Forge 用サーバー側履歴(user_data/history.json) + CSV 互換
  app_web.py / run.py    # Web / CLI エントリ(sys.path シム + 絶対 import)
  web/                   # FastAPI が配信する vanilla JS GUI
  data/dict*/            # ビルド済み辞書(パイプラインが読むのは alias_to_canonical.json と anima_tags.jsonl)
  data/raw/              # danbooru.csv / gelbooru.csv(同梱しない)
  prompts/               # anima_rules.txt / fewshot.txt
build_anima_dictionary.py
install.py               # Forge 起動時: pyahocorasick / rapidfuzz のみ
scripts/anima_prompt_pipeline.py   # Forge タブ本体(Gradio 4)
javascript/anima_prompt_pipeline.js  # txt2img/img2img へ送信(elem_id + DOM onclick、updateInput 必須)
user_data/               # サーバー側履歴。gitignore
```

処理の中心は `anima_pipeline/pipeline.py` の `AnimaPipeline.run(ja_prompt, extra_tags=..., *, temperature, max_tokens, translate)`。日本語プロンプト1本を受け取り、以下の6段階を経て結果 dict(`english` / `prompt` / `negative` / `issues` など)を返す。リクエスト単位のパラメータは `config` を書き換えず、この引数で渡す。

1. **翻訳** — `generate.py::ChatClient.translate_ja_en`(`translate=False` または `TRANSLATE_FIRST=False` なら日本語のまま次へ)
2. **生成** — `ChatClient.chat` が Gemma に問い合わせる。system プロンプトは `prompts/anima_rules.txt`(タグの並び順ルール。品質→人数→キャラブロック→ポーズ→カメラ→背景→ライティング)+ コード側で付加する JSON 出力指示。`prompts/fewshot.txt` の few-shot 例も user/assistant ペアとして messages に混ぜる。Gemma の出力は `{"tags": [...], "natural": "..."}` の JSON を期待するが、思考文混入やコードフェンス等に備えて `pipeline.py::_loads_json_obj` が複数の抽出方法にフォールバックする。`content` が空なら `reasoning_content` を拾う
3. **スナップ補正** — `postprocess.py::Normalizer` を使う `pipeline.py::AnimaPipeline._snap`。各タグ(カンマ区切りの1要素)について: `@artist` / `(tag:1.3)` のような重み付き / `score_N` はそのまま素通し。それ以外は Aho-Corasick による別名→正規タグの完全一致を試み、無ければ rapidfuzz のファジー一致(閾値 `config.SNAP_FUZZY_CUTOFF`、既定90)で寄せる。寄せ先が無ければ原形を残す(削除しない)。`SNAP_MAX_WORDS`(既定4語)を超える要素は「説明句」とみなしスナップ対象外のまま残す
4. **検出名の注入** — 英訳文(または `--tags` 手動指定)からキャラ/作品名(`dict_char`)とアーティスト名(`dict_artist`、正規タグへ `@` を付与)を完全一致検出し、`_inject_head` で `config.STATIC_TAGS`(品質/メタ/レーティング/人数タグの集合)の直後、つまりキャラブロックの先頭へ差し込む。一般辞書の語と衝突する検出や、`*_MIN_SURFACE_LEN` 未満の短い表層は誤検出として除外する
5. **整形・検証** — `constrain.py::render`(タグを並べ替えずに文字列化)と `constrain.py::validate`(二重スペースなど機械的なチェックのみ)
6. **ネガティブ付与** — `config.NEGATIVE_PROMPT` の固定テンプレートを結果に添える

**LLM サーバーは llama-server 1本のみ**。OpenAI 互換の `/v1/chat/completions` を `config.CHAT_URL` 経由で叩く。README / `anima_pipeline/README.md` / `run.py` docstring には `:8080` と書かれているが、実際の `config.py` および `run_llm.bat`/`run_llm_E2B.bat` は **ポート8088**。新しく手を加える際は `config.py` 側を正とし、README の `:8080` を写さない。

**import 規約**: パッケージ内部(`pipeline.py` など)は相対 import。エントリ(`run.py` / `app_web.py` / Forge の `scripts/`)はリポジトリルートを `sys.path` に入れるシム + `from anima_pipeline import ...`。`__init__.py` はサブモジュールを import しない(軽量)。

**Web GUI**(`anima_pipeline/app_web.py`): FastAPI + uvicorn(:7865)。`GET /api/status` は辞書ファイルの有無と Gemma の `/v1/models` 疎通を返す。`POST /api/generate` は `service.get_pipeline(fuzzy_cutoff)` + `pipe.run(..., temperature, max_tokens, translate)`。静的ファイルは `web/`(vanilla JS)。履歴は **ブラウザ localStorage**(キー `anima_prompt_history`)と CSV インポート/エクスポート(BOM 付き UTF-8、列: Name, Datetime, JaPrompt, ExtraTags, English, Anima, Negative, Temperature, MaxTokens, FuzzyCutoff, TranslateFirst)。

**Forge NEO 拡張**: 本リポジトリ自体を拡張化する(別コピーしない)。`install.py` は起動時に `pyahocorasick`/`rapidfuzz` だけ入れる(失敗しても Forge 起動は止めない)。タブ構築時は重い `service`/`pipeline` を import せず、生成ボタンのハンドラ内まで遅延させる。履歴は `history_store.py` が `user_data/history.json` に保存し、上記 CSV 列と相互運用する。送信は `javascript/anima_prompt_pipeline.js` がボタン `elem_id` に DOM `onclick` を付け、ソース textarea を自分で読んで `updateInput` + `switch_to_*` する。ジャンクション時は `on_before_ui` が `javascript/` の realpath を `cmd_opts.gradio_allowed_path` に足す(Gradio 4 がジャンクションを resolve して `/file=` が 403 になるのを防ぐ)。対象は Forge NEO(`C:\aiwork\sd-webui-forge-neo`、Gradio 4 / Python 3.13)。同居の reForge は Gradio 3 / Python 3.10 で別物。

**パイプラインキャッシュ**(`service.py`): `AnimaPipeline()` は辞書ロード + Aho-Corasick 構築が重い。`fuzzy_cutoff` が変わらない限り使い回す。比較は `None` を `config.SNAP_FUZZY_CUTOFF` に解決してから行う(未解決のまま比較すると常にキャッシュミスする)。temperature / max_tokens / translate はキャッシュキーに含めない。`ChatClient.chat` のこれらのデフォルトも **呼び出し時**に `config` から解決する(import 時固定はしない)。

**設定はすべて `anima_pipeline/config.py` に集約**。主な項目: `CHAT_URL`、`TRANSLATE_FIRST`(既定 True)、`USE_FEWSHOT`、`USE_ARTIST_DICT`/`USE_CHAR_DICT`(辞書ファイルが無ければ自動的に無効)、`GEN_TEMPERATURE`/`GEN_MAX_TOKENS`、`SNAP_MAX_WORDS`/`SNAP_FUZZY_CUTOFF`、`NEGATIVE_PROMPT`、`STATIC_TAGS`。

`build_anima_dictionary.py`(ルート直下)は Danbooru/Gelbooru の生 CSV(列: `tag_string`, `category_int64`, `count_int64`, `alias_string`)からカテゴリ/出現数でフィルタし、Gelbooru を優先して統合、`anima_tags.jsonl` / `alias_to_canonical.json` / `vocab.txt` を `anima_pipeline/data/dict*` へ出力する独立 CLI。辞書パスはルートの `/data/` ではない。一般辞書は必須、artist/char は任意。

## 注意点

- `anima_pipeline/*.gguf`(最大7.4GB)と `anima_pipeline/data/raw/*.csv`、`user_data/` は gitignore。コミットに含めない
- `run_llm.bat` の `-m` はファイル名だけ。GGUF は `anima_pipeline/` に置くかフルパスにする
- `run_web.bat` をリポジトリルートから実行すると `..\winvenv` がリポジトリ外を見る
- コメント・README・docstring はほぼ全て日本語。ドキュメントや説明も日本語で書くのが自然
- プラン作成は Fable、コード作成・テストは sonnet5(ユーザー全体ルール)
