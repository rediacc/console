/**
 * Evidence verification on the workstation (`rdc forensics verify`, PLAN-forensics-investigation
 * D5): the same `verifyWindow` module the browser runs, over a directory that holds the raw
 * chain material under the keys the raw manifest names:
 *
 *   audit/<org>/days/<yyyy-mm-dd>.ndjson.gz
 *   f/<subscription>/<machine>/days/<yyyy-mm-dd>/headers.ndjson.gz
 *   f/<subscription>/<machine>/days/<yyyy-mm-dd>/repo-<guid|machine>[.pii].ndjson.gz
 *
 * Nothing here trusts the files: a batch whose header, signature or sections were changed
 * fails the signature, the section hashes or the chain link, and a day file changed after the
 * next day recorded its hash is an edit at that day. The machine keys come from the
 * `raw-manifest.json` an `rdc incident export` writes beside the files (the keys the server
 * pinned), and a `--machine-key` entry replaces the manifest's key for that machine.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { basename, dirname, join, relative, sep } from 'node:path';
import { gunzipSync } from 'node:zlib';
import {
  type AuditDayInput,
  type BatchInput,
  decodeSignature,
  importSpoolPublicKey,
  MACHINE_SECTION,
  sectionKey,
  type VerificationReport,
  verifyWindow,
} from '@rediacc/shared/forensics';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { VERSION } from '../../version.js';
import type { ForensicsWindow } from './window.js';

const AUDIT_DAY = /^audit\/([^/]+)\/days\/(\d{4}-\d{2}-\d{2})\.ndjson\.gz$/;
const HEADERS = /^f\/[^/]+\/([^/]+)\/days\/(\d{4}-\d{2}-\d{2})\/headers\.ndjson\.gz$/;
const REPO_FILE = /^repo-(.+?)(\.pii)?\.ndjson\.gz$/;
const HEX_KEY = /^[0-9a-f]{64}$/i;
const VERIFIER = 'rdc forensics verify';
/** The manifest file an export writes at the root of the evidence directory. */
export const RAW_MANIFEST_FILE = 'raw-manifest.json';

/** True for a key the verifier reads: an audit day file or a forensics headers file. */
export function isChainKey(key: string): boolean {
  return AUDIT_DAY.test(key) || HEADERS.test(key);
}

/** True when a server-named key stays inside the directory it is written under. */
export function isSafeEvidenceKey(key: string): boolean {
  if (key === '' || key.startsWith('/') || key.includes('\\') || key.includes('\0')) return false;
  return key.split('/').every((part) => part !== '' && part !== '.' && part !== '..');
}

export interface LoadedEvidence {
  org: string;
  window: ForensicsWindow;
  auditDays: AuditDayInput[];
  batches: BatchInput[];
  files: number;
}

