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
import {
  journalRoot,
  liveLockPid,
  openJournals,
  RestoreRefused,
  restoreJournal,
  takeLock,
} from './txn.js';

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

/** Runs `body` with hard links refused (EPERM) and one-shot hooks on fs calls, restoring fs after. */
function withFs<T>(
  hooks: {
    rmSync?: (p: fs.PathLike) => void;
    existsSync?: (p: fs.PathLike) => void;
    renameSync?: (from: fs.PathLike, to: fs.PathLike) => void;
  },
  body: () => T
): T {
  const realLink = fs.linkSync;
  const realRm = fs.rmSync;
  const realExists = fs.existsSync;
  const realRename = fs.renameSync;
  fs.linkSync = (): void => {
    throw Object.assign(new Error('operation not permitted'), { code: 'EPERM' });
  };
  fs.rmSync = ((p: fs.PathLike, o?: fs.RmOptions) => {
    hooks.rmSync?.(p);
    return realRm(p, o);
  }) as typeof fs.rmSync;
  fs.existsSync = ((p: fs.PathLike) => {
    const r = realExists(p);
    hooks.existsSync?.(p);
    return r;
  }) as typeof fs.existsSync;
  fs.renameSync = ((from: fs.PathLike, to: fs.PathLike) => {
    realRename(from, to);
    hooks.renameSync?.(from, to);
  }) as typeof fs.renameSync;
  try {
    return body();
  } finally {
    fs.renameSync = realRename;
    fs.linkSync = realLink;
    fs.rmSync = realRm;
    fs.existsSync = realExists;
  }
}

/** Sets a path's times a minute into the past, older than any age threshold a claim could be judged by. */
const ageMinute = (p: string): void => {
  const t = new Date(Date.now() - 60_000);
  fs.utimesSync(p, t, t);
};

/** Two takers judge the same dead claim; one clears it and takes the lock, then a third installs a live claim before the first acts on its old verdict. The first must neither remove nor move that live claim (a move put back later still leaves the slot empty for a moment), and only one taker holds the lock. */
function staleClaimTwoTakers(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  fs.mkdirSync(claim, { recursive: true });
  fs.writeFileSync(path.join(claim, 'owner'), '999999999 - dead0\n');
  ageMinute(claim);
  const live = `${process.ppid} - feed1`;
  let peer: (() => void) | null = null;
  let peerRan = false;
  const runPeer = (): void => {
    if (peerRan) return;
    peerRan = true;
    peer = takeLock(root, { claimWaitMs: 0 });
    // A third taker, live and inside its claim right now.
    fs.mkdirSync(claim);
    fs.writeFileSync(path.join(claim, 'owner'), `${live}\n`);
  };
  let movedLive = false;
  const watchMove = (from: fs.PathLike, to: fs.PathLike): void => {
    const moved = path.join(String(to), 'owner');
    if (from === claim && fs.existsSync(moved) && fs.readFileSync(moved, 'utf8').trim() === live)
      movedLive = true;
  };
  let first: (() => void) | null = null;
  let threw = '';
  try {
    first = withFs({ rmSync: (p) => p === claim && runPeer(), renameSync: watchMove }, () =>
      takeLock(root, { afterClaimVerdict: runPeer, claimWaitMs: 0 })
    );
  } catch (err) {
    threw = (err as Error).message;
  }
  const claimOwner = fs.existsSync(path.join(claim, 'owner'))
    ? fs.readFileSync(path.join(claim, 'owner'), 'utf8').trim()
    : '<absent>';
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a taker acting late on a dead claim leaves the live claim installed since in place, and only one taker holds the lock',
    ok:
      peerRan &&
      peer !== null &&
      first === null &&
      claimOwner === live &&
      !movedLive &&
      held === `${process.pid}\n` &&
      threw === '',
    detail: `peerRan=${peerRan} peer=${peer !== null} first=${first !== null} claim=${JSON.stringify(claimOwner)} movedLive=${movedLive} lock=${JSON.stringify(held)} threw=${threw}`,
  };
}

