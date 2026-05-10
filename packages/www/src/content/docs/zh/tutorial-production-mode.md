---
title: "生产模式"
description: "让应用脱离笔记本独立运行，并通过自动启动在服务器重启后自动恢复。"
category: "Tutorials"
subcategory: advanced
order: 10
language: zh
sourceHash: "0e070fcd877900ab"
---

# 生产模式

到目前为止，你一直在仓库内部用 `renet dev up` 运行应用。这对开发来说很好。在生产环境中，你用 `rdc` 从笔记本管理一切。关上笔记本，应用依然持续运行。

## 观看教程

![Tutorial: Production mode](/assets/tutorials/tutorial-production-mode.cast)

## 开发模式 vs 生产模式

区别很简单：

- `renet dev up` 在**仓库内部**运行，需要保持连接。
- `rdc repo up` 从**笔记本**运行，之后不需要保持连接。

三个操作将你从开发带到生产：

![停止、启动、自动启动](/img/tutorials/tutorial-production-mode/slide-1.svg)

## 第一步：停止开发会话

连接到仓库并将其关闭：

```bash
rdc vscode connect -m my-server -r my-app
time renet dev down
```

## 第二步：以生产模式启动

从笔记本的终端：

```bash
time rdc repo up --name my-app -m my-server
```

完成。应用正在运行，你可以关上笔记本了。`Rediaccfile` 处理一切。`rdc repo up` 调用的是与 `renet dev up` 相同的 `up` 函数，相同的 `Rediaccfile`，不同的调用方式。

## 第三步：在服务器重启后存活

确保应用在服务器重启后自动恢复：

```bash
time rdc repo autostart enable --name my-app -m my-server
```

查看哪些仓库已启用自动启动：

```bash
time rdc repo autostart list -m my-server
```

## 在生产环境中停止应用

需要停止应用时：

```bash
time rdc repo down --name my-app -m my-server
```

一条命令启动，一条命令停止。全从笔记本操作。

---

下一篇：[备份与恢复](/en/docs/tutorial-backup-restore)。
