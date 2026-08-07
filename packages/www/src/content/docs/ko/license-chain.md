---
title: "라이선스 체인 및 위임"
description: "변조 방지 라이선스 발급, 온프레미스를 위한 위임 서명, 포크 감지."
category: "Guides"
order: 8
language: ko
sourceHash: "6486263bfb9ebf98"
sourceCommit: "fc24769cfd0684622952395c5bafe44e6180530d"
---

# 라이선스 체인 및 위임

Rediacc는 라이선스 발급에 변조 방지 해시 체인을, 온프레미스 배포에는 위임 인증서 모델을 사용합니다. 이 페이지에서는 시스템이 변조, 재전송 공격, 라이선스 공유로부터 어떻게 보호하는지 설명합니다.

## 체인이 필요한 이유

계정 서버가 발급하는 모든 라이선스는 추가 전용 원장에 기록됩니다. 각 항목은 SHA-256 해시를 통해 이전 항목과 연결되어 체인을 형성합니다. 이 체인은 변조를 감지할 수 있는 세 가지 속성을 갖습니다.

1. **시퀀스 번호**는 구독당 전역적으로 단조 증가합니다. 항목을 건너뛰거나 순서를 변경하면 체인이 깨집니다.
2. **체인 해시**는 각 항목을 모든 이전 항목과 바인딩합니다. 과거 항목을 수정하면 그 이후의 모든 항목이 무효화됩니다.
3. **Renet은 서명 키와 구독별로 확인한 최고 시퀀스를 저장합니다**. 시퀀스를 롤백하는 서버는 즉시 감지됩니다.

## 라이선스 발급 방법

CLI가 저장소 라이선스를 요청하면 계정 서버는 다음을 수행합니다.

1. 구독에 대한 현재 체인 헤드(마지막 시퀀스 + 해시)를 읽습니다.
2. 다음 시퀀스 번호와 이전 체인 해시가 포함된 라이선스 페이로드를 빌드합니다.
3. Ed25519로 페이로드에 서명합니다.
4. `chainHash = SHA256(prevChainHash + ":" + signedPayload)`를 계산합니다.
5. 원장에 항목을 원자적으로 추가합니다. 두 개의 동시 요청이 같은 시퀀스에서 충돌하면, 실패한 요청이 다음 시퀀스를 재획득하고 다시 서명합니다.
6. 체인 해시와 함께 서명된 블롭을 CLI에 반환합니다.

`sequence`와 `prevChainHash`는 서명된 페이로드 내에 있으므로 서명을 무효화하지 않고는 수정할 수 없습니다. `chainHash`는 봉투에 있으며 순환 의존성을 피하기 위해 서명 후에 계산됩니다.

## 라이선스 갱신 방법

발급은 워크스테이션에서 사용자 본인으로 인증된 상태로 실행됩니다. 갱신은 머신에서 실행되는데, 머신은 계정 자격 증명을 전혀 보유하지 않습니다. 그래서 다른 통로가 필요합니다.

```
POST /licenses/renew
{ license: <설치된 서명 블롭>, machineId, clusterId? }
```

**제시된 라이선스 자체가 자격 증명입니다.** 이 엔드포인트에는 API 토큰이 없습니다. 서버는 머신의 Renet과 똑같은 방식으로 블롭의 Ed25519 서명을, 블롭에 위임 인증서가 딸려 있으면 그 인증서를 거쳐, 검증합니다. 어떤 저장소에 대해 올바르게 서명된 라이선스를 보유하고 있다는 사실 자체가 권한의 증거이며, 그것을 가진 머신은 이미 권한을 부여받은 것입니다.

이 엔드포인트의 전체 URL은 서버가 발급하거나 갱신하는 모든 라이선스 안에 `renewalUrl`로 함께 전달됩니다. 머신은 설정으로 주소를 받는 대신 자기 라이선스에서 자기 계정 서버의 주소를 읽어오며, 덕분에 두 계정 유니버스를 함께 사용하는 머신도 양쪽 모두에 대해 갱신할 수 있습니다.

