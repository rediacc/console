---
title: "Kubernetes"
description: "以 Rediacc 的仓库理念运行 Kubernetes：将一个正在运行的集群（包括其数据）以较短的切换时间 fork 或迁移到另一台机器或数据中心。"
category: "Guides"
tags:
  - containers
  - migration
order: 6
language: zh
sourceHash: "22eef465dfd46ccf"
sourceCommit: "4401262fffbf29b9480dee8ecd209013e4b87f60"
---

# Kubernetes

Rediacc 将 Kubernetes 引入产品，同时不放弃平台其余部分所依赖的仓库理念。其差异化主张很直接：您可以**将一个正在运行的集群（包括其数据）以较短的切换时间 fork 或迁移到另一台机器或数据中心**。这不是停机后恢复式的迁移，也不是零停机的魔法。工作负载会在目标端重启，切换时间以秒计，数据会随之一同迁移。

Kubernetes 运行在经认证的 Kubernetes 发行版 [k3s](https://k3s.io/) 之上，该发行版以与其他服务端二进制文件相同的方式内嵌于 renet 中。

## 对象模型

Rediacc 反转了通常"集群包裹一切"的图景，使仓库理念依然适用：

- **集群就是容器。** 一台机器可以承载 Docker 仓库（不变）和/或集群。单机上的单节点集群在集群这一层保留了"一个文件搬动整个系统"的特性。集群状态（k3s 数据目录：其内嵌数据存储和 containerd）存储在由数据存储支持的写时复制镜像文件中，每个节点一个，k3s 的 `--data-dir` 绑定在镜像挂载点内部。
- **Kubernetes 仓库就是一个命名空间。** `rdc repo create <repo> -m <name>` 创建一个仓库，其运行时归属为该集群内的 Kubernetes 命名空间 `<repo>`。
- **持久卷是独立的写时复制单元。** PV 是 Ceph 上的 RBD 镜像，或在本地后端通过 renet 本地 PV 供应器提供的小型数据存储镜像文件。它们绝不是单一不透明集群镜像内部的目录：内部文件系统没有 reflink，因此独立的按仓库 fork 需要独立的 PV 镜像。

正是这种拆分使得两个承诺能够同时在物理上实现：**始终写时复制的命名空间 fork**（每个仓库的数据独立克隆）和**整集群的可移植性**（集群镜像加上每个 PV 镜像一起迁移）。

| 概念 | Docker 仓库 | Kubernetes 仓库 |
|---|---|---|
| 运行时归属 | 隔离的 Docker 守护进程 | 集群中的命名空间 |
| 注入的环境变量 | `DOCKER_HOST` | `KUBECONFIG` |
| 部署包装器 | `renet compose` | `renet kube` |
| 数据单元 | 一个 LUKS 镜像 | 集群镜像加每个 PV 的镜像 |
| fork 单元 | 仓库镜像 | 命名空间加其 PV 克隆 |
| 整体克隆 | （仓库本身就是那个"地方"） | `rdc cluster fork` / `rdc cluster migrate` |

## 声明并创建集群

集群是私有网络上一组命名的节点池。先在配置中声明，再进行配置（provision）。

```bash
# 声明一个带有节点池的集群（尚未实际配置任何资源）
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# 配置节点池成员，在每个成员上引导 renet，安装组件（先安装 Ceph）
rdc cluster create prod
```

节点池角色包括 `ceph`、`k8s-server`、`k8s-agent` 和 `hyperconverged`（需显式启用，因为 Ceph 的内存目标和 kubelet 的驱逐阈值会争抢同一份内存）。每个节点池以按池的规格和磁盘参数承载硬件的不对称性：磁盘密集型的 Ceph 节点，CPU/内存密集型的 Kubernetes 节点。

节点池成员会以 `<cluster>-<pool>-<n>` 的形式在 `resources.machines` 中具体化，并带有反向引用，因此**所有现有的 `-m` 命令都能在它们上面运行**：`rdc machine status`、`rdc term connect`、仓库命令和备份策略都将集群节点视为普通机器。

云服务提供商通过 [OpenTofu](https://opentofu.org/) 进行配置，遵循与 `rdc machine provision` 相同的 `ProviderMapping` 注册表，并扩展了私有网络块（VLAN 或 VPC、要设置的 MTU、私有网卡命名）。本地 KVM 是通过 `rdc ops` 始终可用的测试路径。

```bash
# 查看集群
rdc cluster status                 # 列出所有集群
rdc cluster status prod     # 查看单个集群的完整配置

# 扩容或缩容节点池（添加/移除机器，加入/清空节点）
rdc cluster scale prod --pool k8s --count 5


# 拆除已配置的成员并从配置中移除集群
rdc cluster destroy prod
```

### 获取 kubeconfig

kubeconfig 从不存储在您的配置文件中（它体积较大且会轮换）。它按需通过 SSH 获取，并以 `0600` 权限缓存在本地，遵循与 OpenTofu 工作目录和证书缓存相同的旁路状态模式。

```bash
rdc cluster kubeconfig prod
# 输出：export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetes 仓库

目标标志决定运行时。没有类型标志。

```bash
# Docker 仓库（不变）：机器上一个隔离的 Docker 守护进程
rdc repo create shop -m server-1 --size 10G

# Kubernetes 仓库：集群内 "shop" 命名空间加其存储
rdc repo create shop --datastore prod --size 10G
```

仓库动词是仓库范围工作的统一接口。通过目标解析漏斗，几乎整个仓库命令集都变得支持集群：`fork`、`migrate`、`push`、`pull`、`up`、`down`、`resize`、`diff`、`commit`、`branch`、`checkout`、`merge`、`trim`、`cat`、`mount`、`sync`、`list`、`status` 和 `log` 都接受 `--cluster`。集群目标会解析为其控制节点，加上固定到该仓库命名空间的 KUBECONFIG 上下文，这与将机器解析为 `DOCKER_HOST` 加一个工作目录是类似的。

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # 导出 KUBECONFIG，然后直接使用 kubectl
```

集群节点同样会在 `resources.machines` 中具体化，因此您可以用普通的 `rdc term connect <cluster>-<pool>-<n>` 通过 SSH 连接到特定节点。

### 双运行时 Rediaccfile

Docker 与 Kubernetes 之间的可移植性依赖于一种约定，而非自动的清单转换。一个在相同的 `up()` 和 `down()` 函数下同时提供 `renet compose` 路径和 `renet kube` 路径的仓库，可以在两个方向自由迁移，因为数据目录的约定是相同的。renet 在机器目标上注入 `DOCKER_HOST`，在集群目标上注入 `KUBECONFIG`；`up()` 读取设置的是哪一个，并据此分派。

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetes 运行时
  else
    renet compose -- up -d             # Docker 运行时
  fi
}
```

缺少目标运行时的仓库会在数据传输阶段**之后**收到明确的拒绝：镜像会被迁移，而部署步骤会告知该仓库未声明 Kubernetes（或 Docker）路径，而不是破坏状态。

## Fork 一个仓库

在 Kubernetes 仓库上执行 `rdc repo fork` 总是复制数据，且总是瞬间完成。没有 `--full` 标志，也没有其他变体。

```bash
rdc repo fork shop --tag joseph
```

这会在同一集群中创建命名空间 `shop-joseph`，以写时复制的方式克隆每个卷（Ceph 上是 RBD 克隆，本地后端上是 PV 镜像文件的 reflink），并在那里部署工作负载。fork 的 URL 在父级的通配符证书下立即生效，因此不会签发新的证书或 DNS 记录。

目标升级：

- `--to-cluster <name>` fork 到另一个已存在的集群。同一 Ceph 后端：RBD 克隆保持写时复制。不同后端：push 机制会迁移镜像。
- `--provider <p>` 会先配置一个新集群，其节点池规格默认镜像源集群的形态（标志可覆盖）。

在 KVM 测试实验室中实测，命名空间 fork 大约在一到五秒内完成，父级工作负载不受影响，两个命名空间独立演化。

## Fork 或迁移整个集群

整集群操作位于 `rdc cluster` 组中，因为它们作用于一个不同的对象（包含其所有仓库的整个地方），无法通过接受单个仓库名称的命令来表达。这是旗舰级的故事。

```bash
# 将整个集群（包括其仓库的数据）克隆到一个新集群
rdc cluster fork prod --to spare --tag staging

# 将整个集群（包括其仓库的数据）迁移到另一台机器或数据中心
rdc cluster migrate prod --to spare
```

两者都会协调集群镜像加上每个仓库 PV 镜像的写时复制，然后重写节点身份，使克隆出的或迁移后的集群在其新地址上健康启动。由于 k3s 将控制平面状态保存在其内嵌数据存储中，集群镜像本身即是快照：一致性顺序是先控制平面，再 PV，最后是代理节点。

在 KVM 测试实验室中端到端实测的诚实数字：

| 操作 | 作用 | 实测 |
|---|---|---|
| 命名空间 fork | 就地克隆一个仓库的命名空间及其 PV | 约 1-5 秒 |
| 单个 RBD 镜像 fork | 对一个 Ceph 支持的 PV 克隆进行写时复制 | 约 5 秒 |
| 整个 2 节点集群 fork | 排空、reflink 控制平面和代理节点、将身份重写为新 IP，父级不受影响 | 约 46 秒 |
| 跨机器集群迁移 | 热预拷贝加停止并重启的切换 | 约 16 秒切换时间 |

默认的一致性是**崩溃一致且引用完整**：与断电重启相同的语义，这也正是工作负载所看到的。当工作负载的文件系统在拷贝期间被冻结时，可以获得应用一致性快照。这被有意地**不**宣传为零停机。目前没有其他产品提供"fork 一个正在运行的集群及其数据"这一能力；诚实的表述是一次短暂的、经过实测的切换，而不是营销式的绝对宣称。

## 存储：ceph-csi 与持久卷

Ceph 由 renet 的 cephadm 流程在 `ceph` 节点池上配置，**位于**任何 Kubernetes 集群**之外**，集群通过 renet 模板化生成的 ceph-csi 清单来使用它。每个集群实例（以及每次 fork）都会获得自己的 RBD/RADOS 命名空间，这正是按租户隔离的基本单元。存储层位于所有集群之下，因此它同时支撑普通 Docker 仓库和数据存储后端；集群 fork 是在 Kubernetes 之下克隆 RBD 镜像，而不是 fork 其自身的存储后端。

在本地后端（没有 Ceph）上，renet 本地 PV 供应器会为每个 PV 提供数据存储中的一个小型写时复制镜像文件作为支持，在 fork 时通过 reflink 克隆。有关磁盘布局和 renet 命令，请参阅[服务器参考](/en/docs/server-reference)。

## 选择发行版

发行版是一个具有小而真实接口的抽象（安装、加入、kubeconfig、健康检查、升级等等）：

- **k3s** 是默认且唯一内嵌的发行版。它采用 Apache-2.0 许可，经 CNCF 认证，是单个可重定位的二进制文件，其内置的 Traefik 和 ServiceLB 都被禁用，转而使用 Rediacc 代理。它的 `--data-dir` 在启动时绑定，这正是集群 fork 和迁移在镜像挂载路径变化时所需要的。k3s 被标记为 `repoEmbeddable`。
- **external** 是自带 kubeconfig 的模式。只有 `getKubeconfig` 和 `healthcheck` 会执行实际工作；生命周期动词会返回一等的"不适用"结果，而不是错误。
- **RKE2** 是为 FIPS/CIS 客户计划中的第三种后端，不在本次发行范围内。

集群 fork 和迁移会以明确的错误拒绝在非 `repoEmbeddable` 的发行版上运行，而不是破坏状态，因为将集群状态内嵌到数据存储镜像中需要一个在启动时绑定的 data-dir。

## 镜像仓库（Registry）

两个不同的镜像问题，两种工具：

- **上游痛点**（Docker Hub 速率限制、被拒绝的拉取、离线场景）：一个内嵌的 [zot](https://zotregistry.dev/) pull-through 缓存运行在控制节点池上，通过 `sync.onDemand` 对接多个上游（docker.io、ghcr.io、quay.io）。它以与其他二进制文件相同的方式内嵌于 renet 中，并取代了 ops 测试镜像仓库，使得每次运行都会实际使用它。
- **集群内分发**：k3s 内嵌的镜像仓库镜像功能让节点之间可以点对点共享已拉取的镜像。

通过 containerd 的 `certs.d/hosts.toml` 和 k3s 的 `registries.yaml`，接入是透明的且无需重启。集群镜像内部按仓库的 containerd 存储仍然是 fork 和迁移所使用的事实来源；镜像仓库只是面向互联网的缓存，从不是状态本身。

## 网络与 URL

Kubernetes 仓库的 URL 遵循扁平方案，命名空间标识折叠在最左侧标签中，集群作为第二个稳定标签：

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetes 仓库（命名空间 = repo）
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    fork（命名空间 = repo-tag）
```

每个命名空间和每次 fork 都继承父级的通配符证书和 DNS 记录，因此 fork 的 URL 立即生效，只有在创建新集群或新仓库时才会签发新证书。路由器通过轮询集群中带有 `rediacc.*` 注解的 Service 来发现 Kubernetes 服务，这是读取 Docker 标签的 Kubernetes 类比。有关路由模型请参阅[网络](/en/docs/networking)，有关存储后端请参阅[架构](/en/docs/architecture)。

## 归属声明

Rediacc 携带了若干第三方二进制文件（k3s、zot，以及 renet 内嵌的其他组件）。随时可以打印它们的版本号、SPDX 许可证标识符和源码归档 URL：

```bash
rdc credits
rdc credits --licenses    # 随发行版打包的完整 THIRD_PARTY_LICENSES 文本
```
