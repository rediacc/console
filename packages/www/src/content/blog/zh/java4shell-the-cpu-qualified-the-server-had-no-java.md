---
title: "Java4Shell：CPU 符合条件，服务器上却没有 Java，而我们的模板教会了我们固定版本的道理"
description: "CVE-2026-114938 需要支持 AVX-512 VBMI 的 CPU 和受影响的 JDK。我们的服务器有这颗 CPU，却一个 JVM 都没有。真正的活儿在我们提供的应用模板里：一个固定的标签把 2023 年的 JDK 冻住了。"
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: zh
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **TL;DR.** Java4Shell（CVE-2026-114938）是 OpenJDK 中经 JIT 编译的 Base64 解码器里的一个堆越界写入漏洞，只会在支持 AVX-512 VBMI 的 x86-64 CPU 上触发。
>
> - 我们生产服务器的 CPU **四个必需的 flag 全都有**。只看 CPU，它像是暴露了。
> - 我们探查了 **43 个容器**、宿主机和未运行的仓库，**一个 Java 运行时都没有找到**。同一个探测脚本改为查找 `python3` 作为对照，该有的地方都找到了。服务器上没有需要打补丁的东西。
> - 我们提供的应用模板就是另一回事了。**四个**模板会启动 JVM。**三个**用的是浮动标签，上游已在 11 月 20 日用打过补丁的 JDK 重新构建。
> - **一个**，Elasticsearch，被固定在 `8.11.0`：这是 2023 年 11 月的镜像，自带 JDK `21.0.1`。Elastic 目前还没有修复版本，所以模板现在用 Elastic 官方给出的缓解 flag 启动 Elasticsearch，并在运行的节点上验证过。

## 披露了什么

11 月 17 日，Calif 的研究人员公布了 **Java4Shell**，Oracle 和 OpenJDK 当天就发布了修复。漏洞出在 HotSpot 的硬件加速 Base64 解码器：AVX-512 VBMI 路径处理最后几个字符时有误，可能写到堆缓冲区末尾之外。没有账号的远程攻击者可以借此造成内存损坏，在合适的应用里还能执行代码。公开的分析文章给出了几个知名 Java 服务器产品的未认证攻击链。

分诊时需要关注的细节：

- **受影响：** OpenJDK 17.0.6 及之后版本、21、25 和 27，在修复构建之前的版本。标准的 Java 8 和 Java 11 不受影响。
- **已修复：** 17.0.21.1、21.0.13.1、25.0.5.1 和 27.0.1.1（Temurin 构建带 `+2`，27 则是 `+4`）。如果运行时报告 `17.0.21` 而没有 `.1`，就仍然有漏洞。
- **前提条件：** 支持 AVX-512 VBMI 的 x86-64 CPU、JIT 已经编译过解码器，以及应用里存在对不可信输入做 Base64 解码的路径。ARM 不受影响。
- **评分：** CVSS 4.0 为 9.2，CVSS 3.1 为 8.1。已有独立的 PoC 公开。截至撰文时，还没有在野利用的报告。
- **缓解：** 用 `-XX:-UseBASE64Intrinsics` 启动 JVM。另一个公开的办法 `-XX:UseAVX=2` 在 x86-64 上同样有效，但会让 ARM 上的 JVM 无法启动。

我们[上一次的补丁行动](/zh/blog/patching-nginx2root-and-php-fork-first)最后是先 fork 再逐个应用上线的四个应用。这一次结束得早得多，有意思的地方正是原因。

## 第一步：CPU 符合条件吗？

大多数 CVE 只有软件层面的前提条件。这一个还有硬件层面的前提条件，而且检查起来很便宜：

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

四个全有。这台机器用的是 AMD EPYC 9354P，一颗完整支持 AVX-512 的新款服务器 CPU。如果分诊到这里就停下，结论会是“已暴露，今晚把所有 Java 都打上补丁”。

![三个前提条件：CPU 符合，JDK 检查不通过，所以输入路径根本到不了](/img/blog-java4shell-preconditions.svg)

## 第二步：有 Java 需要打补丁吗？

CPU 只是链条上的一环。第二环是受影响的 JDK，所以下一个问题很简单：到底哪些容器在跑 Java？

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

我们通过 `rdc term connect <repo>@hostinger` 对机器上的每个仓库都跑了一遍。用 `find` 查找 `libjvm.so`，可以发现打包在应用目录里、不在 `PATH` 中的 JVM，比如 Elasticsearch 就是这样自带 JDK 的。

结果是空的。43 个正在运行的容器里，没有 `java`，也没有 `libjvm.so`。

探测结果为空，在证明探测本身能找到东西之前说明不了任何问题。所以我们把同一个循环又跑了一次，这回查找 `python3`，我们知道 ERPNext 的容器里有它。结果每一个容器里都找到了 Python 3.14。探测是有效的，服务器上就是没有 Java。

结案前我们还检查了另外两个地方。宿主机本身没有 Java，也没有 `/usr/lib/jvm`。没有运行任何东西的仓库，它们的 Docker 守护进程里也没有 Java 镜像。其中一个仓库里有我们自己 monorepo 的检出副本，它的 compose 文件提到了 `cassandra:5.0` 和 `elasticsearch:8.11.0`。这就指向了下一步。

## 第三步：我们提供的模板

Rediacc 提供现成的应用模板：每个应用一个 `docker-compose.yaml` 加一个 Rediaccfile。不是我们运营的服务器也可以部署它们。所以模板里只要有 Java 镜像，所有 CPU 符合条件的客户就都有暴露风险，哪怕我们自己的服务器是干净的。

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

