---
title: "마이그레이션 가이드"
description: "기존 프로젝트를 암호화된 Rediacc 저장소로 마이그레이션합니다."
category: "Guides"
order: 11
language: ko
sourceHash: "24c62c7fa0d043c2"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 마이그레이션 가이드

기존 프로젝트, 파일, Docker 서비스, 데이터베이스를 기존 서버나 로컬 개발 환경에서 암호화된 Rediacc 저장소로 마이그레이션합니다.

## 사전 요구사항

- `rdc` CLI 설치됨([설치](/en/docs/installation))
- 머신 추가 및 프로비저닝 완료([설정](/en/docs/setup))
- 프로젝트를 위한 충분한 디스크 공간(`rdc machine query`로 확인)

## 1단계: 저장소 생성

프로젝트에 맞는 크기의 암호화된 저장소를 생성합니다. Docker 이미지와 컨테이너 데이터를 위한 추가 공간을 할당하십시오.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **팁:** 필요한 경우 나중에 `rdc repo resize`로 크기를 조정할 수 있지만 저장소를 먼저 마운트 해제해야 합니다. 처음부터 충분한 공간으로 시작하는 것이 더 쉽습니다.

## 2단계: 파일 업로드

`rdc repo sync upload`를 사용하여 프로젝트 파일을 저장소로 전송합니다.

