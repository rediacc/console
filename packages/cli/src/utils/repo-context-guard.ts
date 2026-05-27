export interface RepoContextPattern {
  label: string;
  pattern: RegExp;
}

export const REPO_CONTEXT_PATTERNS: RepoContextPattern[] = [
  { label: 'docker', pattern: /\bdocker\b/i },
  { label: 'docker-compose', pattern: /\bdocker-compose\b/i },
  { label: 'DOCKER_HOST', pattern: /\bDOCKER_HOST=/ },
  { label: 'repo docker socket', pattern: /\/var\/run\/rediacc\/docker-/ },
  { label: 'renet compose', pattern: /\brenet\s+compose\b/i },
  { label: 'repo mount path', pattern: /\/mnt\/rediacc\/mounts\/[0-9a-f-]{36}/i },
];

/**
 * Detects if a command requires repository context (DOCKER_HOST, repo env vars).
 * Returns the first matching pattern or null if the command is safe for machine-level execution.
 */
export function detectRepoContextCommand(command: string): RepoContextPattern | null {
  for (const entry of REPO_CONTEXT_PATTERNS) {
    if (entry.pattern.test(command)) {
      return entry;
    }
  }
  return null;
}

// Wrapper tokens that prefix another command without being the command
// themselves. We skip past them (plus their -flags / VAR=val args) to find the
// real command word of a segment, so `sudo docker compose` is still caught.
const COMMAND_PREFIXES = new Set([
  'sudo',
  'env',
  'nice',
  'nohup',
  'time',
  'command',
  'exec',
  'doas',
]);

/**
 * Flags that take a VALUE argument for each wrapper prefix.
 * Without this, `sudo -u root docker compose up` would treat `root` as the
 * command and miss the docker-compose guard.
 */
const PREFIX_FLAGS_WITH_ARGS: Record<string, Set<string>> = {
  sudo: new Set([
    '-u',
    '--user',
    '-g',
    '--group',
    '-p',
    '--prompt',
    '-c',
    '--class',
    '-C',
    '--close-from',
    '-R',
    '--chroot',
  ]),
  env: new Set(['-u', '--unset', '-C', '--chdir']),
  nice: new Set(['-n', '--adjustment']),
  time: new Set(['-o', '--output', '-f', '--format']),
  exec: new Set(['-a']),
};

