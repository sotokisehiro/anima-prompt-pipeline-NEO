@echo off
setlocal
chcp 65001 >nul
title Anima Prompt Pipeline - Dictionary Setup

echo =====================================================================
echo   Anima Prompt Pipeline - CSV Setup and Dictionary Builder
echo =====================================================================
echo.

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "PIPELINE_DIR=%ROOT_DIR%\anima_pipeline"
set "RAW_DIR=%PIPELINE_DIR%\data\raw"
set "DICT_DIR=%PIPELINE_DIR%\data\dict"
set "DICT_ARTIST_DIR=%PIPELINE_DIR%\data\dict_artist"
set "DICT_CHAR_DIR=%PIPELINE_DIR%\data\dict_char"

call :check_python
if errorlevel 1 goto :error

call :prepare_csv
if errorlevel 1 goto :error

call :build_dictionaries
if errorlevel 1 goto :error

call :verify_results
if errorlevel 1 goto :error

echo.
echo =====================================================================
echo  [成功] 共通セットアップ（CSV配置および辞書ビルド）が正常に完了しました！
echo =====================================================================
echo.
echo 生成された辞書:
echo   - 一般タグ辞書:       anima_pipeline\data\dict\
echo   - アーティスト辞書:   anima_pipeline\data\dict_artist\
echo   - キャラ・作品辞書:   anima_pipeline\data\dict_char\
echo.
echo 次のステップ (INSTALL.md Step 4):
echo   1. 別ターミナルで Gemma サーバーを起動してください:
echo      anima_pipeline\run_llm.bat
echo   2. 利用形態に合わせて起動:
echo      - Web GUI: anima_pipeline\run_web.bat
echo      - CLI:     cd anima_pipeline ^&^& python run.py "日本語プロンプト"
echo      - Forge:   Forge NEO を起動して「Anima Prompt」タブを開く
echo.
cd /d "%ROOT_DIR%"
pause
exit /b 0

:: ---------------------------------------------------------------------
:: Python 環境の検出と準備
:: ---------------------------------------------------------------------
:check_python
echo [1/4] Python 環境の確認中...

set "PYTHON_EXE="
set "PIP_EXE="

if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
        set "PYTHON_EXE=%VIRTUAL_ENV%\Scripts\python.exe"
        set "PIP_EXE=%VIRTUAL_ENV%\Scripts\pip.exe"
        echo  - アクティブな仮想環境を使用: %VIRTUAL_ENV%
        goto :python_detected
    )
)

if exist "%ROOT_DIR%\winvenv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\winvenv\Scripts\python.exe"
    set "PIP_EXE=%ROOT_DIR%\winvenv\Scripts\pip.exe"
    echo  - 仮想環境 winvenv を使用: %ROOT_DIR%\winvenv
    goto :python_detected
)

if exist "%ROOT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\venv\Scripts\python.exe"
    set "PIP_EXE=%ROOT_DIR%\venv\Scripts\pip.exe"
    echo  - 仮想環境 venv を使用: %ROOT_DIR%\venv
    goto :python_detected
)

where python >nul 2>&1
if errorlevel 1 (
    echo [エラー] Python が見つかりません。
    echo Python 3.10 以上をインストールし、PATH に通してください。
    exit /b 1
)

echo  - 仮想環境が見つからないため、winvenv を新規作成します...
call python -m venv "%ROOT_DIR%\winvenv"
if errorlevel 1 (
    echo [エラー] 仮想環境 winvenv の作成に失敗しました。
    exit /b 1
)
set "PYTHON_EXE=%ROOT_DIR%\winvenv\Scripts\python.exe"
set "PIP_EXE=%ROOT_DIR%\winvenv\Scripts\pip.exe"

:python_detected
"%PYTHON_EXE%" -c "import pandas" >nul 2>&1
if errorlevel 1 (
    call :install_requirements
    if errorlevel 1 exit /b 1
)

echo  - Python 環境 OK.
echo.
exit /b 0

