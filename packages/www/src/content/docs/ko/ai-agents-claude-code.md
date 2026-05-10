---
title: Claude Code 설정 가이드
description: 자율적인 Rediacc 인프라 관리를 위한 Claude Code 구성 단계별 가이드.
category: Guides
order: 31
language: ko
---

Claude Code는 `rdc` CLI를 통해 Rediacc와 기본적으로 연동됩니다. 이 가이드에서는 설정, 권한 및 일반적인 워크플로를 다룹니다.

> **안전 우선**: 시크릿에 접근하는 에이전트를 연결하기 전에 [AI 에이전트 안전 및 가드레일](/en/docs/ai-agents-safety)을 읽어보세요. `rdc` 하에서 실행되는 Claude Code는 에이전트로 감지됩니다. 민감한 변경에는 `--current <previous-value>` (passwd 스타일 전제조건) 또는 `--rotate-secret` (감사된 승인된 교체)이 필요합니다. 사람과 에이전트 모두에게 동일하게 적용됩니다. 대화형 편집기, `--reveal` 및 직접 머신 SSH는 `REDIACC_ALLOW_CONFIG_EDIT`를 통해 명시적으로 열지 않는 한 기본적으로 거부됩니다. 전제조건이 실패하면 JSON 엔벨로프의 `errors[].next.options[].run` 필드가 에이전트에게 사용자에게 제안할 정확한 CLI 명령을 알려줍니다. 그대로 전달하세요.

## 빠른 설정

1. CLI 설치: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md 템플릿](/en/docs/agents-md-template)을 프로젝트 루트에 `CLAUDE.md`로 복사
3. 프로젝트 디렉터리에서 Claude Code 시작

Claude Code는 시작 시 `CLAUDE.md`를 읽어 모든 상호작용의 영구 컨텍스트로 사용합니다.

## CLAUDE.md 구성

프로젝트 루트에 배치하세요. 완전한 버전은 [AGENTS.md 템플릿](/en/docs/agents-md-template)을 참조하세요. 주요 섹션:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine query --name <machine> -o json
- Deploy: rdc repo up --name <repo> -m <machine> --yes
- Containers: rdc machine containers --name <machine> -o json
- Health: rdc machine health --name <machine> -o json
- SSH: rdc term connect -m <machine> [-r <repo>]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## 도구 권한

Claude Code는 `rdc` 명령 실행 권한을 요청합니다. Claude Code 설정에 다음을 추가하여 일반 작업을 미리 승인할 수 있습니다:

- `rdc machine query *` 허용 - 읽기 전용 상태 확인
- `rdc machine containers *` 허용 - 컨테이너 목록 조회
- `rdc machine health *` 허용 - 상태 확인
- `rdc config repository list` 허용 - 리포지토리 목록 조회

파괴적 작업(`rdc repo up`, `rdc repo delete`)의 경우 명시적으로 승인하지 않는 한 Claude Code가 항상 확인을 요청합니다.

## 예시 워크플로

### 인프라 상태 확인

```
사용자: "prod-1의 상태가 어떤가요?"

Claude Code 실행: rdc machine query --name prod-1 -o json
→ 머신 상태, 리포지토리, 컨테이너, 서비스 표시
```

### 리포지토리 배포

```
사용자: "mail 리포를 prod-1에 배포해 주세요"

Claude Code 실행: rdc repo up --name mail -m prod-1 --dry-run -o json
→ 실행될 내용 표시
Claude Code 실행: rdc repo up --name mail -m prod-1 --yes
→ 리포지토리 배포
```

### 컨테이너 문제 진단

```
사용자: "nextcloud 컨테이너가 비정상 상태인 이유가 뭔가요?"

Claude Code 실행: rdc machine containers --name prod-1 -o json --fields name,status,repository
→ 컨테이너 상태 목록
Claude Code 실행: rdc term connect -m prod-1 -c "docker logs nextcloud-app --tail 50"
→ 최근 로그 확인
```

### 파일 동기화

```
사용자: "로컬 설정을 mail 리포에 업로드해 주세요"

Claude Code 실행: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ 동기화될 파일 표시
Claude Code 실행: rdc repo sync upload -m prod-1 -r mail -l ./config
→ 파일 동기화
```

## 팁

- Claude Code는 non-TTY를 자동 감지하여 JSON 출력으로 전환하므로 대부분의 경우 `-o json`을 지정할 필요가 없습니다
- `rdc agent capabilities`를 사용하면 Claude Code가 모든 사용 가능한 명령을 검색할 수 있습니다
- `rdc agent schema "command name"`을 사용하면 인수/옵션에 대한 상세 정보를 얻을 수 있습니다
- `--fields` 플래그를 사용하면 특정 데이터만 필요할 때 컨텍스트 창 사용량을 줄일 수 있습니다
