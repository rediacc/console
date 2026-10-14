/**
 * Asking an upstream what its newest release is, for the three pin freshness
 * gates: check-real-provider-pin-freshness.ts, check-devcontainer-pin-freshness.ts
 * and check-embed-asset-freshness.ts.
 *
 * ONE POLICY, STATED ONCE (operator rulings 2026-10-13, "Fail closed every time"
 * and "Everything fails closed, nightly included"). A pin whose upstream answer
 * was not obtained was NOT compared, and a pin that was not compared is a red
 * finding, never a note beside a green. The three gates used to disagree on
 * this: one failed closed and two printed "could not check" and exited 0, so a
 * green from either of those did not mean the pins had been compared.
 *
 * THE RETRY BUDGET. A request is tried up to MAX_ATTEMPTS (3) times,
 * HTTP_TIMEOUT_MS (15 s) each, with BACKOFF_MS (2 s, then 4 s) between tries,
 * for a failure that can clear in seconds: a network error, a timeout, 408, 429,
 * a 5xx, and a 403 that carries Retry-After. A primary rate limit (403 with
 * x-ratelimit-remaining 0), a 401, a 404 and every other status are answered at
 * once, as is a Retry-After above MAX_RETRY_AFTER_S. The worst case for one
 * request is 3 x 15 s + 2 s + 4 s = 51 s. Each gate asks its pins concurrently,
 * so the budget is spent once per chain of requests, not once per pin.
 *
 * WHAT A FINDING NAMES: the method, the host and path asked (no query string,
 * no header, no token), the status or the error's own code (never its message,
 * which can carry a URL), and the number of attempts. PinTally.report() adds
 * the sentence that tells a reader of a red nightly what kind of red this is:
 * an upstream reachability failure, with the host, and nothing to change in the
 * tree. `.ci/rediacc_ci/ci/ci_diagnose.py` reads that same sentence (signature
 * `pin-upstream-unreachable`), so `ci-trace.py --why` and the scheduled-red
 * block name it instead of reporting an unknown.
 *
 * THE TOKEN GOES TO api.github.com AND NOWHERE ELSE. Each gate has a seam that
 * points it at another base (a stub server in its test, an unreachable host for
 * a hand-driven offline run); githubAsker() drops the Authorization header
 * whenever that seam is set.
 *
 * PinTally IS THE COUNT A GREEN RESTS ON. Every source ends in exactly one
 * bucket: compared, held by a BLOCKER-reasoned blocklist entry, without a pin,
 * not compared, or answered unusably. report() prints the last three and
 * returns how many pins a green may not hide; a source in no bucket is counted
 * there too, so a gate that loses track of one cannot pass.
 */

import { setTimeout as sleep } from 'node:timers/promises';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { errorLines, NC, RED, YELLOW } from './console.js';
import { githubApiHeaders } from './github-token.js';

const HTTP_TIMEOUT_MS = 15_000;
const MAX_ATTEMPTS = 3;
const BACKOFF_MS = [2_000, 4_000];
// A server that asks for a longer wait than this is not retried: the wait would not fit the budget above.
const MAX_RETRY_AFTER_S = 10;

/** The upstream answered and the answer cannot be used: red, and not a network failure. */
export class UnreadableListing extends Error {}

/** The upstream's answer was not obtained, so the pin was not compared: red. */
export class NotCompared extends Error {
  constructor(
    /** The status or error code of the last attempt. */
    readonly what: string,
    /** The host that was asked, or the fixture that held no entry. */
    readonly host: string,
    /** What was asked, as the finding prints it: method, host and path, with no query, no token and no header. */
    readonly asked: string,
    readonly attempts: number,
    /** The HTTP status of the last attempt, or null when no response arrived. */
    readonly status: number | null
  ) {
    super(`${asked} -> ${what}, after ${attempts} attempt(s)`);
  }

  /** A fixture map that holds no entry for `key`: the test seam's way of saying the upstream did not answer. */
  static absentFromFixture(key: string): NotCompared {
    return new NotCompared('no entry in the fixture', 'the fixture', `fixture ${key}`, 0, null);
  }
}

/** One failed attempt: what answered, and whether asking again within the budget can help. */
interface Failure {
  what: string;
  retry: boolean;
  status: number | null;
  /** Seconds the server asked for, when it did. */
  retryAfterS: number | null;
}

