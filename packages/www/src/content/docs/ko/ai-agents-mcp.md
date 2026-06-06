---
title: MCP 서버 설정
description: Model Context Protocol (MCP) 서버를 사용하여 AI 에이전트를 Rediacc 인프라에 연결하기.
category: Guides
order: 33
language: ko
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## 개요

참고로, `rdc mcp serve` 명령은 AI 에이전트가 인프라를 관리하는 데 사용할 수 있는 로컬 MCP (Model Context Protocol) 서버를 시작합니다. 서버는 stdio 전송을 사용하며, AI 에이전트가 이를 서브프로세스로 생성하고 JSON-RPC를 통해 통신합니다.

**사전 요구사항:** `rdc`가 설치되고 최소 하나의 머신으로 구성되어 있어야 합니다.

## Claude Code

프로젝트의 `.mcp.json`에 추가하세요:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

또는 명명된 설정과 함께:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

설정 열기 → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

## 사용 가능한 도구

### 읽기 도구 (안전, 부작용 없음)

| 도구 | 설명 |
|------|------|
| `machine_query` | 머신의 시스템 정보, 컨테이너, 서비스 및 리소스 사용량 조회 |
| `machine_containers` | 상태, 상태 확인, 리소스 사용량, 레이블 및 자동 라우트 도메인과 함께 Docker 컨테이너 목록 조회 |
| `machine_services` | rediacc가 관리하는 systemd 서비스 목록 조회 (이름, 상태, 서브 상태, 재시작 횟수, 메모리, 소유 리포지토리) |
| `machine_repos` | 배포된 리포지토리 목록 조회 (이름, GUID, 크기, 마운트 상태, Docker 상태, 컨테이너 수, 디스크 사용량, 수정 날짜, Rediaccfile 존재 여부) |
| `machine_health` | 머신 상태 확인 실행 (시스템, 컨테이너, 서비스, 스토리지) |
| `machine_list` | 구성된 모든 머신 목록 조회 |
| `config_repositories` | 이름과 GUID 매핑과 함께 구성된 리포지토리 목록 조회 |
| `config_show_infra` | 머신의 인프라 구성 표시 (기본 도메인, 공개 IP, TLS, Cloudflare 존) |
| `config_providers` | 머신 프로비저닝을 위해 구성된 클라우드 공급자 목록 조회 |
| `agent_capabilities` | 인수와 옵션이 포함된 모든 rdc CLI 명령 목록 조회 |
| `repo_secret_list` | 리포지토리의 시크릿 이름 및 전달 모드 목록 조회 (값 및 다이제스트는 절대 반환하지 않음). 읽기 안전. |
| `repo_secret_get` | 시크릿의 SHA-256 다이제스트 및 전달 모드 조회. 평문 값은 설계상 절대 반환되지 않습니다. 시크릿이 존재하는지 또는 교체되었는지 확인할 때 사용하세요. |

### 쓰기 도구 (파괴적)

| 도구 | 설명 |
|------|------|
| `repo_create` | 머신에 새 암호화된 리포지토리 생성 |
| `repo_up` | 리포지토리 배포/업데이트 (Rediaccfile up 실행, 컨테이너 시작). 처음 배포하거나 pull 후에는 `mount` 사용 |
| `repo_down` | 리포지토리 컨테이너 중지. 기본적으로 마운트 해제하지 않습니다. LUKS 컨테이너도 닫으려면 `unmount` 사용 |
| `repo_delete` | 리포지토리 삭제 (컨테이너, 볼륨, 암호화된 이미지 제거). 자격 증명은 복구를 위해 보관됩니다 |
| `repo_fork` | 새 GUID와 networkId로 CoW 포크 생성 (완전히 독립적인 복사본, 온라인 포킹 지원) |
| `backup_push` | 리포지토리 백업을 스토리지 또는 다른 머신으로 푸시 (동일 GUID -- 백업/마이그레이션, 포크 아님) |
| `backup_pull` | 스토리지 또는 머신에서 리포지토리 백업 풀. 풀 후 `repo_up` (mount=true)으로 배포 |
| `machine_provision` | OpenTofu를 사용하여 클라우드 공급자에 새 머신 프로비저닝 |
| `machine_deprovision` | 클라우드로 프로비저닝된 머신을 제거하고 설정에서 삭제 |
| `config_add_provider` | 머신 프로비저닝을 위한 클라우드 공급자 설정 추가 |
| `config_remove_provider` | 클라우드 공급자 설정 제거 |
| `term_exec` | SSH를 통해 원격 머신에서 명령 실행 |

## 예시 워크플로

**머신 상태 확인:**
> "내 프로덕션 머신의 상태가 어떤가요?"

에이전트가 `machine_query`를 호출 → 시스템 정보, 실행 중인 컨테이너, 서비스 및 리소스 사용량을 반환합니다.

**애플리케이션 배포:**
> "스테이징 머신에 gitlab을 배포해 주세요"

에이전트가 `name: "gitlab"` 및 `machine: "staging"`으로 `repo_up`을 호출 → 리포지토리를 배포하고 성공/실패를 반환합니다.

**서비스 오류 디버깅:**
> "nextcloud가 느립니다, 문제를 파악해 주세요"

에이전트가 `machine_health` → `machine_containers` → `term_exec`를 호출하여 로그를 읽고 → 문제를 식별하고 수정 방법을 제안합니다.

