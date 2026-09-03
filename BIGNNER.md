# ビギナー向けガイド (BIGNNER.md)

この文書は、**Anima Prompt Pipeline** を初めて使う人向けのかんたんスタートガイドです。
専門用語をなるべく省き、「**何ができるのか**」と「**最短で動かすまでの手順**」に絞って説明しています。

> [!NOTE]
> より詳しい技術仕様やカスタマイズ方法、各種設定については [`README.md`](README.md) や [`INSTALL.md`](INSTALL.md) を参照してください。

---

## 1. このツールは何をするもの？

### できること
日本語で思いついたシチュエーションやキャラクターの説明を入力すると、画像生成モデル **[Anima](https://huggingface.co/circlestone-labs/Anima)** に最適な「英語のタグ列（プロンプト）」と「ネガティブプロンプト」を自動で作ってくれます。

- 翻訳とタグの組み立てには、自分の PC で動かす言語モデル **Gemma**（llama.cpp）を使います。
- タグのスペルミスや表記揺れは、Danbooru / Gelbooru 由来の膨大な辞書データを使って実在する正確なタグへと自動で修正（スナップ補正）します。

### できないこと（重要！）
**このツール自体は画像を出力しません。**
本ツールが出力したプロンプトを、画像生成ソフト（ComfyUI や Forge NEO など）に貼り付けて画像を生成します。

---

## 2. 選べる 3 つの使い方（インターフェース）

本ツールには、同じ変換処理を使う 3 つの入り口があります。自分のスタイルに合わせて選んでください。

```
┌──────────────────────────────────────────────────────────────────┐
│                   日本語プロンプトを入力                         │
└─────────────────────────────────┬────────────────────────────────┘
                                  │
      ┌───────────────────────────┼───────────────────────────┐
      ▼                           ▼                           ▼
【 1. CLI (コマンド) 】      【 2. Web GUI 】      【 3. Forge NEO 拡張 】
黒い画面（ターミナル）から   専用のブラウザ画面で       いつも使っている
コマンド 1 行で変換         スライダー調整＆履歴管理    Forge NEO 画面内で完結
                            (http://127.0.0.1:7865)    (txt2img へ 1 クリック送信)
```

| 使い方 | おすすめな人 | 起動方法の目安 |
|---|---|---|
| **1. CLI (CUI)** | コマンドライン操作に慣れている方、スクリプトから自動で呼び出したい方 | ターミナルで `python run.py "日本語"` |
| **2. Web GUI** | コマンドを打たずにブラウザ画面でパラメータ調整や履歴管理を行いたい方 | `anima_pipeline/run_web.bat` を起動 |
| **3. Forge NEO 拡張** | 日常的に Forge NEO で画像生成をしており、タブを行き来せず直接プロンプトを流し込みたい方 | Forge NEO の `extensions` に配置して起動 |

---

## 3. 動かすまでに必要なもの

このリポジトリのプログラムだけでは動きません。以下のものをあらかじめ準備してください（ライセンスや容量の都合上、同梱していません）。

1. **Python 3.10 以降**
2. **llama.cpp (`llama-server`)**:
   - 言語モデルをローカルで動かすための軽量な実行プログラムです。
   - [llama.cpp 公式 Releases](https://github.com/ggml-org/llama.cpp/releases) から Windows 用の zip をダウンロードして展開しておきます。
3. **Gemma 4 Instruct のモデルファイル (GGUF)**:
   - 例: `gemma-4-26B-A4B-it` や、軽快に動く `Huihui-gemma-4-E2B-it` などの Instruct 版 GGUF（量子化は `Q4_K_M` 等がおすすめ）。
4. **タグデータの CSV（2 種類）**:
   - 辞書を作るための元データです。
   - [HDiffusion (John Steward)](https://huggingface.co/HDiffusion) から `danbooru.csv` と `gelbooru.csv` を入手します。

---

## 4. 全体共通のセットアップ（最初に 1 回だけ行う）

どの使い方（CUI / Web GUI / 拡張機能）を選ぶ場合でも、以下の準備が必要です。

### ステップ 1: 仮想環境の作成とライブラリ導入
リポジトリのルートフォルダでターミナル（コマンドプロンプトや PowerShell）を開いて実行します。

```bat
:: 仮想環境 winvenv を作成して有効化
python -m venv winvenv
winvenv\Scripts\activate

:: 必要なライブラリを一括インストール
python -m pip install --upgrade pip
pip install -r anima_pipeline\requirements.txt
```

### ステップ 2: タグ CSV の配置
入手した 2 つの CSV ファイルを、リポジトリ内の `anima_pipeline/data/raw/` フォルダの中に置きます。

- `anima_pipeline/data/raw/danbooru.csv`
- `anima_pipeline/data/raw/gelbooru.csv`

### ステップ 3: 辞書を作る
`anima_pipeline` フォルダへ移動し、辞書ビルドスクリプトを実行します。

```bat
cd anima_pipeline

:: 1. 一般タグ辞書 (必須)
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict

:: 2. アーティスト辞書 (任意: 作家名の自動検出用)
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 1 --min-count 50 --out-dir data/dict_artist

:: 3. キャラクター/作品辞書 (任意: キャラ・作品名の自動検出用)
python ../build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 3,4 --min-count 100 --out-dir data/dict_char
```
※ 完了すると `data/dict/` フォルダなどに `alias_to_canonical.json` 等が生成されます。

### ステップ 4: Gemma サーバーを起動する
**別の新しいターミナルを開き**、Gemma を起動して常駐させます（変換を行う間はずっと開いたままにしておきます）。

> [!IMPORTANT]
> ポート番号は **`8088`** を指定してください。

```bat
llama-server -m C:\path\to\your-gemma-model.gguf --port 8088 -c 8192 -ngl 99 -ot "\.ffn_(up|down|gate)_exps\.=CPU" -fa on --jinja --reasoning-budget 0
```
- `-ot ...` を付けることで、VRAM 不足で止まるのを防ぎます。
- `--reasoning-budget 0` を付けることで、AI が思考過程を長々と出力して止まるのを防ぎます。
- `server is listening on http://127.0.0.1:8088` と出れば準備完了です！

---

## 5. いざ実践！ 使い方別の手順

### A. CLI (コマンドライン) で動かす
黒い画面からサッと変換したい場合の手順です。

1. ターミナルで仮想環境を有効化し、`anima_pipeline` フォルダに移動します。
2. 以下のコマンドを実行します。
   ```bat
   python run.py "教室の窓辺に立つ茶髪の少女、夕暮れの光"
   ```
3. 画面に **English**（英訳）、**Anima prompt**（変換後プロンプト）、**Negative prompt**（ネガティブ）が表示されます。
4. これらをコピーして画像生成ツールに貼り付けます。

---

### B. Web GUI (ブラウザ) で動かす
見やすい画面で履歴を残しながら使いたい場合の手順です。

1. **バッチファイルで起動する場合 (簡単)**:
   - エクスプローラーで `anima_pipeline` フォルダを開き、`run_web.bat` をダブルクリックします。
   - 自動的にブラウザが立ち上がり、`http://127.0.0.1:7865` が開きます。
2. **手動で起動する場合**:
   ```bat
   cd anima_pipeline
   python app_web.py
   ```
   ブラウザで `http://127.0.0.1:7865` を開きます。
3. 画面の入力欄に日本語プロンプトを入れ、「生成」ボタンを押します。
4. 出力されたプロンプトをワンクリックでコピーできます。過去の履歴も一覧から呼び出せます。

---

### C. SD WebUI Forge NEO 拡張機能で動かす
Forge NEO の操作画面の中でそのままプロンプトを作りたい場合の手順です。

1. **拡張機能として登録する (ジャンクション)**:
   管理者権限で開いたコマンドプロンプトで、Forge NEO の `extensions` フォルダへリンクを張ります。
   ```bat
   mklink /J C:\sd-webui-forge-neo\extensions\anima-prompt-pipeline C:\path\to\anima-prompt-pipeline
   ```
2. **Forge NEO を起動する**:
   - 初回起動時に必要な追加ライブラリが自動でインストールされます。
   - 画面上部に **「Anima Prompt」** という新しいタブが追加されます。
3. **プロンプトを生成して転送する**:
   - 「Anima Prompt」タブを開き、日本語を入力して生成ボタンを押します。
   - 結果が表示されたら、**「txt2img へ送信」** をクリックします。
   - 自動的にいつもの画像生成（txt2img）タブに切り替わり、プロンプトとネガティブプロンプトがセットされます。あとはそのまま「Generate」を押して画像を生成します！

---

## 6. よくあるトラブルと解決策

- **「Gemma サーバーに接続できません」と出る**:
  - llama-server の黒い画面が閉じられていませんか？
  - ポート番号が `8088` になっているか確認してください（`8080` ではありません）。
- **「辞書ファイルが見つかりません」と出る**:
  - ステップ 3 の「辞書を作る」を実行していないか、途中でエラーになっていませんか？ `anima_pipeline/data/dict/alias_to_canonical.json` があるか確認してください。
- **Gemma 起動時に「Out of Memory」で落ちる**:
  - 起動オプションに `-ot "\.ffn_(up|down|gate)_exps\.=CPU"` を必ず含めてください。
  - それでも厳しい場合は、より小さいモデル（E2B など）を使うか、`-ngl 0` を指定して CPU で動かしてください。

---

さらに詳しい設定やカスタマイズ方法は [`README.md`](README.md) や [`INSTALL.md`](INSTALL.md) をご覧ください。
