/**
 * Deterministic AI scripts (C42 and AP13 of agent/plans/PLAN-console-ai-providers.md).
 *
 * CI never calls a real provider. Every test that needs a model reads one of these scripts
 * instead: the TEST_MODE console mock serves a script as the NDJSON stream of /console/ai/chat
 * and its smoke verdict as the answer of /console/ai/test, and the executor unit tests feed the
 * same script to the AI SDK mock model as stream parts (render.ts). A script is plain data with
 * no clock, randomness or I/O, so two replays are byte-identical.
 *
 * A script is a list of model steps, each one provider round trip. A tool call names the outcome
 * the loop host gives it: a result (with the renet events the tool streamed), or an approval
 * request, which ends the turn (D9). A script with `error` fails at the provider before any step.
 */
import type { WireEvent } from '../../cli-contract/wire.js';

/** What the loop host made of one tool call. */
export type ScriptToolOutcome =
  | { kind: 'result'; ok: boolean; output: unknown; events?: WireEvent[] }
  | { kind: 'approval' };

export type ScriptPart =
  | { type: 'text'; text: string }
  | {
      type: 'tool-call';
      toolCallId: string;
      toolName: string;
      input: Record<string, unknown>;
      outcome: ScriptToolOutcome;
    };

export interface ScriptStep {
  parts: ScriptPart[];
  /** The provider's finish reason for this step. */
  finish: 'stop' | 'tool-calls';
  usage: { inputTokens: number; outputTokens: number };
}

/** A provider failure, as the provider's HTTP status and message. */
export interface ScriptProviderError {
  status: number;
  message: string;
}

/** The answer of /console/ai/test against a profile served by this script (D12). */
export type ScriptedSmokeResult =
  | { ok: true; latencyMs: number; observed: { tools: boolean; streaming: boolean } }
  | {
      ok: false;
      reason: 'provider-error' | 'no-tool-call';
      message: string;
      status?: number;
      latencyMs: number;
      observed: { tools: boolean; streaming: boolean };
    };

export const SCRIPT_IDS = [
  'text',
  'tool-calls',
  'approval',
  'refusal',
  'feedback-offer',
  'provider-error',
] as const;

export type ScriptId = (typeof SCRIPT_IDS)[number];

export interface AiScript {
  id: ScriptId;
  /** One line naming what the script exercises. */
  summary: string;
  steps: ScriptStep[];
  error?: ScriptProviderError;
  smoke: ScriptedSmokeResult;
}

/** The fixed latency every scripted smoke reports, so a replay stays byte-identical. */
export const SCRIPTED_LATENCY_MS = 42;

const PASS: ScriptedSmokeResult = {
  ok: true,
  latencyMs: SCRIPTED_LATENCY_MS,
  observed: { tools: true, streaming: true },
};

const MACHINE_LIST_OUTPUT = {
  machines: [
    { name: 'mock-machine-1', status: 'online' },
    { name: 'mock-machine-2', status: 'idle' },
  ],
};

