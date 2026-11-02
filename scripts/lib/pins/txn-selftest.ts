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
import { type ControlCase, type RunControlsOptions, runControls } from '../controls.js';
import { isEntryPoint } from '../entry-point.js';
import {
  journalRoot,
  ledgerHolds,
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

/** Runs `body` with hard links refused (EPERM) and a hook after every successful rename, restoring fs after; the takers' race windows are reached through the LockSeams, and this hook only watches. */
function withFs<T>(
  hooks: { renameSync?: (from: fs.PathLike, to: fs.PathLike) => void },
  body: () => T
): T {
  const realLink = fs.linkSync;
  const realRename = fs.renameSync;
  fs.linkSync = (): void => {
    throw Object.assign(new Error('operation not permitted'), { code: 'EPERM' });
  };
  fs.renameSync = ((from: fs.PathLike, to: fs.PathLike) => {
    realRename(from, to);
    hooks.renameSync?.(from, to);
  }) as typeof fs.renameSync;
  try {
    return body();
  } finally {
    fs.renameSync = realRename;
    fs.linkSync = realLink;
  }
}

/** Sets a path's times `n` minutes into the past. */
const ageMinutes = (p: string, n: number): void => {
  const t = new Date(Date.now() - n * 60_000);
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
  ageMinutes(claim, 1);
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
    first = withFs({ renameSync: watchMove }, () =>
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

/** A live holder keeps its claim however long it holds it: a taker arriving within the ceiling is refused as a held lock, one arriving past it is refused by name with the holder's pid and the command to run, neither moves the claim, and the first holder's lock is the only one. */
function slowLiveHolder(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  let early: (() => void) | null = null;
  let late: (() => void) | null = null;
  let lateThrew = '';
  let peerRan = false;
  let peerLock = '';
  let claimMoved = false;
  const runPeer = (): void => {
    if (peerRan) return;
    peerRan = true;
    const mine = fs.readFileSync(path.join(claim, 'owner'), 'utf8');
    early = takeLock(root, { claimWaitMs: 0 });
    ageMinutes(path.join(claim, 'owner'), 2);
    try {
      late = takeLock(root, { claimWaitMs: 0 });
    } catch (err) {
      lateThrew = (err as Error).message;
    }
    claimMoved = fs.readFileSync(path.join(claim, 'owner'), 'utf8') !== mine;
    peerLock = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  };
  let first: (() => void) | null = null;
  let threw = '';
  try {
    first = withFs({}, () => takeLock(root, { whileClaimed: runPeer }));
  } catch (err) {
    threw = (err as Error).message;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: "lock: a live holder keeps its claim however long; a taker within the ceiling reads a held lock, one past it is refused naming the holder's pid",
    ok:
      peerRan &&
      first !== null &&
      early === null &&
      late === null &&
      lateThrew.includes(`live pid ${process.pid}`) &&
      lateThrew.includes(`kill -CONT ${process.pid}`) &&
      !claimMoved &&
      peerLock === '<absent>' &&
      held === `${process.pid}\n` &&
      threw === '',
    detail: `peerRan=${peerRan} first=${first !== null} early=${early !== null} late=${late !== null} lateThrew=${JSON.stringify(lateThrew)} claimMoved=${claimMoved} lockDuringHold=${JSON.stringify(peerLock)} lock=${JSON.stringify(held)} threw=${threw}`,
  };
}

/** A non-empty claim with no owner file, which no taker writes, is cleared rather than refused on every run, and the cleared directory is swept once no other taker is in progress. */
function ownerlessClaim(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  fs.mkdirSync(claim, { recursive: true });
  fs.writeFileSync(path.join(claim, 'junk'), 'x\n');
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = takeLock(root);
  } catch (err) {
    threw = (err as Error).message;
  }
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  taken?.();
  const left = fs.readdirSync(jr).filter((n) => n.startsWith('.lock.claim'));
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: an ownerless claim is cleared and swept, not refused on every run',
    ok: taken !== null && held === `${process.pid}\n` && left.length === 0 && threw === '',
    detail: `took=${taken !== null} lock=${JSON.stringify(held)} left=${left.join(',')} threw=${threw}`,
  };
}

/** A taker acting on a dead claim that left the slot without its tomb (a hand removal) moves the live claim installed since; when a third claim fills the slot before the put-back, the mover refuses by naming the tomb that holds the live claim, rather than leaving it stranded unreported. */
function putBackRefused(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  fs.mkdirSync(claim, { recursive: true });
  fs.writeFileSync(path.join(claim, 'owner'), '999999999 - dead1\n');
  const holder = `${process.ppid} - feed3`;
  const third = `${process.ppid} - feed4`;
  const install = (text: string): void => {
    fs.mkdirSync(claim);
    fs.writeFileSync(path.join(claim, 'owner'), `${text}\n`);
  };
  let tomb = '';
  // withFs runs the real rename first, so by the time this hook fires the judged claim is already in its tomb and the slot is free for the replacement.
  const refill = (from: fs.PathLike, to: fs.PathLike): void => {
    if (tomb || from !== claim || !path.basename(String(to)).startsWith('.lock.claim.dead.'))
      return;
    tomb = String(to);
    install(third);
  };
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = withFs({ renameSync: refill }, () =>
      takeLock(root, {
        claimWaitMs: 50,
        afterClaimVerdict: () => {
          fs.rmSync(claim, { recursive: true, force: true });
          install(holder);
        },
      })
    );
  } catch (err) {
    threw = (err as Error).message;
  }
  const inTomb =
    tomb && fs.existsSync(tomb)
      ? fs.readFileSync(path.join(tomb, 'owner'), 'utf8').trim()
      : '<absent>';
  const inSlot = fs.existsSync(claim)
    ? fs.readFileSync(path.join(claim, 'owner'), 'utf8').trim()
    : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a mis-moved live claim that cannot go back is refused by naming its tomb, not stranded unreported',
    ok:
      taken === null &&
      tomb !== '' &&
      threw.includes(`mv ${tomb} ${claim}`) &&
      inTomb === holder &&
      inSlot === third,
    detail: `took=${taken !== null} tomb=${path.basename(tomb)} inTomb=${JSON.stringify(inTomb)} inSlot=${JSON.stringify(inSlot)} threw=${threw}`,
  };
}

