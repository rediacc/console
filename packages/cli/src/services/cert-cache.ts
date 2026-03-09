/**
 * ACME Certificate Cache Service
 *
 * Manages caching of Traefik's acme.json in the CLI config file.
 * Supports compression (gzip + base64), chunking for size-limited backends,
 * pruning of stale network-ID-based certs, and certificate expiry tracking.
 *
 * Merge strategy: when both local cache and remote have certs for the same
 * domain, the cert with the longer expiry wins. This prevents re-requesting
 * certs that are already cached and avoids overwriting newer renewals.
 */

import { X509Certificate } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';
import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { t } from '../i18n/index.js';
import type { AcmeCertCache } from '../types/index.js';
import { configService } from './config-resources.js';
import { outputService } from './output.js';
import { readSSHKey } from './renet-execution.js';

/** Remote path to Traefik's acme.json. */
const ACME_JSON_PATH = '/opt/rediacc/proxy/letsencrypt/acme.json';

/** Chunk size for base64 data (48KB). Keeps each chunk under Bitwarden/Vault limits. */
const CHUNK_SIZE = 48 * 1024;

/** Regex matching old network-ID-based auto-route domains (e.g., plausible-db-3200.rediacc.io). */
const STALE_CERT_PATTERN = /^.+-\d{4,5}\./;

// ============================================================================
// Traefik acme.json types
// ============================================================================

interface AcmeCertEntry {
  domain: { main: string; sans?: string[] };
  certificate: string;
  key: string;
  Store?: string;
}

interface AcmeResolver {
  Account?: {
    Email: string;
    Registration?: { uri: string };
    PrivateKey?: string;
  };
  Certificates?: AcmeCertEntry[];
}

type AcmeJson = Record<string, AcmeResolver>;

// ============================================================================
// Compression & Chunking
// ============================================================================

/**
 * Compress raw data with gzip and encode as base64.
 * Chunks into 48KB pieces if the result exceeds CHUNK_SIZE.
 */
export function compressAndChunk(raw: Buffer): { data: string | string[]; rawSize: number } {
  const compressed = gzipSync(raw, { level: 9 });
  const b64 = compressed.toString('base64');

  if (b64.length <= CHUNK_SIZE) {
    return { data: b64, rawSize: raw.length };
  }

  // Split into chunks
  const chunks: string[] = [];
  for (let i = 0; i < b64.length; i += CHUNK_SIZE) {
    chunks.push(b64.slice(i, i + CHUNK_SIZE));
  }
  return { data: chunks, rawSize: raw.length };
}

/**
 * Reassemble chunks and decompress gzipped base64 data.
 */
export function decompressFromCache(cache: AcmeCertCache): Buffer {
  const b64 = Array.isArray(cache.data) ? cache.data.join('') : cache.data;
  const compressed = Buffer.from(b64, 'base64');
  return gunzipSync(compressed);
}

