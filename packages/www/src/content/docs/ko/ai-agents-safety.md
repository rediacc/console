---
title: AI 에이전트 안전성 및 가드레일
description: >-
  Rediacc CLI가 AI 코딩 어시스턴트의 시크릿 유출, 자격 증명 덮어쓰기, 권한 상승을 방지하는 방법입니다. 지식 게이트,
  리댁션, 조상 검증된 재정의, 해시 체인 감사 로그를 설명합니다.
category: Concepts
order: 35
language: ko
---

Claude Code, Cursor, Gemini CLI, Copilot CLI 또는 다른 AI 코딩 어시스턴트가 `rdc`를 구동할 때, CLI는 이를 키보드 앞의 사람과 다르게 처리합니다. 이 페이지에서는 에이전트가 할 수 있는 것, 할 수 없는 것, 그리고 에이전트가 스스로 가드레일을 벗어나려 해도 가드레일이 유지되는 방법을 설명합니다.

## 빠른 참조: 에이전트가 할 수 있는 것과 없는 것

| 작업 | 에이전트 기본값 | 특정 사용 사례에서 허용하는 방법 |
|---|---|---|
| `rdc config show` (리댁션 적용) | ✅ 허용 |  |
| `rdc config field get --pointer <pointer>` (리댁션 스텁 또는 다이제스트) | ✅ 허용 |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (공개 필드) | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (민감 필드, **올바른 `--current`와 함께**) | ✅ 허용 |  |
| `rdc config edit --dump` (리댁션 JSONC) | ✅ 허용 |  |
| `rdc config audit {log, tail, verify}` | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (민감 필드, `--current` 없음) | 🔴 거부 | `--current "<이전 값>"` 제공 |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 거부 | 대신 `--digest` 사용 |
| `rdc config show --reveal` | 🔴 거부 | 일반 `rdc config show` 사용 |
| `rdc config edit` (대화형 편집기) | 🔴 거부 | 사람이 에이전트 실행 전 `REDIACC_ALLOW_CONFIG_EDIT=*` 설정 |
| `rdc config edit --apply <file>` | 🔴 거부 | 동일한 재정의 |
| `rdc config field rotate --pointer <pointer>` | 🔴 거부 | 동일한 재정의, 대화형 확인 사용 |
| `rdc term connect -m <machine>` (직접 머신 SSH) | 🔴 거부 | 먼저 레포를 포크한 후 포크에 연결 |

에이전트가 거부된 모든 작업은 `outcome: refused`와 이유가 함께 감사 로그에 기록됩니다.

## 에이전트 감지 방법

CLI는 다음 중 하나가 참일 때 프로세스를 에이전트로 처리합니다.

- `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` 중 하나가 `"1"`로 설정되어 있거나, `CURSOR_TRACE_ID`가 설정되어 있는 경우.
- Linux에서: 조상 프로세스 체인 어딘가에 해당 변수가 환경변수로 존재하는 경우(`/proc/<pid>/environ` 통해). 에이전트가 `env -i`나 래퍼 스크립트로 자체 변수를 해제하더라도, 부모 체인은 여전히 누가 시작했는지 CLI에 알려줍니다.

감지는 프로세스당 한 번 실행되며 캐시됩니다. 비활성화할 수 없습니다.

## 지식 게이트 모델

민감한 변경 작업은 `passwd(1)` 관례를 따릅니다. 시크릿을 변경하려면 이미 알고 있었다는 증명이 필요합니다. **사람과 에이전트에게 동일하게 적용됩니다**. 둘 다 같은 게이트를 통과해야 합니다. "키보드 앞에 있다"는 우회로는 없습니다.

- `/credentials/cfDnsApiToken`에 저장된 API 토큰을 교체하고 싶으신가요?
- CLI는 "현재 값이 무엇인가요?"라고 묻습니다.
- 에이전트(또는 사람)가 `--current "$OLD"`를 통해 평문을 제공합니다. CLI는 `$OLD`를 SHA-256으로 해시하여 현재 저장된 값의 다이제스트와 비교합니다. 일치하면 쓰기가 진행됩니다. 불일치하면 거부되고 감사됩니다.
- 이전 값을 검증하지 않고 교체하려면 `--rotate-secret`을 전달하세요(`--current`와 상호 배타적). 이 작업은 교체로 명시적으로 감사됩니다.

이 모델은 세 가지 공격 표면을 차단합니다.