/** What an HTTP status that is not 2xx means for a pin gate. */
function classifyStatus(res: Response): Failure {
  const header = res.headers.get('retry-after');
  const retryAfterS = header !== null && /^\d+$/.test(header) ? Number(header) : null;
  const status = res.status;
  if (status === 403 && res.headers.get('x-ratelimit-remaining') === '0') {
    const resetS = Number(res.headers.get('x-ratelimit-reset'));
    const reset =
      Number.isFinite(resetS) && resetS > 0
        ? `, resets ${new Date(resetS * 1000).toISOString()}`
        : '';
    // The primary limit resets on the hour, so no wait inside the budget clears it.
    return { what: `HTTP 403 (rate limit${reset})`, retry: false, status, retryAfterS };
  }
  if (status === 429 || (status === 403 && retryAfterS !== null)) {
    return { what: `HTTP ${status} (rate limit)`, retry: true, status, retryAfterS };
  }
  if (status === 401 || status === 403) {
    return { what: `HTTP ${status} (the token was refused)`, retry: false, status, retryAfterS };
  }
  return { what: `HTTP ${status}`, retry: status === 408 || status >= 500, status, retryAfterS };
}

/** What a request that never produced a readable response means: the error's own code, never its message, which can carry a URL. */
function classifyThrown(err: unknown): Failure {
  const name = err instanceof Error ? err.name : 'Error';
  if (name === 'TimeoutError' || name === 'AbortError') {
    return {
      what: `timeout after ${HTTP_TIMEOUT_MS / 1000} s`,
      retry: true,
      status: null,
      retryAfterS: null,
    };
  }
  const cause = err instanceof Error ? (err.cause as { code?: unknown } | undefined) : undefined;
  const code = typeof cause?.code === 'string' ? cause.code : name;
  return { what: `network error ${code}`, retry: true, status: null, retryAfterS: null };
}

export interface UpstreamAsk {
  url: string;
  headers: Record<string, string>;
  /** Whose pin this request serves, for the retry note. */
  who: string;
  /** HEAD asks for the headers alone; the body is never read. */
  method?: 'GET' | 'HEAD';
}

/** What a successful request hands back: the response headers, and the body as text (empty for HEAD). */
interface UpstreamAnswer {
  headers: Headers;
  body: string;
}

/** One request, body included: a connection that drops while the body is read is a failed attempt like any other. */
async function attempt(
  ask: UpstreamAsk,
  method: 'GET' | 'HEAD'
): Promise<UpstreamAnswer | Failure> {
  try {
    const res = await fetch(ask.url, {
      method,
      headers: ask.headers,
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    });
    if (!res.ok) return classifyStatus(res);
    return { headers: res.headers, body: method === 'HEAD' ? '' : await res.text() };
  } catch (err) {
    return classifyThrown(err);
  }
}

/** Ask an upstream, up to MAX_ATTEMPTS times. Throws NotCompared when no usable response arrived. */
export async function askUpstream(ask: UpstreamAsk): Promise<UpstreamAnswer> {
  const method = ask.method ?? 'GET';
  const url = new URL(ask.url);
  const asked = `${method} ${url.host}${url.pathname}`;
  for (let tries = 1; ; tries++) {
    const answer = await attempt(ask, method);
    if ('body' in answer) return answer;
    const waitMs = Math.max(BACKOFF_MS[tries - 1] ?? 0, (answer.retryAfterS ?? 0) * 1000);
    const fits = (answer.retryAfterS ?? 0) <= MAX_RETRY_AFTER_S;
    if (tries >= MAX_ATTEMPTS || !answer.retry || !fits) {
      throw new NotCompared(answer.what, url.host, asked, tries, answer.status);
    }
    console.log(
      `${YELLOW}? ${ask.who}: attempt ${tries} of ${MAX_ATTEMPTS} failed (${answer.what}), asking again in ${waitMs / 1000} s${NC}`
    );
    await sleep(waitMs);
  }
}

/** askUpstream, with the body parsed. A 2xx that is not JSON throws UnreadableListing: the host answered, and not with a listing. */
async function askUpstreamJson(ask: UpstreamAsk): Promise<unknown> {
  const { body } = await askUpstream(ask);
  try {
    return JSON.parse(body);
  } catch {
    throw new UnreadableListing('the response is not JSON');
  }
}

/**
 * A function that asks the GitHub REST API for `apiPath` on behalf of `who`'s
 * pin. `baseOverride` is the gate's seam: when it is set the request goes
 * there instead of api.github.com, and it carries no token.
 */
export function githubAsker(
  userAgent: string,
  baseOverride: string | undefined
): (apiPath: string, who: string) => Promise<unknown> {
  return (apiPath, who) => {
    const headers = githubApiHeaders(userAgent);
    if (baseOverride) delete headers.Authorization;
    return askUpstreamJson({ url: `${baseOverride || WK_GH_API_BASE}${apiPath}`, headers, who });
  };
}

/** One source's answer: the value, the error it threw, or null when it was not asked at all. */
type Asked<T> = { value: T } | { err: unknown } | null;

