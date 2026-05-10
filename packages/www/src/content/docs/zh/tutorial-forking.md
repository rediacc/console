---
title: "Fork 仓库"
description: "在几秒内克隆整个仓库（应用、数据库、文件）。任意大小，零额外磁盘占用。"
category: "Tutorials"
subcategory: advanced
order: 7
language: zh
sourceHash: "9237f00dce2ee5ec"
---

# Fork 仓库

这是杀手级功能：在几秒内克隆整个生产环境（应用、数据库、配置文件）。任意大小，零额外磁盘占用，随心所欲地 fork。

一句话总结：**克隆生产环境，万无一失。**

## 观看教程

![Tutorial: Forking a repository](/assets/tutorials/tutorial-forking.cast)

## 准备一些可以"破坏"的内容

首先，给运行中的应用创建一个文件，用来证明 fork 的隔离性。在 VS Code 中打开仓库：

```bash
rdc vscode connect -m my-server -r my-app
```

在仓库内创建一个标记文件：

```bash
time echo "Hello from production" > index.html
```

现在 fork 它。

## Fork

```bash
time rdc repo fork --parent my-app -m my-server --tag experiment --up
```

![父仓库扇形展开为独立克隆](/img/tutorials/tutorial-forking/slide-1.svg)

一条命令。它克隆了一切（应用、数据库、配置文件），而且只用了几秒。再运行一次，你就得到另一个独立克隆。

## 为什么这么快？

![分享文件夹链接的速度与文件夹大小无关](/img/tutorials/tutorial-forking/slide-2.svg)

想象一下分享文件夹链接。无论文件夹是大是小，链接本身是一样的。文件夹很重，链接很轻。

![1 GB、100 GB、1 TB，每次时间相同。](/img/tutorials/tutorial-forking/slide-3.svg)

Fork 的工作原理相同。1 GB、100 GB、1 TB，每次时间相同。

## 什么是共享的，什么是你独有的

![多面镜子，一个太阳：共享基础，你的改动属于你](/img/tutorials/tutorial-forking/slide-4.svg)

把父仓库想象成太阳。你无法握住太阳，但你可以拿一面镜子来捕捉它。那面镜子就是你的 fork。在镜子上作画，你的画是你的。无论有多少面镜子对着太阳，太阳都保持不变。

> 你无法握住太阳，但你可以把它握在镜子里。

## 父仓库后来发生变化怎么办？

![fork 是一张冻结的照片，父仓库像河流一样继续流淌](/img/tutorials/tutorial-forking/slide-5.svg)

现在想象一条河。水不断流动，每时每刻都在变化。当你 fork 时，你拍下了那一刻河流的照片，冻结在那个瞬间。河流继续流动，你的照片不会。

如果父仓库后来发生了变化，你的 fork 仍然停留在原来的位置。

> 你无法握住一条河，但你可以把它握在照片里。

## 磁盘占用保持平稳

![100 GB 仓库的五个 fork，总占用仍约为 100 GB](/img/tutorials/tutorial-forking/slide-6.svg)

这就是你的磁盘不会爆满的原因。100 GB 仓库的五个 fork？总占用仍约为 100 GB。你只为每个 fork 中实际修改的内容付出磁盘代价。

> Fork 五次也无妨，你的磁盘甚至感觉不到。

## fork 不会继承的内容：密钥

fork 有一件事刻意不继承：密钥。fork 启动时没有 API 密钥、没有数据库密码、没有 Stripe 令牌。这就是"克隆生产环境，万无一失"真正奏效的原因。你的沙盒无法向真实客户收费，因为它无法伪装成你。我们会在[管理密钥](/en/docs/tutorial-managing-secrets)教程中正式设置这一机制。

## 验证隔离性

并排列出两个仓库：

```bash
time rdc repo list -m my-server
```

你会看到 `my-app` 和 `my-app:experiment` 同时运行。

在原始仓库中查看运行状态：

```bash
time docker ps
```

注意运行时间。这些是原始容器。现在切换到 fork：

```bash
rdc vscode connect -m my-server -r my-app:experiment
```

```bash
time docker ps
```

镜像相同，但运行时间是全新的。它们是 fork 时才启动的。

让差异更加明显。仅在 fork 中添加一个容器：

```bash
time docker run --rm -it -d nginx
time docker ps
```

nginx 正在运行，但只在这个 fork 内部。

尝试一些破坏性操作：

```bash
time rm index.html
```

这里已经删除了。现在跳回原始仓库：

```bash
rdc vscode connect -m my-server -r my-app
time docker ps
```

没有 nginx。fork 的容器留在了 fork 里。而 `index.html` 仍然在这里，完好无损。原始仓库从不知道发生了什么。相同的镜像，独立的 Docker 守护进程，独立的文件系统。

## 清理

完成后，直接删除 fork：

```bash
time rdc repo delete --name my-app:experiment -m my-server
```

原始仓库保持原样。**Fork、实验、破坏、删除。** 零风险。

---

下一篇：[管理密钥](/en/docs/tutorial-managing-secrets)。