```bash
# 전송될 내용 미리보기(변경 없음)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# 파일 업로드
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

업로드 전에 저장소가 마운트되어 있어야 합니다. 아직 마운트되지 않은 경우:

```bash
rdc repo mount --name my-project -m server-1
```

원격이 로컬 디렉토리와 정확히 일치하도록 후속 동기화를 수행하려면:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> `--mirror` 플래그는 로컬에 존재하지 않는 원격 파일을 삭제합니다. 확인하려면 먼저 `--dry-run`을 사용하십시오.

## 3단계: 파일 소유권 수정

업로드된 파일은 로컬 사용자의 UID(예: 1000)로 도착합니다. Rediacc는 VS Code, 터미널 세션 및 도구 모두가 일관된 접근을 할 수 있도록 범용 사용자(UID 7111)를 사용합니다. 변환하려면 소유권 명령을 실행하십시오.

```bash
rdc repo ownership --name my-project -m server-1
```

### Docker 인식 제외

Docker 컨테이너가 실행 중이거나 실행된 적이 있는 경우 소유권 명령은 쓰기 가능한 데이터 디렉토리를 자동으로 감지하고 **건너뜁니다**. 이는 다른 UID로 자체 파일을 관리하는 컨테이너가 손상되는 것을 방지합니다(예: MariaDB는 UID 999, Nextcloud는 UID 33 사용).

명령은 수행한 작업을 보고합니다.

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### 실행 시점

- **파일 업로드 후**, 로컬 UID를 7111로 변환하기 위해
- **컨테이너 시작 후**, Docker 볼륨 디렉토리를 자동 제외하려는 경우. 컨테이너가 아직 시작되지 않은 경우 제외할 볼륨이 없으므로 모든 디렉토리가 chown됩니다(괜찮으며 컨테이너가 첫 번째 시작 시 데이터를 다시 생성합니다).

### 강제 모드

컨테이너 데이터 디렉토리를 포함한 모든 것을 Docker 볼륨 감지 없이 chown하려면:

```bash
rdc repo ownership --name my-project -m server-1
```

> **경고:** 이로 인해 실행 중인 컨테이너가 손상될 수 있습니다. 필요한 경우 먼저 `rdc repo down`으로 중지하십시오.

### 사용자 정의 UID

기본값 7111 이외의 UID를 설정하려면:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

> **주의:** `7111`은 모든 곳에서 사용되는 범용 Rediacc UID입니다(devcontainer 이미지에 내장된 `rediacc` 사용자와 일치합니다). 특정 외부 UID가 소유한 파일과의 레거시 호환성을 위해서만 `--uid`로 재정의하십시오. 이것은 **마이그레이션 대상이 아닙니다**. 새 저장소는 기본값을 유지해야 합니다.

## 4단계: Rediaccfile 설정

프로젝트 루트에 `Rediaccfile`을 생성합니다. 이 Bash 스크립트는 서비스가 시작되고 중지되는 방법을 정의합니다.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

두 가지 라이프사이클 함수:

| 함수 | 목적 | 오류 동작 |
|----------|---------|----------------|
| `up()` | 서비스 시작 | 루트 실패는 치명적. 서브디렉토리 실패는 기록되고 계속됨 |
| `down()` | 서비스 중지 | 최선 시도: 항상 모두 시도 |

> **중요:** Rediaccfile에서 `docker compose` 대신 항상 `renet compose --`를 사용하십시오. `renet compose` 래퍼는 renet-proxy에 필요한 호스트 네트워킹, CRIU 체크포인트/복원 기능, IP 할당 및 서비스 검색을 강제합니다. `docker compose`를 직접 사용하면 이러한 모든 것이 우회되며 검증 중에 거부됩니다.
>
> `sudo docker`도 절대 사용하지 마십시오. `sudo`는 `DOCKER_HOST`를 포함한 환경 변수를 재설정하여 컨테이너가 저장소의 격리된 데몬 대신 시스템 Docker 데몬에 생성됩니다. Rediaccfile 함수는 이미 충분한 권한으로 실행됩니다.

Rediaccfile, 다중 서비스 레이아웃 및 실행 순서에 대한 자세한 내용은 [서비스](/en/docs/services)를 참조하십시오.

## 5단계: 서비스 네트워킹 구성

Rediacc는 저장소당 격리된 Docker 데몬을 실행합니다. 서비스는 `network_mode: host`를 사용하고 고유한 루프백 IP에 바인딩하므로 저장소 간 충돌 없이 표준 포트를 사용할 수 있습니다.

### docker-compose.yml 수정

**이전(기존):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**이후(Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

주요 변경사항:

1. **`ports:` 매핑 제거** - `renet compose`는 호스트 네트워킹을 사용하고 포트 매핑을 자동으로 제거합니다
2. **`network_mode: host` 제거** - `renet compose`가 이를 추가합니다
3. **재시작 정책은 유지해도 됩니다** - renet이 CRIU 호환성을 위해 자동으로 제거하고 라우터 감시자가 중지된 컨테이너를 자동 복구합니다
4. **서비스 간 연결에 서비스 이름 사용**(예: `postgres`, `redis`) - renet이 모든 서비스 이름을 해석 가능한 호스트명으로 주입합니다. 데이터베이스나 구성 파일에 저장되는 연결 문자열에 원시 IP를 포함하지 마십시오. 포크 격리를 유지하기 위해 서비스 이름을 사용하십시오
5. **바인딩은 자동입니다** - 커널이 `bind()`를 올바른 루프백 IP로 재작성합니다. 서비스는 `0.0.0.0` 또는 `localhost`를 사용할 수 있습니다

`{SERVICE}_IP` 변수는 여전히 사용 가능하지만 명시적 바인딩은 더 이상 필요하지 않습니다. 바인딩은 자동으로 처리됩니다. 명명 규칙: 대문자, 하이픈을 밑줄로 교체, `_IP` 접미사 추가. 예를 들어 `listmonk-app`은 `LISTMONK_APP_IP`가 됩니다.

IP 할당 및 `.rediacc.json`에 대한 자세한 내용은 [서비스 네트워킹](/en/docs/services#service-networking-rediaccjson)을 참조하십시오.

## 6단계: 서비스 시작

저장소를 마운트하고(아직 마운트되지 않은 경우) 모든 서비스를 시작합니다.

```bash
rdc repo up --name my-project -m server-1
```

이 명령은 다음을 수행합니다.
1. 암호화된 저장소 마운트
2. 격리된 Docker 데몬 시작
3. 서비스 IP 할당이 포함된 `.rediacc.json` 자동 생성
4. 모든 Rediaccfile에서 `up()` 실행

컨테이너가 실행 중인지 확인합니다.

```bash
rdc machine containers --name server-1
```

## 7단계: 자동 시작 활성화(선택사항)

기본적으로 저장소는 서버 재부팅 후 수동으로 마운트하고 시작해야 합니다. 서비스가 자동으로 시작되도록 자동 시작을 활성화하십시오.

```bash
rdc repo autostart enable --name my-project -m server-1
```

저장소 패스프레이즈를 입력하라는 메시지가 표시됩니다.

> **보안 참고:** 자동 시작은 서버에 LUKS 키파일을 저장합니다. 루트 접근 권한이 있는 사람은 패스프레이즈 없이 저장소를 마운트할 수 있습니다. 자세한 내용은 [자동 시작](/en/docs/services#autostart-on-boot)을 참조하십시오.

## 일반적인 마이그레이션 시나리오

### WordPress / 데이터베이스가 있는 PHP

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # WordPress 파일(실행 중 UID 33)
├── database/data/          # MariaDB 데이터(실행 중 UID 999)
└── wp-content/uploads/     # 사용자 업로드
```