:install_requirements
echo  - 必要なパッケージ [pandas 等] をインストール中...
"%PYTHON_EXE%" -m pip install --upgrade pip
"%PIP_EXE%" install -r "%PIPELINE_DIR%\requirements.txt"
if errorlevel 1 (
    echo [エラー] 依存パッケージのインストールに失敗しました。
    exit /b 1
)
exit /b 0

:: ---------------------------------------------------------------------
:: タグ CSV の入手と配置
:: ---------------------------------------------------------------------
:prepare_csv
echo [2/4] タグ CSV ファイルの確認と配置中...

if not exist "%RAW_DIR%" mkdir "%RAW_DIR%"

:: --- Danbooru CSV ---
if exist "%RAW_DIR%\danbooru.csv" (
    for %%A in ("%RAW_DIR%\danbooru.csv") do if %%~zA gtr 0 (
        echo  - danbooru.csv: 配置済み
        goto :danbooru_done
    )
)

echo  - danbooru.csv を探索中...
set "FOUND_DANBOORU="
if exist "%USERPROFILE%\Downloads\danbooru.csv" set "FOUND_DANBOORU=%USERPROFILE%\Downloads\danbooru.csv"

if not defined FOUND_DANBOORU (
    for /f "delims=" %%I in ('dir /b /o:-d "%USERPROFILE%\Downloads\danbooru-20*.csv" 2^>nul') do (
        if not defined FOUND_DANBOORU set "FOUND_DANBOORU=%USERPROFILE%\Downloads\%%I"
    )
)

if defined FOUND_DANBOORU (
    echo  - Downloads からコピー中: "%FOUND_DANBOORU%"
    copy /y "%FOUND_DANBOORU%" "%RAW_DIR%\danbooru.csv" >nul
    goto :check_danbooru
)

echo  - Hugging Face から最新の Danbooru CSV をダウンロード中...
set "DANBOORU_FILE="
"%PYTHON_EXE%" -c "import urllib.request, json; data=json.loads(urllib.request.urlopen('https://huggingface.co/api/datasets/HDiffusion/historical-danbooru-tag-counts').read()); files=[s['rfilename'] for s in data['siblings'] if s['rfilename'].startswith('danbooru-') and s['rfilename'].endswith('.csv')]; print(files[-1])" > "%RAW_DIR%\.danbooru_name.tmp" 2>nul
if exist "%RAW_DIR%\.danbooru_name.tmp" (
    set /p DANBOORU_FILE=<"%RAW_DIR%\.danbooru_name.tmp"
    del "%RAW_DIR%\.danbooru_name.tmp" 2>nul
)
if not defined DANBOORU_FILE set "DANBOORU_FILE=danbooru-2026-09-27.csv"
echo    対象: %DANBOORU_FILE%
curl.exe -L --progress-bar "https://huggingface.co/datasets/HDiffusion/historical-danbooru-tag-counts/resolve/main/%DANBOORU_FILE%" -o "%RAW_DIR%\danbooru.csv"

:check_danbooru
if not exist "%RAW_DIR%\danbooru.csv" (
    echo [エラー] danbooru.csv の取得に失敗しました。
    echo 手動で https://huggingface.co/HDiffusion から入手し、
    echo "%RAW_DIR%\danbooru.csv" に配置してください。
    exit /b 1
)
for %%A in ("%RAW_DIR%\danbooru.csv") do if %%~zA==0 (
    echo [エラー] danbooru.csv のサイズが 0 バイトです。
    del "%RAW_DIR%\danbooru.csv"
    exit /b 1
)

:danbooru_done

:: --- Gelbooru CSV ---
if exist "%RAW_DIR%\gelbooru.csv" (
    for %%A in ("%RAW_DIR%\gelbooru.csv") do if %%~zA gtr 0 (
        echo  - gelbooru.csv: 配置済み
        goto :gelbooru_done
    )
)

echo  - gelbooru.csv を探索中...
set "FOUND_GELBOORU="
if exist "%USERPROFILE%\Downloads\gelbooru.csv" set "FOUND_GELBOORU=%USERPROFILE%\Downloads\gelbooru.csv"

