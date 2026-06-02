---
title: "네트워킹"
description: "리버스 프록시, Docker 레이블, TLS 인증서, DNS, TCP/UDP 포트 포워딩으로 서비스를 노출합니다."
category: "Guides"
order: 6
language: ko
sourceHash: "d60a43cd573517a1"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# 네트워킹

이 페이지는 격리된 Docker 데몬 내에서 실행되는 서비스를 인터넷에서 접근 가능하게 만드는 방법을 설명합니다. 리버스 프록시 시스템, 라우팅을 위한 Docker 레이블, TLS 인증서, DNS 및 TCP/UDP 포트 포워딩을 다룹니다.

서비스가 루프백 IP를 얻는 방법과 `.rediacc.json` 슬롯 시스템에 대해서는 [서비스](/en/docs/services#service-networking-rediaccjson)를 참조하십시오.

## 네트워크 격리

각 저장소는 네트워크 훅을 사용하여 커널 수준에서 자동으로 격리됩니다. Linux 커널 6.1 이상이 필요합니다. 구성이 필요 없습니다.

- **자동 바인드 재작성**: 서비스는 평소대로 `0.0.0.0` 또는 `127.0.0.1`에 바인딩할 수 있습니다. 커널이 투명하게 주소를 서비스에 할당된 루프백 IP로 재작성합니다. `${SERVICE_IP}`에 명시적으로 바인딩할 필요가 없습니다.
- **교차 저장소 연결 차단**: 서비스가 저장소의 `/26` 서브넷 외부의 루프백 IP에 연결하려 하면 커널이 차단합니다. 저장소 A의 프로세스는 저장소 B의 서비스에 접근할 수 없습니다.
- **애플리케이션 변경 불필요**: 서비스는 바인딩을 위해 `0.0.0.0` 또는 `localhost`를 사용하며, 커널은 올바른 루프백 IP에서만 수신하도록 보장합니다. 격리는 완전히 투명합니다.

## 작동 방식

Rediacc는 외부 트래픽을 컨테이너로 라우팅하기 위해 두 가지 구성요소의 프록시 시스템을 사용합니다.

1. **라우트 서버**, 모든 저장소 Docker 데몬에서 실행 중인 컨테이너를 검색하는 systemd 서비스입니다. 컨테이너 레이블을 검사하고 YAML 엔드포인트로 제공되는 라우팅 구성을 생성합니다.
2. **Traefik**, 5초마다 라우트 서버를 폴링하고 검색된 경로를 적용하는 리버스 프록시입니다. HTTP/HTTPS 라우팅, TLS 종료 및 TCP/UDP 포워딩을 처리합니다.

흐름은 다음과 같습니다.

```
Internet → Traefik (ports 80/443/TCP/UDP)
               ↓ polls every 5s
           Route Server (discovers containers)
               ↓ inspects labels
           Docker Daemons (/var/run/rediacc/docker-*.sock)
               ↓
           Containers (bound to 127.x.x.x loopback IPs)
```

컨테이너에 올바른 레이블을 추가하고 `renet compose`로 시작하면 자동으로 라우팅 가능해집니다. 수동 프록시 구성이 필요 없습니다.

> 라우트 서버 바이너리는 CLI 버전과 동기화되어 있습니다. CLI가 머신에서 renet 바이너리를 업데이트하면 라우트 서버가 자동으로 재시작됩니다(약 1~2초). 이로 인한 다운타임은 없습니다. Traefik은 재시작 중에도 마지막으로 알려진 구성으로 트래픽을 계속 제공하며 다음 폴링에서 새 구성을 가져옵니다. 기존 클라이언트 연결은 영향을 받지 않습니다. 애플리케이션 컨테이너는 건드리지 않습니다.

## Docker 레이블

라우팅은 Docker 컨테이너 레이블로 제어됩니다. 두 가지 계층이 있습니다.

### 계층 1: `rediacc.*` 레이블(자동)

이러한 레이블은 서비스 시작 시 `renet compose`에 의해 **자동으로 주입됩니다**. 수동으로 추가할 필요가 없습니다.

| 레이블 | 설명 | 예시 |
|-------|-------------|---------|
| `rediacc.service_name` | 서비스 식별자 | `myapp` |
| `rediacc.service_ip` | 할당된 루프백 IP | `127.0.11.2` |
| `rediacc.network_id` | 저장소 데몬 ID | `2816` |
| `rediacc.repo_name` | 저장소 이름 | `marketing` |
| `rediacc.tcp_ports` | 서비스가 수신하는 TCP 포트 | `8080,8443` |
| `rediacc.udp_ports` | 서비스가 수신하는 UDP 포트 | `53` |

컨테이너에 `rediacc.*` 레이블만 있고(`traefik.enable=true` 없음) 라우트 서버가 저장소 이름과 머신 서브도메인을 사용하여 **자동 경로**를 생성합니다.

```
{service}.{repoName}.{machineName}.{baseDomain}
```

예를 들어 베이스 도메인이 `example.com`인 머신 `server-1`의 저장소 `marketing`에서 `myapp`이라는 서비스는 다음을 얻습니다.

```
myapp.marketing.server-1.example.com
```

포크의 경우 서비스 이름은 예약어 `fork`와 태그가 결합됩니다.

```
{service}-fork-{tag}.{repoName}.{machineName}.{baseDomain}
```

예를 들어 `staging`으로 태그된 `marketing`의 포크는 다음을 얻습니다.

```
myapp-fork-staging.marketing.server-1.example.com
```

각 포크 URL은 부모 저장소의 서브도메인 아래에 있으며 기존 와일드카드 인증서로 보호되므로 새 인증서가 필요하지 않습니다. `-fork-` 구분자는 프로덕션 저장소의 실제 서비스 이름과의 충돌을 방지합니다. 사용자 정의 도메인이 있는 서비스에는 계층 2 레이블 또는 `rediacc.domain` 레이블을 사용하십시오.

#### `rediacc.domain`을 통한 사용자 정의 도메인

`docker-compose.yml`에서 `rediacc.domain` 레이블을 사용하여 서비스에 사용자 정의 도메인을 설정할 수 있습니다. 짧은 이름과 전체 도메인 모두 지원됩니다.

```yaml
labels:
  # 짧은 이름, 머신의 baseDomain을 사용하여 cloud.example.com으로 해석됨
  - "rediacc.domain=cloud"

  # 전체 도메인, 그대로 사용됨
  - "rediacc.domain=cloud.example.com"
```

점이 없는 값은 짧은 이름으로 처리되고 머신의 `baseDomain`이 자동으로 추가됩니다. 점이 있는 값은 전체 도메인으로 사용됩니다. 이는 자동 경로 생성과 CLI 표시 모두에 적용됩니다.

`machineName`이 구성된 경우 사용자 정의 도메인 서비스는 **두 가지 경로**를 얻습니다. 베이스 도메인(`cloud.example.com`)과 머신 서브도메인(`cloud.server-1.example.com`)에 각각 하나씩.

### 계층 2: `traefik.*` 레이블(사용자 정의)

사용자 정의 도메인 라우팅, TLS 또는 특정 엔트리포인트가 필요할 때 `docker-compose.yml`에 이러한 레이블을 추가하십시오. `traefik.enable=true`를 설정하면 라우트 서버가 자동 경로를 생성하는 대신 사용자 정의 규칙을 사용합니다.

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
  - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
  - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
  - "traefik.http.services.myapp.loadbalancer.server.port=8080"
```

이는 표준 [Traefik v3 레이블 구문](https://doc.traefik.io/traefik/routing/providers/docker/)을 사용합니다.

> **팁:** 내부 전용 서비스(데이터베이스, 캐시, 메시지 큐)는 `traefik.enable=true`가 있어서는 **안 됩니다**. 자동으로 주입되는 `rediacc.*` 레이블만 필요합니다.

## HTTP/HTTPS 서비스 노출

### 사전 요구사항

1. 머신에 인프라 구성됨([머신 설정, 인프라 구성](/en/docs/setup#infrastructure-configuration)):

   ```bash
   # 공유 자격증명(구성당 한 번, 모든 머신에 적용)
   rdc config infra set -m server-1 \
     --cert-email admin@example.com \
     --cf-dns-token your-cloudflare-api-token

   # 머신별 설정
   rdc config infra set -m server-1 \
     --public-ipv4 203.0.113.50 \
     --base-domain example.com

   rdc config infra push -m server-1
   ```

2. 도메인을 서버의 공용 IP로 가리키는 DNS 레코드(아래 [DNS 구성](#dns-구성) 참조).

### 레이블 추가

`docker-compose.yml`에서 노출하려는 서비스에 `traefik.*` 레이블을 추가합니다.

```yaml
services:
  myapp:
    image: myapp:latest
    environment:
      - LISTEN_ADDR=0.0.0.0:8080
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.myapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.myapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.myapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.myapp.loadbalancer.server.port=8080"

  database:
    image: postgres:17
    # traefik 레이블 없음, 데이터베이스는 내부 전용
```

| 레이블 | 목적 |
|-------|---------|
| `traefik.enable=true` | 이 컨테이너에 대한 사용자 정의 Traefik 라우팅 활성화 |
| `traefik.http.routers.{name}.rule` | 라우팅 규칙, 일반적으로 `Host(\`domain\`)` |
| `traefik.http.routers.{name}.entrypoints` | 수신할 포트: `websecure`(HTTPS IPv4), `websecure-v6`(HTTPS IPv6) |
| `traefik.http.routers.{name}.tls.certresolver` | 인증서 리졸버, 자동 Let's Encrypt에는 `letsencrypt` 사용 |
| `traefik.http.services.{name}.loadbalancer.server.port` | 컨테이너 내부에서 애플리케이션이 수신하는 포트 |

레이블의 `{name}`은 임의의 식별자입니다. 관련 라우터/서비스/미들웨어 레이블 전반에 걸쳐 일관되게 유지하기만 하면 됩니다.

> **참고:** `rediacc.*` 레이블(`rediacc.service_name`, `rediacc.service_ip`, `rediacc.network_id`)은 `renet compose`에 의해 자동으로 주입됩니다. compose 파일에 추가할 필요가 없습니다.

## TLS 인증서

TLS 인증서는 Cloudflare DNS-01 챌린지를 사용하여 Let's Encrypt를 통해 자동으로 얻어집니다. 자격증명은 구성당 한 번 구성됩니다(모든 머신에서 공유).

```bash
rdc config infra set -m server-1 \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

자동 경로는 서비스별 인증서 대신 저장소 서브도메인 수준에서 **와일드카드 인증서**를 사용합니다(`*.marketing.server-1.example.com`). 인증서는 첫 번째 `repo up` 시 Traefik에 의해 자동으로 프로비저닝됩니다. 수동 단계가 필요하지 않습니다. 포크는 부모 저장소의 기존 와일드카드를 재사용하므로 새 인증서 요청을 트리거하지 않습니다. 사용자 정의 도메인 경로는 머신 수준 와일드카드를 사용합니다(`*.server-1.example.com`).

> **Cloudflare 자격증명이 필요합니다.** 와일드카드 인증서는 DNS-01 챌린지를 사용합니다. `--cf-dns-token`(및 선택적으로 `--cert-email`) 없이는 Traefik이 챌린지를 완료할 수 없으며 HTTPS가 작동하지 않습니다. HTTP는 계속 작동합니다. 첫 번째 배포 전에 `rdc config infra set`으로 자격증명을 구성하십시오.

`traefik.http.routers.{name}.tls.certresolver=letsencrypt`가 있는 계층 2 경로의 경우 와일드카드 도메인 SAN이 경로의 호스트명에 따라 자동으로 주입됩니다.

Cloudflare DNS API 토큰은 보호하려는 도메인에 대한 `Zone:DNS:Edit` 권한이 필요합니다.

### TLS 인증서 라이프사이클

Let's Encrypt 인증서가 발급에서 각 저장소의 컨테이너까지 거치는 전체 경로:

1. **호스트에서 발급.** 머신 수준 Traefik 컨테이너(`rediacc-proxy`, `/opt/rediacc/proxy/`에 배포됨)가 ACME 갱신을 담당합니다. 모든 상태를 호스트의 `/opt/rediacc/proxy/letsencrypt/acme.json`에 저장합니다. 갱신은 만료 약 30일 전에 자동으로 트리거됩니다. `--cf-dns-token`이 구성된 한 운영자 조치가 필요하지 않습니다.

2. **저장소별 덤핑(선택사항).** 자체 컨테이너 내부에 인증서 파일이 필요한 서비스(예: `.pem`을 직접 읽는 메일 서버)는 소형 `traefik-certs-dumper` 컨테이너를 함께 배포합니다. 덤퍼는 `/opt/rediacc/proxy/letsencrypt`를 읽기 전용으로 바인드 마운트하고 추출된 인증서 + 키를 `cert.pem` / `key.pem`으로 저장소의 데이터 볼륨에 씁니다. 이를 위해 저장소별 Docker 데몬이 마운트 네임스페이스 허용 목록에 `/opt/rediacc/proxy`가 있어야 합니다. 이는 기본적으로 이미 포함되어 있습니다.

3. **클라이언트 측 캐시(`rediacc.json`).** CLI는 `acme.json`의 압축 복사본을 `baseDomain`으로 키잉된 구성 파일의 `acmeCertCache` 아래에 캐시합니다. 이를 통해 여러 머신이 인증서를 공유(`rdc config cert-cache push -m <machine>`)하고 오프라인 인벤토리로 활용할 수 있습니다.

**클라이언트 캐시 동기화 트리거:**

- `rdc repo up` 후 자동으로, 단 머신의 `baseDomain`에 대한 로컬 캐시가 6시간보다 오래된 경우에만. 새로운 캐시는 그대로 유지되므로 연속 배포가 SSH를 과도하게 사용하지 않습니다.
- 온디맨드: `rdc config cert-cache pull -m <machine>`(강제 pull) 또는 `rdc machine query --name <machine> --sync-certs`(상태 쿼리의 부작용으로 pull).
- `rdc config infra push` 시 캐시가 머신으로 푸시됩니다(더 긴 만료 기간을 가진 로컬 인증서가 원격보다 우선).

**캐시 유지 관리:**

- 오래된 자동 경로 항목(예: `service-3200.rediacc.io` 같은 이전 네트워크 ID 태그 도메인)은 모든 pull 시 정리됩니다.
- `notAfter`가 7일 이상 지난 인증서는 완전히 제거됩니다. 비활성 상태이며 캐시를 불필요하게 부풀릴 뿐입니다.
- `rdc config cert-cache clear`로 모든 것을 지웁니다. `rdc config cert-cache status`는 인벤토리를 표시합니다.

**문제 해결:** `traefik-certs-dumper`가 `/traefik/acme.json: no such file or directory`로 충돌 루프하는 경우 저장소별 데몬이 호스트의 letsencrypt 저장소를 볼 수 없습니다. (a) `/opt/rediacc/proxy/letsencrypt/acme.json`이 호스트에 존재하는지(이는 호스트 수준 `rediacc-proxy`의 책임입니다) 및 (b) 저장소별 데몬이 `/opt/rediacc/proxy`를 허용 목록에 포함하는 충분히 최신의 renet으로 시작되었는지 확인하십시오. renet을 업그레이드한 후 `rdc repo up`으로 저장소를 재배포하여 적용하십시오.

> **실험적:** 자동 동기화 주기 및 만료 기반 정리는 renet 0.9+에서 출시되었습니다. 이전 CLI/renet 버전은 `rdc config cert-cache pull`을 통한 순수 수동 동기화를 사용합니다.

## TCP/UDP 포트 포워딩

비HTTP 프로토콜(메일 서버, DNS, 외부에 노출된 데이터베이스)의 경우 TCP/UDP 포트 포워딩을 사용하십시오.

### 1단계: 포트 등록

인프라 구성 중에 필요한 포트를 추가합니다.

```bash
rdc config infra set -m server-1 \
  --tcp-ports 25,143,465,587,993 \
  --udp-ports 53

rdc config infra push -m server-1
```

이는 `tcp-{port}` 및 `udp-{port}`로 명명된 Traefik 엔트리포인트를 생성합니다.

> 포트를 추가하거나 제거한 후에는 항상 `rdc config infra push`를 다시 실행하여 프록시 구성을 업데이트하십시오.

### 2단계: TCP/UDP 레이블 추가

compose 파일에서 `traefik.tcp.*` 또는 `traefik.udp.*` 레이블을 사용합니다.

```yaml
services:
  mail-server:
    image: ghcr.io/docker-mailserver/docker-mailserver:latest
    labels:
      - "traefik.enable=true"

      # SMTP (port 25)
      - "traefik.tcp.routers.mail-smtp.entrypoints=tcp-25"
      - "traefik.tcp.routers.mail-smtp.rule=HostSNI(`*`)"
      - "traefik.tcp.routers.mail-smtp.service=mail-smtp"
      - "traefik.tcp.services.mail-smtp.loadbalancer.server.port=25"

      # IMAPS (port 993), TLS passthrough
      - "traefik.tcp.routers.mail-imaps.entrypoints=tcp-993"
      - "traefik.tcp.routers.mail-imaps.rule=HostSNI(`mail.example.com`)"
      - "traefik.tcp.routers.mail-imaps.tls.passthrough=true"
      - "traefik.tcp.routers.mail-imaps.service=mail-imaps"
      - "traefik.tcp.services.mail-imaps.loadbalancer.server.port=993"
```

주요 개념:
- **`HostSNI(\`*\`)`** 임의의 호스트명과 일치합니다(SNI를 보내지 않는 프로토콜용, 예: 일반 SMTP)
- **`tls.passthrough=true`** Traefik이 복호화 없이 원시 TLS 연결을 전달함을 의미합니다. 애플리케이션이 TLS를 직접 처리합니다
- 엔트리포인트 이름은 `tcp-{port}` 또는 `udp-{port}` 규칙을 따릅니다

### 일반 TCP 예시(데이터베이스)

TLS 패스스루 없이 데이터베이스를 외부에 노출하려면(Traefik이 원시 TCP를 전달):

```yaml
services:
  postgres:
    image: postgres:17
    labels:
      - "traefik.enable=true"
      - "traefik.tcp.routers.mydb.entrypoints=tcp-5432"
      - "traefik.tcp.routers.mydb.rule=HostSNI(`*`)"
      - "traefik.tcp.services.mydb.loadbalancer.server.port=5432"
```

포트 5432는 사전 구성되어 있으므로(아래 참조) `--tcp-ports` 설정이 필요하지 않습니다.

> **보안 참고:** 데이터베이스를 인터넷에 노출하는 것은 위험합니다. 원격 클라이언트가 직접 접근해야 하는 경우에만 사용하십시오. 대부분의 설정에서는 데이터베이스를 내부로 유지하고 애플리케이션을 통해 연결하십시오.

### 사전 구성된 포트

다음 TCP/UDP 포트에는 기본적으로 엔트리포인트가 있습니다(`--tcp-ports`로 추가할 필요 없음). 엔트리포인트는 구성된 주소 패밀리에 대해서만 생성됩니다. IPv4 엔트리포인트는 `--public-ipv4`가, IPv6 엔트리포인트는 `--public-ipv6`이 필요합니다.

| 포트 | 프로토콜 | 일반 용도 |
|------|----------|------------|
| 80 | HTTP | 웹(HTTPS로 자동 리다이렉트) |
| 443 | HTTPS | 웹(TLS) |
| 3306 | TCP | MySQL/MariaDB |
| 5432 | TCP | PostgreSQL |
| 6379 | TCP | Redis |
| 27017 | TCP | MongoDB |
| 11211 | TCP | Memcached |
| 5672 | TCP | RabbitMQ |
| 9092 | TCP | Kafka |
| 53 | UDP | DNS |
| 10000~10010 | TCP | 동적 범위(자동 할당) |

## DNS 구성

### 자동 DNS(Cloudflare)

`--cf-dns-token`이 구성된 경우 `rdc config infra push`는 Cloudflare에서 머신 서브도메인의 DNS 레코드를 자동으로 생성합니다.

| 레코드 | 유형 | 내용 | 생성자 |
|--------|------|---------|------------|
| `server-1.example.com` | A / AAAA | 머신 공용 IP | `push-infra` |
| `*.server-1.example.com` | A / AAAA | 머신 공용 IP | `push-infra` |
| `*.marketing.server-1.example.com` | A / AAAA | 머신 공용 IP | `repo up` |

머신 수준 레코드는 `push-infra`에 의해 생성되며 사용자 정의 도메인 경로(`rediacc.domain`)를 포함합니다. 저장소별 와일드카드 레코드는 `repo up`에 의해 자동으로 생성되며 해당 저장소의 자동 경로를 포함합니다.

이는 멱등성이 있습니다: IP가 변경되면 기존 레코드가 업데이트되고, 이미 올바른 경우 변경되지 않습니다.

베이스 도메인 와일드카드(`*.example.com`)는 `rediacc.domain=erp` 같은 사용자 정의 도메인 레이블을 사용하는 경우 수동으로 생성해야 합니다.

### 수동 DNS

Cloudflare를 사용하지 않거나 DNS를 수동으로 관리하는 경우 A(IPv4) 및/또는 AAAA(IPv6) 레코드를 생성하십시오.

```
# 머신 서브도메인(rediacc.domain=erp 같은 사용자 정의 도메인 경로용)
server-1.example.com           A     203.0.113.50
*.server-1.example.com         A     203.0.113.50
*.server-1.example.com         AAAA  2001:db8::1

# 저장소별 와일드카드(myapp.marketing.server-1.example.com 같은 자동 경로용)
*.marketing.server-1.example.com    A     203.0.113.50
*.marketing.server-1.example.com    AAAA  2001:db8::1

# 베이스 도메인 와일드카드(rediacc.domain=erp 같은 사용자 정의 도메인 서비스용)
*.example.com                  A     203.0.113.50
```

Cloudflare DNS가 구성된 경우 저장소별 와일드카드 레코드가 `repo up`에 의해 자동으로 생성됩니다. 여러 머신이 있는 경우 각 머신은 자체 IP를 가리키는 자체 DNS 레코드를 갖습니다.

## 미들웨어

Traefik 미들웨어는 요청과 응답을 수정합니다. 레이블을 통해 적용하십시오.

### HSTS(HTTP Strict Transport Security)

```yaml
labels:
  - "traefik.http.middlewares.myapp-hsts.headers.stsSeconds=15768000"
  - "traefik.http.middlewares.myapp-hsts.headers.stsIncludeSubdomains=true"
  - "traefik.http.middlewares.myapp-hsts.headers.stsPreload=true"
  - "traefik.http.routers.myapp.middlewares=myapp-hsts"
```

### 대용량 파일 업로드 버퍼링

```yaml
labels:
  - "traefik.http.middlewares.myapp-buffering.buffering.maxRequestBodyBytes=536870912"
  - "traefik.http.routers.myapp.middlewares=myapp-buffering"
```

### 다중 미들웨어

쉼표로 구분하여 미들웨어를 연결합니다.

```yaml
labels:
  - "traefik.http.routers.myapp.middlewares=myapp-hsts,myapp-buffering"
```

사용 가능한 미들웨어의 전체 목록은 [Traefik 미들웨어 문서](https://doc.traefik.io/traefik/middlewares/overview/)를 참조하십시오.

## 진단

서비스에 접근할 수 없는 경우 서버에 SSH로 접속하여 라우트 서버 엔드포인트를 확인하십시오.

### 상태 확인

```bash
curl -s http://127.0.0.1:7111/health | python3 -m json.tool
```

전체 상태, 검색된 라우터 및 서비스 수, 자동 경로 활성화 여부를 표시합니다.

### 검색된 경로

```bash
curl -s http://127.0.0.1:7111/routes.json | python3 -m json.tool
```

규칙, 엔트리포인트 및 백엔드 서비스가 있는 모든 HTTP, TCP, UDP 라우터를 나열합니다.

### 포트 할당

```bash
curl -s http://127.0.0.1:7111/ports | python3 -m json.tool
```

동적으로 할당된 포트의 TCP 및 UDP 포트 매핑을 표시합니다.

### 일반적인 문제

| 문제 | 원인 | 해결책 |
|---------|-------|----------|
| 서비스가 경로에 없음 | 컨테이너가 실행 중이지 않거나 레이블이 없음 | 저장소 데몬에서 `docker ps`로 확인. 레이블 점검 |
| 인증서가 발급되지 않음 | DNS가 서버를 가리키지 않거나 유효하지 않은 Cloudflare 토큰 | DNS 해석 확인. Cloudflare API 토큰 권한 점검 |
| 502 Bad Gateway | 애플리케이션이 선언된 포트에서 수신하지 않음 | 앱이 실행 중인지 확인하고 포트가 `loadbalancer.server.port`와 일치하는지 점검 |
| TCP 포트에 접근할 수 없음 | 인프라에 포트가 등록되지 않음 | `rdc config infra set --tcp-ports ...` 및 `push-infra` 실행 |
| 라우트 서버가 이전 버전 실행 중 | 바이너리가 업데이트되었지만 서비스가 재시작되지 않음 | 프로비저닝 시 자동으로 발생함. 수동: `sudo systemctl restart rediacc-router` |
| STUN/TURN 릴레이에 접근할 수 없음 | 릴레이 주소가 시작 시 캐시됨 | DNS 또는 IP 변경 후 서비스를 다시 생성하여 새 네트워크 구성을 적용 |

## 완전한 예시

이 예시는 PostgreSQL 데이터베이스가 있는 웹 애플리케이션을 배포합니다. 앱은 TLS와 함께 `app.example.com`에서 공개적으로 접근 가능합니다. 데이터베이스는 내부 전용입니다.

### docker-compose.yml

```yaml
services:
  webapp:
    image: myregistry/webapp:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      LISTEN_ADDR: 0.0.0.0:3000
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.webapp.rule=Host(`app.example.com`)"
      - "traefik.http.routers.webapp.entrypoints=websecure,websecure-v6"
      - "traefik.http.routers.webapp.tls.certresolver=letsencrypt"
      - "traefik.http.services.webapp.loadbalancer.server.port=3000"
      # HSTS
      - "traefik.http.middlewares.webapp-hsts.headers.stsSeconds=15768000"
      - "traefik.http.middlewares.webapp-hsts.headers.stsIncludeSubdomains=true"
      - "traefik.http.routers.webapp.middlewares=webapp-hsts"

  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    # traefik 레이블 없음, 내부 전용
```

### Rediaccfile

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

### DNS

서버의 공용 IP를 가리키는 `app.example.com`의 A 레코드를 생성합니다.

```
app.example.com   A   203.0.113.50
```

### 배포

```bash
rdc repo up --name my-app -m server-1
```

몇 초 내에 라우트 서버가 컨테이너를 검색하고, Traefik이 경로를 가져오고, TLS 인증서를 요청하면 `https://app.example.com`이 활성화됩니다.
