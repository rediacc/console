---
title: AI 智能体安全与防护机制
description: >-
  Rediacc CLI 如何防止 AI 编程助手泄露密钥、覆盖凭据或提升权限。知识门控、脱敏处理、祖先验证覆盖以及哈希链接审计日志。
category: Concepts
order: 35
language: zh
sourceHash: "eb4c8dd0389a45a6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
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
| `rdc config edit --dump`（已脱敏的 JSONC） | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>`（敏感字段，无 `--current`） | 🔴 refused | 提供 `--current "<旧值>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | 改用 `--digest` |
| `rdc config show --reveal` | 🔴 refused | 使用不带参数的 `rdc config show` |
| `rdc config edit`（交互式编辑器） | 🔴 refused | 由人类在启动智能体前设置 `REDIACC_ALLOW_CONFIG_EDIT=*` |
| `rdc config edit --apply <file>` | 🔴 refused | 相同的覆盖方式 |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | 相同的覆盖方式；使用交互式确认 |
| `rdc term connect -m <machine>`（直接 SSH 到机器） | 🔴 refused | 先 fork 一个仓库，再连接到 fork |

所有被拒绝的操作都会以 `outcome: refused` 和原因写入审计日志。

## 智能体的检测方式

当以下任一条件为真时，CLI 将进程视为智能体：

- `REDIACC_AGENT`、`CLAUDECODE`、`GEMINI_CLI`、`COPILOT_CLI` 之一设置为 `"1"`，或 `CURSOR_TRACE_ID` 被设置（任何值）。
- 在 Linux 上：祖先链中任何父进程的环境变量中包含上述变量之一（通过 `/proc/<pid>/environ`）。即使智能体使用 `env -i` 或包装脚本删除了自己的变量，父进程链仍会告知 CLI 是谁启动了它。

检测每个进程只运行一次并被缓存。无法禁用。

## 知识门控模型

敏感变更遵循 `passwd(1)` 惯例：要修改一个密钥，必须证明你已经知道它。**对人类和智能体都是对称的**。两者都需要经过同一道门控。没有"我在键盘前"的绕过方式。

- 想要轮换存储在 `/credentials/cfDnsApiToken` 的 API 令牌？
- CLI 询问："当前值是什么？"
- 智能体（或人类）通过 `--current "$OLD"` 提供明文。CLI 对 `$OLD` 进行 SHA-256 哈希，并与当前存储值的摘要进行比较。匹配 → 写入通过。不匹配 → 拒绝，记录审计。
- 要在不验证旧值的情况下轮换，传入 `--rotate-secret`（与 `--current` 互斥）。这会被以轮换方式记录在审计日志中。

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
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**智能体应该将 `next.options[].run` 逐字转达给人类，而不是合成自己的命令。** 这样可以避免"智能体编造了一个不存在的命令"这类失败模式，并保持操作者对实际操作的控制。

### 实际示例

```bash
# 获取脱敏占位符的短摘要（对智能体安全）。
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 尝试无证明地覆盖：拒绝。
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# 提供当前明文：允许。
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

如果智能体从未拥有 `$OLD_CF_TOKEN`，它就无法满足前提条件，轮换被拒绝。拥有它的用户仍然可以通过编辑器或从 shell 传入 `--current` 来完成操作。

## 默认脱敏

每个读取敏感状态的 `rdc` 命令（`config show`、`config field get`、`config machine list`、`config edit --dump`）对密钥字段返回**脱敏占位符**而非明文：

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

占位符的 8 位十六进制后缀是 `sha256(canonicalize(value))` 的前 8 个字符：足以一眼区分两个不同的值，但不足以逆向推导。智能体可以使用占位符跟踪某个值是否发生了变化，而无需查看该值。

`--reveal` 为交互式 TTY 上的人类取消脱敏。智能体无论 TTY 状态如何都会被拒绝。每次授予都会写入 `reveal_granted` 审计条目；每次拒绝都会写入 `refused` 条目，并附带操作者的智能体信号。

## `REDIACC_ALLOW_CONFIG_EDIT` 覆盖

某些操作（交互式编辑器、`--apply`、`field rotate`）是为人类设计的，没有对智能体安全的路径。如果你明确希望智能体执行其中一项，可以设置：

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # 完全绕过
# 或
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# （逗号分隔的范围 glob：每段允许 * 通配符）
```

……智能体会继承它。

**关键细节**：覆盖必须出现在祖先链中智能体**上方**的进程中。如果智能体在自己的环境中设置它（或在其启动的子 shell 中），CLI 会拒绝并告知你：

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

效果：智能体不能通过在会话中途运行 `export REDIACC_ALLOW_CONFIG_EDIT='*'` 来绕过防护机制。只有父进程（在启动智能体之前，你在终端中的操作）才能打开那扇门。

## 平台支持：覆盖如何在各操作系统上验证

`REDIACC_ALLOW_CONFIG_EDIT` 和 `REDIACC_ALLOW_GRAND_REPO` 都依赖祖先验证来证明覆盖是由你设置的，而不是由智能体注入的。验证在 Linux、macOS 和 Windows 上都有效，但它读取的证人因平台而异，强度级别也不同：

