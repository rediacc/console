/**
 * POSIX single-quote escaping, for building a remote shell command safely.
 *
 * This is the ONE implementation. There used to be five byte-identical copies
 * (executor, renet binary transfer, backup schedule, sftp helpers), which is the
 * shape of hazard where one copy gets an escaping fix and the others silently do
 * not.
 */

/**
 * Quote a single argument so a POSIX shell reads it as exactly one literal word.
 *
 * Wraps in `'...'` and rewrites embedded single quotes as `'\''` (close, escaped
 * quote, reopen), which is safe for every byte including newlines and `$`.
 *
 * Quote each argument SEPARATELY and join with spaces. Quoting an
 * already-joined command string turns the whole thing into one literal word.
 */
export function shellQuote(arg: string): string {
  return `'${arg.replaceAll("'", "'\\''")}'`;
}
