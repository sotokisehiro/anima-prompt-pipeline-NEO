"""生成履歴のサーバーサイド永続化モジュール。

これまでブラウザの localStorage(キー: `anima_prompt_history`)に保存していた
生成履歴を、Forge NEO 拡張機能向けにサーバー側の JSON ファイルへ移す。
標準ライブラリのみで完結させ、常に import 可能な軽量モジュールとする。

保存先はリポジトリルート(`anima_pipeline/` の親ディレクトリ)直下の
`user_data/history.json`。CSV のインポート/エクスポートは、旧ブラウザ版 GUI
(`anima_pipeline/web/app.js`)と完全互換のフォーマットを維持し、両者の間で
ファイルを行き来できるようにする。
"""
from __future__ import annotations

import csv
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------
# パス(config.py と同じ「このファイルからの相対解決」パターンに倣う)
# --------------------------------------------------------------------------
# anima_pipeline/history_store.py -> parent = anima_pipeline/ -> parent = リポジトリルート
REPO_ROOT = Path(__file__).resolve().parent.parent
USER_DATA_DIR = REPO_ROOT / "user_data"
DEFAULT_HISTORY_PATH = USER_DATA_DIR / "history.json"
EXPORT_DIR = USER_DATA_DIR / "export"

# CSV(app.js の arrayToCSV / parseCSV と完全互換にするための列定義)
CSV_HEADERS = [
    "Name", "Datetime", "JaPrompt", "ExtraTags", "English", "Anima",
    "Negative", "Temperature", "MaxTokens", "FuzzyCutoff", "TranslateFirst",
]

# CSV インポート時、設定値が空/欠落している場合のデフォルト(app.js と同一)
_IMPORT_DEFAULT_TEMPERATURE = 0.4
_IMPORT_DEFAULT_MAX_TOKENS = 2048
_IMPORT_DEFAULT_FUZZY_CUTOFF = 90
_IMPORT_DEFAULT_TRANSLATE_FIRST = True

# CSV インポート時、Name 列が無い/空の場合のデフォルト名(app.js の import 処理と同一)
_IMPORT_DEFAULT_NAME = "インポートした項目"


