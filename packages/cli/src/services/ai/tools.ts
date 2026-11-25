/**
 * AI tools (D9 and D10 of PLAN-console-ai-providers): the LM1 registry's
 * executor-served entries become AI SDK tools that run in process.
 *
 * Every call takes the executor's own path, in its order: `prepareCommand`
 * refuses an unknown, non-proxyable or smuggled-flag call; the target is
 * resolved from the session config the command will run against
 * (`resolveExecutorTarget`); and `authorize`, the executor's enforcement point
 * for `decide()` (PLAN-rmcp-decide.md D3), answers before anything is
 * dispatched. Nothing here judges a command itself.
 *
 * The principal is an agent, always, and this module is what makes it one: the
 * loop host hands over the verified session principal and, for a chat bound to
 * an agent grant, that grant's opt-ins. A tool's input is the registry's
 * schema, so a model cannot name a principal kind or an opt-in: a field the
 * schema does not declare is refused before anything else, including a
 * contract flag the registry leaves out (`--debug`, `--yes`), and
 * `prepareCommand` still refuses anything the contract does not declare. Without a grant the opt-ins are empty (`source: 'none'`), so
 * `decide()` refuses grand-repo and cluster mutations for the agent.
 *
 * A `needs_confirmation` answer runs nothing: the tool returns an
 * `approval_required` result, {@link stopOnApproval} ends the turn on it, and
 * {@link aiEventOfToolResult} turns it into the `approval_required` stream
 * event. Confirming is the approval surface of plan 9 (C33); no call here ever
 * claims a confirmation.
 *
 * Command output is untrusted (untrusted.ts): stripped, truncated and fenced
 * before the model reads it.
 */
import { type ContractCommand, getCommand } from '@rediacc/shared/cli-contract';
import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { listProxyTools, type McpToolEntry } from '@rediacc/shared/mcp/registry';
import type { DecisionNext } from '@rediacc/shared/policy';
import { jsonSchema, type StopCondition, type ToolSet, tool } from 'ai';
import type { RenetEvent } from '../executor/types.js';
import {
  CommandRejected,
  type DispatchOutcome,
  type PreparedCommand,
  prepareCommand,
} from '../serve/command-dispatch.js';
import {
  type AgentGrantOverrides,
  authorize,
  clusterSubjectOf,
  PolicyDenied,
  resolveExecutorTarget,
} from '../serve/policy.js';
import type { SessionPrincipal } from '../serve/sessions.js';
import { fenceUntrusted } from './untrusted.js';

/** The tool input field that asks for `--background`; not a contract option. */
const BACKGROUND_FIELD = 'background';

/**
 * The registry's `machine status` views (commands/mcp/custom-tools.ts): each
 * runs the command with one fixed section switch. A drift test holds this table
 * to the views' own argv.
 */
export const VIEW_SWITCHES: Readonly<Record<string, Readonly<Record<string, true>>>> = {
  machine_containers: { containers: true },
  machine_services: { services: true },
  machine_repos: { repositories: true },
};

/** One prepared command handed to the loop host's runner. */
export interface AiToolRun {
  prepared: PreparedCommand;
  /** The model asked for `background`: each job returns its ticket at once. */
  background: boolean;
  /** Forwards one renet event of this call, for the `event` line tagged with its tool call id. */
  onEvent: (event: RenetEvent) => void;
  abortSignal?: AbortSignal;
}

/**
 * What the AI tools run against, set by the loop host from the request's
 * verified session and never from the request body.
 */
export interface AiToolContext {
  /** The principal the account server resolved for the session. */
  principal: SessionPrincipal;
  /** The session config every call resolves its target in and runs against. */
  config: RdcConfig;
  /** The agent grant a grant-bound chat runs under; absent for a chat bound to none. */
  agentGrant?: AgentGrantOverrides;
  /** Dispatches an authorized command; the loop host passes `dispatchCommand` with its executor. */
  run: (run: AiToolRun) => Promise<DispatchOutcome>;
  /** Receives every renet event a call streams, with the call's id. */
  onEvent?: (toolCallId: string, event: RenetEvent) => void;
}

/** The result a tool hands back to the model. */
export type AiToolResult =
  | {
      status: 'ok' | 'failed';
      exitCode: number;
      errorCode?: string;
      /** The command's printed output, fenced (untrusted.ts). */
      output: string;
    }
  | {
      /** `decide()` refused it, or `prepareCommand` did (`COMMAND_REJECTED`); nothing ran. */
      status: 'refused';
      code: string;
      reason: string;
      next?: DecisionNext;
    }
  | {
      /** `decide()` answered `needs_confirmation`; nothing ran and the turn ends. */
      status: 'approval_required';
      code: string;
      reason: string;
      next?: DecisionNext;
    };

