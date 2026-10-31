/**
 * The executor's report that its own path to a machine is dead.
 *
 * An executor container whose outbound TCP to a machine is dropped cannot say so
 * through the machine, and its account egress (`account.internal`) is the one
 * path known to work. The report is a POST whose JSON body names the machine
 * address the connect never reached, `{ host, port }`: the proxy tries that
 * address itself before the report counts toward moving the executor, because a
 * container cannot tell a closed port from blocked egress. The identity comes
 * from the egress intercept's props, so the body carries no tenant data. It
 * never throws, because a failed report must not lose the command's result line.
 */

export const EGRESS_UNREACHABLE_CODE = 'EGRESS_UNREACHABLE';
export const EGRESS_REPORT_URL = 'http://account.internal/executor/v1/egress-unreachable';
/** Covers the proxy's own 4 s probe of the target plus the round trip. */
const EGRESS_REPORT_DEADLINE_MS = 12_000;

/** The machine address the unanswered connect was aimed at. */
export interface EgressReportTarget {
  host: string;
  port: number;
}

/** What the proxy's probe of the target concluded. */
type EgressProbeVerdict = 'reachable' | 'target-unreachable' | 'skipped';

export interface EgressUnreachableAnswer {
  count: number;
  threshold: number;
  relocated: boolean;
  /** Whether this report counted toward moving the executor. */
  counted: boolean;
  probe: EgressProbeVerdict;
}

export interface EgressReporterOptions {
  fetchImpl?: typeof fetch;
  deadlineMs?: number;
}

const PROBE_VERDICTS: readonly string[] = ['reachable', 'target-unreachable', 'skipped'] as const;

/** The proxy's answer. One without `counted` and `probe` (a proxy from before the probe) counted every report, so it reads as counted and reachable. */
function parseAnswer(value: unknown): EgressUnreachableAnswer | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { count, threshold, relocated, counted, probe } = value as Record<string, unknown>;
  if (typeof count !== 'number' || typeof threshold !== 'number') return undefined;
  if (typeof relocated !== 'boolean') return undefined;
  if (counted === undefined && probe === undefined) {
    return { count, threshold, relocated, counted: true, probe: 'reachable' };
  }
  if (typeof counted !== 'boolean') return undefined;
  if (typeof probe !== 'string' || !PROBE_VERDICTS.includes(probe)) return undefined;
  return { count, threshold, relocated, counted, probe: probe as EgressProbeVerdict };
}

async function postReport(
  doFetch: typeof fetch,
  target: EgressReportTarget,
  signal: AbortSignal
): Promise<EgressUnreachableAnswer | undefined> {
  const response = await doFetch(EGRESS_REPORT_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ host: target.host, port: target.port }),
    signal,
  });
  if (!response.ok) return undefined;
  return parseAnswer(await response.json());
}

/** Build the report call. Answers `undefined` on any failure, refusal or timeout. */
export function createEgressReporter(
  options: EgressReporterOptions = {}
): (target: EgressReportTarget) => Promise<EgressUnreachableAnswer | undefined> {
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const deadlineMs = options.deadlineMs ?? EGRESS_REPORT_DEADLINE_MS;

  return async (target) => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Raced as well as aborted: a fetch that ignores its signal must not hold the result line.
    const deadline = new Promise<undefined>((resolve) => {
      timer = setTimeout(() => {
        controller.abort();
        resolve(undefined);
      }, deadlineMs);
    });
    try {
      return await Promise.race([postReport(doFetch, target, controller.signal), deadline]);
    } catch {
      return undefined;
    } finally {
      clearTimeout(timer);
    }
  };
}

/** The guidance the result line carries for a report's answer. */
export function egressGuidance(
  answer: EgressUnreachableAnswer | undefined,
  target: EgressReportTarget
): string {
  if (!answer) {
    return 'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.';
  }
  if (answer.relocated) {
    return "This org's executor has moved to a new instance. Retry the command now.";
  }
  if (answer.probe === 'target-unreachable') {
    return `${target.host}:${target.port} did not answer an SSH connection from outside the executor either, so the executor is not moving. Check that the machine is up and accepts SSH on that port.`;
  }
  if (!answer.counted) {
    return 'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.';
  }
  return `Attempt ${answer.count} of ${answer.threshold} before the executor moves to a new instance. Retry the command.`;
}