갱신된 블롭은 제시된 블롭의 저장소 GUID, 그랜드 GUID, 종류를 그대로 유지하고, 같은 원장에서 다음 시퀀스와 거기에 이어지는 체인 해시를 가져오며, 새로 계산된 유효 기간을 받습니다. 머신 ID는 블롭을 제시한 머신에 다시 바인딩되는데, 이것이 VM 마이그레이션이 40일 유예 기간 안에서 스스로 회복되는 방식입니다. 스토리지 신원(LUKS UUID 또는 스토리지 지문)은 그대로 이어집니다. 네트워크 호출로는 대상 디스크를 다시 스캔할 수 없기 때문입니다.

### 거부 사유

| 코드 | 상태 | 의미 |
|---|---|---|
| `INVALID_LICENSE_SIGNATURE` | 403 | 블롭의 서명이 검증되지 않았거나, 해당 시퀀스에서 서버 원장의 체인 해시와 일치하지 않음 |
| `INVALID_LICENSE_PAYLOAD` | 400 | 블롭의 형식이 잘못됨 |
| `DELEGATION_CERT_INVALID` | 403 | 첨부된 인증서가 제약 조건 또는 마스터 키 서명 검증에 실패함 |
| `DELEGATION_CERT_EXPIRED` | 403 | 첨부된 인증서가 유효 기간을 벗어남 |
| `DELEGATION_CERT_REVOKED` | 403 | 첨부된 인증서가 업스트림에서 취소됨 |
| `LICENSE_IDENTITY_MISMATCH` | 403 | 제시한 머신이 라이선스 대상 머신이 아니며 40일 유예 기간도 지남 |
| `SUBSCRIPTION_LAPSED` | 403 | 구독이 만료되었거나 정지됨 |
| `GRACE_PERIOD_ENDED` | 403 | 구독의 유예 기간이 끝남 |
| `TRIAL_REQUIRED` | 403 | 구독에 활성 체험판 또는 요금제가 필요함 |
| `REPO_GUID_OWNERSHIP_CONFLICT` | 403 | 저장소 GUID가 다른 구독에 속함 |
| `LICENSE_RENEWAL_FAILED` | 500 | 분류되지 않은 그 밖의 모든 경우 |

거부되어도 설치된 라이선스는 그대로 남습니다. 머신은 그 라이선스가 하드 만료될 때까지 가진 것으로 계속 동작합니다.

### 갱신과 머신 슬롯

갱신에 성공하면 머신의 활성화 레코드가 갱신됩니다. 슬롯이 없었다면 확보하고, 있었다면 기간을 새로 고칩니다. 발급과 달리 상한을 초과했다는 이유로 거부되는 일은 없습니다. 응답에는 `overLimit`이 담기고 활성화에 표시가 붙어, 포털과 라이선스 상태 엔드포인트, `rdc subscription status`에서 모두 확인할 수 있습니다. 진짜로 새로운 라이선스를 발급하는 것은 여전히 상한에서 확실히 막힙니다. 그 이유는 [구독 및 라이선싱 - 머신 슬롯](/ko/docs/subscription-licensing)에 설명되어 있습니다.

### 배포 순서

계정 서버는 위 필드들에 의존하는 CLI 및 Renet Agent 빌드보다 먼저 배포합니다. 라이선스에서 `renewalUrl`을 찾지 못한 Renet Agent는 실패하는 대신 해당 저장소를 건너뛰고 그 사실을 알리므로, 워크스테이션 쪽 새로 고침이 그 필드를 채워줄 때까지 예전 라이선스도 계속 동작합니다. 반대 순서로 진행하면, 아직 존재하지도 않는 엔드포인트를 찾는 머신들이 생깁니다.

## Renet의 검증 방법

