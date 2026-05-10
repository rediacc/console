---
title: "rdc vs renet"
description: "rdc와 renet을 각각 언제 사용해야 하는지 설명합니다."
category: "Concepts"
order: 1
language: ko
---

# rdc vs renet

Rediacc에는 두 개의 바이너리가 있습니다. 각각을 언제 사용할지 알아보세요.

| | rdc | renet |
|---|-----|-------|
| **실행 위치** | 워크스테이션 | 원격 서버 |
| **연결 방식** | SSH | root로 로컬에서 실행 |
| **사용 대상** | 모든 사용자 | 고급 디버깅 전용 |
| **설치** | 직접 설치 | `rdc`가 자동으로 프로비저닝 |

> 일상 작업에는 `rdc`를 사용하세요. `renet`을 직접 사용할 필요는 거의 없습니다.

## 함께 작동하는 방식

`rdc`는 SSH를 통해 서버에 연결하고 `renet` 명령을 대신 실행합니다. 워크스테이션에서 단일 명령을 입력하면 `rdc`가 나머지를 처리합니다.

1. 로컬 config(`~/.config/rediacc/rediacc.json`)를 읽습니다.
2. SSH를 통해 서버에 연결합니다.
3. 필요하면 `renet` 바이너리를 업데이트합니다.
4. 서버에서 해당 `renet` 작업을 실행합니다.
5. 결과를 터미널로 반환합니다.

## 일반 작업에는 `rdc` 사용

모든 일반 작업은 워크스테이션의 `rdc`를 통해 수행합니다.

```bash
# 새 서버 설정
rdc config machine setup --name server-1

# 리포지터리 생성 및 시작
rdc repo create --name my-app -m server-1 --size 10G
rdc repo up --name my-app -m server-1

# 리포지터리 중지
rdc repo down --name my-app -m server-1

# 머신 상태 확인
rdc machine health --name server-1
```

전체 안내는 [빠른 시작](/ko/docs/quick-start)을 참조하세요.

## 서버 측 디버깅에는 `renet` 사용

다음의 경우에만 서버에 SSH로 접속하여 `renet`을 직접 사용합니다.

- `rdc`가 연결할 수 없을 때의 긴급 디버깅
- `rdc`를 통해 사용할 수 없는 시스템 내부 확인
- 저수준 복구 작업

모든 `renet` 명령에는 루트 권한(`sudo`)이 필요합니다. 전체 `renet` 명령 목록은 [서버 참조](/ko/docs/server-reference)를 참조하세요.

## 실험적: `rdc ops` (로컬 VM)

`rdc ops`는 워크스테이션에서 로컬 VM 클러스터를 관리하기 위해 `renet ops`를 래핑합니다.

```bash
rdc ops setup              # 사전 요구 사항 설치 (KVM 또는 QEMU)
rdc ops up --basic         # 최소 클러스터 시작
rdc ops status             # VM 상태 확인
rdc ops ssh --vm-id 1  # 브리지 VM으로 SSH
rdc ops ssh --vm-id 1 -c hostname  # 브리지 VM에서 명령 실행
rdc ops down               # 클러스터 삭제
```

> 로컬 어댑터가 필요합니다. 클라우드 어댑터에서는 사용할 수 없습니다.

이 명령들은 `renet`을 SSH가 아닌 로컬에서 실행합니다. 전체 문서는 [실험적 VM](/ko/docs/experimental-vms)을 참조하세요.

## Rediaccfile 참고 사항

`Rediaccfile` 내부에서 `renet compose -- ...`를 볼 수 있습니다. 이것은 정상입니다. Rediaccfile 함수는 `renet`이 사용 가능한 서버에서 실행됩니다.

워크스테이션에서는 `rdc repo up` 및 `rdc repo down`으로 워크로드를 시작하고 중지합니다.
