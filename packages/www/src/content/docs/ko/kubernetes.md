---
title: "Kubernetes"
description: "Rediacc의 저장소 사고방식으로 Kubernetes를 운영하세요: 실행 중인 클러스터를 데이터까지 포함해 짧은 컷오버로 다른 머신이나 데이터센터로 포크하거나 이동할 수 있습니다."
category: "Guides"
order: 6
language: ko
sourceHash: "56e1f177e8f4ef41"
---

# Kubernetes

Rediacc는 플랫폼의 나머지 부분이 기반으로 삼는 저장소 사고방식을 포기하지 않고 Kubernetes를 제품에 담아냅니다. 차별화된 주장은 명확합니다. **실행 중인 클러스터를 데이터까지 포함해 짧은 컷오버로 다른 머신이나 데이터센터로 포크하거나 이동할 수 있습니다.** 이는 중지 후 복원하는 방식의 마이그레이션도 아니고, 제로 다운타임의 마법도 아닙니다. 워크로드는 대상 위치에서 재시작되고, 컷오버는 초 단위로 측정되며, 데이터는 함께 이동합니다.

Kubernetes는 인증된 Kubernetes 배포판인 [k3s](https://k3s.io/)로 구동되며, 다른 서버 측 바이너리와 동일한 방식으로 renet에 내장되어 있습니다.

## 객체 모델

Rediacc는 저장소 사고방식이 계속 적용되도록 "클러스터가 모든 것을 감싼다"는 일반적인 그림을 뒤집습니다.

- **클러스터가 컨테이너입니다.** 머신은 Docker 저장소(변경 없음)와/또는 클러스터를 호스팅합니다. 한 머신 위의 단일 노드 클러스터는 클러스터 수준에서도 "파일 하나가 시스템 전체를 옮긴다"는 이야기를 유지합니다. 클러스터 상태(노드별 k3s 데이터 디렉터리: 내장된 데이터스토어와 containerd)는 노드마다 데이터스토어 기반 copy-on-write 이미지 파일에 존재하며, k3s의 `--data-dir`가 이미지 마운트 내부에 바인딩됩니다.
- **Kubernetes 저장소는 네임스페이스입니다.** `rdc repo create --cluster <name>`은 해당 클러스터 내 Kubernetes 네임스페이스 `<repo>`를 실행 거처로 하는 저장소를 생성합니다.
- **퍼시스턴트 볼륨은 별도의 copy-on-write 단위입니다.** PV는 Ceph의 RBD 이미지이거나, 로컬 백엔드에서는 로컬 PV 프로비저너를 통한 작은 데이터스토어 이미지 파일입니다. 하나의 불투명한 클러스터 이미지 내부의 디렉터리가 되는 일은 결코 없습니다. 내부 파일시스템에는 reflink가 없으므로, 독립적인 저장소 포크에는 독립적인 PV 이미지가 필요합니다.

이 분리 덕분에 두 가지 약속이 동시에 물리적으로 가능해집니다. **항상 copy-on-write인 네임스페이스 포크**(각 저장소의 데이터가 독립적으로 복제됨)와 **클러스터 전체의 이동성**(클러스터 이미지와 각 PV 이미지가 함께 이동함)입니다.

| 개념 | Docker 저장소 | Kubernetes 저장소 |
|---|---|---|
| 실행 거처 | 격리된 Docker 데몬 | 클러스터 내 네임스페이스 |
| 주입되는 환경 변수 | `DOCKER_HOST` | `KUBECONFIG` |
| 배포 래퍼 | `renet compose` | `renet kube` |
| 데이터 단위 | LUKS 이미지 하나 | 클러스터 이미지 + PV별 이미지 |
| 포크 단위 | 저장소 이미지 | 네임스페이스 + 그 PV 클론 |
| 전체 위치 복제 | (저장소가 곧 위치) | `rdc cluster fork` / `rdc cluster migrate` |

## 클러스터 선언과 생성

클러스터는 프라이빗 네트워크상의 이름이 있는 노드 풀 집합입니다. 먼저 설정에서 선언한 다음 프로비저닝하십시오.

```bash
# 풀을 가진 클러스터를 선언합니다 (아직 아무것도 프로비저닝되지 않음)
rdc config cluster add --name prod \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# 풀 멤버를 프로비저닝하고, 각 멤버에 renet을 부트스트랩하고, 구성 요소(ceph 먼저)를 설치합니다
rdc cluster create --name prod
```

풀 역할은 `ceph`, `k8s-server`, `k8s-agent`, `hyperconverged`입니다(Ceph의 메모리 목표와 kubelet의 축출 임계값이 RAM을 두고 경쟁하므로 명시적인 opt-in입니다). 각 풀은 풀별 크기와 디스크 파라미터로 하드웨어 비대칭성을 담습니다. 디스크 중심의 Ceph 노드, CPU/RAM 중심의 Kubernetes 노드입니다.

풀 멤버는 백레퍼런스와 함께 `<cluster>-<pool>-<n>`으로 `resources.machines`에 구체화되므로, **기존의 모든 `-m` 명령이 그대로 작동합니다**. `rdc machine query`, `rdc term connect`, repo 명령, 백업 전략 모두 클러스터 노드를 일반 머신으로 취급합니다.

클라우드 공급자는 `rdc machine provision`이 사용하는 것과 동일한 `ProviderMapping` 레지스트리를 따르며, 프라이빗 네트워크 블록(VLAN 또는 VPC, 적용할 MTU, 프라이빗 NIC 명명)으로 확장되어 [OpenTofu](https://opentofu.org/)를 통해 프로비저닝됩니다. 로컬 KVM은 `rdc ops`를 통해 항상 사용 가능한 테스트 경로입니다.

```bash
# 클러스터를 확인합니다
rdc cluster status                 # 모든 클러스터 나열
rdc cluster status --name prod     # 클러스터 하나의 전체 설정

# 풀을 확장하거나 축소합니다 (머신 추가/제거, 노드 조인/드레인)
rdc cluster scale --name prod --pool k8s --count 5

# 이미 프로비저닝된 멤버에 구성 요소를 설치합니다
rdc cluster install --name prod

# 프로비저닝된 멤버를 폐기하고 설정에서 클러스터를 제거합니다
rdc cluster destroy --name prod
```

### kubeconfig 가져오기

kubeconfig는 설정 파일에 저장되지 않습니다(크기가 크고 회전하기 때문입니다). SSH를 통해 요청 시점에 가져와, OpenTofu의 workdir 및 인증서 캐시와 동일한 부가 상태 패턴에 따라 `0600` 권한으로 로컬에 캐시됩니다.

```bash
rdc cluster kubeconfig --name prod
# 출력: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetes 저장소

대상 플래그가 런타임을 결정합니다. 타입 플래그는 없습니다.

```bash
# Docker 저장소 (변경 없음): 머신 위의 격리된 Docker 데몬
rdc repo create --name shop -m server-1 --size 10G

# Kubernetes 저장소: 클러스터 안의 네임스페이스 "shop" + 그 스토리지
rdc repo create --name shop --cluster prod --size 10G
```

repo 동사들은 저장소 단위 작업을 위한 단일한 표면입니다. 대상 해석 깔때기를 통해, repo 명령 집합 거의 전체가 클러스터를 다룰 수 있게 됩니다. `fork`, `migrate`, `push`, `pull`, `up`, `down`, `resize`, `diff`, `commit`, `branch`, `checkout`, `merge`, `trim`, `cat`, `mount`, `sync`, `list`, `status`, `log` 모두 `--cluster`를 받습니다. 클러스터 대상은 그 컨트롤 노드와, 저장소의 네임스페이스에 고정된 KUBECONFIG 컨텍스트로 해석됩니다. 이는 머신이 `DOCKER_HOST`와 작업 디렉터리로 해석되는 것과 같은 방식입니다.

```bash
rdc repo sync upload --cluster prod -r shop --local ./config
rdc cluster kubeconfig --name prod           # KUBECONFIG를 export한 뒤 kubectl을 직접 사용
```

클러스터 노드도 `resources.machines`에 구체화되므로, 일반적인 `rdc term connect -m <cluster>-<pool>-<n>`으로 특정 노드에 SSH 접속할 수 있습니다.

### 이중 런타임 Rediaccfile

Docker와 Kubernetes 사이의 이동성은 자동 매니페스트 변환이 아니라 관례에 기반합니다. 동일한 `up()`과 `down()` 함수 아래에 `renet compose` 경로와 `renet kube` 경로를 모두 제공하는 저장소는 데이터 디렉터리 관례가 동일하므로 양방향으로 자유롭게 마이그레이션됩니다. renet은 머신 대상에는 `DOCKER_HOST`를, 클러스터 대상에는 `KUBECONFIG`를 주입합니다. `up()`은 둘 중 어느 것이 설정되어 있는지 읽어 그에 따라 분기합니다.

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetes 런타임
  else
    renet compose -- up -d             # Docker 런타임
  fi
}
```

대상 런타임을 선언하지 않은 저장소는 데이터 전송 단계 **이후에** 명확한 거부를 받습니다. 이미지는 이동하지만, 배포 단계에서 상태를 손상시키는 대신 그 저장소가 Kubernetes(또는 Docker) 경로를 선언하지 않았다는 것을 알려줍니다.

## 저장소 포크

Kubernetes 저장소에 대한 `rdc repo fork`는 항상 데이터를 복사하며, 항상 즉시 실행됩니다. `--full` 플래그도, 변형도 없습니다.

```bash
rdc repo fork --parent shop --tag joseph --cluster prod
```

이렇게 하면 동일한 클러스터 안에 네임스페이스 `shop-joseph`가 생성되고, 모든 볼륨이 copy-on-write로 복제되며(Ceph에서는 RBD 클론, 로컬 백엔드에서는 PV 이미지 파일의 reflink), 그곳에 워크로드가 배포됩니다. 포크의 URL은 부모의 와일드카드 인증서 아래에서 즉시 활성화되므로 새 인증서나 DNS 레코드가 발급되지 않습니다.

대상 확장:

- `--to-cluster <name>`은 다른 기존 클러스터로 포크합니다. 동일한 Ceph 백엔드인 경우: RBD 클론은 copy-on-write를 유지합니다. 백엔드가 다른 경우: push 메커니즘이 이미지를 이동시킵니다.
- `--provider <p>`는 먼저 새 클러스터를 프로비저닝합니다. 풀 사양은 기본적으로 소스 클러스터의 형태를 반영합니다(플래그로 재정의 가능).

KVM 테스트 랩에서 측정한 결과, 네임스페이스 포크는 부모 워크로드에 영향을 주지 않으면서 약 1~5초 만에 완료되며, 두 네임스페이스는 독립적으로 분기해 나갑니다.

## 클러스터 전체 포크 또는 이동

클러스터 전체를 다루는 작업은 `rdc cluster` 그룹에 있습니다. 이들은 서로 다른 객체(모든 저장소를 포함한 전체 위치)에 작용하며, 저장소 이름 하나를 받는 명령으로는 표현할 수 없기 때문입니다. 이것이 플래그십 이야기입니다.

```bash
# 클러스터 전체를 그 저장소들의 데이터까지 포함해 새 클러스터로 복제합니다
rdc cluster fork --name prod --tag staging

# 클러스터 전체를 그 저장소들의 데이터까지 포함해 다른 머신이나 데이터센터로 이동합니다
rdc cluster migrate --name prod --to server-2
```

두 명령 모두 클러스터 이미지와 각 저장소의 PV 이미지에 대한 copy-on-write를 조율한 뒤, 노드 identity를 다시 써서 클론되거나 재배치된 클러스터가 새 주소에서 정상적으로 기동하도록 합니다. k3s는 컨트롤 플레인 상태를 내장 데이터스토어에 저장하므로 클러스터 이미지 자체가 스냅샷이 됩니다. 일관성 순서는 컨트롤 플레인 먼저, 그다음 PV, 그다음 에이전트입니다.

KVM 테스트 랩에서 엔드투엔드로 측정한 정직한 수치입니다.

| 작업 | 하는 일 | 측정값 |
|---|---|---|
| 네임스페이스 포크 | 저장소 하나의 네임스페이스와 PV를 제자리에서 복제 | 약 1~5초 |
| 단일 이미지 RBD 포크 | Ceph 기반 PV 클론 하나의 copy-on-write | 약 5초 |
| 2노드 클러스터 전체 포크 | 드레인 후 컨트롤 플레인과 에이전트를 reflink, identity를 새 IP로 재작성, 부모는 그대로 유지 | 약 46초 |
| 크로스 머신 클러스터 마이그레이션 | 핫 프리카피 후 정지-재시작 컷오버 | 컷오버 약 16초 |

기본 일관성은 **크래시 컨시스턴트하며 참조 무결성이 유지되는** 방식입니다. 이는 전원을 껐다 켰을 때와 동일한 시맨틱이며, 워크로드 입장에서도 그렇게 보입니다. 복사 중에 워크로드의 파일시스템을 프리즈하면 애플리케이션 컨시스턴트 스냅샷도 사용할 수 있습니다. 이는 의도적으로 제로 다운타임으로 제시하지 않습니다. "실행 중인 클러스터를 데이터까지 포함해 포크한다"는 기능 자체를 제공하는 다른 회사는 없습니다. 정직한 프레이밍은 마케팅상의 절대치가 아니라, 짧고 측정된 컷오버입니다.

## 스토리지: ceph-csi와 퍼시스턴트 볼륨

Ceph는 어떤 Kubernetes 클러스터의 **바깥에서**, `ceph` 풀 위에서 renet의 cephadm 플로우로 프로비저닝되며, 클러스터는 renet이 템플릿화한 ceph-csi 매니페스트를 통해 이를 사용합니다. 각 클러스터 인스턴스(그리고 각 포크)는 테넌트별 격리의 기본 단위인 자신만의 RBD/RADOS 네임스페이스를 얻습니다. 스토리지는 모든 클러스터 아래에 위치하므로 일반 Docker 저장소와 데이터스토어 백엔드도 함께 지원하며, 클러스터 포크는 자신의 스토리지 백엔드를 포크하는 대신 Kubernetes 아래에서 RBD 이미지를 복제합니다.

로컬 백엔드(Ceph 없음)에서는 renet의 로컬 PV 프로비저너가 각 PV를 데이터스토어 내 작은 copy-on-write 이미지 파일로 뒷받침하며, 포크 시 reflink로 복제됩니다. 디스크상의 레이아웃과 renet 명령은 [서버 레퍼런스](/ko/docs/server-reference)를 참조하세요.

## 배포판 선택

배포판은 install, join, kubeconfig, healthcheck, upgrade 등 작지만 실질적인 인터페이스를 가진 추상화입니다.

- **k3s**는 기본값이며 유일하게 내장된 배포판입니다. Apache-2.0 라이선스이고 CNCF 인증을 받은 단일 재배치 가능 바이너리이며, 내장된 Traefik과 ServiceLB는 모두 Rediacc 프록시를 위해 비활성화되어 있습니다. `--data-dir`는 시작 시점에 바인딩되는데, 이는 이미지 마운트 경로가 바뀔 때 클러스터 포크와 마이그레이션에 정확히 필요한 특성입니다. k3s는 `repoEmbeddable`로 플래그가 지정되어 있습니다.
- **external**은 사용자가 직접 kubeconfig를 가져오는 방식입니다. `getKubeconfig`와 `healthcheck`만 실질적인 작업을 수행하며, 생명주기 관련 동사들은 오류 대신 일급 "해당 없음" 결과를 반환합니다.
- **RKE2**는 FIPS/CIS 고객을 위해 계획된 세 번째 백엔드이며, 이번 릴리스에는 포함되지 않습니다.

클러스터 포크와 마이그레이션은 `repoEmbeddable`이 아닌 배포판에서는 상태를 손상시키는 대신 명확한 오류로 실행을 거부합니다. 클러스터 상태를 데이터스토어 이미지에 내장하려면 시작 시점에 바인딩되는 data-dir가 필요하기 때문입니다.

## 레지스트리

서로 다른 두 가지 이미지 문제에 두 가지 도구로 대응합니다.

- **업스트림 문제**(Docker Hub 속도 제한, 거부되는 pull, 오프라인): 내장된 [zot](https://zotregistry.dev/) pull-through 캐시가 컨트롤 풀에서 실행되며, 여러 업스트림(docker.io, ghcr.io, quay.io)에 대해 `sync.onDemand`를 수행합니다. 다른 바이너리와 동일한 방식으로 renet에 내장되어 있으며, ops의 테스트 레지스트리를 대체하므로 모든 실행이 이를 실제로 사용하게 됩니다.
- **클러스터 내 배포**: k3s의 내장 레지스트리 미러를 통해 노드들이 이미 가져온 이미지를 피어 투 피어로 공유할 수 있습니다.

배선은 containerd의 `certs.d/hosts.toml`과 k3s의 `registries.yaml`을 통해 투명하고 재시작 없이 이루어집니다. 클러스터 이미지 내부의 저장소별 containerd 저장소는 포크와 마이그레이션이 사용하는 진실의 원천으로 남으며, 레지스트리는 인터넷 앞의 캐시일 뿐 결코 상태 자체가 아닙니다.

## 네트워킹과 URL

Kubernetes 저장소 URL은 평면적인 스킴을 따르며, 네임스페이스 아이덴티티가 가장 왼쪽 레이블에 접히고 클러스터가 두 번째 안정적인 레이블이 됩니다.

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetes 저장소 (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    포크 (namespace = repo-tag)
```

모든 네임스페이스와 모든 포크는 부모의 와일드카드 인증서와 DNS 레코드를 상속하므로, 포크 URL은 즉시 활성화되며 새 인증서는 새 클러스터나 저장소가 생성될 때만 발급됩니다. 라우터는 `rediacc.*` 어노테이션이 붙은 Service를 클러스터에서 폴링하여 Kubernetes 서비스를 발견합니다. 이는 Docker 레이블을 읽는 것의 Kubernetes 버전이라 할 수 있습니다. 라우팅 모델은 [네트워킹](/ko/docs/networking)을, 스토리지 백엔드는 [아키텍처](/ko/docs/architecture)를 참조하세요.

## 저작자 표시

Rediacc는 여러 서드파티 바이너리(k3s, zot, 그리고 renet이 내장하는 다른 것들)를 전달합니다. 언제든 그 버전, SPDX 라이선스 식별자, 소스 아카이브 URL을 출력할 수 있습니다.

```bash
rdc credits
rdc credits --licenses    # 릴리스에 번들된 THIRD_PARTY_LICENSES 전문
```
