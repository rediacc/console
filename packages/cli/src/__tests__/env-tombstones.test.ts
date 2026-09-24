import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Tombstone gate: the "config is the universe" + env cleanup refactor renamed or
 * deleted a set of environment variables, functions, and files. This test walks
 * the CLI and shared source trees and fails if any retired name reappears, so a
 * later change cannot silently resurrect `server.json`, `RDC_UPDATE_CHANNEL`,
 * `loadServerConfig`, etc.
 */

const HERE = dirname(fileURLToPath(import.meta.url)); // packages/cli/src/__tests__
const CLI_SRC = join(HERE, '..'); // packages/cli/src
const SHARED_SRC = join(HERE, '..', '..', '..', 'shared', 'src'); // packages/shared/src
const SELF = fileURLToPath(import.meta.url);

interface Banned {
  token: string;
  /** Repo-relative-ish file suffixes where this token is legitimately allowed. */
  allow?: string[];
  /**
   * Match only an ENVIRONMENT READ of this name, not the bare word.
   *
   * Needed the moment a retired variable's name is also an ordinary English token. `DEBUG`
   * is the case that forced it: retired in favour of the REDIACC_DEBUG scopes, but the
   * word appears legitimately four times over as a LOG LEVEL -- a severity label
   * `'DEBUG'`, a `[DEBUG]` prefix, `BUILD_TYPE: 'DEBUG'`, and `'DEBUG:'` line prefixes in
   * a parser. Banning the bare word reports all four, so the ban was simply omitted and
   * the tombstone went unenforced. Every other entry here is `REDIACC_`/`RDC_`-prefixed
   * and cannot collide, which is why the plain form is still the default.
   */
  envOnly?: boolean;
}

const BANNED: Banned[] = [
  // REMOTE plane literal survives only in the executor's renet env builder.
  { token: 'REDIACC_ENVIRONMENT', allow: ['services/executor/local-executor.ts'] },
  { token: 'REDIACC_SUBSCRIPTION_TOKEN_FILE' },
  { token: 'REDIACC_SUBSCRIPTION_TOKEN' },
  { token: 'REDIACC_API_TOKEN' },
  { token: 'REDIACC_EXECUTOR_TOKEN' },
  { token: 'REDIACC_NO_COLOR' },
  { token: 'REDIACC_DAEMON_DEBUG' },
  { token: 'RDC_UPDATE_CHANNEL' },
  { token: 'RDC_DISABLE_AUTOUPDATE' },
  { token: 'RDC_UPDATE_INTERVAL_HOURS' },
  { token: 'RDC_ALLOW_DOWNGRADE' },
  { token: 'RDC_SKIP_ROUTER_RESTART' },
  { token: 'RDC_SKIP_SETUP_CHECK' },
  { token: 'RDC_DEBUG_RENET_PROVISION' },
  { token: 'RDC_TIMING_CHART' },
  // `docs/environment-variables.md:107` retires this in favour of the REDIACC_DEBUG scopes, and until 2026-09-09 nothing enforced it -- the bare name could not be added
  // while the matcher was a substring test, because it swallows every REDIACC_DEBUG.
  // Scoped to the CLI and shared surfaces this file walks: `DEBUG` is ALSO the npm `debug`
  // package's variable and the CI harness's `DEBUG=true` switch (`.ci/rediacc_ci/env/create_e2e_env.py`), so a
  // repo-wide ban would be false.
  { token: 'DEBUG', envOnly: true },
  { token: 'isDevelopmentSubscriptionMode' },
  { token: 'process.env.REDIACC_TEAM' },
  { token: 'process.env.REDIACC_REGION' },
  { token: 'process.env.X25519_PUBLIC_KEY' },
  { token: 'loadServerConfig' },
  { token: 'saveServerConfig' },
  // The bare reserved-file literal is allowed only in the storage exclusion list.
  { token: "'server.json'", allow: ['adapters/config-file-storage.ts'] },
];

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    // Skip test fixtures/specs and this scanner itself.
    if (entry === '__tests__' || entry === 'node_modules' || entry === 'dist') continue;
    if (full === SELF) continue;
    const st = statSync(full);
    if (st.isDirectory()) {
      yield* walk(full);
    } else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith('.d.ts')) {
      yield full;
    }
  }
}

interface Violation {
  file: string;
  token: string;
}

/**
 * WORD-BOUNDED, NOT `includes`. A substring match cannot express a banned name that is a
 * PREFIX of a live one, and this list has exactly that case: `DEBUG` is retired in favour
 * of the `REDIACC_DEBUG` scopes, and under `content.includes('DEBUG')` every one of
 * `REDIACC_DEBUG`, `REDIACC_DAEMON_DEBUG` and `RDC_DEBUG_RENET_PROVISION` reads as a
 * violation. The ban was simply left out rather than made precise, so a documented
 * tombstone had no enforcement at all.
 *
 * The same defect was found the same day in `collision_findings` in the env-manifest gate,
 * where a substring authority let a file naming the REPLACEMENT satisfy the check for the
 * RETIRED name. Both are the shape where a token happens to be a prefix of its successor.
 */
function tokenPattern(token: string, envOnly?: boolean): RegExp {
  const safe = token.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (envOnly) {
    // `process.env.X`, `process.env['X']`, and a destructured or aliased `env.X`.
    return new RegExp(
      `\\benv\\s*(?:\\.\\s*${safe}(?![A-Za-z0-9_])|\\[\\s*['"\`]${safe}['"\`]\\s*\\])`
    );
  }
  return new RegExp(`(?<![A-Za-z0-9_])${safe}(?![A-Za-z0-9_])`);
}

function scanContent(file: string, content: string): Violation[] {
  const hits: Violation[] = [];
  for (const { token, allow, envOnly } of BANNED) {
    if (!tokenPattern(token, envOnly).test(content)) continue;
    if (allow?.some((suffix) => file.replaceAll('\\', '/').endsWith(suffix))) continue;
    hits.push({ file, token });
  }
  return hits;
}

function findViolations(): Violation[] {
  const violations: Violation[] = [];
  for (const root of [CLI_SRC, SHARED_SRC]) {
    for (const file of walk(root)) {
      violations.push(...scanContent(file, readFileSync(file, 'utf-8')));
    }
  }
  return violations;
}

describe('env-var / API tombstones', () => {
  it('control: the scanner fires on a known banned name (prove the instrument)', () => {
    const fixture = 'const t = process.env.REDIACC_API_TOKEN;';
    const hits = scanContent('/synthetic/fixture.ts', fixture);
    expect(hits.map((h) => h.token)).toContain('REDIACC_API_TOKEN');
  });

  it('control: the scanner is silent on clean content', () => {
    expect(scanContent('/synthetic/clean.ts', 'const t = process.env.REDIACC_TOKEN;')).toEqual([]);
  });

  it('no retired names survive in cli/src or shared/src', () => {
    const violations = findViolations();
    const report = violations
      .map((v) => `${relative(join(HERE, '..', '..', '..'), v.file)} :: ${v.token}`)
      .sort();
    expect(report).toEqual([]);
  });
});
