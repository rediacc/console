/**
 * The local record of one install, per config and domain:
 * `<state dir>/server/<config>/<domain>.json` holds the non-secret facts (machine, repo, TLS method,
 * which steps are done), so `status`, `upgrade`, `backup` and `licence` find the box by its domain,
 * and a rerun of `install` skips what is done. The owner's first password sits beside it in
 * `<domain>.owner.json` at 0600; no box key is ever written here.
 */

import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { getStateDir } from '@rediacc/shared/paths';
import { getEffectiveConfigName } from '../config/config-name.js';
import type { LicenceMode, TlsMethod } from './types.js';

export interface ServerRecord {
  domain: string;
  storeDomain: string;
  machine: string;
  repo: string;
  owner?: string;
  tls?: TlsMethod;
  /** Path of the private CA the box's certificate chains to (bring-your-own TLS). */
  tlsCa?: string;
  licence?: LicenceMode | 'cert';
  /** The cert's subscription, when the server runs under one. */
  subscriptionId?: string;
  image?: string;
  /** The repo was created by this install, so a rerun may use it. */
  repoCreated?: boolean;
  steps: Record<string, string>;
}

export interface OwnerCredentials {
  email: string;
  password: string;
}

export function serverStateDir(configName = getEffectiveConfigName()): string {
  return join(getStateDir(), 'server', configName);
}

function recordPath(domain: string): string {
  return join(serverStateDir(), `${domain}.json`);
}

function ownerPath(domain: string): string {
  return join(serverStateDir(), `${domain}.owner.json`);
}

function readJson<T>(path: string): T | undefined {
  try {
    return JSON.parse(readFileSync(path, 'utf-8')) as T;
  } catch {
    return undefined;
  }
}

export function loadRecord(domain: string): ServerRecord | undefined {
  return readJson<ServerRecord>(recordPath(domain));
}

export function loadOwner(domain: string): OwnerCredentials | undefined {
  return readJson<OwnerCredentials>(ownerPath(domain));
}

export function ensureStateDir(): void {
  mkdirSync(serverStateDir(), { recursive: true, mode: 0o700 });
}

export function recordFile(domain: string): string {
  return recordPath(domain);
}

export function ownerFile(domain: string): string {
  return ownerPath(domain);
}