## 설정 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--config <name>` | (기본 설정) | 모든 명령에 사용할 명명된 설정 |
| `--timeout <ms>` | `120000` | 기본 명령 타임아웃 (밀리초) |
| `--allow-grand` | 꺼짐 | grand (포크가 아닌) 리포지토리에 대한 파괴적 작업 허용 |

## 보안

MCP 서버는 두 가지 보호 레이어를 적용합니다:

### 포크 전용 모드 (기본값)

기본적으로 서버는 **포크 전용 모드**로 실행됩니다. 쓰기 도구(`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`)는 포크 리포지토리에서만 작동할 수 있습니다. Grand (원본) 리포지토리는 에이전트 수정으로부터 보호됩니다. 이는 설계에 의한 동작입니다.

> **리포별 시크릿은 설계상 CLI 전용입니다.** `repo_secret_set`과 `repo_secret_unset`은 의도적으로 MCP 도구로 노출되지 않습니다. 쓰기에는 `--current <previous-value>` 전제조건(또는 검증되지 않은 교체를 승인하는 `--rotate-secret`)이 필요하며, 이 절차는 사람이 직접 확인해야 합니다. 시크릿 교체를 제안해야 하는 에이전트는 `repo_secret_get`을 호출하여 다이제스트를 확인한 다음, JSON 오류 엔벨로프의 `next.options[].run` 필드를 통해 운영자 대상 CLI 명령을 사용자에게 전달해야 합니다. 전체 패턴은 [AI 에이전트 안전](/en/docs/ai-agents-safety#structured-next-action-hints)을 참조하고, 사용자 대상 방법은 [리포지토리 § 시크릿](/en/docs/repositories#secrets)을 참조하세요.

에이전트가 grand 리포지토리를 수정할 수 있게 하려면 `--allow-grand`로 시작하세요:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

`REDIACC_ALLOW_GRAND_REPO` 환경 변수를 단일 리포 이름, 쉼표로 구분된 리포 이름 목록(예: `repo1,repo2,repo3`) 또는 모든 리포에 대해 `*`로 설정할 수도 있습니다. 항목 주위의 공백은 무시되므로 `repo1, repo2`도 작동합니다. 머신 수준 접근(리포 없이 `term connect -m <machine>`)은 여전히 `*`를 요구하며 리포 이름 목록으로는 잠금을 해제할 수 없습니다.

### 리포별 SSH 키 및 서버 측 샌드박스

각 리포지토리는 자체 SSH 키 쌍을 가집니다. 공개 키는 모든 SSH 세션을 `renet sandbox-gateway <repo-name>`을 통해 강제 실행하는 `command=` 접두사와 함께 `authorized_keys`에 배포됩니다. 이는 VS Code를 포함한 모든 클라이언트가 우회할 수 없는 서버 측 ForceCommand입니다.

**작동 방식:**
1. `rdc repo create` 또는 `rdc repo fork`가 리포당 고유한 ed25519 키 쌍을 생성합니다
2. 공개 키가 `command="renet sandbox-gateway <name>"`과 함께 원격에 배포됩니다
3. 해당 키를 사용하는 모든 SSH 연결은 다음을 적용하는 게이트웨이를 통과합니다:
   - **Landlock LSM**, 리포의 마운트 경로에 대한 커널 수준 파일시스템 제한
   - **OverlayFS home overlay**, `$HOME`에 대한 쓰기는 리포별로 캡처되고 읽기는 실제 홈으로 전달됨
   - **리포별 TMPDIR** (`<datastore>/.interim/sandbox/<name>/tmp/`)
   - **Docker 접근** 리포의 격리된 Docker 소켓을 통해
   - **권한 강하** 범용 사용자(`rediacc`)로
4. 리포의 `.envrc`가 Docker 및 환경 설정을 위해 자동으로 로드됩니다

**허용된 RW**: 리포 마운트 경로, 리포별 샌드박스 워크스페이스, 홈 디렉터리 (오버레이를 통해), Docker 소켓
**허용된 RO**: 시스템 경로 (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**차단됨**: 다른 리포의 마운트 경로, 허용 목록 외부의 시스템 파일

**VS Code 통합**: 각 리포는 `<datastore>/.interim/sandbox/<name>/.vscode-server/`에 자체 VS Code 서버 설치를 갖습니다. 여러 리포를 독립적인 샌드박스 환경으로 동시에 열 수 있으며 리포 간 서버를 공유하지 않습니다.

이는 측면 이동을 방지합니다. 에이전트가 포크의 셸 접근 권한을 얻더라도 동일한 머신의 다른 리포지토리를 읽거나 수정할 수 없습니다. 머신 수준 SSH (리포 없이)는 팀 키를 사용하며 샌드박스로 처리되지 않습니다.

## 아키텍처

MCP 서버는 상태가 없습니다. 각 도구 호출은 `--output json --yes --quiet` 플래그와 함께 격리된 자식 프로세스로 `rdc`를 생성합니다. 이는 다음을 의미합니다:

- 도구 호출 간 상태 누출 없음
- 기존 `rdc` 설정 및 SSH 키 사용
- 로컬 어댑터와 클라우드 어댑터 모두에서 작동
- 한 명령의 오류가 다른 명령에 영향을 주지 않음
