---
title: "サブスクリプションとライセンス"
description: "ローカルデプロイメントのサブスクリプションとマシンライセンスを管理します。"
category: "Guides"
order: 7
language: ja
sourceHash: "84215f54750ac4a4"
---

# サブスクリプションとライセンス

ローカルデプロイメントで稼働するマシンは、プランベースのリソース制限を適用するためにサブスクリプションライセンスが必要です。CLIはSSH経由で署名済みライセンスブロブをリモートマシンに自動的に配信します。サーバー側での手動アクティベーションやクラウド接続は不要です。

## 概要

1. `rdc subscription login` でログイン（ブラウザが開いて認証）
2. 任意のマシンコマンドを使用 — ライセンスは自動的に処理されます

マシンを対象とするコマンド（`rdc machine info`、`rdc repo up` など）を実行すると、CLIはマシンに有効なライセンスがあるかを自動的に確認します。ない場合は、アカウントサーバーからライセンスを取得し、SSH経由で配信します。

## ログイン

```bash
rdc subscription login
```

デバイスコードフローによる認証のためにブラウザを開きます。承認後、CLIはAPIトークンを `~/.config/rediacc/api-token.json` にローカル保存します。

| オプション | 必須 | デフォルト | 説明 |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | APIトークン（ブラウザフローをスキップ） |
| `--server <url>` | No | `https://account.rediacc.com` | アカウントサーバーURL |

## ステータスの確認

```bash
# アカウントレベルのステータス（プラン、マシン）
rdc subscription status

# 特定のマシンのライセンス詳細を含める
rdc subscription status -m hostinger
```

アカウントサーバーからサブスクリプションの詳細を表示します。`-m` を指定すると、マシンにSSH接続して現在のライセンス情報も表示します。

## ライセンスの強制リフレッシュ

```bash
rdc subscription refresh -m <machine>
```

指定されたマシンにライセンスを強制的に再発行・配信します。通常これは不要です — ライセンスは通常のCLI使用中に50分ごとに自動リフレッシュされます。

## 仕組み

1. **ログイン** によりワークステーションにAPIトークンが保存されます
2. **任意のマシンコマンド** がSSH経由の自動ライセンスチェックをトリガーします
3. リモートのライセンスが存在しないか50分以上経過している場合、CLIは：
   - SSH経由でリモートマシンのハードウェアIDを読み取り
   - アカウントAPIを呼び出して新しいライセンスを発行
   - マシンライセンスとサブスクリプションブロブの両方をSSH経由でリモートに配信
4. 50分間のインメモリキャッシュにより、同一セッション内の冗長なSSHラウンドトリップを防止します

各マシンのアクティベーションはサブスクリプションのスロットを1つ消費します。スロットを解放するには、アカウントポータルからマシンを非アクティブ化してください。

## 猶予期間とデグレーション

ライセンスが期限切れとなり、3日間の猶予期間内にリフレッシュできない場合、マシンのリソース制限はCommunityプランのデフォルトにデグレードされます。ライセンスがリフレッシュされると（接続を復旧して任意の `rdc` コマンドを実行）、元のプラン制限が即座に復元されます。

## プラン制限

### フローティングライセンス制限

| プラン | Floating Licenses |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### リソース制限

| リソース | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### 機能の利用可否

| 機能 | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
