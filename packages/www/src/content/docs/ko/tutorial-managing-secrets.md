---
title: "시크릿 관리"
description: "배포 시 자격 증명을 포크가 접근할 수 없는 곳에 저장합니다. 설계상 쓰기 전용."
category: "Tutorials"
subcategory: advanced
order: 8
language: ko
sourceHash: "0b4d72c80b489e12"
---

# 시크릿 관리

실제 앱에는 실제 자격 증명이 필요합니다: Stripe 라이브 키, 데이터베이스 비밀번호, API 토큰. 저장소에 넣는 것은 잘못된 방법입니다. 포크가 암호화된 이미지 내의 모든 것을 상속하기 때문에, 갑자기 샌드박스가 실제 고객 카드에 청구하게 됩니다.

올바른 방법은 `rdc repo secret`입니다. 두 가지 전달 모드, 설계상 쓰기 전용, 그리고 포크는 아무것도 없이 시작합니다.

## 튜토리얼 보기

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## 함정: 저장소의 `.env`

![A .env file inside the repo image gets cloned by every fork](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

대부분의 팀은 저장소에 `.env`를 넣습니다. 당연한 선택입니다.

그런 다음 포크합니다.

포크는 부모 이미지의 바이트 단위 복사본입니다. `.env`에 있는 모든 것이 포크의 `.env`에도 있습니다. 포크의 컨테이너가 부팅됩니다. 동일한 Stripe 키를 읽습니다. 프로덕션 자격 증명으로 동일한 Stripe API를 호출합니다. Stripe 입장에서 그 호출은 *당신*입니다.

끔찍한 결과입니다.

## 시크릿 설정

해결책은 `rdc repo secret`입니다. `env` 모드로 설정하면 컨테이너의 환경 변수로 전달됩니다:

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

두 가지를 주목하세요:

- `--mode env`. 값이 환경 변수로 전달됩니다.
- `--current ""`. 빈 문자열. 이전 값이 없는 완전히 새로운 시크릿임을 선언합니다.

민감한 것에 대해 `file` 모드로 또 다른 것을 설정합니다:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file` 모드는 값을 컨테이너의 환경에 넣지 않습니다. 대신 `/run/secrets/stripe_key`에 씁니다. Docker의 표준 메커니즘입니다.

목록을 확인합니다:

```bash
time rdc repo secret list --name my-app
```

이름과 모드가 표시됩니다. **값은 없습니다.** 목록은 절대 값을 표시하지 않습니다.

## compose에 연결하기

`docker-compose.yml`을 엽니다. 두 모드를 모두 참조합니다:

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

`${REDIACC_SECRET_DB_HOST}`는 `env` 모드입니다. `renet`의 compose 래퍼가 배포 시 시크릿 스토어에서 확장합니다.

`secrets:` 블록은 `file` 모드입니다. Docker의 표준 메커니즘입니다. 호스트 경로는 `${REDIACC_NETWORK_ID}`를 사용하므로 동일한 compose가 부모와 포크 모두에서 작동합니다. 각 포크에는 자체 네트워크 ID가 있습니다.

배포합니다:

```bash
time rdc repo up --name my-app -m my-server
```

## 컨테이너에서 확인

두 모드 모두 이제 컨테이너 내부에 있어야 합니다. env 모드 시크릿을 확인합니다:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`이 표시됩니다. env 모드 시크릿이 컨테이너의 환경에 전달되었습니다.

이제 file 모드를 확인합니다:

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`가 표시됩니다. Docker의 표준 시크릿 메커니즘을 통해 파일이 마운트되었습니다.

## 값을 다시 읽을 수 없습니다

![Write-only model: get returns a digest, never the value](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

이제 사람들을 놀라게 하는 부분입니다:

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

다이제스트가 반환됩니다. **값이 아닙니다.** 값을 반환하게 하는 플래그가 없습니다. 어디에도 평문을 돌려주는 명령이 없습니다.

이것이 GitHub Actions 모델입니다: 쓰기 전용. `--current <value>`를 전달하여 전제 조건이 통과되는 것을 확인함으로써 시크릿을 알고 있음을 증명할 수 있습니다. Rediacc에 무엇인지 말해달라고 요청할 수 없습니다.

값을 잃었나요? **들여다보지 마세요. 교체하세요.**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret`는 전제 조건을 건너뜁니다. 감사 로그는 이것을 교체로 표시합니다. 명확하고 의도적입니다.

이전 값을 기억한다면 대신 증명하세요:

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

더 안전한 방법입니다. "잘못된 터미널에 있다"는 실수를 방지합니다.

## 포크의 핵심

![After fork, the secrets list is empty](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

함정을 기억하시나요? 저장소를 포크하고 확인합니다:

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**비어 있습니다.**

포크에는 Stripe 키가 없습니다. 데이터베이스 비밀번호도 없습니다. API 토큰도 없습니다. 포크의 컨테이너는 `${REDIACC_SECRET_STRIPE_KEY}`를 보간할 수 없습니다. `/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` 파일이 존재하지 않습니다.

포크는 당신인 척 할 수 없습니다.

테스트를 위해 포크에 시크릿이 필요하다면 포크에 명시적으로 설정합니다. 샌드박스 값:

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

이제 포크는 Stripe 샌드박스와 통신합니다. 프로덕션 자격 증명은 프로덕션을 떠나지 않았습니다.

## 요약

- `rdc repo secret`은 자격 증명을 저장소 이미지 외부에 저장합니다.
- 포크는 접근할 수 없습니다.
- `get`은 값이 아닌 다이제스트를 반환합니다.
- 잊어버리면 교체하세요. 들여다보지 마세요.

포크가 따라올 수 없는 시크릿.

---

다음: [네트워킹 및 도메인](/ko/docs/tutorial-networking).
