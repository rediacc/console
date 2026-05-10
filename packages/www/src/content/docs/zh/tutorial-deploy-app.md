---
title: "部署第一个应用"
description: "使用 renet dev up 从内置模板部署一个容器化应用。"
category: "Tutorials"
subcategory: essentials
order: 5
language: zh
sourceHash: "f75b5b6a716e94bf"
---

# 部署第一个应用

你有了一个空仓库。`rdc` 内置了模板，让你无需从头编写 `docker-compose` 就能启动真实应用。三个步骤：选择模板、应用模板、运行。

## 观看教程

![Tutorial: Deploying your first app](/assets/tutorials/tutorial-deploy-app.cast)

## 选择 · 应用 · 运行

![选择模板、应用模板、运行](/img/tutorials/tutorial-deploy-app/slide-1.svg)

## 第一步：选择

浏览可用的模板：

```bash
time rdc repo template list
```

你会看到常见应用的现成配置：Postgres、Redis、Web 服务器等。

## 第二步：应用

将模板放入你的仓库。我们使用 `app-postgres`：

```bash
time rdc repo template apply --name app-postgres -m my-server -r my-app
```

仓库中会出现两个新文件：`docker-compose.yml` 和 `Rediaccfile`。compose 文件描述容器，`Rediaccfile` 定义应用启动和停止时的行为（即 `up` 和 `down` 生命周期钩子）。

## 第三步：运行

你已经在仓库的沙盒内（通过上一个教程的 VS Code 连接），因此直接使用 `renet`：

```bash
time renet dev up
```

完成。应用正在运行。验证一下：

```bash
time docker ps
```

这里的 `docker ps` 只列出本仓库的容器。同一服务器上的其他仓库拥有各自的 Docker 守护进程，在这里完全不可见。

---

下一篇：[使用你的仓库](/en/docs/tutorial-work-with-repo)。
