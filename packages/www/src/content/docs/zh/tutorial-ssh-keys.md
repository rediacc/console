---
title: "SSH 密钥配置"
description: "配置你的 SSH 密钥，让 rdc 无需密码即可连接到服务器。"
category: "Tutorials"
subcategory: essentials
order: 2
language: zh
sourceHash: "009a1bd345e93413"
---

# SSH 密钥配置

`rdc` 通过 SSH 连接到服务器，因此每台服务器都需要信任你的 SSH 密钥。总共三个步骤：两步是一次性设置，一步在每次添加新服务器时重复执行。

## 观看教程

![Tutorial: SSH key configuration](/assets/tutorials/tutorial-ssh-keys.cast)

## 三个步骤

![生成、复制、注册](/img/tutorials/tutorial-ssh-keys/slide-1.svg)

1. 在笔记本上**生成** SSH 密钥。一次，永久有效。
2. 将密钥**复制**到服务器。每次添加新服务器时重复此步骤。
3. 将密钥**注册**到 `rdc`。一次，永久有效。

## 第一步：生成密钥

如果你已有想使用的密钥，可以跳过此步骤。否则：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

`ed25519` 是现代默认算法：体积小、速度快、兼容性好。

## 第二步：将密钥复制到服务器

```bash
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip
```

将 `user` 和 `your-server-ip` 替换为服务器的 SSH 用户名和 IP 地址。系统会最后一次提示你输入服务器密码。此后，密码认证将不再需要。

## 第三步：将密钥注册到 `rdc`

```bash
time rdc config ssh set --key ~/.ssh/id_ed25519
```

完成。从此以后，每条 `rdc` 命令都使用此密钥进行认证。不再需要密码，不再有交互提示。

---

下一篇：[添加第一台服务器](/en/docs/tutorial-add-server)。
