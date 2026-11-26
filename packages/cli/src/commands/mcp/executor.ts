import { execFile } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { promisify } from 'node:util';
import {
  type CallToolResult,
  CLIENT_CAPABILITIES_META_KEY,
  type ClientCapabilities,
  createRequestStateCodec,
  type InputRequiredResult,
  inputRequired,
  inputResponse,
  type McpServer,
  type ServerContext,
} from '@modelcontextprotocol/server';
import { getCommand } from '@rediacc/shared/cli-contract';
import type { JobOverlap } from '@rediacc/shared/cli-contract/wire';
import { BackgroundEnvelopeSchema } from '@rediacc/shared/cli-contract/wire';
import { DECISION_CODES, type DecisionCode } from '@rediacc/shared/policy';
import { t } from '../../i18n/index.js';
import { JOB_CLIENT_ENV } from '../../services/jobs/attach.js';
import { CONFIRM_GRAND_FLAG } from '../../utils/command-policy.js';
import { hasAttachWindow } from './tool-factory.js';

const execFileAsync = promisify(execFile);

export interface ExecutorOptions {
  configName?: string;
  defaultTimeoutMs: number;
  /** Run the child as `rdc --background`: the ticket returns at once, also through a `--proxy` executor. */
  background?: boolean;
  /** The value a confirmed retry repeats after `--confirm-grand`: the `confirm` value a `needs_confirmation` refusal named. */
  confirm?: string;
}

/**
 * A refusal of the child's policy check, lifted out of its error entry. The child meets `decide()` through
 * the CLI's command-policy step and reports anything but `allow` as a `VALIDATION_ERROR` whose details are
 * `[code, reason, next]`: `next` is the command past a `deny` (`rdc repo fork ...`), or
 * `--confirm-grand <value>` for a `needs_confirmation`.
 */
export interface PolicyRefusal {
  verdict: 'deny' | 'needs_confirmation';
  code: Exclude<DecisionCode, 'ALLOWED'>;
  /** decide()'s English justification. */
  reason: string;
  /** The child's translated message. */
  message: string;
  next?: { run?: string; confirm?: { argument: 'confirm'; value: string } };
}

export interface ExecutionResult {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings: string[];
  duration_ms: number;
  /** Set when the run outlasted the attach window: the job to follow with `job_status`. */
  job?: { jobId: string; machine: string; follow: string };
  /** The tool that follows the ticket (`job_status`), present with `job`. */
  next?: 'job_status';
  /** The jobs a start overlapped (a warning), or that held the scope of a refused start (a BUSY error). */
  overlaps?: JobOverlap[];
  /** Set when the child's policy check refused the command (deny or needs_confirmation). */
  decision?: PolicyRefusal;
}

interface RdcEnvelope {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings: string[];
  metrics: { duration_ms: number };
}

interface ExecError extends Error {
  stdout?: string;
  stderr?: string;
  killed?: boolean;
  code?: string | number;
}

/** Node flags a child must not inherit: a debugger port the parent already holds. */
const PARENT_ONLY_NODE_FLAG = /^--(inspect|debug)/;

/**
 * Resolve the rdc binary for child process execution.
 * Handles both SEA binary and development (tsx/node) modes.
 *
 * Under `tsx src/index.ts` the TypeScript loader arrives as node flags (`process.execArgv`), so the child gets
 * them too; without them `node src/index.ts` fails to resolve its first `.js` import and every tool call of a
 * dev-run server returned EXECUTION_ERROR (found by stdio-e2e.test.ts).
 */
export function resolveRdcBinary(): { command: string; prefixArgs: string[] } {
  // SEA binary: process.execPath IS the rdc binary
  if (!process.argv[1] || process.execPath === process.argv[1]) {
    return { command: process.execPath, prefixArgs: [] };
  }
  // Development or the bundle: node + its flags + script path
  const flags = process.execArgv.filter((flag) => !PARENT_ONLY_NODE_FLAG.test(flag));
  return { command: process.execPath, prefixArgs: [...flags, process.argv[1]] };
}

