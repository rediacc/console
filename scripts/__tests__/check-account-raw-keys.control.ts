#!/usr/bin/env tsx
/**
 * Control harness for the three raw-key layers (PLAN-account-sidebar-redesign, Design 7).
 *
 * Each layer is driven through its REAL invocation and must go red on a planted raw key, so no
 * layer can go silent while its own selftest still passes:
 *   (a) check-account-i18n-key-usage.ts, on a mirror holding a planted `ui('zzzLabel')`;
 *   (b) check-account-raw-keys.ts, on the same mirror holding a planted unknown `labelKey`, and
 *       again against an allowlist entry with no BLOCKER: reason and one that matches nothing;
 *   (c) raw-key-render.test.tsx, under RAW_KEY_RENDER_PLANT=1, which mounts a component that
 *       renders `offerNameLabel`.
 *
 * A CONTROL OF THE CONTROL comes first: (a) and (b) must PASS on the mirror before anything is
 * planted. Without it a mirror that is merely broken (a missing catalog, a bad copy) would make
 * every plant "fire" and prove nothing about the gates.
 *
 * The plants go into a mirror under the OS temp dir, never into the real tree: the gates read
 * private/account through the shared SUBMODULE_PRESENCE_ROOT seam, so the mirror holds a COPY of
 * web/src (where the plants go) and a symlink to private/account/src (the served catalog that
 * layer (a) imports). The render plant needs no file at all.
 *
 * Run: npx tsx scripts/__tests__/check-account-raw-keys.control.ts
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { GREEN, NC, RED } from '../lib/console.js';
import { REPO_ROOT } from '../lib/repo-root.js';

const ACCOUNT = path.join(REPO_ROOT, 'private/account');
const KEY_USAGE = 'scripts/gates/check-account-i18n-key-usage.ts';
const RAW_KEYS = 'scripts/gates/check-account-raw-keys.ts';
const RENDER_TEST = 'src/test/__tests__/raw-key-render.test.tsx';

interface Run {
  rc: number | null;
  out: string;
}

function run(cmd: string, args: string[], cwd: string, env: Record<string, string>): Run {
  const r = spawnSync(cmd, args, {
    cwd,
    encoding: 'utf8',
    env: { ...process.env, ...env, FORCE_COLOR: '0' },
    timeout: 300_000,
  });
  return {
    rc: r.status,
    out: `${r.stdout ?? ''}${r.stderr ?? ''}${r.error ? String(r.error) : ''}`,
  };
}

const tsx = (gate: string, env: Record<string, string>): Run =>
  run('npx', ['tsx', gate], REPO_ROOT, env);

let failures = 0;
let PASSED = 0;
function check(name: string, ok: boolean, r: Run): void {
  if (ok) {
    PASSED++;
    console.log(`  ${GREEN}PASS${NC}  ${name}`);
    return;
  }
  failures++;
  console.error(`  ${RED}FAIL${NC}  ${name} (rc=${r.rc})`);
  console.error(
    r.out
      .split('\n')
      .slice(-25)
      .map((l) => `        ${l}`)
      .join('\n')
  );
}

function main(): void {
  for (const p of [
    path.join(ACCOUNT, 'web/src/i18n/locales/en'),
    path.join(ACCOUNT, 'src/pricing'),
  ]) {
    if (!fs.existsSync(p)) {
      console.error(
        `${RED}✗${NC} ${p} is missing: the account submodule is not checked out, so no layer can be controlled. Run \`git submodule update --init private/account\`.`
      );
      process.exit(1);
    }
  }
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'raw-keys-mirror-'));
  try {
    const mirrorAccount = path.join(root, 'private/account');
    fs.mkdirSync(path.join(mirrorAccount, 'web'), { recursive: true });
    fs.cpSync(path.join(ACCOUNT, 'web/src'), path.join(mirrorAccount, 'web/src'), {
      recursive: true,
    });
    fs.symlinkSync(path.join(ACCOUNT, 'src'), path.join(mirrorAccount, 'src'), 'dir');
    const seam = { SUBMODULE_PRESENCE_ROOT: root, CI: 'true' };

    console.log('control of the control: both static layers pass on the unplanted mirror');
    const cleanA = tsx(KEY_USAGE, seam);
    check('(a) key-usage gate passes on the clean mirror', cleanA.rc === 0, cleanA);
    const cleanB = tsx(RAW_KEYS, seam);
    check('(b) raw-key gate passes on the clean mirror', cleanB.rc === 0, cleanB);

    console.log('plants');
    const uiProbe = path.join(mirrorAccount, 'web/src/pages/partner/offer/__raw_key_probe__.tsx');
    fs.writeFileSync(
      uiProbe,
      "export const P = ({ ui }: { ui: (k: string) => string }) => <p>{ui('zzzLabel')}</p>;\n"
    );
    const a = tsx(KEY_USAGE, seam);
    check(
      "(a) a scratch ui('zzzLabel') fails the key-usage gate, naming it",
      a.rc !== 0 && a.out.includes("ui('zzzLabel')") && a.out.includes('__raw_key_probe__.tsx'),
      a
    );
    fs.rmSync(uiProbe);

    const navProbe = path.join(mirrorAccount, 'web/src/lib/__raw_key_probe__.ts');
    fs.writeFileSync(
      navProbe,
      "export const PROBE = [\n  { id: 'probe', labelKey: 'nav:item.zzzPlanted' },\n];\n"
    );
    const b = tsx(RAW_KEYS, seam);
    check(
      '(b) an unknown labelKey in a scratch config array fails the raw-key gate, naming file, line and key',
      b.rc !== 0 &&
        b.out.includes("web/src/lib/__raw_key_probe__.ts:2: labelKey 'nav:item.zzzPlanted'"),
      b
    );
    fs.rmSync(navProbe);

    const allowDir = path.join(root, 'allow');
    fs.mkdirSync(allowDir);
    const noBlocker = path.join(allowDir, 'no-blocker.json');
    fs.writeFileSync(
      noBlocker,
      JSON.stringify({
        entries: [{ string: 'zzz', surface: 'lib/nav-config.ts', reason: 'ships next week' }],
      })
    );
    const b2 = tsx(RAW_KEYS, { ...seam, ACCOUNT_RAW_KEY_ALLOWLIST: noBlocker });
    check(
      '(b) an allowlist entry without a BLOCKER: reason fails',
      b2.rc !== 0 && b2.out.includes('must start with "BLOCKER:"'),
      b2
    );
    const stale = path.join(allowDir, 'stale.json');
    fs.writeFileSync(
      stale,
      JSON.stringify({
        entries: [
          {
            string: 'nav:item.neverPresent',
            surface: 'lib/nav-config.ts',
            reason:
              'BLOCKER: control fixture written by check-account-raw-keys.control.ts to prove a dead entry is refused',
          },
        ],
      })
    );
    const b3 = tsx(RAW_KEYS, { ...seam, ACCOUNT_RAW_KEY_ALLOWLIST: stale });
    check(
      '(b) an allowlist entry that matches nothing fails as stale',
      b3.rc !== 0 && b3.out.includes('STALE entry'),
      b3
    );

    const c = run(
      'npx',
      ['vitest', 'run', RENDER_TEST, '--reporter=dot'],
      path.join(ACCOUNT, 'web'),
      {
        RAW_KEY_RENDER_PLANT: '1',
      }
    );
    check(
      '(c) a component rendering offerNameLabel fails the render sweep',
      c.rc !== 0 &&
        c.out.includes('raw key on screen: \\"offerNameLabel\\"') &&
        c.out.includes('planted-raw-key'),
      c
    );
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
  if (failures > 0) {
    console.error(
      `${RED}✗${NC} ${failures} raw-key control(s) failed: a layer cannot be trusted to catch a raw key.`
    );
    process.exit(1);
  }
  console.log(
    `${GREEN}✓${NC} ${PASSED} raw-key controls passed: layers (a), (b) and (c) each fail on a planted raw key and the static layers pass clean.`
  );
}

main();
