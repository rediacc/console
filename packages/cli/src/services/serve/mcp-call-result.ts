/**
 * The result shapes of a hosted MCP call (agent/plans/PLAN-rmcp-agent-grants.md Design 4): the same envelope the
 * local stdio server returns for a tool (commands/mcp/executor.ts `ExecutionResult`), so a call reads the same
 * whichever way it arrived (D18), and the `isError` results that carry a code the Worker passes on untouched.
 */

import type { CallToolResult } from '@modelcontextprotocol/server';
import type { McpToolEntry } from '@rediacc/shared/mcp/registry';
import type { DispatchOutcome } from './command-dispatch.js';

/** An `isError` result whose `structuredContent` carries the code, the message and any extra fields. */
export function toolError(
  code: string,
  message: string,
  extra: Record<string, unknown> = {}
): CallToolResult {
  return {
    content: [{ type: 'text', text: message }],
    structuredContent: { code, message, ...extra },
    isError: true,
  };
}

/** The result for a grant the executor cannot open any more. The wording says nothing about which check failed. */
export const GRANT_ENDED = toolError(
  'REDIACC_GRANT_REVOKED',
  'This grant can no longer be used. Ask the user to authorize the agent again.'
);

/** The envelope a finished command prints (`--output json`), as the local stdio server reads it. */
export interface Envelope {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings: string[];
  duration_ms: number;
  next?: string;
  nextPollSeconds?: number;
  waited_ms?: number;
}

interface PrintedEnvelope {
  success: boolean;
  command: string;
  data: unknown;
  errors: unknown[] | null;
  warnings?: string[];
  metrics?: { duration_ms?: number };
}

/** The envelope the command printed, or undefined when its output is not one. */
function printedEnvelope(text: string, durationMs: number): Envelope | undefined {
  if (!text) return undefined;
  try {
    const parsed = JSON.parse(text) as PrintedEnvelope;
    return {
      success: parsed.success,
      command: parsed.command,
      data: parsed.data,
      errors: parsed.errors,
      warnings: parsed.warnings ?? [],
      duration_ms: parsed.metrics?.duration_ms ?? durationMs,
    };
  } catch {
    // Not an envelope: the printed text is the data.
    return undefined;
  }
}

function printedData(outcome: DispatchOutcome): unknown {
  if (outcome.stdoutBytes !== undefined) {
    return `[${outcome.stdoutBytes.byteLength} bytes of binary output]`;
  }
  return outcome.stdout.trim() || null;
}

/** The envelope of a finished dispatch: what it printed, else one built from its result. */
export function envelopeOf(outcome: DispatchOutcome, command: string): Envelope {
  const printed = printedEnvelope(outcome.stdout.trim(), outcome.result.durationMs);
  if (printed) return printed;
  const { result } = outcome;
  const message = [result.error, outcome.stderr].filter(Boolean).join('\n');
  return {
    success: result.success,
    command,
    data: printedData(outcome),
    errors: result.success
      ? null
      : [
          {
            code: result.errorCode ?? 'EXECUTION_ERROR',
            message: message || 'The command failed.',
          },
        ],
    warnings: [],
    duration_ms: result.durationMs,
  };
}

/** Whether the tool takes a `page` argument (the registry's schema says so). */
export function isPageable(entry: McpToolEntry): boolean {
  const properties = entry.inputSchema.properties;
  return typeof properties === 'object' && properties !== null && 'page' in properties;
}

/** Whether a `job status` envelope names a finished job. */
export function jobFinished(envelope: Envelope): boolean {
  const state = (envelope.data as { state?: unknown } | null)?.state;
  return state === 'succeeded' || state === 'failed' || state === 'cancelled';
}
