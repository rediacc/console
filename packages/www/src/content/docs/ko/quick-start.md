---
title: 빠른 시작
description: 몇 분 안에 서버에서 컨테이너화된 서비스를 실행합니다.
category: Guides
order: -1
language: ko
sourceHash: "b2745d4f0d99d7a4"
sourceCommit: "a56b03aa5da8df74255a6bc9bc9463665c3499b6"
---

# 빠른 시작

자체 서버에서 Rediacc를 설치합니다. 암호화된 격리된 컨테이너 환경, 클라우드 계정 없음, SaaS 의존성 없음. 직접 제어하는 하드웨어입니다.

---

## 소개

### 핵심 개념

리포지터리(repo)는 디스크의 단일 암호화 파일입니다. 이동, 백업, 포크할 수 있습니다. 그냥 파일입니다. 마운트하면 전용 Docker 데몬과 앱 데이터가 들어 있는 폴더가 됩니다.

리포지터리를 USB 드라이브처럼 생각하세요. 어떤 머신에 꽂아도 앱과 데이터가 마운트되어 바로 실행할 수 있습니다. 아무것도 다시 빌드하지 않고 머신이나 클라우드 공급자 간에 이동할 수 있습니다.

**두 가지 도구, 두 가지 역할:**

- **rdc** = 노트북의 CLI (TypeScript, 전역 설치)
- **renet** = 서버의 오케스트레이터 (Go 바이너리, 데몬/네트워크/격리 관리)
- RDC는 `config machine setup` 중에 renet을 자동으로 프로비저닝합니다. 서버에서 수동 설정이 필요하지 않습니다.

> [아키텍처](/ko/docs/architecture)는 보안 모델을 설명합니다. [rdc vs renet](/ko/docs/rdc-vs-renet)은 어느 도구를 언제 사용할지 설명합니다.

