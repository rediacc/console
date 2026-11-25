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
sourceHash: "b30e0030351679c5"
sourceCommit: "456461c5724ba002dc9184dc07d51fbff3358544"
---

## 개요

두 개의 MCP(Model Context Protocol) 서버가 같은 도구 레지스트리를 제공합니다.

| 서버 | 전송 | 실행 방식 | 도구 |
|---|---|---|---|
| 로컬 | stdio | `rdc mcp serve`, 에이전트가 실행 | 모든 도구 |
| 원격 | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | 원격 도구, 즉 로컬 전용 표에 있는 도구를 제외한 전부 |

**사전 요구사항:** 로컬 서버에는 `rdc`가 설치되어 있고 머신이 하나 이상 구성되어 있어야 합니다. 원격 서버에는 구성에 대한 그랜트(grant)가 필요합니다.

## 로컬 서버

`rdc mcp serve`는 stdio로 MCP 서버를 시작합니다. 에이전트가 이를 서브프로세스로 실행하고 JSON-RPC로 통신합니다.

### Claude Code

프로젝트의 `.mcp.json`에 다음 항목이 들어갑니다.

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

이름이 있는 구성을 쓰는 경우:

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

### Cursor

Settings → MCP Servers → Add Server를 엽니다.

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--config <name>` | (기본 구성) | 모든 명령에 사용할 이름 있는 구성 |
| `--timeout <ms>` | `120000` | 명령 기본 제한 시간(밀리초) |

## 원격 서버

리전마다 MCP Worker가 하나씩 `mcp.<region>.rediacc.cloud`에서 실행됩니다. 각 에이전트는 그랜트 하나의 URL `https://mcp.<region>.rediacc.cloud/g/<grantId>`에 연결합니다. 그랜트는 구성 하나, 만료 시각, 범위를 지정합니다. 범위는 읽기 전용 플래그, 허용 도구 목록, 머신 및 리포지토리 이름 글롭(glob)으로 이루어집니다. 도구 호출은 그랜트가 속한 조직의 실행기에서 처리됩니다.

### 자격 증명

두 형식 모두 그랜트를 식별하며, URL의 그랜트 ID는 이름을 가리킬 뿐입니다.

| 형식 | 용도 | 전송 방법 |
|---|---|---|
| OAuth 액세스 토큰 | claude.ai 같은 대화형 클라이언트 | `Authorization: Bearer <token>` |
| 에이전트 베어러 `rmcp_<grantId>.<secret>` | 헤드리스 에이전트 | `Authorization: Bearer` 또는 `x-api-key` |

쿼리 문자열에 담긴 자격 증명은 400으로 거부됩니다. 없거나 만료되었거나 다른 그랜트의 OAuth 토큰은 401과 함께 `WWW-Authenticate: Bearer resource_metadata=...` 헤더를 받으며, 이 헤더는 그랜트의 보호된 리소스 문서를 가리키므로 OAuth 클라이언트가 토큰을 갱신하거나 로그인할 수 있습니다. 알 수 없는 그랜트, 잘못된 시크릿, 다른 그랜트의 에이전트 베어러는 모두 같은 단순 401을 받습니다.

### OAuth

Worker는 PKCE(S256만 지원)를 쓰는 OAuth 2.1 인증 서버입니다. 클라이언트는 Client ID Metadata Document 또는 `/register`의 동적 클라이언트 등록으로 등록합니다.

| 엔드포인트 | 용도 |
|---|---|
| `/.well-known/oauth-authorization-server` | 서버 메타데이터 |
| `/.well-known/oauth-protected-resource/g/<grantId>` | 그랜트 하나의 보호된 리소스 문서 |
| `/authorize` | 인증을 시작하고 계정 페이지 `/account/mcp/authorize`로 리디렉션 |
| `/oauth/token` | 코드 교환, 갱신, 폐기 |
| `/register` | 동적 클라이언트 등록 |

클라이언트는 `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`를 보냅니다. 인증은 리소스가 가리키는 그랜트에 대해서만 완료되며, 토큰은 자기 그랜트의 URL에서만 동작합니다. `/authorize` 리디렉션에는 서명된 일회용 핸들만 담기고 시크릿은 담기지 않습니다.

### 토큰 수명

토큰은 자신의 그랜트보다 오래 살아남지 않습니다.

