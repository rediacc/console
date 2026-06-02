---
title: 계정 보안 및 API
description: 인증, API 토큰, 세션 관리 및 권한 모델.
category: Guides
order: 13
language: ko
sourceHash: "dcd061b971573573"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

### 인증

Rediacc는 여러 가지 인증 방법을 지원합니다:

![Auth Flow](/img/account-auth-flow.svg)

- **비밀번호**: 이메일과 비밀번호를 사용하는 전통적인 로그인
- **매직 링크**: 이메일 링크를 통한 비밀번호 없는 로그인 (15분 만료)
- **2단계 인증(2FA)**: 백업 코드가 포함된 TOTP 기반 인증

2FA가 활성화된 경우 로그인 시 비밀번호(또는 매직 링크)와 6자리 TOTP 코드가 모두 필요합니다.

### API 토큰

API 토큰은 머신 간 작업(CLI 라이선스 활성화, 상태 확인)에 사용되는 인증 수단입니다.

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**범위:**
- `license:read` -- 구독 및 라이선스 상태 조회
- `license:activate` -- 머신 활성화 및 리포지토리 라이선스 발급
- `subscription:read` -- 구독 세부 정보 읽기

**보안 기능:**
- IP 바인딩: 첫 번째 요청 시 해당 IP 주소에 토큰이 잠깁니다
- 팀 범위 지정: 특정 팀으로 토큰을 제한할 수 있습니다
- 자동 취소: 생성자가 조직에서 제거되면 토큰이 자동으로 취소됩니다

토큰 생성:
```bash
# 포털에서: API Tokens > Create
# 토큰 값은 한 번만 표시됩니다. 안전하게 보관하세요
```

### 디바이스 코드 흐름

CLI는 디바이스 코드 흐름을 사용하여 헤드리스 머신에서 인증할 수 있습니다:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# 표시: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# 승인 후 CLI가 자격 증명을 자동으로 수신합니다
```

### 설정 저장소

암호화된 서버 동기화 설정에 대한 전체 가이드는 [설정 저장소](/en/docs/config-storage)를 참조하세요. 설정 저장소는 다음을 사용합니다:
- 제로 지식 암호화 (서버가 평문을 볼 수 없음)
- 패스키 기반 키 파생 (WebAuthn + PRF)
- 요청별 교체를 통한 회전 토큰

### 세션 보안

| 토큰 유형 | 수명 | 저장 방식 | 갱신 |
|-----------|------|----------|------|
| 액세스 토큰 (JWT) | 15분 | HttpOnly 쿠키 | 갱신 토큰으로 자동 갱신 |
| 갱신 토큰 | 7일 | HttpOnly 쿠키 | 사용할 때마다 교체 |
| 승격된 세션 | 10분 | 서버 측 | 재인증 시 트리거 |

승격된 세션은 민감한 작업(비밀번호 변경, 이메일 변경, 2FA 설정, 소유권 이전, 파괴적 관리 작업)에 필요합니다.

### 권한 모델

Rediacc는 세 가지 독립적인 권한 레이어를 사용합니다:

![Permission Flow](/img/account-permission-flow.svg)

**레이어 1: 시스템 역할** -- 시스템 관리 엔드포인트에 대한 접근을 결정합니다.

**레이어 2: 조직 역할** -- 조직 내에서 사용자가 할 수 있는 작업을 제어합니다 (owner, admin, member).

**레이어 3: 팀 역할** -- 특정 팀 리소스에 대한 접근 범위를 지정합니다 (team_admin, member). 조직 소유자와 관리자는 팀 역할 검사를 우회합니다.

모든 API 요청은 해당하는 모든 레이어를 순서대로 통과합니다. 팀 범위 엔드포인트에 대한 요청은 세션 인증, 조직 구성원 자격, 팀 접근을 모두 충족해야 합니다.

### 업데이트 채널

CLI는 두 가지 릴리스 채널을 지원합니다:
- **stable** (기본값): 7일 소크 기간 후 edge에서 승격됩니다. 보수적인 업그레이드 주기를 원할 때 선택하세요
- **edge**: 지속적으로 배포되는 프로덕션으로, main에 병합될 때마다 업데이트됩니다

```bash
rdc update --channel edge      # edge로 전환
rdc update --channel stable    # stable로 돌아가기
rdc update --status            # 현재 채널 표시
```

### AI 에이전트를 위한 CLI 보안 자세

`rdc`를 호출하는 코딩 에이전트는 실제 위협 표면이므로 별도의 주체로 취급합니다. 모든 `rdc` 호출은 시작 시 환경 신호(CLAUDECODE, GEMINI_CLI, COPILOT_CLI, CURSOR_TRACE_ID, REDIACC_AGENT)와 Linux `/proc` 조상 탐색을 기반으로 **human** 또는 **agent**로 분류됩니다. 감지는 최선의 노력입니다. 결연한 래퍼는 환경 변수를 스푸핑할 수 있으므로 조상이 중요합니다. 에이전트는 축소된 권한 집합을 받습니다. 민감한 설정 변경에는 지식 게이트(`--current <old>`)가 필요하며, 조상이 검증된 `REDIACC_ALLOW_CONFIG_EDIT` 재정의 없이는 대화형 편집기가 거부되고 모든 표시 명령에서 `--reveal`이 차단됩니다. 모든 결정(허용, 거부, 또는 `--reveal` 부여)은 `~/.config/rediacc/audit.log.jsonl`에 해시 체인 JSONL 행으로 기록됩니다. `rdc config audit verify`를 실행하여 체인 무결성을 확인하세요.

에이전트가 할 수 있는 작업과 할 수 없는 작업의 전체 매트릭스, 지식 게이트 예제, 범위 재정의 메커니즘은 [AI 에이전트 안전 및 가드레일](/en/docs/ai-agents-safety)을 참조하세요.
