---
title: "컴플라이언스 개요"
description: "Rediacc의 자체 호스팅 아키텍처가 데이터 보호, 개인정보 보호 및 보안 컴플라이언스 요건을 어떻게 충족하는지 설명합니다."
category: "Legal"
order: 0
language: ko
---

Rediacc는 전적으로 귀하의 인프라에서 실행됩니다. 환경 클로닝, 백업 및 배포 작업 중에도 데이터가 귀하의 머신을 벗어나지 않습니다. 귀하는 데이터 컨트롤러이자 처리자로 유지됩니다. 어떠한 제3자 SaaS도 귀하의 데이터를 처리하지 않습니다.

이 섹션은 Rediacc의 기술적 기능을 주요 컴플라이언스 프레임워크의 요건에 매핑합니다. 각 페이지는 공식 법률 문서에 대한 조항 수준 참조와 함께 특정 규정을 다룹니다.

## 컴플라이언스 매트릭스

| 프레임워크 | 적용 범위 | Rediacc 주요 기능 |
|-----------|-------|--------------------------|
| [GDPR](/ko/docs/legal-gdpr) | EU 데이터 보호 및 개인정보 보호 | 동일 머신에서 CoW 클로닝, LUKS2 암호화, 제로 지식 설정 저장소, 감사 로깅, `rdc repo destroy`를 통한 삭제권 |
| [SOC 2](/ko/docs/legal-soc2) | 서비스 조직을 위한 신뢰 서비스 기준 | 저장 시 암호화, 제로 지식 설정 동기화, 네트워크 격리, 감사 추적, 백업 및 복구 |
| [HIPAA](/ko/docs/legal-hipaa) | 미국 의료정보 보호 | LUKS2 암호화, 제로 지식 설정 저장소, SSH 전용 접근, 격리된 Docker 데몬, 전송 보안 |
| [CCPA](/ko/docs/legal-ccpa) | 캘리포니아 소비자 개인정보 권리 | 자체 호스팅(데이터 판매/공유 없음), 제로 지식 암호화, 암호화 삭제, 리포지토리별 데이터 인벤토리 |
| [ISO 27001](/ko/docs/legal-iso27001) | 정보 보안 관리 통제 | 자산 관리, 암호화 통제, 제로 지식 설정 저장소, 접근 제어, 운영 보안 |
| [PCI DSS](/ko/docs/legal-pci-dss) | 결제 카드 데이터 보호 | 아키텍처에 의한 네트워크 분할, 필수 암호화, 감사 로깅, 자체 호스팅을 통한 범위 축소 |
| [NIS2 및 DORA](/ko/docs/legal-nis2-dora) | EU 사이버보안 및 금융 복원력 | 공급망 위험 제거, CoW 클로닝을 통한 복원력 테스트, 암호화, 사고 탐지 |
| [데이터 주권](/ko/docs/legal-data-sovereignty) | 글로벌 데이터 거주지 법률 (PIPL, LGPD, KVKK, PIPA 등) | 자체 호스팅 = 데이터가 귀하의 관할권을 벗어나지 않음. 국경 간 이전 없음, 적정성 평가 불필요 |

## 아키텍처적 기반

이 섹션의 모든 컴플라이언스 프레임워크는 동일한 기술적 속성으로 귀결됩니다.