### 1. CLI 설치

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # 확인: Node, SSH 키, renet, Docker
```

> Windows, Alpine, Arch: [설치](/ko/docs/installation)를 참조하세요. 전체 시스템 요구 사항: [요구 사항](/ko/docs/requirements).

### 2. SSH 키 설정

rdc는 SSH를 통해 연결합니다. rdc가 서버에 접근하려면 서버가 공개 키를 신뢰해야 합니다.

```bash
# 키 생성 (이미 있으면 건너뜁니다)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 공개 키를 서버에 복사합니다 (비밀번호 입력 메시지가 표시됩니다)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# rdc에게 사용할 키를 알립니다
rdc config ssh set --key ~/.ssh/id_ed25519
```

이제 모든 rdc 명령은 이 키로 인증합니다. 비밀번호가 필요하지 않습니다.

### 3. 서버 추가

```bash
rdc machine add my-server --ip 192.168.1.100 --user admin
rdc machine setup my-server  # renet 프로비저닝 + 데이터스토어 생성
```

**수행되는 작업:** SSH 호스트 키 스캔, renet 바이너리 업로드, 서버에 암호화된 데이터스토어 초기화. 리포지터리 사용 준비 완료.

> 데이터스토어 크기 조정, Ceph RBD, 클라우드 공급자: [머신 설정](/ko/docs/setup). SSH 실패: [문제 해결](/ko/docs/troubleshooting).

### 4. Config 파일

```bash
rdc config show                            # 사람이 읽기 쉬운 요약
cat ~/.config/rediacc/rediacc.json         # 원시 JSON: 머신, 리포지터리, 스토리지, SSH 키
```

**파일 하나 = 환경 하나.** 다른 노트북에 복사하면 바로 사용할 수 있습니다.

---

## 리포지터리 작업

### 1. 리포지터리 생성

```bash
rdc repo create my-app -m my-server --size 2G  # 2 GB 암호화 리포지터리 생성
```

암호화 볼륨을 생성하고 마운트하며 Docker 데몬을 시작합니다. 리포지터리는 config에 등록되고 사용 준비가 됩니다.

> 크기 조정, 삭제, 검증: [리포지터리](/ko/docs/repositories).

### 2. 템플릿 적용

```bash
rdc repo admin template list                                        # 내장 템플릿 표시
rdc repo admin template apply my-app --template app-postgres  # docker-compose.yml + Rediaccfile 배포
```

템플릿은 `docker-compose.yml`, `Rediaccfile`, 지원 파일을 제공합니다. 템플릿(또는 자체 compose 파일) 없이는 시작할 것이 없습니다. 첫 번째 리포지터리에는 내장된 템플릿을 사용하세요. 전체 워크플로우를 처음부터 끝까지 보는 가장 빠른 방법입니다.

### 3. 리포지터리 시작

```bash
rdc repo up my-app  # Rediaccfile up() 실행
rdc repo list -m my-server                           # 머신의 모든 리포지터리 보기
rdc repo status my-app  # 마운트 상태, Docker, 크기, 암호화
```

`repo up`은 필요하면 자동으로 마운트합니다. 플래그가 필요하지 않습니다.

### 4. VS Code

```bash
rdc vscode connect my-app              # VS Code SSH를 열고 리포지터리 샌드박스 내부에 착지합니다
```

암호화된 볼륨 *내부의* 파일을 편집하고 있습니다. `docker ps`는 이 리포지터리의 컨테이너만 표시합니다. 저장하고, compose up하고, 반복합니다.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **실행 위치** | 노트북 (CLI) | VS Code 샌드박스 내부 |
| **수행하는 작업** | SSH → 자동 마운트 → Rediaccfile `up()` 실행 | Rediaccfile `up()`을 직접 실행 |
| **사용 사례** | CI/CD, 자동화, 원격 작업 | 개발자 내부 루프 |
| **격리** | 외부에서 오케스트레이션 | 이미 샌드박스 내부 |

**데모 흐름:** `rdc repo admin template apply` → `rdc vscode connect my-app` → `docker-compose.yml` 편집 → `renet dev up` → 앱 실행 확인 → 반복.

> Rediaccfile 구조: [서비스](/ko/docs/services). 어느 도구를 언제 사용할지: [rdc vs renet](/ko/docs/rdc-vs-renet).

### 6. 격리 모델

- **범용 사용자** (`rediacc`): 모든 머신에서 동일한 UID. 리포지터리를 다른 서버로 이동하면 파일 소유권이 그냥 작동합니다. `chown` 번거로움이 없습니다.
- **리포지터리당 Docker 데몬**: 각 리포지터리는 자체 격리된 Docker 데몬을 갖습니다. `docker ps`는 이 리포지터리의 컨테이너만 표시합니다.
- **Landlock + OverlayFS 샌드박스**: VS Code 셸은 파일 시스템이 제한됩니다. 다른 리포지터리를 읽을 수 없습니다. `$HOME` 쓰기는 리포지터리별 오버레이입니다.

> 격리 작동 방식: [아키텍처](/ko/docs/architecture). Rediaccfile 수명 주기: [서비스](/ko/docs/services).

### 7. 터미널, 동기화 및 터널

**터미널:**
```bash
rdc term connect my-app                            # 리포지터리 샌드박스로 SSH
rdc term connect my-app -c "curl localhost:3000"   # 명령 실행 후 종료
rdc term connect my-server                                   # 머신으로 SSH (샌드박스 없음)
```

**파일 동기화 (SSH를 통한 rsync):**
```bash
rdc repo sync upload my-app --local ./src                                   # 디렉터리 푸시
rdc repo sync upload my-app --local ./config.yml --remote conf              # 단일 파일 푸시
rdc repo sync download my-app --local ./backup                              # 디렉터리 풀
rdc repo sync download my-app --remote-file conf/config.yml --local ./dl    # 단일 파일 풀
rdc repo sync download my-app --local ./backup --dry-run                    # 먼저 미리 보기
```

**터널 (컨테이너로의 SSH 포트 포워딩):**
```bash
rdc repo tunnel my-app -c app  # 앱 컨테이너에 대한 포트 자동 감지
rdc repo tunnel my-app -c db --port 5432  # Postgres 터널
rdc repo tunnel my-app -c db --port 5432 --local 15432  # 사용자 정의 로컬 포트
```

터널 실행 → 브라우저에서 `localhost:3000` 열기 → 원격 서버의 실제 앱.

> 동기화, 터미널, VS Code 세부 사항: [도구](/ko/docs/tools).

---

## 포크 및 백업

### 1. Grand 및 Fork 리포지터리

```bash
rdc repo fork my-app --tag experiment --up  # 즉각적인 CoW 클론 + 시작
rdc repo list -m my-server                                  # 표시: my-app (grand) + my-app:experiment (fork)
rdc repo delete my-app:experiment  # 포크 삭제, grand는 그대로 유지
```

**즉각적인 제로 카피 클론.** CoW (copy-on-write). 마이크로초, 데이터 복사 없음. 한쪽이 쓸 때까지 블록이 공유됩니다.

**사용 사례:**
- **AI / ML:** 프로덕션 데이터셋 포크, 실험 실행, 폐기 또는 프로모션
- **DevOps:** 포크 → 마이그레이션 테스트 → 나쁘면 삭제, 좋으면 프로모션
- **백업:** 포크 = 즉각적인 스냅샷, 오프사이트 푸시

> 포크 수명 주기, 교차 머신 포크: [리포지터리](/ko/docs/repositories).

### 2. 다른 머신으로 푸시

```bash
# 리포지터리를 다른 머신으로 푸시
rdc repo push my-app --to backup-server