/** A failure to stamp the install time comes after the claim is installed, so the claim is dropped before the error propagates; a stranded claim would hold every later taker until this process exits. */
function stampFailureDropsClaim(): ControlCase {
  const root = tmpRoot();
  const claim = `${path.join(journalRoot(root), '.lock')}.claim`;
  const realUtimes = fs.utimesSync;
  fs.utimesSync = (() => {
    throw Object.assign(new Error('operation not permitted'), { code: 'EPERM' });
  }) as typeof fs.utimesSync;
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = takeLock(root, { claimWaitMs: 0 });
  } catch (err) {
    threw = (err as Error).message;
  } finally {
    fs.utimesSync = realUtimes;
  }
  const left = fs.existsSync(claim);
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a failure after the claim is installed drops the claim instead of stranding it',
    ok: taken === null && threw.includes('operation not permitted') && !left,
    detail: `took=${taken !== null} claimLeft=${left} threw=${threw}`,
  };
}

/** A taker acting on a dead claim that moves a different dead claim (the judged one left by a hand removal) leaves it in its tomb for the sweep and carries on, rather than waiting and refusing with a message about a live claim. */
function movedDeadClaimIsHarmless(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  fs.mkdirSync(claim, { recursive: true });
  fs.writeFileSync(path.join(claim, 'owner'), '999999999 - dead7\n');
  let moved = false;
  const refill = (from: fs.PathLike, to: fs.PathLike): void => {
    if (moved || from !== claim || !path.basename(String(to)).startsWith('.lock.claim.dead.'))
      return;
    moved = true;
    fs.mkdirSync(claim);
    fs.writeFileSync(path.join(claim, 'owner'), `${process.ppid} - feed9\n`);
  };
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = withFs({ renameSync: refill }, () =>
      takeLock(root, {
        claimWaitMs: 50,
        afterClaimVerdict: () => {
          fs.rmSync(claim, { recursive: true, force: true });
          fs.mkdirSync(claim);
          fs.writeFileSync(path.join(claim, 'owner'), '999999998 - dead8\n');
        },
      })
    );
  } catch (err) {
    threw = (err as Error).message;
  }
  const tombs = fs.existsSync(jr)
    ? fs.readdirSync(jr).filter((n) => n.startsWith('.lock.claim.dead.'))
    : [];
  taken?.();
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a different dead claim moved by mistake is left in its tomb, not reported as a live claim stranded',
    ok: moved && threw === '' && tombs.length > 0,
    detail: `moved=${moved} took=${taken !== null} tombs=${tombs.length} threw=${threw}`,
  };
}

