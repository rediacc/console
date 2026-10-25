/**
 * The provisioner's slot-pruning step, driven in a real POSIX shell against a temp tree: current plus the 2 previous slots survive, the rest go, and a slot a unit file names is kept.
 */

import { execFileSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  utimesSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildSlotPruneStep } from '../renet/renet-slot-prune.js';

let tree: string;
let root: string;
let unitDir: string;

function makeSlot(name: string, ageDays: number): string {
  const dir = join(root, name);
  mkdirSync(dir, { recursive: true });
  const bin = join(dir, 'renet');
  writeFileSync(bin, '#!/bin/sh\n');
  const when = new Date(Date.now() - ageDays * 86_400_000);
  utimesSync(bin, when, when);
  return dir;
}

function pointCurrentAt(slotDir: string): string {
  mkdirSync(join(root, 'current'), { recursive: true });
  const currentPath = join(root, 'current', 'renet');
  symlinkSync(join(slotDir, 'renet'), currentPath);
  return currentPath;
}

function prune(currentPath: string, installPath: string, keep = 3): void {
  execFileSync(
    'sh',
    [
      '-c',
      `set -eu; ${buildSlotPruneStep({ root, currentPath, installPath, unitDir, keep, sudo: '' })}`,
    ],
    { stdio: 'pipe' }
  );
}

beforeEach(() => {
  tree = mkdtempSync(join(tmpdir(), 'slotprune-'));
  root = join(tree, 'renet');
  unitDir = join(tree, 'units');
  mkdirSync(root, { recursive: true });
  mkdirSync(unitDir, { recursive: true });
});

afterEach(() => {
  rmSync(tree, { recursive: true, force: true });
});

describe('buildSlotPruneStep', () => {
  it('leaves current plus the 2 previous when there are 5 slots', () => {
    makeSlot('1.0.0', 50);
    makeSlot('1.1.0', 40);
    makeSlot('1.2.0', 30);
    makeSlot('1.3.0', 20);
    const newest = makeSlot('1.4.0', 1);
    const currentPath = pointCurrentAt(newest);

    prune(currentPath, join(newest, 'renet'));

    expect(existsSync(join(root, '1.0.0'))).toBe(false);
    expect(existsSync(join(root, '1.1.0'))).toBe(false);
    expect(existsSync(join(root, '1.2.0'))).toBe(true);
    expect(existsSync(join(root, '1.3.0'))).toBe(true);
    expect(existsSync(join(root, '1.4.0'))).toBe(true);
    expect(existsSync(currentPath)).toBe(true);
  });

  it('keeps current even when it is not the newest slot, then fills from the newest', () => {
    makeSlot('1.0.0', 50);
    makeSlot('1.1.0', 40);
    makeSlot('1.2.0', 30);
    makeSlot('1.3.0', 20);
    const old = join(root, '1.0.0');
    const currentPath = pointCurrentAt(old);

    prune(currentPath, join(old, 'renet'));

    expect(existsSync(join(root, '1.0.0'))).toBe(true);
    expect(existsSync(join(root, '1.1.0'))).toBe(false);
    expect(existsSync(join(root, '1.2.0'))).toBe(true);
    expect(existsSync(join(root, '1.3.0'))).toBe(true);
  });

  it('keeps a slot a unit file names', () => {
    makeSlot('1.0.0', 50);
    makeSlot('1.1.0', 40);
    makeSlot('1.2.0', 30);
    makeSlot('1.3.0', 20);
    const newest = makeSlot('1.4.0', 1);
    const currentPath = pointCurrentAt(newest);
    writeFileSync(
      join(unitDir, 'rediacc-docker-1.service'),
      `[Service]\nExecStart=${join(root, '1.0.0')}/renet daemon\n`
    );

    prune(currentPath, join(newest, 'renet'));

    expect(existsSync(join(root, '1.0.0'))).toBe(true);
    expect(existsSync(join(root, '1.1.0'))).toBe(false);
  });

  it('leaves a directory without a renet file alone', () => {
    const newest = makeSlot('1.4.0', 1);
    mkdirSync(join(root, 'scratch'));
    const currentPath = pointCurrentAt(newest);

    prune(currentPath, join(newest, 'renet'));

    expect(existsSync(join(root, 'scratch'))).toBe(true);
  });
});