/** Strip a leading path from a command token: `/usr/bin/docker` -> `docker`. */
function basename(token: string): string {
  return token.replace(/^.*\//, '');
}

/**
 * Consume one flag token (and its value token when applicable). Returns the
 * updated index after consuming the flag (and optional value).
 */
function consumeFlag(tokens: string[], i: number, flagsWithArgs: Set<string>): number {
  const tok = tokens[i];
  const eqPos = tok.indexOf('=');
  // `--flag=value` embeds the value; `--flag value` has a separate next token.
  const flagPart = eqPos === -1 ? tok : tok.slice(0, eqPos);
  i++;
  // Flag takes a separate value token: consume it when the next token is a plain value.
  const hasNextValue =
    eqPos === -1 && flagsWithArgs.has(flagPart) && i < tokens.length && !tokens[i].startsWith('-');
  return hasNextValue ? i + 1 : i;
}

function skipPrefixArgs(tokens: string[], start: number, flagsWithArgs: Set<string>): number {
  let i = start;
  while (i < tokens.length) {
    const tok = tokens[i];
    if (tok.startsWith('-')) {
      i = consumeFlag(tokens, i, flagsWithArgs);
      continue;
    }
    if (/^\w+=/.test(tok)) {
      i++; // env assignment passed to the wrapper (e.g. `sudo FOO=bar cmd`)
      continue;
    }
    break; // not a flag or assignment — this is the real command
  }
  return i;
}

/**
 * Resolve the command words of a single shell segment: drop leading env-var
 * assignments (`FOO=bar`) and wrapper prefixes (`sudo`, `env`, ...) along with
 * their flags and flag values, leaving the actual command word first.
 */
function segmentCommandWords(segment: string): string[] {
  const tokens = segment.trim().split(/\s+/).filter(Boolean);
  let i = 0;
  while (i < tokens.length) {
    if (/^\w+=/.test(tokens[i])) {
      i++; // leading env assignment
      continue;
    }
    const prefixName = basename(tokens[i]).toLowerCase();
    if (COMMAND_PREFIXES.has(prefixName)) {
      i++; // consume the wrapper prefix itself
      const flagsWithArgs = PREFIX_FLAGS_WITH_ARGS[prefixName] ?? new Set<string>();
      i = skipPrefixArgs(tokens, i, flagsWithArgs);
      continue;
    }
    break;
  }
  return tokens.slice(i);
}

/**
 * Detects `docker compose` / `docker-compose` *invocation* in repository
 * context, which must be blocked because `renet compose` is a preprocessor that
 * injects per-repo loopback IPs, host network mode, CRIU capabilities, and
 * compose validation — bypassing it silently corrupts the deployment.
 *
 * Matches the command being run, NOT substrings in arguments/filenames: each
 * shell segment (split on `;`, `&&`, `||`, `|`, `&`, newline) is inspected at
 * its command position, so `cat docker-compose.yml`, `find -iname
 * 'docker-compose*'`, and `grep compose docker-compose.yml` are allowed while
 * `docker compose up`, `sudo docker-compose down`, and
 * `FOO=bar docker compose up` are still blocked (rediacc/console#490).
 *
 * Known limitation: docker-compose nested inside an opaque `bash -c "..."`
 * string is not matched — the server-side sandbox and per-repo DOCKER_HOST are
 * the real enforcement; this guard is an ergonomic guardrail.
 */
export function detectDockerComposeCommand(command: string): boolean {
  for (const segment of command.split(/&&|\|\||[;&|\n]/)) {
    const words = segmentCommandWords(segment);
    if (words.length === 0) continue;
    const cmd = basename(words[0]).toLowerCase();
    if (cmd === 'docker-compose') return true;
    if (cmd === 'docker' && words[1]?.toLowerCase() === 'compose') return true;
  }
  return false;
}

export interface RenetCommandMatch {
  renetCommand: string;
  cliHelpCommand: string;
}

const RENET_CLI_EQUIVALENTS: { pattern: RegExp; renetCommand: string; cliHelpCommand: string }[] = [
  {
    pattern: /\brenet\s+repository\b/,
    renetCommand: 'renet repository',
    cliHelpCommand: 'rdc repo --help',
  },
  {
    pattern: /\brenet\s+backup\b/,
    renetCommand: 'renet backup',
    cliHelpCommand: 'rdc repo backup --help',
  },
  {
    pattern: /\brenet\s+daemon\b/,
    renetCommand: 'renet daemon',
    cliHelpCommand: 'rdc repo --help',
  },
  {
    pattern: /\brenet\s+datastore\b/,
    renetCommand: 'renet datastore',
    cliHelpCommand: 'rdc machine --help',
  },
  {
    pattern: /\brenet\s+network\b/,
    renetCommand: 'renet network',
    cliHelpCommand: 'rdc machine --help',
  },
];

/**
 * Detects if a command runs a renet subcommand that has a CLI equivalent.
 * Matches both `renet <cmd>` and `sudo renet <cmd>` patterns.
 */
export function detectDirectRenetCommand(command: string): RenetCommandMatch | null {
  for (const entry of RENET_CLI_EQUIVALENTS) {
    if (entry.pattern.test(command)) {
      return { renetCommand: entry.renetCommand, cliHelpCommand: entry.cliHelpCommand };
    }
  }
  return null;
}

// ─── File-write detection ──────────────────────────────────────────────

export interface FileWriteMatch {
  label: string;
  pattern: RegExp;
}

/**
 * Patterns that indicate a command is writing data to a file on the remote
 * machine. When detected inside `rdc term connect -c`, we suggest
 * `rdc repo sync upload` instead (rsync, delta transfer, proper permissions).
 *
 * Conservative by design — false positives are worse than missed cases:
 *   - `tee somefile` matches, `tee --help` and `tee /dev/null` don't
 *   - `cat > file` matches, `cat /etc/hostname` (read) doesn't
 *   - `echo "x" > f` matches, `echo hello | grep x` doesn't
 *   - `2>/dev/null` and `2>&1` are excluded via negative lookahead
 */
export const FILE_WRITE_PATTERNS: FileWriteMatch[] = [
  // `tee somefile` — but not `tee -a`, `tee --help`, `tee /dev/null`
  { label: 'tee', pattern: /\btee\s+(?!-)(?!\/dev\/null\b)\S/ },
  // `cat > file`, `echo "x" > out`, `printf '%s' > f`, `base64 -d > /tmp/x`
  // The [^|;&]* stops at pipe/semicolon so `echo hi | grep x` doesn't match.
  // (?!\/dev\/null) and (?!&) exclude `>/dev/null` and `>&` (fd redirects).
  {
    label: 'redirect',
    pattern: /\b(cat|echo|printf|base64)\b[^|;&]*>>?\s*(?!\/dev\/null\b)(?!&)\S/,
  },
];

/**
 * Detects file-write patterns in a shell command string.
 *
 * Skipped entirely when `REDIACC_SKIP_FILE_WRITE_GUARD=1` is set — used by
 * the rotation tool (`rotate.ts:runOnObservability`) which legitimately
 * writes `.env` files via `base64 -d > file` through `rdc term connect`.
 */
export function detectFileWriteCommand(command: string): FileWriteMatch | null {
  if (process.env.REDIACC_SKIP_FILE_WRITE_GUARD === '1') return null;
  for (const entry of FILE_WRITE_PATTERNS) {
    if (entry.pattern.test(command)) {
      return entry;
    }
  }
  return null;
}
