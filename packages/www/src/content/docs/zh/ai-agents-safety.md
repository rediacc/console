---
title: AI 智能体安全与防护机制
description: >-
  Rediacc 如何防止 AI 编程助手泄露密钥、覆盖凭据或提升权限。所有入口共用一个
  决策，主动授权与策略上限缺一不可，另有知识门控、脱敏和哈希链式审计日志。
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: zh
sourceHash: "90603fac1c7635d4"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
---

当 Claude Code、Cursor、Gemini CLI、Copilot CLI 或其他任何 AI 编程助手驱动 `rdc` 时，CLI 对其的处理方式与坐在键盘前的人类不同。本页说明智能体能做什么、不能做什么，以及即使智能体试图绕过防护机制，这些机制依然有效的原因。

## 快速参考：智能体能做和不能做的事

| 操作 | 智能体默认行为 | 如何为特定用途解锁 |
|---|---|---|
| `rdc config show`（已脱敏） | ✅ allowed |  |
| `rdc config field get --pointer <pointer>`（脱敏占位符或摘要） | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（公开字段） | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（敏感字段，**提供正确的 `--current`**） | ✅ allowed |  |
| `rdc config edit --dump --redacted`（已脱敏的 JSONC） | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（敏感字段，无 `--current`） | 🔴 refused | 提供 `--current "<旧值>"` |
| `rdc repo secret set <repo> --rotate-secret`（不带 `--current` 的轮换） | 🔴 refused | 提供 `--current`，或由人类在终端中执行轮换 |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | 改用 `--digest` |
| `rdc config show --reveal` | 🔴 refused | 使用不带参数的 `rdc config show` |
| `rdc config edit`（交互式编辑器） | 🔴 refused，无覆盖方式 | 用 `--dump --redacted` 查看，用 `config field set --current` 修改单个字段 |
| `rdc config edit --apply <file>` | 🔴 refused，无覆盖方式 | 同上；整份文档的修改由终端前的人类应用 |
| `rdc config edit --reveal` | 🔴 refused，无覆盖方式 | 同上 |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | 由人类在交互式终端中运行 |
| 修改 grand（生产）仓库 | 🔴 refused | 在允许修改 grand 仓库的策略范围内，由人类针对该仓库主动授权（[见下文](#one-decision-opt-in-and-policy-ceiling)） |
| 集群或数据存储生命周期操作 | 🔴 refused | 在允许集群操作的策略范围内，由人类针对该集群主动授权 |
| `rdc term connect <machine>`（直接 SSH 到机器） | 🔴 refused | 先 fork 一个仓库，再连接到 fork |

每次对智能体的拒绝都会连同 `outcome: refused` 和原因写入审计日志。整份配置文档的编辑对智能体完全没有可用路径：配置中保存着每个仓库的 LUKS 凭据，能够改写配置的智能体也就能删掉某个凭据，而没有它加密卷就无法打开。

## 智能体的检测方式

当以下任一条件为真时，CLI 将进程视为智能体：

- `REDIACC_AGENT`、`CLAUDECODE`、`GEMINI_CLI`、`COPILOT_CLI` 之一设置为 `"1"`，或 `CURSOR_TRACE_ID` 被设置（任何值）。
- 在 Linux 上：祖先链中任何父进程的环境变量中包含上述变量之一（通过 `/proc/<pid>/environ`）。即使智能体使用 `env -i` 或包装脚本删除了自己的变量，父进程链仍会告知 CLI 是谁启动了它。

检测每个进程只运行一次并被缓存，无法禁用。远程 MCP 授权会在执行端把它的调用标记为智能体调用，无需任何检测。

## 一个决策：主动授权与策略上限缺一不可

每个运行 `rdc` 命令的入口（CLI、本地 MCP 服务器、远程 MCP 服务器、`rdc --proxy` 和 Web 控制台）都向同一个决策函数发起询问，因此它们拒绝和允许的内容完全一致。该函数应用两个条件，只有两者都满足时智能体才能行动：

1. **策略上限。** 组织策略经团队策略收窄后，决定调用方可以使用哪些命令、机器和仓库，以及是否允许修改 grand 仓库（`allowGrandRepos`）和执行集群操作（`allowClusterOps`）。没有策略记录的配置会回退到按角色设定的默认值：所有者和管理员可以操作，成员不可以。策略是一条独立的密封记录，只有所有者和管理员可以写入（[安全模型](/zh/docs/security-model#policy)）；任何智能体和任何 CLI 命令都无法编辑它。
2. **人类的主动授权。** 即使在上限之内，智能体仍然需要人类指明它可以修改的 grand 仓库或集群：
   - **本地智能体**（CLI 和本地 MCP）：人类在启动智能体之前，先在终端中导出 `REDIACC_ALLOW_GRAND_REPO`（仓库名，或 `*`）或 `REDIACC_ALLOW_CLUSTER_OPS`（集群名，或 `*`）。CLI 会检查进程祖先，因此智能体在会话中途设置的变量不算数（[各操作系统如何验证](#how-a-local-opt-in-is-verified-on-each-os)）。
   - **远程智能体**（远程 MCP）：主动授权是人类在账户界面中创建的授权的一部分（[远程服务器](/zh/docs/ai-agents-mcp#remote-server)）。

主动授权永远不会放宽上限：被策略关闭的仓库，无论环境或授权如何声明，仍然保持关闭。fork 不需要主动授权。CLI 无法识别的仓库按 grand 处理。

**破坏性变更会先询问。** 当智能体被允许对 grand 仓库做破坏性变更（例如 `repo delete`）时，返回的结果是 `needs_confirmation`。MCP 客户端会向用户显示确认提示；没有提示功能的客户端会得到一个 `confirm` 参数，在询问用户后回传。在 CLI 中，由人类加上 `--confirm-grand <repo>` 重新运行命令。

每个结果都带有稳定的代码（`POLICY_DENIED`、`GRAND_REPO_DENIED`、`CLUSTER_OPS_DENIED`、`AGENT_OPT_IN_MISSING`、`FORK_BLOCKED`、`AGENT_BLOCKED`、`CONFIRMATION_REQUIRED`），脚本或智能体据此代码而不是消息文本来分支处理（[JSON 输出](/zh/docs/ai-agents-json-output)）。

## 知识门控模型

敏感变更遵循 `passwd(1)` 惯例：要修改一个密钥，必须证明你已经知道它。**对人类和智能体都是对称的**。两者都需要经过同一道门控。没有"我在键盘前"的绕过方式。

- 想要轮换存储在 `/credentials/cfDnsApiToken` 的 API 令牌？
- CLI 询问："当前值是什么？"
- 智能体（或人类）通过 `--current "$OLD"` 提供明文。CLI 对 `$OLD` 进行 SHA-256 哈希，并与当前存储值的摘要进行比较。匹配 → 写入通过。不匹配 → 拒绝，记录审计。
- 若要在不验证旧值的情况下轮换，请传入 `--rotate-secret`（与 `--current` 互斥）。它会作为轮换被明确记入审计，并且只对交互式终端前的人类有效：智能体，或 stdin 上没有终端的脚本，仍然需要 `--current`。

该模型关闭了三个攻击面：

1. **静默轮换**：没有预先访问 `$OLD` 的调用者（智能体或人类）无法用自己选择的值替换它。
2. **探测式泄露**：摘要响应从不包含明文；即使审计日志被攻破，也只显示 `expected abc12345…, got deadbeef…`，而不是底层值。
3. **意外覆盖生产配置**：每次都需要明确的 `--current`，即使在 TTY 中也是如此。可以捕获"我本来想设置 STRIPE_TEST，但我在生产 shell 中"这类错误。

### 结构化的后续操作提示

当前提条件失败时，JSON 信封（`--output json`）会携带一个结构化的 `errors[].next` 字段，准确地告诉智能体建议人类执行什么操作：

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**智能体应当把 `next.options[].run` 原样转交给人类，而不是自己编造命令。** 这样可以避免智能体捏造出一条不存在的命令，也让操作者始终掌控真正执行的动作。轮换选项是留给人类在终端中运行的，对智能体本身则会被拒绝。

### 实际示例

```bash
# 获取脱敏占位符的短摘要（对智能体安全）。
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 尝试无证明地覆盖：拒绝。
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# 提供当前明文：允许。
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

如果智能体从未拥有 `$OLD_CF_TOKEN`，它就无法满足前提条件，轮换会被拒绝。知道该值的人仍然可以完成：在自己的 shell 中传入 `--current`，或在交互式终端中使用 `rdc config field rotate`。

## 默认脱敏

每个读取敏感状态的 `rdc` 命令（`config show`、`config field get`、`config machine list`、`config edit --dump --redacted`）对密钥字段返回**脱敏占位符**而非明文：

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

占位符的 8 位十六进制后缀是 `sha256(canonicalize(value))` 的前 8 个字符：足以一眼区分两个不同的值，但不足以逆向推导。智能体可以使用占位符跟踪某个值是否发生了变化，而无需查看该值。

`--reveal` 为交互式 TTY 上的人类取消脱敏。智能体无论 TTY 状态如何都会被拒绝。每次授予都会写入 `reveal_granted` 审计条目；每次拒绝都会写入 `refused` 条目，并附带操作者的智能体信号。

## 各操作系统如何验证本地主动授权

`REDIACC_ALLOW_GRAND_REPO` 和 `REDIACC_ALLOW_CLUSTER_OPS` 都依赖祖先验证来证明主动授权是由人类设置的，而不是由智能体注入的。验证在 Linux、macOS 和 Windows 上都能工作，但它读取的凭证因平台而异，保证的强度也不同：

| 平台 | 证人 | 强度 |
|---|---|---|
| Linux | 祖先链中每个进程的 `/proc/<pid>/environ` | exec 时快照，由内核提供。进程无法逆向修改其启动时的环境。 |
| macOS | `kern.procargs2` sysctl，由随 `rdc` 内附的小型助手读取 | 与 Linux 相同的 exec 时快照属性。对自己的进程不需要 root 权限即可读取。 |
| Windows | 每个祖先进程的实时环境块（PEB），由同一助手读取，并带有 PID 重用保护 | 较弱：Windows 没有保存 exec 时快照，因此检查读取当前内存。祖先进程仍无法被智能体通常运行的任何东西改写，但证人不像 Linux 和 macOS 那样由内核冻结。 |

在 macOS 和 Windows 上，CLI 会启动其内置的 `renet` 二进制文件来读取；该辅助程序报告每个祖先进程携带了哪些受监视的变量，所有决策逻辑仍留在 CLI 中。如果辅助程序缺失、版本过旧或因任何原因失败，CLI 无法验证主动授权，并会**安全地失败关闭**：主动授权被拒绝，错误信息说明的是验证不可用，而不是有什么地方做错了。正常的安装不会出现这条信息；重新安装 `rdc` 即可恢复辅助程序。

各平台上始终成立的一点：主动授权必须在智能体进程启动时就已存在于它的环境中。先在终端中导出，再启动智能体。在会话中途设置该变量的智能体会被拒绝。

## 审计日志

每次变更、每次拒绝、每次 `--reveal` 授予都会向 `~/.config/rediacc/audit.log.jsonl`（模式 `0600`，10 MB 时轮换）写入一行 JSONL。每行都经过哈希链接：其 `prevHash` 字段为 `sha256("<上一行>")`。篡改任何一行都会破坏此后所有行的链。

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### 检查

```bash
# 列出最近的条目
rdc config audit log --since 24h

# 按指针 glob 过滤
rdc config audit log --path '/credentials/*'

# 仅显示智能体发起的条目
rdc config audit log --actor agent

# 实时流式传输新条目（Ctrl+C 停止）
rdc config audit tail

# 验证哈希链是否完整
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   或
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### 审计日志中绝不会出现的内容

- 明文密钥值
- 密码短语、令牌、SSH 密钥
- `--current` 前提条件不匹配时的新旧值（仅 8 位摘要前缀）

该日志可安全地与安全审计人员共享，或附在错误报告中。

## 行为模型的局限性

智能体防护机制是**行为性的，而非密码学性的**。在与配置文件相同的 UID 下运行的有意或经过指示的智能体，始终可以执行 `cat ~/.config/rediacc/rediacc.json` 并读取明文，因为该文件对进程是可读的。

如需真正的密码学强制，请使用[加密配置存储](/zh/docs/config-storage)：密钥存储在服务器端，每个敏感字段携带字段级别的 HMAC 承诺，账户 Worker 会拒绝 `--current` 前提条件与存储哈希不匹配的写入。服务器永远不会看到明文（零知识），但门控仍然被强制执行。

本地文件：简单的路也是安全的。远程存储：困难的路也是加密困难的。

## Rediacc 不隔离的内容

本页所述的智能体防护机制保护的是 Rediacc 自身的基础设施：配置文件、每个仓库的 Docker 守护进程、LUKS 加密的仓库数据、限定范围的 SSH 沙箱。它们并不保护你的仓库为之保存凭据的外部服务。

仓库 fork 是父仓库卷的 BTRFS reflink。父仓库磁盘上的所有内容在 fork 中字节相同：代码、数据以及 `.env` 文件都一样。如果你的仓库包含 `STRIPE_LIVE_KEY`、`AWS_ACCESS_KEY_ID`、Railway API 令牌或任何其他第三方服务的长期凭据，fork 都会继承它们。在 fork 沙箱中操作的智能体可以读取该文件、外泄该值，或使用它调用第三方 API。第三方服务无从得知该调用是来自 fork 而不是生产环境。

这就是责任共担的边界：

| 边界 | 责任方 |
|---|---|
| 仓库数据、挂载命名空间、Docker 范围、智能体防护、审计日志、部署时密钥注入 | Rediacc |
| 使用这些密钥的应用代码，以及在构建时烘烤到镜像中的任何凭据 | 仓库开发者 |

主要的缓解措施是内置的：**[每个仓库的密钥](/zh/docs/repositories#secrets)** 存储在与加密仓库镜像不同的平面中，不会在 fork 边界之间复制。fork 的容器启动时会获得一个空的密钥映射，并以不同的外部主体身份自我标识。使用 `rdc repo secret set` 设置它们（环境变量模式用于 compose 插值，文件模式用于 tmpfs `secrets:` 块）。变更门控是对称的。人类和智能体都必须提供 `--current`（passwd 风格的前提条件）来覆盖或删除现有值；`--rotate-secret`（审计轮换）是终端前人类的替代方式。

**跨仓库隔离是强制执行的。** 仓库 B 中的恶意或不谨慎的 compose 文件无法引用仓库 A 的密钥目录。Renet 的 compose 验证器会硬拒绝任何指向当前仓库 `${REDIACC_NETWORK_ID}` 目录之外的 `secrets: file:`、`configs: file:` 或 `env_file:` 路径，而且这个拒绝**不能被 `--unsafe` 覆盖**。纵深防御：围绕 Rediaccfile bash 子进程的 Landlock 沙箱将文件系统读取限制为仅当前网络的密钥目录，因此来自恶意 Rediaccfile 的 `cat /var/run/rediacc/net-<other>/secrets/X` 会在内核层以 EACCES 失败。Docker API 上同样如此：每个仓库的 Docker 套接字由 renet 策略代理提供服务，它会以 `403` 拒绝 `--privileged`、主机 `pid`、`ipc` 和 `uts`、设备请求，以及触及其他仓库运行时或数据的绑定挂载，因此持有 `${DOCKER_SOCKET}` 的容器无法借助该 API 访问其他仓库，被检查的也不仅是 compose 文件。只有运维人员能放宽绑定规则，且仅限指定名称的主机目录，方式是一份 root 所有、任何容器都无法写入的授权。

还有两种额外的模式可以关闭边界情况：

1. **不要在仓库文件系统本身中烘烤生产凭据。** 提交到镜像中的 `.env` 文件，或在 `up()` 期间持久化到卷的凭据，都会被 reflink 到 fork 中。每个仓库的密钥功能只保护你保存在密钥平面中的值。它无法逆向保护已经存在于 LUKS 镜像内的字节。对于现有的具有烘烤 `.env` 文件的仓库，请手动将其提升到每个仓库的密钥功能中。
2. **通过 eBPF 出站过滤限制 fork 的出站网络**，使 fork 仅能访问 localhost 和明确的沙箱端点。Rediacc 的每个仓库的网络隔离是基础；每个 fork 的出站允许列表目前尚未构建，但路径已经打开。

Rediacc 处理部署时注入、跨 fork 隔离和跨仓库隔离。"不要把它烘烤到镜像中"这一半是你的责任。

## 快速方案

### 让智能体处理单个 grand 仓库

```bash
# 以人类身份，在启动智能体之前：
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # 或 cursor、gemini 等
```

智能体现在可以在策略允许修改 grand 仓库的范围内修改 `gitlab`，而不能修改其他任何 grand 仓库。像 `repo delete gitlab` 这样的破坏性变更仍然会要求确认。

### 在不知道旧值的情况下轮换云令牌

```bash
# 以人类身份，在交互式终端中：
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

不带 `--current` 的轮换仍由人类负责。知道当前值的智能体则改用 `rdc config field set --current`。

### 了解智能体被允许访问的字段

```bash
rdc config field list --sensitive --output json
```

返回每个指针模板、其类型（`secret` / `credential` / `pii` / `identifier`），以及是否已提交到服务器端 HMAC 信封。

## 另请参阅

- [AI 智能体集成概览](/zh/docs/ai-agents-overview): 顶层介绍
- [MCP 服务器](/zh/docs/ai-agents-mcp)：本地和远程 MCP、授权及其主动授权
- [安全模型](/zh/docs/security-model)：策略记录以及谁可以写入它
- [Claude Code 配置](/zh/docs/ai-agents-claude-code): 集成模板
- [JSON 输出信封](/zh/docs/ai-agents-json-output): 机器可读响应
- [加密配置存储](/zh/docs/config-storage): 服务器端密码学强制
- [账户安全](/zh/docs/account-security): 运营商安全态势
