/**
 * The tunables registry, `.ci/config/settings.json`, read and checked
 * (agent/plans/PLAN-settings-set-verb.md Design 2).
 *
 * Loading validates the SHAPE (unique ids, a known unit, min <= max, at least one copy, a
 * well-formed copy and reason path); `inspect` resolves every copy against the tree and says
 * whether they agree and sit in range. Neither writes.
 */
import fs from 'node:fs';
import path from 'node:path';
import { type Copy, CopyError, copyLabel, type ReasonPath, readCopy } from './copies.js';
import { UNITS, type Unit } from './units.js';

export const REGISTRY_REL = '.ci/config/settings.json';

export interface SettingEntry {
  id: string;
  unit: Unit;
  min: number;
  max: number;
  why: string;
  copies: Copy[];
  reason_paths: ReasonPath[];
  tests: { gates: string[]; pytest: string[] };
}

export class RegistryError extends Error {}

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === 'string' && v !== '';
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const strs = (v: unknown): v is string[] => Array.isArray(v) && v.every(isStr);

function checkCopy(id: string, c: unknown, i: number): Copy {
  const at = `${id} copies[${i}]`;
  if (!isObj(c) || !isStr(c.file)) throw new RegistryError(`${at}: needs a file`);
  if (isStr(c.json_path) && c.py_dict === undefined)
    return { file: c.file, json_path: c.json_path };
  if (isStr(c.py_dict) && isStr(c.py_key) && c.json_path === undefined)
    return { file: c.file, py_dict: c.py_dict, py_key: c.py_key };
  throw new RegistryError(`${at}: needs exactly one of json_path, or py_dict with py_key`);
}

function checkReason(id: string, r: unknown, i: number): ReasonPath {
  const at = `${id} reason_paths[${i}]`;
  if (!isObj(r) || !isStr(r.file) || !isStr(r.json_path))
    throw new RegistryError(`${at}: needs a file and a json_path`);
  if (r.mode !== 'replace' && r.mode !== 'segment')
    throw new RegistryError(`${at}: mode is replace or segment`);
  if (r.mode === 'segment' && !isStr(r.key))
    throw new RegistryError(`${at}: a segment needs a key`);
  if (r.prefix !== undefined && typeof r.prefix !== 'string')
    throw new RegistryError(`${at}: prefix is a string`);
  return {
    file: r.file,
    json_path: r.json_path,
    mode: r.mode,
    ...(typeof r.prefix === 'string' ? { prefix: r.prefix } : {}),
    ...(isStr(r.key) ? { key: r.key } : {}),
  };
}

/** Validate a parsed registry document; throws RegistryError naming the first bad entry. */
export function parseRegistry(doc: unknown): SettingEntry[] {
  if (!isObj(doc) || !Array.isArray(doc.settings))
    throw new RegistryError(`${REGISTRY_REL}: needs a settings array`);
  const seen = new Set<string>();
  return doc.settings.map((e: unknown, n: number) => {
    if (!isObj(e) || !isStr(e.id)) throw new RegistryError(`settings[${n}]: needs an id`);
    const id = e.id;
    if (seen.has(id)) throw new RegistryError(`${id}: registered twice`);
    seen.add(id);
    if (!UNITS.includes(e.unit as Unit))
      throw new RegistryError(
        `${id}: unit ${JSON.stringify(e.unit)} is not one of ${UNITS.join(', ')}`
      );
    if (!isNum(e.min) || !isNum(e.max) || e.min > e.max)
      throw new RegistryError(`${id}: needs numeric min <= max`);
    if (!isStr(e.why)) throw new RegistryError(`${id}: needs a why`);
    if (!Array.isArray(e.copies) || e.copies.length === 0)
      throw new RegistryError(`${id}: needs at least one copy`);
    const reasons = e.reason_paths ?? [];
    if (!Array.isArray(reasons)) throw new RegistryError(`${id}: reason_paths is an array`);
    const t = e.tests;
    if (!isObj(t) || !strs(t.gates ?? []) || !strs(t.pytest ?? []))
      throw new RegistryError(`${id}: tests is {gates: [...], pytest: [...]}`);
    return {
      id,
      unit: e.unit as Unit,
      min: e.min,
      max: e.max,
      why: e.why,
      copies: e.copies.map((c, i) => checkCopy(id, c, i)),
      reason_paths: reasons.map((r, i) => checkReason(id, r, i)),
      tests: {
        gates: strs(t.gates) ? t.gates : [],
        pytest: strs(t.pytest) ? t.pytest : [],
      },
    };
  });
}

export function loadRegistry(root: string): SettingEntry[] {
  const file = path.join(root, REGISTRY_REL);
  let doc: unknown;
  try {
    doc = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (err) {
    throw new RegistryError(`${REGISTRY_REL}: ${(err as Error).message}`);
  }
  return parseRegistry(doc);
}

export interface CopyState {
  label: string;
  file: string;
  line: number | null;
  value: unknown;
  error: string | null;
}

export interface EntryState {
  entry: SettingEntry;
  copies: CopyState[];
  /** Every copy resolved to the same number. */
  agree: boolean;
  /** The source copy's value when it resolved to a number. */
  value: number | null;
  inRange: boolean;
  problems: string[];
}

/** Resolve every copy of an entry against the tree at `root`, reading through `read` (the planned overlay in `set`). */
export function inspect(
  root: string,
  e: SettingEntry,
  read: (rel: string) => string | null = (rel) => {
    const abs = path.join(root, rel);
    return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
  }
): EntryState {
  const copies: CopyState[] = e.copies.map((c) => {
    const text = read(c.file);
    if (text === null)
      return { label: copyLabel(c), file: c.file, line: null, value: null, error: 'file missing' };
    try {
      const v = readCopy(text, c);
      return { label: copyLabel(c), file: c.file, line: v.line, value: v.value, error: null };
    } catch (err) {
      if (!(err instanceof CopyError)) throw err;
      return { label: copyLabel(c), file: c.file, line: null, value: null, error: err.message };
    }
  });
  const problems: string[] = [];
  for (const c of copies) {
    if (c.error) problems.push(`${c.label}: ${c.error}`);
    else if (typeof c.value !== 'number') problems.push(`${c.label}: not a number`);
  }
  const nums = copies.map((c) => c.value).filter((v): v is number => typeof v === 'number');
  const agree = problems.length === 0 && nums.every((n) => n === nums[0]);
  if (problems.length === 0 && !agree)
    problems.push(
      `copies disagree: ${copies.map((c) => `${c.label}=${String(c.value)}`).join(', ')}`
    );
  const value = typeof copies[0].value === 'number' ? copies[0].value : null;
  const inRange = value !== null && value >= e.min && value <= e.max;
  if (value !== null && !inRange) problems.push(`${value} is outside [${e.min}, ${e.max}]`);
  return { entry: e, copies, agree, value, inRange, problems };
}
