---
title: "SIEM連携"
description: "Rediaccの監査イベントを、Splunk、OpenSearch、Sentinel、またはOpenTelemetry互換のSIEMへ転送します"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: ja
sourceHash: "224ef90a952edb1c"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# SIEM連携

Rediacc CLI経由で発行されるマシンレベルの操作は、すべてアカウントサーバーの`event_log`テーブルに記録されると同時に、OpenTelemetryのログレコードとして送信されます。アカウントサーバーをOpenTelemetry Collectorに向け、そこから任意のSIEM（Splunk、OpenSearch、Microsoft Sentinel、AWS CloudWatchなど）へエクスポートすることで、オペレーターはこれらのレコードをSIEMに取り込めます。

このページでは、その設定方法を説明します。監査イベントのスキーマとCollectorのリファレンス構成は、公開モノレポの[`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector)にあります。

## 記録される内容

アカウントサーバーの`event_log`テーブルに書き込まれるエントリは、すべてOTLPログパイプラインにミラーされます。これにはアカウントレベルのイベント（認証、設定ストレージ、ライセンス）とマシンレベルのCLIイベント（`cli.repo.up`、`cli.repo.fork`、`cli.backup.push`、`cli.sync.upload`、`cli.term.session`、…）の両方が含まれます。

イベントタイプの語彙は、[`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts)で定義された閉じた判別共用体です。新しいイベントタイプの追加にはコード変更が必要で、CIでゲートされるため、SIEMルールの作成者は語彙が安定していることを前提にできます。

各ログレコードには、OpenTelemetryのセマンティック属性が付きます。

| 属性 | 意味 |
|---|---|
| `event.domain` | 固定値`rediacc.audit` -- 無関係なログを除外するためのフィルタに使います |
| `event.name` | 正規のイベントタイプ（例: `cli.repo.up`） |
| `event.source` | `cli`、`api`、`system`、… |
| `enduser.id` | 操作を開始したユーザー |
| `organization.id`、`team.id` | 組織・チームのスコープ |
| `cloud.account.id` | StripeのカスタマーID |
| `subscription.id` | ライセンスのサブスクリプション |
| `audit.data.*` | フラット化された操作ペイロード |

## セットアップ

### 1. Collectorをデプロイする

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

デフォルトでは、Collectorは`:4318`（OTLP/HTTP）で待ち受け、`debug`エクスポーター経由で自身の標準出力に書き込みます。コストのかかる転送先へ流す前に、パイプラインを確認するのに便利です。

### 2. アカウントサーバーをCollectorに向ける

アカウントサーバーの環境（Worker のシークレット、またはオンプレミスサーバーのプロセス環境）で:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

アカウントサーバーを再起動します。監査イベントは直ちにCollectorへ流れ始めます。

### 3. SIEMエクスポーターを設定する

`compose/otel-collector/config.yaml`を編集します。このファイルには、コメントアウトされた4つのエクスポーター例が含まれています。

- **OpenSearch / Elasticsearch** -- `opensearch`エクスポーター。`basicauth/opensearch`拡張が必要です。
- **Splunk HEC** -- `splunk_hec`エクスポーター。HECトークンとインデックスが必要です。
- **AWS CloudWatch Logs** -- `awscloudwatchlogs`エクスポーター。Collectorの環境にIAM認証情報が必要です。
- **Microsoft Sentinel** -- `azuremonitor`エクスポーター経由。App Insightsの接続文字列を使います。

1つだけコメントを外し、`logs:`パイプラインの`exporters:`リストで`debug`と入れ替えてから、Collectorを再起動します。

ログを受け付ける[OTel Collector contribのエクスポーター](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter)であれば、どれでも動作します。監査パイプラインは標準のOTLPログレコードを生成します。

## 検知コンテンツ

監査イベントは、[Sigma](https://sigmahq.io)ルールの作成を想定して設計されています。Sigmaルールはベンダー中立で、`sigma-cli`によってOpenSearch、Splunk、Sentinelなどのネイティブクエリに変換できます。

ルールの例（想定外のユーザーによる`repo.fork`の失敗）:

```yaml
title: Unexpected Rediacc repo fork
detection:
  selection:
    event.domain: rediacc.audit
    event.name: cli.repo.fork
    audit.data.success: false
  condition: selection
level: medium
```

## コンプライアンス上の位置づけ

監査パイプラインは、Rediaccのコンプライアンスドキュメントで参照されている監査ログ要件の基盤です。

- **GDPR 第30条** -- 処理活動の記録
- **SOC 2 CC6.1 / CC7.2** -- アクセスログとモニタリング
- **HIPAA 45 CFR 164.312(b)** -- 監査制御
- **PCI DSS 要件10** -- すべてのアクセスの追跡と監視
- **NIS2 第21条** -- 監査イベントはインシデント対応への入力となります。インシデントタイムライン、クロック、段階的レポートは別の機能です
- **DORA 第10条** -- 監査イベントは検出への入力となります。異常検知器はこのパイプラインではなく、フォレンジクスのフローレコードを対象に動作します

## 信頼性

OTLPの送信はファイア・アンド・フォーゲットです。Collectorが停止しても、Rediaccへのリクエストがブロックされたり失敗したりすることはなく、すべてのイベントはそれと無関係にアカウントサーバーの`event_log`テーブルへ保存されます。Collectorのバッチ処理とリトライの動作と合わせて、このパイプラインはどのSIEMの手前に置いても安全に運用できます。
