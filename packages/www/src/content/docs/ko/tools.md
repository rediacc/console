---
title: "도구"
description: "파일 동기화, 터미널 접속, VS Code 통합, CLI 업데이트."
category: "Guides"
order: 9
language: ko
---

# 도구

Rediacc는 원격 저장소 작업을 위한 생산성 도구를 제공합니다: 파일 동기화, SSH 터미널, VS Code 통합, CLI 업데이트.

## 파일 동기화 (sync)

rsync over SSH를 사용하여 워크스테이션과 원격 저장소 간에 파일을 전송합니다.

### 파일 업로드

`--local`은 하나 이상의 경로를 받습니다. 각 경로는 파일 또는 디렉터리일 수 있습니다. 파일은 `<remote>/<basename>`에 저장되며, 디렉터리 내용은 `<remote>/`에 병합됩니다. 단일 파일의 경우 `--remote-file`을 사용하여 목적지 경로를 명시적으로 지정하는 것이 좋습니다.

```bash
# 디렉터리 (내용이 원격에 병합됨)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# 단일 파일을 원격 디렉터리에 저장 (기본 이름 유지)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# 단일 파일, 명시적 목적지 경로
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# 한 번의 호출로 여러 소스 지정
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote`와 `--remote-file`은 함께 사용할 수 없습니다. `--remote-file`은 파일을 가리키는 `--local` 경로가 정확히 하나여야 합니다.

`--mirror`는 파일 소스와 함께 사용할 수 없습니다. 원격 디렉터리의 인접 파일이 삭제될 수 있습니다.

### 파일 다운로드

디렉터리에는 `--remote`를, 단일 파일에는 `--remote-file`을 사용합니다. 두 플래그는 함께 사용할 수 없습니다.

```bash
# 디렉터리
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# 단일 파일 -- --local은 기존 디렉터리여야 함
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### 동기화 상태 확인

```bash
rdc repo sync status -m server-1 -r my-app
```

### 옵션

| 옵션 | 설명 |
|--------|-------------|
| `-m, --machine <name>` | 대상 머신 |
| `-r, --repository <name>` | 대상 저장소 |
| `--local <paths...>` | 하나 이상의 로컬 파일 또는 디렉터리 경로 (업로드) 또는 로컬 목적지 디렉터리 (다운로드) |
| `--remote <path>` | 원격 디렉터리 (저장소 마운트 기준 상대 경로) |
| `--remote-file <path>` | 단일 파일 업로드 또는 다운로드를 위한 원격 파일 경로 (`--remote` 대안) |
| `--dry-run` | 전송 없이 변경 사항 미리보기 |
| `--mirror` | 소스를 목적지에 미러링, 추가 파일 삭제 (디렉터리 소스만) |
| `--verify` | 전송 후 체크섬 검증 |
| `--confirm` | 상세 보기와 함께 대화형 확인 |
| `--exclude <patterns...>` | 파일 패턴 제외 |
| `--skip-router-restart` | 작업 후 라우트 서버 재시작 건너뜀 |

## SSH 터미널 (term)

머신 또는 저장소 환경으로의 대화형 SSH 세션을 엽니다.

### 단축 구문

가장 빠른 연결 방법:

```bash
rdc term connect -m server-1                    # 머신에 연결
rdc term connect -m server-1 -r my-app             # 저장소에 연결
```

### 명령 실행

대화형 세션 없이 명령을 실행합니다:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

저장소에 연결할 때 `DOCKER_HOST`가 자동으로 저장소의 격리된 Docker 소켓으로 설정되므로, `docker ps`는 해당 저장소의 컨테이너만 표시합니다.

### connect 하위 명령

`connect` 하위 명령은 명시적 플래그로 동일한 기능을 제공합니다:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### 컨테이너 작업

실행 중인 컨테이너와 직접 상호작용합니다:

```bash
# 컨테이너 내부에서 셸 열기
rdc term connect -m server-1 -r my-app --container <container-id>

# 컨테이너 로그 보기
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# 실시간 로그 팔로우
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# 컨테이너 통계 보기
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# 컨테이너에서 명령 실행
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
```

| 옵션 | 설명 |
|--------|-------------|
| `--container <id>` | 대상 Docker 컨테이너 ID |
| `--container-action <action>` | 작업: `terminal` (기본값), `logs`, `stats`, `exec` |
| `--log-lines <n>` | 표시할 로그 줄 수 (기본값: 50) |
| `--follow` | 로그 지속 팔로우 |
| `--external` | 인라인 SSH 대신 외부 터미널 사용 |

## VS Code 통합 (vscode)

올바른 SSH 설정으로 미리 구성된 VS Code의 원격 SSH 세션을 엽니다.

### 저장소에 연결

```bash
rdc vscode connect -r my-app -m server-1
```

이 명령은:
1. VS Code 설치를 감지합니다
2. `~/.ssh/config`에 SSH 연결을 구성합니다
3. 세션을 위해 SSH 키를 유지합니다
4. 저장소 경로로의 Remote SSH 연결로 VS Code를 엽니다

### 구성된 연결 목록 확인

```bash
rdc vscode list
```

### 연결 정리

```bash
rdc vscode cleanup
```

더 이상 필요하지 않은 VS Code SSH 구성을 제거합니다.

### 구성 확인

```bash
rdc vscode check
```

VS Code 설치, Remote SSH 확장, 활성 연결을 확인합니다.

> **전제 조건:** VS Code에 [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) 확장을 설치하세요.

## CLI 업데이트 (update)

`rdc` CLI를 최신 상태로 유지합니다.

### 업데이트 확인

```bash
rdc update --check-only
```

### 업데이트 적용

```bash
rdc update
```

업데이트는 다운로드되어 제자리에서 적용됩니다. CLI가 자동으로 플랫폼(Linux, macOS, Windows)에 맞는 올바른 바이너리를 선택합니다. 새 버전은 다음 실행 시 적용됩니다.

### 롤백

```bash
rdc update --rollback
```

이전에 설치된 버전으로 되돌립니다. 업데이트 적용 후에만 사용할 수 있습니다.

### 업데이트 상태

```bash
rdc update --status
```

현재 버전, 업데이트 채널, 자동 업데이트 구성을 표시합니다.

#### 릴리스 채널

```bash
rdc update --channel edge      # 지속적으로 배포되는 프로덕션 업데이트
rdc update --channel stable    # 7일 soak 후 edge에서 승격됨 (기본값)
rdc update --status            # 현재 채널 및 버전 정보 표시
```
