---
title: "저장소 포크하기"
description: "전체 저장소(앱, 데이터베이스, 파일)를 몇 초 만에 복제합니다. 크기 무관. 추가 디스크 없음."
category: "Tutorials"
subcategory: advanced
order: 7
language: ko
sourceHash: "9237f00dce2ee5ec"
---

# 저장소 포크하기

이것이 핵심 기능입니다: 앱, 데이터베이스, 구성 파일을 포함한 전체 프로덕션 환경을 몇 초 만에 복제합니다. 크기 무관. 추가 디스크 없음. 원하는 만큼 포크할 수 있습니다.

핵심 문구: **프로덕션을 복제하되, 아무것도 망가뜨리지 않습니다.**

## 튜토리얼 보기

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## 잃을 것 만들기

먼저, 포크의 격리를 증명하기 위해 실행 중인 앱에 파일을 추가합니다. VS Code에서 저장소를 엽니다:

```bash
rdc vscode connect -m my-server -r my-app
```

저장소 내부에서 마커 파일을 만듭니다:

```bash
time echo "Hello from production" > index.html
```

이제 포크합니다.

## 포크

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![Parent fans out into independent clones](/img/tutorials/tutorial-forking/slide-1.svg)

하나의 명령으로 앱, 데이터베이스, 구성 파일 모든 것이 복제되었고, 몇 초 만에 완료되었습니다. 다시 실행하면 또 다른 독립적인 복제본이 생성됩니다.

## 왜 이렇게 빠른가요?

![Sharing a folder link is the same speed regardless of the folder's size](/img/tutorials/tutorial-forking/slide-2.svg)

폴더 링크를 공유하는 것을 상상해 보세요. 링크는 폴더가 작든 크든 동일합니다. 폴더는 무겁지만, 링크는 가볍습니다.

![1 GB, 100 GB, 1 TB -- same time, every time](/img/tutorials/tutorial-forking/slide-3.svg)

포크도 마찬가지입니다. 1 GB, 100 GB, 1 TB 언제나 같은 시간.

## 무엇이 공유되고, 무엇이 내 것인가요?

![Many mirrors, one sun -- shared base, your changes are yours](/img/tutorials/tutorial-forking/slide-4.svg)

부모 저장소를 태양이라고 생각하세요. 태양을 손에 쥘 수는 없지만, 태양을 담는 거울을 쥘 수 있습니다. 그 거울이 바로 여러분의 포크입니다. 거울에 그림을 그리면 그 그림은 여러분의 것입니다. 아무리 많은 거울이 태양을 향해 있어도 태양은 변하지 않습니다.

> 태양을 손에 쥘 수 없지만, 거울에 담을 수 있습니다.

## 나중에 부모가 변경되면 어떻게 되나요?

![A fork is a frozen photograph; the parent keeps flowing like a river](/img/tutorials/tutorial-forking/slide-5.svg)

이제 강을 생각해 보세요. 물은 계속 흐릅니다. 매 순간 달라집니다. 포크할 때 그 순간에 얼어붙은 강의 사진을 찍는 것과 같습니다. 강은 계속 흐릅니다. 사진은 그렇지 않습니다.

나중에 부모 저장소가 변경되어도 포크는 그 자리에 있습니다.

> 강을 손에 쥘 수 없지만, 사진에 담을 수 있습니다.

## 디스크 사용량이 증가하지 않습니다

![Five forks of a 100 GB repo -- still about 100 GB](/img/tutorials/tutorial-forking/slide-6.svg)

그래서 디스크가 폭발하지 않습니다. 100 GB 저장소의 포크가 다섯 개? 총 여전히 약 100 GB입니다. 각 포크에서 변경한 내용에 대해서만 디스크 비용을 지불합니다.

> 다섯 번 포크해도 디스크는 알아채지도 못합니다.

## 포크가 *상속하지 않는* 것: 시크릿

포크가 의도적으로 따르지 않는 한 가지가 있습니다: 시크릿입니다. 포크는 API 키, 데이터베이스 비밀번호, Stripe 토큰 없이 시작합니다. 그래서 "프로덕션 복제, 아무것도 망가뜨리지 않음"이 실제로 작동합니다. 샌드박스는 여러분인 척 할 수 없으므로 실제 고객에게 청구할 수 없습니다. [시크릿 관리](/ko/docs/tutorial-managing-secrets) 튜토리얼에서 이것을 제대로 설정합니다.

## 격리 확인

두 저장소를 나란히 나열합니다:

```bash
time rdc repo list -m my-server
```

`my-app`과 `my-app:experiment`가 동시에 실행되고 있음을 볼 수 있습니다.

원본 저장소에서 실행 중인 것을 확인합니다:

```bash
time docker ps
```

가동 시간을 확인하세요. 이것들이 원본 컨테이너입니다. 이제 포크로 전환합니다:

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

동일한 이미지이지만 가동 시간이 새롭습니다. 포크가 시작될 때 이것들이 시작되었습니다.

차이를 더 명확하게 확인합니다. 포크에만 컨테이너를 추가합니다:

```bash
time docker run --rm -it -d nginx
time docker ps
```

Nginx가 실행 중이지만, 이 포크 내에서만입니다.

파괴적인 작업을 시도합니다:

```bash
time rm index.html
```

여기서는 삭제되었습니다. 이제 원본으로 돌아갑니다:

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

nginx가 없습니다. 포크의 컨테이너는 포크에 남아 있었습니다. 그리고 `index.html`은 여기에 그대로 있습니다. 원본은 아무것도 모릅니다. 동일한 이미지, 별도의 Docker 데몬, 별도의 파일 시스템.

## 정리

완료되면 포크를 삭제하기만 하면 됩니다:

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

원본은 그대로 유지됩니다. **포크하고, 실험하고, 망가뜨리고, 삭제하세요.** 위험 없음.

---

다음: [시크릿 관리](/ko/docs/tutorial-managing-secrets).
