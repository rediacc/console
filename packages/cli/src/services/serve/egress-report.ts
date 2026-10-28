/**
 * The executor's report that its own path to a machine is dead.
 *
 * An executor container whose outbound TCP to a machine is dropped cannot say so
 * through the machine, and its account egress (`account.internal`) is the one
 * path known to work. The report is a bodiless POST: the identity comes from the
 * egress intercept's props, so the container sends no host, address or tenant
 * data. It never throws, because a failed report must not lose the command's
 * result line.
 */

export const EGRESS_UNREACHABLE_CODE = 'EGRESS_UNREACHABLE';
export const EGRESS_REPORT_URL = 'http://account.internal/executor/v1/egress-unreachable';
export const EGRESS_REPORT_DEADLINE_MS = 5000;

export interface EgressUnreachableAnswer {
  count: number;
  threshold: number;
  relocated: boolean;
}

export interface EgressReporterOptions {
  fetchImpl?: typeof fetch;
  deadlineMs?: number;
}

function parseAnswer(value: unknown): EgressUnreachableAnswer | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { count, threshold, relocated } = value as Record<string, unknown>;
  if (typeof count !== 'number' || typeof threshold !== 'number') return undefined;
  if (typeof relocated !== 'boolean') return undefined;
  return { count, threshold, relocated };
}

async function postReport(
  doFetch: typeof fetch,
  signal: AbortSignal
): Promise<EgressUnreachableAnswer | undefined> {
  const response = await doFetch(EGRESS_REPORT_URL, { method: 'POST', signal });
  if (!response.ok) return undefined;
  return parseAnswer(await response.json());
}

/** Build the report call. Answers `undefined` on any failure, refusal or timeout. */
export function createEgressReporter(
  options: EgressReporterOptions = {}
): () => Promise<EgressUnreachableAnswer | undefined> {
  const doFetch = options.fetchImpl ?? globalThis.fetch;
  const deadlineMs = options.deadlineMs ?? EGRESS_REPORT_DEADLINE_MS;

  return async () => {
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
      return await Promise.race([postReport(doFetch, controller.signal), deadline]);
    } catch {
      return undefined;
    } finally {
      clearTimeout(timer);
    }
  };
}

/** The guidance the result line carries for a report's answer. */
export function egressGuidance(answer: EgressUnreachableAnswer | undefined): string {
  if (!answer) {
    return 'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.';
  }
  if (answer.relocated) {
    return "This org's executor has moved to a new instance. Retry the command now.";
  }
  return `Attempt ${answer.count} of ${answer.threshold} before the executor moves to a new instance. Retry the command.`;
}
