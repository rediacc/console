---
title: Cursor 설정 가이드
description: .cursorrules 및 터미널 통합을 사용하여 Cursor IDE를 Rediacc 인프라와 연동하도록 구성하기.
category: Guides
order: 32
language: ko
sourceHash: "b5e835461de00400"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

요약: `.cursorrules`는 Rediacc 컨텍스트를 Cursor AI에 로드하고, 터미널을 통해 실제 머신에 `rdc` 명령을 실행할 수 있습니다.

## 빠른 설정

1. CLI 설치: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md 템플릿](/en/docs/agents-md-template)을 프로젝트 루트에 `.cursorrules`로 복사
3. Cursor에서 프로젝트 열기

Cursor는 시작 시 `.cursorrules`를 읽습니다. 중요한 점은 컨텍스트 윈도우 한계가 있으므로, 일반적인 보일러플레이트보다는 실제 사용하는 머신과 레포지토리 정보에 집중해서 파일을 작성하는 것이 좋습니다.

## .cursorrules 구성

Rediacc 인프라 컨텍스트를 담은 `.cursorrules`를 프로젝트 루트에 생성하세요. 완전한 버전은 [AGENTS.md 템플릿](/en/docs/agents-md-template)을 참조하세요.

포함해야 할 주요 섹션:

- CLI 도구 이름(`rdc`) 및 설치 방법
- `--output json` 플래그가 포함된 공통 명령
- 아키텍처 개요 (리포지토리 격리, Docker 데몬)
- 용어 규칙 (어댑터, 모드 아님)

## 터미널 통합

Cursor는 통합 터미널을 통해 `rdc` 명령을 실행할 수 있습니다. 일반적인 패턴:

### 상태 확인

Cursor에 요청: *"내 프로덕션 서버의 상태를 확인해 주세요"*

Cursor가 터미널에서 실행:
```bash
rdc machine query --name prod-1 -o json
```

### 변경사항 배포

Cursor에 요청: *"업데이트된 nextcloud 설정을 배포해 주세요"*

Cursor가 터미널에서 실행:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### 로그 확인

Cursor에 요청: *"최근 mail 컨테이너 로그를 보여주세요"*

Cursor가 터미널에서 실행:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## 워크스페이스 설정

팀 프로젝트의 경우 Rediacc 관련 Cursor 설정을 `.cursor/settings.json`에 추가하세요:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## 팁

- Cursor의 Composer 모드는 다단계 인프라 작업에 적합합니다
- Cursor 채팅에서 `@terminal`을 사용하면 최근 터미널 출력을 참조할 수 있습니다
- `rdc agent capabilities` 명령은 Cursor에게 전체 명령 참조를 제공합니다
- AI 도구 간 최대 호환성을 위해 `.cursorrules`와 `CLAUDE.md` 파일을 함께 사용하세요
