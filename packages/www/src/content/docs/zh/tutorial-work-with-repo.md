---
title: "使用你的仓库"
description: "将端口隧道转发到浏览器，在沙盒内运行命令，并在笔记本和仓库之间同步文件。"
category: "Tutorials"
subcategory: essentials
order: 6
language: zh
sourceHash: "3d56eb69e72c1a5a"
---

# 使用你的仓库

应用正在运行，但目前你只通过 `docker ps` 查看过它。三条命令涵盖了日常工作流程：**tunnel** 在浏览器中查看应用，**term** 在沙盒内运行命令，**sync** 在笔记本和仓库之间移动文件。

## 观看教程

![Tutorial: Working with your repo](/assets/tutorials/tutorial-work-with-repo.cast)

## 日常三件套

![Tunnel、term、sync](/img/tutorials/tutorial-work-with-repo/slide-1.svg)

1. **Tunnel**：在浏览器中打开应用。
2. **Term**：在沙盒内运行命令。
3. **Sync**：文件移入移出。

## Tunnel：在浏览器中查看应用

应用运行在服务器上，而不是你的笔记本上。通过 SSH 转发容器端口：

```bash
rdc repo tunnel -m my-server -r my-app -c app
```

在浏览器中打开 `localhost`，应用就在那里。完成后按 `Ctrl+C`。

需要访问不同容器时，替换 `-c` 并指定端口：

```bash
rdc repo tunnel -m my-server -r my-app -c db --port 5432
```

## Term：在仓库内运行命令

只需要一个 shell 时，无需打开 VS Code：

```bash
rdc term connect -m my-server -r my-app
```

现在你在仓库的沙盒内。试试看：

```bash
time docker ps
```

你只看到 `my-app` 的容器，和在 VS Code 中看到的视图相同。

需要一次性命令时，用 `-c` 跳过交互式 shell：

```bash
time rdc term connect -m my-server -r my-app -c "df -h ."
```

## Sync：在笔记本和仓库之间移动文件

将笔记本上的文件夹推送到仓库：

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src
```

将文件拉取回来：

```bash
time rdc repo sync download -m my-server -r my-app --local ./backup
```

不确定时先预览。`--dry-run` 会显示将要变更的内容，而不实际复制：

```bash
time rdc repo sync upload -m my-server -r my-app --local ./src --dry-run
```

Tunnel、term、sync。三条命令覆盖日常循环。

---

下一篇：[Fork 仓库](/en/docs/tutorial-forking)。
