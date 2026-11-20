---
title: "nginx2root 与 PHP 远程代码执行漏洞：先 fork 再动手，一个晚上修完生产服务器"
description: "两天内连发两个严重安全版本。我们检查了 43 个容器，找出真正暴露的 6 个，先在 fork 上测试风险最高的升级，最后在不丢数据的前提下给生产环境打上补丁。"
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - nginx
  - php
  - case-study
featured: true
language: zh
sourceHash: "94c45a97bd6b1c4e"
sourceCommit: "c3bae279da16e5441ac808ac85b812debb514694"
---

> **TL;DR.** nginx 在 11 月 18 日发布了 nginx2root（CVE-2026-123007 以及另外四个同类 RCE）的修复。PHP 在 11 月 19 日发布了 17 个 CVE 的修复，其中 7 个是严重级别。20 日晚上，我们给自己的生产服务器打了补丁。
>
> - 几分钟内查完 **43 个容器**，办法是直接问每个容器自己跑的是哪个版本的 nginx 和 PHP。
> - 其中 **13 个**版本偏旧，但真正暴露在外的只有 **6 个**：三个公网 Web 应用的 PHP 容器。
> - 所有修复都来自**官方镜像**，下载前先在镜像仓库里核实过。
> - 风险最高的升级（ERPNext 一次跨 8 个版本）先在带真实数据的 **fork** 上演练。发布说明回答不了的那个问题，fork 给出了答案。
> - 下载到一半磁盘满了。在线扩容卷只用了 **3.9 秒**，没有停机。

## 披露了什么

**nginx2root** 是开源 nginx 中的一组共五个远程代码执行漏洞。其中最主要的 CVE-2026-123007 是 HTTP/2 流量控制里的整数下溢，CVSS 4.0 评分 9.2。从 1.9.5（2015 年）到 1.31.8 的所有 nginx，只要开启了 HTTP/2 就受影响。另外四个漏洞需要满足以下条件之一：代理后面启用 HTTP/3，使用带 `auth_http` 的邮件代理，或者 DNS 解析器与 `mirror` 搭配使用。修复版本是 **1.31.9**（主线）和 **1.30.7**（稳定版）。同一天就出现了公开的 PoC。

**PHP 的版本**晚一天发布：8.5.13、8.4.28、8.3.37 和 8.2.36。最严重的漏洞出在会话处理和时区缓存，最终可能导致代码执行。第二组漏洞只影响 PHP-FPM：请求走私、状态页面的 XSS，以及本地提权。

这次的主角是 `hostinger`，也就是我们在 [PocketOS 测试](/zh/blog/i-tested-rediacc-against-the-pocketos-incident)里用过的那台生产机器。上面跑着带 Webmail 的邮件服务器、Nextcloud、营销套件、ERPNext、一个 GitLab、一套可观测性组件和几个演示。每个应用都放在自己的 Rediacc 仓库里：一个加密卷，带独立的 Docker 守护进程和独立的私有 IP 段。

## 第一步：先找出哪些有漏洞，再找出哪些真正暴露

镜像标签只说一半的实话。`nextcloud:35-apache` 看不出里面的 PHP 是哪个版本，Debian 软件包在安全修复前后也都显示 `nginx/1.26.3`。所以我们不看标签，直接问每个正在运行的容器。

```bash
for repo in nextcloud mail mautic erpnext gitlab marketing observability demo-stackoverflow; do
  rdc term connect "$repo@hostinger" -c 'for c in $(docker ps --format "{{.Names}}"); do
    echo "$c: $(docker exec "$c" sh -c "nginx -v 2>&1; php -v 2>/dev/null | head -1")"
  done'
done
```

`rdc term connect <repo>` 会在仓库自己的环境里打开一个 shell，`DOCKER_HOST` 已经指向该仓库的 Docker 守护进程。一个循环就扫完了整台机器。

![分诊漏斗：43 个容器，13 个含 nginx 或 PHP，13 个版本偏旧，6 个暴露在外](/img/blog-cve-triage-funnel.svg)

结果是：13 个容器里有 nginx 或 PHP，而且版本全都低于修复版本。听起来像是 13 个紧急故障，其实不是。

有漏洞是指代码里存在这个 bug，暴露是指攻击者真的能碰到这个 bug。两者的差别在网络路径上，而这台服务器上所有公网请求走的是同一条路径。

![流量路径：访客通过 HTTPS 和 HTTP/2 访问 Traefik，Traefik 再以明文 HTTP/1.1 转发给各个应用](/img/blog-cve-traffic-path.svg)

Traefik 是每个仓库前面的反向代理，负责终止 TLS 和 HTTP/2，再通过私有回环地址以明文 HTTP/1.1 与各个应用通信。我们检查了两个自带 nginx 的应用里的 nginx 配置：没有 `http2`，没有 HTTP/3，没有 `mirror`，也没有邮件代理。所以 nginx2root 根本无从下手。