/** A holder whose claim was moved into a tomb while it held it takes it back out, leaves the claim now in the slot alone, gives back the lock it took and refuses. */
function claimMovedWhileHeld(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const lock = path.join(jr, '.lock');
  const claim = `${lock}.claim`;
  const tomb = `${claim}.dead.${'12'.repeat(8)}`;
  const other = `${process.ppid} - feed6`;
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = takeLock(root, {
      whileClaimed: () => {
        fs.renameSync(claim, tomb);
        fs.mkdirSync(claim);
        fs.writeFileSync(path.join(claim, 'owner'), `${other}\n`);
      },
    });
  } catch (err) {
    threw = (err as Error).message;
  }
  const inSlot = fs.existsSync(claim)
    ? fs.readFileSync(path.join(claim, 'owner'), 'utf8').trim()
    : '<absent>';
  const tombLeft = fs.existsSync(tomb);
  const held = fs.existsSync(lock) ? fs.readFileSync(lock, 'utf8') : '<absent>';
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'lock: a holder whose claim was moved aside takes it back out of its tomb, leaves the slot alone, gives back its lock and refuses',
    ok:
      taken === null &&
      threw.includes('was moved to') &&
      !tombLeft &&
      inSlot === other &&
      held === '<absent>',
    detail: `took=${taken !== null} tombLeft=${tombLeft} inSlot=${JSON.stringify(inSlot)} lock=${JSON.stringify(held)} threw=${threw}`,
  };
}

