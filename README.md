# Claude Code Remote Relay

Windows PC上で動作するClaude CodeとPixel WatchをAndroidスマートフォン経由でつなぐPC中継サーバー。仕様は [仕様書仮](仕様書仮) (v0.2) を参照。

## 目的

* Claude Codeの権限承認要求をリモートで確認・承認／拒否できるようにする
* 質問入力待ち状態をPixel Watchから回答できるようにする
* Pixel Watchから音声・定型文を送信してClaude Codeへ入力できるようにする

## 実装状況

現在実装済みなのはPC中継サーバー（Python/FastAPI）と、それに向けたClaude Code Hookスクリプトです。Android / Wear OSアプリは `android/` に初期スケルトンのみあり、この中継サーバーの新プロトコルへの追従はまだ行っていません（後述）。

### PC中継サーバー

* `app/protocol.py` — メッセージエンベロープとペイロード定義（仕様7章）
* `app/risk.py` — 危険度分類（仕様12章）
* `app/terminal.py` — `TerminalAdapter` / `TmuxTerminalAdapter`（仕様8.3章）
* `app/state.py` — Claude Code状態モデルと出力検出用アダプタのインターフェース（仕様8.4章）
* `app/storage.py` — SQLiteスキーマとidempotent更新（仕様9.2, 14章）
* `app/errors.py` — 共通エラーコード（仕様15章）
* `app/main.py` — FastAPIエンドポイントとWebSocket処理

### Claude Code Hook

* `claude-hooks/permission_request.py` — `PermissionRequest` Hook。PC中継サーバーへ要求を送り、承認/拒否をポーリングで待つ
* `claude-hooks/notification.py` — `Notification` Hook。入力待ち状態を質問要求として登録する（fire-and-forget）
* `claude-hooks/install_hooks.py` — 上記2つを`settings.json`へ登録するユーティリティ
* `claude-hooks/config.example.yaml` — タイムアウトやフォールバック動作の設定例

**注意**：Claude Code公式Hookスキーマは実装時点の推測に基づいています。実際の運用前に最新の公式ドキュメントと突き合わせてください（仕様11章 項目11）。

## API概要（仕様9.1章）

```text
GET  /health
GET  /api/v1/status
POST /api/v1/pair/start
POST /api/v1/pair/complete
POST /api/v1/hooks/permission
POST /api/v1/hooks/question       (拡張: 質問フロー用)
POST /api/v1/prompts
GET  /api/v1/sessions
GET  /api/v1/requests
GET  /api/v1/requests/{id}        (拡張: Hookスクリプトのポーリング用)
WS   /ws/mobile
```

`/api/v1/hooks/permission` と `/api/v1/hooks/question` は要求を作成して即座に `{"decision": "pending", "requestId": ...}` を返します。Hookスクリプトは `GET /api/v1/requests/{id}` をポーリングして解決を待ちます（仕様の同期待ち擬似コードをDB駆動のポーリングに置き換えたものです）。

`POST /api/v1/prompts` と `WS /ws/mobile` はペアリング済みデバイスの認証（`Authorization: Bearer <deviceToken>` またはWebSocketの `?token=` クエリ）が必要です。

## 必要条件

* Python 3.12+
* tmux（PCエージェントがtmux経由でClaude Codeへ入力するため）
* Linux環境（Ubuntu実機を推奨。Windows 11 + WSL2でも動くが、WSLのインストールに管理者権限＋再起動が要ること、WSL2のNAT越えのネットワーク設定（mirrored networkingまたは`netsh portproxy`＋ファイアウォール許可）が別途必要になる点で、Ubuntu実機の方が手間が少ない）

### Ubuntu実機での起動（推奨）

このリポジトリを対象のUbuntu機に置いた上で、セットアップスクリプトを実行する。

```bash
bash scripts/setup_ubuntu_host.sh
```

tmux・Node.js・Claude Code CLIのインストール、Python仮想環境の作成、`requirements.txt`のインストール、（ufw有効時は）ポート開放までを行う。実行後に表示される手順（`claude login`、`tmux new -s claude-remote` → `claude`起動、サーバー起動コマンド）に従う。

