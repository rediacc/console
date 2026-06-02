---
title: "온프레미스 설치"
description: "자체 인프라에서 계정 서버 및 CLI 배포를 실행하는 방법입니다."
category: "Guides"
order: 5
language: ko
sourceHash: "c8c9aceeeeea1411"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc는 자체 인프라에서 완전히 실행할 수 있습니다. 독립 실행형 Docker 이미지에는 계정 서버, 웹 포털, 마케팅 사이트, CLI 배포 엔드포인트가 포함되어 있습니다. Rediacc의 호스팅 서비스에 대한 외부 의존성은 필요하지 않습니다.

## Docker 이미지

독립 실행형 이미지를 가져옵니다.

```bash
docker pull ghcr.io/rediacc/server:stable
```

기본 설정으로 실행합니다.

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

이미지에서 제공하는 항목:
- `/account/api/v1/`의 계정 API
- `/account/`의 웹 포털
- `/`의 마케팅 사이트
- `/releases/`의 CLI 아티팩트
- `/bin/`의 Renet 바이너리

## 서버에서 CLI 설치하기

사용자는 온프레미스 서버에서 직접 CLI를 설치할 수 있습니다. 설치 스크립트는 업데이트 채널을 자동으로 감지하고 서버에서 업데이트를 확인하도록 CLI를 구성합니다.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

이 단일 명령은 다음을 수행합니다.
1. 서버의 `/releases/` 엔드포인트에서 CLI 바이너리를 다운로드합니다.
2. `/account/api/v1/.well-known/server-info`를 쿼리하여 업데이트 채널을 검색합니다.
3. 서버 URL, 업데이트 채널, 암호화 키를 포함한 `server.json`을 작성합니다.
4. `rdc update`가 향후 업데이트를 위해 서버를 확인하도록 구성합니다.

`REDIACC_CHANNEL` 변수는 필요하지 않습니다. 설치 스크립트는 서버 구성에서 채널을 자동으로 읽습니다.

## 명명된 config를 사용한 CLI 구성

여러 서버(온프레미스, 프로덕션, edge)에 연결하는 사용자의 경우, 명명된 config를 사용하면 각 환경을 독립적으로 유지할 수 있습니다.

```bash
# 온프레미스 서버에 대한 config 생성
rdc config init --name myserver --server https://account.example.com

# 해당 config로 로그인
rdc --config myserver subscription login

# --config를 사용하는 모든 명령은 온프레미스 서버를 사용합니다
rdc --config myserver machine query --name prod-1
```

각 명명된 config는 자체 계정 서버 URL 및 구독 토큰을 저장합니다. config를 전환하면 전체 서버 컨텍스트가 전환됩니다.

## 에어갭 환경

인터넷 액세스가 없는 환경의 경우, 서버 URL과 사용자 정의 릴리스 URL을 모두 설정합니다.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

CLI는 공개 릴리스 CDN 대신 `account.example.com/releases/cli/stable/manifest.json`에서 업데이트를 확인합니다.

서버가 완전히 오프라인인 경우, 번들된 tarball에서 npm을 통해 CLI를 설치합니다.

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## 환경 변수 참조

| 변수 | 사용처 | 목적 |
|---|---|---|
| `REDIACC_SERVER_URL` | 설치 스크립트 | 계정 서버 URL. 채널 및 암호화 키를 자동으로 검색합니다. |
| `REDIACC_RELEASES_URL` | 설치 스크립트, CLI 업데이터 | CLI 바이너리에 대한 사용자 정의 릴리스 엔드포인트. 기본값: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | 설치 스크립트 | 업데이트 채널을 재정의합니다. 설정되지 않은 경우 서버에서 자동으로 감지됩니다. |
| `REDIACC_ACCOUNT_SERVER` | CLI 런타임 | 모든 CLI 명령에 대한 계정 서버 URL을 재정의합니다. |
| `RDC_UPDATE_CHANNEL` | CLI 런타임 | `rdc update`의 업데이트 채널을 재정의합니다. |

## 서버 구성

온프레미스 Docker 이미지는 호스팅 서비스와 동일한 `ENVIRONMENT` 변수를 사용합니다. Docker 환경 또는 오케스트레이션 config에서 설정합니다.

- `ENVIRONMENT=production` (기본값): 표준 리소스 제한; 이 서버에 연결하는 CLI의 기본값은 **stable** 업데이트 채널입니다. `production` 값 이름은 레거시 배포 식별자입니다. `production`과 `edge` 모두 프로덕션 품질입니다.
- `ENVIRONMENT=edge`: 2X Community 제한; CLI 기본값은 **edge** 업데이트 채널입니다.

각 환경이 제공하는 항목에 대한 자세한 내용은 [릴리스 채널](/ko/docs/release-channels)을 참조하세요.

