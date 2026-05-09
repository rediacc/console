---
title: "添加第一台服务器"
description: "向 rdc 注册第一台服务器，完成配置，并了解 rdc 与 renet 的架构。"
category: "Tutorials"
subcategory: essentials
order: 3
language: zh
sourceHash: "2b5de59f61cfb88c"
---

# 添加第一台服务器

在添加服务器之前，先了解 `rdc` 的工作原理会很有帮助。Rediacc 采用双工具架构：笔记本上运行 `rdc`，服务器上运行 `renet`。

## 观看教程

![Tutorial: Adding your first server](/assets/tutorials/tutorial-add-server.cast)

## 为什么需要两个工具？

![rdc 在笔记本上，renet 在服务器上，SSH 连接两者](/img/tutorials/tutorial-add-server/slide-1.svg)

- **`rdc`** 是运行在笔记本上的 CLI，你在这里输入命令。
- **`renet`** 是服务器上的编排器，负责管理加密、Docker 和隔离环境。

当你在本地运行命令时，`rdc` 通过 SSH 连接并在服务器上执行 `renet`。你永远不需要手动 SSH 进入服务器，`rdc` 会替你完成这一切。

## 第一步：注册服务器

告诉 `rdc` 服务器的信息。将名称、IP 和用户替换为你自己的。

```bash
time rdc config machine add --name my-server --ip 192.168.1.100 --user deploy
```

## 第二步：配置服务器

配置过程会在服务器上安装 `renet` 并创建加密数据存储。

```bash
time rdc config machine setup --name my-server
```

完成后，服务器就可以托管仓库了。

## 配置文件存放在哪里

验证 `rdc` 对你的配置的了解情况：

```bash
time rdc config show
```

或者直接打开原始 JSON 文件：

```bash
vim ~/.config/rediacc/rediacc.json
```

这个单一文件保存了一切：机器列表、仓库、SSH 密钥、加密凭据。将它复制到另一台笔记本，即可从那台机器操作相同的服务器。

---

下一篇：[创建第一个仓库](/en/docs/tutorial-create-repo)。