/** A holder that stays inside its claim longer than any age threshold keeps it: a second taker arriving then is refused, and the first holder's lock is the only one. */
function slowLiveHolder(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  let peer: (() => void) | null = null;
  let peerRan = false;
  let peerLock = '';
  const runPeer = (): void => {
    if (peerRan) return;
    peerRan = true;
    ageMinute(claim);
    if (fs.existsSync(path.join(claim, 'owner'))) ageMinute(path.join(claim, 'owner'));
    peer = takeLock(root, { claimWaitMs: 0 });
    peerLock = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  };
  let first: (() => void) | null = null;
  let threw = '';
  try {
    first = withFs({ existsSync: (p) => p === lock && runPeer() }, () =>
      takeLock(root, { whileClaimed: runPeer })
    );
  } catch (err) {
    threw = (err as Error).message;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a live holder slower than any age threshold keeps its claim, and a second taker arriving then is refused',
    ok:
      peerRan &&
      first !== null &&
      peer === null &&
      peerLock === '<absent>' &&
      held === `${process.pid}\n` &&
      threw === '',
    detail: `peerRan=${peerRan} first=${first !== null} peer=${peer !== null} lockDuringHold=${JSON.stringify(peerLock)} lock=${JSON.stringify(held)} threw=${threw}`,
  };
}

/** Without hard links, a live lock that replaced the judged stale one before the move is put back into the empty slot, not stranded in a tomb. */
function noHardLinkPutBack(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  fs.mkdirSync(jr, { recursive: true });
  fs.writeFileSync(lock, '999999999\n');
  const fresh = `${process.ppid}\n`;
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = withFs({}, () =>
      takeLock(root, {
        afterStaleVerdict: () => {
          fs.rmSync(lock, { force: true });
          fs.writeFileSync(lock, fresh);
        },
      })
    );
  } catch (err) {
    threw = (err as Error).message;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  const tombs = fs.readdirSync(jr).filter((n) => n.startsWith('.lock.stale.'));
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: without hard links a live lock moved aside by mistake goes back into its empty slot',
    ok: taken === null && held === fresh && tombs.length === 0 && threw === '',
    detail: `took=${taken !== null} lock=${JSON.stringify(held)} tombs=${tombs.length} threw=${threw}`,
  };
}

/** A lock whose pid is alive but belongs to a process started after the lock was written (a reused pid) is stale; so is a claim owned that way. */
function reusedPid(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  fs.mkdirSync(`${lock}.claim`, { recursive: true });
  fs.writeFileSync(path.join(`${lock}.claim`, 'owner'), `${process.ppid} 1 abc\n`);
  fs.writeFileSync(lock, `${process.ppid}\n`);
  fs.writeFileSync(`${lock}.owner`, `${process.ppid} 1 abc\n`);
  const before = liveLockPid(root);
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = takeLock(root, { claimWaitMs: 0 });
  } catch (err) {
    threw = (err as Error).message;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a live pid whose start time differs from the one recorded is a reused pid, not the holder',
    ok: before === null && taken !== null && held === `${process.pid}\n` && threw === '',
    detail: `liveLockPid=${before} took=${taken !== null} lock=${JSON.stringify(held)} threw=${threw}`,
  };
}

/** A killed taker's private names (its creator pid dead) are swept; a live taker's and the tombs are kept. */
function deadTakerDebris(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const hex = 'ab'.repeat(8);
  const dead = [
    `.lock.claim.999999999.${hex}`,
    `.lock.999999999.${hex}`,
    `.lock.owner.999999999.${hex}`,
  ];
  const kept = [
    `.lock.claim.${process.ppid}.${hex}`,
    `.lock.claim.dead.${hex}`,
    '.lock.stale.999999999.abcd1234',
  ];
  fs.mkdirSync(path.join(jr, dead[0]), { recursive: true });
  fs.writeFileSync(path.join(jr, dead[0], 'owner'), `999999999 - ${hex}\n`);
  fs.writeFileSync(path.join(jr, dead[1]), '999999999\n');
  fs.writeFileSync(path.join(jr, dead[2]), `999999999 - ${hex}\n`);
  fs.mkdirSync(path.join(jr, kept[0]));
  fs.mkdirSync(path.join(jr, kept[1]));
  fs.writeFileSync(path.join(jr, kept[2]), '999999999\n');
  const release = takeLock(root);
  const left = fs.readdirSync(jr).sort();
  release?.();
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: "lock: a killed taker's private names are swept, a live taker's and the tombs are kept",
    ok:
      release !== null &&
      dead.every((n) => !left.includes(n)) &&
      kept.every((n) => left.includes(n)),
    detail: `left=${left.join(',')}`,
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
  return [
    noHardLinkLock(),
    staleClaimTwoTakers(),
    slowLiveHolder(),
    noHardLinkPutBack(),
    reusedPid(),
    deadTakerDebris(),
    symlinkedStamp(),
    liveRunRefusesReplay(),
  ];
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  process.exit(runControls(txnCases()) === 0 ? 0 : 1);
