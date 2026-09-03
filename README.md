### 謝辞

このスクリプトを構築するにあたっては、Crodyさん ([Civitai Profile](https://civitai.com/user/Crody)) の知見をほぼそのまま参考にさせて頂いています。

# anima-prompt-pipeline

日本語で書いたプロンプトを、ローカルの **Gemma**（llama.cpp 経由）で英語に翻訳し、**Danbooru / Gelbooru 由来の辞書** と **Anima 用ルール** を使って、画像生成モデル **[Anima](https://huggingface.co/circlestone-labs/Anima)** が理解しやすいプロンプト（タグ列＋ネガティブプロンプト）へ整形するツールです。

> [!IMPORTANT]
> **画像生成そのものは本ツール単体では行いません。**
> 本ツールは「Anima 用に整えたプロンプト文字列・ネガティブプロンプト」を出力する前処理パイプラインです。画像生成は ComfyUI や Stable Diffusion WebUI Forge NEO などで行います。

---

## 3 つの利用形態

本プロジェクトは共通の変換パイプライン（`anima_pipeline`）をベースに、以下の **3 つの異なるインターフェース** を提供しています。用途や作業環境に合わせて選んで利用できます。

```
                    ┌─────────────────────────┐
                    │     ユーザーの日本語入力   │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
【1. CLI (CUI)】         【2. Web GUI】      【3. Forge NEO 拡張機能】
ターミナルから 1 行実行    ブラウザで手軽に変換      Forge NEO 画面内で変換
出力をコピーして使用       履歴保存・パラメータ調整  txt2img/img2img へ直接転送
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
               ┌─────────────────────────────────┐
               │    共通パイプライン & ローカル    │
               │  ・Gemma (llama-server :8088)   │
               │  ・Danbooru/Gelbooru 辞書補正   │
               └────────────────┬────────────────┘
                                ▼
               ┌─────────────────────────────────┐
               │    Anima 用プロンプト & ネガティブ │
               └────────────────┬────────────────┘
                                ▼
               ┌─────────────────────────────────┐
               │     ComfyUI / Forge NEO で生成   │
               └─────────────────────────────────┘
```

| 形態                  | 主な用途・特徴                                               | 起動方法 / エントリポイント                                                     |
| --------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| **1. CLI (CUI)**      | スクリプト連携、ターミナル作業、動作確認                     | `cd anima_pipeline && python run.py "プロンプト"`                               |
| **2. Web GUI**        | 単体起動の専用ブラウザUI、パラメータ調整、履歴保存/CSV       | `anima_pipeline/run_web.bat` または `python app_web.py` (http://127.0.0.1:7865) |
| **3. Forge NEO 拡張** | WebUI 完結、生成画面（txt2img / img2img）への 1 クリック転送 | Forge NEO の `extensions/` に配置・ジャンクション                               |

---

## 処理の流れ

日本語を入力すると、パイプライン内部で以下のステップが実行されます。

1. **翻訳**: 日本語プロンプトをローカルの Gemma で英語に翻訳します。
2. **タグ生成**: Gemma が Anima 用ルール（`prompts/anima_rules.txt`：品質→人数→キャラ→ポーズ→構図→背景→ライティングの順）に従いタグ列を出力します。
3. **スナップ補正**: 出力されたタグを辞書と照合し、実在タグへの寄せ（別名→正規形、綴り揺れの近似補正）を行います。
4. **固有名詞の自動注入**: 本文中のキャラ名・作品名・アーティスト名（`@` 付き）を辞書から完全一致検出し、キャラブロック先頭に差し込みます（任意・既定有効）。
5. **ネガティブプロンプト付与**: 推奨テンプレートを自動付与して出力します。

---

## 前提条件（事前に用意するもの）

本リポジトリには容量およびライセンスの観点から **モデルファイルや生データ CSV を同梱していません**。各自でご用意ください。

1. **Python 3.10 以上**
2. **llama.cpp (`llama-server`)**: [llama.cpp GitHub](https://github.com/ggml-org/llama.cpp)
3. **Gemma 4 Instruct モデル（GGUF 形式）**:
   - 推奨: 公式 Instruct GGUF（量子化 `Q4_K_M` など、例: `gemma-4-26B-A4B-it` や軽量な `E2B` 等）
   - ※ 翻訳とプロンプト整形をこのモデル 1 本で行います。
4. **タグ元データ CSV（2 種類）**:
   - 入手元: Hugging Face [HDiffusion (John Steward)](https://huggingface.co/HDiffusion)
   - Danbooru タグ数データ (`danbooru.csv`) および Gelbooru タグデータ (`gelbooru.csv`)
5. **画像生成環境**:
   - [ComfyUI](https://github.com/comfyanonymous/ComfyUI) または [SD WebUI Forge NEO](https://github.com/hirorohi03/EasyForgeNeo)
   - [Anima モデル一式](https://huggingface.co/circlestone-labs/Anima)（`anima-base-v1.0.safetensors`, `qwen_3_06b_base.safetensors`, `qwen_image_vae.safetensors`）

---

## 共通セットアップ（全形態で必須）

どの形態で利用する場合でも、**「タグ CSV の配置」「辞書ビルド」「Gemma サーバーの起動」** が前提となります。

### 1. 仮想環境の作成と依存インストール

本ツールの実依存は `anima_pipeline/requirements.txt` に記述されています。

```bash
# リポジトリルートで作業
python -m venv winvenv                  # Web GUI バッチを使う場合は winvenv を推奨
# 有効化 (Windows cmd: winvenv\Scripts\activate / PowerShell: .\winvenv\Scripts\Activate.ps1 / Linux: source venv/bin/activate)
winvenv\Scripts\activate
python -m pip install --upgrade pip
pip install -r anima_pipeline/requirements.txt
```

### 2. タグ CSV の配置

HDiffusion からダウンロードした CSV をリポジトリ内の `anima_pipeline/data/raw/` に配置します。

- `anima_pipeline/data/raw/danbooru.csv`
- `anima_pipeline/data/raw/gelbooru.csv`

詳細は [`anima_pipeline/data/raw/README.md`](anima_pipeline/data/raw/README.md) を参照してください。

### 3. 辞書のビルド

`anima_pipeline` ディレクトリ内で `build_anima_dictionary.py` を実行し、スナップ補正用の辞書を作成します。

```bash
cd anima_pipeline

# (a) 一般タグ辞書【必須】
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict

# (b) アーティスト辞書【任意: 作家名の自動検出用】
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 1 --min-count 50 --out-dir data/dict_artist

# (c) キャラクター/作品辞書【任意: キャラ・作品名の自動検出用】
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 3,4 --min-count 100 --out-dir data/dict_char
```

### 4. Gemma サーバー (llama-server) の起動

**別のターミナルを開き、サーバーを常駐させます。**
ポートは **`8088`**（`anima_pipeline/config.py` の既定値）を使用します。

```bash
llama-server -m /path/to/gemma-4-it.gguf --port 8088 -c 8192 -ngl 99 -ot "\.ffn_(up|down|gate)_exps\.=CPU" -fa on --jinja --reasoning-budget 0
```

> [!TIP]
>
> - `-ot "\.ffn_(up|down|gate)_exps\.=CPU"`: 巨大なエキスパート層をメインメモリ（RAM）へ逃がし、VRAM 不足（OOM）を防ぎます。
> - `--reasoning-budget 0`: Gemma が長文の思考過程（Reasoning）を出力して JSON が途切れるのを防ぎます。
> - Windows では `anima_pipeline/run_llm.bat` のモデルパスを書き換えて利用することも可能です。

---

## 各機能の使い方

### 1. CLI (コマンドライン) モード

ターミナルで手軽に変換したい場合に使用します。

```bash
cd anima_pipeline

# 基本実行（日本語プロンプトを指定）
python run.py "茶髪の少女が教室の窓辺に立っている"

# アーティストや辞書外のキャラタグを手動注入
python run.py --tags "fern,@kantoku" "公園のベンチに座る二人の少女"
```

**出力結果**:

- `English`: 翻訳後の英文
- `Anima prompt`: スナップ補正・整列済みの Anima 向けプロンプト
- `Negative prompt`: 推奨ネガティブプロンプト

これらをコピーして ComfyUI 等のプロンプト入力欄へ貼り付けて使用します。

---

### 2. Web GUI モード

ブラウザ上でパラメータを調整しながら変換・履歴管理を行いたい場合に使用します。

#### 起動方法

- **Windows バッチ**: `anima_pipeline/run_web.bat` を実行（エクスプローラーからダブルクリック、または `anima_pipeline/` 内で実行）
- **手動起動**:
  ```bash
  cd anima_pipeline
  python app_web.py
  ```
- 起動後、ブラウザで **http://127.0.0.1:7865** にアクセスします。

#### 主な特徴

- **ステータス表示**: 画面上部で辞書の読み込み状態や Gemma サーバー（:8088）との接続状態を確認可能。
- **パラメータ調整**: Temperature、Max Tokens、ファジー検索の閾値（Fuzzy Cutoff）をスライダーで変更可能。
- **履歴とインポート/エクスポート**: 過去の変換結果がブラウザに自動保存され、いつでも再呼び出し可能。CSV 形式での保存・読み込みにも対応。

---

### 3. SD WebUI Forge NEO 拡張機能モード

Stable Diffusion WebUI Forge NEO をお使いの場合、拡張機能として組み込むことで **WebUI 内部のタブで変換し、1クリックで txt2img / img2img に送信** できます。

#### インストール方法（ジャンクション推奨）

Forge NEO の `extensions/` フォルダへ本リポジトリをジャンクション（またはクローン）します。

```bat
:: 管理者権限のコマンドプロンプトで実行
mklink /J C:\path\to\sd-webui-forge-neo\extensions\anima-prompt-pipeline C:\path\to\anima-prompt-pipeline
```

#### 使い方

1. 前提として **辞書がビルド済み** であり、**Gemma サーバー（:8088）が起動中** であることを確認します。
2. Forge NEO を起動します（初回起動時に `install.py` が必要なライブラリ `pyahocorasick`, `rapidfuzz` を Forge 環境へ自動導入します）。
3. UI 上部に **「Anima Prompt」タブ** が追加されます。
4. 日本語を入力して「Anima プロンプトを生成」をクリックします。
5. 生成後、**「txt2img へ送信」** または **「img2img へ送信」** ボタンをクリックすると、各生成画面の Prompt / Negative Prompt 欄に自動入力され、画面が切り替わります。

---

## 設定のカスタマイズ

主要な設定は [`anima_pipeline/config.py`](anima_pipeline/config.py) に集約されています。

- `CHAT_URL`: Gemma サーバーのエンドポイント（既定: `http://127.0.0.1:8088`）
- `SNAP_FUZZY_CUTOFF`: ファジー照合の類似度しきい値（既定: `90`）
- `SNAP_MAX_WORDS`: スナップ補正の対象とする単語数の上限（既定: `4`）
- `USE_ARTIST_DICT` / `USE_CHAR_DICT`: 辞書による自動抽出の有効/無効
- `NEGATIVE_PROMPT`: 自動付与されるネガティブプロンプトのテンプレート

---

## ライセンスとクレジット

詳細は [`NOTICE.md`](NOTICE.md) を必ずご確認ください。

- **本リポジトリのコード**: MIT License ([`LICENSE`](LICENSE))
- **Anima モデル本体**: CircleStone Labs 非商用ライセンス（商用利用不可）
- **タグ辞書元データ**: [HDiffusion (John Steward)](https://huggingface.co/HDiffusion)
- **プロンプト構成ルール**: Civitai の **Crody** (Team-C) さんの知見・解説記事（[Articles #19107](https://civitai.com/articles/19107)）に基づき Anima 向けに調整

---

## 関連ドキュメント

- [BIGNNER.md](BIGNNER.md) — 初めての方向けの導入スタートガイド
- [INSTALL.md](INSTALL.md) — 詳細な環境構築・インストール手順書
- [NOTICE.md](NOTICE.md) — ライセンス・権利関係・免責事項
- [anima_pipeline/README.md](anima_pipeline/README.md) — パイプライン内部処理・アーキテクチャ詳細
- [anima_pipeline/prompts/README.md](anima_pipeline/prompts/README.md) — ルール定義プロンプトの調整ガイド