/** The code of a call refused before policy: an undeclared field, or one `prepareCommand` refused. */
export const COMMAND_REJECTED = 'COMMAND_REJECTED';

/** The opt-ins of an agent bound to no grant: none, so `decide()` sees `source: 'none'`. */
const NO_GRANT: AgentGrantOverrides = { allowGrandRepos: false, allowClusterOps: false };

/** The registry fields a tool call needs (a subset of McpToolEntry). */
export interface AiToolSpec {
  /** Registry tool name, e.g. "repo_up". */
  name: string;
  /** The contract pathKey the tool runs, e.g. "repo up". */
  command: string;
  /** The tool may start a machine job, so it takes the `background` field. */
  attachWindow: boolean;
  /** JSON Schema of the tool arguments; its `properties` are the only fields a call may carry. */
  inputSchema: Record<string, unknown>;
}

/** The first input field the tool's registry schema does not declare, or undefined. */
function undeclaredField(spec: AiToolSpec, input: Record<string, unknown>): string | undefined {
  const declared = (spec.inputSchema.properties ?? {}) as Record<string, unknown>;
  return Object.keys(input).find((key) => !Object.hasOwn(declared, key));
}

/**
 * Split a tool input into the contract's positionals and options, and the
 * background ask, which only a tool with an attach window takes.
 */
export function requestOf(
  spec: AiToolSpec,
  entry: ContractCommand,
  input: Record<string, unknown>
): { params: Record<string, unknown>; positionals: Record<string, unknown>; background: boolean } {
  const positionalNames = new Set(entry.positionals.map((p) => p.name));
  const optionByKey = new Map(entry.options.map((o) => [o.long.replaceAll('-', '_'), o.long]));
  const params: Record<string, unknown> = { ...VIEW_SWITCHES[spec.name] };
  const positionals: Record<string, unknown> = {};
  let background = false;
  for (const [key, value] of Object.entries(input)) {
    if (positionalNames.has(key)) positionals[key] = value;
    else if (optionByKey.has(key)) params[optionByKey.get(key) as string] = value;
    else if (key === BACKGROUND_FIELD && spec.attachWindow) background = value === true;
    // Declared in the schema but neither a positional, an option nor a usable background ask (an undeclared field never reaches here: prepareCall refuses it first); passed on under its own name so prepareCommand refuses it as a smuggled flag.
    else params[key] = value;
  }
  return { params, positionals, background };
}

/** The ref or machine a command names, by flag or by positional (the executor route's own rule). */
function targetFrom(
  option: string | null,
  positional: string | null,
  params: Record<string, unknown>,
  positionals: Record<string, unknown>
): string | undefined {
  const fromFlag = option ? params[option] : undefined;
  if (typeof fromFlag === 'string') return fromFlag;
  const fromPositional = positional ? positionals[positional] : undefined;
  return typeof fromPositional === 'string' ? fromPositional : undefined;
}

/** The first target field (ref or machine, by flag or positional) a call carries as a non-string, or undefined. */
function nonStringTarget(
  entry: ContractCommand,
  params: Record<string, unknown>,
  positionals: Record<string, unknown>
): string | undefined {
  const fields: [string | null, Record<string, unknown>][] = [
    [entry.repoOption, params],
    [entry.repoPositional, positionals],
    [entry.machineOption, params],
    [entry.machinePositional, positionals],
  ];
  for (const [name, bag] of fields) {
    if (name && bag[name] !== undefined && typeof bag[name] !== 'string') return name;
  }
  return undefined;
}

/** The text a run hands the model: what the command printed, else renet's output, then any error. */
function printedOutput(outcome: DispatchOutcome): string {
  const printed =
    outcome.stdoutBytes === undefined
      ? [outcome.stdout, outcome.result.stdout].find((text) => text !== undefined && text !== '')
      : `[${outcome.stdoutBytes.byteLength} bytes of binary output]`;
  const failure = outcome.result.success ? [] : [outcome.result.error, outcome.stderr];
  return [printed, ...failure].filter(Boolean).join('\n');
}

/** A checked call, or the refusal of one the contract or `prepareCommand` will not run. */
function prepareCall(
  spec: AiToolSpec,
  input: Record<string, unknown>
): { prepared: PreparedCommand; request: ReturnType<typeof requestOf> } | AiToolResult {
  const known = getCommand(spec.command);
  if (!known) {
    return {
      status: 'refused',
      code: COMMAND_REJECTED,
      reason: `There is no "rdc ${spec.command}" command.`,
    };
  }
  const extra = undeclaredField(spec, input);
  if (extra !== undefined) {
    return {
      status: 'refused',
      code: COMMAND_REJECTED,
      reason: `The ${spec.name} tool has no ${extra} field.`,
    };
  }
  const request = requestOf(spec, known, input);
  // authorize() reads the target as a string, so a ref of another type would be run unauthorized.
  const badTarget = nonStringTarget(known, request.params, request.positionals);
  if (badTarget !== undefined) {
    return {
      status: 'refused',
      code: COMMAND_REJECTED,
      reason: `The ${badTarget} field of the ${spec.name} tool must be a string.`,
    };
  }
  try {
    return { prepared: prepareCommand(spec.command, request.params, request.positionals), request };
  } catch (error) {
    if (!(error instanceof CommandRejected)) throw error;
    return { status: 'refused', code: COMMAND_REJECTED, reason: error.message };
  }
}

