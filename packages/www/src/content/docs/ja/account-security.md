---
title: アカウントセキュリティとAPI
description: 認証、APIトークン、セッション管理、および権限モデル。
category: Guides
order: 13
language: ja
sourceHash: "c4e24e7a3494b6f6"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

### 認証

Rediaccは複数の認証方法をサポートしています：

![Auth Flow](/img/account-auth-flow.svg)

- **パスワード**：従来のメールアドレス＋パスワードによるログイン
- **Magic Link**：メールリンクによるパスワードレスログイン（15分で期限切れ）
- **二要素認証（2FA）**：バックアップコード付きのTOTPベース

2FAが有効な場合、ログインにはパスワード（またはMagic Link）と6桁のTOTPコードの両方が必要です。

### APIトークン

APIトークンはマシン間の操作（CLIライセンスのアクティベーション、ステータス確認）を認証します。

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**スコープ：**
- `license:read` -- サブスクリプションとライセンスのステータスを照会
- `license:activate` -- マシンのアクティベーションとリポジトリライセンスの発行
- `subscription:read` -- サブスクリプション詳細の読み取り

**セキュリティ機能：**
- IPバインディング：最初のリクエストでトークンがそのIPアドレスに固定される
- チームスコーピング：トークンを特定のチームに制限可能
- 自動取り消し：作成者が組織から削除されるとトークンが取り消される

トークンの作成：
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### デバイスコードフロー

CLIはデバイスコードフローを使用してヘッドレスマシンで認証できます：

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

暗号化されたサーバー同期設定については、[Config Storage](/en/docs/config-storage) の完全ガイドを参照してください。Config Storageは以下を使用します：
- ゼロ知識暗号化（サーバーは平文を見ることがない）
- Passkeyベースの鍵導出（WebAuthn + PRF）
- リクエストごとのローテーション付きローテーショントークン

### セッションセキュリティ

| トークンタイプ | 有効期間 | ストレージ | 更新 |
|----------------|----------|------------|------|
| Access Token (JWT) | 15分 | HttpOnly Cookie | Refresh Tokenによる自動更新 |
| Refresh Token | 7日間 | HttpOnly Cookie | 使用ごとにローテーション |
| Elevated Session | 10分 | サーバーサイド | 再認証でトリガー |

昇格セッションは機密操作に必要です：パスワード変更、メールアドレス変更、2FAセットアップ、所有権移転、および管理者の破壊的操作。

### 権限モデル

Rediaccは3つの独立した権限レイヤーを使用します：

![Permission Flow](/img/account-permission-flow.svg)

**レイヤー1：システムロール** -- システム管理エンドポイントへのアクセスを決定します。

**レイヤー2：組織ロール** -- ユーザーが組織内で何ができるかを制御します（owner、admin、member）。

**レイヤー3：チームロール** -- 特定のチームリソースへのアクセスを限定します（team_admin、member）。組織のオーナーと管理者はチームロールのチェックをバイパスします。

すべてのAPIリクエストは、該当する全レイヤーを順番に通過します。チーム範囲のエンドポイントへのリクエストは、セッション認証、組織メンバーシップ、およびチームアクセスを満たす必要があります。

### アップデートチャンネル

CLIは2つのリリースチャンネルをサポートしています：
- **stable**（デフォルト）：7日間のソーク期間を経てedgeから昇格。保守的なアップグレード周期を希望する場合にこちらを選択
- **edge**：最新機能、リリースごとに更新

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