## 서버가 CLI에 알려주는 정보

CLI가 서버에 연결하면 `/.well-known/server-info`를 쿼리하여 다음을 검색합니다.

- **E2E 암호화 공개 키**: 제로 지식 config 저장을 위해 사용됩니다.
- **최소 CLI 버전**: 오래된 CLI의 연결을 차단합니다.
- **업데이트 채널**: CLI에 업데이트에 사용할 릴리스 채널을 알려줍니다.
- **환경**: 서버가 실행 중인 배포 프로필(표준 제한 vs. 2X 제한이 있는 edge)입니다.

이 자동 구성을 통해 사용자는 서버 URL만 있으면 됩니다. 나머지는 모두 자동으로 검색됩니다.

## 에어갭 배포의 라이선스

에어갭 및 셀프 호스팅 온프레미스 서버는 업스트림 마스터 키로 서명된 **위임 인증서**를 사용하여 로컬에서 라이선스를 발급합니다. 인증서는 온프레미스 서버를 플랜 제한으로 제한하고 변조 방지 체인을 생성합니다. 암호화 설계(체인 무결성, 포크 감지, 감사 증명)에 대해서는 [라이선스 체인 및 위임](/ko/docs/license-chain)을 참조하세요.

이 섹션에서는 운영 설정을 다룹니다: 키 생성, 인증서 요청, 자동 갱신 구성, 오프라인(에어갭) 갱신 흐름.

### 구독 하나, 온프레미스 설치 하나

구독에는 **한 번에 최대 하나의 활성 위임 인증서**만 있을 수 있습니다. 각 온프레미스 설치는 자체 로컬 발급 원장에 대해 월별 및 머신별 제한을 적용하므로, 여러 개의 활성 인증서가 있으면 조정할 방법이 없어 실효 할당량이 배증됩니다.

별도의 환경(프로덕션, 스테이징, DR, 멀티 리전)이 필요한 경우, 설치당 하나의 구독을 구입하세요. 단일 활성 적용은 이 계약을 성문화합니다: 두 번째 활성 인증서를 생성하려는 시도는 기존 인증서 id와 함께 `409 DELEGATION_CERT_ALREADY_ACTIVE`를 반환하고, 갱신(권장, 체인 보존) 또는 취소 후 재생성(체인 초기화) 지침을 제공합니다.

### 1. 온프레미스 Ed25519 키 쌍 생성

온프레미스 서버는 별도의 Ed25519 키 쌍을 사용하여 라이선스에 서명합니다. 업스트림의 위임 인증서는 이 특정 공개 키를 승인합니다.

```bash
# 새 키 쌍 생성
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# base64로 변환 (온프레미스가 환경 변수에서 기대하는 형식)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

개인 키를 다른 시크릿과 함께 저장합니다(예: Docker 시크릿 또는 Kubernetes Secret). 개인 키는 온프레미스 서버를 절대 벗어나지 않습니다.

### 2. 업스트림에서 위임 인증서 요청

업스트림 계정 포털에서 세 가지 방법으로 인증서를 요청할 수 있습니다.

**옵션 A: 고객 셀프 서비스 (권장).** 조직 소유자 또는 관리자로 업스트림 포털에 로그인하고 **/account/delegation-certs**로 이동합니다. **새로 만들기**를 클릭하고 온프레미스 공개 키(base64 SPKI)를 붙여넣고, 유효 기간을 선택(또는 플랜별 기본값 수락)한 후 결과 `.json` 파일을 다운로드합니다.

**옵션 B: 관리자 (교차 고객).** Rediacc 지원 또는 업스트림 시스템 관리자가 동일한 매개변수로 `POST /admin/delegation-certs`를 호출할 수 있습니다.

**옵션 C: `rdc` CLI (예정).** 향후 CLI 명령이 포털 흐름을 래핑할 예정입니다.

반환된 `.json`의 형태:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

인증서의 유효 기간은 유효성 정책(플랜별 기본값 및 상한, 구독별 재정의, 구독 종료 + 3일 유예 기간으로 제한)에 의해 결정됩니다. 응답에는 `effectiveDays`와 `reason`도 포함되어 있어 해당 값이 선택된 이유를 확인할 수 있습니다. 전체 규칙은 [라이선스 체인 - 유효성 정책](/ko/docs/license-chain)을 참조하세요.

### 3. 온프레미스 서버에 인증서 설치

다운로드한 `.json`을 알려진 경로에 저장하고 온프레미스가 이를 가리키도록 합니다.

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

임시/Docker 시크릿 워크플로의 경우, 인증서를 환경 변수에 base64로 포함합니다.

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. 업스트림 검증 및 자동 갱신 구성 (선택 사항이지만 권장)

온프레미스가 업스트림에 대한 아웃바운드 HTTPS 액세스가 있는 경우, 수동 개입 없이 인증서가 만료 전에 갱신되도록 자동 갱신을 설정합니다.

```bash
# /onprem/cert-upload이 업스트림 마스터 키에 대해 업로드된 인증서를 검증하는 데 필요합니다.
# UPSTREAM_API_KEY가 설정된 상태에서 이것이 없으면 부팅 시 빠르게 실패합니다.
UPSTREAM_PUBLIC_KEY="<upstream master Ed25519 SPKI public key, base64>"

