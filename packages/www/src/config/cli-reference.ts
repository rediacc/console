/**
 * Single source of truth for CLI reference content used across llms.txt,
 * inline LLM scripts, and documentation. Update this file when CLI commands,
 * flags, or the JSON envelope format change.
 */

export const CLI_TOOL = 'rdc';
export const CLI_INSTALL = 'curl -fsSL https://www.rediacc.com/install.sh | bash';

export const CLI_FLAGS = [
  { flag: '--output json', alias: '-o json', description: 'machine-readable JSON output' },
  { flag: '--yes', alias: '-y', description: 'skip interactive confirmations' },
  { flag: '--quiet', alias: '-q', description: 'suppress informational output' },
  { flag: '--fields name,status', description: 'limit output fields' },
  { flag: '--dry-run', description: 'preview destructive operations without executing' },
] as const;

export const CLI_COMMANDS = {
  deploy: `${CLI_TOOL} repo up <repo> -m <machine> --yes`,
  status: `${CLI_TOOL} machine info <machine> -o json`,
  containers: `${CLI_TOOL} machine containers <machine> -o json`,
  ssh: `${CLI_TOOL} term <machine> [repo]`,
  health: `${CLI_TOOL} machine health <machine> -o json`,
  capabilities: `${CLI_TOOL} agent capabilities`,
} as const;

export const JSON_ENVELOPE =
  '{"success": true, "command": "...", "data": ..., "errors": null, "warnings": [], "metrics": {"duration_ms": N}}';

export const TERMINOLOGY = [
  '"local adapter" / "cloud adapter" — never "modes"',
  '"Repository" = isolated application with its own Docker daemon and encrypted storage',
] as const;

/** Auto-JSON note for LLM context */
export const AUTO_JSON_NOTE = 'Auto-JSON: output defaults to JSON when piped (non-TTY)';
