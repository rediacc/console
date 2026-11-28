import { describe, expect, it } from 'vitest';
import {
  EXECUTOR_ACCOUNT_PREFIX,
  EXECUTOR_ACCOUNT_ROUTES,
  executorAccountPath,
  matchExecutorRoute,
} from '../executor-account-routes.js';

const LINEAGE = '0f1e2d3c-4b5a-6978-8a9b-acbdcedf0011';
const SNAPSHOT = '20261127T101500Z-0123456789abcdef';
const MACHINE = 'a'.repeat(32) + 'B'.repeat(32);
const UUID = '0f1e2d3c-4b5a-6978-8a9b-acbdcedf0011';

/** Split a CLI path `/account/api/v1/<inner>?<query>` into its inner path and query. */
function split(cliPath: string): [string, string] {
  const url = new URL(cliPath, 'https://account.invalid');
  expect(url.pathname.startsWith('/account/api/v1/')).toBe(true);
  return [url.pathname.slice('/account/api/v1/'.length), url.search];
}

function match(method: string, cliPath: string) {
  const [inner, query] = split(cliPath);
  return matchExecutorRoute(method, inner, query);
}

describe('matchExecutorRoute controls: calls outside the table match nothing', () => {
  it.each([
    ['the sealed tunnel', 'POST', '/account/api/v1/tunnel'],
    ['immutability set (not proxy-capable)', 'PUT', '/account/api/v1/backups/immutability'],
    [
      'a manifests read with an unlisted teamId',
      'GET',
      '/account/api/v1/backups/manifests?teamId=x',
    ],
    [
      'a lineage segment carrying a slash',
      'POST',
      `/account/api/v1/backups/lineages/${LINEAGE}%2Fx/orphan`,
    ],
    [
      'a lineage segment of 65 characters',
      'DELETE',
      `/account/api/v1/backups/lineages/${'a'.repeat(65)}`,
    ],
    [
      'snapshots delete (not proxy-capable)',
      'DELETE',
      `/account/api/v1/backups/snapshots/${SNAPSHOT}`,
    ],
    ['the session-authenticated backup route', 'GET', '/account/api/v1/backups/session'],
    ['token CRUD', 'GET', '/account/api/v1/api-tokens'],
    ['retention set (not proxy-capable)', 'PUT', '/account/api/v1/backups/retention?lineage=x'],
    [
      'retention clear (not proxy-capable)',
      'DELETE',
      '/account/api/v1/backups/retention?lineage=x',
    ],
    [
      'purge cancel (not served)',
      'POST',
      `/account/api/v1/backups/lineages/${LINEAGE}/purge/cancel`,
    ],
    ['a machine id that is not 64 hex', 'POST', '/account/api/v1/licenses/machines/m-1/deactivate'],
    [
      'an upper-case retire GUID',
      'POST',
      `/account/api/v1/licenses/repos/${UUID.toUpperCase()}/retire`,
    ],
    ['a trailing slash', 'GET', '/account/api/v1/backups/usage/'],
    ['the wrong method on a listed path', 'POST', '/account/api/v1/backups/usage'],
  ])('%s', (_label, method, cliPath) => {
    expect(match(method, cliPath)).toBeUndefined();
  });

  it('a literal slash inside a raw lineage segment adds a segment and matches nothing', () => {
    expect(matchExecutorRoute('DELETE', `backups/lineages/${LINEAGE}/x`)).toBeUndefined();
    expect(matchExecutorRoute('DELETE', 'backups/lineages/')).toBeUndefined();
  });

  it('a query string left in the path matches nothing', () => {
    expect(matchExecutorRoute('GET', 'backups/usage?x=1')).toBeUndefined();
  });

  it('the old PL1 executor licence paths are not inner paths of the table', () => {
    expect(matchExecutorRoute('POST', 'proxy/licenses/activate-repo')).toBeUndefined();
  });
});

