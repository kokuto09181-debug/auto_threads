# システムアーキテクチャ設計

> 作成日: 2026-03-26
> 目的: 実装前の技術設計確定

---

## 全体像: 何が何をやるか

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│   ① post.yml       毎日3回定時起動 (投稿パイプライン)        │
│   ② metrics.yml    毎日1回起動 (24h後のデータ回収)          │
│   ③ token.yml      月1回起動 (APIトークン自動更新)          │
└──────────────────────┬──────────────────────────────────────┘
                       │ Python スクリプトを実行
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Python Pipeline                             │
│                                                             │
│  [1] Notion から「今日のコンテキスト」を取得                 │
│       - ペルソナ設定                                        │
│       - 過去のエンゲージTOP5投稿（プロンプトに注入用）       │
│       - 今週のトピックシード                                 │
│            ↓                                               │
│  [2] Claude API: コピーライター（投稿文を生成）              │
│            ↓                                               │
│  [3] Claude API: 採点エージェント（7項目 / ≥7.0点で通過）   │
│       - 不合格 → 最大3回再生成                              │
│            ↓                                               │
│  [4] 重複チェック（過去30投稿との類似度 < 70%）             │
│            ↓                                               │
│  [5] Threads API: 投稿実行                                 │
│            ↓                                               │
│  [6] Notion に記録（投稿ID・テキスト・投稿時刻）            │
└─────────────────────────────────────────────────────────────┘
                       │
         (24時間後に metrics.yml が起動)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  [7] Threads API: メトリクス取得                            │
│       - 閲覧数・いいね・返信・リポスト                      │
│            ↓                                               │
│  [8] Notion に書き込み + エンゲージ率計算                   │
│            ↓                                               │
│  [9] TOP5更新 → 次の生成プロンプトに自動反映                │
└─────────────────────────────────────────────────────────────┘
```

---

## コンポーネント別の責任

### GitHub Actions（スケジューラー）
**役割**: 何も考えない。決まった時間にスクリプトを起動するだけ。

```yaml
# 投稿ワークフローのcron設定（UTC表記）
# 7:30 JST = 22:30 UTC (前日)
# 12:30 JST = 03:30 UTC
# 21:30 JST = 12:30 UTC

schedule:
  - cron: '30 22 * * *'   # 朝7:30 JST
  - cron: '30 3 * * *'    # 昼12:30 JST
  - cron: '30 12 * * *'   # 夜21:30 JST
```

**管理するもの**:
- Secrets（APIキー類） → 環境変数としてスクリプトに渡す
- 実行ログ → GitHub Actions の Run history に残る

---

### Claude API（生成エンジン）
**役割**: テキストを作る・採点する。2回呼ばれる。

```
呼び出し1: コピーライター
  入力: ペルソナ設定 + トピック + エンゲージTOP5（参考例）
  出力: 投稿文テキスト（500〜800文字目安）

呼び出し2: 採点エージェント
  入力: 生成されたテキスト + 採点基準
  出力: 7項目スコア + 平均点 + 改善コメント
  判定: 平均 ≥ 7.0 → OK / < 7.0 → 再生成指示を返す
```

**モデル選定**:
- 生成: `claude-sonnet-4-6`（コスパ重視。Opusは高品質だがコスト3倍）
- 採点: `claude-haiku-4-5-20251001`（採点だけなので軽量で十分）

**コスト試算**（1日3投稿、月90投稿）:
```
Sonnet（生成）: ~1,500 tokens × 90回 ≈ $0.40/月
Haiku（採点）:  ~500 tokens × 90回 ≈ $0.04/月
再生成を考慮しても: 月$1〜2（¥150〜300）
```

---

### Threads API（投稿・データ取得）
**役割**: 実際に投稿する・数値を取得する。

```
投稿フロー（2ステップ必要）:
  Step1: POST /threads
         → media_container_id を取得
  Step2: POST /threads/publish
         → 実際に公開

メトリクス取得:
  GET /{post_id}/insights
  → views, likes, replies, reposts, quotes

利用制限確認:
  GET /{user_id}/threads_publishing_limit
  → 残り投稿可能数を確認（250/日上限）
```

**トークン管理**:
```
問題: Threads長期トークンは60日で期限切れ
解決: 50日目に自動更新ワークフローを実行
  GET /refresh_access_token?grant_type=th_refresh_token&access_token={token}
  → 新トークンをGitHub Secrets経由で更新
