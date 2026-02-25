---
title: 监控
description: 监控机器健康状况、容器、服务、仓库，并运行诊断。
category: Guides
order: 9
language: zh
sourceHash: 5a0f43834cb143a2
---

# 监控

Rediacc 提供内置的监控命令，用于检查机器健康状况、运行中的容器、服务、仓库状态和系统诊断。

## 机器健康状况

获取机器的综合健康报告：

```bash
rdc machine health server-1
```

报告内容：
- **System**：运行时间、磁盘使用率、数据存储使用率
- **容器**：运行中、健康和不健康的容器数量
- **存储**：SMART 健康状态
- **问题**：已识别的问题

使用 `--output json` 获取机器可读的输出。

## 列出容器

查看机器上所有仓库中运行的全部容器：

```bash
rdc machine containers server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 容器名称 |
| Status | 运行时间或退出原因 |
| State | 运行中、已退出等 |
| Health | 健康、不健康、无 |
| CPU | CPU 使用百分比 |
| Memory | 内存使用量 / 限制 |
| Repository | 容器所属的仓库 |

选项：
- `--health-check` — 对容器执行主动健康检查
- `--output json` — 机器可读的 JSON 输出

## 列出服务

查看机器上与 Rediacc 相关的 systemd 服务：

```bash
rdc machine services server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 服务名称 |
| State | 活跃、非活跃、失败 |
| Sub-state | 运行中、已停止等 |
| Restarts | 重启次数 |
| Memory | 服务内存使用量 |
| Repository | 关联的仓库 |

选项：
- `--stability-check` — 标记不稳定的服务（失败、超过 3 次重启、自动重启）
- `--output json` — 机器可读的 JSON 输出

## 列出仓库

查看机器上的仓库及详细统计信息：

```bash
rdc machine repos server-1
```

| 列名 | 描述 |
|--------|-------------|
| Name | 仓库名称 |
| Size | 磁盘镜像大小 |
| Mount | 已挂载或未挂载 |
| Docker | Docker daemon 运行中或已停止 |
| Containers | 容器数量 |
| Disk Usage | 仓库内的实际磁盘使用量 |
| Modified | 最后修改时间 |

选项：
- `--search <text>` — 按名称或挂载路径筛选
- `--output json` — 机器可读的 JSON 输出

## Vault 状态

获取机器的完整概览，包括部署信息：

```bash
rdc machine vault-status server-1
```

提供的信息：
- 主机名和运行时间
- 内存、磁盘和数据存储使用情况
- 仓库总数、已挂载数量和运行中的 Docker 数量
- 每个仓库的详细信息

使用 `--output json` 获取机器可读的输出。

## 测试连接

> **仅限云适配器。** 在本地模式下，使用 `rdc term server-1 -c "hostname"` 验证连接。

验证与机器的 SSH 连接：

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

报告内容：
- 连接状态（成功/失败）
- 使用的认证方式
- SSH 密钥配置
- 公钥部署状态
- Known hosts 条目

选项：
- `--port <number>` — SSH 端口（默认：22）
- `--save -m server-1` — 将已验证的主机密钥保存到机器配置中

## 诊断 (doctor)

对 Rediacc 环境运行全面的诊断检查：

```bash
rdc doctor
```

| 类别 | 检查项 |
|----------|--------|
| **环境** | Node.js 版本、CLI 版本、SEA 模式、Go 安装、Docker 可用性 |
| **Renet** | 二进制文件位置、版本、CRIU、rsync、SEA 嵌入式资源 |
| **配置** | 活跃配置、适配器、机器、SSH 密钥 |
| **虚拟化** | 检查系统是否可以运行本地虚拟机（`rdc ops`） |

每项检查报告 **OK**、**警告** 或 **错误**。在排查任何问题时，请将此作为第一步。

退出代码：`0` = 全部通过，`1` = 有警告，`2` = 有错误。
