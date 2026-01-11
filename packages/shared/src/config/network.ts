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
  DATASTORE_PATH: '/mnt/rediacc',
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
