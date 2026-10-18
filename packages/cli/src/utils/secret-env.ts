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

/** Seconds a staged secrets directory survives when no session consumes it. */
export const STAGED_SECRETS_TTL_SECONDS = 120;

const STAGED_DIR_MARKER = 'RDC_STAGED_SECRETS=';

/** A staged directory as STAGE_SECRETS_COMMAND prints it: absolute, `rdc-env.` plus mktemp's suffix. */
const STAGED_DIR = /^\/[A-Za-z0-9._/-]*\/rdc-env\.[A-Za-z0-9]+$/;

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
  `(sleep ${STAGED_SECRETS_TTL_SECONDS}; rm -rf "$d") </dev/null >/dev/null 2>&1 &`,
  `printf '${STAGED_DIR_MARKER}%s\\n' "$d"`,
].join('\n');

/** The staged directory from the staging call's stdout, or undefined when it printed none. */
export function parseStagedSecretsDir(stdout: string): string | undefined {
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith(STAGED_DIR_MARKER)) continue;
    const dir = trimmed.slice(STAGED_DIR_MARKER.length);
    return STAGED_DIR.test(dir) ? dir : undefined;
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
  return `if [ -r ${file} ]; then . ${file}; else echo 'rdc: the repository secrets did not reach this session' >&2; fi; rm -rf -- ${quotedDir}; `;
}