PHP 的漏洞就不一样了，它们藏在普通的 Web 请求里。Nextcloud、Roundcube（Webmail）和 Mautic 都是在 Apache 后面跑 PHP，都面向公网，而且都落后一个补丁版本。这六个容器被排到了最前面。

有一点让 PHP 这边的情况好了一些：这三个应用都是把 PHP 当作 Apache 模块运行，而不是 PHP-FPM，所以只影响 FPM 的漏洞对它们不适用。会话和时区漏洞则依然适用。

## 第二步：找到官方修复，相信镜像仓库而不是博客文章

最初的几次网络搜索给出了言之凿凿却互相矛盾的答案。一篇文章说官方 Nextcloud 镜像还在用旧版 PHP，另一篇说某个第三方镜像已经修复了。没有一篇引用镜像本身的内容。

其实不用下载镜像就能看到里面有什么。镜像仓库会提供每个镜像的配置，基于 PHP 的官方镜像都会在里面记录 `PHP_VERSION`。

```bash
curl -s "https://registry-1.docker.io/v2/library/nextcloud/blobs/<config-digest>" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.config.Env[]' | grep PHP_VERSION
# PHP_VERSION=8.5.13
```

这样几分钟内就拿到了每个应用的明确答案：

| 应用 | 当前运行 | 官方修复 | 修复版本里的 PHP |
|---|---|---|---|
| Nextcloud | 35.0.2 | `nextcloud:35.0.3-apache` | 8.5.13 |
| Roundcube | 1.7.5 | `roundcube/roundcubemail:1.7.6-apache` | 8.4.28 |
| Mautic | 7.2.1 | `mautic/mautic:7.2.2-20261119-apache` | 8.3.37 |
| ERPNext | v16.52.1 | `frappe/erpnext:v16.60.0` | （nginx：未知） |

ERPNext 是个特例。它的 nginx 来自 Debian 的软件包，所以版本号无论如何都停在 1.26.3。Debian 的修复构建是 `1.26.3-3+deb13u11`，11 月 19 日发布。新的 ERPNext 镜像是当天晚上构建的，修复在不在里面？镜像配置看不出来，只有把镜像跑起来才知道。

## 第三步：在 fork 上演练风险最高的升级

像 Roundcube 1.7.5 到 1.7.6 这样的补丁版本风险很低。而 ERPNext 从 v16.52 到 v16.60，是跨八个版本的数据库迁移，操作的还是真实的账务数据。这一个必须先演练。

![先 fork 的发布流程：冻结 fork、测试 fork、升级并检查，最后上生产](/img/blog-cve-fork-first-rollout.svg)

Rediacc 的 fork 是仓库的完整副本，数据也包含在内，用写时复制（copy-on-write）克隆实现。不管多大都只要几秒，副本有自己的 Docker 守护进程、IP 段和 URL，里面的任何操作都碰不到生产环境。

```bash
rdc repo fork erpnext@hostinger --tag cve-test
rdc repo up erpnext:cve-test@hostinger --no-start   # mount only, start nothing yet
```

启动 fork 之前，我们先改了它的 compose 文件：换上新的镜像标签，并把调度器和两个任务队列放进一个默认禁用的 profile。带着真实 ERPNext 数据的副本如果跑着调度器，会给真实客户发出真实邮件。关掉之后，fork 只能提供页面和执行迁移，别的什么也做不了。

```bash
docker run --rm --entrypoint dpkg-query frappe/erpnext:v16.60.0 -W nginx
# nginx  1.26.3-3+deb13u11
```

答案出来了：新镜像带的是 Debian 打过补丁的 nginx。接着 fork 跑完了完整升级：`bench --site all migrate` 在生产数据库的副本上顺利完成，应用的健康检查接口返回了 `pong`，登录页面也能在 fork 自己的 URL 上正常打开。

如果镜像里还是旧的软件包，计划也很简单：停下来，删掉 fork，等下一次构建。生产环境不会为了一次没有任何修复效果的升级而重启，保持原样。

## 第四步：生产环境，一次一个应用

每个应用都走同一套简短的流程：

1. **快照。** `rdc repo fork <app> --tag pre-cve-20261120 --immutable` 生成一份冻结的只读副本。它无法被挂载或启动，所以永远不会被改动。
2. **固定标签。** 把 compose 文件改成确切的修复版本标签。
3. **先拉取，再部署。** 先 `docker pull`，再 `rdc repo up <app> -y`。
4. **执行应用自带的升级步骤**（如果有的话）。
5. **验证**：从内部看（版本、迁移），也从外部看（公网 URL）。

