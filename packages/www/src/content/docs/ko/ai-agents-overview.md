---
title: AI 에이전트 통합 개요
description: "Claude Code, Cursor, Cline이 rdc를 통해 Rediacc 인프라를 관리하는 방법: JSON 출력, 에이전트 내부 검사, 안전 가드레일."
category: Guides
order: 30
language: ko
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

`rdc`는 설계부터 에이전트를 고려했습니다. Claude Code, Cursor, Cline 등 서브셸에서 `rdc`를 호출하는 AI 어시스턴트는 구조화된 JSON 출력, 머신 가독 오류, 그리고 자율적인 Rediacc 인프라 관리에 필요한 가드레일을 그대로 활용할 수 있습니다. 통합 방식을 소개합니다.

## 셀프호스팅과 AI 에이전트가 잘 맞는 이유

Rediacc의 아키텍처는 에이전트에 잘 맞습니다.

- **CLI 우선**: 모든 작업은 `rdc` 명령어로 수행되며, GUI가 필요하지 않습니다.
- **SSH 기반**: 에이전트가 학습 데이터에서 가장 잘 알고 있는 프로토콜입니다.
- **JSON 출력**: 모든 명령어는 일관된 봉투 형식으로 `--output json`을 지원합니다.
- **Docker 격리**: 각 레포지토리는 자체 데몬과 네트워크 네임스페이스를 갖습니다.
- **스크립트 가능**: `--yes`는 확인 프롬프트를 건너뛰고, `--dry-run`은 파괴적 작업을 미리 확인합니다.

## 통합 방식

### 1. AGENTS.md / CLAUDE.md 템플릿

가장 빠르게 시작할 수 있는 방법입니다. [AGENTS.md 템플릿](/en/docs/agents-md-template)을 프로젝트 루트에 복사하세요.

- Claude Code용 `CLAUDE.md`
- Cursor용 `.cursorrules`
- Windsurf용 `.windsurfrules`

파일을 추가하면 에이전트는 전체 명령어 레퍼런스, 아키텍처 컨텍스트, 그리고 추측 없이 작업하는 데 필요한 관례를 바로 갖추게 됩니다.

### 2. JSON 출력 파이프라인

에이전트가 서브셸에서 `rdc`를 호출하면 출력이 자동으로 JSON으로 전환됩니다(non-TTY 감지). 모든 JSON 응답은 일관된 봉투 형식을 사용합니다.

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

오류 응답에는 `retryable`과 `guidance` 필드가 포함됩니다.

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. 에이전트 기능 탐색

`rdc agent` 서브커맨드는 구조화된 내부 검사 기능을 제공합니다.

```bash
# 모든 명령어와 인수 및 옵션 목록 확인
rdc agent capabilities

# 특정 명령어의 상세 스키마 확인
rdc agent schema --command "machine query"

# JSON stdin으로 명령어 실행
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## 에이전트용 주요 플래그

| 플래그 | 목적 |
|------|---------|
| `--output json` / `-o json` | 머신 가독 JSON 출력 |
| `--yes` / `-y` | 대화형 확인 건너뜀 |
| `--quiet` / `-q` | 안내용 stderr 출력 억제 |
| `--fields name,status` | 특정 필드로 출력 제한 |
| `--dry-run` | 파괴적 작업을 실행하지 않고 미리 확인 |

## 안전성 및 가드레일

CLI는 터미널 앞의 사람과 에이전트를 동일하게 처리하지 않습니다. 민감한 작업은 현재 상태를 이미 파악하고 있다는 증명(`--current` 플래그)이 필요하고, 대화형 편집기 흐름은 기본적으로 거부되며, 모든 거부는 감사 로그에 기록됩니다. [AI 에이전트 안전성 및 가드레일](/en/docs/ai-agents-safety) 문서에는 전체 방화벽 테이블, 지식 게이트 모델, `REDIACC_ALLOW_CONFIG_EDIT` 스코프 재정의, 해시 체인 감사 로그가 설명되어 있습니다.

## 다음 단계

- [AI 에이전트 안전성 및 가드레일](/en/docs/ai-agents-safety), 에이전트가 할 수 있는 것과 없는 것, 지식 게이트, 감사 로그
- [Claude Code 설정 가이드](/en/docs/ai-agents-claude-code), 단계별 Claude Code 설정 방법
- [Cursor 설정 가이드](/en/docs/ai-agents-cursor), Cursor IDE 통합
- [JSON 출력 참조](/en/docs/ai-agents-json-output), 전체 JSON 출력 문서
- [AGENTS.md 템플릿](/en/docs/agents-md-template), 복사해서 바로 쓰는 에이전트 설정 템플릿