// Every served caller of PLAN-executor-account-routes Context 3 and 4, in the
// shape the CLI sends it today.
const SERVED: [string, string, string, string][] = [
  [
    'backup check manifests',
    'GET',
    `/account/api/v1/backups/manifests?lineage=${LINEAGE}&limit=1`,
    'backups/manifests',
  ],
  [
    'backup check verification',
    'POST',
    `/account/api/v1/backups/snapshots/${SNAPSHOT}/verification`,
    'backups/snapshots/:snapshot/verification',
  ],
  ['backup verify', 'POST', '/account/api/v1/backups/verify', 'backups/verify'],
  ['backup repair', 'POST', '/account/api/v1/backups/chunks/repair', 'backups/chunks/repair'],
  [
    'backup restore resolve (anchor)',
    'GET',
    `/account/api/v1/backups/snapshots/resolve?lineage=${LINEAGE}&anchorSnapshotId=${SNAPSHOT}&storeId=home`,
    'backups/snapshots/resolve',
  ],
  [
    'backup restore resolve (any stream, at, index)',
    'GET',
    `/account/api/v1/backups/snapshots/resolve?lineage=${LINEAGE}&anyStream=1&at=2026-11-27T10%3A15%3A00Z&needIndex=1`,
    'backups/snapshots/resolve',
  ],
  [
    'backup restore route manifests',
    'GET',
    `/account/api/v1/backups/manifests?lineage=${LINEAGE}&limit=1`,
    'backups/manifests',
  ],
  [
    'store pick lineage stores',
    'GET',
    `/account/api/v1/backups/stores/lineage/${LINEAGE}`,
    'backups/stores/lineage/:lineage',
  ],
  ['backup reconcile', 'POST', '/account/api/v1/backups/reconcile', 'backups/reconcile'],
  ['backup usage', 'GET', '/account/api/v1/backups/usage', 'backups/usage'],
  [
    'backup manifests (every flag)',
    'GET',
    `/account/api/v1/backups/manifests?lineage=${LINEAGE}&limit=5&before=${SNAPSHOT}&includeDeleted=1`,
    'backups/manifests',
  ],
  [
    'backup retention',
    'GET',
    `/account/api/v1/backups/retention?lineage=${LINEAGE}`,
    'backups/retention',
  ],
  [
    'backup retention (all lineages)',
    'GET',
    '/account/api/v1/backups/retention',
    'backups/retention',
  ],
  [
    'backup retention preview',
    'GET',
    `/account/api/v1/backups/retention/preview?lineage=${LINEAGE}`,
    'backups/retention/preview',
  ],
  [
    'backup undelete',
    'POST',
    `/account/api/v1/backups/snapshots/${SNAPSHOT}/undelete`,
    'backups/snapshots/:snapshot/undelete',
  ],
  [
    'backup immutability show',
    'GET',
    '/account/api/v1/backups/immutability',
    'backups/immutability',
  ],
  ['subscription status report', 'GET', '/account/api/v1/licenses/report', 'licenses/report'],
  [
    'repo delete --purge-backups',
    'DELETE',
    `/account/api/v1/backups/lineages/${LINEAGE}`,
    'backups/lineages/:lineage',
  ],
  [
    'repo delete orphan',
    'POST',
    `/account/api/v1/backups/lineages/${LINEAGE}/orphan`,
    'backups/lineages/:lineage/orphan',
  ],
  [
    'machine deprovision deactivate',
    'POST',
    `/account/api/v1/licenses/machines/${MACHINE}/deactivate`,
    'licenses/machines/:machine/deactivate',
  ],
  [
    'restore size lookup',
    'GET',
    `/account/api/v1/backups/snapshots/resolve?lineage=${LINEAGE}&anchorSnapshotId=${SNAPSHOT}&includeDeleted=1`,
    'backups/snapshots/resolve',
  ],
  ['backup status', 'GET', '/account/api/v1/backups/status', 'backups/status'],
  ['licence activate', 'POST', '/account/api/v1/licenses/activate-repo', 'licenses/activate-repo'],
  [
    'licence activate batch',
    'POST',
    '/account/api/v1/licenses/activate-repo-batch',
    'licenses/activate-repo-batch',
  ],
  [
    'licence retire',
    'POST',
    `/account/api/v1/licenses/repos/${UUID}/retire`,
    'licenses/repos/:uuid/retire',
  ],
];

