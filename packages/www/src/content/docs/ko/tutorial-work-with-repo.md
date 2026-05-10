---
title: "저장소 작업하기"
description: "포트를 브라우저로 터널링하고, 샌드박스 내에서 명령을 실행하고, 노트북과 저장소 간에 파일을 동기화합니다."
category: "Tutorials"
subcategory: essentials
order: 6
language: ko
sourceHash: "3d56eb69e72c1a5a"
---

# 저장소 작업하기

앱이 실행 중이지만 지금까지 `docker ps`를 통해서만 확인했습니다. 세 가지 명령이 일상적인 워크플로를 담당합니다: **tunnel**로 브라우저에서 앱 확인, **term**으로 샌드박스 내에서 명령 실행, **sync**로 노트북과 저장소 간 파일 이동.

## 튜토리얼 보기

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## 일상적인 세 가지

![Tunnel, term, sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel** - 브라우저에서 앱을 엽니다.
2. **Term** - 샌드박스 내에서 명령을 실행합니다.
3. **Sync** - 파일을 주고받습니다.

## Tunnel: 브라우저에서 앱 확인

앱은 노트북이 아닌 서버에서 실행됩니다. 컨테이너의 포트를 SSH를 통해 전달합니다:

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

브라우저에서 `localhost`를 엽니다. 앱이 바로 거기 있습니다. 완료되면 `Ctrl+C`를 누릅니다.

다른 컨테이너의 경우 `-c`를 교체하고 포트를 선택합니다:

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term: 저장소 내에서 명령 실행

셸만 필요할 때 VS Code를 건너뜁니다:

```bash
rdc term connect -m my-server -r my-app
```

이제 저장소의 샌드박스 내부에 있습니다. 시도해 봅니다:

```bash
time docker ps
```

`my-app`의 컨테이너만 보입니다. VS Code에서 보는 것과 동일한 뷰입니다.

일회성 명령에는 `-c`를 사용하고 대화형 셸을 건너뜁니다:

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync: 노트북과 저장소 간 파일 이동

노트북에서 저장소로 폴더를 푸시합니다:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

파일을 다시 가져옵니다:

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

불확실하다면 먼저 미리 봅니다. `--dry-run`은 실제로 복사하지 않고 변경될 내용을 표시합니다:

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel, term, sync. 세 가지 명령이 일상적인 루프를 담당합니다.

---

다음: [저장소 포크하기](/ko/docs/tutorial-forking).
