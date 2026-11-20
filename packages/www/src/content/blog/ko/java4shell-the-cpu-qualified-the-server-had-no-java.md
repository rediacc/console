---
title: "Java4Shell: CPU는 조건을 충족했지만 서버에는 Java가 없었고, 템플릿이 버전 고정에 대해 가르쳐 주었습니다"
description: "CVE-2026-114938은 AVX-512 VBMI CPU와 영향받는 JDK가 모두 있어야 발동합니다. 저희 서버에는 CPU는 있었지만 JVM이 하나도 없었습니다. 진짜 작업은 저희가 배포하는 앱 템플릿에 있었습니다. 고정된 태그 하나가 2023년 JDK를 그대로 묶어 두고 있었습니다."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: ko
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **요약.** Java4Shell(CVE-2026-114938)은 OpenJDK의 JIT 컴파일된 Base64 디코더에서 발생하는 힙 범위 밖 쓰기 버그입니다. AVX-512 VBMI를 지원하는 x86-64 CPU에서만 발동합니다.
>
> - 저희 프로덕션 서버의 CPU는 필요한 플래그 **네 개를 모두 갖고 있습니다**. CPU만 확인하면 노출된 것처럼 보였습니다.
> - **컨테이너 43개**, 호스트, 중지된 저장소를 점검했지만 **Java 런타임은 하나도 없었습니다**. 같은 점검으로 `python3`를 찾는 대조 실행에서는 있어야 할 곳마다 전부 나왔습니다. 서버에는 패치할 것이 없었습니다.
> - 저희가 배포하는 앱 템플릿은 사정이 달랐습니다. **네 개**가 JVM을 시작합니다. **세 개**는 유동 태그를 쓰고 있었고, 11월 20일에 패치된 JDK로 업스트림에서 이미 다시 빌드되었습니다.
> - Elasticsearch **하나**는 `8.11.0`으로 고정되어 있었습니다. 2023년 11월에 빌드되어 JDK `21.0.1`이 번들된 이미지입니다. Elastic은 아직 수정 릴리스가 없으므로, 템플릿은 이제 Elastic이 안내하는 완화 플래그로 Elasticsearch를 시작하며, 실행 중인 노드에서 확인했습니다.

## 공개된 취약점

11월 17일에 Calif의 연구자들이 **Java4Shell**을 공개했고, Oracle과 OpenJDK는 같은 날 수정 빌드를 내놓았습니다. 버그는 HotSpot의 하드웨어 가속 Base64 디코더에 있습니다. AVX-512 VBMI 경로가 마지막 몇 글자를 잘못 처리해서 힙 버퍼의 끝 너머에 쓸 수 있습니다. 계정이 없는 원격 공격자가 이를 메모리 손상으로, 조건이 맞는 애플리케이션에서는 코드 실행으로 연결할 수 있습니다. 공개된 분석에는 잘 알려진 여러 Java 서버 제품에 대한 인증 전 공격 체인이 담겨 있습니다.

분류에 중요한 세부 사항은 다음과 같습니다.

- **영향받는 버전:** 수정 빌드 이전의 OpenJDK 17.0.6 이상, 21, 25, 27입니다. 표준 Java 8과 Java 11은 영향이 없습니다.
- **수정 버전:** 17.0.21.1, 21.0.13.1, 25.0.5.1, 27.0.1.1입니다(Temurin 빌드는 `+2`, 27은 `+4`가 붙습니다). `.1` 없이 `17.0.21`이라고 표시하는 런타임은 여전히 취약합니다.
- **전제 조건:** AVX-512 VBMI를 지원하는 x86-64 CPU, 디코더를 이미 컴파일한 JIT, 신뢰할 수 없는 입력에서 Base64를 디코딩하는 앱 경로입니다. ARM은 영향이 없습니다.
- **점수:** CVSS 4.0 기준 9.2점, CVSS 3.1 기준 8.1점입니다. 독립 실행형 개념 증명(PoC)이 공개되어 있습니다. 작성 시점에는 실제 공격이 보고되지 않았습니다.
- **완화책:** JVM을 `-XX:-UseBASE64Intrinsics`로 시작합니다. 공개된 다른 방법인 `-XX:UseAVX=2`도 x86-64에서는 동작하지만, ARM JVM은 시작을 거부합니다.

[지난 패치 작업](/ko/blog/patching-nginx2root-and-php-fork-first)은 앱 네 개를 포크 먼저 롤아웃하는 것으로 끝났습니다. 이번에는 훨씬 이른 단계에서 끝났고, 흥미로운 부분은 그 이유입니다.

## 1단계: CPU가 조건을 충족하는가?

대부분의 CVE에는 소프트웨어 전제 조건이 있습니다. 이 취약점에는 하드웨어 전제 조건도 있고, 확인하기도 쉽습니다.

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

네 개 모두 있었습니다. 이 머신은 AVX-512를 완전히 지원하는 최신 서버 CPU인 AMD EPYC 9354P를 씁니다. 분류를 여기서 멈췄다면 답은 "노출됨, 오늘 밤 Java를 전부 패치"였을 것입니다.