Renet을 실행하는 각 머신은 `{licenseDir}/chain-state.json`(즉 `/var/lib/rediacc/license/chain-state.json`, 저장소별 `repos/` 디렉터리와 같은 레벨)에 마지막으로 알려진 체인 상태를 저장합니다. 체인 상태는 서명 키, 구독, 저장소, 데이터스토어별로 범위가 지정되며 `"<keyId>:<subscriptionId>:<repositoryGuid>:<datastoreId>"` 형태의 키로 관리됩니다(머신의 기본 데이터스토어에 있는 저장소라면 데이터스토어 부분은 비워집니다).

이 키에서 저장소와 데이터스토어 부분이 핵심입니다. 서버의 시퀀스 번호는 구독 단위이므로, 한 구독으로 여러 저장소를 보유한 머신에서는 저장소 B에 대해 기록된 체인 헤드가 저장소 A가 곧 제시할 라이선스보다 앞서게 되고, 저장소 A는 자신과 아무 상관 없는 재전송으로 거부되어 버립니다. 데이터스토어 포크는 같은 문제를 더 키웁니다. 복제본은 저장소의 GUID를 그대로 유지하고 데이터스토어 아이디만 새로 발급되므로, 데이터스토어 부분이 없으면 포크 쪽의 더 최신 라이선스가 원본이 여전히 검증에 사용하는 헤드를 앞으로 밀어버립니다. 기록하는 헤드의 범위를 라이선스가 가리키는 저장소와 데이터스토어 단위로 좁히면 두 문제가 모두 사라집니다. 구버전 Renet Agent가 더 짧은 키 형식으로 기록한 항목은 상태가 처음 저장될 때 폐기되고, 다음 검증에서 헤드가 다시 만들어집니다.

체인 상태를 읽고 진행시키는 것은 전체 계층에서 검증하는 작업뿐입니다. 운영 계층은 읽지도 진행시키지도 않으므로, 저장소를 시작한다고 해서 헤드가 움직이는 일은 없습니다.

모든 라이선스 검증 시 Renet은 다음을 확인합니다.

| 확인 | 실패 의미 |
|---|---|
| Ed25519 서명이 유효함 | 라이선스가 위조되거나 변조됨 |
| `sequence >= lastKnownSequence` | 서버가 체인을 롤백함(재전송 공격) |
| `lastKnownSequence`의 반복이 같은 `chainHash`를 가짐 | 갈라진 체인이 시퀀스 번호를 재사용함 |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | 체인 항목이 수정됨 |

이미 설치된 라이선스를 다시 검증하는 것은 되돌림이 아닙니다. 같은 시퀀스에 같은 체인 해시가 함께 오면 그대로 수락되며, 덕분에 머신은 저장소를 시작할 때마다 같은 파일을 검증할 수 있습니다.

확인 중 하나라도 실패하면 라이선스가 거부되고 실패 이유가 보고됩니다.

## 위임 인증서(온프레미스)

에어갭 또는 자체 호스팅 배포의 경우 업스트림 계정 서버는 온프레미스 서버가 자체 Ed25519 키로 라이선스에 서명할 수 있도록 승인하는 **위임 인증서**를 발급합니다. 인증서는 온프레미스 서버가 할 수 있는 작업을 제한합니다.

### 인증서 구조

위임 인증서에는 다음이 포함됩니다.