/** Whether the command starts a machine job the child attaches to for the window (the contract says which). */
function commandAttaches(argv: string[]): boolean {
  const firstFlag = argv.findIndex((a) => a.startsWith('-'));
  const words = firstFlag === -1 ? argv : argv.slice(0, firstFlag);
  for (let n = Math.min(words.length, 3); n > 0; n--) {
    const cmd = getCommand(words.slice(0, n).join(' '));
    if (cmd) return hasAttachWindow(cmd);
  }
  return false;
}

/** The ticket envelope a child prints when its job outlived the window, found among the lines of its stdout. */
function ticketOf(stdout: string) {
  for (const line of stdout.split('\n')) {
    if (!line.startsWith('{') || !line.includes('"jobId"')) continue;
    try {
      const parsed = BackgroundEnvelopeSchema.safeParse(JSON.parse(line));
      if (parsed.success) return parsed.data;
    } catch {
      // Not a ticket line.
    }
  }
  return undefined;
}

function ticketResult(
  argv: string[],
  ticket: NonNullable<ReturnType<typeof ticketOf>>
): ExecutionResult {
  return {
    success: true,
    command: argv.join(' '),
    data: ticket,
    errors: null,
    warnings: [],
    duration_ms: 0,
    job: { jobId: ticket.jobId, machine: ticket.machine, follow: ticket.follow },
    next: 'job_status',
    ...(ticket.overlaps.length > 0 ? { overlaps: ticket.overlaps } : {}),
  };
}

/** The structured overlaps an error entry carries (a BUSY refusal), lifted to a field of the tool result. */
function overlapsOf(errors: unknown[] | null): { overlaps?: JobOverlap[] } {
  for (const entry of errors ?? []) {
    const overlaps = (entry as { overlaps?: unknown } | null)?.overlaps;
    if (Array.isArray(overlaps) && overlaps.length > 0)
      return { overlaps: overlaps as JobOverlap[] };
  }
  return {};
}

const REFUSAL_CODES: ReadonlySet<string> = new Set(DECISION_CODES.filter((c) => c !== 'ALLOWED'));

/** The `next` of a refusal from the third detail: the confirm value after the flag, else the command past a deny. */
function refusalNext(code: string, detail: unknown): PolicyRefusal['next'] {
  if (typeof detail !== 'string' || detail === '') return undefined;
  if (code !== 'CONFIRMATION_REQUIRED') return { run: detail };
  const prefix = `${CONFIRM_GRAND_FLAG} `;
  if (!detail.startsWith(prefix)) return undefined;
  return { confirm: { argument: 'confirm', value: detail.slice(prefix.length) } };
}

/** The policy refusal an error entry carries (details `[code, reason, next?]`), lifted to a field of the tool result. */
function decisionOf(errors: unknown[] | null): { decision?: PolicyRefusal } {
  for (const entry of errors ?? []) {
    const { code, message, details } = (entry ?? {}) as {
      code?: unknown;
      message?: unknown;
      details?: unknown;
    };
    if (code !== 'VALIDATION_ERROR' || !Array.isArray(details)) continue;
    const [decisionCode, reason, detail] = details as unknown[];
    if (typeof decisionCode !== 'string' || !REFUSAL_CODES.has(decisionCode)) continue;
    const next = refusalNext(decisionCode, detail);
    return {
      decision: {
        verdict: decisionCode === 'CONFIRMATION_REQUIRED' ? 'needs_confirmation' : 'deny',
        code: decisionCode as PolicyRefusal['code'],
        reason: typeof reason === 'string' ? reason : '',
        message: typeof message === 'string' ? message : '',
        ...(next ? { next } : {}),
      },
    };
  }
  return {};
}

/**
 * Execute an rdc command as a child process and parse the JSON envelope response.
 */
