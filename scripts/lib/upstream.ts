/**
 * Asking an upstream, for every gate whose verdict depends on a host outside
 * this repository: the three pin freshness gates
 * (check-real-provider-pin-freshness.ts, check-devcontainer-pin-freshness.ts,
 * check-embed-asset-freshness.ts), the actions pins (check-actions.ts), the
 * external links (check-external-links.ts) and the DKIM DNS records
 * (check-dkim-notify.ts). The Go dependency gate is Python and carries the same
 * rule in `.ci/rediacc_ci/core/upstream.py`; a test compares the two copies'
 * numbers so they cannot drift apart.
 *
 * ONE POLICY, STATED ONCE (operator rulings 2026-10-13, "Fail closed every time"
 * and "Everything fails closed, nightly included", extended to every external
 * gate 2026-10-14, "Extend to all seven"). A thing whose upstream answer was not
 * obtained was NOT compared, and a thing that was not compared is a red
 * finding, never a note beside a green. The gates used to disagree on this: one
 * failed closed, some printed "could not check" and exited 0, and the rest were
 * softened to a warning on the nightly, so a green did not mean the comparison
 * had happened.
 *
 * THE RETRY BUDGET. A request is tried up to MAX_ATTEMPTS (3) times,
 * HTTP_TIMEOUT_MS (15 s) each, with BACKOFF_MS (2 s, then 4 s) between tries,
 * for a failure that can clear in seconds: a network error, a timeout, 408, 429,
 * a 5xx, and a 403 that carries Retry-After. A primary rate limit (403 with
 * x-ratelimit-remaining 0), a 401, a 404 and every other status are answered at
 * once, as is a Retry-After above MAX_RETRY_AFTER_S. The worst case for one
 * request is 3 x 15 s + 2 s + 4 s = 51 s. Each gate asks concurrently, so the
 * budget is spent once per chain of requests, not once per item.
 * retryUpstream() is the same loop for a request that is not HTTP (a DNS
 * query), with the caller classifying its own failures.
 *
 * WHAT A FINDING NAMES: the method, the host and path asked (no query string,
 * no header, no token), the status or the error's own code (never its message,
 * which can carry a URL), and the number of attempts. reportUnreachable() adds
 * the sentence that tells a reader of a red nightly what kind of red this is:
 * an upstream reachability failure, with the host, and nothing to change in the
 * tree. `.ci/rediacc_ci/ci/ci_diagnose.py` reads that same sentence (signature
 * `upstream-unreachable`), so `ci-trace.py --why` and the scheduled-red block
 * name it instead of reporting an unknown.
 *
 * THE TOKEN GOES TO api.github.com AND NOWHERE ELSE. Each gate has a seam that
 * points it at another base (a stub server in its test, an unreachable host for
 * a hand-driven offline run); githubAsker() drops the Authorization header
 * whenever that seam is set.
 *
 * PinTally IS THE COUNT A PIN GATE'S GREEN RESTS ON. Every source ends in
 * exactly one bucket: compared, held by a BLOCKER-reasoned blocklist entry,
 * without a pin, not compared, or answered unusably. report() prints the last
 * three and returns how many pins a green may not hide; a source in no bucket
 * is counted there too, so a gate that loses track of one cannot pass.
 */

import { setTimeout as sleep } from 'node:timers/promises';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { errorLines, NC, RED, YELLOW } from './console.js';
import { githubApiHeaders } from './github-token.js';

// The retry budget. `.ci/rediacc_ci/core/upstream.py` carries the same four numbers for the Python gate, and `.ci/rediacc_ci/tests/test_core_upstream.py` fails when the two copies disagree.
export const HTTP_TIMEOUT_MS = 15_000;
export const MAX_ATTEMPTS = 3;
export const BACKOFF_MS: readonly number[] = [2_000, 4_000];
// A server that asks for a longer wait than this is not retried: the wait would not fit the budget above.
export const MAX_RETRY_AFTER_S = 10;

/** The upstream answered and the answer cannot be used: red, and not a network failure. */
export class UnreadableListing extends Error {}

/** The upstream's answer was not obtained, so the thing it was asked about was not compared: red. */
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
    readonly status: number | null,
    /**
     * True when the host never gave an answer about the thing asked: no response, a timeout, 408, 429, a 5xx or a
     * rate limit. False for a definite answer (a 404, a refused token), which a link checker reads as a broken link
     * and not as an outage.
     */
    readonly unreachable: boolean = true
  ) {
    // A fixture lookup makes no request, so "after 0 attempt(s)" would claim a try that never happened.
    super(
      attempts > 0 ? `${asked} -> ${what}, after ${attempts} attempt(s)` : `${asked} -> ${what}`
    );
  }

  /** A fixture map that holds no entry for `key`: the test seam's way of saying the upstream did not answer. */
  static absentFromFixture(key: string): NotCompared {
    return new NotCompared('no entry in the fixture', 'the fixture', `fixture ${key}`, 0, null);
  }
}

