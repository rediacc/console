---
title: MCP 서버 설정
description: Model Context Protocol (MCP) 서버를 사용하여 AI 에이전트를 Rediacc 인프라에 연결하기.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: ko
sourceHash: "5aa932e999695e20"
sourceCommit: "a2b1f5471f48c44fb704157f615369df9c354832"
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

<!-- >>> translated-table: mcp-tools -->

| 도구 | 파괴적 | 설명 |
|---|---|---|
| `backup_browse` | 아니요 | 리포지토리에 들어 있는 파일을 나열합니다. |
| `backup_cancel` | 아니요 | 원격 머신에서 실행 중인 백업을 취소합니다. |
| `backup_check` | 아니요 | 파일 하나를 복원해 저장된 스냅샷이 암호문으로 열리는지 확인합니다. |
| `backup_immutability_show` | 아니요 | 적용 중인 지연 삭제 유예 기간을 보여 줍니다. |
| `backup_list` | 아니요 | 머신에 있는 백업 결과물을 나열합니다. |
| `backup_manifests` | 아니요 | 서버에 기록된 백업 스냅샷 매니페스트를 나열합니다. |
| `backup_reconcile` | 예 | 리포지토리의 저장 바이트 장부를 저장소가 실제로 보유한 값으로 되돌립니다(청크는 삭제하지 않습니다). |
| `backup_repair` | 예 | 저장소가 잃어버렸거나 잘못 보관 중인 청크를 이 머신의 앵커에서 다시 업로드합니다. |
| `backup_restore` | 예 | 백업 결과물을 라이브 리포지토리로 만듭니다. |
| `backup_retention` | 아니요 | 서버가 적용 중인 스냅샷 보존 정책을 보여 줍니다. |
| `backup_retention_preview` | 아니요 | 다음 정리에서 삭제될 스냅샷과 확보될 공간을 보여 줍니다. |
| `backup_run` | 아니요 | 지금 백업을 실행합니다. |
| `backup_snapshot` | 아니요 | 청크 저장소 스냅샷을 업로드합니다. 전체 인벤토리를 먼저 올리고, 이후에는 변경된 셀만 올립니다. |
| `backup_status` | 아니요 | 원격 머신의 백업 상태와 타이머 상태를 보여 줍니다. |
| `backup_strategy_list` | 아니요 | 모든 백업 전략을 나열합니다. |
| `backup_strategy_show` | 아니요 | 백업 전략의 세부 정보를 보여 줍니다. |
| `backup_toc-key_sync` | 아니요 | 리포지토리의 목록 조회 키를 해당 머신에 설치하거나, 다른 키가 있으면 교체합니다. |
| `backup_undelete` | 아니요 | 지연 스냅샷 삭제가 적용되기 전에 취소합니다. |
| `backup_usage` | 아니요 | 백업 저장소 할당량, 저장된 바이트 수, 리포지토리별 사용량을 보여 줍니다. |
| `backup_verify` | 아니요 | 리포지토리의 백업 앵커를 청크 저장소와 대조해 검증합니다. |
| `cluster_snapshot_list` | 아니요 | 클러스터의 그룹 스냅샷을 나열합니다. |
| `cluster_status` | 아니요 | 모든 클러스터를 나열하거나, 클러스터 이름을 주면 해당 클러스터의 전체 구성을 보여 줍니다. |
| `config_access_list` | 아니요 | 구성의 액세스 키를 나열합니다. |
| `config_prune` | 아니요 | 로컬 구성 파일 ~/.config/rediacc/<config>.json에서 불필요한 항목을 정리합니다. |
| `config_reconcile` | 아니요 | 머신의 실제 상태를 바탕으로 로컬 상태 저장소를 다시 만듭니다(renet list all). |
| `config_show` | 아니요 | 현재 구성의 세부 정보를 보여 줍니다. |
| `credits` | 아니요 | 이 계정의 남은 크레딧 잔액을 보여 줍니다. |
| `datastore_list` | 아니요 | 이름이 붙은 데이터스토어와 연결된 위치, 보유 내용을 나열합니다. |
| `datastore_snapshot_list` | 아니요 | 데이터스토어의 스냅샷을 나열합니다. |
| `datastore_status` | 아니요 | 데이터스토어 하나를 보여 줍니다. 백엔드, 연결 대상, 사용량, 리포지토리, 스냅샷을 확인할 수 있습니다. |
| `feedback_list` | 아니요 | 이 머신에서 볼 수 있는 피드백 보고서를 나열합니다(ID, 짧은 지문, 상태, 날짜). |
| `feedback_report` | 아니요 | 가장 최근에 실패한 명령(--last), 기록된 명령(--command <n>) 또는 메시지만으로 보고서를 만들고, 전송될 내용을 그대로 출력한 뒤 확인을 받아 전송합니다. |
| `feedback_show` | 아니요 | 피드백 보고서를 ID(또는 고유한 접두사)로 보여 줍니다. 상태, 발생 횟수, 날짜도 함께 표시됩니다. |
| `job_cancel` | 예 | 실행 중인 분리형 작업을 취소합니다. |
| `job_dismiss` | 예 | 작업 티켓을 로컬에서 포기합니다. 남은 단계는 버려지고 티켓은 더 이상 표시되지 않습니다. |
| `job_gc` | 예 | 완료된 작업과 해당 로그를 제거합니다. |
| `job_list` | 아니요 | 머신의 분리형 작업을 최신순으로 나열합니다. |
| `job_logs` | 아니요 | 분리형 작업의 이벤트 로그를 다시 재생하거나 실시간으로 따라갑니다. |
| `job_status` | 아니요 | 분리형 작업의 상태를 보여 줍니다. |
| `job_wait` | 아니요 | 작업이 끝날 때까지 최대 50초 기다립니다. |
| `legal` | 아니요 | CLI 언어로 된 법적 문서 링크와 기준이 되는 영어 링크, 현재 서비스 약관 버전(체크섬과 아카이브 URL 포함), 기록된 동의 내역(로그인 시 계정 서버, 익명일 때 이 구성에서 가져옴), 계약 당사자를 출력합니다. |
| `machine_access_show` | 아니요 | 머신에 연결된 액세스 키와 각 키가 그곳에서 해석하는 범위를 보여 줍니다. |
| `machine_add` | 아니요 | SSH로 접근할 수 있는 기존 머신을 등록합니다. |
| `machine_containers` | 아니요 | 머신의 Docker 컨테이너를 나열합니다. |
| `machine_converge` | 예 | 이전 런타임 레이아웃으로 아직 실행 중인 리포지토리 데몬을 한 번에 하나씩 재시작해 현재 레이아웃으로 옮깁니다. |
| `machine_deprovision` | 예 | 클라우드에서 프로비저닝한 머신을 삭제하고 구성에서 제거합니다. |
| `machine_gpu_list` | 아니요 | 머신에서 감지된 GPU, 해당 사양이 정의하는 CDI 장치 이름, 각 장치가 할당된 리포지토리를 나열합니다. |
| `machine_health` | 아니요 | CI/CD 파이프라인용으로 머신의 상태를 점검합니다. |
| `machine_infra_show` | 아니요 | 머신의 인프라 구성(기본 도메인, 공인 IP, 포트), 공유 TLS 설정(인증서 이메일, CF DNS 토큰), Cloudflare 영역 ID를 보여 줍니다. |
| `machine_list` | 아니요 | 머신을 나열합니다. |
| `machine_provider_add` | 아니요 | 클라우드 공급자를 추가합니다. |
| `machine_provider_list` | 아니요 | 머신 프로비저닝용으로 구성된 클라우드 공급자를 나열합니다. |
| `machine_provider_remove` | 예 | 클라우드 공급자 구성을 제거합니다. |
| `machine_provision` | 예 | OpenTofu로 클라우드 공급자에 새 머신을 프로비저닝합니다. |
| `machine_prune` | 예 | 머신에서 고아가 된 데이터스토어 리소스와 오래된 스냅샷을 제거합니다. |
| `machine_remove` | 예 | 머신을 구성에서 제거합니다. |
| `machine_repos` | 아니요 | 머신에 배포된 리포지토리를 나열합니다. |
| `machine_restart-services` | 예 | 교체된 바이너리를 아직 실행 중인 renet 데몬을 한 번에 한 유닛씩 설치된 바이너리로 전환하고, 다음으로 넘어가기 전에 각 유닛이 새 바이너리로 활성 상태인지 확인합니다. |
| `machine_scan-keys` | 아니요 | 머신의 SSH 호스트 키를 로컬 구성에 기록합니다. |
| `machine_services` | 아니요 | 머신에서 Rediacc가 관리하는 systemd 서비스를 나열합니다(이름, 상태, 하위 상태, 재시작 횟수, 메모리, 이름으로 변환된 리포지토리와 repository_guid에 담긴 원본). |
| `machine_setup` | 아니요 | 머신 온보딩을 마무리합니다. renet을 설치하고 리포지토리를 호스팅할 수 있도록 준비합니다. |
| `machine_status` | 아니요 | 머신의 연결 정보(IP, 사용자, 포트, 데이터스토어), 시스템 정보, 컨테이너(이름으로 변환된 리포지토리, repository_guid에 담긴 원본, 도메인, autoRoute), 서비스(이름으로 변환된 리포지토리), 리포지토리(GUID에서 변환된 이름, guid에 담긴 원본), 리소스 사용량을 가져옵니다. |
| `repo_admin_fsck` | 아니요 | 구성 참조(브랜치/HEAD)를 머신에 존재하는 객체와 대조해 검증하고, 끊어진 참조와 고아 커밋을 보고합니다. |
| `repo_cat` | 아니요 | 리포지토리 안의 파일 일부를 범위를 제한해 stdout으로 읽습니다(진단 메시지는 stderr로 출력). |
| `repo_checkout` | 예 | 불변 커밋(또는 브랜치 끝)을 리플링크로 새 쓰기 가능 작업 포크에 복제하고 HEAD를 그 포크로 지정합니다. |
| `repo_commit` | 예 | 마운트된 작업 포크를 새 불변 커밋으로 고정합니다(git과 비슷합니다). |
| `repo_create` | 예 | 새 리포지토리를 만듭니다. |
| `repo_delete` | 예 | 리포지토리와 그 데이터를 삭제합니다. |
| `repo_diff` | 아니요 | copy-on-write로 포크된 두 리포지토리 사이의 git 방식 파일 단위 diff를 보여 줍니다. |
| `repo_down` | 예 | 리포지토리의 Docker 컨테이너를 중지합니다(Rediaccfile down 실행). |
| `repo_exec` | 예 | 리포지토리 컨테이너 안에서 명령을 실행합니다. |
| `repo_fork` | 예 | 새 GUID와 networkId를 가진 거의 즉각적인 CoW 포크를 리포지토리에서 만듭니다(완전히 독립된 복사본). |
| `repo_gc` | 예 | 도달 가능성 기반 가비지 컬렉션입니다. 어떤 브랜치/HEAD도 도달하지 못하는 불변 커밋 객체를 머신에서 삭제합니다. |
| `repo_health` | 아니요 | 리포지토리 Rediaccfile의 health() 검사를 실행하고 0(정상), 1(경고), 2(오류)로 종료합니다. |
| `repo_list` | 아니요 | 머신의 리포지토리를 나열합니다. |
| `repo_log` | 아니요 | 작업 포크의 현재 커밋(또는 커밋 참조)에서 도달할 수 있는 커밋 기록을, 'rdc repo commit'이 기록한 부모 체인을 따라 출력합니다. |
| `repo_logs` | 아니요 | 리포지토리 컨테이너의 애플리케이션 로그를 보여 줍니다. |
| `repo_merge` | 예 | 수명 주기를 해치지 않고 소스 커밋/포크를 대상 작업 포크에 병합합니다. |
| `repo_migrate` | 예 | 다운타임을 최소화하며 리포지토리를 다른 머신으로 옮깁니다. 2단계 복사(실행 중 대량 동기화, 이어서 짧은 중지, 차이분 동기화, 대상에서 시작)와 DNS 전환으로 진행합니다. |
| `repo_pull` | 예 | 다른 머신에서 리포지토리를 가져옵니다. |
| `repo_push` | 예 | 리포지토리 백업을 스토리지 또는 다른 머신으로 직접 푸시합니다. |
| `repo_replicate` | 아니요 | 리포지토리의 읽기 전용 복제본을 프로비저닝합니다. |
| `repo_replicate_remove` | 예 | 복제본 세트를 제거합니다. 생성된 k8s 객체(레이블 범위 한정)를 삭제하고, 포크 데이터스토어를 폐기하고, 스냅샷을 버리고, 상태를 잊습니다. |
| `repo_replicate_status` | 아니요 | 관리되는 복제본 세트를 보여 줍니다. 복제본, 호스팅 노드, 포크 데이터스토어, 스냅샷, 새로 고침 시각을 확인할 수 있습니다. |
| `repo_secret_get` | 아니요 | 시크릿의 SHA-256 다이제스트를 보여 줍니다. |
| `repo_secret_list` | 아니요 | 시크릿 키와 모드를 나열합니다(값이나 다이제스트는 절대 표시하지 않습니다). |
| `repo_status` | 아니요 | 리포지토리 상태(마운트 상태, Docker 데몬 실행 여부, 컨테이너 수, 디스크 사용량)를 가져옵니다. |
| `repo_trim` | 아니요 | 마운트된 리포지토리에서 데이터스토어 풀 공간을 회수합니다(온라인, 다운타임 없음). |
| `repo_up` | 예 | 리포지토리를 배포하거나 업데이트합니다(renet compose로 Rediaccfile up을 실행하고 컨테이너를 시작). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| 도구 | 파괴적 | 설명 |
|---|---|---|
| `cluster_kubeconfig` | 아니요 | SSH로 클러스터 컨트롤 노드의 kubeconfig를 가져와 kubectl용으로 로컬(0600)에 캐시합니다. |
| `config_audit_log` | 아니요 | 이 구성으로 수행된 변경의 감사 로그를 읽습니다. |
| `config_audit_verify` | 아니요 | 감사 로그의 해시 체인이 변조되지 않았는지 검증합니다. |
| `config_current` | 아니요 | 활성 구성을 보여 줍니다. 이름, 파일, 확인된 서버와 채널, 토큰 상태를 확인할 수 있습니다. |
| `config_list` | 아니요 | 모든 구성 파일을 나열합니다. |
| `machine_infra_cert_status` | 아니요 | 캐시된 인증서 인벤토리를 보여 줍니다. |
| `server_status` | 아니요 | 설치된 서버의 상태, 티어, 인증서, 이미지를 보여 줍니다. |
| `version` | 아니요 | CLI 버전, 플랫폼, 업데이트 채널, 활성 라이선스를 출력합니다. 로그인한 경우 플랜, 로그인하지 않은 경우 "anonymous (FREE per repository)", 계정 서버에 연결할 수 없는 경우 "unknown (server unreachable)"이 표시됩니다. |