- `subscriptionId` -- 이 인증서가 적용되는 구독
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` -- 플랜 제한 내장
- `maxTotalIssuances` -- 체인 시퀀스 번호의 상한
- `delegatedPublicKey` -- 온프레미스 서버의 Ed25519 공개 키(SPKI base64). 이 키의 16자리 16진수 지문(원시 키에 대한 `SHA-256`의 처음 8바이트)이, 이 키로 서명되는 모든 라이선스 블롭에 기록되는 `publicKeyId`입니다. `publicKeyId`는 항상 실제 키 지문이며, `"default"`와 같은 자리표시자가 되는 일은 없습니다.
- `genesisHash` -- 체인 시작점(이전 인증서에서의 계속 또는 "genesis")
- `genesisSequence` -- 발급 시 체인 시퀀스. 전송 중 체인이 진행된 경우 새 인증서가 로컬 발급 원장의 알려진 항목과 연결되는지 `/onprem/cert-upload`가 검증할 때 사용됩니다. 하위 호환성을 위해 선택적입니다(없으면 0으로 처리됨).
- `validFrom`, `validUntil` -- 유효 기간(아래 유효성 정책에 의해 규정됨)
- 업스트림 마스터 Ed25519 키로 서명됨

### 위임 작동 방식

1. 엔터프라이즈 관리자가 온프레미스 서버에서 Ed25519 키 쌍을 생성합니다.
2. 관리자가 업스트림에 위임 인증서를 요청합니다.
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. 업스트림이 마스터 키로 인증서에 서명하고 반환합니다.
4. 온프레미스 서버는 인증서와 개인 키를 저장하고 라이선스에 서명할 준비를 합니다.
5. CLI가 온프레미스 서버에 라이선스를 요청하면 서버는 위임 키로 서명하고, **위임 인증서 전체를 라이선스 블롭 안에 임베드합니다**(`delegationCert` 필드). 인증서는 별도로 가져오지 않으며, 모든 저장소 라이선스에 함께 포함되어 전달됩니다.
6. Renet은 다음 순서로 **2단계 검증**을 수행합니다.
   - 내장된 업스트림 마스터 키에 대해 인증서의 서명을 검증합니다.
   - 인증서의 유효 기간(`validFrom` / `validUntil`)을 성장 작업(`repo create`, `fork`, `resize`, `expand`)과 백업 전송(`repo push`, `pull`, backups)에 대해 강제합니다. 운영 계층(`repo up`, `up all`, autostart)은 이 유효 기간 검사만 건너뛰며, 이는 이미 라이선스 만료 검사를 건너뛰는 방식과 같습니다. 실행 중인 워크로드는 인증서가 만료되었다는 이유만으로 중단되지 않지만, 만료된 인증서는 새로운 어떤 작업도 승인할 수 없습니다. 서명, 키 바인딩, 그 밖의 모든 인증서 제약은 모든 계층에서 계속 강제됩니다.
   - `fingerprint(cert.delegatedPublicKey) == blob.publicKeyId`(16자리 16진수 키 지문)를 요구합니다. 이렇게 하면 인증서는 자신이 위임한 바로 그 키로 서명된 라이선스만 보증할 수 있습니다.
   - 인증서의 위임 키에 대해 블롭의 서명을 검증합니다.
   - 인증서의 제약(구독 일치, 플랜 일치, 크기 상한 `maxRepositorySizeGb`, `blob.sequence <= cert.maxTotalIssuances`)을 강제합니다.
   - 모든 표준 체인 확인을 적용합니다.

인증서 검증 실패는 전용 사유로 즉시 실패 처리됩니다: `cert_expired`(유효 기간 밖) 또는 `cert_invalid`(마스터 키 서명 오류 또는 제약 위반)입니다. 이들은 `invalid_signature`보다 **먼저** 확인되므로 인증서 사유가 우선합니다.

온프레미스 서버는 다음을 할 수 없습니다.
- 위임 인증서의 플랜 제한 외의 라이선스 위조(renet이 거부).
- `maxTotalIssuances` 이상의 총 작업 발급(renet이 시퀀스 오버플로 거부).
- 인증서의 `validUntil`이 지난 뒤에도 실행 가능한 라이선스에 계속 서명(만료 확인이 생략되는 작업에서도 이 기간은 강제됩니다).
- 인증서 수정(업스트림 서명이 깨짐).

## 유효성 정책

위임 인증서의 유효 기간은 업스트림 백엔드와 고객 포털 프론트엔드 모두에서 실행되는 공유 정책 헬퍼(`computeDelegationCertValidity()`)에 의해 계산됩니다. 동일한 입력은 항상 동일한 `validUntil`을 생성하므로 고객은 제출 전에 생성 모달에서 유효 기간을 미리 볼 수 있습니다.

### 플랜별 기본값 및 상한

| 플랜 | 기본 유효 기간 | 플랜 상한 |
|---|---|---|
| COMMUNITY | 15일 | 30일 |
| PROFESSIONAL | 60일 | 120일 |
| BUSINESS | 90일 | 180일 |
| ENTERPRISE | 120일 | 365일 |

기본값은 호출자가 `validDays`를 생략했을 때 생성 엔드포인트가 선택하는 값입니다. 상한은 호출자가 요청할 수 있는 최대값입니다.

### 구독별 재정의

관리자는 관리자 구독 상세 페이지를 통해 특정 구독에 사용자 정의 `delegationCertDefaultDays` 값을 설정할 수 있습니다. **재정의는 해당 구독의 기본값과 상한 모두를 대체합니다.** 이는 특별한 고객을 위한 탈출구입니다(예: COMMUNITY 플랜에서 200일 인증서가 필요한 엔터프라이즈 계약). Zod 스키마는 여전히 절대 범위 `1..365`를 적용합니다.

### 하드 캡: 구독 종료 + 3일 유예

플랜 상한 및 재정의와 무관하게 모든 인증서는 `subscription.expiresAt + 3일`(기존 `SUBSCRIPTION_CONFIG.gracePeriodDays`)로 하드 캡이 설정됩니다. 이는 다음을 의미합니다.

- 영구 구독(`expiresAt = null`)의 경우 만료 캡이 적용되지 않으며 플랜 상한만 적용됩니다.
- Stripe 청구 월간 구독의 경우 캡은 대략 다음 결제일 + 3일입니다. Stripe가 매달 `expiresAt`을 앞으로 이동하면 캡도 함께 이동합니다.
- 평가판 구독의 경우 캡은 평가판 종료일 + 3일입니다.

### 유효 일수 및 이유

모든 생성/갱신 응답에는 `effectiveDays`와 `reason`이 포함되어 호출자가 인증서가 해당 유효성을 갖게 된 이유를 정확히 파악할 수 있습니다.

| 이유 | 의미 |
|---|---|
| `plan_default` | 요청 없음, 재정의 없음 - 플랜별 기본값 사용 |
| `subscription_override` | 요청 없음 - 구독별 재정의를 기본값으로 사용 |
| `requested` | 모든 캡 범위 내에서 호출자 요청 수락 |
| `plan_max_clamp` | 호출자 요청이 플랜별 상한 초과 - 하향 조정 |
| `override_max_clamp` | 호출자 요청이 구독별 재정의 초과 - 하향 조정 |
| `subscription_cap_clamp` | 유효한 목표가 구독의 `expiresAt + 3일`을 초과하는 경우 |

고객 포털 생성 모달은 이러한 이유를 사용하여 실시간 미리보기를 렌더링합니다("18일 인증서를 받게 됩니다. 인증서가 구독 종료일보다 3일 이상 초과할 수 없으므로 하향 조정되었습니다."). 고객이 내용을 확인하지 않고 제출하지 않도록 합니다.

### 적응형 갱신 임계값

온프레미스 자동 갱신 루프는 Let's Encrypt를 모델로 한 적응형 임계값을 사용합니다.

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

15일 COMMUNITY 인증서는 5일 남았을 때 갱신됩니다. 90일 BUSINESS 인증서는 14일 남았을 때 갱신됩니다(환경 설정 상한 적용). 120일 ENTERPRISE 인증서는 14일 남았을 때 갱신됩니다. 이는 단기 인증서가 즉시 갱신을 트리거하지 않으면서 장기 인증서에 충분한 버퍼를 제공합니다.

## 단일 활성 강제

구독은 한 번에 **최대 하나의 활성 위임 인증서**만 가질 수 있습니다(`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### 하나인 이유

