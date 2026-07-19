/**
 * Line-level cleanup for renet's relayed output.
 *
 * `renet functions once` RELAYS the inner process's stdout/stderr line by line
 * with a `[<function>] ` prefix (see renet `pkg/functions/executor_local.go`
 * `scanAndReport`), interleaved with its own logrus lines. Three consumers need
 * to undo that framing, and each used to carry its own copy of the regexes:
 * `parseCapturedJson` (JSON payloads), `cleanOutputLines` (failure-message
 * extraction), and the passthrough stdout handler (`repo exec` / `repo logs` /
 * `run`, whose output IS the answer).
 *
 * The prefix pattern matches ONLY a bridge-function relay prefix, `[<name>] `
 * with `<name>` a snake_case identifier, never a JSON array. A looser `[^\]]+`
 * form ate a whole single-line array payload `[{...},{...}]` (whose only `]` is
 * the closing bracket); anchoring to an identifier fixes that, because a JSON
 * array's first character after `[` is never an identifier character.
 */

/** `[<function>] ` as emitted by renet's output relay. */
const RELAY_PREFIX_RE = /^\s*\[[A-Za-z_][A-Za-z0-9_]*\]\s?/;

/** logrus structured-log lines, which renet writes on the same streams. */
const LOGRUS_LEVEL_RE = /\blevel=(?:info|warn|warning|error|debug|fatal|trace)\b/;
const LOGRUS_LINE_PREFIX = 'time="';

/** Remove renet's `[<function>] ` relay prefix, if the line carries one. */
export function stripRelayPrefix(line: string): string {
  return line.replace(RELAY_PREFIX_RE, '');
}

/** Whether the line is renet's own structured logging rather than program output. */
export function isLogrusLine(line: string): boolean {
  return line.startsWith(LOGRUS_LINE_PREFIX) || LOGRUS_LEVEL_RE.test(line);
}

/**
 * Reduce one relayed line to the inner process's own bytes, or `undefined` when
 * the line is renet's noise rather than program output.
 *
 * Deliberately does NOT drop JSON-shaped lines the way `cleanOutputLines` does:
 * container logs are frequently structured JSON, and dropping them here would
 * re-create the very bug this module exists to fix (`repo logs` printing
 * nothing). Callers that need the JSON-dropping behavior apply it themselves.
 */
export function cleanRelayLine(line: string): string | undefined {
  if (isLogrusLine(line)) return undefined;
  return stripRelayPrefix(line);
}
