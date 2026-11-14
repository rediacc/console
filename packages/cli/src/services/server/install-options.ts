/** The options and the result of `rdc server install`, and the ordered step names. */

import type { LicenceMode, TlsMethod } from './types.js';

export const INSTALL_STEPS = [
  'preflight',
  'setup',
  'dns',
  'tls',
  'repo',
  'template',
  'keys',
  'bws',
  'licence',
  'settings',
  'image',
  'up',
  'wait',
  'owner',
] as const;
export type InstallStep = (typeof INSTALL_STEPS)[number];

export interface InstallOptions {
  machine?: string;
  ip?: string;
  user?: string;
  port?: string;
  name?: string;
  domain?: string;
  storeDomain?: string;
  repo?: string;
  size?: string;
  owner?: string;
  tls?: TlsMethod;
  cfToken?: string;
  certEmail?: string;
  tlsCert?: string;
  tlsKey?: string;
  tlsCa?: string;
  licence?: LicenceMode;
  cert?: string;
  image?: string;
  imageFile?: string;
  /** `docker save` the `--image` ref from the local Docker and ship it (a locally built image). */
  localImage?: boolean;
  dnsWait?: boolean;
  /** Copy the generated secrets to this Bitwarden Secrets Manager project (Rediacc's own installs). */
  bwsProject?: string;
  /** Replace a differing value in that project instead of refusing. */
  rotate?: boolean;
  yes?: boolean;
  /** `--output json` (or another machine-readable format): the bundle is never printed. */
  machineReadable?: boolean;
}

export interface InstallResult {
  domain: string;
  storeDomain: string;
  machine: string;
  repo: string;
  owner: string;
  tier: string;
  subscriptionId?: string;
  image: string;
  tls: TlsMethod;
}
