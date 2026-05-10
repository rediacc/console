---
title: "첫 번째 서버 추가하기"
description: "rdc에 첫 번째 서버를 등록하고, 프로비저닝하고, rdc + renet 아키텍처를 이해합니다."
category: "Tutorials"
subcategory: essentials
order: 3
language: ko
sourceHash: "2b5de59f61cfb88c"
---

# 첫 번째 서버 추가하기

서버를 추가하기 전에 `rdc`가 어떻게 작동하는지 이해하는 것이 도움이 됩니다. Rediacc는 두 가지 도구 아키텍처를 사용합니다: 노트북의 `rdc`와 서버의 `renet`.

## 튜토리얼 보기

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## 왜 두 가지 도구인가요?

![rdc on laptop, renet on server, SSH between](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`**는 노트북의 CLI입니다. 여기서 명령을 입력합니다.
- **`renet`**은 서버의 오케스트레이터입니다. 암호화, Docker, 격리를 관리합니다.

로컬에서 명령을 실행하면 `rdc`가 SSH를 통해 서버에 연결하고 서버에서 `renet`을 실행합니다. 서버에 직접 SSH로 접속할 필요가 없습니다. `rdc`가 대신 처리합니다.

## 1단계: 서버 등록

`rdc`에 서버를 알립니다. 이름, IP, 사용자를 본인 것으로 교체하세요.

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## 2단계: 프로비저닝

설정은 서버에 `renet`을 설치하고 암호화된 데이터스토어를 생성합니다.

```bash
time rdc config machine setup --name my-server
```

완료되면 서버가 저장소를 호스팅할 준비가 됩니다.

## 설정 파일의 위치

`rdc`가 설정에 대해 아는 것을 확인합니다:

```bash
time rdc config show
```

또는 원시 JSON 파일을 직접 엽니다:

```bash
vim ~/.config/rediacc/rediacc.json
```

이 단일 파일에 모든 것이 담겨 있습니다: 머신, 저장소, SSH 키, 암호화 자격 증명. 다른 노트북에 복사하면 그 머신에서도 바로 사용할 수 있습니다.

---

다음: [첫 번째 저장소 만들기](/ko/docs/tutorial-create-repo).
