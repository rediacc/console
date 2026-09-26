/**
 * Reading what a `renet execute` run printed: its step timeline, the failure
 * reason worth surfacing, captured JSON, and the stdout handlers that render
 * it live.
 */

import { formatStepDuration, getActiveLabel, getDoneLabel } from '../../utils/timeline.js';
import { outputService } from '../core/output.js';
import { writeStderr, writeStdout } from '../core/request-context.js';
import type { JobOutputCollector } from './job-client.js';
import { cleanRelayLine, isLogrusLine, stripRelayPrefix } from './output-lines.js';
import type { ExecuteOptions, RenetEvent } from './types.js';

type StepEntry = { name: string; duration_ms: number; detail?: string };

/** Try to extract steps from a single parsed JSON object. */
function collectStepsFromParsed(parsed: Record<string, unknown>, steps: StepEntry[]): void {
  if (parsed.step_done && typeof parsed.step_done === 'object') {
    const step = parsed.step_done as StepEntry;
    if (step.name && typeof step.duration_ms === 'number') {
      steps.push(step);
    }
  }
  if (Array.isArray(parsed.steps) && parsed.steps.length > 0) {
    steps.push(...(parsed.steps as StepEntry[]));
  }
}

/** Extract step timing from renet's combined stdout+stderr output. */
export function extractStepsFromOutput(output: string): StepEntry[] | undefined {
  const steps: StepEntry[] = [];

  for (const rawLine of output.split('\n')) {
    const line = rawLine.trim();
    const jsonStart = line.indexOf('{');
    if (jsonStart < 0) continue;
    try {
      const parsed = JSON.parse(line.slice(jsonStart)) as Record<string, unknown>;
      collectStepsFromParsed(parsed, steps);
    } catch {
      // Not valid JSON, continue
    }
  }

  return steps.length > 0 ? steps : undefined;
}

const MAX_FAILURE_REASON_CHARS = 300;

// Parser patterns for renet output lines, not user-facing strings.
const COBRA_ERROR_PREFIX = 'Error: ';
const LOGRUS_LINE_PREFIX = 'time="';

/**
 * Build the non-zero-exit error message, including renet's actual failure
 * reason when one is available. Without this the operator only sees
 * "renet exited with code 1" while the real cause ("repository X is not
 * mounted") sits unprinted in the captured output. The bridge relays the
 * inner command's streams into stdout (with a `[function] ` prefix) while
 * its own logrus noise lands in stderr, so the cobra "Error: ..." line is
 * searched across BOTH streams before any last-line fallback.
 */
export function buildRenetExitError(exitCode: number, stderr: string, stdout: string): string {
  const base = `renet exited with code ${exitCode}`;
  const reason =
    extractErrorLine(stderr) ??
    extractErrorLine(stdout) ??
    lastInformativeLine(stderr) ??
    lastInformativeLine(stdout);
  return reason ? `${base}: ${capReason(reason)}` : base;
}

/**
 * Echo renet's full output to stderr on a non-capture failure, so the operator
 * sees the real reason rather than a bare exit code. Returns whether it echoed,
 * so failure renderers downstream do not repeat what was already printed.
 */
export function echoRenetFailure(
  exitCode: number,
  combined: string,
  options: ExecuteOptions
): boolean {
  if (exitCode === 0 || options.debug || options.captureOutput) return false;
  const output = combined.trim();
  if (!output) return false;
  writeStderr(`\n--- renet output (exit code ${exitCode}) ---\n`);
  writeStderr(`${output}\n`);
  writeStderr('---\n\n');
  return true;
}

/**
 * Surface renet's WARNINGS on a SUCCESSFUL run.
 *
 * renet's output is otherwise echoed only on failure (above) or under --debug, so a
 * command that succeeded while warning that it had silently skipped half its job said
 * nothing at all to the operator, which is how a datastore could report "attached"
 * while its CSI enablement had been skipped and every future PVC would hang Pending
 * (#86). A warning nobody can see is not a warning.
 *
 * Warnings are rare by construction (a full `cluster create` emits one), so this is not
 * a noise channel: renet uses log.Warn for "the thing is done, and the operator needs to
 * know something", which is exactly what an operator must read.
 */
export function surfaceRenetWarnings(
  exitCode: number,
  combined: string,
  options: ExecuteOptions
): void {
  if (exitCode !== 0 || options.debug) return; // failures echo everything; debug already shows it
  for (const line of combined.split('\n')) {
    if (!line.includes('level=warning')) continue;
    // logrus renders the payload as msg="..."; fall back to the raw line if it does not.
    const msg = /msg="((?:[^"\\]|\\.)*)"/
      .exec(line)?.[1]
      ?.replaceAll('\\"', '"')
      .replaceAll('\\\\', '\\');
    outputService.warn(msg ?? line.trim());
  }
}