# 자동 갱신 루프에 필요합니다. 포털에서 발급합니다:
#   조직 소유자/관리자 → /account/delegation-certs → "자동 갱신 토큰 가져오기"
# 이것이 delegation:renew 범위의 api 토큰을 얻는 유일한 방법입니다.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# 선택적 조정 (기본값 표시).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

온프레미스 자동 갱신 루프는 부팅 시 한 번 실행된 후 구성된 간격으로 실행됩니다. **적응형 임계값**(`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`)을 사용하므로 15일 COMMUNITY 인증서는 1일에 갱신이 트리거되는 대신 5일이 남았을 때 갱신됩니다. 90일 BUSINESS 인증서는 14일이 남았을 때 갱신됩니다(환경 구성 상한).

갱신에 실패하면, 인증서는 자연 만료까지 계속 사용됩니다. 실패는 1시간 동안 백오프하고 `${DELEGATION_CERT_PATH}.status.json`에 기록되며 `GET /onprem/cert-status`를 통해 노출됩니다.

### 5. 에어갭 갱신 (아웃바운드 HTTPS 없음)

온프레미스가 업스트림에 연결할 수 없는 경우, 수동 전송 흐름을 사용합니다.

1. **온프레미스 관리자 포털에서 갱신 요청을 다운로드합니다.** 온프레미스 시스템 루트로 `GET /onprem/renewal-request`를 호출합니다. 이렇게 하면 로컬 체인 헤드, 위임된 공개 키, 온프레미스 개인 키의 변조 방지 Ed25519 서명이 포함된 JSON 매니페스트가 반환됩니다.
2. **매니페스트를 업스트림으로 전송합니다.** USB, 암호화된 이메일 또는 기타 대역 외 채널을 통해 전송합니다. 매니페스트는 작으며(수 KB) 시크릿을 포함하지 않습니다.
3. **업스트림에서 매니페스트를 처리합니다.** 조직 소유자/관리자가 **/account/delegation-certs** → **갱신 요청 업로드** → 매니페스트 파일 선택을 엽니다. 업스트림은 활성 인증서의 `delegatedPublicKey`에 대해 매니페스트 서명을 검증하고(온프레미스 개인 키 보유자로부터 왔음을 증명), 재재생 방지를 확인하고(7일보다 오래된 매니페스트는 거부됨), 새 인증서를 발급합니다.
4. **업스트림 포털에서 새 인증서를 `.json` 파일로 다운로드합니다.**
5. **인증서를 온프레미스로 다시 전송합니다.**
6. **로컬 관리자 포털을 통해 온프레미스에 업로드합니다** (`POST /onprem/cert-upload`). 온프레미스는 `UPSTREAM_PUBLIC_KEY`에 대해 새 인증서를 검증하고 인증서의 `genesisSequence`가 여전히 로컬 발급 원장의 체인 항목에 연결되는지 검증합니다(전송 중 시퀀스 진행이 지원됨 - 체인이 자연스럽게 확장됨).

이 전체 루프는 온프레미스에서 네트워크 이그레스를 필요로 하지 않습니다.

#### 매니페스트 오류 모드

| 코드 | 원인 | 해결 방법 |
|---|---|---|
| `NO_ACTIVE_CERT` | 업스트림에 이 구독에 대한 활성 인증서가 없습니다. | 갱신 대신 생성 흐름을 통해 새 인증서를 발급합니다. |
| `DELEGATED_KEY_MISMATCH` | 매니페스트의 `delegatedPublicKey`가 활성 인증서와 다릅니다. | 매니페스트가 다른 온프레미스 설치의 재생일 수 있습니다. |
| `MANIFEST_SIGNATURE_INVALID` | 서명이 위임된 공개 키에 대해 검증되지 않습니다. | 매니페스트가 전송 중에 변조되었거나 다른 온프레미스에서 생성된 것입니다. |
| `MANIFEST_EXPIRED` | 매니페스트가 7일보다 오래되었습니다. | 온프레미스에서 새 갱신 요청을 생성합니다. |

#### 인증서 업로드 오류 모드