1. 프로젝트 파일 업로드
2. 서비스를 먼저 시작(`rdc repo up`)하여 컨테이너가 데이터 디렉토리를 생성하도록 함
3. 소유권 수정 실행. MariaDB 및 앱 데이터 디렉토리는 자동 제외됨

### Redis가 있는 Node.js / Python

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # 애플리케이션 소스
├── node_modules/           # 의존성
└── redis-data/             # Redis 지속성(실행 중 UID 999)
```

1. 프로젝트 업로드(`node_modules` 제외하고 `up()`에서 가져오는 것 고려)
2. 컨테이너가 시작된 후 소유권 수정 실행

### 사용자 정의 Docker 프로젝트

Docker 서비스가 있는 모든 프로젝트의 경우:

1. 프로젝트 파일 업로드
2. `docker-compose.yml` 수정(5단계 참조)
3. 라이프사이클 함수가 있는 `Rediaccfile` 생성
4. 소유권 수정 실행
5. 서비스 시작

## 문제 해결

### 업로드 후 권한 거부됨

파일에 아직 로컬 UID가 있습니다. 소유권 명령을 실행하십시오.

```bash
rdc repo ownership --name my-project -m server-1
```

### 컨테이너가 시작되지 않음

서비스가 실행 중인지 확인하고 로그를 검토하십시오.

```bash
# 할당된 IP 확인
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# 컨테이너 로그 확인
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### 저장소 간 포트 충돌

각 저장소는 고유한 루프백 IP를 갖으며 커널이 자동으로 `bind()` 호출을 올바른 IP로 재작성합니다. 저장소 간 포트 충돌은 발생하지 않습니다. 예상치 못한 동작이 발생하면 서비스가 `renet compose`를 통해(`docker compose`가 아닌) 시작되었는지 확인하십시오. 다른 서비스에 **연결**할 때는 원시 IP 대신 서비스 이름(예: `postgres`)을 사용하십시오. 서비스 이름은 모든 포크에서 올바르게 해석됩니다.

### 소유권 수정이 컨테이너를 손상시킴

`rdc repo ownership`을 실행했는데 컨테이너가 작동을 중지한 경우 컨테이너의 데이터 파일이 chown되었습니다. 컨테이너를 중지하고 데이터 디렉토리를 삭제한 후 재시작하십시오. 컨테이너가 다시 생성합니다.

```bash
rdc repo down --name my-project -m server-1
# 컨테이너의 데이터 디렉토리 삭제(예: database/data)
rdc repo up --name my-project -m server-1
```
