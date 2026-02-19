---
title: "rdc vs renet"
description: "什么时候使用 rdc，什么时候使用 renet。"
category: "Guides"
order: 1
language: zh
---

# rdc vs renet

Rediacc 使用两个二进制：

- `rdc` 是面向用户的 CLI，在你的工作站上运行。
- `renet` 是在服务器上运行的低层远程二进制。

在几乎所有日常操作中，请使用 `rdc`。

## 心智模型

可以把 `rdc` 看作 control plane，把 `renet` 看作 data plane。

`rdc`：
- 读取本地上下文和机器映射
- 通过 SSH 连接服务器
- 在需要时部署/更新 `renet`
- 为你执行正确的远程操作

`renet`：
- 以较高权限在服务器上运行
- 管理 datastore、LUKS 卷、挂载点以及隔离的 Docker daemon
- 执行仓库与系统层面的低层操作

## 实际该用什么

### 使用 `rdc`（默认）

日常工作流请使用 `rdc`：

```bash
rdc context setup-machine server-1
rdc repo create my-app -m server-1 --size 10G
rdc repo up my-app -m server-1 --mount
rdc repo down my-app -m server-1
rdc machine status server-1
```

### 使用 `renet`（高级 / 服务器侧）

仅在你明确需要低层远程控制时，才直接使用 `renet`，例如：

- 直接在服务器上进行紧急调试
- 主机级维护与恢复
- 验证 `rdc` 未暴露的内部细节

大多数用户在日常操作中不需要直接调用 `renet`。

## Rediaccfile 说明

你可能会在 `Rediaccfile` 中看到 `renet compose -- ...`。这是正常的：Rediaccfile 函数运行在有 `renet` 的服务器侧。

从工作站侧，你通常仍通过 `rdc repo up` 和 `rdc repo down` 启停工作负载。
