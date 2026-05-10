---
title: "网络与域名"
description: "通过域名、自动 TLS 和 Traefik 反向代理让你的应用在互联网上可访问。"
category: "Tutorials"
subcategory: advanced
order: 9
language: zh
sourceHash: "9f72a61ed1ff4cb9"
---

# 网络与域名

你的应用正在运行，但目前还没有人能访问到它。本教程将帮你配置真实域名、通过 Let's Encrypt 实现自动 TLS，以及部署能自动发现容器的 Traefik 代理。你需要在 Cloudflare 上托管一个域名和一个 API 令牌。

## 观看教程

![Tutorial: Networking and domains](/assets/tutorials/tutorial-networking.cast)

## 四个步骤

![获取令牌、配置、推送、部署](/img/tutorials/tutorial-networking/slide-1.svg)

1. **获取** Cloudflare API 令牌。
2. 在 `rdc` 上**配置**基础设施。
3. 将配置**推送**到服务器。
4. **部署**代理。

## 第一步：Cloudflare API 令牌

在 Cloudflare 控制台，进入 **My Profile → API Tokens**，创建一个具有 **Zone DNS Edit** 权限的令牌。复制令牌值，它只会显示一次。

## 第二步：配置基础设施

告诉 `rdc` 你的公网 IP、根域名、证书邮箱和令牌：

```bash
time rdc config infra set -m my-server \
  --public-ipv4 203.0.113.50 \
  --base-domain yourdomain.com \
  --cert-email admin@yourdomain.com \
  --cf-dns-token your-cloudflare-api-token
```

将 IP、域名、邮箱和令牌替换为你自己的。

`--cert-email` 和 `--cf-dns-token` 在你所有机器间共享，因此只需设置一次。

## 第三步：推送到服务器

```bash
time rdc config infra push -m my-server
```

这会自动在 Cloudflare 上创建 DNS 记录，并在服务器上准备代理配置。

## 第四步：部署代理

代理本身还没有运行。使用内置的 `proxy` 模板，在一个名为 `infra` 的小仓库中部署它：

```bash
time rdc repo create --name infra -m my-server --size 1G
time rdc repo template apply --name proxy -m my-server -r infra
time rdc repo up --name infra -m my-server
```

完成。Traefik 现在正在运行。你的应用可以通过以下地址访问：

```
myapp.my-app.my-server.yourdomain.com
```

Traefik 每 5 秒自动发现你的容器，TLS 证书由 Let's Encrypt 自动颁发。无需手动配置代理。

---

下一篇：[生产模式](/en/docs/tutorial-production-mode)。
