import { WK_DATASTORE_PATH } from './well-known.generated.js';

/**
 * Network configuration defaults
 */
export const NETWORK_DEFAULTS = {
  /** Default API base URL for development */
  API_URL: 'http://localhost:7322/api',

  /** Default web UI port */
  WEB_PORT: 7322,

  /** Default dev server port (Vite) */
  DEV_PORT: 3000,

  /** Default datastore mount path */
  DATASTORE_PATH: WK_DATASTORE_PATH,

  /** Default datastore size (percentage of available disk) */
  DATASTORE_SIZE: '95%',
} as const;

/**
 * VM network configuration (for OPS/testing)
 */
export const VM_NETWORK = {
  /** Bridge VM IP */
  BRIDGE_IP: '192.168.111.1',

  /** Worker VM IPs */
  WORKER_IPS: ['192.168.111.11', '192.168.111.12'] as const,

  /** Default SSH user for VMs */
  VM_USER: 'muhammed',
} as const;

/**
 * Seed source ranges for an SSH key the hosted executor uses
 * (`rdc config access add --hosted-executor` copies them into the config;
 * nothing reads this constant while resolving a key's ranges).
 *
 * These are OBSERVED Cloudflare egress ranges, not a published list:
 * Cloudflare documents no container egress range, and 104.28.0.0/16 is absent
 * from https://www.cloudflare.com/ips-v4. RDAP owners: 104.28.0.0/16 lies in
 * ARIN CLOUDFLARENET 104.16.0.0/12; 2a09:bac0::/29 is the RIPE parent of the
 * CLOUDFLAREWARP /32 nets. Every executor source seen so far (104.28.x.x,
 * 2a09:bac1:..., 2a09:bac5:...) falls inside them. The ranges are shared
 * Cloudflare egress, so `from=` narrows a key to Cloudflare's network; the key
 * stays the authentication.
 */
export const HOSTED_EXECUTOR_SOURCE_RANGES = {
  ipv4: ['104.28.0.0/16'],
  ipv6: ['2a09:bac0::/29'],
} as const satisfies { ipv4: readonly string[]; ipv6: readonly string[] };
