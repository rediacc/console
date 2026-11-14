/**
 * The on-premise free tier (PLAN-enterprise-tenants C5, ruling R6).
 *
 * An on-premise account server with no delegation certificate (bootstrap mode)
 * reports `tier: free` on `GET /onprem/cert-status` and serves
 * `POST /onprem/free-license` by asking the upstream public
 * `POST /licenses/free` for the licence on the caller's behalf. The upstream
 * route owns every real bound (per-address window, per-machine cap, one licence
 * per repository GUID, the 3 GB size cap); the numbers below are the server's
 * own early refusal, so a box never spends a request upstream will refuse.
 *
 * The account server's runtime doc carries the design:
 * private/account/docs/runtime/on-premise-licensing.md "Free tier (no certificate)".
 */

import { WK_ACCOUNT_DEFAULT_ORIGIN } from '../config/well-known.generated.js';
import { PLAN_LIMITS } from './constants.js';
import type { PlanCode } from './types.js';

/** The tier `GET /onprem/cert-status` reports: `free` with no cert, else the cert's plan. */
export type OnPremTier = 'free' | PlanCode;

/** The tier value of a server running with no delegation certificate. */
export const ONPREM_FREE_TIER = 'free' as const satisfies OnPremTier;

/**
 * The upstream origin a free-tier server asks when `UPSTREAM_URL` is unset:
 * the default public account server, the same one an unconfigured CLI uses.
 */
export const ONPREM_FREE_TIER_DEFAULT_UPSTREAM = WK_ACCOUNT_DEFAULT_ORIGIN;

/** The upstream path of the public FREE licence route, relative to the origin. */
export const ONPREM_FREE_TIER_UPSTREAM_PATH = '/account/api/v1/licenses/free' as const;

/** The on-premise route that serves the free tier, relative to the account API base. */
export const ONPREM_FREE_TIER_LOCAL_PATH = '/onprem/free-license' as const;

/**
 * The free tier's quotas. Every request from one server reaches upstream from
 * that server's address, so the server's own window mirrors upstream's
 * per-address window: 8 new licences per 72 hours for the whole server.
 */
export const ONPREM_FREE_TIER_LIMITS = {
  /** New free licences this server obtains inside one window. */
  maxNewLicensesPerWindow: 8,
  /** The window length, in hours. */
  windowHours: 72,
  /** Unexpired free licences upstream allows per machine (enforced upstream). */
  maxUnexpiredPerMachine: 3,
  /** Hours a free licence stays valid after issuance or renewal (set upstream). */
  licenceValidityHours: 48,
  /** The repository size cap, read from the FREE plan. */
  maxRepositorySizeGb: PLAN_LIMITS.FREE.maxRepositorySizeGb,
} as const;

/** How long the server waits for upstream before it treats itself as offline, in ms. */
export const ONPREM_FREE_TIER_UPSTREAM_TIMEOUT_MS = 15_000;

/** The refusal codes the server's own free-tier checks answer with. */
export const ONPREM_FREE_TIER_CODES = {
  /** Upstream is unreachable: no free tier offline; install a cert with `--cert`. */
  OFFLINE: 'ONPREM_FREE_TIER_OFFLINE',
  /** The server's own window is full. */
  QUOTA: 'ONPREM_FREE_TIER_QUOTA',
  /** The server holds or held a cert, so it issues licences under that cert instead. */
  NOT_FREE: 'ONPREM_FREE_TIER_NOT_FREE',
  /** Upstream answered with something that is not a licence. */
  UPSTREAM_INVALID: 'ONPREM_FREE_TIER_UPSTREAM_INVALID',
} as const;

export type OnPremFreeTierCode =
  (typeof ONPREM_FREE_TIER_CODES)[keyof typeof ONPREM_FREE_TIER_CODES];

/** The event the server logs per free licence obtained; the window counts these. */
export const ONPREM_FREE_TIER_EVENT_TYPE = 'onprem_free_license_obtained' as const;
