/**
 * Per-grant monitoring of the hosted MCP Worker (agent/plans/PLAN-rmcp-remote-worker.md Design 10).
 *
 * Every `tools/call` writes one Workers Analytics Engine data point: the grant id is the index, the blobs carry the tool, the outcome code and the region, the doubles carry the latency, an error flag and a destructive flag. The data point holds no argument, no credential and no result text (Design 9). A Worker deployed without the `MCP_METRICS` binding records nothing.
 *
 * The ops alert reads those points back: `ALERT_QUERY` is the Analytics Engine SQL the ops job runs over `ALERT_RULE.windowMinutes`, and `evaluateAlerts` is the rule applied to its rows, so the threshold lives once. A grant raises an alert on a burst of `REDIACC_GRANT_*` refusals (a revoked or expired grant, or an out-of-scope call, repeated) or on a burst of destructive calls; a quiet grant raises none.
 */
import { getMcpTool } from '../mcp/registry.js';

/** The Analytics Engine binding (`[[analytics_engine_datasets]]`, dataset `mcp_<region>`); the same shape as the account Worker's `TELEMETRY`. */
export interface MetricsDataset {
  writeDataPoint: (point: { indexes?: string[]; blobs?: string[]; doubles?: number[] }) => void;
}

/** The index of a data point whose caller never authenticated: an unknown grant id is never an index, so a flood of made-up ids cannot grow the dataset's key space. */
export const UNAUTHENTICATED_INDEX = 'unauthenticated';

export interface CallObservation {
  /** The grant id of an authenticated call; absent for a request the transport refused with 401. */
  grantId?: string;
  region: string;
  /** The tool a `tools/call` named. */
  tool: string;
  /** `ok`, the `REDIACC_*` or executor code of an `isError` result, or `HTTP_<status>`. */
  code: string;
  latencyMs: number;
}

/** Whether the registry marks `tool` destructive. An unknown tool is not counted as destructive. */
export function isDestructiveTool(tool: string): boolean {
  return getMcpTool(tool)?.annotations.destructiveHint === true;
}

/** Write the data point of one call; never throws, so monitoring cannot fail a request. */
export function recordCall(dataset: MetricsDataset | undefined, call: CallObservation): void {
  if (!dataset) return;
  try {
    dataset.writeDataPoint({
      indexes: [call.grantId ?? UNAUTHENTICATED_INDEX],
      blobs: [call.tool, call.code, call.region],
      doubles: [
        call.latencyMs,
        call.code === 'ok' ? 0 : 1,
        isDestructiveTool(call.tool) && call.code === 'ok' ? 1 : 0,
      ],
    });
  } catch {
    // A dataset that rejects a point loses that point only.
  }
}

/** The JSON message of an answer body: plain JSON, or the first `data:` line of an event stream. Undefined when neither parses. */
export function messageOf(text: string): unknown {
  const candidate =
    text.trimStart().startsWith('{') || text.trimStart().startsWith('[')
      ? text
      : text
          .split('\n')
          .find((line) => line.startsWith('data:'))
          ?.slice('data:'.length);
  if (candidate === undefined) return undefined;
  try {
    return JSON.parse(candidate);
  } catch {
    return undefined;
  }
}

/** The outcome of a `tools/call` answer body: `ok`, or the code of its `isError` result. */
export function outcomeOf(body: unknown): string {
  const answer = Array.isArray(body) ? body[0] : body;
  if (typeof answer !== 'object' || answer === null) return 'ok';
  const result = (answer as { result?: unknown }).result;
  if (typeof result !== 'object' || result === null) return 'ok';
  const { isError, structuredContent } = result as {
    isError?: unknown;
    structuredContent?: unknown;
  };
  if (isError !== true) return 'ok';
  const code =
    typeof structuredContent === 'object' && structuredContent !== null
      ? (structuredContent as { code?: unknown }).code
      : undefined;
  return typeof code === 'string' && code !== '' ? code : 'ERROR';
}

/** The tool a request body names when it is a `tools/call`, else undefined. */
export function toolOf(body: unknown): string | undefined {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return undefined;
  const { method, params } = body as { method?: unknown; params?: unknown };
  if (method !== 'tools/call' || typeof params !== 'object' || params === null) return undefined;
  const name = (params as { name?: unknown }).name;
  return typeof name === 'string' ? name : undefined;
}

/** The ops alert's thresholds, per grant and window. */
export const ALERT_RULE = {
  windowMinutes: 5,
  /** `REDIACC_GRANT_*` refusals from one grant in the window. */
  grantRefusals: 10,
  /** Destructive calls that ran, from one grant in the window. */
  destructiveCalls: 5,
} as const;

/**
 * The Analytics Engine SQL the ops alert runs, one row per grant over the window. `index1` is the grant id, `blob2` the outcome code, `double3` the destructive flag.
 */
export const ALERT_QUERY = `SELECT index1 AS grant_id, SUM(IF(blob2 LIKE 'REDIACC_GRANT_%', _sample_interval, 0)) AS grant_refusals, SUM(double3 * _sample_interval) AS destructive_calls FROM mcp_<region> WHERE timestamp > NOW() - INTERVAL '${ALERT_RULE.windowMinutes}' MINUTE AND index1 != '${UNAUTHENTICATED_INDEX}' GROUP BY index1`;

export interface GrantWindow {
  grant_id: string;
  grant_refusals: number;
  destructive_calls: number;
}

export interface GrantAlert {
  grantId: string;
  reason: 'grant-refusals' | 'destructive-calls';
  count: number;
}

/** The alerts the rule raises over per-grant window rows: a grant at or above a threshold, one alert per threshold it reaches. */
export function evaluateAlerts(rows: readonly GrantWindow[], rule = ALERT_RULE): GrantAlert[] {
  const alerts: GrantAlert[] = [];
  for (const row of rows) {
    if (row.grant_refusals >= rule.grantRefusals) {
      alerts.push({ grantId: row.grant_id, reason: 'grant-refusals', count: row.grant_refusals });
    }
    if (row.destructive_calls >= rule.destructiveCalls) {
      alerts.push({
        grantId: row.grant_id,
        reason: 'destructive-calls',
        count: row.destructive_calls,
      });
    }
  }
  return alerts;
}