# 대상에서 자동 배포로 푸시
rdc backup restore my-app --as my-app -m backup-server --up

# CRIU 체크포인트로 푸시 (라이브 마이그레이션, 메모리 상태 보존)
rdc repo push my-app --to new-server --checkpoint

# 새 머신으로 푸시 (클라우드 공급자를 통한 자동 프로비저닝)
rdc repo push my-app --to new-server --provision linode
```

### 3. 청크 스토리지에 백업

```bash
# 특정 시점 스냅샷 생성
rdc backup snapshot my-app

# 존재하는 스냅샷 확인
rdc backup manifests my-app

# 저장된 바이트를 쿼터와 비교 확인
rdc backup usage
```

스냅샷은 청크 스토리지로 업로드되며, 이를 위해서는 계정 서버와 라이선스가 있는 저장소가 필요합니다. 변경된 데이터만 저장되므로 동일한 저장소의 두 번째 스냅샷은 전체 이미지가 아니라 차이만큼의 비용이 듭니다.

`--to <storage>`로 저장소를 클라우드 스토리지에 푸시하는 기능은 폐지되어 이제 거부됩니다. 그 변경 이전에 작성된 아카이브를 읽으려면 `rdc storage browse`가 계속 작동하며, PATH에 `rclone`이 있어야 합니다.

### 4. 원격에서 풀

```bash
# 클라우드 머신에서 로컬 서버로 리포지터리 풀
rdc repo pull my-app@my-local-server --from cloud-server

# 풀하고 즉시 시작
rdc repo pull my-app@my-local-server --from cloud-server --up

# 대신 청크 스토리지에서 특정 시점을 복원
rdc backup restore my-app --at <snapshot> --as my-app --up
```

**왜 풀인가요?** 로컬 머신이 NAT 뒤에 있습니다. 클라우드가 푸시할 수 없습니다. 하지만 클라우드에는 접근할 수 있습니다. 풀은 리포지터리를 집으로 가져옵니다.

**전체 사이클:** 개발에서 생성 → 클라우드로 푸시 → 프로덕션에서 풀 → `--up`. 리포지터리 하나, 어떤 머신이든, 어떤 클라우드든.

> 예약, 자동화된 백업, 복원: [백업 및 복원](/ko/docs/backup-restore).

---

## 프록시 및 SSL

### 1. 인프라 Config

```bash
rdc machine infra set my-server  # 구성: 기본 도메인, 공용 IP, 포트 범위
rdc machine infra show my-server  # 구성 검토
rdc machine infra push my-server  # 원격에 프록시 config 푸시
```

**라우팅 작동 방식:**
- Traefik이 `rediacc.service_name` 및 `rediacc.service_port` 레이블을 통해 컨테이너를 자동으로 검색합니다.
- 경로: `{service}-{networkId}.{baseDomain}` → 컨테이너 IP:포트
- SSL: Cloudflare DNS-01 챌린지를 통한 Let's Encrypt (자동 갱신, 와일드카드 인증서)

### 2. 프록시 템플릿

```bash
rdc repo admin template apply infra --template proxy  # 리포지터리에 프록시 배포
rdc repo up infra  # Traefik 시작
```

이제 Traefik이 이 머신의 모든 리포지터리로 외부 트래픽을 라우팅합니다. 모든 컨테이너는 자동으로 HTTPS 엔드포인트를 갖습니다.

```bash
# https://my-app.example.com으로 이동 → 컨테이너로 라우팅됨
# 데이터베이스용 TCP/UDP 포워딩:
#   rediacc.tcp_ports=3306,5432 → 자동 할당된 외부 포트
```

> 라우팅 규칙, DNS, TLS 구성: [네트워킹](/ko/docs/networking).

---

## 다음 단계

- **[마이그레이션 가이드](/ko/docs/migration)** - 기존 프로젝트를 Rediacc 리포지터리로 가져오기
- **[모니터링](/ko/docs/monitoring)** - 머신 상태, 컨테이너, 서비스, 진단
- **[CLI 참조](/ko/docs/cli-application)** - 전체 명령 참조
- **[치트 시트](/ko/docs/rdc-cheat-sheet)** - 빠른 명령 조회
- **[문제 해결](/ko/docs/troubleshooting)** - 일반적인 문제 해결책
- **[Rediacc 규칙](/ko/docs/rules-of-rediacc)** - Rediaccfile 모범 사례 및 배포 체크리스트