- **저장 시 암호화**: 모든 리포지토리는 LUKS2 AES-256으로 암호화됩니다. 자격증명은 서버가 아닌 운영자의 로컬 설정에만 저장됩니다.
- **네트워크 격리**: 각 리포지토리는 자체 Docker 데몬, 루프백 IP 서브넷(/26), iptables 규칙을 갖습니다. 서로 다른 리포지토리의 컨테이너는 통신할 수 없습니다.
- **CoW(Copy-on-Write) 클로닝**: `rdc repo fork`는 파일 시스템 리플링크(`cp --reflink=always`)를 사용합니다. 데이터는 네트워크 이전 없이 동일 머신에서 복제됩니다.
- **감사 로깅**: 인증(로그인, 2FA, 비밀번호 변경, 세션 취소), API 토큰 수명 주기, 설정 저장소 작업, 구독/라이선싱 활동 및 CLI 머신 작업(리포지토리 수명 주기, 백업, 동기화, 터미널 세션)을 포함하는 70가지 이상의 이벤트 유형. 관리자 대시보드, 포털 활동 페이지(조직 범위 필터링 포함) 및 `rdc audit` CLI를 통해 접근할 수 있습니다. 머신 작업은 심층 방어를 위해 시스템 로그에도 기록됩니다.
- **암호화 백업**: `rdc repo backup push/pull`이 SSH를 통해 데이터를 이전합니다. 백업 목적지는 LUKS 암호화 볼륨을 수신합니다.
- **제로 지식 설정 저장소**: 기기 간 선택적 암호화 설정 동기화. 설정은 업로드 전 클라이언트 측에서 AES-256-GCM으로 암호화됩니다. 서버는 불투명 블롭만 저장합니다. 서버는 SSH 키, 자격증명, IP 주소 또는 어떠한 평문 설정 데이터도 읽을 수 없습니다. 키 파생은 패스키 PRF 확장 + 도메인 분리를 사용한 HKDF를 사용합니다. 구성원 접근은 X25519 키 교환을 통해 관리되며 취소는 즉각적입니다.

이러한 기능에 대한 자세한 내용은 [아키텍처](/ko/docs/architecture), [리포지토리](/ko/docs/repositories), [설정 저장소](/ko/docs/config-storage) 및 [계정 보안](/ko/docs/account-security)을 참조하십시오.

## 중요성

컴플라이언스 위반은 막대한 비용을 초래합니다. 다음 집행 사례들은 Rediacc의 아키텍처가 구조적으로 방지하는 문제들을 포함합니다.

| 사고 | 제재금 | 문제점 |
|----------|------|----------------|
| [Meta: EU-미국 데이터 이전](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | EUR 12억 | 적절한 보호 조치 없이 국경 간 개인정보 이전. 자체 호스팅은 이전 자체가 없습니다. |
| [Equifax: 비암호화 데이터](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | $7억 | 빈약한 네트워크 분할로 1억 4,700만 건의 기록이 비암호화 상태로 저장됨. LUKS2는 선택 사항이 아닌 필수입니다. |
| [Target: 측면 이동](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | $1,850만 | 공격자가 평면 네트워크를 통해 HVAC 공급업체에서 결제 시스템으로 이동. 리포지토리당 격리가 이를 방지합니다. |
| [Anthem: 비암호화 PHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | $1,600만 | 암호화 없이 7,900만 건의 의료 기록 저장. LUKS2 AES-256은 항상 활성화되어 있습니다. |
| [Blackbaud: SaaS 침해 연쇄](https://www.sec.gov/newsroom/press-releases/2023-48) | $4,950만 | SaaS 공급업체 한 곳의 랜섬웨어로 13,000개 이상의 고객 조직 데이터 노출. 자체 호스팅은 공급업체 침해가 귀하의 데이터에 도달하지 못함을 의미합니다. |
| [British Airways: 빈약한 분할](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | GBP 2,000만 | 부적절한 네트워크 통제로 공격자가 악성 코드 주입. 격리된 Docker 데몬과 iptables가 측면 접근을 방지합니다. |
| [Google: 삭제권](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | EUR 5,000만 | 분산 시스템에서 데이터 완전 삭제 어려움. LUKS destroy를 통한 암호화 삭제는 즉각적이고 완전합니다. |

## 중요 공지

이 페이지들은 컴플라이언스 요건과 관련하여 Rediacc의 기술적 기능을 설명합니다. 어떠한 규정에 대한 컴플라이언스도 단일 도구의 범위를 넘어서는 조직 정책, 절차, 직원 교육 및 잠재적으로 제3자 감사를 필요로 합니다. 귀 기관에 특화된 지침은 법률 및 컴플라이언스 팀에 문의하십시오.
