/**
 * The executor account-route table (PLAN-executor-account-routes Design 1).
 *
 * A command served by `rdc serve --mode container` cannot reach the account
 * server through the sealed E2E tunnel: the proxy egress refuses the tunnel,
 * since its bearer is sealed and it re-dispatches to any route. Each account
 * call a served command makes is listed here instead, once, and the same table
 * is read in three places: the CLI's `accountServerFetch` refuses an unlisted
 * call before sending it, the proxy egress forwards only listed pairs (its own
 * literal copy, held equal to this one by a parity test, since the worker does
 * not import this package at runtime), and the account server's executor
 * router answers 404 for anything unlisted.
 *
 * An entry's `inner` path is relative to `/account/api/v1`, the path the CLI
 * route has today; the executor reaches it at
 * `/account/api/v1/proxy/account/<inner>`. A `:name` segment is typed and
 * matched by the pattern named in `EXECUTOR_SEGMENT_PATTERNS`. `query` is the
 * exact set of parameter names admitted, each at most once; an empty set admits
 * no query at all. `scope` is the API-token scope the CLI route requires, or
 * `null` for `POST backups/reconcile`, whose handler checks `backup:read` (dry
 * run) or `backup:manage` itself.
 */
import type { ApiTokenScope } from './types.js';

/** The account server's API prefix, under which every `inner` path sits. */
export const ACCOUNT_API_PREFIX = '/account/api/v1';

/** The executor mount: an entry's executor path is this prefix, a slash, and its `inner` path. */
export const EXECUTOR_ACCOUNT_PREFIX = `${ACCOUNT_API_PREFIX}/proxy/account`;

/**
 * The typed path segments. Lineage and snapshot ids are the account server's
 * `identifierSchema` (private/account/src/dto/backup.dto.ts). The machine id is
 * what the CLI sends to the deactivate route: `renet machine-id`'s 64 hex
 * characters (packages/cli/src/services/account/license-machine.ts), narrower
 * than the route's own 1-200 characters, so an id of another shape is refused
 * rather than forwarded. The repository GUID of the licence retire is a
 * lower-case UUID.
 */
export const EXECUTOR_SEGMENT_PATTERNS = {
  lineage: /^[A-Za-z0-9-]{1,64}$/,
  snapshot: /^[A-Za-z0-9-]{1,64}$/,
  machine: /^[A-Fa-f0-9]{64}$/,
  uuid: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
} as const;

export type ExecutorSegmentType = keyof typeof EXECUTOR_SEGMENT_PATTERNS;

export type ExecutorRouteMethod = 'GET' | 'POST' | 'DELETE';

export interface ExecutorAccountRoute {
  method: ExecutorRouteMethod;
  /** Path template under `/account/api/v1`, no leading slash; `:lineage`, `:snapshot`, `:machine` and `:uuid` are typed segments. */
  inner: string;
  /** The query parameter names admitted, each at most once; empty admits none. */
  query: readonly string[];
  /** The scope the CLI route requires, or null when the handler checks it itself (reconcile). */
  scope: ApiTokenScope | null;
}

const NONE: readonly string[] = [];

