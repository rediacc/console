/**
 * Per-repo env-mode secrets reach a remote shell as `REDIACC_SECRET_<NAME>`.
 * Their values never ride a command line (local argv, an external terminal's
 * argv, the remote `ps`), and the delivery needs nothing from the machine's
 * sshd (no `AcceptEnv`) nor from the local terminal (no inherited environment).
 *
 * The delivery is staged: one non-interactive ssh call runs
 * STAGE_SECRETS_COMMAND, which reads a script of `export NAME='value'` lines
 * from its stdin into a 0600 file inside a fresh 0700 directory (`mktemp -d`,
 * under the user's runtime directory, else `$TMPDIR`, else /tmp) and prints the
 * directory. The session's own remote command then starts with
 * consumeStagedSecrets(dir), which sources that file and deletes the directory
 * before anything else runs. A reaper started by the staging call deletes the
 * directory after STAGED_SECRETS_TTL_SECONDS if the session never starts.
 */

import { shellQuote } from './shell-quote.js';

const SECRET_ENV_PREFIX = 'REDIACC_SECRET_';

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * Seconds a staged secrets directory survives when no session consumes it.
 * The session deletes it itself on start, so this only reaps a session that
 * never began; it is long enough for an interactive passphrase or host-key
 * prompt between staging and the session (review 67e482c0.2). The session
 * kills the reaper when it consumes the file, and the reaper traps that kill
 * and stops its own sleep, so no sleeper outlives a started session
 * (reviews 2e951e55.4, 73f53020.1).
 */
export const STAGED_SECRETS_TTL_SECONDS = 600;

const STAGED_DIR_MARKER = 'RDC_STAGED_SECRETS=';

/**
 * A staged directory as STAGE_SECRETS_COMMAND prints it: absolute, ending in
 * `rdc-env.` plus mktemp's suffix. Any character but a newline or NUL may sit
 * in the parent ($TMPDIR or $XDG_RUNTIME_DIR can hold a space), since every use
 * shell-quotes the path (review 67e482c0.1); a `..` segment is refused.
 */
const STAGED_DIR = /^\/[^\n\0]*\/rdc-env\.[A-Za-z0-9]+$/;

function isSecretEnvName(name: string): boolean {
  return name.startsWith(SECRET_ENV_PREFIX);
}

/** Split an environment into the values a command line may carry and the secrets. */
export function splitSecretEnv(env: Record<string, string> | undefined): {
  plain: Record<string, string>;
  secrets: Record<string, string>;
} {
  const plain: Record<string, string> = {};
  const secrets: Record<string, string> = {};
  for (const [key, value] of Object.entries(env ?? {})) {
    if (isSecretEnvName(key)) secrets[key] = value;
    else plain[key] = value;
  }
  return { plain, secrets };
}

/**
 * The script a session sources to receive its secrets: one
 * `export NAME='value'` line per secret. A name that is not a valid shell
 * variable name cannot be exported, so it is skipped and `warn` receives the
 * name (never the value); the session still starts with the others. Returns
 * '' when nothing is left to deliver.
 */
export function secretExportScript(
  secrets: Record<string, string>,
  warn: (name: string) => void
): string {
  const lines: string[] = [];
  for (const [name, value] of Object.entries(secrets)) {
    if (!ENV_NAME.test(name)) {
      warn(name);
      continue;
    }
    lines.push(`export ${name}=${shellQuote(value)}\n`);
  }
  return lines.join('');
}

/**
 * The remote command of the staging call. POSIX sh, so it runs under the
 * sandbox gateway's `bash -c` and under any login shell alike. Under the
 * sandbox the runtime directory is outside the Landlock view, so `mktemp`
 * falls through to `$TMPDIR`, the repo's private tmp, which the session's
 * later connection sees again.
 */
export const STAGE_SECRETS_COMMAND = [
  'umask 077',
  `d=$(mktemp -d "\${XDG_RUNTIME_DIR:-/nonexistent}/rdc-env.XXXXXXXXXX" 2>/dev/null || mktemp -d "\${TMPDIR:-/tmp}/rdc-env.XXXXXXXXXX") || exit 1`,
  `cat > "$d/env" || { rm -rf "$d"; exit 1; }`,
  // The reaper traps the session's kill and stops its own sleep first, so killing the pid in "$d/reaper" ends both (review 73f53020.1).
  `(trap 'kill "$s" 2>/dev/null; exit 0' TERM; sleep ${STAGED_SECRETS_TTL_SECONDS} & s=$!; wait "$s"; rm -rf "$d") </dev/null >/dev/null 2>&1 &`,
  `echo $! > "$d/reaper"`,
  `printf '${STAGED_DIR_MARKER}%s\\n' "$d"`,
].join('\n');

/** The staged directory from the staging call's stdout, or undefined when it printed none. */
export function parseStagedSecretsDir(stdout: string): string | undefined {
  for (const line of stdout.split('\n')) {
    // Leading blanks and a carriage return are stripped (review 2e951e55.1); a trailing space belongs to the path.
    const trimmed = line.replace(/^[ \t]+/, '').replace(/\r$/, '');
    if (!trimmed.startsWith(STAGED_DIR_MARKER)) continue;
    const dir = trimmed.slice(STAGED_DIR_MARKER.length);
    const safe = STAGED_DIR.test(dir) && !dir.split('/').includes('..');
    return safe ? dir : undefined;
  }
  return undefined;
}

/**
 * The shell prefix that loads the staged secrets into a session and deletes
 * them, ahead of everything else in its remote command. A file that is gone
 * (the reaper won a very slow start) is reported on stderr, and the session
 * still opens.
 */
export function consumeStagedSecrets(dir: string): string {
  const quotedDir = shellQuote(dir);
  const file = shellQuote(`${dir}/env`);
  const reaper = shellQuote(`${dir}/reaper`);
  return `if [ -r ${file} ]; then . ${file}; else echo 'rdc: the repository secrets did not reach this session' >&2; fi; [ -r ${reaper} ] && kill "$(cat ${reaper})" 2>/dev/null; rm -rf -- ${quotedDir}; `;
}
