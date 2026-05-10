---
title: "릴리스 채널"
description: "Edge와 Stable 릴리스 채널, 차이점, 선택 방법을 이해합니다."
category: "Concepts"
order: 2
language: ko
---

Rediacc는 두 가지 릴리스 채널을 통해 업데이트를 게시합니다: **Stable**과 **Edge**. 각 채널은 다른 대상을 위해 제공되며 서로 다른 트레이드오프가 있습니다.

## Stable 채널

Stable은 모든 사용자의 기본 채널입니다. 릴리스는 보고된 문제 없이 7일 소크 기간을 거친 후 Edge에서 프로모션됩니다.

- 보수적인 업그레이드 주기를 선호하고 유료 플랜에 액세스하려는 경우 권장됩니다.
- Edge에서 7일 테스트 후 배포됩니다.
- 중요한 경우 핫픽스를 직접 푸시할 수 있습니다.
- 도메인: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Edge 채널

Edge는 main에 병합된 직후 모든 변경 사항을 받습니다. 최신 버전의 소프트웨어로, 지속적으로 배포됩니다.

- 매 main 병합 시 릴리스되는 지속적으로 배포된 프로덕션
- 2X Community 플랜 제한 (아래 표 참조)
- 무료 영구 사용. Edge에서는 유료 플랜 사용 불가.
- Stable과 별도의 계정. 채널 간 데이터가 이전되지 않습니다.
- 도메인: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## 비교

| | Stable | Edge |
|---|---|---|
| **배포 주기** | 7일 소크 후 | main에 매 병합 시 |
| **안정성** | 7일 테스트됨 | 프로덕션, 지속적으로 배포됨 |
| **Community 플랜 제한** | 10 GB 리포지터리, 500건/월, 머신 2대 | 20 GB 리포지터리, 1,000건/월, 머신 4대 |
| **유료 플랜** | 사용 가능 (Professional, Business, Enterprise) | 사용 불가 |
| **계정** | 독립적 | 독립적 (Stable과 분리) |
| **적합한 대상** | 프로덕션, 유료 워크로드 | 프로덕션, 사이드 프로젝트, 얼리 액세스 |

## Edge 2X 제한

Edge의 Community 플랜 사용자는 무료로 두 배의 리소스 제한을 받습니다.

| 리소스 | Stable Community | Edge Community |
|---|---|---|
| 리포지터리 크기 | 10 GB | 20 GB |
| 월별 라이선스 발급 | 500 | 1,000 |
| 머신 활성화 | 2 | 4 |

더 높은 제한이나 유료 플랜 기능이 필요하면 Stable 채널에서 계정을 만들고 업그레이드하세요.

## 분리된 계정

Edge와 Stable은 별도의 데이터베이스를 사용하는 별도의 인프라에서 실행됩니다. Edge에서 만든 계정은 Stable에 존재하지 않으며, 그 반대도 마찬가지입니다. 채널 간 마이그레이션 경로가 없습니다. Edge에서 시작하고 나중에 유료 플랜을 원하면 Stable에서 새 계정을 만들어야 합니다.

## 프로모션 작동 방식

1. main 브랜치에 매 병합 시 Edge에 즉시 배포됩니다.
2. 7일 동안 문제가 없으면 Edge가 자동으로 Stable로 프로모션됩니다.
3. 중요한 핫픽스는 두 채널에 동시에 푸시될 수 있습니다.

즉 Stable은 항상 최대 7일 뒤처집니다. 소크 기간은 Edge에서 Stable로 전파되기 전에 회귀를 포착합니다.

## 어느 채널을 선택해야 하나요?

**Stable을 선택하세요:**
- 7일 소크 기간이 있는 보수적인 업그레이드 주기를 선호하는 경우
- 유료 플랜(Professional, Business, Enterprise)이 필요한 경우
- 최신 기능보다 최대 안정성을 선호하는 경우

**Edge를 선택하세요:**
- 새 기능을 일찍 시험해보고 싶은 경우
- 플랫폼을 평가 중인 경우
- 사이드 프로젝트를 위한 넉넉한 무료 제한을 원하는 경우
- 최신의 덜 테스트된 코드를 사용하는 것에 익숙한 경우

## 설치

각 채널에서 설치하는 명령(패키지 관리자 구성 및 Docker 태그 포함)은 [설치](/ko/docs/installation)를 참조하세요.

## CLI 채널 관리

CLI는 설치 또는 로그인 중에 구성된 채널을 자동으로 사용합니다. 채널을 전환하려면:

```bash
rdc update --channel edge      # Edge로 전환
rdc update --channel stable    # Stable로 전환
```

`rdc subscription login`을 실행하고 Edge 리전을 선택하면 CLI가 자동으로 Edge 업데이트 채널을 구성합니다. 수동 `--channel` 플래그가 필요하지 않습니다.