有四个模板会启动 JVM。其中两个的镜像仓库配置里已经写明了 JDK，另外两个没有，所以我们把每个镜像各跑一次来确认：

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| 模板 | 模板里的标签 | 现在里面的 JDK | 状态 |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | 上游已修复，11 月 20 日重新构建 |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | 上游已修复，11 月 20 日重新构建 |
| Solr | `solr:9-slim` | 17.0.21.1+2 | 上游已修复，11 月 20 日重新构建 |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1（自带） | **有漏洞**，Elastic 还没有修复版本 |

![固定与浮动的对比：固定的 Elasticsearch 镜像保留了 2023 年的 JDK，浮动标签已用修复后的版本重新构建](/img/blog-java4shell-pinned-vs-floating.svg)

## 关于固定版本的教训，修订版

上一篇文章最后说“固定确切的标签”。这次行动给这条规则加了一个脚注。

对于我们自己运行、并有计划升级的应用，固定版本是对的。固定之后运行的版本一目了然，而浮动标签可能已经指向了修复版本，服务器却还在跑旧镜像，因为 `docker compose up -d` 不会去拉取本地已有的镜像。

对于别人从零部署的模板，情况正好相反。三个浮动的大版本标签（`5.0`、`5-community`、`9-slim`）在修复发布三天后就用上了打过补丁的 JDK，我们这边什么都没改。唯一一个确切的固定版本 `8.11.0`，把 Elasticsearch 冻在了 2023 年 11 月构建的镜像上，这个标签以后再怎么重新构建，也修不了里面的 JDK。

所以我们保留的规则有两半。生产应用用确切的标签，并有计划地升级。模板也要固定版本，因为 Elasticsearch 和 Kibana 必须运行同一个版本，但现在每个模板里的固定版本都登记在我们的固定版本清单里，新鲜度检查会标出落后的版本，而不是任由它放上三年。

## 第四步：缓解措施，在真实节点上验证

Elastic 已宣布，修复会以自带 JDK 更新的形式，随即将发布的 8.19.26、9.4.10、9.5.7 和 9.6.0 提供。在这些版本出来之前，官方的建议是使用 JVM flag。在模板里，只是在 `ES_JAVA_OPTS` 里多加一个参数：

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![这个 flag 改变了什么：JIT 保留普通的 Java 解码器，而不是使用 AVX-512 内建实现](/img/blog-java4shell-intrinsic-flag.svg)

compose 文件里的一个 flag，在 JVM 确认之前只是一个声明。我们检查了两次。第一次，直接检查自带的 JDK，分别带上和不带这个 flag：

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

第二次，用模板里的选项启动一个真实的单节点集群。它状态为 green，而且它自己的 API 在 JVM 参数里列出了这个 flag：

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## 出了什么问题

**CPU 检查差点决定了结论。** 它是最显眼的前提条件，一条命令就能查完，而且结果是“已暴露”。只有第二项检查，也就是找真正的 JVM，才把一场半夜的紧急处理变成了一次模板修改。

**一套测试在不该运行的地方运行了。** 为了验证模板的修改，我们在工作站上跑了模板包的生命周期测试。这套测试是给有授权的 Rediacc 仓库用的，不是给裸 Docker 主机用的，它花了十多分钟去启动其他模板。它还暴露出另一个不相关的模板会把生成的密钥写进自己的源码目录，这种文件没人想提交进 commit。那个模板现在把密钥写到源码树之外，而且如果没有所需的仓库，测试套件会拒绝启动。

**没有可 fork 的东西。** 我们惯用的安全步骤，也就是在任何改动之前先 fork 生产仓库，这次没有对象。改动在 git 里的一个模板文件中，所以安全网是一个可审查的 commit 和一次真实的启动测试，而不是快照。

## 各种选择，以及理由

| 我们可选的做法 | 我们的选择 | 原因 |
|---|---|---|
| 把 CPU 检查当作结论 | 探测是否真有 JVM | CPU 说已暴露，但没有 JVM 就没有可利用的东西。 |
| 相信为空的探测结果 | 跑一个必须能找到东西的对照 | 探测本身坏了得到的空结果，和干净的服务器看起来一模一样。 |
| 从镜像仓库读取 JDK 版本 | 把每个镜像各跑一次 | 四个镜像里有两个没有在配置里记录 JDK 版本。 |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | 范围更窄：只关闭一个例程，而不是所有 AVX-512 加速，而且 ARM 上的 JVM 仍能启动。 |
| 现在就把 Elasticsearch 升到最新的 8.19 | 保持 8.11.0，加上 flag，等修复版本发布后再升级 | 现在已发布的最新版本仍然自带受影响的 JDK，而且 Kibana 必须同步升级。 |
| 到处都用确切的固定版本 | 确切的固定版本，加上对每个模板固定版本的新鲜度检查 | 没有告警的固定版本冻住了 2023 年的 JDK，检查保留了固定，又加上了告警。 |

## 我们一直保留的检查清单

1. 检查每一个前提条件，而不是只看第一个匹配的。
2. 查找运行时本身（`java`、`libjvm.so`），而不只是产品名称。
3. 每一个为空的探测都用对照来证明。
4. 排查我们提供的东西，而不只是我们运行的东西。
5. 读取镜像里面的版本，配置里没写时就把镜像跑起来看。
6. 优先选择范围最窄的缓解措施，并在运行的进程里确认它生效。
7. 跟踪厂商的修复版本，发布后撤掉缓解措施。

和上一次一样，这次的工作由 AI 智能体（Claude Code）通过 `rdc` 完成，生产环境的访问权限由运维人员在会话开始前授予。这一次生产环境完全没有改动：服务器上的每一步都是读取，唯一的修复进了模板，经过 git，并有一次真实的测试作为保证。
