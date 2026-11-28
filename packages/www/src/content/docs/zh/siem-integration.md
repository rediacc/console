---
title: "SIEM 集成"
description: "将 Rediacc 审计事件路由到 Splunk、OpenSearch、Sentinel 或任何兼容 OpenTelemetry 的 SIEM"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: zh
sourceHash: "69ec0d3d122d13df"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# SIEM 集成

通过 Rediacc CLI 发出的每一次机器级操作，都会记录到账户服务器的 `event_log` 表，并同时作为 OpenTelemetry 日志记录发出。操作员将账户服务器指向 OpenTelemetry Collector，再由其导出到所选的 SIEM（Splunk、OpenSearch、Microsoft Sentinel、AWS CloudWatch 等），即可把这些记录送入 SIEM。

本页介绍如何完成配置。审计事件模式和 Collector 参考部署位于公开的 monorepo 中的 [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector)。

## 记录哪些内容

写入账户服务器 `event_log` 表的每一条记录 -- 既包括账户级事件（认证、配置存储、许可证），也包括机器级 CLI 事件（`cli.repo.up`、`cli.repo.fork`、`cli.backup.push`、`cli.sync.upload`、`cli.term.session`、…） -- 都会镜像到 OTLP 日志管道。

事件类型词汇表是一个封闭的可辨识联合类型，定义在 [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts)。新增事件类型需要修改代码，并受 CI 把关，因此 SIEM 规则作者可以依赖词汇表保持稳定。

每条日志记录都带有 OpenTelemetry 语义属性：

| 属性 | 含义 |
|---|---|
| `event.domain` | 固定为 `rediacc.audit` -- 按它过滤即可忽略无关日志 |
| `event.name` | 规范的事件类型（例如 `cli.repo.up`） |
| `event.source` | `cli`、`api`、`system`、… |
| `enduser.id` | 发起操作的用户 |
| `organization.id`、`team.id` | 组织/团队范围 |
| `cloud.account.id` | Stripe 客户 ID |
| `subscription.id` | 许可证订阅 |
| `audit.data.*` | 展平后的操作负载 |

## 配置步骤

### 1. 部署 Collector

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

默认情况下，Collector 监听 `:4318`（OTLP/HTTP），并通过 `debug` 导出器写入自己的 stdout -- 便于在路由到成本更高的系统之前先验证管道。

### 2. 将账户服务器指向 Collector

在账户服务器的环境中（Worker 的密钥，或本地部署服务器的进程环境）：

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

重启账户服务器后，审计事件会立即开始流向 Collector。

### 3. 配置 SIEM 导出器

编辑 `compose/otel-collector/config.yaml`。该文件自带四个已注释的导出器示例：

- **OpenSearch / Elasticsearch** -- `opensearch` 导出器，需要 `basicauth/opensearch` 扩展。
- **Splunk HEC** -- `splunk_hec` 导出器，需要 HEC 令牌和索引。
- **AWS CloudWatch Logs** -- `awscloudwatchlogs` 导出器，需要在 Collector 的环境中提供 IAM 凭据。
- **Microsoft Sentinel** -- 通过 `azuremonitor` 导出器，使用 App Insights 连接字符串。

只取消注释其中一个，在 `logs:` 管道的 `exporters:` 列表中用它替换 `debug`，然后重启 Collector。

任何接受日志的 [OTel Collector contrib 导出器](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter)都可以使用 -- 审计管道产生的是标准 OTLP 日志记录。

## 检测内容

审计事件专为编写 [Sigma](https://sigmahq.io) 规则而设计。Sigma 规则与厂商无关，可通过 `sigma-cli` 转换为 OpenSearch、Splunk、Sentinel 等的原生查询。

示例规则（来自意外用户的失败 `repo.fork`）：

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

## 合规态势

审计管道是 Rediacc 合规文档中所提审计日志要求的基础：

- **GDPR Art. 30** -- 处理活动记录
- **SOC 2 CC6.1 / CC7.2** -- 访问日志与监控
- **HIPAA 45 CFR 164.312(b)** -- 审计控制
- **PCI DSS Req 10** -- 跟踪并监控所有访问
- **NIS2 Art. 21** -- 审计事件是事件处理的输入；事件时间线、计时和分阶段报告是独立的功能
- **DORA Art. 10** -- 审计事件是检测的输入；异常检测器在机器和服务器上基于 forensics 流记录运行，而不是这条管道上

## 可靠性

OTLP 发送采用即发即弃方式 -- Collector 故障绝不会阻塞或导致 Rediacc API 请求失败，并且无论如何每个事件都仍会保存在账户服务器的 `event_log` 表中。结合 Collector 的批处理和重试机制，这使得该管道可以安全地部署在任何 SIEM 前面。