/**
 * A GitHub release list that came back EMPTY for a repository the gate tracks. That is almost always the API failing to
 * answer (seen 2026-10-22 during GitHub's "Actions Results" incident: four sources at once answered 200 with no release,
 * while the same calls minutes later returned 100, 90 and 44), not a changed tag scheme, so it is reported as not compared,
 * the reachability class. The other cause, a repository that really lost every release, is named in the finding too, so a
 * reader whose re-run stays empty checks the repository instead of waiting.
 */
export function emptyReleaseList(repo: string, attempts = 1): NotCompared {
  return new NotCompared(
    'HTTP 200 with an empty release list (a GitHub API outage, or the repository lost every release: check it if a re-run stays empty)',
    'api.github.com',
    `GET api.github.com/repos/${repo}/releases`,
    attempts,
    200
  );
}

/**
 * A repository's GitHub release list, asking again on an EMPTY answer with the same numbers as a transient failure
 * (MAX_ATTEMPTS, BACKOFF_MS). The two budgets NEST: each attempt here is one `ask`, which retries its own transient
 * failures, so the worst case is MAX_ATTEMPTS x MAX_ATTEMPTS requests for one repository. Measured 2026-10-22 after the incident: 3 of 10 identical calls for go-delve/delve answered
 * 200 with an empty list and 7 with all 44 releases, so one empty answer is noise and only an empty answer on every
 * attempt is reported (emptyReleaseList). A non-array answer is returned as is, for the caller's UnreadableListing check.
 */
export async function askReleaseList(
  ask: (apiPath: string, who: string) => Promise<unknown>,
  repo: string,
  who: string
): Promise<unknown> {
  for (let attempt = 1; ; attempt++) {
    const listing = await ask(`/repos/${repo}/releases?per_page=100`, who);
    if (!Array.isArray(listing) || listing.length > 0) return listing;
    if (attempt >= MAX_ATTEMPTS) throw emptyReleaseList(repo, attempt);
    await sleep(BACKOFF_MS[attempt - 1] ?? 0);
  }
}

/** One failed attempt: what answered, whether asking again within the budget can help, and whether it was an answer at all. */
export interface Failure {
  what: string;
  retry: boolean;
  status: number | null;
  /** Seconds the server asked for, when it did. */
  retryAfterS: number | null;
  /** See NotCompared.unreachable. */
  unreachable: boolean;
}

/** What an HTTP status that is not 2xx means for an external gate. */
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
    return {
      what: `HTTP 403 (rate limit${reset})`,
      retry: false,
      status,
      retryAfterS,
      unreachable: true,
    };
  }
  if (status === 429 || (status === 403 && retryAfterS !== null)) {
    return {
      what: `HTTP ${status} (rate limit)`,
      retry: true,
      status,
      retryAfterS,
      unreachable: true,
    };
  }
  if (status === 401 || status === 403) {
    return {
      what: `HTTP ${status} (the token was refused)`,
      retry: false,
      status,
      retryAfterS,
      unreachable: false,
    };
  }
  const transient = status === 408 || status >= 500;
  return { what: `HTTP ${status}`, retry: transient, status, retryAfterS, unreachable: transient };
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
      unreachable: true,
    };
  }
  const cause = err instanceof Error ? (err.cause as { code?: unknown } | undefined) : undefined;
  const code = typeof cause?.code === 'string' ? cause.code : name;
  return {
    what: `network error ${code}`,
    retry: true,
    status: null,
    retryAfterS: null,
    unreachable: true,
  };
}

export interface UpstreamAsk {
  url: string;
  headers: Record<string, string>;
  /** Whose pin, link or record this request serves, for the retry note. */
  who: string;
  /** HEAD asks for the headers alone; the body is never read. */
  method?: 'GET' | 'HEAD';
  /**
   * Fewer attempts than MAX_ATTEMPTS, never more. The one caller is the link checker's last-chance GET, which only
   * follows a request that has already spent the full budget on the same URL.
   */
  maxAttempts?: number;
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
): Promise<{ value: UpstreamAnswer } | Failure> {
  try {
    const res = await fetch(ask.url, {
      method,
      headers: ask.headers,
      signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
    });
    if (!res.ok) return classifyStatus(res);
    return { value: { headers: res.headers, body: method === 'HEAD' ? '' : await res.text() } };
  } catch (err) {
    return classifyThrown(err);
  }
}