![세 가지 전제 조건: CPU는 조건을 충족하지만 JDK 확인에서 막히므로 입력 경로에는 도달하지 못한다](/img/blog-java4shell-preconditions.svg)

## 2단계: 패치할 Java가 있는가?

CPU는 공격 사슬의 한 고리일 뿐입니다. 두 번째 고리는 영향받는 JDK이므로, 다음 질문은 단순했습니다. 어떤 컨테이너가 Java를 실행하는가?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

머신의 모든 저장소에 대해 `rdc term connect <repo>@hostinger`로 이를 실행했습니다. `libjvm.so`를 찾는 `find`는 앱 폴더 안에 번들되어 `PATH`에 없는 JVM을 잡아냅니다. 예를 들어 Elasticsearch가 JDK를 이런 식으로 포함합니다.

결과는 비어 있었습니다. 실행 중인 컨테이너 43개 어디에도 `java`와 `libjvm.so`가 없었습니다.

점검이 무언가를 찾을 수 있다는 사실을 보이기 전에는, 빈 결과가 아무것도 증명하지 못합니다. 그래서 같은 반복문을 이번에는 `python3`를 찾도록 다시 실행했습니다. ERPNext 컨테이너에 있다는 것을 아는 런타임입니다. 모든 ERPNext 컨테이너에서 Python 3.14가 나왔습니다. 점검은 제대로 동작하고, 서버에 Java가 없는 것입니다.

질문을 닫기 전에 두 곳을 더 확인했습니다. 호스트 자체에도 Java와 `/usr/lib/jvm`이 없었습니다. 실행 중인 것이 없는 저장소들의 Docker 데몬에도 Java 이미지가 없었습니다. 그중 한 곳에는 저희 모노레포의 체크아웃이 있었고, 그 compose 파일에 `cassandra:5.0`과 `elasticsearch:8.11.0`이 언급되어 있었습니다. 이것이 다음 단계로 이어졌습니다.

## 3단계: 저희가 배포하는 템플릿

Rediacc는 앱마다 `docker-compose.yaml`과 Rediaccfile로 이루어진 즉시 쓸 수 있는 앱 템플릿을 배포합니다. 저희가 운영하지 않는 서버에서도 이를 배포할 수 있습니다. 따라서 템플릿에 Java 이미지가 있으면, 저희 서버가 깨끗하더라도 해당 CPU를 가진 모든 고객이 노출됩니다.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

템플릿 네 개가 JVM을 시작합니다. 그중 두 개는 레지스트리의 이미지 config에 JDK가 이미 적혀 있습니다. 나머지 두 개는 그렇지 않아서, 각 이미지를 한 번씩 실행해 물어봤습니다.

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| 템플릿 | 템플릿의 태그 | 현재 내부 JDK | 상태 |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | 업스트림에서 수정, 11월 20일 재빌드 |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | 업스트림에서 수정, 11월 20일 재빌드 |
| Solr | `solr:9-slim` | 17.0.21.1+2 | 업스트림에서 수정, 11월 20일 재빌드 |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (번들) | **취약**, Elastic 수정 릴리스 아직 없음 |

![고정과 유동 비교: 고정된 Elasticsearch 이미지는 2023년 JDK를 그대로 유지했고, 유동 태그는 수정본으로 다시 빌드되었다](/img/blog-java4shell-pinned-vs-floating.svg)

## 버전 고정에 대한 교훈, 수정판

지난 글은 "정확한 태그로 고정한다"로 끝났습니다. 이번 작업은 그 규칙에 각주를 하나 덧붙입니다.

고정은 저희가 의도를 갖고 운영하고 업그레이드하는 앱에는 맞습니다. 고정하면 실행 중인 버전이 드러납니다. 유동 태그는 수정본을 가리키는데도 서버가 옛 이미지를 계속 실행할 수 있습니다. `docker compose up -d`는 이미 가진 이미지를 pull하지 않기 때문입니다.

사람들이 새로 배포하는 템플릿에서는 상황이 뒤집힙니다. 유동 메이저 태그 세 개(`5.0`, `5-community`, `9-slim`)는 저희가 아무것도 바꾸지 않았는데도 수정 사흘 뒤에 패치된 JDK를 받았습니다. 정확히 고정한 `8.11.0` 하나는 Elasticsearch를 2023년 11월에 빌드된 이미지에 묶어 두었고, 그 태그를 다시 빌드하더라도 JDK는 고쳐지지 않습니다.

그래서 저희가 지키는 규칙은 두 부분입니다. 프로덕션 앱은 정확한 태그와 의도적인 업그레이드를 씁니다. 템플릿도 고정을 쓰는데, Elasticsearch와 Kibana는 같은 버전으로 실행되어야 하기 때문입니다. 대신 모든 템플릿의 고정 항목은 이제 핀 레지스트리에 기록되고, 최신성 게이트가 뒤처진 핀을 표시하므로 3년씩 방치되지 않습니다.

## 4단계: 완화책, 실제 노드에서 검증