/**
 * Parse a JSON payload out of a captured bridge stdout. A bridge function that
 * SHELLS OUT to a sub-`renet` command (e.g. datastore_list ->
 * `renet datastore list --json`, ceph_client_config_export ->
 * `renet ceph client config export --json`) has its sub-process stdout RELAYED
 * by `renet functions once` with a `[function] ` line prefix, so the captured
 * `result.stdout` is `[datastore_list] [ ... ]`, not raw JSON, a plain
 * `JSON.parse` dies with `Unexpected token '['/'{'`. Strip the relay prefix per
 * line, then extract the JSON object/array payload (first `{`/`[` to its matching
 * last `}`/`]`), tolerating interleaved logrus lines outside the payload.
 * `cleanOutputLines` cannot be reused here, it deliberately DROPS JSON lines.
 *
 * The prefix strip matches ONLY a bridge-function relay prefix, `[<name>] ` with
 * `<name>` a snake_case identifier, never a JSON array. An earlier `[^\]]+`
 * strip ate a whole single-line array payload `[{...},{...}]` (whose only `]` is
 * the closing bracket), turning a valid `datastore list --json` capture into "no
 * JSON payload"; anchoring to an identifier fixes that (a JSON array's first char
 * after `[` is never an identifier char).
 */
export function parseCapturedJson<T>(stdout: string | undefined): T {
  const stripped = (stdout ?? '')
    .split('\n')
    .map(stripRelayPrefix)
    // Drop renet logrus lines (`time="..." level=... msg="..."`) BEFORE the
    // payload scan: their messages carry stray brackets (e.g. a "[detached]"
    // fork message) that would otherwise be mistaken for the start of a JSON
    // array. The JSON payload itself never matches this shape.
    .filter((line) => !isLogrusLine(line))
    .join('\n');
  const start = stripped.search(/[[{]/);
  if (start === -1) {
    throw new Error(`no JSON payload in captured output: ${(stdout ?? '').slice(0, 160)}`);
  }
  const close = stripped[start] === '{' ? '}' : ']';
  const end = stripped.lastIndexOf(close);
  if (end < start) {
    throw new Error(`unterminated JSON payload in captured output: ${stripped.slice(start, 160)}`);
  }
  return JSON.parse(stripped.slice(start, end + 1)) as T;
}

/** Strip bridge `[function] ` prefixes and drop empty lines and JSON
 * fragments (multi-line JSON yields lines starting with braces, brackets, or
 * quoted keys). The JSON-fragment drop is specific to failure-message
 * extraction and is why `cleanRelayLine` cannot simply replace this. */
function cleanOutputLines(output: string): string[] {
  return output
    .split('\n')
    .map((line) => stripRelayPrefix(line).trim())
    .filter((line) => line.length > 0 && !/^[{}\][",]/.test(line));
}

/** The last cobra-style "Error: ..." line, without the prefix. */
function extractErrorLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => line.startsWith(COBRA_ERROR_PREFIX))
    .at(-1)
    ?.slice(COBRA_ERROR_PREFIX.length)
    .trim();
}

/** The last line that isn't structured-log noise (`time="..." level=...`). */
function lastInformativeLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => !line.startsWith(LOGRUS_LINE_PREFIX))
    .at(-1);
}

export function capReason(reason: string): string {
  return reason.length > MAX_FAILURE_REASON_CHARS
    ? `${reason.slice(0, MAX_FAILURE_REASON_CHARS)}…`
    : reason;
}

/**
 * A stdout sink. `flush` exists because the line-buffered handlers hold a
 * trailing partial line: a stream that ends without a final newline (a killed
 * `--follow`, a command whose last line has no `\n`) would otherwise drop it.
 */
type StdoutHandler = ((data: Buffer) => void) & { flush?: () => void };

/** Handle NDJSON events from renet in events mode. */
function handleEventsStdout(onEvent: (event: RenetEvent) => void): StdoutHandler {
  let lineBuffer = '';
  return (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split('\n');
    lineBuffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event = JSON.parse(trimmed) as RenetEvent;
        onEvent(event);
      } catch {
        writeStdout(`${line}\n`);
      }
    }
  };
}

