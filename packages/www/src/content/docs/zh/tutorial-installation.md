---
title: "安装"
description: "用一条命令在笔记本上安装 rdc CLI，并用 rdc doctor 验证安装结果。"
category: "Tutorials"
subcategory: essentials
order: 1
language: zh
sourceHash: "99d4ca1a4f89278e"
---

# 安装

安装 `rdc` 只需三步：打开安装页面，选择操作系统，将命令粘贴到终端。整个过程通常一两分钟就能完成。

## 观看教程

![Tutorial: Installation](/assets/tutorials/tutorial-installation.cast)

## 三个步骤

![三步概览](/img/tutorials/tutorial-installation/slide-1.svg)

1. 打开[安装页面](/en/install)。
2. 选择你的操作系统。
3. 复制安装命令并粘贴到终端。

## 在你的平台上安装

安装页面会为你生成正确的命令，以下是各平台的标准单行命令。

**Linux / macOS：**

```bash
time curl -fsSL https://www.rediacc.com/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
iwr -useb https://www.rediacc.com/install.ps1 | iex
```

> `time` 前缀是一个 shell 技巧，用于打印命令的执行时长。我们在本系列中全程使用它，让你能直观感受每一步的实际速度。它是可选的，不需要时可以去掉。

## 验证安装

脚本执行完成后，检查 `rdc` 所需的一切是否都已就绪：

```bash
time rdc doctor
```

`rdc doctor` 会逐一检查 Node、SSH 以及 `rdc` 的其他依赖项，并报告任何缺失项。

## 为什么 `rdc` 运行在笔记本上

![rdc 在笔记本上，renet 在服务器上](/img/tutorials/tutorial-installation/slide-2.svg)

`rdc` 是运行在笔记本上的 CLI。服务器运行一个名为 `renet` 的独立组件，`rdc` 通过 SSH 对其进行配置和驱动。你永远不需要手动 SSH 进入服务器，`rdc` 会替你完成这一切。

我们会在接下来的两个教程中完成这部分设置。

---

下一篇：[SSH 密钥配置](/en/docs/tutorial-ssh-keys)。