Elastic은 수정이 곧 나올 8.19.26, 9.4.10, 9.5.7, 9.6.0 릴리스에 번들 JDK 업데이트로 포함된다고 발표했습니다. 그중 하나가 나오기 전까지 공식 안내는 JVM 플래그입니다. 템플릿에서는 `ES_JAVA_OPTS`에 단어 하나를 더하는 것입니다.

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![플래그가 바꾸는 것: JIT가 AVX-512 인트린식 대신 일반 Java 디코더를 유지한다](/img/blog-java4shell-intrinsic-flag.svg)

compose 파일의 플래그는 JVM이 확인해 주기 전에는 주장에 불과합니다. 두 번 확인했습니다. 먼저 번들된 JDK 자체를 플래그 유무에 따라 확인했습니다.

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

그다음 템플릿의 옵션으로 실제 단일 노드 클러스터를 시작했습니다. 상태는 green으로 올라왔고, 노드 자체 API가 JVM 인자 목록에 이 플래그를 보여 주었습니다.

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## 잘못된 부분

**CPU 확인이 하마터면 답을 결정할 뻔했습니다.** 가장 눈에 띄는 전제 조건이고, 명령 한 줄이면 되고, 결과는 "노출됨"이었습니다. 실제 JVM을 찾는 두 번째 확인이 있었기 때문에 한밤의 비상이 템플릿 수정 하나로 바뀌었습니다.

**테스트 스위트가 돌아서는 안 되는 곳에서 돌았습니다.** 템플릿 수정을 확인하려고 템플릿 패키지의 라이프사이클 스위트를 워크스테이션에서 실행했습니다. 이 스위트는 단순한 Docker 호스트가 아니라 라이선스가 있는 Rediacc 저장소를 위한 것이라, 다른 템플릿을 시작하느라 10분 넘게 걸렸습니다. 또한 관련 없는 템플릿 하나가 생성한 시크릿을 자기 소스 폴더에 쓴다는 점도 드러났습니다. 커밋에 들어가면 안 되는 파일입니다. 이제 그 템플릿은 시크릿을 소스 트리 밖에 쓰고, 스위트는 필요한 저장소가 없으면 시작을 거부합니다.

**포크할 대상이 없었습니다.** 변경 전에 프로덕션 저장소를 포크하는 평소의 안전 단계는 이번에는 대상이 없었습니다. 변경은 git에 있는 템플릿 파일에 있었으므로, 안전망은 스냅샷이 아니라 검토할 수 있는 커밋과 실제 부팅 테스트였습니다.

## 선택과 그 이유

| 가능했던 선택지 | 저희의 선택 | 이유 |
|---|---|---|
| CPU 확인을 답으로 취급 | 실제 JVM을 점검 | CPU는 노출됨이라고 했지만, JVM이 없으면 악용할 것이 없습니다. |
| 빈 점검 결과를 신뢰 | 반드시 무언가를 찾아야 하는 대조 실행 | 고장 난 점검의 빈 결과는 깨끗한 서버와 똑같아 보입니다. |
| 레지스트리에서 JDK 버전 읽기 | 각 이미지를 한 번씩 실행 | 이미지 네 개 중 두 개는 config에 JDK 버전이 기록되어 있지 않습니다. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | 범위가 더 좁습니다. 모든 AVX-512 가속이 아니라 루틴 하나만 끄고, ARM JVM도 여전히 시작됩니다. |
| Elasticsearch를 지금 최신 8.19로 올리기 | 8.11.0 유지, 플래그 추가, 수정 릴리스가 나오면 올리기 | 현재 나와 있는 최신 릴리스도 영향받는 JDK를 번들하고 있고, Kibana도 같은 단계에서 함께 올려야 합니다. |
| 모든 곳에 정확한 고정 | 정확한 고정에 모든 템플릿 핀의 최신성 게이트를 더함 | 경보 없는 핀이 2023년 JDK를 묶어 두었습니다. 게이트는 핀을 유지하면서 경보를 추가합니다. |

## 저희가 쓰는 체크리스트

1. 처음 일치하는 조건만이 아니라 모든 전제 조건을 확인합니다.
2. 제품 이름만이 아니라 런타임 자체(`java`, `libjvm.so`)를 찾습니다.
3. 빈 점검 결과는 모두 대조 실행으로 증명합니다.
4. 운영하는 것만이 아니라 배포하는 것도 훑습니다.
5. 이미지 안의 버전을 읽고, config에 없으면 이미지를 실행합니다.
6. 가장 범위가 좁은 완화책을 선호하고, 실행 중인 프로세스에서 확인합니다.
7. 벤더의 수정 릴리스를 추적하고, 나오면 완화책을 제거합니다.

지난 작업과 마찬가지로 `rdc`로 작업하는 AI 에이전트(Claude Code)가 진행했고, 프로덕션 접근 권한은 세션이 시작되기 전에 운영자가 부여했습니다. 이번에는 프로덕션이 전혀 바뀌지 않았습니다. 서버에서 한 모든 단계는 읽기였고, 유일한 수정은 git을 통해 템플릿에 들어갔으며 실제 테스트가 뒷받침했습니다.
