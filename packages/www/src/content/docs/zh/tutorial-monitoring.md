---
title: "监控"
description: "使用 rdc machine 命令从笔记本检查服务器和仓库的健康状态。"
category: "Tutorials"
subcategory: advanced
order: 12
language: zh
sourceHash: "e6eaaed180c35e36"
sourceCommit: "be90e8e7896623c088b86360ec29c1baef2e86b4"
---

# 监控

你的应用已部署、上线并完成备份。现在确保一切保持健康。`rdc` 让你从笔记本就能全面了解任意服务器（健康状态、容器、仓库）的情况。

## 观看教程

![Tutorial: Monitoring](/assets/tutorials/tutorial-monitoring.cast)

## 三类可检查内容

![健康状态、容器、仓库](/img/tutorials/tutorial-monitoring/slide-1.svg)

## 健康状态：系统信息

从系统视图开始：

```bash
time rdc machine query --name my-server --system
```

这会显示系统运行时间、磁盘使用情况和存储状态。如果有异常，它会告诉你。

## 容器

查看机器上每个仓库中所有运行中的容器：

```bash
time rdc machine query --name my-server --containers
```

你会得到每个容器的名称、状态、健康检查、CPU 和内存使用情况，以及所属仓库。

## 仓库

检查你的仓库：

```bash
time rdc machine query --name my-server --repositories
```

这会显示每个仓库的大小、挂载状态、Docker 状态和磁盘使用情况。

## 一次性获取所有信息

```bash
time rdc machine query --name my-server
```

系统信息、仓库、容器，一条命令全部获取。不带过滤器的 `query` 命令返回完整信息；带 `--system`、`--containers`、`--repositories`、`--services`、`--network` 或 `--block-devices` 时只返回对应部分。

## 本地健康检查

`rdc doctor` 独立于任何特定服务器，检查你的本地设置（Node、SSH 密钥、`renet`、Docker）：

```bash
time rdc doctor
```

## 大功告成

这就是完整的系列教程。你现在可以安装、配置、部署、fork、上线、自动启动、备份和监控。全从终端完成，全在你自己的服务器上。