각 온프레미스 설치는 자체 로컬 발급 원장에 대해 `maxRepoLicenseIssuancesPerMonth`, `maxActivations` 및 체인 무결성을 강제합니다. 온프레미스는 사용량 수를 업스트림에 동기화하지 않습니다. 이것이 오프라인 가능한 위임의 핵심입니다.

구독에 여러 활성 인증서(설치당 하나)가 있으면 각 설치가 독립적으로 제한을 강제합니다.

- 3개의 활성 인증서가 있는 월 500회 구독은 실제로 **월 1,500회 발급**을 허용합니다.
- 감사 조정이 불가능한 세 개의 병렬 체인이 각각 genesis에 고정됩니다.

온프레미스는 오프라인으로 작동하도록 설계되어 업스트림이 이 우회를 감지할 수 없습니다. **단일 활성이 유일하게 강제 가능한 모델입니다.** 다중 설치 고객(프로덕션 + 스테이징 + DR)은 설치당 하나의 구독을 구매해야 합니다.

### 충돌 동작

`POST /admin/delegation-certs` 및 `POST /portal/delegation-certs`는 두 번째 생성을 다음과 같이 거부합니다.

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

고객 포털은 결과를 설명하는 전용 대화상자를 표시합니다.

- **갱신(권장)** - 기존 체인을 연장합니다. 이전에 발급된 모든 저장소 라이선스가 계속 작동합니다.
- **취소 후 생성** - 기존 체인을 버리고 genesis에서 새로 시작합니다. 이전에 발급된 저장소 라이선스는 이전 인증서의 `validUntil`이 지나면 검증할 수 없게 됩니다. 다른 서명 키를 사용하는 새 온프레미스로 마이그레이션하거나 손상된 키에서 복구할 때만 사용하십시오.