export const EXECUTOR_ACCOUNT_ROUTES: readonly ExecutorAccountRoute[] = [
  { method: 'GET', inner: 'backups/usage', query: NONE, scope: 'backup:read' },
  { method: 'GET', inner: 'backups/status', query: NONE, scope: 'backup:read' },
  {
    method: 'GET',
    inner: 'backups/manifests',
    query: ['lineage', 'limit', 'before', 'includeDeleted'],
    scope: 'backup:read',
  },
  {
    method: 'GET',
    inner: 'backups/snapshots/resolve',
    query: [
      'lineage',
      'anchorSnapshotId',
      'anyStream',
      'storeId',
      'at',
      'needIndex',
      'includeDeleted',
    ],
    scope: 'backup:read',
  },
  { method: 'GET', inner: 'backups/retention', query: ['lineage'], scope: 'backup:read' },
  { method: 'GET', inner: 'backups/retention/preview', query: ['lineage'], scope: 'backup:read' },
  { method: 'GET', inner: 'backups/immutability', query: NONE, scope: 'backup:read' },
  {
    method: 'GET',
    inner: 'backups/stores/lineage/:lineage',
    query: NONE,
    scope: 'backup:read',
  },
  { method: 'POST', inner: 'backups/verify', query: NONE, scope: 'backup:read' },
  {
    method: 'POST',
    inner: 'backups/snapshots/:snapshot/verification',
    query: NONE,
    scope: 'backup:read',
  },
  {
    method: 'POST',
    inner: 'backups/snapshots/:snapshot/undelete',
    query: NONE,
    scope: 'backup:manage',
  },
  { method: 'POST', inner: 'backups/chunks/repair', query: NONE, scope: 'backup:manage' },
  { method: 'POST', inner: 'backups/reconcile', query: NONE, scope: null },
  {
    method: 'POST',
    inner: 'backups/lineages/:lineage/orphan',
    query: NONE,
    scope: 'backup:manage',
  },
  { method: 'DELETE', inner: 'backups/lineages/:lineage', query: NONE, scope: 'backup:manage' },
  { method: 'GET', inner: 'licenses/report', query: NONE, scope: 'license:read' },
  {
    method: 'POST',
    inner: 'licenses/machines/:machine/deactivate',
    query: NONE,
    scope: 'license:activate',
  },
  { method: 'POST', inner: 'licenses/activate-repo', query: NONE, scope: 'license:activate' },
  {
    method: 'POST',
    inner: 'licenses/activate-repo-batch',
    query: NONE,
    scope: 'license:activate',
  },
  { method: 'POST', inner: 'licenses/repos/:uuid/retire', query: NONE, scope: 'license:activate' },
];

/** The executor path of an inner path: `/account/api/v1/proxy/account/<inner>`. */
export function executorAccountPath(inner: string): string {
  return `${EXECUTOR_ACCOUNT_PREFIX}/${inner.replace(/^\//, '')}`;
}

function segmentMatches(template: string, actual: string): boolean {
  if (!template.startsWith(':')) return template === actual;
  const type = template.slice(1);
  if (!Object.hasOwn(EXECUTOR_SEGMENT_PATTERNS, type)) return false;
  return EXECUTOR_SEGMENT_PATTERNS[type as ExecutorSegmentType].test(actual);
}

function pathMatches(template: string, path: string): boolean {
  const want = template.split('/');
  const got = path.split('/');
  if (want.length !== got.length) return false;
  return want.every((segment, index) => segmentMatches(segment, got[index] ?? ''));
}

/** Every query name is in the admitted set and none repeats. */
function queryAdmitted(admitted: readonly string[], params: URLSearchParams): boolean {
  const seen = new Set<string>();
  for (const name of params.keys()) {
    if (!admitted.includes(name) || seen.has(name)) return false;
    seen.add(name);
  }
  return true;
}

/**
 * The table entry a call matches, or undefined. `path` is the inner path,
 * relative to `/account/api/v1` (one leading slash is tolerated), with no query
 * string and no trailing slash; `searchParams` is the call's query. A path that
 * carries `?`, an empty segment, a segment outside its pattern, a query name
 * outside the entry's set or a repeated name matches nothing.
 */
export function matchExecutorRoute(
  method: string,
  path: string,
  searchParams?: URLSearchParams | string
): ExecutorAccountRoute | undefined {
  const inner = path.startsWith('/') ? path.slice(1) : path;
  if (inner.includes('?') || inner.includes('#')) return undefined;
  const params =
    searchParams instanceof URLSearchParams
      ? searchParams
      : new URLSearchParams(searchParams ?? '');
  const verb = method.toUpperCase();
  return EXECUTOR_ACCOUNT_ROUTES.find(
    (route) =>
      route.method === verb && pathMatches(route.inner, inner) && queryAdmitted(route.query, params)
  );
}
