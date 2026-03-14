# AGENTS.md — Rediacc CLI (`rdc`)

> Self-hosted infrastructure platform with encrypted repositories, container isolation, and automated disaster recovery.

## Tool

- **CLI**: `rdc` (not `rediacc`)
- **Install**: `curl -fsSL https://www.rediacc.com/install.sh | bash`
- **MCP Server**: `rdc mcp serve` (stdio transport)

## MCP Configuration

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

With a named config:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Key Flags

- `--output json` (`-o json`) — machine-readable JSON output
- `--yes` (`-y`) — skip interactive confirmations
- `--quiet` (`-q`) — suppress informational output
- `--fields name,status` — limit output fields
- `--dry-run` — preview destructive operations without executing
- Auto-JSON: output defaults to JSON when piped (non-TTY)

## JSON Envelope

All JSON output uses a consistent envelope:

```json
{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}
```

## Common Commands

```bash
rdc machine info <machine> -o json       # Machine status and resources
rdc machine containers <machine> -o json  # List Docker containers
rdc machine services <machine> -o json    # List systemd services
rdc machine repos <machine> -o json       # List deployed repositories
rdc machine health <machine> -o json      # Health check
rdc repo up <repo> -m <machine> --yes     # Deploy a repository
rdc repo down <repo> -m <machine> --yes   # Stop a repository
rdc term <machine> -c "command"           # Run command via SSH
rdc sync upload -m <machine> -r <repo>    # Upload files
rdc sync download -m <machine> -r <repo>  # Download files
rdc agent capabilities                    # List all commands (for discovery)
```

## Security

Each repo has its own SSH key. All repo-level connections (term, VS Code, sync) are sandboxed server-side:
- **Per-repo SSH keys**: `command="renet sandbox-gateway <name>"` in `authorized_keys` — un-bypassable
- **Landlock LSM**: Kernel-level filesystem restriction to the repo's own mount path
- **OverlayFS home**: Writes to `$HOME` captured per-repo — real home never modified
- **Per-repo TMPDIR**: Isolated temp directory, no shared `/tmp`
- **Docker access**: Repo's `.envrc` auto-loaded for per-repo Docker socket
- **VS Code**: Each repo gets its own server installation — multiple repos simultaneously
- Use `--reset-home` on `rdc term` to clear per-repo home state

## Terminology

- "local adapter" / "cloud adapter" — never "modes"
- "Repository" = isolated application with its own Docker daemon and encrypted storage
- The CLI tool is `rdc`, not `rediacc`

## Documentation

- [Full docs](https://www.rediacc.com/llms.txt)
- [AI agent integration guide](https://www.rediacc.com/en/docs/ai-agents-overview)
- [MCP setup guide](https://www.rediacc.com/en/docs/ai-agents-mcp)
- [JSON output reference](https://www.rediacc.com/en/docs/ai-agents-json-output)
