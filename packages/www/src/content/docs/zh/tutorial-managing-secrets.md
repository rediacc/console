---
title: "管理密钥"
description: "将部署时的凭据存放在 fork 无法访问的地方。设计上只写不读。"
category: "Tutorials"
subcategory: advanced
order: 8
language: zh
sourceHash: "0b4d72c80b489e12"
---

# 管理密钥

真实应用需要真实凭据：Stripe 生产密钥、数据库密码、API 令牌。把它们放在仓库里是错误的做法，因为 fork 会继承加密镜像内的所有内容。这样一来，你的沙盒就会向真实客户收费。

正确的做法是使用 `rdc repo secret`。两种交付模式，设计上只写不读，fork 启动时什么都没有。

## 观看教程

![Tutorial: Managing secrets](/assets/tutorials/tutorial-managing-secrets.cast)

## 陷阱：仓库里的 `.env`

![仓库镜像内的点 env 文件会被每个 fork 克隆](/img/tutorials/tutorial-managing-secrets/slide-1.svg)

大多数团队把 `.env` 放在仓库里。这是显而易见的做法。

然后他们 fork 了。

fork 是父仓库镜像的逐字节拷贝。`.env` 里有什么，fork 的 `.env` 里就有什么。fork 的容器启动了，读取了相同的 Stripe 密钥，用生产凭据调用了相同的 Stripe API。从 Stripe 的角度看，那次调用就是*你*发出的。

那会是糟糕的一天。

## 设置密钥

解决方案是 `rdc repo secret`。以 `env` 模式设置一个密钥，它会作为环境变量落入容器：

```bash
time rdc repo secret set --name my-app --key DB_HOST --value postgres.internal --mode env --current ""
```

注意两点：

- `--mode env`：值作为环境变量落入容器。
- `--current ""`：空字符串，声明这是一个全新密钥，没有先前的值。

以 `file` 模式再设置一个，适用于任何敏感内容：

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_xxx --mode file --current ""
```

`file` 模式永远不会将值放入容器的环境变量。它会使用 Docker 的标准机制将值写入 `/run/secrets/stripe_key`。

列出现有密钥：

```bash
time rdc repo secret list --name my-app
```

你看到的是名称和模式。**没有值。** 列表永远不显示值。

## 接入 compose

打开 `docker-compose.yml`，引用两种模式：

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

`${REDIACC_SECRET_DB_HOST}` 是 `env` 模式：`renet` 的 compose 包装器在部署时从密钥存储中展开它。

`secrets:` 块是 `file` 模式，使用 Docker 的标准机制。宿主机路径使用 `${REDIACC_NETWORK_ID}`，使同一个 compose 文件适用于父仓库和 fork。每个 fork 有自己的网络 ID。

部署：

```bash
time rdc repo up --name my-app -m my-server
```

## 在容器内验证

两种模式现在都应该在容器内了。检查 env 模式密钥：

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) printenv DATABASE_HOST'
```

`postgres.internal`。env 模式密钥已到达容器的环境变量。

现在检查 file 模式密钥：

```bash
time rdc term connect -m my-server -r my-app -c 'docker exec $(docker ps -q -f name=api) cat /run/secrets/stripe_key'
```

`sk_test_xxx`。文件通过 Docker 的标准密钥机制挂载。

## 永远无法读回密钥值

![只写模型：get 返回摘要，而不是值](/img/tutorials/tutorial-managing-secrets/slide-2.svg)

现在是让人意外的部分：

```bash
time rdc repo secret get --name my-app --key STRIPE_KEY
```

你得到的是摘要。**不是值。** 没有任何标志可以让它返回值。没有任何命令能给你返回明文。

这就是 GitHub Actions 模型：只写设计。你可以通过传入 `--current <value>` 并看到前置条件通过来证明你知道密钥的内容。但你无法要求 Rediacc 告诉你它是什么。

忘记了值？**别去偷看。轮换它。**

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --rotate-secret
```

`--rotate-secret` 跳过前置条件检查。审计日志将此次变更标记为轮换操作：明确、有意为之。

如果你确实记得旧值，可以用它来证明：

```bash
time rdc repo secret set --name my-app --key STRIPE_KEY --value sk_test_new --mode file --current sk_test_xxx
```

这是更安全的路径，它能捕捉到"我在错误的终端里"这类失误。

## fork 的结局

![fork 后，密钥列表为空](/img/tutorials/tutorial-managing-secrets/slide-3.svg)

还记得那个陷阱吗？Fork 仓库然后看看：

```bash
time rdc repo fork --parent my-app --tag test -m my-server
time rdc repo secret list --name my-app:test
```

**空的。**

fork 没有 Stripe 密钥，没有数据库密码，没有 API 令牌。fork 中的容器无法展开 `${REDIACC_SECRET_STRIPE_KEY}`。`/var/run/rediacc/secrets/<fork-id>/STRIPE_KEY` 这个文件并不存在。

fork 无法伪装成你。

如果你想在 fork 中使用密钥进行测试，用沙盒值在 fork 上单独设置：

```bash
time rdc repo secret set --name my-app:test --key STRIPE_KEY --value sk_sandbox_yyy --mode file --current ""
```

现在 fork 与 Stripe 沙盒通信。生产凭据从未离开生产环境。

## 总结

- `rdc repo secret` 将凭据存放在仓库镜像之外。
- fork 无法访问它们。
- `get` 返回摘要，而不是值。
- 忘记了就轮换，不要去偷看。

密钥，fork 无法追随。

---

下一篇：[网络与域名](/en/docs/tutorial-networking)。