if not defined FOUND_GELBOORU (
    for /f "delims=" %%I in ('dir /b /o:-d "%USERPROFILE%\Downloads\gelbooru*.csv" 2^>nul') do (
        if not defined FOUND_GELBOORU set "FOUND_GELBOORU=%USERPROFILE%\Downloads\%%I"
    )
)

if defined FOUND_GELBOORU (
    echo  - Downloads からコピー中: "%FOUND_GELBOORU%"
    copy /y "%FOUND_GELBOORU%" "%RAW_DIR%\gelbooru.csv" >nul
    goto :check_gelbooru
)

echo  - Hugging Face から Gelbooru CSV [約23MB] をダウンロード中...
curl.exe -L --progress-bar "https://huggingface.co/datasets/HDiffusion/gelbooru-tags/resolve/main/gelbooru-09-09-2025.csv" -o "%RAW_DIR%\gelbooru.csv"

:check_gelbooru
if not exist "%RAW_DIR%\gelbooru.csv" (
    echo [エラー] gelbooru.csv の取得に失敗しました。
    echo 手動で https://huggingface.co/HDiffusion から入手し、
    echo "%RAW_DIR%\gelbooru.csv" に配置してください。
    exit /b 1
)
for %%A in ("%RAW_DIR%\gelbooru.csv") do if %%~zA==0 (
    echo [エラー] gelbooru.csv のサイズが 0 バイトです。
    del "%RAW_DIR%\gelbooru.csv"
    exit /b 1
)

:gelbooru_done

echo  - CSV タグデータ配置完了.
echo.
exit /b 0

:: ---------------------------------------------------------------------
:: 辞書データのビルド
:: ---------------------------------------------------------------------
:build_dictionaries
echo [3/4] 辞書データのビルドを開始します...
cd /d "%PIPELINE_DIR%"

echo.
echo --- [1/3] 一般タグ辞書 (data/dict) のビルド ---
"%PYTHON_EXE%" ..\build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 0 --min-count 10 --out-dir data/dict
if errorlevel 1 (
    echo [エラー] 一般タグ辞書のビルドに失敗しました。
    exit /b 1
)

echo.
echo --- [2/3] アーティスト辞書 (data/dict_artist) のビルド ---
"%PYTHON_EXE%" ..\build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 1 --min-count 50 --out-dir data/dict_artist
if errorlevel 1 (
    echo [エラー] アーティスト辞書のビルドに失敗しました。
    exit /b 1
)

echo.
echo --- [3/3] キャラクター/作品辞書 (data/dict_char) のビルド ---
"%PYTHON_EXE%" ..\build_anima_dictionary.py --danbooru data/raw/danbooru.csv --gelbooru data/raw/gelbooru.csv --keep-categories 3,4 --min-count 100 --out-dir data/dict_char
if errorlevel 1 (
    echo [エラー] キャラクター/作品辞書のビルドに失敗しました。
    exit /b 1
)

echo.
exit /b 0

:: ---------------------------------------------------------------------
:: 結果検証
:: ---------------------------------------------------------------------
:verify_results
echo [4/4] 生成結果の検証中...

if not exist "%DICT_DIR%\alias_to_canonical.json" (
    echo [エラー] %DICT_DIR%\alias_to_canonical.json が見つかりません。
    exit /b 1
)
if not exist "%DICT_DIR%\anima_tags.jsonl" (
    echo [エラー] %DICT_DIR%\anima_tags.jsonl が見つかりません。
    exit /b 1
)
if not exist "%DICT_ARTIST_DIR%\alias_to_canonical.json" (
    echo [エラー] %DICT_ARTIST_DIR%\alias_to_canonical.json が見つかりません。
    exit /b 1
)
if not exist "%DICT_CHAR_DIR%\alias_to_canonical.json" (
    echo [エラー] %DICT_CHAR_DIR%\alias_to_canonical.json が見つかりません。
    exit /b 1
)

exit /b 0

:error
echo.
echo =====================================================================
echo  [失敗] エラーが発生したため処理を中断しました。
echo =====================================================================
cd /d "%ROOT_DIR%"
pause
exit /b 1