```

---

### Notion（データ管理・可視化）
**役割**: 全データの保存・可視化・設定管理。人間が見る場所。

#### DB設計: Posts（投稿管理）

| カラム | 型 | 内容 |
|--------|-----|------|
| title | text | 投稿冒頭30文字 |
| body | text | 投稿全文 |
| status | select | `scheduled` / `posted` / `failed` |
| threads_post_id | text | Threads APIが返すID |
| posted_at | datetime | 実際の投稿時刻 |
| topic | text | どのトピックシードから生成したか |
| ai_score | number | 採点平均点 |
| views | number | 閲覧数 |
| likes | number | いいね数 |
| replies | number | 返信数 |
| reposts | number | リポスト数 |
| engagement_rate | formula | (likes+replies+reposts) / views |
| is_top5 | checkbox | TOP5かどうか |

#### DB設計: Config（設定管理）

| カラム | 型 | 内容 |
|--------|-----|------|
| key | text | 設定キー名 |
| value | text | 設定値 |
| updated_at | datetime | 最終更新 |

**Config に入れるもの**:
- `persona_text`: ペルソナ設定の全文
- `weekly_topics`: 今週のトピックリスト（改行区切り）
- `top5_posts`: エンゲージTOP5の投稿全文（プロンプト注入用）
- `link_post_interval`: リンク投稿の間隔設定（現在値）

---

## ファイル構成（実装時の予定）

```
auto_threads/
├── src/
│   ├── pipeline.py          # メイン実行スクリプト（投稿フロー）
│   ├── metrics.py           # メトリクス収集スクリプト
│   ├── agents/
│   │   ├── copywriter.py    # 生成エージェント（Claudeプロンプト）
│   │   └── scorer.py        # 採点エージェント（Claudeプロンプト）
│   ├── clients/
│   │   ├── threads.py       # Threads API ラッパー
│   │   ├── claude.py        # Claude API ラッパー
│   │   └── notion.py        # Notion API ラッパー
│   └── utils/
│       ├── dedup.py         # 重複チェック
│       └── jitter.py        # 投稿時間ランダム化
├── config/
│   └── persona.yaml         # ペルソナ設定（後で差し替える）
├── .github/workflows/
│   ├── post.yml             # 投稿ワークフロー
│   ├── metrics.yml          # メトリクス収集ワークフロー
│   └── token_refresh.yml    # トークン更新ワークフロー
├── tests/
│   └── test_pipeline.py     # 動作確認用テスト
└── requirements.txt
```

---

## GitHub Secrets 一覧（必要なもの）

```
THREADS_ACCESS_TOKEN     # Threads APIの長期トークン（60日更新）
THREADS_USER_ID          # ThreadsのユーザーID
ANTHROPIC_API_KEY        # Claude API キー
NOTION_API_KEY           # Notion Integration Token
NOTION_POSTS_DB_ID       # Posts DBのID
NOTION_CONFIG_DB_ID      # Config DBのID
GITHUB_TOKEN             # トークン自動更新時にSecretsを書き換えるため
```

---

## データの流れ（時系列）

```
Day 0 (初期設定):
  Notion Config に persona_text と weekly_topics を手動設定
  GitHub Secrets に各APIキーを設定

毎日 7:30 / 12:30 / 21:30:
  1. Notion Config から persona + top5 を読み込む
  2. Claude に生成させる
  3. Claude に採点させる（不合格なら再生成 × 最大3回）
  4. 過去30投稿と類似度チェック
  5. Threads に投稿
  6. Notion Posts に記録（status: posted）

毎日 9:00（24h後チェック）:
  1. Notion から status=posted かつ 24h経過した投稿を取得
  2. Threads API でメトリクスを取得
  3. Notion を更新（views, likes, replies, reposts）
  4. エンゲージ率でソート → TOP5を選定
  5. Notion Config の top5_posts を更新
     → 次回の生成プロンプトに自動で反映される
```

---

## 設計上の判断と理由

| 判断 | 採用 | 却下 | 理由 |
|------|------|------|------|
| 状態の保存場所 | Notion | DB / JSON in repo | 人間が見やすい・設定変更がコード不要 |
| 生成モデル | Sonnet+Haiku | Opus統一 | コスト差が10倍。品質差は採点ゲートで補う |
| スケジューラー | GitHub Actions | 自前サーバー / Vercel Cron | コスト¥0・管理不要 |
| 重複チェック | Jaccard係数 | 埋め込みベクトル | 軽量・API呼び出し不要・十分な精度 |
| ジッター実装 | Pythonでsleep | Actions schedule細分化 | Actionsのcron精度は1分単位なので不向き |
| トークン更新 | 専用workflow | 手動 | 忘れるとアカウント止まるため自動化必須 |

---

## 未解決の設計問題（議論したいポイント）

```
① Notionのトピックシードは誰が更新するか？
   現状: 週1回、人間が手動でNotionに入力する想定
   改善案: Claudeが「今週のトレンドトピック」を自動生成してNotionに書く

② 採点3回連続不合格の時どうするか？
   現状: スキップしてログに記録
   改善案: Slack/メール通知を送る

③ リンク投稿（アフィリ）の挿入をどこで制御するか？
   現状: pipeline.py でカウンターを持ち「5投稿に1回」を強制
   改善案: Notion Config で比率を変更できるようにする

④ ペルソナ・トピックを複数アカウントに対応させるか？
   現状: 1アカウント前提
   将来: config/accounts/ ディレクトリで複数管理
```