export async function executeRdcCommand(
  argv: string[],
  options: ExecutorOptions & { timeoutMs?: number }
): Promise<ExecutionResult> {
  const args: string[] = [];
  if (options.configName) {
    args.push('--config', options.configName);
  }
  args.push(...argv, '--output', 'json', '--yes', '--quiet');
  if (options.background) args.push('--background');
  if (options.confirm !== undefined) args.push(CONFIRM_GRAND_FLAG, options.confirm);

  const timeoutMs = options.timeoutMs ?? options.defaultTimeoutMs;
  const bin = resolveRdcBinary();
  const windowed = commandAttaches(argv);

  try {
    const { stdout } = await execFileAsync(bin.command, [...bin.prefixArgs, ...args], {
      timeout: timeoutMs,
      maxBuffer: 10 * 1024 * 1024,
      env: {
        ...process.env,
        REDIACC_YES: '1',
        NO_COLOR: '1',
        REDIACC_AGENT: '1',
        // The child attaches to a machine job for the attach window, then hands back the ticket.
        ...(windowed ? { [JOB_CLIENT_ENV]: 'mcp' } : {}),
      },
    });

    const trimmed = stdout.trim();
    const ticket = ticketOf(trimmed);
    if (ticket) return ticketResult(argv, ticket);
    if (!trimmed) {
      return {
        success: true,
        command: argv.join(' '),
        data: null,
        errors: null,
        warnings: [],
        duration_ms: 0,
      };
    }

    const envelope: RdcEnvelope = JSON.parse(trimmed);
    return {
      success: envelope.success,
      command: envelope.command,
      data: envelope.data,
      errors: envelope.errors,
      warnings: envelope.warnings,
      duration_ms: envelope.metrics.duration_ms,
      ...overlapsOf(envelope.errors),
    };
  } catch (error: unknown) {
    const err = error as ExecError;

    // If the command produced JSON on stdout before failing, parse it
    if (err.stdout?.trim()) {
      try {
        const envelope: RdcEnvelope = JSON.parse(err.stdout.trim());
        return {
          success: false,
          command: envelope.command,
          data: envelope.data,
          errors: envelope.errors,
          warnings: envelope.warnings,
          duration_ms: envelope.metrics.duration_ms,
          ...overlapsOf(envelope.errors),
          ...decisionOf(envelope.errors),
        };
      } catch {
        // JSON parse failed, fall through
      }
    }

    // Timeout
    if (err.killed) {
      return {
        success: false,
        command: argv.join(' '),
        data: null,
        errors: [{ code: 'TIMEOUT', message: `Command timed out after ${timeoutMs}ms` }],
        warnings: [],
        duration_ms: timeoutMs,
      };
    }

    // Generic error
    return {
      success: false,
      command: argv.join(' '),
      data: null,
      errors: [{ code: 'EXECUTION_ERROR', message: err.message }],
      warnings: [],
      duration_ms: 0,
    };
  }
}

/** The key of the confirmation an elicitation asks for, in `inputRequests` and in the retry's `inputResponses`. */
const CONFIRM_INPUT = 'confirm';

/** What a confirmation's `requestState` carries: the call it was minted for and the value the retry repeats. */
interface ConfirmState {
  tool: string;
  args: string;
  value: string;
}

/**
 * Seals the confirmation state with a per-process key: one stdio process serves every round of a flow, and a
 * state the client altered, or echoes back after ten minutes, is refused before the handler runs.
 */
const confirmStates = createRequestStateCodec<ConfirmState>({ key: randomBytes(32) });

/** The `requestState` hook the server is built with (server.ts). */
export const verifyConfirmState = confirmStates.verify;

/** The tool arguments in one canonical form without `confirm`, which the retry of a confirmation adds. */
function canonicalArgs(args: Record<string, unknown>): string {
  const keys = Object.keys(args)
    .filter((key) => key !== CONFIRM_INPUT && args[key] !== undefined)
    .sort((a, b) => a.localeCompare(b, 'en'));
  return JSON.stringify(keys.map((key) => [key, args[key]]));
}

/**
 * Whether the client declared form elicitation: on the 2026-07-28 era in the request's own envelope, on a
 * 2025-era connection at `initialize`. A bare `elicitation: {}` counts as form (the rule before modes).
 */
function declaresFormElicitation(server: McpServer, ctx: ServerContext): boolean {
  // The SDK types the envelope as `{}`; its keys are the reserved `io.modelcontextprotocol/*` names.
  const envelope = ctx.mcpReq.envelope as Record<string, unknown> | undefined;
  const caps = (envelope?.[CLIENT_CAPABILITIES_META_KEY] ??
    server.server.getClientCapabilities()) as ClientCapabilities | undefined;
  const elicitation = caps?.elicitation as { form?: object; url?: object } | undefined;
  if (!elicitation) return false;
  return elicitation.form !== undefined || elicitation.url === undefined;
}