/** With no other taker in progress, a claim holder sweeps the tombs of dead claims and keeps a tomb whose owner is alive. */
function deadTombsSwept(): ControlCase {
  const root = tmpRoot();
  const jr = journalRoot(root);
  const deadTomb = `.lock.claim.dead.${'cd'.repeat(8)}`;
  const liveTomb = `.lock.claim.dead.${'ef'.repeat(8)}`;
  fs.mkdirSync(path.join(jr, deadTomb), { recursive: true });
  fs.writeFileSync(path.join(jr, deadTomb, 'owner'), '999999999 - dead2\n');
  fs.mkdirSync(path.join(jr, liveTomb));
  fs.writeFileSync(path.join(jr, liveTomb, 'owner'), `${process.ppid} - feed5\n`);
  const release = takeLock(root);
  const left = fs.readdirSync(jr);
  release?.();
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: "lock: with no other taker in progress the dead claims' tombs are swept, a live-owned one is kept",
    ok: release !== null && !left.includes(deadTomb) && left.includes(liveTomb),
    detail: `left=${left.join(',')}`,
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
  const staleNames: string[] = [];
  const watch = (_from: fs.PathLike, to: fs.PathLike): void => {
    if (path.basename(String(to)).startsWith('.lock.stale.'))
      staleNames.push(path.basename(String(to)));
  };
  let taken: (() => void) | null = null;
  let threw = '';
  try {
    taken = withFs({ renameSync: watch }, () =>
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
    name: 'lock: without hard links a live lock moved aside by mistake goes back into its empty slot, from a tomb named .lock.stale.<pid>.<16-hex nonce>',
    ok:
      taken === null &&
      held === fresh &&
      tombs.length === 0 &&
      staleNames.length > 0 &&
      staleNames.every((n) => /^\.lock\.stale\.\d+\.[0-9a-f]{16}$/.test(n)) &&
      threw === '',
    detail: `took=${taken !== null} lock=${JSON.stringify(held)} tombs=${tombs.length} staleNames=${staleNames.join(',')} threw=${threw}`,
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

/** The selftest's exit code: 1 with a VACUOUS line when the case list is below the floor, otherwise the controls' verdict. */
export function txnSelftestExit(cases: ControlCase[], opts: RunControlsOptions = {}): number {
  const err = opts.err ?? ((l: string) => console.error(l));
  if (cases.length < MIN_TXN_CASES) {
    err(`VACUOUS: ${cases.length} txn control(s), below the floor of ${MIN_TXN_CASES}`);
    return 1;
  }
  return runControls(cases, opts) === 0 ? 0 : 1;
}

/** A case list one short of the floor exits 1 with its VACUOUS line before any control runs, and one at the floor runs its controls. */
function floorRefusesShortRun(): ControlCase {
  const lines: string[] = [];
  const opts = { log: (l: string) => lines.push(l), err: (l: string) => lines.push(l) };
  const passing = (n: number): ControlCase[] =>
    Array.from({ length: n }, (_, i) => ({ name: `planted ${i}`, ok: true }));
  const short = txnSelftestExit(passing(MIN_TXN_CASES - 1), opts);
  const shortLines = lines.splice(0);
  const full = txnSelftestExit(passing(MIN_TXN_CASES), opts);
  return {
    name: 'floor: a run one control short of the floor exits 1 as VACUOUS, a run at the floor runs its controls',
    ok:
      short === 1 &&
      shortLines.length === 1 &&
      shortLines[0].startsWith('VACUOUS:') &&
      full === 0 &&
      lines.length === MIN_TXN_CASES,
    detail: `short=${short} shortLines=${JSON.stringify(shortLines)} full=${full} fullLines=${lines.length}`,
  };
}

/** The ledger holds for the exact bytes a done journal recorded, not for other bytes, a missing key, or a journal that did not finish. */
function ledgerByHash(): ControlCase {
  const root = tmpRoot();
  const put = (stamp: string, state: string, wrote: string | null, late?: string): void => {
    const dir = path.join(journalRoot(root), stamp);
    fs.mkdirSync(dir, { recursive: true });
    const files = { a: { repo: '.', file: 'a', before: null, wrote } };
    fs.writeFileSync(
      path.join(dir, 'journal.json'),
      JSON.stringify({ stamp, state, pins: [], files, late: late ? { b: late } : undefined })
    );
  };
  put('s1', 'done', 'h1', 'h2');
  put('s2', 'restored', 'h3');
  const got = {
    exact: ledgerHolds(root, 'a', 'h1'),
    other: ledgerHolds(root, 'a', 'hX'),
    late: ledgerHolds(root, 'b', 'h2'),
    unfinished: ledgerHolds(root, 'a', 'h3'),
    missing: ledgerHolds(root, 'c', 'h1'),
  };
  fs.rmSync(root, { recursive: true, force: true });
  return {
    name: 'ledger: holds for the bytes a done journal wrote (or late-wrote) and for nothing else',
    ok: got.exact && got.late && !got.other && !got.unfinished && !got.missing,
    detail: JSON.stringify(got),
  };
}

export function txnCases(): ControlCase[] {
  return [
    noHardLinkLock(),
    staleClaimTwoTakers(),
    slowLiveHolder(),
    ownerlessClaim(),
    putBackRefused(),
    stampFailureDropsClaim(),
    movedDeadClaimIsHarmless(),
    claimMovedWhileHeld(),
    deadTombsSwept(),
    noHardLinkPutBack(),
    reusedPid(),
    deadTakerDebris(),
    symlinkedStamp(),
    liveRunRefusesReplay(),
    floorRefusesShortRun(),
    ledgerByHash(),
  ];
}

// The two directory listings above are each judged against a file the case wrote itself, so an empty listing fails its case; the floor guards the case list, so a run that drops controls is refused rather than reported green.
const MIN_TXN_CASES = 13;

if (isEntryPoint(import.meta.filename)) {
  process.exit(txnSelftestExit(txnCases()));
}
