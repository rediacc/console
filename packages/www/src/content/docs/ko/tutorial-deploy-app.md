---
title: "첫 번째 앱 배포하기"
description: "renet dev up을 사용하여 내장 템플릿에서 컨테이너화된 앱을 배포합니다."
category: "Tutorials"
subcategory: essentials
order: 5
language: ko
sourceHash: "f75b5b6a716e94bf"
---

# 첫 번째 앱 배포하기

빈 저장소가 있습니다. `rdc`에는 `docker-compose`를 처음부터 작성하지 않고도 실제 앱을 실행할 수 있는 내장 템플릿이 있습니다. 세 가지 단계: 템플릿 선택, 적용, 실행.

## 튜토리얼 보기

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## 선택 - 적용 - 실행

![Pick a template, apply it, run it](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## 1단계: 선택

사용 가능한 템플릿을 탐색합니다:

```bash
time rdc repo template list
```

Postgres, Redis, 웹 서버 등 일반적인 앱을 위한 기성 설정이 표시됩니다.

## 2단계: 적용

저장소에 템플릿을 적용합니다. `app-postgres`를 사용하겠습니다:

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

저장소에 두 개의 새 파일이 생성됩니다: `docker-compose.yml`과 `Rediaccfile`. compose 파일은 컨테이너를 설명하고, `Rediaccfile`은 앱이 시작하고 중지할 때 발생하는 것, 즉 `up` 및 `down` 수명 주기 훅을 정의합니다.

## 3단계: 실행

이전 튜토리얼의 VS Code 연결을 통해 이미 저장소의 샌드박스 내부에 있으므로 `renet`을 직접 사용합니다:

```bash
time renet dev up
```

완료되었습니다. 앱이 실행 중입니다. 확인합니다:

```bash
time docker ps
```

여기서 `docker ps`는 이 저장소의 컨테이너만 나열합니다. 동일한 서버의 다른 저장소는 자체 Docker 데몬을 가지고 있으며 이 저장소에서는 완전히 보이지 않습니다.

---

다음: [저장소 작업하기](/ko/docs/tutorial-work-with-repo).
