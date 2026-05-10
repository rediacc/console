---
title: "SSH 키 구성"
description: "rdc가 비밀번호 없이 서버에 연결할 수 있도록 SSH 키를 구성합니다."
category: "Tutorials"
subcategory: essentials
order: 2
language: ko
sourceHash: "009a1bd345e93413"
---

# SSH 키 구성

`rdc`는 SSH를 통해 서버에 연결하므로 각 서버가 SSH 키를 신뢰해야 합니다. 총 세 단계입니다. 두 단계는 일회성 설정이고, 한 단계는 새 서버를 추가할 때마다 반복합니다.

## 튜토리얼 보기

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## 세 단계

![Generate, copy, register](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. 노트북에서 SSH 키를 **생성**합니다. 딱 한 번.
2. 서버에 **복사**합니다. 새 서버마다 반복.
3. `rdc`에 키를 **등록**합니다. 딱 한 번.

## 1단계: 키 생성

사용하고 싶은 키가 이미 있다면 건너뜁니다. 없다면:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519`는 현대적인 기본값입니다. 작고, 빠르고, 잘 지원됩니다.

## 2단계: 서버에 복사

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

`user`와 `your-server-ip`를 서버의 SSH 사용자와 IP로 교체하세요. 서버 비밀번호를 마지막으로 한 번 입력하라는 요청이 있습니다. 이후 비밀번호 인증이 더 이상 필요하지 않습니다.

## 3단계: `rdc`에 키 등록

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

완료되었습니다. 이후 모든 `rdc` 명령이 이 키로 인증됩니다. 더 이상 비밀번호도, 대화형 프롬프트도 없습니다.

---

다음: [첫 번째 서버 추가하기](/ko/docs/tutorial-add-server).
