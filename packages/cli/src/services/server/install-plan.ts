/** The resolved install values and the two name helpers `ServerInstall` derives them with. */

import type { MachineConfig } from '../../types/index.js';
import { LOGIN_EMAIL_ENV } from '../account/subscription-password-auth.js';
import type { LicenceMode, TlsMethod } from './types.js';

/** The resolved values, every one known before the first step runs. */
export interface Plan {
  machine: string;
  machineConfig: MachineConfig;
  domain: string;
  storeDomain: string;
  repo: string;
  size: string;
  owner: string;
  tls: TlsMethod;
  licence: LicenceMode;
  image: string;
}

export function loggedInEmail(): string | undefined {
  return process.env[LOGIN_EMAIL_ENV]?.trim() || undefined;
}

export function defaultMachineName(ip: string): string {
  return `server-${ip
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`;
}
