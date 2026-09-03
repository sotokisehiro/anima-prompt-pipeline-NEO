# Anima Prompt Pipeline インストールガイド (INSTALL.md)

本ドキュメントでは、**Anima Prompt Pipeline** の導入手順を、以下の 3 つの利用形態に合わせて詳しく解説します。

1. **CUI (コマンドライン)** — ターミナルからスクリプトを実行してプロンプトを変換
2. **Web GUI (FastAPI / ブラウザ)** — ローカル Web サーバーを起動し、ブラウザ UI から変換・履歴管理
3. **SD WebUI 拡張機能 (Forge NEO)** — Stable Diffusion WebUI Forge NEO の「Anima Prompt」タブから直接変換して txt2img / img2img に送信

---

## 目次

1. [全体概要と処理の流れ](#全体概要と処理の流れ)
2. [事前に用意するもの（前提条件）](#事前に用意するもの前提条件)
3. [共通セットアップ（全形態で必須）](#共通セットアップ全形態で必須)
   - [Step 1: リポジトリの配置](#step-1-リポジトリの配置)
   - [Step 2: タグ CSV の入手と配置](#step-2-タグ-csv-の入手と配置)
   - [Step 3: 辞書データのビルド](#step-3-辞書データのビルド)
   - [Step 4: Gemma (llama-server) の起動](#step-4-gemma-llama-server-の起動)
4. [利用形態別のセットアップ＆起動手順](#利用形態別のセットアップ起動手順)
   - [A. CUI (コマンドライン) で使う場合](#a-cui-コマンドライン-で使う場合)
   - [B. Web GUI (ブラウザ) で使う場合](#b-web-gui-ブラウザ-で使う場合)
   - [C. SD WebUI (Forge NEO) 拡張機能として使う場合](#c-sd-webui-forge-neo-拡張機能として使う場合)
5. [画像生成へのプロンプト適用](#画像生成へのプロンプト適用)
6. [トラブルシューティング / よくある落とし穴](#トラブルシューティング--よくある落とし穴)
7. [関連ドキュメント](#関連ドキュメント)

---

## 全体概要と処理の流れ

Anima Prompt Pipeline は、日本語で入力したプロンプトを画像生成モデル [Anima](https://huggingface.co/circlestone-labs/Anima) が高精度に解釈できるタグ列（＋ネガティブプロンプト）へ変換するツールです。

- **行われる処理**:
  1. **翻訳**: 日本語プロンプトを Gemma (llama.cpp) で英語へ翻訳
  2. **タグ生成**: Anima の並び順ルール (`anima_rules.txt`) に従ってタグ列を生成
  3. **スナップ補正**: Danbooru / Gelbooru 由来の辞書と Aho-Corasick / RapidFuzz を用い、正規タグへの変換・綴り揺れ補正
  4. **固有名詞の注入**: プロンプト内のキャラクター名・作品名・アーティスト名（`@` 付き）を自動抽出して先頭付近へ挿入
  5. **ネガティブ出力**: 推奨ネガティブプロンプトを自動付与
- **注意（行われない処理）**:
  - **画像生成そのものは本ツール単体では行いません**。出力されたプロンプトを ComfyUI や Forge NEO などの画像生成環境に渡して生成します。

---

## 事前に用意するもの（前提条件）

本リポジトリには容量やライセンスの都合上、**モデル重みや生データ CSV は同梱されていません**。以下のものを各自で準備してください。

| 項目 | 説明・推奨バージョン | 入手先 / 補足 |
|---|---|---|
| **Python** | 3.10 以上 (3.10〜3.13) | [python.org](https://www.python.org/) |
| **llama.cpp** | `llama-server` バイナリ | [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases) から環境に合った最新版を取得 |
| **Gemma 4 GGUF** | チャット・翻訳・整形用 LLM<br>推奨: `gemma-4-26B-A4B-it` または軽量な E2B などの公式 Instruct GGUF (`Q4_K_M`) | Hugging Face などの各配布元から取得 |
| **タグ元データ CSV** | `danbooru.csv` および `gelbooru.csv` | Hugging Face [HDiffusion (John Steward)](https://huggingface.co/HDiffusion) より取得 |
| **画像生成環境** | ComfyUI または Forge NEO、および Anima モデル一式 | [Anima Model (Hugging Face)](https://huggingface.co/circlestone-labs/Anima)（非商用ライセンス） |

---

## 共通セットアップ（全形態で必須）

どの利用形態（CUI / GUI / 拡張機能）でも、**「タグ CSV の配置」「辞書ビルド」「Gemma サーバーの起動」** は共通して必要となります。

### Step 1: リポジトリの配置

リポジトリを任意の場所にクローンまたは展開します。

```bash
git clone https://github.com/sotokisehiro/anima-prompt-pipeline.git
cd anima-prompt-pipeline
```

---

### Step 2: タグ CSV の入手と配置

1. [HDiffusion (John Steward)](https://huggingface.co/HDiffusion) から以下の 2 つのデータセット（CSV）をダウンロードします。
   - Danbooru タグ数データ (`historical-danbooru-tag-counts` 系)
   - Gelbooru タグデータ (`gelbooru-tags` 系)
2. ダウンロードしたファイルを、以下のパス・ファイル名になるようにリポジトリ内の `anima_pipeline/data/raw/` フォルダへ配置します。
   - `anima_pipeline/data/raw/danbooru.csv`
   - `anima_pipeline/data/raw/gelbooru.csv`

---

### Step 3: 辞書データのビルド

生タグ CSV から、スナップ補正用の軽量な JSONL / JSON 辞書を作成します。

> **注意**: ビルド作業はリポジトリ内の `anima_pipeline` ディレクトリに移動して行います。
> 仮想環境（後述の手順で作る `venv` や `winvenv`）を有効化した状態で実行してください。

```bash
# anima_pipeline ディレクトリへ移動
cd anima_pipeline

# 1. 一般タグ辞書（必須: スナップ補正に必須）
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict

# 2. アーティスト辞書（任意: 本文中の作家名自動検出用）
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 1 --min-count 50 --out-dir data/dict_artist

# 3. キャラクター / 作品辞書（任意: 本文中のキャラ名・作品名自動検出用）
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 3,4 --min-count 100 --out-dir data/dict_char
```

ビルドが完了すると、各出力先フォルダ（`data/dict/` 等）に以下のファイルが生成されます。
- `alias_to_canonical.json` (別名から正規タグへのマッピング)
- `anima_tags.jsonl` (正規タグのデータベース)
- `vocab.txt`

---

### Step 4: Gemma (llama-server) の起動

Anima Prompt Pipeline は、翻訳とプロンプト生成をローカルの Gemma に問い合わせます。
**別のターミナルウィンドウを開き、llama-server を起動したままにしておきます。**

> **重要**:
> - 待受ポートは **`8088`** です（`anima_pipeline/config.py` の既定値）。
> - `-ot "\.ffn_(up|down|gate)_exps\.=CPU"` は巨大なエキスパート層を RAM に逃がす設定です。外すと VRAM 不足（Out of Memory）になります。
> - `--reasoning-budget 0` は思考文（Reasoning）の出力を抑え、プロンプト生成の JSON を即座に返すための必須指定です。

#### コマンド例（Windows コマンドプロンプト / PowerShell / Linux 共通）:

```bash
llama-server -m /path/to/your/gemma-4-it.gguf --port 8088 -c 8192 -ngl 99 -ot "\.ffn_(up|down|gate)_exps\.=CPU" -fa on --jinja --reasoning-budget 0
```

※ Windows で `anima_pipeline/run_llm.bat` を使用する場合は、バッチファイル内のモデルパス（`-m` の後ろ）をお手元の GGUF ファイル名またはフルパスに書き換えて実行してください。

コンソールに `server is listening on http://127.0.0.1:8088` と表示されれば準備完了です。このウィンドウは閉じずに開いたままにしておきます。

---

## 利用形態別のセットアップ＆起動手順

### A. CUI (コマンドライン) で使う場合

ターミナルから 1 行で素早くプロンプト変換を行いたい場合の手順です。

#### 1. 仮想環境の作成と依存ライブラリのインストール

リポジトリルート（`anima-prompt-pipeline/`）で実行します。

**Windows (コマンドプロンプト):**
```bat
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r anima_pipeline\requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r anima_pipeline\requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r anima_pipeline/requirements.txt
```

#### 2. コマンドの実行

仮想環境を有効化した状態で、`anima_pipeline` ディレクトリから実行します。

```bash
cd anima_pipeline

# 基本的な使い方 (日本語プロンプトを指定)
python run.py "教室の窓辺に立つ茶髪の少女、夕暮れの光"

# キャラクター名やアーティスト名を手動で指定する場合
python run.py --tags "fern,@kantoku" "本を読む少女"

# 翻訳を行わず、直接 Gemma に指示する場合
python run.py --no-translate "1girl, sitting on a bench, looking at viewer"
```

コンソールに「英訳」「Anima プロンプト」「ネガティブプロンプト」が出力されます。

---

### B. Web GUI (ブラウザ) で使う場合

直感的な Web 画面から入力・パラメータ調整・履歴管理を行いたい場合の手順です。FastAPI + Vanilla JS 製の軽量 Web GUI が付属しています。

#### 1. 仮想環境の作成

Windows 用起動バッチ `anima_pipeline/run_web.bat` は、リポジトリルート直下の **`winvenv`** という仮想環境名を自動参照する設計になっています。

リポジトリルート（`anima-prompt-pipeline/`）で以下を実行します。

**Windows:**
```bat
python -m venv winvenv
winvenv\Scripts\activate
python -m pip install --upgrade pip
pip install -r anima_pipeline\requirements.txt
```

#### 2. Web GUI の起動

**方法 1: バッチファイルから起動（Windows 推奨）**
1. エクスプローラー等で `anima_pipeline` フォルダを開きます。
2. `anima_pipeline/run_web.bat` をダブルクリック（またはカレントディレクトリを `anima_pipeline` にして実行）します。
3. 自動で依存チェックが行われ、ブラウザで `http://127.0.0.1:7865` が立ち上がります。

> **注意**: `run_web.bat` は必ず **`anima_pipeline` フォルダを作業ディレクトリとして実行** してください（リポジトリルートから叩くと `..\winvenv` の相対パスが狂います）。

**方法 2: コマンドラインから手動起動 (Windows / Linux 共通)**
```bash
# 仮想環境を有効化した状態で
cd anima_pipeline
python app_web.py
```
起動後、ブラウザで `http://127.0.0.1:7865` にアクセスしてください。

#### 3. Web GUI の主な機能
- **リアルタイムステータス表示**: 辞書ファイルのロード状態や Gemma サーバー（ポート 8088）との疎通を上部バッジで確認可能
- **パラメータ調整**: Temperature、Max Tokens、Fuzzy Cutoff（曖昧検索のしきい値）を GUI 上でスライダー調整可能
- **履歴機能**: 過去の変換履歴をブラウザの LocalStorage に保存（CSV 形式での一括エクスポート / インポートにも対応）

---

### C. SD WebUI (Forge NEO) 拡張機能として使う場合

画像生成 WebUI **Stable Diffusion WebUI Forge NEO** の画面内に専用タブ「Anima Prompt」を追加し、生成画面（txt2img / img2img）へ 1 クリックでプロンプトを転送できるようにする手順です。

> **対象環境**:
> - Stable Diffusion WebUI Forge NEO（Gradio 4 / Python 3.13 環境）
> ※ 従来の WebUI (Automatic1111) や Gradio 3 ベースの reForge とは仕様が異なります。

#### 1. 拡張機能のインストール（2 通りの方法）

**方法 A: ディレクトリジャンクションを作成する（推奨・開発向け）**
リポジトリの実体を複製せず、Forge NEO の `extensions` フォルダからリンクさせます。

管理者権限のコマンドプロンプトで実行:
```bat
mklink /J "C:\path\to\sd-webui-forge-neo\extensions\anima-prompt-pipeline" "C:\path\to\anima-prompt-pipeline"
```
（例: `mklink /J C:\aiwork\sd-webui-forge-neo\extensions\anima-prompt-pipeline C:\aiwork2\anima-prompt-pipeline`）

**方法 B: extensions フォルダ配下にクローンする**
```bash
cd /path/to/sd-webui-forge-neo/extensions
git clone https://github.com/sotokisehiro/anima-prompt-pipeline.git
```

#### 2. Forge NEO の起動と依存自動インストール

Forge NEO を通常通り起動します（`run.bat` 等）。

- 起動時に本拡張の `install.py` が自動的に走り、Forge NEO 側の Python 環境へ必要な最小限のライブラリ（`pyahocorasick`, `rapidfuzz`）をインストールします。
- 起動完了後、Forge NEO の Web 画面上部に **「Anima Prompt」** タブが表示されます。

#### 3. 拡張機能利用時の重要チェック事項

1. **Gemma サーバーの起動**:
   - Forge NEO とは別に、[Step 4](#step-4-gemma-llama-server-の起動) で説明した `llama-server`（ポート 8088）が立ち上がっている必要があります。
2. **辞書の存在**:
   - [Step 3](#step-3-辞書データのビルド) で生成した辞書ファイル（`anima_pipeline/data/dict/`）が存在している必要があります。
3. **txt2img / img2img への送信**:
   - 「Anima Prompt」タブでプロンプトを生成後、「txt2img へ送信」または「img2img へ送信」ボタンを押すと、メインの生成タブへプロンプトおよびネガティブプロンプトが自動反映され、タブが切り替わります。

---

## 画像生成へのプロンプト適用

本ツールが出力したプロンプトを各ツールへ適用する方法です。

### 1. ComfyUI で利用する場合
- 出力された **Anima 用プロンプト** を ComfyUI のポジティブプロンプト（CLIP Text Encode）に貼り付けます。
- 出力された **ネガティブプロンプト** をネガティブプロンプト側に貼り付けます。
- モデルには Anima 公式（`anima-base-v1.0.safetensors` 等）と Qwen テキストエンコーダ・VAE を設定して生成を実行します。

### 2. Forge NEO で利用する場合
- 「Anima Prompt」タブ内の **「txt2img へ送信」** を押すだけで、プロンプト入力欄に自動入力されます。
- チェックポイントに Anima モデルを指定して生成を実行してください。

---

## トラブルシューティング / よくある落とし穴

### Q1. 「Gemma サーバーに接続できません」「Connection refused」と表示される
- `anima_pipeline/config.py` のデフォルトポートは **`8088`** です。`llama-server` を起動する際のポートが `--port 8088` になっているか確認してください（一部古いドキュメントで 8080 と表記されている場合がありますが、`8088` が正です）。
- ターミナルで `llama-server` がエラーで終了していないか確認してください。

### Q2. Gemma 起動時に Out of Memory (VRAM不足) でクラッシュする
- 起動引数に `-ot "\.ffn_(up|down|gate)_exps\.=CPU"` が含まれているか確認してください。これをつけることで、重たいエキスパート層をメインメモリ（RAM）へ退避できます。
- VRAM 容量が極めて少ない場合、`-ngl 0` を指定して Gemma を完全に CPU 駆動にすることも可能です（画像生成側の VRAM を圧迫しません）。

### Q3. 出力結果に Gemma の思考文（箇条書きや `Thought:` 等）が混ざる・途中で切れる
- Gemma 4 が推論プロセスをそのまま出力してしまい、JSON 出力に達していない状態です。
- `llama-server` の起動オプションに必ず **`--reasoning-budget 0`** を付与してください。
- それでも思考が混入する場合は、追加引数として `--chat-template-kwargs "{\"enable_thinking\": false}"` を渡してください。

### Q4. Windows の PowerShell で `Activate.ps1` を実行するとエラーになる
- PowerShell のスクリプト実行ポリシーによる制限です。管理者権限または当該ターミナルセッションで以下を実行して許可してください。
  ```powershell
  Set-ExecutionPolicy -Scope Process RemoteSigned
  ```

### Q5. `run_web.bat` を実行するとモジュールが見つからない等のエラーが出る
- リポジトリのルートフォルダから実行していませんか？ `run_web.bat` は `anima_pipeline` ディレクトリ内で実行されることを前提に相対パス（`..\winvenv`）を解決します。`cd anima_pipeline` してから実行するか、エクスプローラーから `anima_pipeline` フォルダ内のバッチをダブルクリックしてください。
- 仮想環境のフォルダ名が `winvenv` 以外になっている場合は、`winvenv` という名前で作成し直すか、バッチ内のパスを編集してください。

### Q6. Forge NEO でジャンクションした際、JavaScript やスタイルが 403 Forbidden になる
- 本拡張の `scripts/anima_prompt_pipeline.py` にてジャンクション実パスを Gradio の許可パス (`cmd_opts.gradio_allowed_path`) に自動追加する対策が組み込まれています。拡張機能が最新の状態になっていることを確認してください。

---

## 関連ドキュメント

- [README.md](README.md) — プロジェクト全体の概要・背景・謝辞
- [BIGNNER.md](BIGNNER.md) — 初心者向けスタートガイド
- [NOTICE.md](NOTICE.md) — ライセンス情報とクレジット（Anima およびデータセットの権利関係）
- [anima_pipeline/README.md](anima_pipeline/README.md) — パイプラインの詳細仕様・アルゴリズム解説
- [anima_pipeline/prompts/README.md](anima_pipeline/prompts/README.md) — プロンプトルールとお手本の調整ガイド