const SCRIPTS: Record<ScriptId, AiScript> = {
  text: {
    id: 'text',
    summary: 'a plain streamed answer with no tool call',
    steps: [
      {
        parts: [
          {
            type: 'text',
            text: 'Scripted reply: this console answers from a deterministic test provider.',
          },
        ],
        finish: 'stop',
        usage: { inputTokens: 120, outputTokens: 14 },
      },
    ],
    smoke: PASS,
  },
  'tool-calls': {
    id: 'tool-calls',
    summary: 'a tool call whose renet events stream before its result, then a final answer',
    steps: [
      {
        parts: [
          { type: 'text', text: 'Listing the machines in this config.' },
          {
            type: 'tool-call',
            toolCallId: 'scripted-call-1',
            toolName: 'machine_list',
            input: {},
            outcome: {
              kind: 'result',
              ok: true,
              output: MACHINE_LIST_OUTPUT,
              events: [
                { type: 'step_start', name: 'list_machines' },
                { type: 'step_done', name: 'list_machines', duration_ms: 18 },
              ],
            },
          },
        ],
        finish: 'tool-calls',
        usage: { inputTokens: 140, outputTokens: 22 },
      },
      {
        parts: [
          {
            type: 'text',
            text: 'Two machines: mock-machine-1 is online and mock-machine-2 is idle.',
          },
        ],
        finish: 'stop',
        usage: { inputTokens: 210, outputTokens: 17 },
      },
    ],
    smoke: PASS,
  },
  approval: {
    id: 'approval',
    summary: 'a mutating tool call that decide() holds for confirmation, ending the turn',
    steps: [
      {
        parts: [
          { type: 'text', text: 'Deleting the fork needs confirmation first.' },
          {
            type: 'tool-call',
            toolCallId: 'scripted-call-1',
            toolName: 'repo_delete',
            input: { repo: 'mock-repo:mock-fork' },
            outcome: { kind: 'approval' },
          },
        ],
        finish: 'tool-calls',
        usage: { inputTokens: 150, outputTokens: 25 },
      },
    ],
    smoke: PASS,
  },
  refusal: {
    id: 'refusal',
    summary: 'the model declines and calls no tool',
    steps: [
      {
        parts: [
          {
            type: 'text',
            text: 'That request is outside what this assistant may do, so no command was run.',
          },
        ],
        finish: 'stop',
        usage: { inputTokens: 110, outputTokens: 16 },
      },
    ],
    smoke: {
      ok: false,
      reason: 'no-tool-call',
      message: 'the model did not call echo_nonce',
      latencyMs: SCRIPTED_LATENCY_MS,
      observed: { tools: false, streaming: true },
    },
  },
  'feedback-offer': {
    id: 'feedback-offer',
    summary: 'a tool fails on a Rediacc-origin error and the answer offers a feedback report',
    steps: [
      {
        parts: [
          {
            type: 'tool-call',
            toolCallId: 'scripted-call-1',
            toolName: 'repo_up',
            input: { repo: 'mock-repo' },
            outcome: {
              kind: 'result',
              ok: false,
              output: { exitCode: 1, error: 'renet: compose up failed: internal error' },
              events: [
                { type: 'step_start', name: 'compose_up' },
                { type: 'log', level: 'error', msg: 'renet: compose up failed: internal error' },
              ],
            },
          },
        ],
        finish: 'tool-calls',
        usage: { inputTokens: 160, outputTokens: 20 },
      },
      {
        parts: [
          {
            type: 'text',
            text: 'The start failed inside Rediacc, not in the repository. A feedback report can be sent from the run record.',
          },
        ],
        finish: 'stop',
        usage: { inputTokens: 240, outputTokens: 24 },
      },
    ],
    smoke: PASS,
  },
  'provider-error': {
    id: 'provider-error',
    summary: 'the provider refuses the call before any step',
    steps: [],
    error: { status: 401, message: 'invalid x-api-key' },
    smoke: {
      ok: false,
      reason: 'provider-error',
      message: 'invalid x-api-key',
      status: 401,
      latencyMs: SCRIPTED_LATENCY_MS,
      observed: { tools: false, streaming: false },
    },
  },
};

export function isScriptId(value: unknown): value is ScriptId {
  return typeof value === 'string' && (SCRIPT_IDS as readonly string[]).includes(value);
}

export function getScript(id: ScriptId): AiScript {
  return SCRIPTS[id];
}

/** The prefix of a user message that selects a script by id, as in `script:refusal`. */
export const SCRIPT_MESSAGE_PREFIX = 'script:';

/**
 * Which script answers a request: a profile named after a script id, else a last user message
 * of the form `script:<id>`, else `text`. A test picks the outcome through what it would send
 * anyway, so no request field exists only for tests.
 */
export function pickScript(request: { profile?: string; lastUserMessage?: string }): AiScript {
  if (isScriptId(request.profile)) return SCRIPTS[request.profile];
  const message = request.lastUserMessage?.trim();
  if (message?.startsWith(SCRIPT_MESSAGE_PREFIX)) {
    const id = message.slice(SCRIPT_MESSAGE_PREFIX.length).trim();
    if (isScriptId(id)) return SCRIPTS[id];
  }
  return SCRIPTS.text;
}