/** What retryUpstream() is told about the request, for the finding and the retry note. */
export interface RetryTarget {
  /** As the finding prints it, e.g. `GET api.github.com/repos/x/y/releases` or `TXT a._domainkey.example.org`. */
  asked: string;
  host: string;
  who: string;
  maxAttempts?: number;
}

/**
 * The retry loop itself, for any kind of request. `once` makes one attempt and returns `{ value }` or a Failure it
 * classified itself. Throws NotCompared once the budget is spent or the failure is not worth asking again.
 */
export async function retryUpstream<T>(
  target: RetryTarget,
  once: () => Promise<{ value: T } | Failure>
): Promise<T> {
  const limit = Math.min(target.maxAttempts ?? MAX_ATTEMPTS, MAX_ATTEMPTS);
  for (let tries = 1; ; tries++) {
    const answer = await once();
    if ('value' in answer) return answer.value;
    const waitMs = Math.max(BACKOFF_MS[tries - 1] ?? 0, (answer.retryAfterS ?? 0) * 1000);
    const fits = (answer.retryAfterS ?? 0) <= MAX_RETRY_AFTER_S;
    if (tries >= limit || !answer.retry || !fits) {
      throw new NotCompared(
        answer.what,
        target.host,
        target.asked,
        tries,
        answer.status,
        answer.unreachable
      );
    }
    // Progress, so stderr: a caller printing `--json` on stdout must stay parseable.
    console.error(
      `${YELLOW}? ${target.who}: attempt ${tries} of ${limit} failed (${answer.what}), asking again in ${waitMs / 1000} s${NC}`
    );
    await sleep(waitMs);
  }
}

/** Ask an upstream over HTTP, up to MAX_ATTEMPTS times. Throws NotCompared when no usable response arrived. */
export function askUpstream(ask: UpstreamAsk): Promise<UpstreamAnswer> {
  const method = ask.method ?? 'GET';
  const url = new URL(ask.url);
  return retryUpstream(
    {
      asked: `${method} ${url.host}${url.pathname}`,
      host: url.host,
      who: ask.who,
      maxAttempts: ask.maxAttempts,
    },
    () => attempt(ask, method)
  );
}

/** The default local remedy under an unreachability finding: the hosts these gates ask most are GitHub's. */
const GITHUB_HINT = [
  '  (https://www.githubstatus.com for api.github.com), and re-run the failed job when',
  '  this is a nightly. A rate limit locally means the request went out without a',
  '  token; `gh auth login` or GITHUB_TOKEN supplies one.',
];

/**
 * Print the fail-closed finding for things whose upstream did not answer: one line per thing, then the sentence
 * `ci_diagnose.py`'s `upstream-unreachable` signature reads ("were NOT compared with upstream" and "UPSTREAM
 * REACHABILITY FAILURE"). `subject` is the plural noun with its count suffix, e.g. "real-provider pin(s)" or
 * "external link(s)". `notA` names the finding this is NOT ("a stale pin", "a broken link"), and `hint` replaces
 * the GitHub-specific remedy lines for a gate that asks another host.
 */
export function reportUnreachable(
  subject: string,
  items: ReadonlyArray<{ who: string; err: NotCompared }>,
  opts: { notA?: string; hint?: readonly string[] } = {}
): void {
  if (items.length === 0) return;
  const notA = opts.notA ?? 'a stale pin';
  const hint = opts.hint ?? GITHUB_HINT;
  const hosts = [...new Set(items.map((f) => f.err.host))].join(', ');
  console.error('');
  console.error(`${RED}✗ ${items.length} ${subject} were NOT compared with upstream:${NC}`);
  for (const f of items) console.error(`  ${f.who}: ${f.err.message}`);
  errorLines(
    `  UPSTREAM REACHABILITY FAILURE (${hosts}), not ${notA} and not a defect in the tree.`,
    '  The comparison did not happen, so this run says nothing about whether these',
    '  are current, and it fails closed instead of passing unchecked. Nothing in the tree',
    '  needs a change for this finding: run the gate again once the host answers',
    ...hint
  );
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
    return askUpstreamJson({
      url: `${baseOverride === undefined || baseOverride === '' ? WK_GH_API_BASE : baseOverride}${apiPath}`,
      headers,
      who,
    });
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
   * `upstream-unreachable` signature matches (reportUnreachable).
   */
  report(hints: ReportHints): number {
    reportUnreachable(
      `${this.noun} pin(s)`,
      this.notCompared.map((f) => ({ who: f.pin, err: f.err }))
    );
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
    if (this.noPin.length > 0) {
      console.error('');
      console.error(`${RED}✗ a watched source has no pin to compare:${NC}`);
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
      this.noPin.length +
      Math.abs(this.total - seen)
    );
  }
}