/** The answer of authorize() for a prepared call: null on `allow`, the refusal or approval request otherwise. */
async function decideCall(
  ctx: AiToolContext,
  prepared: PreparedCommand,
  request: ReturnType<typeof requestOf>
): Promise<AiToolResult | null> {
  const { entry } = prepared;
  const { params, positionals } = request;
  const machineName = targetFrom(entry.machineOption, entry.machinePositional, params, positionals);
  const target = await resolveExecutorTarget(
    entry,
    {
      ref: targetFrom(entry.repoOption, entry.repoPositional, params, positionals),
      machine: machineName,
      subject: clusterSubjectOf(entry, positionals),
    },
    ctx.config
  );
  try {
    authorize({
      principal: ctx.principal,
      commandPath: entry.pathKey,
      config: ctx.config,
      target,
      machineName,
      // The agent principal: authorize() makes the principal an agent exactly when a grant is passed.
      agentGrant: ctx.agentGrant ?? NO_GRANT,
    });
    return null;
  } catch (error) {
    if (!(error instanceof PolicyDenied)) throw error;
    const { verdict, code, reason, next } = error.decision;
    return {
      status: verdict === 'needs_confirmation' ? 'approval_required' : 'refused',
      code,
      reason,
      ...(next ? { next } : {}),
    };
  }
}

/** Run one tool call through the executor's path. */
export async function runAiTool(
  ctx: AiToolContext,
  spec: AiToolSpec,
  input: Record<string, unknown>,
  call: { toolCallId: string; abortSignal?: AbortSignal }
): Promise<AiToolResult> {
  const checked = prepareCall(spec, input);
  if ('status' in checked) return checked;
  const { prepared, request } = checked;
  const held = await decideCall(ctx, prepared, request);
  if (held) return held;

  const outcome = await ctx.run({
    prepared,
    background: request.background,
    onEvent: (event) => ctx.onEvent?.(call.toolCallId, event),
    ...(call.abortSignal ? { abortSignal: call.abortSignal } : {}),
  });
  const { result } = outcome;
  return {
    status: result.success ? 'ok' : 'failed',
    exitCode: result.exitCode,
    ...(result.errorCode ? { errorCode: result.errorCode } : {}),
    output: fenceUntrusted(printedOutput(outcome)).text,
  };
}

/** The registry entries the AI may call: the ones the executor serves. */
export function aiToolEntries(): readonly McpToolEntry[] {
  return listProxyTools();
}

/** The AI SDK tool set of one chat, keyed by registry tool name. */
export function buildAiTools(ctx: AiToolContext): ToolSet {
  const tools: ToolSet = {};
  for (const entry of aiToolEntries()) {
    tools[entry.name] = tool({
      description: entry.description,
      inputSchema: jsonSchema<Record<string, unknown>>(entry.inputSchema),
      execute: (input, options) =>
        runAiTool(ctx, entry, input, {
          toolCallId: options.toolCallId,
          ...(options.abortSignal ? { abortSignal: options.abortSignal } : {}),
        }),
    });
  }
  return tools;
}

function isApprovalResult(output: unknown): boolean {
  return (output as { status?: unknown } | null)?.status === 'approval_required';
}

/** A stop condition that ends the turn after a step whose tool results include an approval request. */
export const stopOnApproval: StopCondition<ToolSet> = ({ steps }) =>
  steps.at(-1)?.toolResults.some((part) => isApprovalResult(part.output)) ?? false;

/**
 * The stream event of one tool result: `approval_required` for a call
 * `decide()` held for confirmation, `tool_result` for every other.
 */
export function aiEventOfToolResult(part: {
  toolCallId: string;
  toolName: string;
  input: unknown;
  output: unknown;
}): AiEvent {
  if (isApprovalResult(part.output)) {
    return {
      type: 'approval_required',
      toolCallId: part.toolCallId,
      name: part.toolName,
      input: part.input,
    };
  }
  const status = (part.output as { status?: unknown } | null)?.status;
  return {
    type: 'tool_result',
    toolCallId: part.toolCallId,
    ok: status === 'ok',
    output: part.output,
  };
}
