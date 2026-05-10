---
title: "创建第一个仓库"
description: "在服务器上创建一个加密仓库，并在 VS Code 中打开它。"
category: "Tutorials"
subcategory: essentials
order: 4
language: zh
sourceHash: "1294b0494f20671b"
---

# 创建第一个仓库

Rediacc 仓库是服务器上的一个单一加密文件。挂载后，它会变成一个拥有独立 Docker 守护进程和独立应用数据的文件夹：完全隔离，完全可移植。

可以把它想象成生产环境的 USB 驱动器：静态时是一个文件，运行时是一台服务器。

## 观看教程

![Tutorial: Creating your first repository](/assets/tutorials/tutorial-create-repo.cast)

## 磁盘上的文件，挂载后的环境

![加密文件挂载为隔离文件夹](/img/tutorials/tutorial-create-repo/slide-1.svg)

磁盘上的形式是一个单一加密镜像。挂载后，你将获得：

- 一个专用的 Docker 守护进程（与宿主机的完全分离）
- 加密卷内的应用数据
- 不会与服务器上其他内容冲突的回环 IP 地址

仓库是可移植的。你可以在机器之间迁移、备份，或即时 fork 任意仓库。同一台服务器上的每个仓库都与其他仓库完全隔离。

## 创建仓库

```bash
time rdc repo create --name my-app -m my-server --size 2G
```

这会在 `my-server` 上创建一个 2 GB 的加密仓库。验证结果：

```bash
time rdc repo list -m my-server
```

## 在 VS Code 中打开

```bash
rdc vscode connect -m my-server -r my-app
```

VS Code 会直接在仓库内部打开。注意工作区是空的，这就是你的隔离环境。你在这里创建的一切都存储在加密卷内，对同一服务器上的其他任何仓库都是不可见的。

---

下一篇：[部署第一个应用](/en/docs/tutorial-deploy-app)。
