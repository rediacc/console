---
title: JSON 출력 참조
description: rdc CLI JSON 출력 형식, 엔벨로프 스키마, 오류 처리 및 에이전트 검색 명령에 대한 전체 참조.
category: Reference
order: 51
language: ko
---

모든 `rdc` 명령은 AI 에이전트와 스크립트의 프로그래밍 방식 소비를 위한 구조화된 JSON 출력을 지원합니다.

## JSON 출력 활성화

### 명시적 플래그

```bash
rdc machine query --name prod-1 --output json
rdc machine query --name prod-1 -o json
```

### 자동 감지

`rdc`가 non-TTY 환경(파이프, 서브쉘 또는 AI 에이전트에 의해 실행)에서 실행될 때 출력이 자동으로 JSON으로 전환됩니다. 플래그가 필요하지 않습니다.

```bash
# 이 모든 명령은 자동으로 JSON을 생성합니다
result=$(rdc machine query --name prod-1)
echo '{}' | rdc agent exec "machine query"
```

## JSON 엔벨로프

모든 JSON 응답은 일관된 엔벨로프를 사용합니다:

```json
{
  "success": true,
  "command": "machine query",
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

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | `boolean` | 명령이 성공적으로 완료되었는지 여부 |
| `command` | `string` | 전체 명령 경로 (예: `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | 성공 시 명령별 페이로드, 오류 시 `null` |
| `errors` | `array \| null` | 실패 시 오류 객체, 성공 시 `null` |
| `warnings` | `string[]` | 실행 중 수집된 치명적이지 않은 경고 |
| `metrics` | `object` | 실행 메타데이터 |

## 오류 응답

실패한 명령은 복구 힌트와 함께 구조화된 오류를 반환합니다:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### 오류 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `code` | `string` | 머신이 읽을 수 있는 오류 코드 (표준 목록은 `ERROR_CODES` 상수 참조) |
| `message` | `string` | 사람이 읽을 수 있는 설명 |
| `retryable` | `boolean` | 같은 명령을 재시도하면 성공할 수 있는지 여부 |
| `guidance` | `string` | 자유 형식 힌트 (레거시. 구조화된 액션 데이터는 `next` 사용 권장) |
| `next` | `object?` | 구조화된 다음 액션 힌트 (있는 경우). 아래 참조 |

### 구조화된 `next` 액션 힌트

고가치 오류 코드(예: `PRECONDITION_MISMATCH`)의 경우, 오류에는 에이전트에게 사용자에게 제안할 명령을 정확히 알려주는 구조화된 `next` 필드가 포함됩니다. **에이전트는 자체 명령을 합성하는 대신 `next.options[].run`을 그대로 사용자에게 전달해야 합니다.** 이렇게 하면 "에이전트가 존재하지 않는 명령을 만들어내는" 오류 패턴을 방지할 수 있습니다.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

스키마:

| 필드 | 타입 | 설명 |
|------|------|------|
| `next.summary` | `string` | 사용자가 결정해야 할 사항에 대한 한 줄 설명 |
| `next.options[]` | `array` | 구체적인 액션. 각각은 사용자가 선택할 수 있는 대안입니다 |
| `next.options[].description` | `string` | 이 옵션에 대한 사람이 읽을 수 있는 설명 |
| `next.options[].run` | `string` | 정확한 CLI 명령. 사용자에게 그대로 전달하세요 |

### 재시도 가능한 오류

다음 오류 유형은 `retryable: true`로 표시됩니다:

- **NETWORK_ERROR**, SSH 연결 또는 네트워크 오류
- **RATE_LIMITED**, 요청이 너무 많음, 대기 후 재시도
- **API_ERROR**, 일시적인 백엔드 오류

재시도 불가능한 오류(인증, 찾을 수 없음, 잘못된 인수)는 재시도 전에 수정 조치가 필요합니다.

## 출력 필터링

`--fields`를 사용하여 출력을 특정 키로 제한하세요. 특정 데이터만 필요할 때 토큰 사용량을 줄여줍니다:

```bash
rdc machine containers --name prod-1 -o json --fields name,status,repository
```

## 드라이런 출력

파괴적 명령은 `--dry-run`으로 실행될 내용을 미리 확인할 수 있습니다:

```bash
rdc repo delete --name mail -m prod-1 --dry-run -o json
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

`--dry-run`을 지원하는 명령: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## 에이전트 검색 명령

`rdc agent` 서브커맨드는 AI 에이전트가 런타임에 사용 가능한 작업을 검색할 수 있도록 구조화된 검사를 제공합니다.

### 모든 명령 목록 조회

```bash
rdc agent capabilities
```

인수, 옵션 및 설명이 포함된 전체 명령 트리를 반환합니다:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
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

### 명령 스키마 조회

```bash
rdc agent schema --command "machine query"
```

타입 및 기본값을 포함한 모든 인수와 옵션이 포함된 단일 명령의 상세 스키마를 반환합니다.

### JSON을 통한 실행

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

stdin에서 JSON을 받아 키를 명령 인수 및 옵션에 매핑하고 JSON 출력을 강제하여 실행합니다. 셸 명령 문자열을 구성하지 않고 구조화된 에이전트-CLI 통신에 유용합니다.

## 파싱 예시

### Shell (jq)

```bash
status=$(rdc machine query --name prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