| 应用 | 过程 | 容器恢复用时 |
|---|---|---|
| Nextcloud | 镜像入口脚本执行了 `occ upgrade`，从 35.0.2 升到 35.0.3，维护模式约一分钟 | 66 秒 |
| Roundcube | 直接换镜像，schema 检查发现无事可做 | 24 秒 |
| Mautic | 第一次拉取时磁盘已满（见下文），之后执行 `doctrine:migrations:migrate` | 6 秒 |
| ERPNext | 步骤与演练一致，调度器保持开启，`bench migrate` 退出码为 0 | 17 秒 |

最后的探测显示，每个 PHP 容器里都是 PHP 8.5.13、8.4.28 和 8.3.37，ERPNext 里的 nginx 是 `deb13u11`，43 个容器全部在运行，没有任何健康检查失败。

## 出了什么问题

**浮动标签掩盖了一个过期镜像。** Nextcloud 原先用的是 `nextcloud:35-apache`。这个标签其实已经指向了修复后的镜像，但 `docker compose up -d` 不会去拉取本地已有的镜像，服务器会一直用着旧的 PHP。固定成 `35.0.3-apache` 之后，运行的版本在 compose 文件里一目了然，每次升级也都会产生真实的变更。

**下载到一半磁盘满了。** Mautic 的镜像有 2.1 GB，而它的仓库只剩 1.4 GB 可用空间。拉取在碰到运行中的容器之前就失败了，报错 `no space left on device`。解决只要一条命令，而且 Mautic 全程都在正常提供服务：

```bash
rdc repo expand mautic@hostinger --size 12G
# Repository expanded (3.9s)
```

卷在线从 8 GB 扩到了 12 GB，拉取随即成功。机器的容量策略现在可以在仓库写满之前自动扩容。

**冻结的快照一次都没用上。** 每次升级都成功了，所以四份 `pre-cve` 副本只是放在那里。这正是安全网的意义，但有两点要老实说。它们是在应用运行时创建的，所以里面的数据库文件是崩溃一致的，相当于断电后的状态，而不是干净关机后的状态。还有，从没演练过的回滚只是一个计划，不是保证。下次我们会趁快照还新鲜，实际测试一次恢复。

**有一个应用还没有修复版本。** 另一个应用在厂商镜像里自带了 nginx，而该厂商还没有发布 nginx 1.31.9。前面说的流量路径让 HTTP/2 碰不到它，所以我们选择等厂商发布，而不是自己手工构建镜像。

## 各种选择，以及理由

| 我们可选的做法 | 我们的选择 | 原因 |
|---|---|---|
| 关闭 HTTP/2 作为临时缓解 | 用新镜像打补丁 | HTTP/2 在 Traefik 那里就已经终止，缓解措施没有任何作用。打补丁是消除 bug，而不是把它藏起来。 |
| 相信版本字符串 | 检查镜像里的软件包 | Debian 会回移植修复而不改变 `nginx -v` 的输出，只有 `dpkg-query` 能看到真实的构建。 |
| 相信文章里说哪个镜像已修复 | 读取镜像仓库里的镜像配置 | 文章之间互相矛盾，镜像仓库才是源头。 |
| 像 `35-apache` 这样的浮动标签 | 像 `35.0.3-apache` 这样的确切标签 | 浮动标签可能已经指向修复版本，而服务器还在跑旧镜像。 |
| 原地升级，出问题再回滚 | 大版本跨度先 fork，小改动先快照 | 在 fork 上演练只要几秒，能赶在用户之前发现问题。给一次单步补丁升级做完整演练则是小题大做。 |
| 用金丝雀拆分流量（`rdc repo canary`） | 在 fork 上演练 | 金丝雀是在线上数据上运行新版本，适合 schema 向后兼容的应用。跨 8 个版本的迁移不属于这种情况。 |
| 手工清理已满的磁盘 | 在线扩容卷 | 在 Docker 数据目录下删文件有风险。扩容只要一条命令，也不用重启。 |

## 我们一直保留的检查清单

1. 问每个容器自己跑的是什么，不要看标签。
2. 顺着真实的网络路径，把有漏洞和真正暴露区分开。
3. 暴露的当天就修，其余的本周内修。
4. 从镜像仓库读取修复内容，不要信文章。
5. 对基于软件包的修复，检查镜像里的软件包构建。
6. 每次变更前先做快照。升级涉及数据迁移时，先在 fork 上演练。
7. 固定确切的标签。
8. 从内部和外部各验证一遍，然后清理 fork。

从阅读安全公告到最后一次验证，整个过程都由 AI 智能体（Claude Code）通过 `rdc` 完成，生产环境的访问权限由运维人员在会话开始前授予。先 fork 的流程让这件事做起来很放心：智能体在副本上做实验，生产环境只会看到已经验证过可行的步骤。
