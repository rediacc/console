---
title: RDC CLI 치트 시트
description: 모든 rdc 명령, config, 리포지터리, 머신, 동기화, 컨테이너 등에 대한 빠른 참조입니다.
category: Guides
order: 3
language: ko
---

# RDC CLI 치트 시트

가장 일반적인 `rdc` 명령에 대한 빠른 참조입니다. 전체 옵션은 `--help`와 함께 명령을 실행하세요.

## 리포지터리 수명 주기

| 명령 | 설명 |
|---------|-------------|
| `rdc repo create --name <repo> -m <machine>` | 머신에 새 리포지터리 생성 |
| `rdc repo up --name <repo> -m <machine>` | 리포지터리 배포 또는 업데이트 |
| `rdc repo down --name <repo> -m <machine>` | 리포지터리 중지 |
| `rdc repo delete --name <repo> -m <machine>` | 리포지터리 삭제 |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | 리포지터리 포크 (거의 즉각적, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | 기존 리포지터리 소유권 획득 |
| `rdc config repository list` | 이름 및 GUID와 함께 모든 리포지터리 나열 |

## 리포지터리별 시크릿

쓰기 전용 배포 시점 자격 증명. `get`은 다이제스트만 반환합니다. 값은 절대 반환되지 않습니다. 전체 가이드는 [리포지터리 § 시크릿](/ko/docs/repositories#secrets)을 참조하세요.

| 명령 | 설명 |
|---------|-------------|
| `rdc repo secret set --name <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | 새 시크릿 생성 (첫 번째 쓰기에는 `--current ""`) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --current <prev>` | 기존 시크릿 덮어쓰기 (passwd 스타일 사전 조건) |
| `rdc repo secret set --name <repo> --key <KEY> --value <val> --rotate-secret` | 이전 값 확인 없이 덮어쓰기 (교체로 감사됨) |
| `rdc repo secret list --name <repo>` | 시크릿 이름 + 전달 모드 나열 (값 및 다이제스트 절대 없음) |
| `rdc repo secret get --name <repo> --key <KEY>` | 시크릿 다이제스트 + 모드 표시 (평문 값 없음, 절대로) |
| `rdc repo secret unset --name <repo> --key <KEY> --current <prev>` | 시크릿 삭제 |
| `rdc repo secret unset --name <repo> --key <KEY> --rotate-secret` | 이전 값 확인 없이 삭제 |

> 포크는 시크릿을 상속하지 않습니다. `rdc repo secret set --name <repo>:<tag>`로 포크에 명시적으로 설정하세요.

## 백업 및 복원

| 명령 | 설명 |
|---------|-------------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | 리포지터리 백업을 스토리지로 푸시 |
| `rdc repo push --to <storage> -m <machine>` | 모든 리포지터리를 스토리지로 푸시 |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | 스토리지에서 리포지터리 복원 |
| `rdc repo pull --from <storage> -m <machine>` | 스토리지에서 모든 리포지터리 복원 |
| `rdc repo push ... --bwlimit <limit>` | 푸시 중 rsync 대역폭 제한 (예: `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | 풀 중 rsync 대역폭 제한 |
| `rdc repo push ... --checkpoint` | 푸시 전 컨테이너 체크포인트 생성 |
| `rdc repo backup list --from <storage> -m <machine>` | 스토리지의 사용 가능한 백업 나열 |
| `rdc storage browse --name <storage>` | 스토리지 내용 탐색 |

## 리포지터리 마이그레이션

| 명령 | 설명 |
|---------|-------------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | 머신 간 리포지터리 이동 |
| `rdc repo migrate ... --provision` | 전송 전 대상에 프로비저닝 |
| `rdc repo migrate ... --checkpoint` | 마이그레이션 전 체크포인트 생성 |
| `rdc repo migrate ... --skip-dns` | 마이그레이션 후 DNS 업데이트 건너뜀 |
| `rdc repo migrate ... --bwlimit <limit>` | 전송 대역폭 제한 |

## 백업 전략

| 명령 | 설명 |
|---------|-------------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | 명명된 백업 전략 생성 또는 업데이트 |
| `rdc config backup-strategy list` | 정의된 모든 백업 전략 나열 |
| `rdc config backup-strategy show --name <name>` | 전략의 세부 사항 표시 |
| `rdc config backup-strategy remove --name <name>` | 전략 제거 |
| `rdc config machine set <machine> --backup-strategies <s1,s2>` | 전략을 머신에 바인딩 |

## 백업 작업

| 명령 | 설명 |
|---------|-------------|
| `rdc machine backup schedule -m <machine>` | 바인딩된 전략을 systemd 타이머로 배포 |
| `rdc machine backup schedule -m <machine> --dry-run` | 배포 없이 타이머 단위 미리 보기 (토큰 마스킹) |
| `rdc machine backup now -m <machine>` | 바인딩된 모든 전략 즉시 실행 |
| `rdc machine backup now -m <machine> --strategy <name>` | 특정 전략 즉시 실행 |
| `rdc machine backup status -m <machine>` | 타이머 상태 및 최근 작업 결과 표시 |
| `rdc machine backup status -m <machine> --strategy <name>` | 특정 전략의 상태 표시 |
| `rdc machine backup cancel -m <machine>` | 실행 중인 백업 취소 |
| `rdc machine backup cancel -m <machine> --strategy <name>` | 특정 실행 중인 백업 취소 |

## 머신 관리

| 명령 | 설명 |
|---------|-------------|
| `rdc machine query --name <machine>` | 전체 머신 상태 (시스템, 컨테이너, 서비스, 리포지터리, 네트워크) |
| `rdc machine query --name <machine> --system` | 시스템 정보만 |
| `rdc machine query --name <machine> --containers` | 컨테이너 목록만 |
| `rdc machine query --name <machine> --repositories` | 리포지터리 목록만 |
| `rdc machine query --name <machine> --services` | 서비스 목록만 |
| `rdc machine query --name <machine> --network` | 네트워크 정보만 |
| `rdc machine query --name <machine> --block-devices` | 블록 디바이스 정보만 |
| `rdc machine list` | config의 모든 머신 나열 |
| `rdc config machine setup --name <machine>` | 초기 머신 프로비저닝 실행 |
| `rdc machine prune --name <machine>` | 머신에서 사용하지 않는 리소스 제거 |
| `rdc machine deprovision --name <machine>` | 머신 완전히 디프로비저닝 |
| `rdc machine vault-status --name <machine>` | LUKS 볼트 상태 표시 |

## 터미널 및 동기화

| 명령 | 설명 |
|---------|-------------|
| `rdc term connect -m <machine>` | 머신으로 SSH 터미널 열기 |
| `rdc term connect -m <machine> -r <repo>` | 리포지터리로 SSH 터미널 열기 (DOCKER_HOST 설정) |
| `rdc term connect -m <machine> -c "<command>"` | 머신에서 명령 실행 |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | 하나 이상의 로컬 파일/디렉터리를 리포지터리에 업로드 |
| `rdc repo sync upload -m <machine> -r <repo> --local <file> --remote-file <path>` | 단일 로컬 파일을 명시적인 원격 경로에 업로드 |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | 리포지터리 디렉터리를 로컬에 다운로드 |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | 단일 원격 파일을 로컬 디렉터리로 다운로드 |
| `rdc vscode connect -m <machine> -r <repo>` | VS Code Remote SSH 세션 열기 |

## 구성

| 명령 | 설명 |
|---------|-------------|
| `rdc config init --name <name>` | 명명된 config 파일 생성 |
| `rdc config machine add --name <machine> --host <host> --user <user>` | config에 머신 추가 |
| `rdc config storage import --file rclone.conf` | rclone config에서 스토리지 공급자 가져오기 |
| `rdc config storage list` | 구성된 스토리지 공급자 나열 |
| `rdc config backup-strategy set ...` | 명명된 백업 전략 정의 |
| `rdc --config <name> <command>` | 명명된 config 파일 사용 |

## 디버그 및 이스케이프 해치

| 명령 | 설명 |
|---------|-------------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | 리포지터리의 컨테이너 나열 |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | 컨테이너 로그 가져오기 |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | 컨테이너에서 명령 실행 |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | 컨테이너 재시작 |
