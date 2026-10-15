/**
 * How a renet invocation is wrapped in sudo with its environment, keeping
 * every secret off the command line. Dependency-free (shell quoting only), so
 * job-client.ts can build its launch without the executor's config plumbing.
 */

import { shellQuote } from '../../utils/shell-quote.js';

/**
 * The environment of a renet subprocess launched over SSH, in two parts.
 *
 * `prefix` holds the non-secret settings as an `env K=V ` command prefix
 * (trailing space, or '' when empty); they are harmless in `ps`. `secrets`
 * holds the OTLP credentials and the per-repo env-mode secrets, which never
 * ride a command line: `sudoRenet` delivers them on stdin ahead of the vault.
 */
export interface RenetEnv {
  prefix: string;
  secrets: Record<string, string>;
}

/** A remote command plus the bytes that must precede the payload on its stdin. */
export interface RenetLaunch {
  command: string;
  /** Written to the command's stdin before the vault (or alone, with no vault). */
  stdinPrefix: string;
}

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * The launcher a secret-carrying renet runs under: root bash reads
 * NUL-terminated `NAME=value` records from stdin until an empty record,
 * exports each, then execs the renet invocation, which inherits the rest of
 * stdin (the vault) untouched, because bash reads a pipe one byte at a time.
 * Values may hold any byte but NUL, which no environment value can hold.
 */
const STDIN_ENV_READER = `while IFS= read -r -d '' kv && [ -n "$kv" ]; do export "$kv"; done; exec `;

/**
 * Wrap a renet invocation (`<path> <subcommand> ...`) in sudo with its
 * environment. Without secrets this is the plain `sudo env K=V renet ...`
 * form. With secrets the values travel on stdin (`stdinPrefix`), so neither
 * the local SSH argv nor the machine's `ps` ever carries them; renet still
 * reads them from its environment, unchanged.
 */
export function sudoRenet(env: RenetEnv, invocation: string): RenetLaunch {
  const entries = Object.entries(env.secrets);
  if (entries.length === 0) {
    return { command: `sudo ${env.prefix}${invocation}`, stdinPrefix: '' };
  }
  for (const [name, value] of entries) {
    if (!ENV_NAME.test(name)) throw new Error(`Invalid environment variable name: ${name}`);
    if (value.includes('\0')) throw new Error(`Environment value for ${name} contains a NUL byte`);
  }
  const stdinPrefix = `${entries.map(([name, value]) => `${name}=${value}\0`).join('')}\0`;
  const script = `${STDIN_ENV_READER}${env.prefix}${invocation}`;
  return { command: `sudo bash -c ${shellQuote(script)}`, stdinPrefix };
}
