---
title: "备份目标"
description: "把每个备份策略发送到多个存储,从持有最佳快照的存储恢复,并按目标查看各自的一行状态。"
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: zh
sourceHash: "10ded4035f1e9641"
sourceCommit: "7264926d04c36ba68ec76946fc14565405acd340"
---

# 备份目标

一个备份策略可以写入多个存储。每个目标都是独立的恢复点:它有自己的快照、自己的提交和自己的状态行,所以某个存储失败不会影响其他存储。

所有存储都属于同一个账户。一份 config、一个许可证和一张账单就能覆盖它们。同时登录两个账户的机器仍然会被拒绝,因为多个目标意味着同一个账户内的多个存储。

## 存储

存储是账户服务器代表机器写入的存储桶。每个订阅从第一天起就有一个名为 `home` 的存储,也就是备份命令一直在使用的托管存储。没有指定存储的目标会写入 `home`。

除此之外,还可以注册两种类型。

| 类型 | 说明 | 注册所需信息 |
|------|------|--------------|
| `hosted-r2` | 第二个托管区域,从部署提供的区域中选择 | 一个 ID 和区域。无需凭据 |
| `customer-s3` | 客户自己运行的存储桶,位于 S3、RustFS 或任何兼容 S3 的服务上 | 一个 ID、HTTPS 端点、存储桶、签名区域(默认 `us-east-1`)、可选的公共端点,以及一对访问密钥 |

机器从不持有客户存储桶的密钥。密钥以密封形式保存在账户服务器上,机器只会为其会话所指定的那一个存储收到短期有效的预签名 URL。

### 注册存储

注册是对账户 API 的调用,而不是 `rdc` 命令。`POST /backups/stores` 注册存储,`GET /backups/stores` 列出已注册的存储,`DELETE /backups/stores/<id>` 停用存储。注册、轮换和停用都需要一个范围为 `backup:manage` 的 API 令牌,该令牌必须由当前的组织所有者或管理员创建,并且每次操作都会被审计。列出存储需要 `backup:read`。

服务器会在接受存储之前先检查它。

- **一致性探测。** 服务器运行托管存储通过的同一套检查。不强制校验和的存储会在注册时被拒绝,而不是等到第一次备份时才发现。
- **删除探测。** 探测还会尝试一次删除。如果存储拒绝删除,则该存储会以禁用清理的状态注册(见下文)。
- **端点规则。** 仅限 HTTPS、端口 443,且不能是内部网络上的端点。
- **存储数量上限。** 每个订阅的存储数量取决于套餐,包含 `home`,不计已停用的存储。

| 套餐 | 存储数量 |
|------|----------|
| Free | 1 |
| Community | 2 |
| Professional | 3 |
| Business | 5 |
| Enterprise | 10 |

注册一个已存在的 ID 只会轮换其凭据,其他都不变,并且会重新运行探测。凭据失效的存储会在第一次授权被拒绝时被标记为已暂停。`GET /backups/stores` 会显示端点、存储桶和密钥 ID 的最后几个字符,绝不会显示密钥本身。

只要还有已启用的目标指向某个存储,就不能停用它,而且 `home` 不能被停用。

## 为目标指定存储

目标通过 `--target` 指定存储,它需要和 `--destination` 一起使用:

```bash
# Write to the home store (the default).
rdc backup strategy set daily --destination primary

# Write to a registered store.
rdc backup strategy set daily --destination offsite --target office-rustfs
```

| 选项 | 说明 |
|------|------|
| `--destination <name>` | 要创建或修改的目标 |
| `--target <storeId>` | 目标写入的已注册存储 ID(默认 `home`)。需要 `--destination` |

同一个策略中两个已启用的目标不能指向同一个存储,指向未注册存储的目标会被拒绝,并附上已注册 ID 的列表。

每次计划运行会为每个已启用的目标各拍一个快照,顺序与目标的声明顺序一致,各自有独立的带宽上限。每个快照都是新的写时复制 reflink,因此每个快照本身都是一个一致的时间点。某个目标失败不会导致跳过下一个目标。只要有任何目标失败,该单元仍会以非零状态退出,这样 systemd 和漏跑检查就能看到失败。

## 从存储恢复

`rdc backup restore`、`rdc backup restore --path`、`rdc backup browse --at` 和 `rdc backup download --store` 都接受 `--from <storeId>`:

```bash
# The best store, chosen automatically.
rdc backup restore my-app --as my-app-copy --at <snapshot-id>

# One named store.
rdc backup restore my-app --as my-app-copy --at <snapshot-id> --from office-rustfs
```

不带 `--from` 时,CLI 会向账户服务器询问哪些存储持有该仓库的血统,并排序:最新快照通过了最近一次验证的存储排在最前,CLI 按这个顺序依次尝试。没有快照的存储会被跳过。如果无法读取排序,恢复会使用 `home` 并给出提示。

不带 `--from` 时,`backup restore`、`restore --path`、`browse --at` 和 `download --store` 从该排序的第一个存储开始,当故障出在存储一侧时转到下一个存储,例如服务器错误、授权或会话被拒绝,或者端点没有响应。每个命令都会说明由哪个存储提供了服务。快照本身出现问题时,它们都不会回退。缺失、已过期或已损坏的快照在每个存储中看起来都一样,所以会直接显示错误。带 `--from` 的命令只读取该存储,绝不回退。

不带 `--from` 给出的快照 ID,会在该血统的所有存储中查找。

## 各目标的状态

`rdc backup status` 在计划表旁边为每个目标打印一行:

| 列 | 含义 |
|----|------|
| Store | 目标写入的存储 ID |
| Last run | 该存储最近一次运行的结束时间 |
| Result | 该次运行的结果 |
| Newest snapshot | 该存储持有的最新快照 |
| Verify | 该存储最近一次验证的结果 |
| Clean-up | `enabled`,或附带原因的已禁用 |

账户无法报告状态的存储,其各列显示 `-`。漏跑检查按存储进行,所以停止接收备份的存储会触发自己的告警,而其他存储保持正常。

## 哪些计入配额

托管存储,即 `home` 和任何第二个区域,按物理上实际存储的唯一字节数计量,这些字节计入同一个套餐配额。`rdc backup usage` 会显示它们。

客户存储桶的字节不由 Rediacc 存储,也不计入配额。账户为它保存的元数据(清单行、验证运行和索引对象)的计量方式与托管存储相同。

## 禁用清理的存储

拒绝删除的存储会保留所有对象。保留策略和垃圾回收永远不会从中删除任何内容。快照过期时,清扫会在账户中将其标记为已过期,不再提供给恢复使用,并把它的对象留在存储桶中。

`rdc backup status` 和备份健康摘要会把该存储报告为已禁用清理。存储桶会持续增长,直到重新注册同一个 ID 并使用有删除权限的密钥来补充删除凭据。