1. **조용한 교체**: `$OLD`에 사전 접근 없이는 에이전트나 사람 모두 자신이 선택한 값으로 교체할 수 없습니다.
2. **탐색을 통한 유출**: 다이제스트 응답에는 평문이 없습니다. 손상된 감사 로그도 `expected abc12345…, got deadbeef…`만 표시하며, 실제 값은 보이지 않습니다.
3. **프로덕션 설정 실수 덮어쓰기**: TTY에서도 매번 의도적인 `--current`가 필요합니다. "STRIPE_TEST를 설정하려 했는데 프로덕션 셸에 있었다"는 실수를 방지합니다.

### 구조화된 다음 작업 힌트

전제 조건이 실패하면 JSON 봉투(`--output json`)에 에이전트가 사람에게 정확히 무엇을 제안해야 하는지 알려주는 구조화된 `errors[].next` 필드가 포함됩니다.

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

**에이전트는 `next.options[].run`을 그대로 사람에게 전달해야 하며, 자체적으로 명령어를 생성해서는 안 됩니다.** 이는 "에이전트가 존재하지 않는 명령어를 만들어낸다"는 실패 모드를 방지하고 운영자가 실제 작업의 통제권을 유지할 수 있게 합니다.

### 실제 예시

```bash
# 리댁션 스텁의 짧은 다이제스트 확인 (에이전트에게 안전).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 증명 없이 덮어쓰기 시도: 거부.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# 현재 평문 제공: 허용.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

에이전트가 `$OLD_CF_TOKEN`을 가진 적 없다면 전제 조건을 충족할 수 없고 교체는 거부됩니다. 실제로 갖고 있는 사용자는 편집기를 통하거나 셸에서 `--current`를 전달하여 수행할 수 있습니다.

## 기본 리댁션

민감한 상태를 읽는 모든 `rdc` 명령어(`config show`, `config field get`, `config machine list`, `config edit --dump`)는 시크릿 필드에 대해 평문이 아닌 **리댁션 스텁**을 반환합니다.

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

스텁의 8자 16진수 접미사는 `sha256(canonicalize(value))`의 처음 8자입니다. 두 값의 차이를 한눈에 구분할 수 있을 만큼은 충분하지만, 역추적하기에는 충분하지 않습니다. 에이전트는 스텁을 사용하여 값을 직접 보지 않고도 변경 여부를 추적할 수 있습니다.

`--reveal`은 대화형 TTY에서 사람에게 리댁션을 해제합니다. 에이전트는 TTY 상태와 관계없이 거부됩니다. 각 허용 시에는 `reveal_granted` 감사 항목이 기록되고, 각 거부 시에는 에이전트의 신호가 첨부된 `refused` 항목이 기록됩니다.

## `REDIACC_ALLOW_CONFIG_EDIT` 재정의

일부 작업(대화형 편집기, `--apply`, `field rotate`)은 사람을 위해 존재하며 에이전트에 안전한 경로가 없습니다. 에이전트가 이 중 하나를 수행하기를 원한다면 다음과 같이 설정합니다.

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # 전체 우회
# 또는
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (쉼표로 구분된 스코프 글로브: 세그먼트당 * 와일드카드 허용)
```

그러면 에이전트가 이를 상속합니다.

**중요한 세부 사항**: 재정의는 조상 체인에서 에이전트 **위**에 있는 프로세스에서 나타나야 합니다. 에이전트가 자체 환경(또는 생성한 서브셸)에서 설정하면 CLI가 거부하고 알려줍니다.

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

효과: 에이전트는 세션 중간에 `export REDIACC_ALLOW_CONFIG_EDIT='*'`를 실행하여 가드레일을 우회할 수 없습니다. 부모 프로세스(에이전트를 실행하기 전 터미널의 사용자)만 그 문을 열 수 있습니다.

## 플랫폼 지원: 재정의는 Linux 전용

`REDIACC_ALLOW_CONFIG_EDIT`와 `REDIACC_ALLOW_GRAND_REPO` 모두 재정의가 에이전트가 아닌 사용자에 의해 설정되었음을 증명하기 위해 조상 검증에 의존합니다. 검증은 체인의 모든 프로세스에 대해 `/proc/<pid>/environ`을 읽습니다. 해당 파일은 exec 시점에 커널에 의해 설정되며 프로세스 자체가 수정할 수 없으므로, 부모 셸의 환경이 변조 방지 증인이 됩니다.

macOS나 Windows에는 해당 파일이 존재하지 않습니다. 정당성을 검증할 방법이 없으므로 CLI는 닫힌 상태로 실패합니다. 에이전트를 실행하기 전 셸에서 올바르게 재정의를 설정하더라도 거부됩니다. 오류 메시지는 정확히 무엇을 해야 하는지 알려줍니다.