/** What report() needs to know about the gate it speaks for. */
interface ReportHints {
  /** Where a reader checks a source that answered unusably, e.g. a file path. */
  sources: string;
  /** How to put a missing pin back. Omitted by a gate whose pins cannot be missing. */
  noPinFix?: string[];
  /** A missing pin is the check run's finding; --upgrade prints it and leaves the verdict to the check. */
  noPinIsRed?: boolean;
}

/** Where every source of one gate run ended up. See the header. */
export class PinTally {
  compared = 0;
  readonly held: string[] = [];
  readonly noPin: string[] = [];
  private readonly notCompared: Array<{ pin: string; err: NotCompared }> = [];
  private readonly unreadable: string[] = [];

  constructor(
    /** The gate's pins as its messages name them: "devcontainer", "embed-asset", "real-provider". */
    private readonly noun: string,
    private readonly total: number
  ) {}

  /**
   * Ask every source at once, so the retry budget is spent once and not once
   * per pin, and hand the answers back in the sources' order. `ask` returns
   * null for a source that must not be asked (a held pin, a source with no pin).
   */
  askAll<S, T>(sources: readonly S[], ask: (src: S) => Promise<T> | null): Promise<Asked<T>[]> {
    return Promise.all(
      sources.map((src) => {
        const pending = ask(src);
        if (pending === null) return null;
        return pending.then(
          (value) => ({ value }),
          (err: unknown) => ({ err })
        );
      })
    );
  }

  /** Record an ask that threw. FAIL CLOSED: both known errors are findings. Anything else is a defect in the gate and is rethrown. */
  failed(pin: string, source: string, err: unknown): void {
    if (err instanceof NotCompared) this.notCompared.push({ pin, err });
    else if (err instanceof UnreadableListing) this.unreadable.push(`${source}: ${err.message}`);
    else throw err;
  }

  /** The line a green prints, so a reader can see the count was not trivial. */
  get shape(): string {
    return `${this.compared} of ${this.total} compared with upstream, ${this.held.length} held`;
  }

  /**
   * Print every fail-closed finding and return how many pins a green may not
   * hide. The wording is read by people and by `ci_diagnose.py`: "were NOT
   * compared with upstream" and "UPSTREAM REACHABILITY FAILURE" are what its
   * `pin-upstream-unreachable` signature matches.
   */
  report(hints: ReportHints): number {
    if (this.notCompared.length > 0) {
      const hosts = [...new Set(this.notCompared.map((f) => f.err.host))].join(', ');
      console.error('');
      console.error(
        `${RED}✗ ${this.notCompared.length} ${this.noun} pin(s) were NOT compared with upstream:${NC}`
      );
      for (const f of this.notCompared) console.error(`  ${f.pin}: ${f.err.message}`);
      errorLines(
        `  UPSTREAM REACHABILITY FAILURE (${hosts}), not a stale pin and not a defect in the tree.`,
        '  The comparison did not happen, so this run says nothing about whether these pins',
        '  are current, and it fails closed instead of passing unchecked. Nothing in the tree',
        '  needs a change for this finding: run the gate again once the host answers',
        '  (https://www.githubstatus.com for api.github.com), and re-run the failed job when',
        '  this is a nightly. A rate limit locally means the request went out without a',
        '  token; `gh auth login` or GITHUB_TOKEN supplies one.'
      );
    }
    if (this.unreadable.length > 0) {
      console.error('');
      console.error(`${RED}✗ upstream answered with something this gate cannot use:${NC}`);
      for (const line of this.unreadable) console.error(`  ${line}`);
      errorLines(
        '  The comparison did not happen for these pins, and this is not a network failure:',
        '  the gate would never see a new release again. Check the source and its tag',
        `  scheme against ${hints.sources}.`
      );
    }
    const noPinIsRed = hints.noPinIsRed ?? true;
    if (this.noPin.length > 0) {
      console.error('');
      console.error(`${noPinIsRed ? RED : YELLOW}✗ a watched source has no pin to compare:${NC}`);
      for (const line of this.noPin) console.error(`  ${line}`);
      errorLines(...(hints.noPinFix ?? []));
    }
    const seen =
      this.compared +
      this.held.length +
      this.noPin.length +
      this.notCompared.length +
      this.unreadable.length;
    if (seen !== this.total) {
      console.error(
        `${RED}✗ ${seen} of ${this.total} ${this.noun} source(s) were accounted for; a green here would rest on a pin nobody judged${NC}`
      );
    }
    return (
      this.notCompared.length +
      this.unreadable.length +
      (noPinIsRed ? this.noPin.length : 0) +
      Math.abs(this.total - seen)
    );
  }
}
