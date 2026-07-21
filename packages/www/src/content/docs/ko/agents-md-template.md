---
title: AI 어시스턴트용 AGENTS.md 템플릿
description: Claude Code, Cursor 및 기타 AI 코딩 어시스턴트를 Rediacc 인프라와 함께 작동하도록 구성하기 위한 복사/붙여넣기 템플릿.
category: Reference
order: 50
language: ko
sourceHash: "1edff3471ded906d"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

문제는 이것입니다. AI 코딩 어시스턴트(Claude Code, Cursor, Cline, Windsurf)가 존재하지 않는 `rdc` 플래그를 계속 만들어 내고, 매번 물어보지 않으면 어떤 Rediacc 저장소 이름이 어떤 GUID에 매핑되는지 알 수 없습니다. 이 템플릿이 그 문제를 해결합니다. 아래 블록을 프로젝트의 `CLAUDE.md`, `.cursorrules`, 또는 도구가 사용하는 에이전트 설정 파일에 붙여넣으세요.

## 템플릿

```markdown
# Rediacc Infrastructure

Self-hosted infrastructure platform. Each machine runs Docker-based repositories with encrypted, isolated environments.

## CLI Tool: rdc

Install: `curl -fsSL https://www.rediacc.com/install.sh | bash`

### Key Flags
- `--output json` (or `-o json`), machine-readable JSON output
- `--yes` (or `-y`), skip interactive confirmations
- `--quiet` (or `-q`), suppress informational output
- `--fields name,status`, limit output fields
- Auto-JSON: when piped (non-TTY), output defaults to JSON automatically

### JSON Envelope
All JSON output uses a consistent envelope:
{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}

On error: {"success": false, "command": "...", "data": null, "errors": [{"code": "...", "message": "...", "retryable": false, "guidance": "..."}], ...}

### Common Operations

# Machine status
rdc machine status <machine> -o json

# List containers on a machine
rdc machine status <machine> --containers -o json

# Machine health check
rdc machine health <machine> -o json

# Deploy a repository
rdc repo up <repo>@<machine> --yes

# Stop a repository
rdc repo down <repo>@<machine> --yes

# SSH terminal to machine
rdc term connect <machine>

# SSH terminal to specific repo (sets DOCKER_HOST)
rdc term connect <repo>@<machine>

# Run command on machine
rdc term connect <machine> -c "command"

# File sync
rdc repo sync upload <repo>@<machine> --local ./local-path
rdc repo sync download <repo>@<machine> --local ./local-path

# List all available commands
rdc --help-all

### Architecture
- **Repository**: Isolated application deployment with its own Docker daemon at /var/run/rediacc/docker-<networkId>.sock, loopback IP range (127.0.x.x/26), and encrypted btrfs mount at /mnt/rediacc/mounts/<guid>/
- **Config**: CLI config at ~/.config/rediacc/rediacc.json. Auto-created on first use.
- One adapter: **local** (SSH-based)

### Rules
- Say "local adapter", never "local mode"
- S3 is a resource state backend, not a separate adapter
- Default config is created automatically on first use, do not tell users to run `rdc config init`
- Always use `--output json` when parsing output programmatically
- Always use `--yes` to skip confirmations in automated workflows
- Use `--dry-run` on destructive commands (repo delete, repo up, repo down) to preview before executing
```

## 커스터마이징

`<machine>`과 `<repo>`를 실제 머신 및 리포지토리 이름으로 교체하세요. `rdc repo list`를 실행하면 이름과 GUID 매핑과 함께 사용 가능한 리포지토리 목록을 확인할 수 있습니다.

### 설정 확인

```bash
# 구성된 머신 목록 조회
rdc machine status <machine-name>

# GUID와 함께 리포지토리 목록 조회
rdc repo list

# 사용 가능한 명령어 확인
rdc --help-all
```

## 에이전트별 설정

- **Claude Code**: 프로젝트 루트에 `CLAUDE.md`로 저장
- **Cursor**: 프로젝트 루트에 `.cursorrules`로 저장
- **Cline**: Cline 시스템 프롬프트 또는 프로젝트 지침에 추가
- **Windsurf**: 프로젝트 루트에 `.windsurfrules`로 저장