describe('matchExecutorRoute: every served caller matches its entry', () => {
  it.each(SERVED)('%s', (_label, method, cliPath, inner) => {
    const entry = match(method, cliPath);
    expect(entry?.inner).toBe(inner);
    expect(entry?.method).toBe(method);
  });

  it('every table entry is reached by at least one served caller', () => {
    const reached = new Set(SERVED.map(([, method, , inner]) => `${method} ${inner}`));
    for (const route of EXECUTOR_ACCOUNT_ROUTES) {
      expect(reached.has(`${route.method} ${route.inner}`)).toBe(true);
    }
  });

  it('a leading slash, a lower-case method and URLSearchParams are accepted', () => {
    const entry = matchExecutorRoute(
      'get',
      '/backups/manifests',
      new URLSearchParams({ lineage: LINEAGE, limit: '1' })
    );
    expect(entry?.inner).toBe('backups/manifests');
  });
});

describe('matchExecutorRoute: admitted query sets', () => {
  it.each(
    EXECUTOR_ACCOUNT_ROUTES.filter((route) => route.query.length > 0).map(
      (route) => [route.method, route.inner, route.query] as const
    )
  )('%s %s admits exactly its own names', (method, inner, names) => {
    const all = new URLSearchParams(names.map((name) => [name, '1']));
    expect(matchExecutorRoute(method, inner, all)?.inner).toBe(inner);
    all.append('teamId', 'x');
    expect(matchExecutorRoute(method, inner, all)).toBeUndefined();
  });

  it('a repeated admitted name is refused', () => {
    expect(
      matchExecutorRoute('GET', 'backups/manifests', `lineage=${LINEAGE}&lineage=${LINEAGE}`)
    ).toBeUndefined();
  });

  it('an entry with no query set refuses any query', () => {
    expect(matchExecutorRoute('GET', 'backups/usage', 'lineage=x')).toBeUndefined();
    expect(matchExecutorRoute('POST', `licenses/repos/${UUID}/retire`, 'x=1')).toBeUndefined();
  });

  it('an empty query string is no query', () => {
    expect(matchExecutorRoute('GET', 'backups/usage', '')?.inner).toBe('backups/usage');
    expect(matchExecutorRoute('GET', 'backups/usage', '?')?.inner).toBe('backups/usage');
  });
});

describe('table shape', () => {
  it('no method and path template repeats', () => {
    const keys = EXECUTOR_ACCOUNT_ROUTES.map((route) => `${route.method} ${route.inner}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('only the scope-less reconcile carries a null scope', () => {
    const nullScoped = EXECUTOR_ACCOUNT_ROUTES.filter((route) => route.scope === null);
    expect(nullScoped.map((route) => route.inner)).toEqual(['backups/reconcile']);
  });

  it('every typed segment names a known pattern', () => {
    for (const route of EXECUTOR_ACCOUNT_ROUTES) {
      for (const segment of route.inner.split('/').filter((s) => s.startsWith(':'))) {
        expect(['lineage', 'snapshot', 'machine', 'uuid']).toContain(segment.slice(1));
      }
    }
  });

  it('an executor path sits under the proxy/account mount', () => {
    expect(EXECUTOR_ACCOUNT_PREFIX).toBe('/account/api/v1/proxy/account');
    expect(executorAccountPath('backups/usage')).toBe(
      '/account/api/v1/proxy/account/backups/usage'
    );
    expect(executorAccountPath('/licenses/report')).toBe(
      '/account/api/v1/proxy/account/licenses/report'
    );
  });
});
