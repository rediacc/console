---
title: "첫 번째 저장소 만들기"
description: "서버에 암호화된 저장소를 만들고 VS Code에서 엽니다."
category: "Tutorials"
subcategory: essentials
order: 4
language: ko
sourceHash: "1294b0494f20671b"
---

# 첫 번째 저장소 만들기

Rediacc 저장소는 서버의 단일 암호화 파일입니다. 마운트되면 자체 Docker 데몬과 자체 애플리케이션 데이터를 가진 폴더가 됩니다. 완전히 격리되고 완전히 이식 가능합니다.

프로덕션을 위한 USB 드라이브라고 생각하세요: 정지 상태에서는 파일, 실행 시에는 서버.

## 튜토리얼 보기

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## 디스크의 파일, 마운트 시 환경

![Encrypted file mounts as an isolated folder](/img/tutorials/tutorial-create-repo/slide-1.svg)

디스크상의 형태는 단일 암호화 이미지입니다. 마운트되면 다음을 얻습니다:

- 전용 Docker 데몬 (호스트의 것과 분리됨)
- 암호화된 볼륨 내의 애플리케이션 데이터
- 박스의 다른 어떤 것과도 충돌하지 않는 루프백 IP

저장소는 이식 가능합니다. 머신 간에 이동하거나, 백업하거나, 즉시 포크할 수 있습니다. 모든 저장소는 동일한 서버의 다른 모든 저장소와 격리됩니다.

## 저장소 만들기

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

`my-server`에 2 GB 암호화 저장소를 생성합니다. 확인합니다:

```bash
time rdc repo list -m my-server
```

## VS Code에서 열기

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code가 저장소 내부에서 직접 열립니다. 워크스페이스가 비어 있음을 확인하세요. 이것이 격리된 환경입니다. 여기서 만드는 모든 것은 암호화된 볼륨 내부에 저장되며, 동일한 서버의 다른 저장소에는 보이지 않습니다.

---

다음: [첫 번째 앱 배포하기](/ko/docs/tutorial-deploy-app).
