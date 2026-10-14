/**
 * Controls for the transaction journal and lock (txn.ts), over temporary roots; nothing here
 * touches the tracked tree.
 *
 *   npx tsx scripts/lib/pins/txn-selftest.ts
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { type ControlCase, runControls } from '../controls.js';
import { journalRoot, openJournals, RestoreRefused, restoreJournal, takeLock } from './txn.js';

const tmpRoot = (): string => fs.mkdtempSync(path.join(os.tmpdir(), 'txn-selftest-'));

const writingJournal = (stamp: string): string =>
  `${JSON.stringify({ stamp, state: 'writing', pins: [], files: {} })}\n`;

/** With hard links refused, the lock still appears whole: nothing writes the lock path in place (an in-place create leaves it empty for a moment, which a second taker reads as debris), and a second taker is refused. */
function noHardLinkLock(): ControlCase {
  const root = tmpRoot();
  const lock = path.join(journalRoot(root), '.lock');
  const realLink = fs.linkSync;
  const realWrite = fs.writeFileSync;
  const inPlace: string[] = [];
  fs.linkSync = (): void => {
    throw Object.assign(new Error('operation not permitted'), { code: 'EPERM' });
  };
  fs.writeFileSync = ((p: fs.PathOrFileDescriptor, ...rest: unknown[]) => {
    if (p === lock) inPlace.push(String(p));
    return (realWrite as (...a: unknown[]) => void)(p, ...rest);
  }) as typeof fs.writeFileSync;
  let first: (() => void) | null = null;
  let second: (() => void) | null = null;
  let threw = '';
  try {
    first = takeLock(root);
    second = takeLock(root);
  } catch (err) {
    threw = (err as Error).message;
  } finally {
    fs.linkSync = realLink;
    fs.writeFileSync = realWrite;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  const claimLeft = fs.existsSync(`${lock}.claim`);
  first?.();
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: without hard links the lock appears whole by rename, a second taker is refused, and no claim is left',
    ok:
      first !== null &&
      second === null &&
      held === `${process.pid}\n` &&
      inPlace.length === 0 &&
      !claimLeft,
    detail: `first=${first !== null} second=${second !== null} lock=${JSON.stringify(held)} inPlaceWrites=${inPlace.length} claim=${claimLeft} threw=${threw}`,
  };
}

/** An unfinished journal reached through a symlinked stamp directory is still listed. */
function symlinkedStamp(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  fs.mkdirSync(path.join(jr, 'real'), { recursive: true });
  fs.writeFileSync(path.join(jr, 'real', 'journal.json'), writingJournal('real'));
  fs.symlinkSync(path.join(jr, 'real'), path.join(jr, 'linked'));
  fs.symlinkSync(path.join(jr, 'gone'), path.join(jr, 'dangling'));
  fs.writeFileSync(path.join(jr, '.lock'), '');
  fs.mkdirSync(path.join(jr, '.lock.claim'));
  const stamps = openJournals(root).map((j) => j.stamp);
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'journals: a symlinked stamp directory is listed, a dangling link, the lock and its claim are not',
    ok: stamps.join() === 'linked,real',
    detail: `stamps=${stamps.join()}`,
  };
}

/** A replay is refused while a live run holds the lock, and the journal is left in 'writing'. */
function liveRunRefusesReplay(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  fs.mkdirSync(path.join(jr, 's1'), { recursive: true });
  fs.writeFileSync(path.join(jr, 's1', 'journal.json'), writingJournal('s1'));
  fs.writeFileSync(path.join(jr, '.lock'), `${process.ppid}\n`);
  let refused = false;
  try {
    restoreJournal(root, 's1');
  } catch (err) {
    refused = err instanceof RestoreRefused && err.message.includes('a live run');
  }
  const state = JSON.parse(fs.readFileSync(path.join(jr, 's1', 'journal.json'), 'utf8')).state;
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'restore: a stamp is refused while a live run holds the lock, and stays writing',
    ok: refused && state === 'writing',
    detail: `refused=${refused} state=${state}`,
  };
}

export function txnCases(): ControlCase[] {
  return [noHardLinkLock(), symlinkedStamp(), liveRunRefusesReplay()];
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  process.exit(runControls(txnCases()) === 0 ? 0 : 1);