/**
 * Format byte count as human-readable string.
 */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(0)}KB`;
  return `${(kb / 1024).toFixed(1)}MB`;
}

// ============================================================================
// Certificate Parsing
// ============================================================================

/**
 * Parse X.509 certificate PEM to extract expiry date.
 * Returns ISO 8601 string or undefined if parsing fails.
 */
function parseCertExpiry(certPem: string): string | undefined {
  try {
    // acme.json stores certs as base64-encoded PEM
    const pem = Buffer.from(certPem, 'base64').toString('utf8');
    const x509 = new X509Certificate(pem);
    return new Date(x509.validTo).toISOString();
  } catch {
    return undefined;
  }
}

/**
 * Build a certificate inventory: domain → expiry date.
 */
function buildCertInventory(acme: AcmeJson): Record<string, string> {
  const inventory: Record<string, string> = {};
  for (const resolver of Object.values(acme)) {
    for (const cert of resolver.Certificates ?? []) {
      const expiry = parseCertExpiry(cert.certificate);
      if (expiry) {
        inventory[cert.domain.main] = expiry;
      }
    }
  }
  return inventory;
}

// ============================================================================
// Merging
// ============================================================================

/**
 * Merge two acme.json objects, keeping the cert with the longer expiry for each domain.
 * Account data is taken from `primary` (the actively-used side).
 * Returns the merged acme.json and count of certs taken from `secondary`.
 */
/**
 * Build a domain → { cert, expiry } map from a resolver's certificates.
 */
function buildCertMap(
  certs: AcmeCertEntry[]
): Map<string, { cert: AcmeCertEntry; expiry: string }> {
  const map = new Map<string, { cert: AcmeCertEntry; expiry: string }>();
  for (const cert of certs) {
    const expiry = parseCertExpiry(cert.certificate) ?? '';
    map.set(cert.domain.main, { cert, expiry });
  }
  return map;
}

/**
 * Merge secondary certs into a primary resolver, returning count of merged certs.
 */
function mergeResolverCerts(
  primaryResolver: AcmeResolver,
  secondaryCerts: AcmeCertEntry[]
): number {
  const primaryCerts = primaryResolver.Certificates!;
  const primaryMap = buildCertMap(primaryCerts);
  let merged = 0;

  for (const sCert of secondaryCerts) {
    const sExpiry = parseCertExpiry(sCert.certificate) ?? '';
    const existing = primaryMap.get(sCert.domain.main);

    if (!existing) {
      primaryCerts.push(sCert);
      primaryMap.set(sCert.domain.main, { cert: sCert, expiry: sExpiry });
      merged++;
    } else if (sExpiry > existing.expiry) {
      const idx = primaryCerts.indexOf(existing.cert);
      if (idx !== -1) {
        primaryCerts[idx] = sCert;
        primaryMap.set(sCert.domain.main, { cert: sCert, expiry: sExpiry });
        merged++;
      }
    }
  }
  return merged;
}

export function mergeAcmeJson(
  primary: AcmeJson,
  secondary: AcmeJson
): { merged: AcmeJson; mergedFromSecondary: number } {
  let mergedFromSecondary = 0;

  for (const [resolverName, secondaryResolver] of Object.entries(secondary)) {
    if (!secondaryResolver.Certificates?.length) continue;

    if (!(resolverName in primary)) {
      primary[resolverName] = { Certificates: [] };
    }
    primary[resolverName].Certificates ??= [];

    mergedFromSecondary += mergeResolverCerts(
      primary[resolverName],
      secondaryResolver.Certificates
    );
  }

  return { merged: primary, mergedFromSecondary };
}

// ============================================================================
// Pruning
// ============================================================================

/**
 * Remove stale network-ID-based certificates from acme.json.
 * Matches domains like `plausible-db-3200.rediacc.io` (old auto-route format).
 * Returns the cleaned JSON and count of removed certs.
 */
export function pruneStaleAcmeCerts(acme: AcmeJson): { cleaned: AcmeJson; removedCount: number } {
  let removedCount = 0;

  for (const resolver of Object.values(acme)) {
    if (!resolver.Certificates) continue;

    const kept: AcmeCertEntry[] = [];
    for (const cert of resolver.Certificates) {
      if (STALE_CERT_PATTERN.test(cert.domain.main)) {
        removedCount++;
      } else {
        kept.push(cert);
      }
    }
    resolver.Certificates = kept;
  }

  return { cleaned: acme, removedCount };
}

// ============================================================================
// SSH Operations
// ============================================================================

/**
 * Create an SFTP connection to a machine.
 */
async function connectToMachine(
  machineName: string
): Promise<{ sftp: SFTPClient; baseDomain?: string }> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  return { sftp, baseDomain: machine.infra?.baseDomain };
}

/**
 * Download acme.json from a remote machine via SSH.
 */
async function readRemoteAcmeJson(sftp: SFTPClient): Promise<string | null> {
  try {
    const output = await sftp.exec(`sudo cat ${ACME_JSON_PATH}`);
    return output.trim() ? output : null;
  } catch {
    return null;
  }
}

/**
 * Upload acme.json to a remote machine via SSH.
 * Writes via stdin to sudo sh to handle root-owned file permissions.
 */
async function writeRemoteAcmeJson(sftp: SFTPClient, content: string): Promise<void> {
  const cmd = `sudo sh -c 'mkdir -p $(dirname ${ACME_JSON_PATH}) && cat > ${ACME_JSON_PATH} && chmod 600 ${ACME_JSON_PATH}'`;
  const exitCode = await sftp.execStreaming(cmd, { stdin: content });
  if (exitCode !== 0) {
    throw new Error(`Failed to write acme.json (exit code ${exitCode})`);
  }
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Build an AcmeCertCache entry from an AcmeJson object.
 */
function buildCacheEntry(
  acme: AcmeJson,
  baseDomain: string,
  machineName: string
): { entry: AcmeCertCache; compressedSize: number } {
  const certs = buildCertInventory(acme);
  const certCount = Object.keys(certs).length;
  const jsonStr = JSON.stringify(acme);
  const { data, rawSize } = compressAndChunk(Buffer.from(jsonStr, 'utf8'));

  const compressedSize = Array.isArray(data)
    ? data.reduce((sum, chunk) => sum + chunk.length, 0)
    : data.length;

  return {
    entry: {
      baseDomain,
      updatedAt: new Date().toISOString(),
      sourceMachine: machineName,
      certCount,
      certs,
      data,
      rawSize,
    },
    compressedSize,
  };
}

// ============================================================================
// Public API
// ============================================================================

export interface DownloadCertCacheOptions {
  /** Suppress non-error output */
  silent?: boolean;
  /** Enable debug output */
  debug?: boolean;
  /** Skip pruning stale certs */
  noPrune?: boolean;
}

/**
 * Download acme.json from a remote machine, merge with local cache
 * (keeping certs with longer expiry), prune stale certs, and store in config.
 */
/**
 * Merge remote acme.json with existing local cache, preserving certs with longer expiry.
 */
async function mergeWithLocalCache(
  remoteAcme: AcmeJson,
  baseDomain: string,
  silent?: boolean
): Promise<void> {
  const currentConfig = await configService.getCurrent();
  const existingCache = currentConfig?.acmeCertCache?.[baseDomain];
  if (!existingCache) return;

  try {
    const localAcme: AcmeJson = JSON.parse(decompressFromCache(existingCache).toString('utf8'));
    const { mergedFromSecondary } = mergeAcmeJson(remoteAcme, localAcme);
    if (mergedFromSecondary > 0 && !silent) {
      outputService.info(
        t('commands.config.certCache.pull.merged', { count: mergedFromSecondary })
      );
    }
  } catch {
    // Local cache corrupted — just use remote
  }
}

/**
 * Parse raw acme.json string and optionally prune stale certs.
 */
function pruneAndParse(raw: string, options: DownloadCertCacheOptions): AcmeJson {
  let acme: AcmeJson = JSON.parse(raw);
  if (!options.noPrune) {
    const { cleaned, removedCount } = pruneStaleAcmeCerts(acme);
    acme = cleaned;
    if (removedCount > 0 && !options.silent) {
      outputService.info(t('commands.config.certCache.pull.pruned', { count: removedCount }));
    }
  }
  return acme;
}

export async function downloadCertCache(
  machineName: string,
  options: DownloadCertCacheOptions = {}
): Promise<{ certCount: number; compressedSize: number } | null> {
  const { sftp, baseDomain } = await connectToMachine(machineName);

  try {
    if (!baseDomain) {
      if (!options.silent) outputService.warn(t('commands.config.certCache.noBaseDomain'));
      return null;
    }

    if (!options.silent) {
      outputService.info(t('commands.config.certCache.pull.downloading', { machine: machineName }));
    }

    const raw = await readRemoteAcmeJson(sftp);
    if (!raw) {
      if (!options.silent)
        outputService.warn(
          t('commands.config.certCache.pull.noAcmeJson', { machine: machineName })
        );
      return null;
    }

    const remoteAcme = pruneAndParse(raw, options);
    await mergeWithLocalCache(remoteAcme, baseDomain, options.silent);

    const currentConfig = await configService.getCurrent();
    const acmeCertCache = currentConfig?.acmeCertCache ?? {};
    const { entry, compressedSize } = buildCacheEntry(remoteAcme, baseDomain, machineName);
    acmeCertCache[baseDomain] = entry;
    await configService.updateConfigFields({ acmeCertCache });

    if (!options.silent) {
      outputService.success(
        t('commands.config.certCache.pull.cached', {
          count: entry.certCount,
          size: formatSize(compressedSize),
        })
      );
    }

    return { certCount: entry.certCount, compressedSize };
  } finally {
    sftp.close();
  }
}

export interface UploadCertCacheOptions {
  /** Enable debug output */
  debug?: boolean;
}

/**
 * Upload cached acme.json to a remote machine, merging with existing remote certs.
 * Remote is primary (its Account data is preserved); local cache provides certs
 * with longer expiry that the remote may be missing.
 * Uses an existing SFTP connection (for integration with push-infra).
 */
export async function uploadCertCacheViaConnection(
  sftp: SFTPClient,
  baseDomain: string,
  options: UploadCertCacheOptions = {}
): Promise<boolean> {
  const currentConfig = await configService.getCurrent();
  const cache = currentConfig?.acmeCertCache?.[baseDomain];
  if (!cache) {
    if (options.debug)
      outputService.info(t('commands.config.certCache.noCacheForDomain', { domain: baseDomain }));
    return false;
  }

  const localAcme: AcmeJson = JSON.parse(decompressFromCache(cache).toString('utf8'));
  const remoteRaw = await readRemoteAcmeJson(sftp);

  if (!remoteRaw) {
    await writeRemoteAcmeJson(sftp, JSON.stringify(localAcme));
    return true;
  }

  const remoteAcme: AcmeJson = JSON.parse(remoteRaw);
  const { merged, mergedFromSecondary } = mergeAcmeJson(remoteAcme, localAcme);
  if (mergedFromSecondary === 0) {
    if (options.debug)
      outputService.info(t('commands.config.certCache.push.upToDate', { machine: 'remote' }));
    return false;
  }

  await writeRemoteAcmeJson(sftp, JSON.stringify(merged));
  return true;
}

/**
 * Upload cached acme.json to a named machine (standalone command).
 */
export async function uploadCertCache(
  machineName: string,
  _options: UploadCertCacheOptions = {}
): Promise<boolean> {
  const { sftp, baseDomain } = await connectToMachine(machineName);

  try {
    if (!baseDomain) {
      outputService.warn(t('commands.config.certCache.noBaseDomain'));
      return false;
    }

    const currentConfig = await configService.getCurrent();
    const cache = currentConfig?.acmeCertCache?.[baseDomain];
    if (!cache) {
      outputService.warn(t('commands.config.certCache.push.noCache'));
      return false;
    }

    outputService.info(t('commands.config.certCache.push.uploading', { machine: machineName }));

    const localAcme: AcmeJson = JSON.parse(decompressFromCache(cache).toString('utf8'));

    // Read remote for merge
    const remoteRaw = await readRemoteAcmeJson(sftp);
    let result: AcmeJson;
    let finalCount: number;

    if (remoteRaw) {
      const remoteAcme: AcmeJson = JSON.parse(remoteRaw);
      const { merged, mergedFromSecondary } = mergeAcmeJson(remoteAcme, localAcme);
      result = merged;
      finalCount = Object.keys(buildCertInventory(merged)).length;
      if (mergedFromSecondary > 0) {
        outputService.info(
          t('commands.config.certCache.push.merged', {
            count: mergedFromSecondary,
            machine: machineName,
          })
        );
      } else {
        outputService.info(t('commands.config.certCache.push.upToDate', { machine: machineName }));
        return false;
      }
    } else {
      result = localAcme;
      finalCount = cache.certCount;
    }

    await writeRemoteAcmeJson(sftp, JSON.stringify(result));

    outputService.success(
      t('commands.config.certCache.push.uploaded', {
        count: finalCount,
        machine: machineName,
      })
    );
    return true;
  } finally {
    sftp.close();
  }
}

/**
 * Get certificate cache status for display.
 */
export async function getCertStatus(): Promise<
  {
    baseDomain: string;
    updatedAt: string;
    sourceMachine: string;
    certCount: number;
    compressedSize: string;
    rawSize: string;
    certs: Record<string, string>;
  }[]
> {
  const currentConfig = await configService.getCurrent();
  const cacheMap = currentConfig?.acmeCertCache;
  if (!cacheMap) return [];

  return Object.values(cacheMap).map((cache) => {
    const compressedBytes = Array.isArray(cache.data)
      ? cache.data.reduce((sum, chunk) => sum + chunk.length, 0)
      : cache.data.length;

    return {
      baseDomain: cache.baseDomain,
      updatedAt: cache.updatedAt,
      sourceMachine: cache.sourceMachine,
      certCount: cache.certCount,
      compressedSize: formatSize(compressedBytes),
      rawSize: formatSize(cache.rawSize),
      certs: cache.certs,
    };
  });
}

/**
 * Clear certificate cache from config.
 */
export async function clearCertCache(baseDomain?: string): Promise<boolean> {
  const currentConfig = await configService.getCurrent();
  const cacheMap = currentConfig?.acmeCertCache;
  if (!cacheMap || Object.keys(cacheMap).length === 0) return false;

  if (baseDomain) {
    if (!(baseDomain in cacheMap)) return false;
    delete cacheMap[baseDomain];
    await configService.updateConfigFields({
      acmeCertCache: Object.keys(cacheMap).length > 0 ? cacheMap : undefined,
    });
  } else {
    await configService.updateConfigFields({ acmeCertCache: undefined });
  }
  return true;
}
