---
title: "프로덕션 모드"
description: "노트북과 분리된 상태에서 앱을 실행하고 자동 시작으로 서버 재부팅에서 살아남습니다."
category: "Tutorials"
subcategory: advanced
order: 10
language: ko
sourceHash: "0e070fcd877900ab"
---

# 프로덕션 모드

지금까지 저장소 내부에서 `renet dev up`으로 앱을 실행했습니다. 개발에는 훌륭합니다. 프로덕션에서는 `rdc`로 노트북에서 모든 것을 관리합니다. 노트북을 닫아도 앱은 계속 실행됩니다.

## 튜토리얼 보기

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## 개발 vs 프로덕션

차이는 간단합니다:

- `renet dev up`은 **저장소 내부**에서 실행됩니다. 연결되어 있어야 합니다.
- `rdc repo up`은 **노트북에서** 실행됩니다. 이후 연결이 필요 없습니다.

세 가지 작업으로 개발에서 프로덕션으로 전환합니다:

![Stop, start, autostart](/img/tutorials/tutorial-production-mode/slide-1.svg)

## 1단계: 개발 세션 중지

저장소에 연결하고 내립니다:

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## 2단계: 프로덕션 모드로 시작

노트북의 터미널에서:

```bash
time rdc repo up --name my-app -m my-server
```

완료되었습니다. 앱이 실행 중이고 노트북을 닫을 수 있습니다. `Rediaccfile`이 모든 것을 처리합니다. `rdc repo up`은 `renet dev up`이 했던 것과 동일한 `up` 함수를 호출합니다. 동일한 `Rediaccfile`, 다른 호출 방식.

## 3단계: 서버 재부팅에서 살아남기

서버가 재시작될 때 앱이 자동으로 복구되도록 합니다:

```bash
time rdc repo autostart enable --name my-app -m my-server
```

자동 시작이 활성화된 저장소를 확인합니다:

```bash
time rdc repo autostart list -m my-server
```

## 프로덕션에서 중지하기

앱을 중지해야 할 때:

```bash
time rdc repo down --name my-app -m my-server
```

올리는 명령 하나, 내리는 명령 하나. 모두 노트북에서.

---

다음: [백업 및 복원](/ko/docs/tutorial-backup-restore).