| 토큰 | 수명 |
|---|---|
| 액세스 토큰 | 1시간과 그랜트 잔여 시간 중 짧은 쪽 |
| 리프레시 토큰 | 30일과 그랜트 잔여 시간 중 짧은 쪽 |

코드 교환과 갱신이 있을 때마다 그랜트를 다시 조회합니다. 만료되었거나 폐기되었거나 키가 교체된 그랜트는 `invalid_grant`로 응답하고 OAuth 그랜트를 폐기합니다. 리프레시 토큰은 교체되며, 같은 토큰을 두 번 제시하면 그랜트가 폐기됩니다.

### 그랜트당 구성 하나

그랜트는 자신이 지정한 구성 하나만 처리합니다. 다른 구성을 가리키는 인자(`config` 또는 그 변형 표기)가 담긴 `tools/call`은 아무것도 실행되기 전에 `REDIACC_GRANT_SCOPE`로 거부됩니다. 구성이 여러 개인 사용자는 구성마다 그랜트를 하나씩 승인합니다. 그랜트의 허용 목록에 없는 도구나 읽기 전용 그랜트의 쓰기 도구는 `tools/list`에 나타나지 않으며, 호출하면 거부됩니다.

### 리전

그랜트 ID는 `eu_`처럼 리전으로 시작합니다. 다른 리전의 Worker에서 `/g/<grantId>`로 요청하면 올바른 URL과 함께 421이 돌아옵니다.

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

그랜트는 자신의 리전 밖에서는 OAuth 리소스, 토큰 대상(audience), 인증 대상으로 받아들여지지 않습니다.

### 그랜트 상태와 제한

만료되었거나, 폐기되었거나, 구성 저장소의 키 교체로 키를 잃은 그랜트도 `initialize`와 `tools/list`에는 계속 응답합니다. 이후 각 `tools/call`은 `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED`, `REDIACC_KEY_ROTATED` 중 하나를 `reauthUrl`과 함께 반환하며, 사용자는 이 URL을 열어 다시 승인합니다.

그랜트마다 분당 60회 호출과 동시 진행 호출 5개까지 허용됩니다. 둘 중 하나를 넘는 호출은 `retryAfterSeconds`와 함께 `REDIACC_RATE_LIMITED`를 반환합니다.

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

## 예시 워크플로

**머신 상태 확인:**
> "프로덕션 머신 상태가 어때?"

에이전트가 `machine_status`를 호출해 연결 정보, 시스템 정보, 컨테이너, 서비스, 리포지토리, 리소스 사용량을 받아옵니다.

**애플리케이션 배포:**
> "스테이징 머신에 gitlab을 배포해 줘"

에이전트가 `name: "gitlab"`, `machine: "staging"`으로 `repo_up`을 호출하면 리포지토리가 배포되고 성공 또는 실패가 반환됩니다.

**오래 걸리는 작업 따라가기:**
> "nextcloud의 어젯밤 백업을 복원해 줘"

에이전트가 `backup_restore`를 호출합니다. 제한 시간을 넘기는 명령은 작업 핸들을 반환하고, 에이전트는 작업이 끝날 때까지 `job_wait`(호출당 최대 50초)와 `job_logs`를 호출합니다.

**문제가 있는 서비스 디버깅:**
> "nextcloud가 느린데 원인을 찾아 줘"

에이전트가 `machine_health`를 호출한 뒤 `machine_containers`와 `repo_logs`를 호출하고 해결 방법을 제안합니다.

## 보안

로컬 MCP 서버는 두 겹의 보호를 적용합니다. 원격 서버의 제한은 [원격 서버](#원격-서버)에 있습니다.

### 포크 전용 모드 (기본값)

서버는 기본적으로 **포크 전용 모드**로 실행됩니다. 쓰기 도구(`repo_up`, `repo_down`, `repo_delete`, `repo_exec`)는 포크 리포지토리에서만 동작합니다. 에이전트는 그랜드(원본) 리포지토리를 건드릴 수 없습니다. 의도된 설계입니다.

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

로컬 MCP 서버는 상태를 저장하지 않습니다. 도구를 호출할 때마다 `rdc`가 `--output json --yes --quiet` 플래그와 함께 격리된 자식 프로세스로 실행됩니다. 따라서 다음과 같습니다.

- 도구 호출 간 상태 누출 없음
- 기존 `rdc` 설정 및 SSH 키 사용
- 한 명령의 오류가 다른 명령에 영향을 주지 않음