<!-- <<< translated-table -->

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

## 보안

MCP 서버는 두 가지 보호 레이어를 적용합니다:

### 포크 전용 모드 (기본값)

기본적으로 서버는 **포크 전용 모드**로 실행됩니다. 쓰기 도구(`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`)는 포크 리포지토리에서만 작동할 수 있습니다. Grand (원본) 리포지토리는 에이전트 수정으로부터 보호됩니다. 이는 설계에 의한 동작입니다.

> **리포별 시크릿은 설계상 CLI 전용입니다.** `repo_secret_set`과 `repo_secret_unset`은 의도적으로 MCP 도구로 노출되지 않습니다. 쓰기에는 `--current <previous-value>` 전제조건(또는 검증되지 않은 교체를 승인하는 `--rotate-secret`)이 필요하며, 이 절차는 사람이 직접 확인해야 합니다. 시크릿 교체를 제안해야 하는 에이전트는 `repo_secret_get`을 호출하여 다이제스트를 확인한 다음, JSON 오류 엔벨로프의 `next.options[].run` 필드를 통해 운영자 대상 CLI 명령을 사용자에게 전달해야 합니다. 전체 패턴은 [AI 에이전트 안전](/en/docs/ai-agents-safety#structured-next-action-hints)을 참조하고, 사용자 대상 방법은 [리포지토리 § 시크릿](/en/docs/repositories#secrets)을 참조하세요.

에이전트가 grand 리포지토리를 수정할 수 있게 하려면 MCP 서버를 호스팅하는 에이전트를 시작하기 **전**에 터미널에서 `REDIACC_ALLOW_GRAND_REPO`를 내보내세요:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # 단일 리포
# 또는 'repo1,repo2,repo3' (항목 주위의 공백은 무시됨), 또는 모든 리포에 대해 '*'
claude   # 또는 cursor, gemini 등
```

재정의는 프로세스 조상에 대해 검증됩니다. 에이전트 프로세스 자체의 환경에 이미 존재했을 때만 계산됩니다. 즉, 에이전트(그리고 그것이 생성한 MCP 서버)가 시작하기 전에 내보냈다는 뜻입니다. 에이전트는 세션 중간에 변수를 설정하여 자신에게 접근 권한을 부여할 수 없습니다. 이를 위한 서버 플래그는 의도적으로 없습니다. MCP 서버 인수의 플래그는 누가 입력했는지 증명하지 못하지만, 조상 검사는 증명합니다. 머신 수준 접근(리포 없이 `term connect <machine>`)은 여전히 `*`를 필요로 합니다. 리포 이름 목록은 이를 잠금 해제하지 않습니다.

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
- 한 명령의 오류가 다른 명령에 영향을 주지 않음
