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

function scanContent(file: string, content: string): Violation[] {
  const hits: Violation[] = [];
  for (const { token, allow } of BANNED) {
    if (!content.includes(token)) continue;
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