### Windows + WSL2での起動

1. Python仮想環境を作成する

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. サーバーを起動する

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

3. `http://localhost:8000/docs` からAPIを確認できます。

## テスト

```powershell
pytest
```

tmuxが無い環境でもテストは通ります（`TmuxTerminalAdapter` はtmux不在時に `is_alive()` が `False` を返すよう作られています。エンドポイントのテストはフェイクの `TerminalAdapter` を使います）。

## Claude Code Hookの有効化

```powershell
python claude-hooks/install_hooks.py --dry-run   # まず内容を確認
python claude-hooks/install_hooks.py             # ~/.claude/settings.json へ反映
```

タイムアウトやフォールバック動作を変更する場合は `claude-hooks/config.example.yaml` を `claude-hooks/config.yaml` としてコピーし、`CLAUDE_WATCH_HOOK_CONFIG` 環境変数で明示的に指定することもできます。

## Android / Wear OS

`android/` のKotlinコードも新プロトコル（`/ws/mobile`、メッセージエンベロープ、`Authorization: Bearer` 認証）に合わせて更新しました。**この環境にはAndroid SDK / JDKが無く、ビルド・実機検証は一度もできていません**。次にAndroid Studioが使える環境でビルドし、コンパイルエラーやAPIの版差異を洗い出すのが必須の次ステップです。

### 実装した範囲（縦方向スライス優先、仕様21章の方針に合わせた）

* **スマホ (`android/app`)**
  * `protocol/Envelope.kt` — メッセージエンベロープのKotlin版
  * `data/DeviceCredentialStore.kt` — `EncryptedSharedPreferences`（Keystore裏付け）でPCのURLとデバイストークンを保存（仕様13.2）
  * `network/RelayApi.kt` — `pair/start` → `pair/complete` → `prompts` の新REST API
  * `network/WebSocketClient.kt` — `/ws/mobile?token=...` への接続、エンベロープ送受信
  * `wearable/WearableBridge.kt` / `WearableCommandProcessor.kt` — PCからの`permission.request`/`question.request`を`DataClient`の`/state/pending-requests`でWatchへ同期し、Watchからの`/watch/action`・`/watch/prompt`をPCへ中継
  * `viewmodel/MainViewModel.kt`（ペアリング・HTTPフォールバック）、`viewmodel/WebSocketViewModel.kt`（WebSocket・Watch中継）、`ui/MainScreen.kt`（ペアリング画面＋保留要求への承認/拒否/回答UI）
* **Watch (`android/wear`)**
  * `protocol/Envelope.kt` — 同上のWatch版
  * `network/WearableClient.kt` — `/watch/action`・`/watch/prompt`・`/watch/request-detail`をスマホへ送信（**WatchはPCへ直接通信しない**、仕様19章 項目1）
  * `network/WatchDataListener.kt` / `WatchMessageListener.kt` — スマホからの`/state/pending-requests`・`/mobile/action-result`・`/mobile/connection-state`を受信
  * `viewmodel/MainViewModel.kt` / `ui/MainScreen.kt` — 保留要求表示、承認/拒否、選択肢回答、音声入力（`RecognizerIntent`、送信前に確認画面を必須化）、定型プロンプト、高危険度要求は時計単体承認を禁止してスマホ確認へ誘導

### 既知の制約・未実装

* ビルド未検証。Wear Compose Material / Data Layer APIのバージョン差異でコンパイルエラーが出る可能性が高い
* PC一覧・要求詳細・設定画面、Foreground Service、Room、通知チャネル、ACK再送、複数PC対応は未実装（仕様10章の一部）
* ペアリングはこの端末から直接`pair/start`→`pair/complete`を呼ぶ簡易フロー。QRコード読み取りは未実装
* Watchの「スマホで確認」は`/watch/request-detail`を送るだけで、スマホ側に詳細表示画面はまだ無い（要求は一覧に出るので回答自体は可能）
