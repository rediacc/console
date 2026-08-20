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

import { debugEnabled } from '../../utils/debug.js';
import { terminalWidth, wrapProse } from '../core/output.js';

/** `[<function>] ` as emitted by renet's output relay. */
const RELAY_PREFIX_RE = /^\s*\[[A-Za-z_][A-Za-z0-9_]*\]\s?/;

/** logrus structured-log lines, which renet writes on the same streams. */
const LOGRUS_LEVEL_RE = /\blevel=(?:info|warn|warning|error|debug|fatal|trace)\b/;
const LOGRUS_LINE_PREFIX = 'time="';
/** The levels a reader must always see, even when the rest is withheld. */
const LOGRUS_LOUD_RE = /\blevel=(?:warn|warning|error|fatal|panic)\b/;

/** Remove renet's `[<function>] ` relay prefix, if the line carries one. */
export function stripRelayPrefix(line: string): string {
  return line.replace(RELAY_PREFIX_RE, '');
}

/** Whether the line is renet's own structured logging rather than program output. */
export function isLogrusLine(line: string): boolean {
  return line.startsWith(LOGRUS_LINE_PREFIX) || LOGRUS_LEVEL_RE.test(line);
}

/**
 * Whether a relayed line is logrus noise that can be WITHHELD from a live
 * terminal: structured, and below warning.
 *
 * Splitting "is logrus" from "is quiet enough to hide" matters because hiding
 * everything was tried and broke failure diagnosis -- a renet child exited 1 and
 * every explanatory line was info-level. Callers withhold these and flush them
 * only when the job actually fails.
 */
function isQuietLogrusLine(line: string): boolean {
  return isLogrusLine(line) && !LOGRUS_LOUD_RE.test(line);
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

/** Cap on withheld lines: a failing command's tail is what explains it. */
const WITHHELD_LIMIT = 200;
/** A chunk starting with this may be a logrus line split across two reads. */
const LOGRUS_PARTIAL_PREFIX = 'time="';

/**
 * Write one diagnostic to stderr, wrapped to the terminal.
 *
 * There are TWO withhold-and-replay buffers in the CLI (this module's pump for
 * the direct path, and the daemon client's deferredLogs), and the first fix
 * wrapped only one of them, so a 115-column logrus line still shipped in a
 * recorded tutorial. One helper, used by both, is what stops a third copy from
 * drifting the same way.
 *
 * A replayed line is being read by a human, and at 115-358 columns an unwrapped
 * one is wrapped by the TERMINAL instead, which interleaves it with the row
 * below and shreds the layout.
 */
export function writeWrappedToStderr(line: string): void {
  for (const row of wrapProse(line, terminalWidth())) process.stderr.write(`${row}\n`);
}

/**
 * A stderr pump that WITHHOLDS renet's info/debug chatter and replays it only if
 * the operation failed.
 *
 * Every place the CLI streams renet's stderr live used to be a raw byte pump
 * (`process.stderr.write(data)`), and there are seven of them. That put
 * 227-358 column logrus lines on the terminal and into every tutorial
 * recording. Dropping the lines outright is NOT the fix and was tried: a renet
 * child exited 1 and every explanatory line was info-level, so the failure
 * became unreadable. Hence withhold-and-replay, in one place so the seven
 * cannot drift apart.
 *
 * Spinner and progress repaints carry no newline, so a tail without one is
 * passed straight through -- holding it would freeze the animation on screen.
 */
/**
 * Should renet's relayed stderr be echoed LIVE rather than withheld?
 *
 * TRUE for the env var OR the `--debug` flag. Extracted from the call site
 * because an inline expression there was UNPINNABLE: a peer proved the point by
 * reverting the flag half and re-running the pump tests, which stayed green 5/5.
 * The pump's own contract was covered; the decision feeding it was not, so the
 * regression could return through that one line with nothing going red.
 *
 * The regression it exists to stop: `debugEnabled()` reads only REDIACC_DEBUG,
 * so `rdc repo up --debug` still withheld info-level lines. The
 * concurrent-fork-isolation suite greps a `--debug` log for renet's
 * "restored from checkpoint" (log.Infof), found nothing, and reported
 * console#440 as regressed when the checkpoint had in fact worked.
 */
export function shouldEchoRelayLive(options: { debug?: boolean } = {}): boolean {
  return debugEnabled() || Boolean(options.debug);
}

export function createQuietStderrPump(options: { echoAll?: boolean } = {}) {
  const echoAll = options.echoAll ?? false;
  const withheld: string[] = [];
  let pending = '';

  return {
    write(chunk: string): void {
      pending += chunk;
      let nl = pending.indexOf('\n');
      while (nl !== -1) {
        const line = pending.slice(0, nl);
        pending = pending.slice(nl + 1);
        if (!echoAll && isQuietLogrusLine(line)) {
          withheld.push(line);
          if (withheld.length > WITHHELD_LIMIT) withheld.shift();
        } else {
          process.stderr.write(`${line}\n`);
        }
        nl = pending.indexOf('\n');
      }
      if (pending && !pending.startsWith(LOGRUS_PARTIAL_PREFIX)) {
        process.stderr.write(pending);
        pending = '';
      }
    },
    /** Call once the outcome is known. On failure the withheld lines are replayed. */
    flush(failed: boolean): void {
      if (pending) {
        if (echoAll || !isQuietLogrusLine(pending)) process.stderr.write(pending);
        pending = '';
      }
      // WRAPPED on replay. These are 115-358 columns wide, and the moment they
      // are replayed a human is reading them: an unwrapped line is wrapped by
      // the TERMINAL instead, which interleaves it with the row below and
      // shreds the layout. `run_cmd_expect_fail` demos in the tutorials are
      // exactly this path - there the failure IS the demo, so the diagnostic is
      // on camera and has to be legible.
      if (failed) for (const line of withheld) writeWrappedToStderr(line);
      withheld.length = 0;
    },
  };
}

/**
 * Is this relay line renet's MACHINE-READABLE protocol rather than something a
 * human is meant to read?
 *
 * renet emits a handful of whole-line JSON objects on stdout for the CLI to
 * parse - `{"push_result":...}`, `{"steps":[...]}`, the `repo log` envelope, the
 * `repo admin autostart` record. The CLI reads them from CAPTURED stdout, which
 * is collected separately from rendering, so dropping them from the human stream
 * costs nothing and `extractPushResult` keeps working.
 *
 * Left on camera they are 322 to 400 columns wide and wrap into unreadable
 * ribbon across every terminal narrower than that, which is exactly what the
 * recorded tutorials showed.
 *
 * The rule is deliberately structural rather than a key allowlist: renet's
 * human-facing output is never a bare JSON object, so "the whole line parses as
 * a JSON object" identifies the protocol without needing to enumerate every
 * payload shape and go stale the next time one is added. Arrays and scalars do
 * NOT count - a command whose answer genuinely is JSON reaches the user through
 * the passthrough handler, which does not consult this.
 */
export function isMachineReadableRelayLine(line: string): boolean {
  const trimmed = stripRelayPrefix(line).trim();
  // The brace test is what excludes arrays and scalars: anything that both
  // starts with `{` and parses as JSON IS an object, so a further
  // `typeof parsed === 'object'` check would be unreachable. It was written
  // that way first and a mutation test proved the extra condition could never
  // be false.
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return false;
  try {
    JSON.parse(trimmed);
    return true;
  } catch {
    return false;
  }
}
