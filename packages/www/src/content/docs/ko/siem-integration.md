---
title: "SIEM 연동"
description: "Rediacc 감사 이벤트를 Splunk, OpenSearch, Sentinel 또는 OpenTelemetry 호환 SIEM으로 전달합니다"
category: "Guides"
tags:
  - security
  - operations
subcategory: operations
order: 15
language: ko
sourceHash: "224ef90a952edb1c"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

# SIEM 연동

Rediacc CLI를 통해 실행되는 모든 머신 수준 작업은 계정 서버의 `event_log` 테이블에 기록되는 동시에 OpenTelemetry 로그 레코드로 내보내집니다. 운영자는 계정 서버를 OpenTelemetry Collector에 연결하고, Collector가 원하는 SIEM(Splunk, OpenSearch, Microsoft Sentinel, AWS CloudWatch 등)으로 내보내도록 설정하여 이 레코드를 SIEM으로 보낼 수 있습니다.

이 페이지는 연동 방법을 다룹니다. 감사 이벤트 스키마와 Collector 참조 배포 구성은 공개 모노레포의 [`compose/otel-collector/`](https://github.com/rediacc/console/tree/main/compose/otel-collector)에 있습니다.

## 기록되는 내용

계정 서버의 `event_log` 테이블에 기록되는 모든 항목은 OTLP 로그 파이프라인에 미러링됩니다. 여기에는 계정 수준 이벤트(인증, 설정 스토리지, 라이선스)와 머신 수준 CLI 이벤트(`cli.repo.up`, `cli.repo.fork`, `cli.backup.push`, `cli.sync.upload`, `cli.term.session`, …)가 모두 포함됩니다.

이벤트 유형 어휘는 [`packages/shared/src/audit/event-schema.ts`](https://github.com/rediacc/console/blob/main/packages/shared/src/audit/event-schema.ts)에 정의된 닫힌 구분 유니온입니다. 새 이벤트 유형을 추가하려면 코드 변경이 필요하고 CI에서 게이트로 검증되므로, SIEM 규칙 작성자는 어휘가 안정적이라는 점을 전제로 삼을 수 있습니다.

각 로그 레코드에는 OpenTelemetry 시맨틱 속성이 붙습니다.

| 속성 | 의미 |
|---|---|
| `event.domain` | 고정값 `rediacc.audit` -- 관련 없는 로그를 걸러 내는 필터로 사용합니다 |
| `event.name` | 표준 이벤트 유형(예: `cli.repo.up`) |
| `event.source` | `cli`, `api`, `system`, … |
| `enduser.id` | 작업을 시작한 사용자 |
| `organization.id`, `team.id` | 조직/팀 범위 |
| `cloud.account.id` | Stripe 고객 ID |
| `subscription.id` | 라이선스 구독 |
| `audit.data.*` | 평탄화된 작업 페이로드 |

## 설정 방법

### 1. Collector 배포

```bash
git clone https://github.com/rediacc/console
cd console/compose/otel-collector
docker compose up -d
```

기본적으로 Collector는 `:4318`(OTLP/HTTP)에서 수신하고 `debug` 익스포터를 통해 자체 표준 출력에 기록합니다. 비용이 큰 대상으로 보내기 전에 파이프라인을 확인하는 데 유용합니다.

### 2. 계정 서버를 Collector에 연결

계정 서버 환경(Worker 시크릿 또는 온프레미스 서버의 프로세스 환경)에서:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

계정 서버를 재시작합니다. 감사 이벤트가 즉시 Collector로 흐르기 시작합니다.

### 3. SIEM 익스포터 설정

`compose/otel-collector/config.yaml`을 편집합니다. 이 파일에는 주석 처리된 익스포터 예시 네 가지가 들어 있습니다.

- **OpenSearch / Elasticsearch** -- `opensearch` 익스포터. `basicauth/opensearch` 확장이 필요합니다.
- **Splunk HEC** -- `splunk_hec` 익스포터. HEC 토큰과 인덱스가 필요합니다.
- **AWS CloudWatch Logs** -- `awscloudwatchlogs` 익스포터. Collector 환경에 IAM 자격 증명이 필요합니다.
- **Microsoft Sentinel** -- `azuremonitor` 익스포터를 통해 App Insights 연결 문자열을 사용합니다.

하나만 주석을 해제하고, `logs:` 파이프라인의 `exporters:` 목록에서 `debug`와 교체한 뒤 Collector를 재시작합니다.

로그를 받는 [OTel Collector contrib 익스포터](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/exporter)라면 무엇이든 동작합니다. 감사 파이프라인은 표준 OTLP 로그 레코드를 생성합니다.

## 탐지 콘텐츠

감사 이벤트는 [Sigma](https://sigmahq.io) 규칙 작성을 염두에 두고 설계되었습니다. Sigma 규칙은 벤더 중립적이며 `sigma-cli`를 통해 OpenSearch, Splunk, Sentinel 등의 네이티브 쿼리로 변환됩니다.

규칙 예시(예상치 못한 사용자의 `repo.fork` 실패):

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

## 컴플라이언스 관점

감사 파이프라인은 Rediacc 컴플라이언스 문서에서 참조하는 감사 로깅 요구 사항의 기반입니다.

- **GDPR 제30조** -- 처리 활동 기록
- **SOC 2 CC6.1 / CC7.2** -- 접근 로깅 및 모니터링
- **HIPAA 45 CFR 164.312(b)** -- 감사 제어
- **PCI DSS 요구 사항 10** -- 모든 접근 추적 및 모니터링
- **NIS2 제21조** -- 감사 이벤트는 사고 처리의 입력입니다. 사고 타임라인, 시계, 단계별 보고서는 별도의 기능입니다
- **DORA 제10조** -- 감사 이벤트는 탐지의 입력입니다. 이상 탐지기는 이 파이프라인이 아니라 포렌식 플로 기록을 대상으로 동작합니다

## 안정성

OTLP 전송은 보내고 잊는(fire-and-forget) 방식입니다. Collector가 중단되어도 Rediacc API 요청이 차단되거나 실패하는 일은 없으며, 모든 이벤트는 그와 무관하게 계정 서버의 `event_log` 테이블에 저장됩니다. Collector의 배치 및 재시도 동작과 함께 쓰면 어떤 SIEM 앞에 두어도 안전하게 운영할 수 있는 파이프라인이 됩니다.