def _now_str() -> str:
    """現在時刻を 'YYYY-MM-DD HH:MM:SS' 形式で返す。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class HistoryStore:
    """生成履歴を JSON ファイルへ保存・読み込みするストア。

    スレッドセーフ性: `threading.Lock` で読み込み〜変更〜書き込みの一連を
    保護する。ファイル全体を読み、メモリ上で変更し、全体を書き戻すという
    シンプルな方式(高頻度アクセスを想定したサーバーではないため十分)。
    """

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_HISTORY_PATH
        self._lock = threading.Lock()
        # 保存先ディレクトリが無ければ作成しておく
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # 内部ヘルパー(呼び出し側で必ずロックを取ってから使うこと)
    # ----------------------------------------------------------------
    def _load(self) -> list[dict]:
        """JSON ファイルを読み込んで履歴リストを返す。無ければ空リスト。"""
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # 壊れたファイルや読み込み失敗時は空扱いにする(黙って上書きされうる)
            return []
        if not isinstance(data, list):
            return []
        return data

    def _save(self, data: list[dict]) -> None:
        """履歴リストを JSON ファイルへ書き込む。"""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------------
    # 公開 API
    # ----------------------------------------------------------------
    def list(self) -> list[dict]:
        """全履歴を保存順で返す。ファイルが無ければ空リスト。"""
        with self._lock:
            return self._load()

    def add(
        self,
        *,
        name: str,
        ja_prompt: str,
        extra_tags: str,
        english: str,
        anima: str,
        negative: str,
        issues: list[str] | None = None,
        settings: dict | None = None,
    ) -> dict:
        """新規履歴を1件追加して保存し、追加したアイテムを返す。

        id は uuid4 の文字列、datetime は現在時刻を 'YYYY-MM-DD HH:MM:SS' で
        記録する。
        """
        item = {
            "id": str(uuid.uuid4()),
            "name": name,
            "datetime": _now_str(),
            "jaPrompt": ja_prompt,
            "extraTags": extra_tags,
            "english": english,
            "anima": anima,
            "negative": negative,
            "issues": issues if issues is not None else [],
            "settings": dict(settings) if settings else None,
        }
        with self._lock:
            data = self._load()
            data.append(item)
            self._save(data)
        return item

    def get(self, item_id: str) -> dict | None:
        """id で1件取得する。見つからなければ None。"""
        with self._lock:
            data = self._load()
        for item in data:
            if item.get("id") == item_id:
                return item
        return None

    def delete(self, item_id: str) -> bool:
        """id で1件削除する。削除できたら True、見つからなければ False。"""
        with self._lock:
            data = self._load()
            new_data = [item for item in data if item.get("id") != item_id]
            if len(new_data) == len(data):
                return False
            self._save(new_data)
        return True

    # ----------------------------------------------------------------
    # CSV エクスポート / インポート(app.js と完全互換)
    # ----------------------------------------------------------------
    def export_csv(self, out_path: Path | None = None) -> Path:
        """全履歴を CSV へ出力し、実際に書いたパスを返す。

        out_path が None の場合は
        `<repo_root>/user_data/export/anima_prompts_YYYYMMDD.csv`
        (YYYYMMDD は現在日付)に出力する。

        フォーマットは旧ブラウザ版 GUI(app.js の arrayToCSV)と完全互換:
        UTF-8 BOM 付き、CRLF 改行、RFC4180 相当のクォーティング。
        設定値(temperature 等)が無い場合は空文字を書く
        (app.js のエクスポート時に独自のデフォルト値を補完しない挙動に合わせる)。
        """
        if out_path is None:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"anima_prompts_{datetime.now().strftime('%Y%m%d')}.csv"
            out_path = EXPORT_DIR / filename
        else:
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            data = self._load()

        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, lineterminator="\r\n")
            writer.writerow(CSV_HEADERS)
            for item in data:
                settings = item.get("settings") or {}
                writer.writerow([
                    item.get("name", ""),
                    item.get("datetime", ""),
                    item.get("jaPrompt", ""),
                    item.get("extraTags", ""),
                    item.get("english", ""),
                    item.get("anima", ""),
                    item.get("negative", ""),
                    settings.get("temperature", ""),
                    settings.get("maxTokens", ""),
                    settings.get("fuzzyCutoff", ""),
                    settings.get("translateFirst", ""),
                ])

        return out_path

    def import_csv(self, file_path: Path) -> int:
        """CSV から履歴を読み込み、末尾に追加保存する。

        JaPrompt が空(または空白のみ)の行はスキップする。
        JaPrompt / Anima 列がヘッダーに無ければ ValueError を送出する。
        取り込んだ件数を返す。
        """
        file_path = Path(file_path)
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            normalized_fields = {name.strip().lower() for name in fieldnames}

            if "japrompt" not in normalized_fields or "anima" not in normalized_fields:
                raise ValueError(
                    "CSVに必要な列 (JaPrompt, Anima) が見つかりません。"
                )

            rows = []
            for row in reader:
                normalized = {
                    (k.strip().lower() if k else ""): (v if v is not None else "")
                    for k, v in row.items()
                }
                rows.append(normalized)

        imported: list[dict] = []
        for row in rows:
            ja_prompt = (row.get("japrompt") or "").strip()
            if not ja_prompt:
                continue

            name = row.get("name") or _IMPORT_DEFAULT_NAME
            datetime_val = row.get("datetime") or ""
            datetime_str = datetime_val if datetime_val.strip() else _now_str()

            temp_raw = row.get("temperature", "")
            max_tokens_raw = row.get("maxtokens", "")
            fuzzy_raw = row.get("fuzzycutoff", "")
            translate_raw = row.get("translatefirst", "")

            try:
                temperature = float(temp_raw) if temp_raw.strip() else _IMPORT_DEFAULT_TEMPERATURE
            except ValueError:
                temperature = _IMPORT_DEFAULT_TEMPERATURE
            try:
                max_tokens = int(max_tokens_raw) if max_tokens_raw.strip() else _IMPORT_DEFAULT_MAX_TOKENS
            except ValueError:
                max_tokens = _IMPORT_DEFAULT_MAX_TOKENS
            try:
                fuzzy_cutoff = int(fuzzy_raw) if fuzzy_raw.strip() else _IMPORT_DEFAULT_FUZZY_CUTOFF
            except ValueError:
                fuzzy_cutoff = _IMPORT_DEFAULT_FUZZY_CUTOFF
            translate_first = (
                translate_raw.strip().lower() == "true"
                if translate_raw.strip() != ""
                else _IMPORT_DEFAULT_TRANSLATE_FIRST
            )

            item = {
                "id": str(uuid.uuid4()),
                "name": name,
                "datetime": datetime_str,
                "jaPrompt": ja_prompt,
                "extraTags": row.get("extratags") or "",
                "english": row.get("english") or "",
                "anima": row.get("anima") or "",
                "negative": row.get("negative") or "",
                "issues": [],
                "settings": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                    "fuzzyCutoff": fuzzy_cutoff,
                    "translateFirst": translate_first,
                },
            }
            imported.append(item)

        if imported:
            with self._lock:
                data = self._load()
                data.extend(imported)
                self._save(data)

        return len(imported)