> The REDIACC_ALLOW_GRAND_REPO override is not supported on darwin. This override only works on Linux. On Windows and macOS, agents must use the fork-first workflow. … To use the override, run your agent on Linux (directly, WSL, Docker, or a VM).

실제로 비 Linux 사용자는 포크 우선 워크플로우에서 벗어날 방법이 없습니다. 이는 의도적입니다. 에이전트는 어떻게 프롬프트를 받았든 상관없이 도달할 수 없는 샌드박스를 통해 진행됩니다. 재정의가 필요하다면 WSL, Linux 컨테이너, 또는 Linux VM 내에서 에이전트를 실행하세요. 그렇지 않으면 포크에서 작업하세요.

## 감사 로그

모든 변경, 모든 거부, 모든 `--reveal` 허용은 `~/.config/rediacc/audit.log.jsonl`(모드 `0600`, 10 MB에서 순환)에 JSONL 라인으로 기록됩니다. 각 라인은 해시 체인으로 연결되어 있습니다. `prevHash` 필드는 `sha256("<이전 라인>")` 입니다. 어떤 라인을 변조해도 이후의 모든 라인에서 체인이 깨집니다.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### 검사

```bash
# 최근 항목 목록
rdc config audit log --since 24h

# 포인터 글로브로 필터링
rdc config audit log --path '/credentials/*'

# 에이전트 발원 항목만
rdc config audit log --actor agent

# 새 항목을 실시간으로 스트리밍 (Ctrl+C로 중지)
rdc config audit tail

# 해시 체인 무결성 검증
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   또는
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### 감사 로그에 절대 나타나지 않는 것

- 평문 시크릿 값
- 패스프레이즈, 토큰, SSH 키
- `--current` 전제 조건 불일치 시의 이전/새 값 (8자 다이제스트 접두사만 표시)

로그는 보안 검토자와 공유하거나 버그 보고서에 첨부하기에 안전합니다.

## 행동 모델의 한계

에이전트 가드레일은 **행동적이며, 암호화 기반이 아닙니다**. 설정 파일과 동일한 UID로 실행되는 결의 있거나 프롬프트된 에이전트는 언제든지 `cat ~/.config/rediacc/rediacc.json`을 실행하여 평문을 읽을 수 있습니다. 파일이 해당 프로세스에서 읽기 가능하기 때문입니다.

실제 암호화 기반 강제를 위해서는 [암호화된 설정 저장소](/en/docs/config-storage)를 사용하세요. 시크릿은 서버 측에 존재하고, 각 민감 필드는 필드별 HMAC 커밋을 갖고 있으며, 계정 워커는 `--current` 전제 조건이 저장된 내용과 해시 일치하지 않는 쓰기를 거부합니다. 서버는 평문을 절대 보지 않습니다. 영지식이지만 게이트를 강제합니다.

로컬 파일 경로는 "쉬운 경로가 안전"합니다. 원격 저장소 경로는 "어려운 경로도 어렵습니다."

## Rediacc가 격리하지 않는 것

이 페이지의 에이전트 가드레일은 Rediacc 자체 인프라, 즉 설정 파일, 레포별 Docker 데몬, LUKS 암호화 레포지토리 데이터, 스코프된 SSH 샌드박스를 보호합니다. 레포지토리가 자격 증명을 보유한 외부 서비스는 보호하지 않습니다.

레포지토리 포크는 부모 볼륨의 BTRFS 리링크입니다. 부모 디스크에 있는 모든 것, 즉 코드, 데이터, `.env` 파일이 포크에서 바이트 단위로 동일합니다. 레포지토리에 `STRIPE_LIVE_KEY`, `AWS_ACCESS_KEY_ID`, Railway API 토큰, 또는 서드파티 서비스를 위한 장기 자격 증명이 있다면 포크가 이를 상속합니다. 포크의 샌드박스에서 작동하는 에이전트는 해당 파일을 읽고, 값을 유출하거나, 서드파티 API를 호출하는 데 사용할 수 있습니다. 서드파티 서비스는 호출이 프로덕션이 아닌 포크에서 온 것인지 알 방법이 없습니다.

이것이 공동 책임의 경계입니다.

| 경계 | 소유자 |
|---|---|
| 레포지토리 데이터, 마운트 네임스페이스, Docker 스코프, 에이전트 가드, 감사 로그, 배포 시점 시크릿 주입 | Rediacc |
| 해당 시크릿을 사용하는 애플리케이션 코드, 빌드 시점에 이미지에 포함된 자격 증명 | 레포지토리 개발자 |

기본 완화책이 내장되어 있습니다. **[레포별 시크릿](/en/docs/repositories#secrets)**은 암호화된 레포지토리 이미지와 별도의 평면에 저장되며 포크 경계를 넘어 복사되지 않습니다. 포크의 컨테이너는 빈 시크릿 맵으로 부팅하고 부모와 다른 외부 주체로 식별됩니다. `rdc repo secret set`으로 설정하세요(compose 보간을 위한 env 모드, tmpfs `secrets:` 블록을 위한 file 모드). 변경 게이트는 대칭적입니다. 사람과 에이전트 모두 기존 값을 덮어쓰거나 삭제하려면 `--current`(passwd 스타일 전제 조건) 또는 `--rotate-secret`(감사된 교체)을 제공해야 합니다.

**크로스 레포 격리가 적용됩니다.** 레포 B의 악의적이거나 부주의한 compose 파일은 레포 A의 시크릿 디렉토리를 참조할 수 없습니다. Renet의 compose 검증기는 현재 레포의 `${REDIACC_NETWORK_ID}` 디렉토리 밖을 가리키는 `secrets: file:`, `configs: file:`, `env_file:` 경로를 강하게 거부하며, 이 거부는 `--unsafe`로 재정의할 수 없습니다. 심층 방어: Rediaccfile bash 서브프로세스 주변의 Landlock 샌드박스는 파일시스템 읽기를 현재 네트워크의 시크릿 디렉토리로만 제한하므로, 악의적인 Rediaccfile에서의 `cat /var/run/rediacc/secrets/<other>/X`는 커널 계층에서 EACCES로 실패합니다.

두 가지 추가 패턴이 엣지 케이스를 해소합니다.

1. **레포지토리 파일시스템 자체에 프로덕션 자격 증명을 포함시키지 마세요.** 이미지에 커밋된 `.env` 파일이나 `up()` 중 볼륨에 지속된 자격 증명은 포크로 리링크됩니다. 레포별 시크릿 기능은 시크릿 평면에 보관하는 값만 보호합니다. LUKS 이미지 내부에 이미 존재하는 바이트는 소급하여 보호할 수 없습니다. 기존 레포의 포함된 `.env` 파일의 경우 수동으로 레포별 시크릿으로 이동하세요.
2. **eBPF egress 필터링으로 포크의 아웃바운드 네트워크를 제한하여** 포크가 localhost와 명시적 샌드박스 엔드포인트에만 도달할 수 있도록 하세요. Rediacc의 레포별 네트워크 격리가 기반이며, 포크별 egress 허용 목록은 아직 구축되지 않았지만 경로는 열려 있습니다.

Rediacc는 배포 시점 주입, 크로스 포크 격리, 크로스 레포 격리를 처리합니다. "이미지에 포함시키지 않기" 부분은 사용자의 몫입니다.

## 빠른 레시피

### 에이전트가 단일 클라우드 토큰을 교체하도록 허용

```bash
# 에이전트를 시작하기 전, 사용자로서:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # 또는 cursor, gemini 등
```

이제 에이전트는 `config field rotate /credentials/cfDnsApiToken --new …`를 실행할 수 있지만, `/credentials/ssh/privateKey`를 편집하거나 대화형 편집기를 열 수는 없습니다.

### 에이전트가 광범위한 설정 편집 세션을 수행하도록 허용

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

에이전트는 `rdc config edit`을 열고, `--reveal`을 사용하고, `field rotate`를 실행할 수 있습니다. 모든 작업은 여전히 `actor.kind: agent`와 `CLAUDECODE` 신호와 함께 감사 로그에 기록됩니다.

### 에이전트가 접근 가능한 필드 확인

```bash
rdc config field list --sensitive --output json
```

모든 포인터 템플릿, 종류(`secret` / `credential` / `pii` / `identifier`), 서버 측 HMAC 봉투에 커밋되었는지 여부를 반환합니다.

## 관련 문서

- [AI 에이전트 통합 개요](/en/docs/ai-agents-overview): 최상위 개요
- [Claude Code 설정](/en/docs/ai-agents-claude-code): 통합 템플릿
- [JSON 출력 봉투](/en/docs/ai-agents-json-output): 머신 가독 응답
- [암호화된 설정 저장소](/en/docs/config-storage): 서버 측 암호화 강제
- [계정 보안](/en/docs/account-security): 운영자 보안 포지션
