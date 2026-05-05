---
title: "管理密钥"
description: "设置每个仓库的密钥，将其连接到 compose，验证它们到达容器，轮换它们，并确认 fork 不继承任何内容。"
category: "Tutorials"
order: 7
language: zh
sourceHash: "fb8bc967ed22fc10"
---

# 如何使用 Rediacc 管理每个仓库的密钥

真实的应用程序需要凭据：Stripe 实时密钥、数据库密码、API 令牌。错误的位置是放在仓库内部。fork 会继承加密映像中的所有内容，其容器以父级身份对外部服务进行身份验证。正确的位置是 `rdc repo secret`。值落在加密映像之外，因此 fork 以空的密钥映射开始。

在本教程中，您设置两种密钥模式，将它们连接到 compose 文件，验证它们到达容器，轮换一个并确认 fork 不继承任何内容。

## 前提条件

- 已安装并初始化配置的 `rdc` CLI
- 已配置的机器和已创建的仓库（参见[教程：仓库生命周期](/zh/docs/tutorial-repos)）
- 您可以编辑的 `Rediaccfile` 和 `docker-compose.yml`

## 步骤 1：设置密钥

有两种交付模式可用。`env` 将值导出为 `REDIACC_SECRET_<KEY>` 用于 compose 的 `${...}` 插值。`file` 将值写入主机端 tmpfs 文件 `/var/run/rediacc/secrets/<networkID>/<KEY>`，与 Docker compose 的 `secrets:` 块一起使用。对任何敏感内容使用 `file`。env 模式下的值会出现在 `docker inspect` 和 `/proc/<pid>/environ` 中。

对于全新密钥的首次写入，传递 `--current ""`（空）以确认没有先前的值。

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

## 步骤 2：列出现有内容

```bash
rdc repo secret list --name my-app
```

输出是包含每个密钥的名称和模式的 JSON。值永远不会出现在列表中。它们甚至不会从磁盘获取。

```json
{
  "repository": "my-app:latest",
  "secrets": [
    { "key": "DB_HOST", "mode": "env" },
    { "key": "STRIPE_KEY", "mode": "file" }
  ]
}
```

## 步骤 3：连接到 compose

两种模式都从同一个 `docker-compose.yml` 引用：

```yaml
services:
  api:
    image: myapp:latest
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_key

secrets:
  stripe_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_KEY
```

服务上的小写 `stripe_key` 是容器内的 `/run/secrets/<name>` 文件名。主机路径中的大写 `STRIPE_KEY` 与您设置的 `--key` 匹配。`${REDIACC_NETWORK_ID}` 由 `renet compose` 自动插值。这很重要，因为网络 ID 是按 fork 的，所以同一个 compose 文件在父级和任何 fork 中都能工作（在那里，正如您将在步骤 6 中看到的，文件根本不存在）。

> **强制执行跨仓库隔离。** renet 的 compose 验证器拒绝任何针对另一个仓库网络 ID 的 `secrets: file:`（或 `configs: file:` 或 `env_file:`）路径。字面上的 `${REDIACC_NETWORK_ID}` 标记（或您自己网络的整数）是唯一接受的形式，`--unsafe` 不会覆盖它。围绕 Rediaccfile bash 子进程的 Landlock 沙盒还将文件系统读取限制在您自己网络的密钥目录中。因此即使来自 Rediaccfile 的恶意 `cat /var/run/rediacc/secrets/<其他>/X` 也会在内核层因 EACCES 而失败。您无需执行任何操作来选择加入；保护默认开启。

## 步骤 4：部署并验证

```bash
rdc repo up --name my-app -m server-1
```

部署后，进入容器以确认两种模式都已到达：

```bash
# env-mode reaches the container's environment
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
# postgres.internal

# file-mode reaches /run/secrets/ inside the container
rdc term connect -m server-1 -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
# sk_test_xxx
```

如果您想直接检查主机端 tmpfs 文件：

```bash
rdc term connect -m server-1 -c 'sudo ls -la /var/run/rediacc/secrets/<networkID>/'
# -r--r--r-- 1 root root 11 May  4 12:01 STRIPE_KEY
# parent dir is mode 0700 root:root; per-file mode 0444. The dir is the security gate.
```

## 步骤 5：在不知道先前值的情况下轮换

您可以使用 `rdc repo secret get` 读取摘要，但永远不能读取明文值。这是仅写模型。如果您需要验证存储的值与您拥有的值匹配，请通过 `--current` 传递它，并观察前置条件通过或失败：

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --current postgres.internal
```

如果您完全忘记了先前的值（您的密码管理器丢失了它，或者您继承了仓库），请使用 `--rotate-secret` 跳过前置条件。审计日志会大声将其记录为轮换：

```bash
rdc repo secret set --name my-app --key DB_HOST --value postgres-new.internal --rotate-secret
```

`--current` 和 `--rotate-secret` 互斥。选择一个。

## 步骤 6：确认 fork 不继承任何内容

整个要点：fork 仓库并检查 fork 的密钥列表：

```bash
rdc repo fork --parent my-app --tag test -m server-1
rdc repo secret list --name my-app:test
```

```json
{
  "repository": "my-app:test",
  "secrets": []
}
```

为空。fork 的容器无法插值 `${REDIACC_SECRET_DB_HOST}`（变量未设置，因此为空字符串），并且 `/var/run/rediacc/secrets/<fork-networkID>/STRIPE_KEY` 处的文件根本不存在。如果 fork 的 `repo up` 尝试通过 compose `secrets:` 块挂载它，部署将以明确的错误失败。这正是您想要的失败模式，因为这意味着沙盒无法在外部服务面前假装是生产环境。

要在 fork 中使用密钥，请使用沙盒范围的值在 fork 上显式设置它们：

```bash
rdc repo secret set --name my-app:test --key DB_HOST --value postgres-test.internal --mode env --current ""
rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

现在 fork 与测试数据库和 Stripe 沙盒帐户通信。父级的生产凭据永远不会离开父级。

## 清理

```bash
rdc repo secret unset --name my-app --key STRIPE_KEY --current sk_test_xxx
rdc repo delete --name my-app:test -m server-1
```

## 另请参阅

- [仓库 § 密钥](/zh/docs/repositories#secrets)。完整参考
- [RDC CLI 速查表 § 每个仓库的密钥](/zh/docs/rdc-cheat-sheet#per-repo-secrets)。命令快速参考
- [AI 代理安全](/zh/docs/ai-agents-safety)。对称突变门和错误信封中的结构化 `next` 操作提示
- [服务 § 在 compose 中使用每个仓库的密钥](/zh/docs/services#using-per-repo-secrets-in-compose)。Compose 模式参考
