/**
 * Release-age freshness window -- THE implementation. There is no twin any more.
 *
 * A freshly-published dependency, action, image tag or advisory fix is not
 * actionable the instant it ships: bumping to a version a few hours old churns
 * the tree for nothing. So a version is DEFERRED until the next UTC midnight
 * after it has aged the base window, which batches a day's upgrades into one
 * surfacing instead of trickling them in hour by hour.
 *
 *     eligibleAt = startOfNextUtcDay(publishedAt + window)
 *     deferred   = now < eligibleAt                       // effective age 24-48h
 *
 * The base window is `minimum_release_age_minutes` in .ci/config/release-age.json.
 * It is this repo's CI-gate knob, NOT an npm install guard: npm never enforced it,
 * and it moved out of .npmrc once npm 11 began warning about the unknown key.
 *
 * WHY THIS FILE IS THE ONE THAT SURVIVED. Until 2026-09-06 the same rule existed
 * twice: here, and as `is_release_deferred` in .ci/scripts/lib/release-age.sh,
 * joined only by two "keep the two in sync" comments. A comment cannot fail, and
 * the two had already drifted -- see the FALLBACK note on getMinReleaseAgeMs
 * below. The bash is now a shim that delegates every verdict here (`--deferred`
 * / `--eligible-epoch` / `--window-seconds` at the bottom of this file), for
 * three reasons: this side has six consumers to the bash side's two; this side
 * is portable while the bash rounds the day with `date -u -d`, which is GNU-only
 * and these gates run on developer macOS too; and the bash tree is the one
 * scheduled to be ported away, so making it the source of truth would have meant
 * doing this collapse twice.
 *
 * Consumers here: check-deps.ts, check-actions.ts, check-embed-asset-freshness.ts,
 * check-devcontainer-pin-freshness.ts, check-docker-image-freshness.ts, and the
 * bash shim above (audit.sh, check-go-deps.sh).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_CONFIG = path.resolve(__dirname, '..', '..', '.ci', 'config', 'release-age.json');

/**
 * Read `minimum_release_age_minutes` from .ci/config/release-age.json and return
 * it in milliseconds. Returns 0 when the file or the key is absent, or the value
 * is not a non-negative integer -- the feature is then disabled (no deferral).
 *
 * FALLBACK, and the one place the two implementations had genuinely drifted: the
 * bash twin fell back to a hard-coded 86400-second window when no setting was
 * configured, while this one returns 0 and disables deferral outright. Neither is
 * reachable today (check:ci-npmrc gates the setting's presence and value), and the
 * divergence is preserved rather than papered over: the shim applies ITS OWN 86400
 * default before asking for a verdict, exactly the way null-handling is already the
 * caller's policy in isWithinFreshnessWindow below. The RULE lives here once; the
 * missing-config policy stays with each caller, where it always was.
 */
export function getMinReleaseAgeMs(configFile: string = DEFAULT_CONFIG): number {
  try {
    const parsed: unknown = JSON.parse(fs.readFileSync(configFile, 'utf-8'));
    const minutes =
      parsed !== null && typeof parsed === 'object'
        ? (parsed as Record<string, unknown>).minimum_release_age_minutes
        : undefined;
    if (typeof minutes === 'number' && Number.isInteger(minutes) && minutes >= 0) {
      return minutes * 60 * 1000;
    }
  } catch {
    // No config file, or not JSON -- feature disabled.
  }
  return 0;
}

/** Epoch ms of 00:00:00 UTC on the day AFTER the day that contains `ms`. */
function startOfNextUtcDay(ms: number): number {
  const d = new Date(ms);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
}

/**
 * Epoch ms at which a release published at `publishedMs` becomes actionable.
 *
 * The single expression of the rule. isWithinFreshnessWindow() below and the
 * `--eligible-epoch` CLI both go through here, so the bash shim and the six TS
 * gates cannot answer differently: there is only one round-up left in the tree.
 *
 * Module-private on purpose: no caller outside this file needs the raw epoch,
 * and exporting a function nothing imports is the shape `lint:unused` refuses.
 */
function eligibleAtMs(publishedMs: number, minReleaseAgeMs: number): number {
  return startOfNextUtcDay(publishedMs + minReleaseAgeMs);
}

/**
 * True when a release published at `publishedMs` is still within the freshness
 * window as of `nowMs` (i.e. too new to act on yet). Null-handling is the
 * CALLER's policy — this takes a concrete timestamp:
 *   - check-deps treats a null publish time as deferred (fail-closed: don't pull
 *     a version whose age is unknown);
 *   - the embed-asset freshness gate treats null as NOT deferred (fail-open: a
 *     stale pin from a dateless source, e.g. a plain git tag, must still surface).
 */
export function isWithinFreshnessWindow(
  publishedMs: number,
  nowMs: number,
  minReleaseAgeMs: number
): boolean {
  if (minReleaseAgeMs <= 0) return false;
  return nowMs < eligibleAtMs(publishedMs, minReleaseAgeMs);
}

// --------------------------------------------------------------------------- CLI -- the seam .ci/scripts/lib/release-age.sh delegates to.
//
// Seconds in, seconds out, because every bash caller already holds epoch SECONDS (`date -u -d ... +%s`); doing the milliseconds conversion here keeps the unit mismatch from being a second thing two implementations can disagree about. Every mode writes ONE line to stdout and nothing to stderr on success, so the shim can capture it with a plain command substitution.
//
// --window-seconds -> the base window, or 0 if unset --eligible-epoch <publish> [window] -> the epoch it becomes actionable --deferred <publish> [now] [window] -> prints "deferred" or "eligible"
//
// Guarded so importing the module never runs it; the six TS gates import the functions above and must not pay for argv parsing. ---------------------------------------------------------------------------

function cliMain(argv: string[]): number {
  const mode = argv[0] ?? '';
  const num = (v: string | undefined, what: string): number => {
    if (v === undefined || !/^-?\d+$/.test(v)) {
      throw new Error(
        `release-age: ${what} must be an integer number of seconds, got "${v ?? ''}"`
      );
    }
    return Number(v);
  };

  if (mode === '--window-seconds') {
    process.stdout.write(`${Math.floor(getMinReleaseAgeMs() / 1000)}\n`);
    return 0;
  }
  if (mode === '--eligible-epoch') {
    const published = num(argv[1], 'publish epoch');
    const window = argv[2] === undefined ? getMinReleaseAgeMs() / 1000 : num(argv[2], 'window');
    process.stdout.write(`${Math.floor(eligibleAtMs(published * 1000, window * 1000) / 1000)}\n`);
    return 0;
  }
  if (mode === '--deferred') {
    const published = num(argv[1], 'publish epoch');
    const now =
      argv[2] === undefined || argv[2] === '' ? Math.floor(Date.now() / 1000) : num(argv[2], 'now');
    const window = argv[3] === undefined ? getMinReleaseAgeMs() / 1000 : num(argv[3], 'window');
    const deferred = isWithinFreshnessWindow(published * 1000, now * 1000, window * 1000);
    process.stdout.write(`${deferred ? 'deferred' : 'eligible'}\n`);
    return 0;
  }

  throw new Error(
    `release-age: unknown mode "${mode}". Expected --window-seconds, --eligible-epoch or --deferred.`
  );
}

// process.argv[1] is the script path only when this file was EXECUTED. An
// import leaves it pointing at the importer, so the comparison is false and
// nothing runs.
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (invokedPath === fileURLToPath(import.meta.url)) {
  try {
    process.exit(cliMain(process.argv.slice(2)));
  } catch (err) {
    process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
    process.exit(2);
  }
}
