---
title: JSON 输出参考
description: rdc CLI JSON 输出格式、信封模式、错误处理和代理发现命令的完整参考。
category: Reference
order: 51
language: zh
---

所有 `rdc` 命令都支持结构化 JSON 输出，供 AI 代理和脚本进行程序化消费。

## 启用 JSON 输出

### 显式标志

```bash
rdc machine info prod-1 --output json
rdc machine info prod-1 -o json
```

### 自动检测

当 `rdc` 在非 TTY 环境中运行（管道、子 shell 或由 AI 代理启动）时，输出会自动切换为 JSON。无需标志。

```bash
# These all produce JSON automatically
result=$(rdc machine info prod-1)
echo '{}' | rdc agent exec "machine info"
```

## JSON 信封

每个 JSON 响应使用一致的信封格式：

```json
{
  "success": true,
  "command": "machine info",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `success` | `boolean` | 命令是否成功完成 |
| `command` | `string` | 完整命令路径（例如 `"machine info"`、`"repo up"`） |
| `data` | `object \| array \| null` | 成功时的命令特定数据，错误时为 `null` |
| `errors` | `array \| null` | 失败时的错误对象，成功时为 `null` |
| `warnings` | `string[]` | 执行期间收集的非致命警告 |
| `metrics` | `object` | 执行元数据 |

## 错误响应

失败的命令返回带有恢复提示的结构化错误：

```json
{
  "success": false,
  "command": "machine info",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine info\" or \"rdc config repositories\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### 错误字段

| 字段 | 类型 | 描述 |
|-------|------|-------------|
| `code` | `string` | 机器可读的错误代码 |
| `message` | `string` | 人类可读的描述 |
| `retryable` | `boolean` | 重试相同命令是否可能成功 |
| `guidance` | `string` | 解决错误的建议下一步操作 |

### 可重试错误

以下错误类型标记为 `retryable: true`：

- **NETWORK_ERROR** — SSH 连接或网络故障
- **RATE_LIMITED** — 请求过多，等待后重试
- **API_ERROR** — 暂时性后端故障

不可重试的错误（身份验证、未找到、无效参数）需要在重试前采取纠正措施。

## 过滤输出

使用 `--fields` 将输出限制为特定键。当只需要特定数据时，这可以减少 token 使用量：

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## 模拟运行输出

破坏性命令支持 `--dry-run` 来预览将要发生的操作：

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

支持 `--dry-run` 的命令：`repo up`、`repo down`、`repo delete`、`snapshot delete`、`sync upload`、`sync download`。

## 代理发现命令

`rdc agent` 子命令提供结构化内省功能，供 AI 代理在运行时发现可用操作。

### 列出所有命令

```bash
rdc agent capabilities
```

返回包含参数、选项和描述的完整命令树：

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine info",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### 获取命令模式

```bash
rdc agent schema "machine info"
```

返回单个命令的详细模式，包括所有参数和选项的类型和默认值。

### 通过 JSON 执行

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine info"
```

通过 stdin 接受 JSON，将键映射到命令参数和选项，并强制以 JSON 输出执行。适用于无需构建 shell 命令字符串的结构化代理到 CLI 通信。

## 解析示例

### Shell (jq)

```bash
status=$(rdc machine info prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "info", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'info', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
