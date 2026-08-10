# Claude Code Remote Relay

Windows PC上で動作するClaude CodeとPixel WatchをAndroidスマートフォン経由でつなぐPC中継サーバー。仕様は [仕様書仮](仕様書仮) (v0.2) を参照。

## 目的

* Claude Codeの権限承認要求をリモートで確認・承認／拒否できるようにする
* 質問入力待ち状態をPixel Watchから回答できるようにする
* Pixel Watchから音声・定型文を送信してClaude Codeへ入力できるようにする
* Claudeが応答を出し終えたら、その本文をPixel Watchに表示する

## 実装状況

PC中継サーバー（Python/FastAPI）、Claude Code Hookスクリプト、Android/Wear OSアプリ（`android/`）まで実装済み。Android側は実機（Pixel 10 + Pixel Watch 4）でのペアリング・通知・承認/回答フローを確認済み（詳細は後述）。**未確認なのはPC側のtmux経由での実際のClaude Code入力**——これはtmuxの無い環境で開発したため。

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
* `claude-hooks/stop.py` — `Stop` Hook。Claudeが応答し終わった本文を取り出してWatchへ送る（fire-and-forget）。Stopイベント自体は本文を持たず`transcript_path`だけを渡してくるため、そのJSONLを末尾から遡って直近のassistantターンのテキストを復元する
* `claude-hooks/install_hooks.py` — 上記3つを`settings.json`へ登録するユーティリティ
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
POST /api/v1/hooks/assistant-message  (拡張: 応答表示用)
POST /api/v1/prompts
GET  /api/v1/sessions
GET  /api/v1/requests
GET  /api/v1/requests/{id}        (拡張: Hookスクリプトのポーリング用)
WS   /ws/mobile
```

`/api/v1/hooks/permission` と `/api/v1/hooks/question` は要求を作成して即座に `{"decision": "pending", "requestId": ...}` を返します。Hookスクリプトは `GET /api/v1/requests/{id}` をポーリングして解決を待ちます（仕様の同期待ち擬似コードをDB駆動のポーリングに置き換えたものです）。

`/api/v1/hooks/assistant-message` は表示専用なので、他の2つと違って `requests` テーブルに行を作らず（承認も期限切れも無い）、接続中デバイスへ配信した時点で `{"status": "broadcast", "delivered": <接続数>}` を返します。Hookスクリプトはポーリングしません。本文は時計の画面に合わせて既定500文字で切り詰められます（`CLAUDE_WATCH_MESSAGE_MAX_CHARS` で変更可、切り詰めた場合は `truncated` と元の文字数 `fullLength` が付きます）。

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

`android/` は新プロトコル（`/ws/mobile`、メッセージエンベロープ、`Authorization: Bearer` 認証）に対応済みで、**実機（Pixel 10 + Pixel Watch 4）でビルド・インストール・動作確認済み**です。JDK 17 / Android SDK cmdline-tools / Gradle wrapperはこのリポジトリの外（開発機のユーザーローカル環境）に別途セットアップした前提です。

### 実装した範囲

* **スマホ (`android/app`)**
  * `protocol/Envelope.kt` — メッセージエンベロープのKotlin版
  * `data/DeviceCredentialStore.kt` — `EncryptedSharedPreferences`（Keystore裏付け）でPCのURLとデバイストークンを保存（仕様13.2）
  * `network/RelayApi.kt` — `pair/start` → `pair/complete` → `prompts` の新REST API
  * `network/WebSocketClient.kt` — `/ws/mobile?token=...` への接続、エンベロープ送受信
  * `service/RelayConnectionService.kt` — WebSocket接続を保持するForeground Service（仕様10.2）。ここが`permission.request`/`question.request`受信の起点
  * `notifications/NotificationHelper.kt` / `NotificationActionReceiver.kt` — 承認要求・質問を**バイブレーション付きの通知**として表示し、通知の承認/拒否/選択肢ボタンから直接応答できる（仕様5.6/10.3）。高危険度要求は通知にワンタップ承認ボタンを出さない（仕様12章）。Claudeの応答（`assistant.message`）は別チャンネル「Claudeの応答」で`BigTextStyle`表示。応答は1セッション中に何度も届くので**既定でバイブレーション・音なし**（時計には出るが震えない）にしてあり、セッションごとに1枠を上書きするので通知が積み上がらない。震わせたい場合はAndroidの通知設定でこのチャンネルの重要度を上げる
  * `wearable/WearableBridge.kt` / `WearableCommandProcessor.kt` — 保留要求を`DataClient`の`/state/pending-requests`でWatchアプリ内表示用に同期し、Watchアプリからの`/watch/action`・`/watch/prompt`をPCへ中継（アプリ内のフォールバック画面用。主経路は下記の通知）
  * `ui/MainScreen.kt` — ペアリング画面＋保留要求一覧（フォールバック表示）
* **Watch (`android/wear`)**
  * `protocol/Envelope.kt` — 同上のWatch版
  * `network/WearableClient.kt` — `/watch/action`・`/watch/prompt`・`/watch/request-detail`をスマホへ送信（**WatchはPCへ直接通信しない**、仕様19章 項目1）
  * `network/WatchDataListener.kt`（起動時に現在の保留要求を`fetchCurrent`で取得＋以後の変化を購読）/ `WatchMessageListener.kt`
  * `viewmodel/MainViewModel.kt` / `ui/MainScreen.kt` — 主用途は**音声入力・定型文でのプロンプト送信**（送信前に確認画面を必須化）。承認/質問はWear OSの通知ブリッジ機能で自動的にWatchへ転送される通知から操作する想定で、アプリ内の保留要求画面はフォールバック

### 実機で検証済み

* ペアリング（`pair/start`→`pair/complete`）、`/ws/mobile`の接続維持（Foreground Service）
* 承認要求・質問通知がスマホとWatch（Wear OS標準の通知ブリッジ経由、Watch側コード不要）の両方に届き、バイブレーションと承認/拒否/選択肢ボタンが機能する
* 通知のボタン操作がサーバーまで届き、`requests`テーブルが正しく`allowed`/`answered`に遷移する
* 期限切れ（120秒）の要求が承認/回答できないこと
* **`Stop` Hookが本物のClaude Codeイベントから自動発火する**こと。Ubuntu機で`install_hooks.py`を実行したあと、（Claude Codeの再起動なしで）応答ごとに`POST /api/v1/hooks/assistant-message`が飛ぶのを確認した
* **`stop.py`が実物のtranscript JSONLをパースできる**こと。651KBの実セッションログに対して直近のassistantターンのテキストを正しく抽出できた——`type`/`message.content`のブロック構造の想定は実データと一致している
* `assistant.message`が接続中の実機スマホまで届くこと（`delivered: 1`）。`requests`テーブルに行を作らないことも実DB（52行中`assistant.message`は0行）で確認

### 未検証（Ubuntu機側で確認すべきこと）

* **`terminal.send_text`が実際にtmux経由でClaude Codeへ文字を打ち込むか**（このリポジトリの開発・検証はtmuxの無いWindows機で行ったため、`CLAUDE_NOT_RUNNING`が返ることまでしか確認できていない）
* `claude-hooks/permission_request.py`・`notification.py`が本物のClaude Code Hookイベントから正しく呼ばれるか（公式Hookスキーマは推測に基づくため要突き合わせ、仕様11章項目11）
* **`assistant.message`が実際にWatchの画面に出るか。** サーバー→スマホまでは上記の通り実機で確認済みだが、`NotificationHelper.notifyAssistantMessage`を入れた**APKをまだビルド・インストールしていない**ため、現状スマホは受信したエンベロープを黙って捨てている（古いAPKの`handleIncomingText`に`assistant.message`の分岐が無い）。**残作業はAPKの再ビルドとインストールのみ**
* PC一覧・要求詳細・設定画面、Room、ACK再送、複数PC対応は未実装（仕様10章の一部）
* ペアリングはこの端末から直接`pair/start`→`pair/complete`を呼ぶ簡易フロー。QRコード読み取りは未実装