function invalid(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

function walk(root: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(root)) {
    const full = join(root, name);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function ndjson(bytes: Uint8Array): unknown[] {
  return new TextDecoder()
    .decode(gunzipSync(bytes))
    .split('\n')
    .filter((line) => line.trim() !== '')
    .map((line) => JSON.parse(line) as unknown);
}

type SectionsBySeq = Map<number, Map<string, Uint8Array>>;

/** Add one repo file's `{seq, section}` lines under `key`. */
function addRepoFile(bySeq: SectionsBySeq, full: string, key: string): void {
  for (const line of ndjson(readFileSync(full))) {
    const entry = line as { seq?: number; section?: string };
    const bytes = typeof entry.section === 'string' ? decodeSignature(entry.section) : null;
    if (typeof entry.seq !== 'number' || bytes === null) continue;
    const sections = bySeq.get(entry.seq) ?? new Map<string, Uint8Array>();
    sections.set(key, bytes);
    bySeq.set(entry.seq, sections);
  }
}

/** The section bytes of one machine-day by (sequence, section key), from its repo files. */
function readSections(files: ReadonlyMap<string, string>, directory: string): SectionsBySeq {
  const bySeq: SectionsBySeq = new Map();
  for (const [rel, full] of files) {
    const match = dirname(rel) === directory ? REPO_FILE.exec(basename(rel)) : null;
    if (!match) continue;
    const guid = match[1] === 'machine' ? MACHINE_SECTION : (match[1] ?? '');
    addRepoFile(bySeq, full, sectionKey(guid, match[2] ? 'pii' : 'records'));
  }
  return bySeq;
}

function readBatches(
  headersFile: string,
  directory: string,
  files: ReadonlyMap<string, string>
): BatchInput[] {
  const sections = readSections(files, directory);
  const lines = ndjson(readFileSync(headersFile)).slice(1);
  const batches: BatchInput[] = [];
  for (const line of lines) {
    const entry = line as { seq?: number; header?: string; signature?: string };
    const headerBytes = typeof entry.header === 'string' ? decodeSignature(entry.header) : null;
    const signature = typeof entry.signature === 'string' ? decodeSignature(entry.signature) : null;
    if (headerBytes === null || signature === null) {
      batches.push({
        headerBytes: new Uint8Array(),
        signature: new Uint8Array(),
        sections: new Map(),
      });
      continue;
    }
    batches.push({
      headerBytes,
      signature,
      sections: sections.get(entry.seq ?? -1) ?? new Map(),
    });
  }
  return batches;
}

const dayOf = (instant: string) => instant.slice(0, 10);
const byDay = (a: { day: string }, b: { day: string }) => (a.day < b.day ? -1 : 1);

interface Classified {
  orgs: Set<string>;
  audit: { day: string; full: string }[];
  headerFiles: { day: string; rel: string; full: string }[];
}

function classify(files: ReadonlyMap<string, string>): Classified {
  const found: Classified = { orgs: new Set(), audit: [], headerFiles: [] };
  for (const [rel, full] of files) {
    const day = AUDIT_DAY.exec(rel);
    if (day?.[1] && day[2]) {
      found.orgs.add(day[1]);
      found.audit.push({ day: day[2], full });
      continue;
    }
    const headers = HEADERS.exec(rel);
    if (headers?.[2]) found.headerFiles.push({ day: headers[2], rel, full });
  }
  return found;
}

/** The audit days inside the window plus the one before it, which the first link compares against. */
function auditWindowDays(audit: Classified['audit'], window: ForensicsWindow) {
  const fromDay = dayOf(window.from);
  const inside = audit.filter((a) => a.day >= fromDay && a.day <= dayOf(window.to));
  const before = audit
    .filter((a) => a.day < fromDay)
    .sort(byDay)
    .at(-1);
  return (before ? [before, ...inside] : inside).sort(byDay);
}

/** Read the evidence directory; audit days are limited to the window plus the day before it. Without a window, every day found is checked. */
export function loadEvidence(
  directory: string,
  requested: ForensicsWindow | undefined
): LoadedEvidence {
  let paths: string[];
  try {
    paths = walk(directory);
  } catch {
    throw invalid(t('forensics.noEvidenceDir', { dir: directory }));
  }
  const files = new Map<string, string>();
  for (const full of paths) files.set(relative(directory, full).split(sep).join('/'), full);

  const { orgs, audit, headerFiles } = classify(files);
  if (orgs.size > 1) throw invalid(t('forensics.severalOrgs', { orgs: [...orgs].join(', ') }));
  if (audit.length === 0 && headerFiles.length === 0) {
    throw invalid(t('forensics.noEvidence', { dir: directory }));
  }

  const days = [...audit, ...headerFiles].sort(byDay);
  const window = requested ?? {
    from: `${days[0]?.day}T00:00:00.000Z`,
    to: `${days.at(-1)?.day}T23:59:59.999Z`,
  };
  const chosen = auditWindowDays(audit, window);
  const inWindowHeaders = headerFiles
    .filter((h) => h.day >= dayOf(window.from) && h.day <= dayOf(window.to))
    .sort((a, b) => (a.rel < b.rel ? -1 : 1));
  return {
    org: [...orgs][0] ?? '',
    window,
    auditDays: chosen.map((a) => ({ day: a.day, bytes: new Uint8Array(readFileSync(a.full)) })),
    batches: inWindowHeaders.flatMap((h) => readBatches(h.full, dirname(h.rel), files)),
    files: chosen.length + inWindowHeaders.length,
  };
}

/** `--machine-key <machine>=<64 hex>` entries as a map from machine id to the raw Ed25519 key. */
export function parseMachineKeys(entries: readonly string[]): Map<string, string> {
  const keys = new Map<string, string>();
  for (const entry of entries) {
    const at = entry.indexOf('=');
    const machine = at > 0 ? entry.slice(0, at) : '';
    const hex = at > 0 ? entry.slice(at + 1) : '';
    if (machine === '' || !HEX_KEY.test(hex))
      throw invalid(t('forensics.badMachineKey', { entry }));
    keys.set(machine, hex.toLowerCase());
  }
  return keys;
}

/** The pinned machine keys of the `raw-manifest.json` in `directory`; empty when there is none. */
export function manifestMachineKeys(directory: string): Map<string, string> {
  const keys = new Map<string, string>();
  const file = join(directory, RAW_MANIFEST_FILE);
  if (!existsSync(file)) return keys;
  let manifest: { machineKeys?: { machineId?: unknown; publicKey?: unknown }[] };
  try {
    manifest = JSON.parse(readFileSync(file, 'utf8')) as typeof manifest;
  } catch {
    throw invalid(t('forensics.badManifest', { file }));
  }
  for (const entry of manifest.machineKeys ?? []) {
    if (typeof entry.machineId !== 'string' || typeof entry.publicKey !== 'string') continue;
    if (HEX_KEY.test(entry.publicKey)) keys.set(entry.machineId, entry.publicKey.toLowerCase());
  }
  return keys;
}

function hexBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** Verify a directory of evidence for the window with the machine keys given. */
export async function verifyEvidenceDir(
  directory: string,
  requested: ForensicsWindow | undefined,
  machineKeys: ReadonlyMap<string, string>
): Promise<VerificationReport & { files: number }> {
  const evidence = loadEvidence(directory, requested);
  const report = await verifyWindow({
    org: evidence.org,
    window: evidence.window,
    auditDays: evidence.auditDays,
    batches: evidence.batches,
    publicKeyFor: (machineId) => {
      const hex = machineKeys.get(machineId);
      return Promise.resolve(hex === undefined ? null : importSpoolPublicKey(hexBytes(hex)));
    },
    verifier: VERIFIER,
    toolVersion: VERSION,
  });
  return { ...report, files: evidence.files };
}
