---
title: AI 에이전트 안전성 및 가드레일
description: >-
  Rediacc가 AI 코딩 어시스턴트의 시크릿 유출, 자격 증명 덮어쓰기, 권한 상승을
  어떻게 막는지 설명합니다. 모든 인터페이스에 적용되는 하나의 결정, 옵트인과
  정책 상한의 동시 충족, 지식 게이트, 리댁션, 해시 체인 감사 로그를 다룹니다.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: ko
sourceHash: "90603fac1c7635d4"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
---

당신의 인프라에 AI 코딩 어시스턴트를 배치하려고 합니다. Claude Code, Cursor, Gemini CLI, Copilot CLI 또는 유사한 것이 `rdc`를 구동할 때, CLI는 이를 감지하여 키보드 앞의 사람과는 다른 규칙 집합을 적용합니다. 이 페이지에서는 에이전트가 할 수 있는 것, 할 수 없는 것, 그리고 에이전트가 스스로 가드레일을 벗어나려 해도 가드레일이 유지되는 방법을 설명합니다.

## 빠른 참조: 에이전트가 할 수 있는 것과 없는 것

| 작업 | 에이전트 기본값 | 특정 사용 사례에서 허용하는 방법 |
|---|---|---|
| `rdc config show` (리댁션 적용) | ✅ 허용 |  |
| `rdc config field get --pointer <pointer>` (리댁션 스텁 또는 다이제스트) | ✅ 허용 |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (공개 필드) | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (민감 필드, **올바른 `--current`와 함께**) | ✅ 허용 |  |
| `rdc config edit --dump --redacted` (리댁션된 JSONC) | ✅ 허용 |  |
| `rdc config audit {log, tail, verify}` | ✅ 허용 |  |
| `rdc config field set --pointer <pointer>` (민감 필드, `--current` 없음) | 🔴 거부 | `--current "<이전 값>"` 제공 |
| `rdc repo secret set <repo> --rotate-secret` (`--current` 없는 교체) | 🔴 거부 | `--current` 제공, 또는 사람이 터미널에서 교체 실행 |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 거부 | 대신 `--digest` 사용 |
| `rdc config show --reveal` | 🔴 거부 | 일반 `rdc config show` 사용 |
| `rdc config edit` (대화형 편집기) | 🔴 거부, 재정의 없음 | `--dump --redacted`로 확인하고, 필드 하나는 `config field set --current`로 변경 |
| `rdc config edit --apply <file>` | 🔴 거부, 재정의 없음 | 동일, 문서 전체 편집은 터미널의 사람이 적용 |
| `rdc config edit --reveal` | 🔴 거부, 재정의 없음 | 동일 |
| `rdc config field rotate --pointer <pointer>` | 🔴 거부 | 사람이 대화형 터미널에서 실행 |
| grand(프로덕션) 레포지토리 변경 | 🔴 거부 | grand 레포지토리 변경을 허용하는 정책 안에서, 해당 레포지토리에 대한 사람의 옵트인 ([아래](#one-decision-opt-in-and-policy-ceiling)) |
| 클러스터 또는 데이터스토어 수명 주기 작업 | 🔴 거부 | 클러스터 작업을 허용하는 정책 안에서, 해당 클러스터에 대한 사람의 옵트인 |
| `rdc term connect <machine>` (직접 머신 SSH) | 🔴 거부 | 먼저 레포를 포크한 후 포크에 연결 |

에이전트에게 거부된 모든 요청은 `outcome: refused`와 사유와 함께 감사 로그에 기록됩니다. 설정 문서 전체를 편집하는 방법은 에이전트에게 아예 없습니다. 설정에는 모든 레포지토리의 LUKS 자격 증명이 들어 있고, 설정을 다시 쓸 수 있는 에이전트는 암호화된 볼륨을 여는 데 꼭 필요한 자격 증명도 삭제할 수 있기 때문입니다.

## 에이전트 감지 방법

CLI는 다음 중 하나가 참일 때 프로세스를 에이전트로 처리합니다.

- `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` 중 하나가 `"1"`로 설정되어 있거나, `CURSOR_TRACE_ID`가 설정되어 있는 경우.
- Linux에서: 조상 프로세스 체인 어딘가에 해당 변수가 환경변수로 존재하는 경우(`/proc/<pid>/environ` 통해). 에이전트가 `env -i`나 래퍼 스크립트로 자체 변수를 해제하더라도, 부모 체인은 여전히 누가 시작했는지 CLI에 알려줍니다.

감지는 프로세스당 한 번 실행되고 캐시됩니다. 비활성화할 수 없습니다. 원격 MCP 권한 부여는 실행기에서 해당 호출을 에이전트 호출로 표시하므로 감지가 필요 없습니다.

## 하나의 결정: 옵트인과 정책 상한의 동시 충족

`rdc` 명령을 실행하는 모든 인터페이스(CLI, 로컬 MCP 서버, 원격 MCP 서버, `rdc --proxy`, 웹 콘솔)는 같은 결정 함수에 묻기 때문에, 거부와 허용이 모두 동일합니다. 이 함수는 두 가지 조건을 적용하며, 에이전트는 두 조건이 모두 성립하는 곳에서만 동작할 수 있습니다.

1. **정책 상한.** 팀 정책으로 좁혀진 조직 정책이 호출자가 사용할 수 있는 명령, 머신, 레포지토리를 정하고, grand 레포지토리 변경(`allowGrandRepos`)과 클러스터 작업(`allowClusterOps`)을 아예 허용할지도 정합니다. 정책 레코드가 없는 설정은 역할별 기본값으로 대체됩니다. 소유자와 관리자는 동작할 수 있고 멤버는 할 수 없습니다. 정책은 소유자와 관리자만 쓸 수 있는 별도의 봉인된 레코드이며([보안 모델](/ko/docs/security-model#policy)), 어떤 에이전트나 CLI 명령도 이를 편집할 수 없습니다.
2. **사람의 옵트인.** 상한 안에서도 에이전트에게는 변경해도 되는 grand 레포지토리나 클러스터를 사람이 지정해 주는 절차가 필요합니다.
   - **로컬 에이전트**(CLI와 로컬 MCP): 사람이 에이전트를 시작하기 전에 터미널에서 `REDIACC_ALLOW_GRAND_REPO`(레포지토리 이름 또는 `*`)나 `REDIACC_ALLOW_CLUSTER_OPS`(클러스터 이름 또는 `*`)를 내보냅니다. CLI가 프로세스 조상을 확인하므로, 에이전트가 세션 도중 설정한 변수는 인정되지 않습니다([운영 체제별 확인 방식](#how-a-local-opt-in-is-verified-on-each-os)).
   - **원격 에이전트**(원격 MCP): 옵트인은 사람이 계정 화면에서 만드는 권한 부여에 포함됩니다([원격 서버](/ko/docs/ai-agents-mcp#remote-server)).

옵트인이 상한을 넓히는 일은 없습니다. 정책이 닫은 레포지토리는 환경이나 권한 부여가 무엇이라 하든 닫힌 채로 유지됩니다. 포크에는 옵트인이 필요 없습니다. CLI가 식별할 수 없는 레포지토리는 grand로 간주됩니다.

**파괴적인 변경은 먼저 확인을 요청합니다.** 에이전트가 grand 레포지토리에 대한 파괴적인 변경(예: `repo delete`)을 허가받은 경우 응답은 `needs_confirmation`입니다. MCP 클라이언트는 사용자에게 확인 프롬프트를 보여 주고, 프롬프트가 없는 클라이언트는 사용자에게 물어본 뒤 다시 보낼 `confirm` 인수를 받습니다. CLI에서는 사람이 `--confirm-grand <repo>`를 붙여 명령을 다시 실행합니다.

모든 응답에는 안정적인 코드(`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`)가 붙으므로, 스크립트나 에이전트는 메시지가 아닌 코드로 분기할 수 있습니다([JSON 출력](/ko/docs/ai-agents-json-output)).

## 지식 게이트 모델

민감한 변경 작업은 `passwd(1)` 관례를 따릅니다. 시크릿을 변경하려면 이미 알고 있었다는 증명이 필요합니다. **사람과 에이전트에게 동일하게 적용됩니다**. 둘 다 같은 게이트를 통과해야 합니다. "키보드 앞에 있다"는 우회로는 없습니다.

- `/credentials/cfDnsApiToken`에 저장된 API 토큰을 교체하고 싶으신가요?
- CLI는 "현재 값이 무엇인가요?"라고 묻습니다.
- 에이전트(또는 사람)가 `--current "$OLD"`를 통해 평문을 제공합니다. CLI는 `$OLD`를 SHA-256으로 해시하여 현재 저장된 값의 다이제스트와 비교합니다. 일치하면 쓰기가 진행됩니다. 불일치하면 거부되고 감사됩니다.
- 이전 값을 확인하지 않고 교체하려면 `--rotate-secret`을 전달합니다(`--current`와 함께 쓸 수 없음). 이는 교체로 분명하게 감사 기록되며, 대화형 터미널의 사람에게만 인정됩니다. 에이전트나 stdin에 터미널이 없는 스크립트에는 여전히 `--current`가 필요합니다.

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
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**에이전트는 자체 명령을 만들어 내는 대신 `next.options[].run`을 사람에게 그대로 전달해야 합니다.** 이렇게 하면 에이전트가 존재하지 않는 명령을 지어내는 실패를 막고, 실제 작업의 주도권을 운영자가 유지합니다. 교체 옵션은 사람이 터미널에서 실행하기 위한 것이며, 에이전트 자신에게는 거부됩니다.

### 실제 예시

```bash
# 리댁션 스텁의 짧은 다이제스트 확인 (에이전트에게 안전).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# 증명 없이 덮어쓰기 시도: 거부.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# 현재 평문 제공: 허용.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

에이전트가 `$OLD_CF_TOKEN`을 가진 적이 없다면 전제 조건을 충족할 수 없고 교체는 거부됩니다. 값을 아는 사람은 자신의 셸에서 `--current`를 전달하거나 대화형 터미널에서 `rdc config field rotate`로 교체할 수 있습니다.

## 기본 리댁션

민감한 상태를 읽는 모든 `rdc` 명령어(`config show`, `config field get`, `config machine list`, `config edit --dump --redacted`)는 시크릿 필드에 대해 평문이 아닌 **리댁션 스텁**을 반환합니다.

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

스텁의 8자 16진수 접미사는 `sha256(canonicalize(value))`의 처음 8자입니다. 두 값의 차이를 한눈에 구분할 수 있을 만큼은 충분하지만, 역추적하기에는 충분하지 않습니다. 에이전트는 스텁을 사용하여 값을 직접 보지 않고도 변경 여부를 추적할 수 있습니다.

`--reveal`은 대화형 TTY에서 사람에게 리댁션을 해제합니다. 에이전트는 TTY 상태와 관계없이 거부됩니다. 각 허용 시에는 `reveal_granted` 감사 항목이 기록되고, 각 거부 시에는 에이전트의 신호가 첨부된 `refused` 항목이 기록됩니다.

## 로컬 옵트인을 운영 체제별로 확인하는 방법

`REDIACC_ALLOW_GRAND_REPO`와 `REDIACC_ALLOW_CLUSTER_OPS`는 모두 조상 확인에 의존해, 옵트인이 에이전트가 주입한 것이 아니라 사람이 설정한 것임을 증명합니다. 확인은 Linux, macOS, Windows에서 동작하지만, 읽어 들이는 증거는 플랫폼마다 다르고 보장의 강도도 다릅니다.

| 플랫폼 | 증거 | 강도 |
|---|---|---|
| Linux | 체인의 모든 프로세스에 대한 `/proc/<pid>/environ` | Exec 시점의 스냅샷, 커널이 제공. 프로세스는 시작 당시의 상태를 소급하여 수정할 수 없습니다. |
| macOS | `kern.procargs2` sysctl, `rdc` 내부에 포함된 작은 헬퍼가 읽음 | Linux와 동일한 exec 시점 스냅샷 속성. 루트 없이 자신의 프로세스에 대해 읽을 수 있습니다. |
| Windows | 각 조상 프로세스의 현재 환경 블록(PEB), 동일한 헬퍼가 읽음, PID 재사용 보호 포함 | 더 약함: Windows는 exec 시점 스냅샷을 유지하지 않으므로 체크가 현재 메모리를 읽습니다. 조상은 여전히 에이전트가 일반적으로 실행하는 어떤 것도 다시 쓸 수 없지만, 증거가 Linux와 macOS처럼 커널에서 동결되어 있지 않습니다. |

macOS와 Windows에서는 CLI가 번들된 `renet` 바이너리를 실행해 값을 읽습니다. 헬퍼는 각 조상이 감시 대상 변수 중 무엇을 가지고 있는지 보고하며, 모든 결정 로직은 CLI에 남아 있습니다. 헬퍼가 없거나, 오래되었거나, 어떤 이유로든 실패하면 CLI는 옵트인을 확인할 수 없어 **안전하게 차단 상태로 실패합니다**. 옵트인은 거부되고, 오류 메시지는 무언가 잘못되었다는 것이 아니라 확인을 수행할 수 없었다고 알려 줍니다. 정상 설치에서는 이 메시지가 나타나지 않으며, `rdc`를 다시 설치하면 헬퍼가 복구됩니다.

모든 플랫폼에서 달라지지 않는 점: 옵트인은 에이전트 프로세스가 시작될 때 이미 그 환경에 있어야 합니다. 터미널에서 내보낸 다음 에이전트를 시작합니다. 세션 도중 변수를 설정하는 에이전트는 거부됩니다.

## 감사 로그

모든 변경, 모든 거부, 모든 `--reveal` 허용은 `~/.config/rediacc/audit.log.jsonl`(모드 `0600`, 10 MB에서 순환)에 JSONL 라인으로 기록됩니다. 각 라인은 해시 체인으로 연결되어 있습니다. `prevHash` 필드는 `sha256("<이전 라인>")` 입니다. 어떤 라인을 변조해도 이후의 모든 라인에서 체인이 깨집니다.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
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

기본 완화책이 내장되어 있습니다. **[레포별 시크릿](/en/docs/repositories#secrets)**은 암호화된 레포지토리 이미지와 별도의 평면에 저장되며 포크 경계를 넘어 복사되지 않습니다. 포크의 컨테이너는 빈 시크릿 맵으로 부팅하고 부모와 다른 외부 주체로 식별됩니다. `rdc repo secret set`으로 설정하세요(compose 보간을 위한 env 모드, tmpfs `secrets:` 블록을 위한 file 모드). 변경 게이트는 대칭적입니다. 사람과 에이전트 모두 기존 값을 덮어쓰거나 삭제하려면 `--current`(passwd 스타일 전제 조건)를 제공해야 합니다. `--rotate-secret`(감사되는 교체)은 터미널의 사람을 위한 대안입니다.

**크로스 레포 격리가 적용됩니다.** 레포 B의 악의적이거나 부주의한 compose 파일은 레포 A의 시크릿 디렉토리를 참조할 수 없습니다. Renet의 compose 검증기는 현재 레포의 `${REDIACC_NETWORK_ID}` 디렉토리 밖을 가리키는 `secrets: file:`, `configs: file:`, `env_file:` 경로를 강하게 거부하며, 이 거부는 `--unsafe`로 재정의할 수 없습니다. 심층 방어: Rediaccfile bash 서브프로세스 주변의 Landlock 샌드박스는 파일시스템 읽기를 현재 네트워크의 시크릿 디렉토리로만 제한하므로, 악의적인 Rediaccfile에서의 `cat /var/run/rediacc/net-<other>/secrets/X`는 커널 계층에서 EACCES로 실패합니다. Docker API에서도 마찬가지입니다. 각 레포의 Docker 소켓은 renet 정책 프록시가 처리하며, 이 프록시는 `--privileged`, 호스트 `pid`, `ipc`, `uts`, 장치 요청, 다른 레포의 런타임이나 데이터에 닿는 바인드를 `403`으로 거부합니다. 따라서 `${DOCKER_SOCKET}`을 가진 컨테이너가 API로 다른 레포에 접근할 수 없으며, compose 파일만 검사하는 것이 아닙니다. 바인드 규칙은 이름을 지정한 호스트 디렉토리에 한해 운영자만 넓힐 수 있고, 방법은 어떤 컨테이너도 쓸 수 없는 root 소유의 허용 파일입니다.

두 가지 추가 패턴이 엣지 케이스를 해소합니다.

1. **레포지토리 파일시스템 자체에 프로덕션 자격 증명을 포함시키지 마세요.** 이미지에 커밋된 `.env` 파일이나 `up()` 중 볼륨에 지속된 자격 증명은 포크로 리링크됩니다. 레포별 시크릿 기능은 시크릿 평면에 보관하는 값만 보호합니다. LUKS 이미지 내부에 이미 존재하는 바이트는 소급하여 보호할 수 없습니다. 기존 레포의 포함된 `.env` 파일의 경우 수동으로 레포별 시크릿으로 이동하세요.
2. **eBPF egress 필터링으로 포크의 아웃바운드 네트워크를 제한하여** 포크가 localhost와 명시적 샌드박스 엔드포인트에만 도달할 수 있도록 하세요. Rediacc의 레포별 네트워크 격리가 기반이며, 포크별 egress 허용 목록은 아직 구축되지 않았지만 경로는 열려 있습니다.

Rediacc는 배포 시점 주입, 크로스 포크 격리, 크로스 레포 격리를 처리합니다. "이미지에 포함시키지 않기" 부분은 사용자의 몫입니다.

## 빠른 레시피

### 에이전트가 grand 레포지토리 하나에서 작업하도록 허용하기

```bash
# 사람으로서, 에이전트를 시작하기 전에:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # 또는 cursor, gemini 등
```

이제 에이전트는 정책이 grand 레포지토리 변경을 허용하는 범위에서 `gitlab`을 변경할 수 있으며, 다른 grand 레포지토리는 변경할 수 없습니다. `repo delete gitlab` 같은 파괴적인 변경은 여전히 확인을 요청합니다.

### 이전 값을 모른 채 클라우드 토큰 교체하기

```bash
# 사람으로서, 대화형 터미널에서:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

`--current` 없는 교체는 사람의 몫입니다. 현재 값을 아는 에이전트는 대신 `rdc config field set --current`를 사용합니다.

### 에이전트가 접근 가능한 필드 확인

```bash
rdc config field list --sensitive --output json
```

모든 포인터 템플릿, 종류(`secret` / `credential` / `pii` / `identifier`), 서버 측 HMAC 봉투에 커밋되었는지 여부를 반환합니다.

## 관련 문서

- [AI 에이전트 통합 개요](/en/docs/ai-agents-overview): 최상위 개요
- [MCP 서버](/ko/docs/ai-agents-mcp): 로컬 및 원격 MCP, 권한 부여와 그 옵트인
- [보안 모델](/ko/docs/security-model): 정책 레코드와 이를 쓸 수 있는 주체
- [Claude Code 설정](/en/docs/ai-agents-claude-code): 통합 템플릿
- [JSON 출력 봉투](/en/docs/ai-agents-json-output): 머신 가독 응답
- [암호화된 설정 저장소](/en/docs/config-storage): 서버 측 암호화 강제
- [계정 보안](/en/docs/account-security): 운영자 보안 포지션