`renew()`는 단일 활성을 유지하는 원자적 교환이며 409 충돌 확인의 대상이 **아닙니다**.

### 속도 제한

단일 활성이라도 악의적인 호출자가 `취소 -> 생성 -> 취소 -> 생성`을 반복하여 업스트림 마스터 키 서명 사이클을 소모할 수 있습니다. 두 생성 엔드포인트 모두 기존 `rateLimits` 테이블을 통해 구독당 **롤링 24시간당 10회 시도**로 제한합니다.

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

카운터는 결과에 관계없이 모든 시도에서 증가합니다(충돌 스팸 루프도 제한됨).

## 포크 감지

고객이 위임 인증서를 다른 당사자와 공유하거나(또는 동일한 인증서로 두 개의 온프레미스 서버를 실행하면) 체인이 분기됩니다. 업스트림은 갱신 시 이를 감지합니다.

### 갱신 흐름

1. 온프레미스 관리자가 현재 체인 헤드와 함께 `POST /admin/delegation-certs/renew`를 호출합니다.
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. 업스트림이 자체 원장 레코드에 대해 체인 항목을 검토합니다.
3. `currentChainHash`가 `currentSequence`에서 업스트림의 기록된 체인과 일치하지 않으면 포크가 감지됩니다.
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. 새 인증서의 `genesisHash`는 현재 체인 해시로 설정되어 이전 체인 상태의 머신이 중단된 지점에서 계속할 수 있습니다.

인증서가 비고객과 공유된 경우:
- 인증서의 유효 기간 동안 사용할 수 있습니다.
- 첫 번째 갱신 시 업스트림은 하나의 체인(합법적인 것)만 봅니다.
- 새 인증서의 `genesisHash`는 합법적인 체인에만 일치합니다.
- 공유된 체인의 머신은 저장된 `chainHash`가 새 인증서의 `genesisHash`에 연결되지 않으므로 즉시 새 라이선스를 거부합니다.