/** A refusal as the tool result: `isError`, the child's message, and `structuredContent { code, reason, next }`. */
function refusalResult(decision: PolicyRefusal, text = decision.message): CallToolResult {
  return {
    content: [{ type: 'text', text }],
    structuredContent: {
      code: decision.code,
      reason: decision.reason,
      ...(decision.next ? { next: decision.next } : {}),
    },
    isError: true,
  };
}

/** A tool error of the confirmation flow itself (the user declined, or the state no longer fits the call). */
function confirmationError(text: string): CallToolResult {
  return {
    content: [{ type: 'text', text }],
    structuredContent: { code: 'CONFIRMATION_REQUIRED', reason: text },
    isError: true,
  };
}

export interface PolicyCall {
  server: McpServer;
  ctx: ServerContext;
  tool: string;
  /** The tool arguments as the client sent them, `confirm` included. */
  args: Record<string, unknown>;
}

/** A finished run to render, or the answer that replaces it. */
export type PolicyOutcome =
  | { result: ExecutionResult }
  | { answer: CallToolResult | InputRequiredResult };

/** The confirm value of this call: the user's yes on the retry of an elicitation, else the `confirm` argument. */
function confirmOf(call: PolicyCall): { value?: string } | { answer: CallToolResult } {
  const reply = inputResponse(call.ctx.mcpReq.inputResponses, CONFIRM_INPUT);
  if (reply.kind === 'elicit') {
    if (reply.action !== 'accept' || reply.content?.[CONFIRM_INPUT] !== true) {
      return { answer: confirmationError(t('errors.agent.confirmDeclined')) };
    }
    const state = call.ctx.mcpReq.requestState<ConfirmState>();
    const fits =
      typeof state === 'object' &&
      state !== null &&
      state.tool === call.tool &&
      state.args === canonicalArgs(call.args);
    if (!fits) return { answer: confirmationError(t('errors.agent.confirmStale')) };
    return { value: state.value };
  }
  const { confirm } = call.args;
  return typeof confirm === 'string' && confirm !== '' ? { value: confirm } : {};
}

/**
 * Run a tool call and map the child's policy answer to MCP (agent/plans/PLAN-rmcp-local-mcp.md Design 7):
 * a `deny` becomes an `isError` result with `structuredContent { code, reason, next }`; a
 * `needs_confirmation` becomes a form-mode elicitation when the client declared one, whose retry runs with
 * the confirmed value, and any other client gets an error naming the `confirm` argument. A call that already
 * carried a confirmation and is still refused gets that error too, so no call asks twice.
 */
export async function runUnderPolicy(
  call: PolicyCall,
  run: (confirm: string | undefined) => Promise<ExecutionResult>
): Promise<PolicyOutcome> {
  const confirm = confirmOf(call);
  if ('answer' in confirm) return confirm;
  const result = await run(confirm.value);
  const { decision } = result;
  if (!decision) return { result };
  const value = decision.next?.confirm?.value;
  if (decision.verdict === 'deny' || value === undefined)
    return { answer: refusalResult(decision) };
  if (confirm.value === undefined && declaresFormElicitation(call.server, call.ctx)) {
    const state: ConfirmState = { tool: call.tool, args: canonicalArgs(call.args), value };
    return {
      answer: inputRequired({
        inputRequests: {
          [CONFIRM_INPUT]: inputRequired.elicit({
            message: decision.reason,
            requestedSchema: {
              type: 'object',
              properties: {
                [CONFIRM_INPUT]: { type: 'boolean', title: t('errors.agent.confirmTitle') },
              },
              required: [CONFIRM_INPUT],
            },
          }),
        },
        requestState: await confirmStates.mint(state),
      }),
    };
  }
  const how = t('errors.agent.confirmByArgument', { tool: call.tool, value });
  return { answer: refusalResult(decision, `${decision.message}\n\n${how}`) };
}