| 코드 | 원인 | 해결 방법 |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | 새 인증서의 `genesisSequence`가 로컬 체인 헤드보다 앞에 있습니다. | 업스트림이 포크된 체인에 있습니다 - 조사하세요. |
| `CHAIN_FORK_ON_UPLOAD` | 인증서의 `genesisSequence`에서의 체인 해시가 로컬 원장과 일치하지 않습니다. | 로컬 체인이 업스트림에서 분기되었습니다 - 조사하세요. |
| `Signature verification failed` | 인증서가 구성된 `UPSTREAM_PUBLIC_KEY`로 서명되지 않았습니다. | `UPSTREAM_PUBLIC_KEY`가 업스트림 마스터 공개 키와 일치하는지 확인하세요. |

### 6. 상태 및 모니터링

언제든지 온프레미스 로컬 인증서 상태를 쿼리합니다.

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <admin session>"
```

로드된 인증서의 `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry`, 그리고 `autoRenew` 블록(`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`)을 반환합니다. 이것을 모니터링 스택에 연결하여 오래된 `lastSuccessAt` 또는 null이 아닌 `lastError`에 대해 알림을 받습니다.

백업 및 감사를 위해, 온프레미스 관리자는 `GET /onprem/cert-current`를 통해 현재 로드된 서명된 인증서를 다운로드할 수도 있습니다(상승된 세션 필요).

### 위임 인증서 환경 변수 참조

| 변수 | 필수 여부 | 목적 |
|---|---|---|
| `ON_PREMISE_MODE` | 예 | 온프레미스 경로 서브셋을 활성화하려면 `true`로 설정합니다. |
| `ON_PREMISE_PRIVATE_KEY` | 예 | 위임된 서명을 위한 Base64 PKCS8 Ed25519 개인 키 |
| `ON_PREMISE_PUBLIC_KEY` | 예 | Base64 SPKI Ed25519 공개 키 (인증서의 `delegatedPublicKey`와 일치해야 함) |
| `DELEGATION_CERT_PATH` | 둘 중 하나 | 서명된 인증서 JSON의 파일 시스템 경로 |
| `DELEGATION_CERT_BASE64` | 둘 중 하나 | Base64로 인코딩된 인증서 JSON (파일 경로의 대안) |
| `UPSTREAM_PUBLIC_KEY` | `UPSTREAM_API_KEY`가 설정된 경우 또는 `/onprem/cert-upload` 작동을 위해 필요 | 업스트림 마스터 공개 키의 Base64 SPKI. 누락된 경우 부팅 시 빠르게 실패합니다. |
| `UPSTREAM_URL` | 자동 갱신을 위해 | 업스트림 계정 서버 기본 URL, 예: `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | 자동 갱신을 위해 | `delegation:renew` 범위의 api 토큰. 포털을 통해 발급합니다 - 4단계를 참조하세요. |
| `AUTO_RENEW_INTERVAL_HOURS` | 선택 사항 | 기본값 24. 인증서 갱신이 필요한지 확인하는 빈도입니다. |
| `RENEW_THRESHOLD_DAYS` | 선택 사항 | 기본값 14. 적응형 1/3-유효성 임계값의 상한으로 작용합니다. |

### 위협 모델 요약

위임 인증서 모델은 다음으로부터 보호합니다.

- **위조된 라이선스**: 온프레미스는 플랜 제한 내에서만 서명할 수 있습니다; renet은 인증서 범위를 벗어난 모든 것을 거부합니다.
- **배포 간 인증서 공유**: 갱신 시 체인 분기가 감지됩니다 (`CHAIN_FORK_DETECTED` 반환).
- **멀티 설치를 통한 할당량 우회**: 업스트림에서 단일 활성(구독당 하나의 인증서)으로 적용됩니다.
- **체인 롤백**: renet은 구독당 최고 시퀀스를 저장하고 더 낮은 시퀀스를 가진 모든 blob을 거부합니다.
- **손상된 업스트림 자격 증명**: 부트스트랩 `delegation:renew` 토큰은 전용 포털 엔드포인트를 통해서만 발급 가능하며 관리자 승인이 필요합니다. 토큰은 갱신만 허용하며 다른 리소스를 읽거나 수정할 수 없습니다.
- **매니페스트에 대한 재생 공격**: 7일보다 오래된 매니페스트는 거부됩니다.

보호하지 **않는** 것:

- **손상된 온프레미스 개인 키**: 유출된 개인 키를 통해 공격자가 인증서의 `validUntil`까지 라이선스에 서명할 수 있습니다. 완화 방법: 키 쌍을 교체(이전 인증서 취소 + 새 키로 새 인증서 생성)하고 이전 키로 서명된 모든 라이선스를 의심스러운 것으로 처리합니다.
- **손상된 업스트림 마스터 키**: 이것은 신뢰 루트입니다. 교체 절차는 여기서 다루지 않습니다.