## 에어갭 갱신

업스트림으로의 아웃바운드 HTTPS 접근이 없는 온프레미스 설치의 경우 갱신 흐름이 완전히 오프라인입니다. 루프를 닫는 세 가지 새 엔드포인트가 있습니다.

**온프레미스(`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - 현재 로드된 서명 인증서 다운로드(백업, 감사, 재가져오기)
- `GET /onprem/renewal-request` - 온프레미스 개인 키로 서명된 로컬 체인 헤드 + 위임 공개 키를 포함하는 서명된 매니페스트 생성

**업스트림(관리자 또는 조직 범위 포털):**
- `POST /admin/delegation-certs/process-renewal-request`(교차 고객 시스템 루트)
- `POST /portal/delegation-certs/process-renewal-request`(조직 소유자/관리자)

### 갱신 요청 매니페스트

갱신 요청은 소형 JSON 문서입니다.

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

서명은 온프레미스 개인 키를 사용하여 매니페스트의 정규 인코딩(키를 알파벳순으로 정렬한 후 `JSON.stringify`)에 대해 계산됩니다. 이는 객체 구성 순서에 관계없이 양측이 동일한 바이트를 계산하도록 보장합니다.

### 업스트림에서의 검증

`processRenewalManifest()`는 다섯 가지 확인을 실행합니다.

1. **활성 인증서 존재** - 매니페스트의 구독에 대해. 그렇지 않으면 `404 NO_ACTIVE_CERT` 반환 - 고객은 갱신이 아닌 생성 흐름을 사용해야 합니다.
2. **위임 공개 키 일치** - 활성 인증서에 대해. 그렇지 않으면 `400 DELEGATED_KEY_MISMATCH` 반환 - 다른 온프레미스의 재전송을 방지합니다.
3. **매니페스트 서명 검증** - 활성 인증서의 `delegatedPublicKey`에 대해. 그렇지 않으면 `400 MANIFEST_SIGNATURE_INVALID` 반환 - 매니페스트가 온프레미스 개인 키 보유자로부터 왔음을 증명합니다.
4. **매니페스트 수명** - 7일 이내(`RENEWAL_MANIFEST_MAX_AGE_MS`). 그렇지 않으면 `400 MANIFEST_EXPIRED` 반환 - 재전송 방지 앵커.
5. **체인 해시 연결** - 매니페스트의 `currentSequence`에서 업스트림 원장과 일치. 그렇지 않으면 `409 CHAIN_FORK_DETECTED` 반환 - 포크된 체인을 방지합니다.

모든 확인이 통과하면 `processRenewalManifest`가 기존 `renew()` 흐름을 호출하여 이전 인증서를 원자적으로 만료시키고 새 인증서를 삽입합니다. 이는 2단계 취소+생성이 아닌 원자적 교환이므로 **생성 측 단일 활성 409의 대상이 아닙니다**.

### 전송 중 시퀀스 진행

갱신 요청 매니페스트는 생성 시점의 체인 헤드를 캡처합니다. 매니페스트가 전송 중인 동안(USB 전달, 암호화된 이메일) 온프레미스는 저장소 라이선스를 계속 발급하여 로컬 체인을 진행할 수 있습니다.

새 인증서가 온프레미스에 다시 업로드되면 `/onprem/cert-upload`가 새 인증서의 `genesisSequence`가 여전히 로컬 발급 원장의 알려진 항목과 연결되는지 검증합니다.

- `cert.genesisSequence > localHead.sequence`인 경우 - `409 CHAIN_HEAD_BEHIND` 반환(업스트림이 포크된 체인에 있음).
- `cert.genesisSequence > 0`이고 해당 시퀀스의 로컬 원장 항목의 `chainHash`가 `cert.genesisHash`와 다른 경우 - `409 CHAIN_FORK_ON_UPLOAD` 반환(로컬 체인이 분기됨).
- 그렇지 않으면 인증서가 수락됩니다. 향후 발급은 `localHead.sequence + 1`에서 계속됩니다.

이는 **전송 중 쓰기 동결이 필요하지 않음**을 의미합니다. 체인은 양측에서 자연스럽게 확장됩니다. X.509 인증서 갱신이 진행 중인 일련 번호를 처리하는 방식과 동일합니다.

## 주기적 감사

업스트림은 인증서를 갱신하지 않고 체인 무결성을 검증하는 감사 엔드포인트를 제공합니다.

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

업스트림이 항목을 검토하고 `{ valid: true }` 또는 `{ valid: false, divergedAtSequence: N, expected, actual }`를 반환합니다.

온프레미스 서버는 포크를 조기에 감지하기 위해 이 엔드포인트를 주기적으로 호출해야 합니다(기본값: `UPSTREAM_AUDIT_URL` 환경 변수를 통해 주간).

### 머신 측 감사 증명

Renet은 `VerifyAuditProof`를 사용하여 체인 연속성을 로컬에서 검증할 수 있습니다. 머신이 긴 간격 후 라이선스를 갱신할 때 서버는 중간 체인 항목을 증명으로 반환할 수 있습니다. 머신은 증명을 검토하여 각 `chainHash`가 SHA-256을 통해 이전 `prevHash + blobHash`에서 파생되는지 확인하여 업스트림에 연락하지 않고도 변조를 감지합니다.

## 동시성 안전

D1(Cloudflare의 데이터베이스)은 대화형 트랜잭션을 지원하지 않습니다. 동일한 구독에 대한 동시 라이선스 발급이 시퀀스 번호에서 충돌할 수 있습니다. 계정 서버는 이를 다음과 같이 처리합니다.

1. 다음 시퀀스 + 이전 체인 해시 읽기.
2. 해당 시퀀스가 내장된 블롭 빌드 및 서명.
3. `onConflictDoNothing`으로 원장 항목 삽입.
4. 삽입이 0행을 반환하면 시퀀스가 다른 요청에 의해 요청됨 -- 시퀀스를 재획득하고, 재빌드하고, **재서명**하고 재시도.
5. 10번의 실패 후 오류로 종료.

중요한 세부 사항: 재시도는 블롭을 **재서명**합니다. 원장 항목만 업데이트하는 순진한 재시도는 서명된 블롭에 오래된 시퀀스 번호가 남아 체인이 깨질 수 있습니다.

## 이메일 전송

계정 서버는 두 가지 플러그형 전송을 통해 트랜잭션 이메일(매직 링크, 비밀번호 재설정, 보안 알림)을 전송할 수 있습니다.

| 전송 | 구성 |
|---|---|
| `ses`(기본값) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

두 전송 모두 클라우드 및 온프레미스 배포에서 작동합니다. 인프라에 맞는 것을 선택하십시오. 자체 AWS 계정의 AWS SES 또는 임의의 SMTP 서버(Microsoft Exchange, Postfix, SendGrid, Mailgun 등).

전송은 `EMAIL_TRANSPORT` 환경 변수를 통해 시작 시 선택됩니다. SMTP는 연결 풀링과 지연 로딩을 사용하므로 SMTP가 선택된 경우에만 SMTP 클라이언트 라이브러리가 초기화됩니다.

모든 이메일 템플릿과 공개 이메일 API는 전송에 관계없이 동일합니다.

## 관련 문서

- [온프레미스 설치](/ko/docs/on-premise) -- 온프레미스 서버 배포 방법
- [구독 및 라이선스](/ko/docs/subscription-licensing) -- 플랜 제한 및 머신 슬롯
- [릴리스 채널](/ko/docs/release-channels) -- edge vs stable 채널
- [데이터 리전](/ko/docs/data-regions) -- 리전별 데이터 거주