| 平台 | 证人 | 强度 |
|---|---|---|
| Linux | 祖先链中每个进程的 `/proc/<pid>/environ` | exec 时快照，由内核提供。进程无法逆向修改其启动时的环境。 |
| macOS | `kern.procargs2` sysctl，由随 `rdc` 内附的小型助手读取 | 与 Linux 相同的 exec 时快照属性。对自己的进程不需要 root 权限即可读取。 |
| Windows | 每个祖先进程的实时环境块（PEB），由同一助手读取，并带有 PID 重用保护 | 较弱：Windows 没有保存 exec 时快照，因此检查读取当前内存。祖先进程仍无法被智能体通常运行的任何东西改写，但证人不像 Linux 和 macOS 那样由内核冻结。 |

在 macOS 和 Windows 上，CLI 会生成其内附的 `renet` 二进制文件来进行读取；助手报告每个祖先携带的被监视变量，所有决策逻辑保留在 CLI 中。如果助手缺失、过期或出于任何原因失败，CLI 无法验证覆盖并**以安全失败模式关闭**：覆盖被拒绝，错误表明验证不可用，而不是说你做错了什么。正常安装永远不会显示该消息；重新安装 `rdc` 会恢复助手。

在每个平台上都真实的是：覆盖必须在智能体启动时已经存在于其环境中。在你的终端中导出它，然后启动智能体。在会话中途设置该变量的智能体会被拒绝。

## 审计日志

每次变更、每次拒绝、每次 `--reveal` 授予都会向 `~/.config/rediacc/audit.log.jsonl`（模式 `0600`，10 MB 时轮换）写入一行 JSONL。每行都经过哈希链接：其 `prevHash` 字段为 `sha256("<上一行>")`。篡改任何一行都会破坏此后所有行的链。

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
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

主要的缓解措施是内置的：**[每个仓库的密钥](/zh/docs/repositories#secrets)** 存储在与加密仓库镜像不同的平面中，不会在 fork 边界之间复制。fork 的容器启动时会获得一个空的密钥映射，并以不同的外部主体身份自我标识。使用 `rdc repo secret set` 设置它们（环境变量模式用于 compose 插值，文件模式用于 tmpfs `secrets:` 块）。变更门控是对称的。人类和智能体都必须提供 `--current`（passwd 风格的前提条件）或 `--rotate-secret`（审计轮换）来覆盖或删除现有值。

**跨仓库隔离是强制执行的。** 仓库 B 中的恶意或不谨慎的 compose 文件无法引用仓库 A 的密钥目录。Renet 的 compose 验证器会硬拒绝任何指向当前仓库 `${REDIACC_NETWORK_ID}` 目录之外的 `secrets: file:`、`configs: file:` 或 `env_file:` 路径，而且这个拒绝**不能被 `--unsafe` 覆盖**。纵深防御：围绕 Rediaccfile bash 子进程的 Landlock 沙箱将文件系统读取限制为仅当前网络的密钥目录，因此来自恶意 Rediaccfile 的 `cat /var/run/rediacc/secrets/<other>/X` 会在内核层以 EACCES 失败。

还有两种额外的模式可以关闭边界情况：

1. **不要在仓库文件系统本身中烘烤生产凭据。** 提交到镜像中的 `.env` 文件，或在 `up()` 期间持久化到卷的凭据，都会被 reflink 到 fork 中。每个仓库的密钥功能只保护你保存在密钥平面中的值。它无法逆向保护已经存在于 LUKS 镜像内的字节。对于现有的具有烘烤 `.env` 文件的仓库，请手动将其提升到每个仓库的密钥功能中。
2. **通过 eBPF 出站过滤限制 fork 的出站网络**，使 fork 仅能访问 localhost 和明确的沙箱端点。Rediacc 的每个仓库的网络隔离是基础；每个 fork 的出站允许列表目前尚未构建，但路径已经打开。

Rediacc 处理部署时注入、跨 fork 隔离和跨仓库隔离。"不要把它烘烤到镜像中"这一半是你的责任。

## 快速方案

### 允许智能体轮换单个云端令牌

```bash
# 以你自己的身份，在启动智能体之前：
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # 或 cursor、gemini 等
```

现在智能体可以执行 `config field rotate /credentials/cfDnsApiToken --new …`，但仍无法编辑 `/credentials/ssh/privateKey` 或打开交互式编辑器。

### 允许智能体进行广泛的配置编辑会话

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

智能体可以打开 `rdc config edit`、使用 `--reveal` 并运行 `field rotate`。每个操作仍会以 `actor.kind: agent` 和 `CLAUDECODE` 信号记录在审计日志中。

### 了解智能体被允许访问的字段

```bash
rdc config field list --sensitive --output json
```

返回每个指针模板、其类型（`secret` / `credential` / `pii` / `identifier`），以及是否已提交到服务器端 HMAC 信封。

## 另请参阅

- [AI 智能体集成概览](/zh/docs/ai-agents-overview): 顶层介绍
- [Claude Code 配置](/zh/docs/ai-agents-claude-code): 集成模板
- [JSON 输出信封](/zh/docs/ai-agents-json-output): 机器可读响应
- [加密配置存储](/zh/docs/config-storage): 服务器端密码学强制
- [账户安全](/zh/docs/account-security): 运营商安全态势