/**
 * Render real-time step events from a single parsed JSON object.
 *
 * `write` exists so passthrough commands can send progress to STDERR: for
 * `repo exec`/`repo logs` stdout is the command's data, and a `✔ Provisioning
 * renet (2.0s)` line landing in `$(rdc repo exec …)` is corruption, not progress.
 */
function renderStepEvent(
  parsed: Record<string, unknown>,
  write: (text: string) => void = writeStdout
): void {
  if (parsed.step_start && typeof parsed.step_start === 'object') {
    const s = parsed.step_start as { name?: string };
    if (s.name) write(`⠋ ${getActiveLabel(s.name)}...`);
  } else if (parsed.step_done && typeof parsed.step_done === 'object') {
    const s = parsed.step_done as { name?: string; duration_ms?: number };
    if (s.name && s.duration_ms != null) {
      write(`\r✔ ${getDoneLabel(s.name)} (${formatStepDuration(s.duration_ms)})\n`);
    }
  }
}

/** Handle stdout in non-events, non-capture mode: detect step events and render them. */
function handleStepDetectionStdout(): StdoutHandler {
  let stepLineBuffer = '';
  return (data: Buffer) => {
    stepLineBuffer += data.toString();
    const stepLines = stepLineBuffer.split('\n');
    stepLineBuffer = stepLines.pop() ?? '';
    for (const sl of stepLines) {
      const trimmed = sl.trim();
      const jsonIdx = trimmed.indexOf('{');
      if (jsonIdx < 0) continue;
      try {
        const p = JSON.parse(trimmed.slice(jsonIdx)) as Record<string, unknown>;
        renderStepEvent(p);
      } catch {
        /* not JSON, ignore */
      }
    }
  };
}

/**
 * Stream the inner process's own output live, minus renet's relay scaffolding.
 *
 * This is what makes `repo exec`, `repo logs` and `run -f` print anything at
 * all: the default handler below detects step events and DROPS every other
 * line, which is right for `repo up`/`fork`/`push` (renet's chatter is noise
 * there) and exactly wrong for the three verbs whose output is the answer.
 *
 * Line-buffered rather than accumulate-then-print, because `repo logs --follow`
 * must emit each line as it completes. Step-event lines are swallowed, not
 * printed: leaking a `{"step_done":...}` line would poison `$(rdc repo exec …)`.
 */
function handlePassthroughStdout(renderSteps: boolean): StdoutHandler {
  let lineBuffer = '';

  const emit = (line: string): void => {
    const trimmed = line.trim();
    const jsonIdx = trimmed.indexOf('{');
    if (jsonIdx >= 0) {
      try {
        const parsed = JSON.parse(trimmed.slice(jsonIdx)) as Record<string, unknown>;
        if (parsed.step_start || parsed.step_done) {
          // Progress to stderr, never stdout: stdout belongs to the command.
          if (renderSteps) renderStepEvent(parsed, writeStderr);
          return;
        }
      } catch {
        /* not a step event, fall through and print it */
      }
    }
    // writeStdout, not process.stdout: inside the MCP/serve dispatch context this output belongs to ONE request's envelope, and writing to the process stream would interleave concurrent tenants' command output.
    const cleaned = cleanRelayLine(line);
    if (cleaned !== undefined) writeStdout(`${cleaned}\n`);
  };

  const handler: StdoutHandler = (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split('\n');
    lineBuffer = lines.pop() ?? '';
    for (const line of lines) emit(line);
  };
  handler.flush = () => {
    if (!lineBuffer) return;
    const tail = lineBuffer;
    lineBuffer = '';
    emit(tail);
  };
  return handler;
}

/** Create the appropriate stdout handler based on execution options. */
export function createStdoutHandler(
  options: ExecuteOptions,
  collector?: JobOutputCollector
): StdoutHandler {
  if (collector) {
    // Events mode: parse the NDJSON, feed the collector so result.stdout is the reconstructed text (not raw events) that parseCapturedJson expects, and still forward each event to the caller's renderer when it set one.
    const render = options.onEvent;
    return handleEventsStdout((event) => {
      collector.consume(event);
      render?.(event);
    });
  }
  if (options.captureOutput) {
    return () => {};
  }
  if (options.debug) {
    return (data: Buffer) => writeStdout(data);
  }
  // Opt-in, per command: only the verbs whose output IS the answer ask for it, so every other command keeps the step-detection handler unchanged.
  if (options.passthroughOutput) {
    return handlePassthroughStdout(!options.quietSpinners);
  }
  return handleStepDetectionStdout();
}
