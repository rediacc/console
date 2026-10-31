/**
 * The controls of the T8 drivers (actions, go-mod, os-ceph-host, ceph-image, real-provider,
 * docker), over fixture trees and stub network answers; nothing here reads the network or
 * touches the tracked tree.
 *
 *   npx tsx scripts/lib/pins/drivers/selftest.ts [--selftest]
 *   PINS_T8_MUTANT=<name> npx tsx scripts/lib/pins/drivers/selftest.ts --selftest   # exits 1
 *
 * The registry entries are the REAL ones (.ci/config/pins.json), so a site regex that
 * changes is caught here; the trees are minimal files shaped like the real ones. Every
 * mutant of ./shared.ts T8_MUTANTS must turn its own case red, and `--selftest` proves it
 * in-process for all of them before it reports.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { WK_CEPH_IMAGE_REPO } from '../../../../packages/shared/src/config/well-known.generated.js';
import { runControls } from '../../controls.js';
import { isEntryPoint } from '../../entry-point.js';
import { policyPath } from '../../policy-paths.js';
import { REPO_ROOT } from '../../repo-root.js';
// driver.js first: the driver modules use its exports only inside functions, but a driver as
// the entry point would evaluate the table before the drivers finish (see ./index.ts).
import { type DriverContext, type PinPlan, PlanRefused } from '../driver.js';
import { loadRegistry, type PinEntry, type PinRegistry } from '../registry.js';
import { majorLineOf } from '../status.js';
import { actionsDriver } from './actions.js';
import { cephImageDriver } from './cephimage.js';
import { dockerDriver } from './docker.js';
import { gomodDriver } from './gomod.js';
import {
  deferredCount,
  deferredNames,
  inRangePlan,
  inRangeReleases,
  judgeOverrides,
  keptMoves,
  type NpmPlanJson,
  type OverrideJudgement,
  overrideDrift,
  overrideTarget,
  type Packument,
  stepsOf,
} from './npm.js';
import { osCephHostDriver } from './os.js';
import { planBiomeSchema } from './pin-manifests.js';
import { realProviderDriver } from './realprovider.js';
import { type Deps, T8_MUTANTS, type T8Mutant } from './shared.js';

const DAY = 86_400_000;
const NOW = Date.parse('2026-10-14T12:00:00Z');
const OLD = Date.parse('2026-08-01T00:00:00Z');
const FRESH = Date.parse('2026-10-14T06:00:00Z');
const iso = (ms: number): string => new Date(ms).toISOString();
const sha = (c: string): string => c.repeat(40);

const REG: PinRegistry = loadRegistry(path.join(REPO_ROOT, '.ci/config/pins.json'));
const entry = (id: string): PinEntry => {
  const e = REG.entries.find((x) => x.id === id);
  if (!e) throw new Error(`the registry has no entry ${id}`);
  return e;
};

// ---- fixtures -------------------------------------------------------------------------------

const tmps: string[] = [];
function tree(files: Record<string, string>): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'pins-t8-'));
  tmps.push(root);
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  return root;
}
const ctxOf = (root: string): DriverContext => ({
  root,
  reg: REG,
  fixture: null,
  mutant: null,
  read(p) {
    const abs = path.join(root, p.repo, p.file);
    return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
  },
});

interface Stub {
  github?: (p: string) => unknown;
  json?: (u: string) => unknown;
  run?: (cmd: string) => { rc: number; out: string; stdout?: string };
}
function deps(s: Stub, nowMs = NOW): { deps: Deps; cmds: string[] } {
  const cmds: string[] = [];
  return {
    cmds,
    deps: {
      nowMs: () => nowMs,
      windowMs: () => DAY,
      github: (p) => {
        try {
          return Promise.resolve(s.github?.(p));
        } catch (err) {
          return Promise.reject(err);
        }
      },
      json: (u) => {
        try {
          return Promise.resolve(s.json?.(u));
        } catch (err) {
          return Promise.reject(err);
        }
      },
      run: (cmd) => {
        cmds.push(cmd);
        const r = s.run?.(cmd) ?? { rc: 127, out: 'no stub' };
        return { rc: r.rc, out: r.out, stdout: r.stdout ?? r.out };
      },
    },
  };
}

const rejects = async (p: Promise<unknown>): Promise<Error | null> => {
  try {
    await p;
    return null;
  } catch (err) {
    return err as Error;
  }
};

/** What a plan wrote, by file. */
const written = (plan: PinPlan): Partial<Record<string, string>> =>
  Object.fromEntries(plan.writes.map((w) => [`${w.repo}:${w.file}`, w.after]));

// ---- actions --------------------------------------------------------------------------------

const S = { co: sha('1'), ua: sha('2'), cache: sha('3'), bx: sha('4'), bw: sha('5'), bl: sha('6') };
const N = { co: sha('a'), ua: sha('b'), cache: sha('c'), bw: sha('d') };

function actionsTree(extra: Record<string, string> = {}): string {
  return tree({
    '.github/workflows/ci-a.yml': [
      'jobs:',
      '  a:',
      '    steps:',
      `      - uses: actions/checkout@${S.co} # v1.0.1`,
      `      - uses: actions/upload-artifact@${S.ua}  # v7.0.2`,
      `      - uses: actions/cache/restore@${S.cache} # v6.1.0`,
      `      - uses: actions/cache/save@${S.cache} # v6.1.0`,
      `      - uses: docker/setup-buildx-action@${S.bx}  # v4`,
      `      - uses: bitwarden/sm-action@${S.bw}  # v3.0.1`,
      `      - uses: blocked/thing@${S.bl} # v1.0.0`,
      '      - uses: ./local',
      '',
    ].join('\n'),
    '.github/workflows/ci-b.yml': `steps:\n  - uses: actions/checkout@${S.co} # v1.0.1\n  - uses: actions/upload-artifact@${S.ua} # v7.0.2\n`,
    '.github/actions/x/action.yml': `runs:\n  steps:\n    - uses: actions/checkout@${S.co} # v1.0.1\n`,
    '.ci/breakpoint/workflow/breakpoint.yml': `steps:\n  - uses: actions/checkout@${S.co} # v1.0.1\n`,
    'scripts/gate-bind.ts': `export const UPLOAD_ARTIFACT_PIN =\n  'actions/upload-artifact@${S.ua}  # v7.0.2';\n`,
    '.ci/config/actions-allowlist.json': `{\n  "patterns_allowed": [\n    "rediacc/*",\n    "bitwarden/sm-action@${S.bw}"\n  ]\n}\n`,
    [policyPath('.actions-upgrade-blocklist', '.')]:
      '# Format: owner/repo # reason\nblocked/thing # BLOCKER: pinned for a reason\n',
    ...extra,
  });
}

interface Latest {
  tag: string;
  at: number;
}
function ghLatest(m: Record<string, Latest>): (p: string) => unknown {
  return (p) => {
    const rel = /^\/repos\/([^/]+\/[^/]+)\/releases\/latest$/.exec(p);
    if (rel) {
      const l = m[rel[1]];
      if (!l) throw new Error(`stub: no release for ${rel[1]}`);
      return { tag_name: l.tag, published_at: iso(l.at) };
    }
    const c = /^\/repos\/([^/]+\/[^/]+)\/commits\/(.+)$/.exec(p);
    if (c) {
      const key = c[1];
      const sh =
        key === 'actions/checkout'
          ? N.co
          : key === 'actions/upload-artifact'
            ? N.ua
            : key === 'actions/cache'
              ? N.cache
              : key === 'bitwarden/sm-action'
                ? N.bw
                : sha('e');
      return { sha: sh };
    }
    throw new Error(`stub: unexpected ${p}`);
  };
}
const SETTLED: Record<string, Latest> = {
  'actions/checkout': { tag: 'v1.0.2', at: OLD },
  'actions/upload-artifact': { tag: 'v7.0.3', at: OLD },
  'actions/cache': { tag: 'v6.1.1', at: OLD },
  'docker/setup-buildx-action': { tag: 'v4.2.0', at: OLD },
  'bitwarden/sm-action': { tag: 'v3.0.2', at: OLD },
};

async function actionsCases(
  mutant?: T8Mutant
): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('actions');

  // A settled bump: every pin, the constant, the allowlist, the regions.
  {
    const root = actionsTree();
    const d = deps({ github: ghLatest(SETTLED) });
    const drv = actionsDriver(() => d.deps, mutant);
    const ctx = ctxOf(root);
    const insp = await drv.inspect(e, ctx);
    const rel = insp.releases[0];
    const plan = rel ? await drv.plan(e, rel, ctx) : null;
    const w = plan ? written(plan) : {};
    const a = w['.:.github/workflows/ci-a.yml'] ?? '';
    out.push({
      name: 'actions: a settled release plans one group that stands for checkout, upload-artifact, cache and sm-action',
      ok: insp.releases.length === 1 && rel.version === '1.4' && rel.publishedMs === OLD,
      detail: JSON.stringify(insp),
    });
    out.push({
      name: 'actions: every `uses:` moves, sub-path actions with their repository, spacing and `# v` style kept',
      ok:
        a.includes(`actions/checkout@${N.co} # v1.0.2`) &&
        a.includes(`actions/upload-artifact@${N.ua}  # v7.0.3`) &&
        a.includes(`actions/cache/restore@${N.cache} # v6.1.1`) &&
        a.includes(`actions/cache/save@${N.cache} # v6.1.1`) &&
        (w['.:.github/workflows/ci-b.yml'] ?? '').includes(
          `actions/upload-artifact@${N.ua} # v7.0.3`
        ) &&
        (w['.:.github/actions/x/action.yml'] ?? '').includes(`${N.co} # v1.0.2`) &&
        (w['.:.ci/breakpoint/workflow/breakpoint.yml'] ?? '').includes(`${N.co} # v1.0.2`),
      detail: a,
    });
    out.push({
      name: 'actions: a floating `# v4` pin that is current stays, and a blocklisted action is not touched',
      ok:
        a.includes(`docker/setup-buildx-action@${S.bx}  # v4`) &&
        a.includes(`blocked/thing@${S.bl} # v1.0.0`) &&
        a.includes('uses: ./local'),
    });
    out.push({
      name: 'actions: UPLOAD_ARTIFACT_PIN moves with the uses (sha and version comment), or the next gate-bind --write reverts the bump',
      ok: (w['.:scripts/gate-bind.ts'] ?? '').includes(
        `'actions/upload-artifact@${N.ua}  # v7.0.3'`
      ),
      detail: w['.:scripts/gate-bind.ts'],
    });
    out.push({
      name: 'actions: the allowlist @sha pattern moves, and the plan says the repository setting needs a refresh',
      ok:
        (w['.:.ci/config/actions-allowlist.json'] ?? '').includes(
          `"bitwarden/sm-action@${N.bw}"`
        ) && (plan?.changes ?? []).some((c) => c.includes('REFRESH')),
      detail: JSON.stringify(plan?.changes),
    });
    const step = plan?.steps[0];
    out.push({
      name: 'actions: gate-bind --write is a derive step declaring the workflows it may regenerate',
      ok:
        step?.run === 'npx tsx scripts/gate-bind.ts --write' &&
        step.writes.some((x) => x.file === '.github/workflows/ci-a.yml'),
      detail: JSON.stringify(plan?.steps),
    });
  }

  // Inside the window: deferred, not eligible.
  {
    const root = actionsTree();
    const fresh = { ...SETTLED, 'actions/upload-artifact': { tag: 'v7.0.3', at: FRESH } };
    const drv = actionsDriver(() => deps({ github: ghLatest(fresh) }).deps, mutant);
    const insp = await drv.inspect(entry('actions'), ctxOf(root));
    const versions = insp.releases.map((r) => `${r.version}@${r.publishedMs}`);
    out.push({
      name: 'actions: a release inside the window is its own deferred group, the settled ones still go (deferred first)',
      ok:
        insp.releases.length === 2 &&
        insp.releases[0].publishedMs === FRESH &&
        insp.releases[1].publishedMs === OLD &&
        insp.releases[1].version === '1.3',
      detail: versions.join(' '),
    });
  }

  // A major move is a group of its own, and a pin with no version comment is not compared.
  {
    const root = actionsTree();
    const drv = actionsDriver(
      () =>
        deps({ github: ghLatest({ ...SETTLED, 'actions/checkout': { tag: 'v2.0.0', at: OLD } }) })
          .deps,
      mutant
    );
    const insp = await drv.inspect(entry('actions'), ctxOf(root));
    out.push({
      name: 'actions: a major move is the 2.n group, never mixed into the in-range one',
      ok:
        insp.releases.some((r) => r.version === '2.1') &&
        insp.releases.some((r) => r.version === '1.3'),
      detail: JSON.stringify(insp.releases),
    });
    const bare = actionsTree({
      '.github/workflows/ci-c.yml': `steps:\n  - uses: actions/setup-go@${sha('9')}\n`,
    });
    const err = await rejects(
      actionsDriver(() => deps({ github: ghLatest(SETTLED) }).deps, mutant).inspect(
        entry('actions'),
        ctxOf(bare)
      )
    );
    out.push({
      name: 'actions: a pin with no version comment is refused by name, not skipped',
      ok:
        !!err &&
        err.message.includes('actions/setup-go') &&
        err.message.includes('no version comment'),
      detail: String(err),
    });
  }

  // An upstream that did not answer, and a site that drifted.
  {
    const root = actionsTree();
    const bad = actionsDriver(
      () =>
        deps({
          github: () => {
            throw new Error('UPSTREAM REACHABILITY FAILURE');
          },
        }).deps,
      mutant
    );
    const err = await rejects(bad.inspect(entry('actions'), ctxOf(root)));
    out.push({
      name: 'actions: an upstream that did not answer is not compared (fail closed)',
      ok: !!err && err.message.includes('UPSTREAM'),
      detail: String(err),
    });

    const drift = actionsTree({
      'scripts/gate-bind.ts': `export const UPLOAD_ARTIFACT_PIN = 'something else';\n`,
    });
    const drv = actionsDriver(() => deps({ github: ghLatest(SETTLED) }).deps, mutant);
    const ctx = ctxOf(drift);
    const insp = await drv.inspect(entry('actions'), ctx);
    const err2 = await rejects(drv.plan(entry('actions'), insp.releases[0], ctx));
    out.push({
      name: 'actions: a registry site that no longer matches refuses the whole pin, writing nothing',
      ok:
        err2 instanceof PlanRefused &&
        err2.message.includes('gate-bind.ts') &&
        err2.message.includes('nothing is written'),
      detail: String(err2),
    });

    const badSha = actionsDriver(
      () =>
        deps({
          github: (p) => (p.includes('/commits/') ? { sha: 'abc' } : ghLatest(SETTLED)(p)),
        }).deps,
      mutant
    );
    const ctx3 = ctxOf(root);
    const i3 = await badSha.inspect(entry('actions'), ctx3);
    const err3 = await rejects(badSha.plan(entry('actions'), i3.releases[0], ctx3));
    out.push({
      name: 'actions: a tag that does not resolve to a 40-digit SHA is refused',
      ok: err3 instanceof PlanRefused,
      detail: String(err3),
    });
  }
  return out;
}

// ---- go-mod ---------------------------------------------------------------------------------

function goDoc(records: unknown[], extra: Record<string, unknown> = {}): string {
  return JSON.stringify({
    dirs: [{ dir: 'private/renet', records }],
    unanswered: [],
    probeFailures: [],
    ...extra,
  });
}
const rec = (module: string, current: string, latest: string, kind: string, at: number | null) => ({
  module,
  current,
  latest,
  kind,
  published: at === null ? null : Math.floor(at / 1000),
});

async function goCases(
  mutant?: T8Mutant
): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('go-mod');
  const root = tree({});
  const ctx = ctxOf(root);
  const doc = goDoc([
    rec('golang.org/x/net', 'v0.50.0', 'v0.51.0', 'minor', OLD),
    rec('github.com/spf13/cobra', 'v1.9.0', 'v1.10.0', 'minor', OLD + DAY),
    rec('google.golang.org/grpc', 'v1.83.2', 'v1.84.0', 'blocked', null),
    rec('golang.org/x/crypto', 'v0.57.0', 'v0.58.0', 'vulnerable:GO-2026-5932', OLD),
    rec('github.com/foo/bar', 'v0.9.0', 'v1.0.0', 'major', OLD),
    rec('github.com/new/mod', 'v0.1.0', 'v0.2.0', 'toofresh', FRESH),
  ]);
  const d = deps({ run: () => ({ rc: 0, out: doc }) });
  const drv = gomodDriver(() => d.deps, mutant);
  const insp = await drv.inspect(e, ctx);
  const by = (v: string) => insp.releases.find((r) => r.version === v);
  out.push({
    name: 'go-mod: the gate probe splits into the in-range group, the deferred group and the refused major; blocked and vulnerable modules are in none',
    ok:
      insp.releases.length === 3 &&
      by('1.2')?.publishedMs === OLD + DAY &&
      by('1.3')?.publishedMs === FRESH &&
      by('2.1')?.verdict?.eligible === false,
    detail: JSON.stringify(insp),
  });
  const plan = await drv.plan(e, by('1.2') as NonNullable<ReturnType<typeof by>>, ctx);
  const runs = plan.steps.map((s) => `${s.cwd}: ${s.run}`);
  out.push({
    name: 'go-mod: one go get for the group, go mod tidy in renet, then license-mint tidied against it',
    ok:
      runs[0] ===
        "private/renet: go get 'golang.org/x/net@v0.51.0' 'github.com/spf13/cobra@v1.10.0'" &&
      runs[1] === 'private/renet: go mod tidy' &&
      runs[2] === '.ci/scripts/private/license-mint: go mod tidy' &&
      plan.steps.every(
        (s) => s.writes.length === 2 && s.writes.every((w) => /go\.(mod|sum)$/.test(w.file))
      ),
    detail: runs.join('\n'),
  });
  out.push({
    name: 'go-mod: blocked, vulnerable and major modules are not in the go get',
    ok: !runs[0].includes('grpc') && !runs[0].includes('crypto') && !runs[0].includes('foo/bar'),
    detail: runs[0],
  });
  const err = await rejects(drv.plan(e, by('2.1') as NonNullable<ReturnType<typeof by>>, ctx));
  out.push({
    name: 'go-mod: a Go major is refused with its message (--major cannot take it)',
    ok:
      err instanceof PlanRefused &&
      err.message.includes('a Go major move is refused') &&
      err.message.includes('github.com/foo/bar v0.9.0 -> v1.0.0'),
    detail: String(err),
  });
  const fail = gomodDriver(
    () =>
      deps({
        run: () => ({
          rc: 0,
          out: goDoc([], { probeFailures: ['renet: __PROBE_FAILED__ go-list exit=1'] }),
        }),
      }).deps,
    mutant
  );
  const e2 = await rejects(fail.inspect(e, ctx));
  out.push({
    name: 'go-mod: a probe that could not run is not "nothing to bump"',
    ok: !!e2 && e2.message.includes('probe failed'),
    detail: String(e2),
  });
  const unans = gomodDriver(
    () =>
      deps({
        run: () => ({
          rc: 0,
          out: goDoc([], { unanswered: ['renet: x unanswered:proxy.golang.org'] }),
        }),
      }).deps,
    mutant
  );
  const e3 = await rejects(unans.inspect(e, ctx));
  out.push({
    name: 'go-mod: an upstream that did not answer is not compared',
    ok: !!e3 && e3.message.includes('UPSTREAM REACHABILITY'),
    detail: String(e3),
  });
  const stray = gomodDriver(
    () =>
      deps({
        run: () => ({
          rc: 0,
          out: JSON.stringify({
            dirs: [{ dir: 'private/other', records: [] }],
            unanswered: [],
            probeFailures: [],
          }),
        }),
      }).deps,
    mutant
  );
  const e4 = await rejects(stray.inspect(e, ctx));
  out.push({
    name: 'go-mod: a Go directory outside the registry scope is refused by name',
    ok: !!e4 && e4.message.includes('private/other'),
    detail: String(e4),
  });
  return out;
}

// ---- os-ceph-host and ceph-image ------------------------------------------------------------

const PIN_FILE = (evr: string, extra = '') =>
  `image=${WK_CEPH_IMAGE_REPO}:v19.2.3-20250717\nhost-version=19.2.3\nreview=2026-11-18\nhost.ubuntu=19.2.3-0ubuntu0.24.04.3\nhost.opensuse-16.0=${evr}\n${extra}`;
function leapTree(evr = '19.2.3-lp160.4.1', over: Record<string, string> = {}): string {
  return tree({
    'private/renet/.ceph-image-pin': PIN_FILE(evr),
    'private/renet/pkg/infra/cephpkg/cephpkg.go': `var hostPins = map[string]string{\n\t"opensuse-16.0": "${evr}",\n}\n`,
    'private/renet/cmd/renet/ceph_install_profile_test.go': `want := "zypper -n install --no-recommends ceph-common=${evr}"\n`,
    ...over,
  });
}
const obs = (evr: string, tag: 'present' | 'absent' | 'error') => (cmd: string) => {
  if (cmd.endsWith('upstream')) return { rc: 0, out: `obs_evr=${evr}\npin=x\n` };
  if (cmd.includes('mirror-tag'))
    return tag === 'error'
      ? { rc: 1, out: '::error::obs_mirror: oras manifest fetch failed (rc=1): denied' }
      : { rc: 0, out: `mirror_tag=${tag}\n` };
  return { rc: 127, out: 'no stub' };
};

async function osCases(
  mutant?: T8Mutant
): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('os:opensuse-16.0-ceph');
  const NEW = '19.2.3-lp160.4.2';
  {
    const root = leapTree();
    const ctx = ctxOf(root);
    const drv = osCephHostDriver(() => deps({ run: obs(NEW, 'present') }).deps, mutant);
    const insp = await drv.inspect(e, ctx);
    const plan = await drv.plan(e, insp.releases[0], ctx);
    const w = written(plan);
    out.push({
      name: 'os:leap: the same series with the mirror tag present is eligible with no soak, and the three sites move together',
      ok:
        insp.releases[0]?.verdict?.eligible === true &&
        insp.releases[0].publishedMs === null &&
        Object.keys(w).length === 3 &&
        Object.values(w).every((t) => t?.includes(NEW) === true && !t.includes('lp160.4.1')),
      detail: JSON.stringify(insp) + Object.keys(w).join(','),
    });
  }
  {
    const ctx = ctxOf(leapTree());
    const drv = osCephHostDriver(() => deps({ run: obs(NEW, 'absent') }).deps, mutant);
    const insp = await drv.inspect(e, ctx);
    const err = await rejects(drv.plan(e, insp.releases[0], ctx));
    out.push({
      name: 'os:leap: an EVR with no obs-mirror tag is refused, naming the ci-obs-mirror dispatch',
      ok:
        insp.releases[0]?.verdict?.eligible === false &&
        err instanceof PlanRefused &&
        err.message.includes('ci-obs-mirror'),
      detail: JSON.stringify(insp) + String(err),
    });
  }
  {
    const ctx = ctxOf(leapTree());
    const d = deps({ run: obs('20.1.0-lp160.1.1', 'present') });
    const drv = osCephHostDriver(() => d.deps, mutant);
    const insp = await drv.inspect(e, ctx);
    const err = await rejects(drv.plan(e, insp.releases[0], ctx));
    out.push({
      name: 'os:leap: an upstream version that differs from host-version is refused, and the mirror is not even asked',
      ok:
        insp.releases[0]?.verdict?.eligible === false &&
        err instanceof PlanRefused &&
        !d.cmds.some((c) => c.includes('mirror-tag')),
      detail: JSON.stringify(insp) + d.cmds.join('|'),
    });
  }
  {
    const withOverride = (reason: boolean) =>
      ctxOf(
        tree({
          'private/renet/.ceph-image-pin': `${PIN_FILE('19.2.3-lp160.4.1')}host-version.opensuse-16.0=20.1.0\n${reason ? 'host-version-reason.opensuse-16.0=ruling\n' : ''}`,
          'private/renet/pkg/infra/cephpkg/cephpkg.go': `var hostPins = map[string]string{\n\t"opensuse-16.0": "19.2.3-lp160.4.1",\n}\n`,
          'private/renet/cmd/renet/ceph_install_profile_test.go': `want := "zypper -n install --no-recommends ceph-common=19.2.3-lp160.4.1"\n`,
        })
      );
    const ok = await osCephHostDriver(
      () => deps({ run: obs('20.1.0-lp160.1.1', 'present') }).deps,
      mutant
    ).inspect(e, withOverride(true));
    const noReason = await osCephHostDriver(
      () => deps({ run: obs('20.1.0-lp160.1.1', 'present') }).deps,
      mutant
    ).inspect(e, withOverride(false));
    out.push({
      name: 'os:leap: a host-version.opensuse-16.0 override with a reason admits that series; without a reason it is ignored',
      ok:
        ok.releases[0]?.verdict?.eligible === true &&
        noReason.releases[0]?.verdict?.eligible === false,
      detail: JSON.stringify([ok, noReason]),
    });
  }
  {
    const ctx = ctxOf(leapTree());
    const same = await osCephHostDriver(
      () => deps({ run: obs('19.2.3-lp160.4.1', 'present') }).deps,
      mutant
    ).inspect(e, ctx);
    out.push({
      name: 'os:leap: OBS serving the pinned EVR is current',
      ok: same.releases.length === 0,
    });
    const err = await rejects(
      osCephHostDriver(() => deps({ run: obs(NEW, 'error') }).deps, mutant).inspect(e, ctx)
    );
    out.push({
      name: 'os:leap: a mirror probe that fails is not "absent": the pin is not compared',
      ok: !!err && err.message.includes('could not probe'),
      detail: String(err),
    });
    const down = await rejects(
      osCephHostDriver(
        () => deps({ run: () => ({ rc: 1, out: 'URLError' }) }).deps,
        mutant
      ).inspect(e, ctx)
    );
    out.push({
      name: 'os:leap: an OBS origin that cannot be read is not compared',
      ok: !!down && down.message.includes('could not read the OBS origin'),
      detail: String(down),
    });
    const ub = await rejects(
      osCephHostDriver(() => deps({ run: obs(NEW, 'present') }).deps, mutant).inspect(
        entry('os:ubuntu-ceph'),
        ctx
      )
    );
    out.push({
      name: 'os:ubuntu: a host with no source reads its BLOCKER reason, never a bump',
      ok: !!ub && ub.message.startsWith('BLOCKER:'),
      detail: String(ub),
    });
  }
  {
    const root = leapTree('19.2.3-lp160.4.1', {
      'private/renet/cmd/renet/ceph_install_profile_test.go': 'nothing here\n',
    });
    const ctx = ctxOf(root);
    const drv = osCephHostDriver(() => deps({ run: obs(NEW, 'present') }).deps, mutant);
    const insp = await drv.inspect(e, ctx);
    const err = await rejects(drv.plan(e, insp.releases[0], ctx));
    out.push({
      name: 'os:leap: a site that does not match leaves all three files alone (the whole pin is refused)',
      ok: err instanceof PlanRefused && err.message.includes('matches 0 time(s)'),
      detail: String(err),
    });
  }
  return out;
}

const quay = (tags: [string, number][]) => () => ({
  tags: tags.map(([name, ts]) => ({ name, start_ts: Math.floor(ts / 1000) })),
  has_additional: false,
});
async function cephImageCases(
  mutant?: T8Mutant
): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('ceph-image');
  const root = tree({
    'private/renet/.ceph-image-pin': PIN_FILE('19.2.3-lp160.4.1'),
    'private/renet/pkg/infra/ceph/provisioner.go': `const CephImagePin = "${WK_CEPH_IMAGE_REPO}:v19.2.3-20250717"\n`,
  });
  const ctx = ctxOf(root);
  const tags: [string, number][] = [
    ['v19.2.3-20260301', OLD],
    ['v19.2.3-20260601', OLD + DAY],
    ['v19.2.3-20261014', FRESH],
    ['v19.2.6-20260801', OLD],
    ['v19.2.3-20250101', OLD],
    ['v19.2.3', OLD],
    ['v19', OLD],
  ];
  const drv = cephImageDriver(() => deps({ json: quay(tags) }).deps, mutant);
  const insp = await drv.inspect(e, ctx);
  out.push({
    name: 'ceph-image: only dated tags of the same host-version newer than the pin are candidates, newest first',
    ok:
      insp.releases.map((r) => r.version).join(',') ===
      'v19.2.3-20261014,v19.2.3-20260601,v19.2.3-20260301',
    detail: JSON.stringify(insp.releases.map((r) => r.version)),
  });
  out.push({
    name: 'ceph-image: a tag inside the release-age window is not eligible, a settled one is',
    ok: insp.releases[0].verdict?.eligible === false && insp.releases[1].verdict?.eligible === true,
  });
  const plan = await drv.plan(e, insp.releases[1], ctx);
  const w = written(plan);
  const pin = w['private/renet:.ceph-image-pin'] ?? '';
  out.push({
    name: 'ceph-image: a bump moves image= and CephImagePin, keeps host-version=, and sets review= ninety days out',
    ok:
      pin.includes(`image=${WK_CEPH_IMAGE_REPO}:v19.2.3-20260601`) &&
      pin.includes('host-version=19.2.3') &&
      pin.includes('review=2027-01-12') &&
      (w['private/renet:pkg/infra/ceph/provisioner.go'] ?? '').includes('v19.2.3-20260601'),
    detail: pin,
  });
  const err = await rejects(drv.plan(e, insp.releases[0], ctx));
  out.push({
    name: 'ceph-image: a deferred tag is refused at plan too',
    ok: err instanceof PlanRefused,
    detail: String(err),
  });
  return out;
}

// ---- real-provider and docker ---------------------------------------------------------------

async function realProviderCases(): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('real-provider:bitwarden');
  const root = tree({
    'private/account/e2e/real-provider.lock.json': `${JSON.stringify({ bitwarden: { version: '2026.9.3', sha256: 'x' } }, null, 2)}\n`,
  });
  const ctx = ctxOf(root);
  const rel = (tag: string, extra: Record<string, unknown> = {}) => ({
    tag_name: tag,
    published_at: iso(OLD),
    ...extra,
  });
  const drv = realProviderDriver(
    () =>
      deps({
        github: () => [
          rel('browser-v2026.10.0'),
          rel('browser-v2026.9.4'),
          rel('browser-v2026.11.0', { prerelease: true }),
          rel('cli-v2027.1.0'),
          rel('browser-v2026.9.3'),
        ],
      }).deps
  );
  const insp = await drv.inspect(e, ctx);
  out.push({
    name: 'real-provider: published browser-v releases newer than the pin, newest first; pre-releases and other products are skipped',
    ok: insp.releases.map((r) => r.version).join(',') === '2026.10.0,2026.9.4',
    detail: JSON.stringify(insp),
  });
  const plan = await drv.plan(e, insp.releases[0], ctx);
  out.push({
    name: 'real-provider: the plan is the wrapped bump script, writing only the lock, and says it needs live verification',
    ok:
      plan.writes.length === 0 &&
      plan.steps[0].run === 'npm run real-provider:bump -- --bitwarden 2026.10.0' &&
      plan.steps[0].cwd === 'private/account/e2e' &&
      plan.steps[0].writes.length === 1 &&
      plan.changes[0].includes('NEEDS LIVE VERIFICATION'),
    detail: JSON.stringify(plan),
  });
  return out;
}

async function dockerCases(
  mutant?: T8Mutant
): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  const out: Array<{ name: string; ok: boolean; detail?: string }> = [];
  const e = entry('image:ci-node');
  const root = tree({
    '.ci/docker/render/Dockerfile': 'FROM node:24-bookworm-slim\n',
    '.ci/docker/web/Dockerfile': 'FROM node:24-bookworm-slim\n',
    'scripts/data/docker-image-freshness-baseline.json':
      '[\n  "node:24-bookworm-slim",\n  "ubuntu:24.04"\n]\n',
  });
  const ctx = ctxOf(root);
  const hub = () => ({
    results: [
      { name: '26-bookworm-slim', last_updated: iso(OLD) },
      { name: '25-bookworm-slim', last_updated: iso(OLD) },
      { name: '24-bookworm-slim', last_updated: iso(OLD) },
      { name: '26.1.0-bookworm-slim', last_updated: iso(OLD) },
      { name: '26-slim', last_updated: iso(OLD) },
      { name: '26-alpine', last_updated: iso(OLD) },
    ],
    next: null,
  });
  const drv = dockerDriver(() => deps({ json: hub }).deps, mutant);
  const insp = await drv.inspect(e, ctx);
  out.push({
    name: "docker: candidates have the pin's shape (suffix and component count) and are newer, labelled so the core reads them as a major",
    ok:
      insp.current === 'node:24-bookworm-slim' &&
      insp.releases.map((r) => r.version).join(',') ===
        'node:26-bookworm-slim,node:25-bookworm-slim',
    detail: JSON.stringify(insp),
  });
  const plan = await drv.plan(e, insp.releases[0], ctx);
  const w = written(plan);
  out.push({
    name: 'docker: both FROM sites move, and the baseline drain step is planned because the old tag is listed',
    ok:
      (w['.:.ci/docker/render/Dockerfile'] ?? '').includes('FROM node:26-bookworm-slim') &&
      (w['.:.ci/docker/web/Dockerfile'] ?? '').includes('FROM node:26-bookworm-slim') &&
      plan.steps[0]?.run.endsWith('--write-baseline') &&
      plan.steps[0].writes[0].file === 'scripts/data/docker-image-freshness-baseline.json',
    detail: JSON.stringify(plan.steps),
  });
  const unlisted = tree({
    '.ci/docker/render/Dockerfile': 'FROM node:24-bookworm-slim\n',
    '.ci/docker/web/Dockerfile': 'FROM node:24-bookworm-slim\n',
    'scripts/data/docker-image-freshness-baseline.json': '[\n  "ubuntu:24.04"\n]\n',
  });
  const c2 = ctxOf(unlisted);
  const p2 = await drv.plan(e, (await drv.inspect(e, c2)).releases[0], c2);
  out.push({
    name: 'docker: a pin that is not in the baseline plans no drain',
    ok: p2.steps.length === 0,
  });
  const fam = await dockerDriver(() => deps({}).deps, mutant).inspect(entry('docker'), ctx);
  out.push({
    name: 'docker: the family entry has nothing to bump itself',
    ok: fam.releases.length === 0,
  });
  const nosrc = await rejects(
    dockerDriver(() => deps({}).deps, mutant).inspect(entry('image:devcontainer-base'), ctx)
  );
  out.push({
    name: 'docker: a leaf with no source reads its BLOCKER reason',
    ok: !!nosrc && nosrc.message.startsWith('BLOCKER:'),
    detail: String(nosrc),
  });

  // A leaf spanning an ARG default and six FROM stages in two submodule files: one bump moves all eight lines.
  const ub = entry('image:renet-ubuntu');
  const stages = ['rsync-builder', 'zot-downloader', 'k3s-downloader'].flatMap((n) => [
    `FROM ubuntu:24.04 AS ${n}-amd64`,
    `FROM ubuntu:24.04 AS ${n}-arm64`,
  ]);
  const renet = tree({
    'private/renet/Dockerfile': `ARG TARGET_IMAGE=ubuntu:24.04\nFROM debian:bookworm AS criu-source\n${stages.join('\n')}\nFROM $TARGET_IMAGE\n`,
    'private/renet/Dockerfile.native': `ARG BASE_IMAGE=ubuntu:24.04\nFROM $BASE_IMAGE\n`,
    'scripts/data/docker-image-freshness-baseline.json': '[\n  "ubuntu:24.04"\n]\n',
  });
  const cu = ctxOf(renet);
  // Docker Hub's answer, measured shape (2026-10-14): `26.04` re-pushed last week with an id from
  // late 2025, a never-re-pushed dated codename tag created after it, and 26.10 pushed last month.
  const ubHub = () => ({
    results: [
      { name: '26.04', id: 1010, last_updated: iso(NOW - 10 * DAY) },
      { name: '26.10', id: 1204, last_updated: iso(NOW - 26 * DAY) },
      { name: 'resolute-20260106', id: 1049, last_updated: iso(NOW - 268 * DAY) },
      { name: '24.04', id: 500, last_updated: iso(NOW - 10 * DAY) },
    ],
    next: null,
  });
  const ui = await dockerDriver(() => deps({ json: ubHub }).deps, mutant).inspect(ub, cu);
  const up = await dockerDriver(() => deps({ json: ubHub }).deps, mutant).plan(
    ub,
    ui.releases.find((r) => r.version === 'ubuntu:26.04') as (typeof ui.releases)[number],
    cu
  );
  const uw = written(up);
  out.push({
    name: 'docker: a leaf with an ARG site and six FROM stages in two submodule files moves every line, and leaves debian alone',
    ok:
      (uw['private/renet:Dockerfile'] ?? '').split('ubuntu:26.04').length - 1 === 7 &&
      !(uw['private/renet:Dockerfile'] ?? '').includes('ubuntu:24.04') &&
      (uw['private/renet:Dockerfile'] ?? '').includes('FROM debian:bookworm AS criu-source') &&
      (uw['private/renet:Dockerfile.native'] ?? '').includes('ARG BASE_IMAGE=ubuntu:26.04') &&
      up.steps[0]?.run.endsWith('--write-baseline'),
    detail: JSON.stringify(uw),
  });
  const line26 = ui.releases.map((r) => (r as { lineFirstMs?: number | null }).lineFirstMs);
  out.push({
    name: "docker: a re-pushed tag's line is dated by the oldest push among tags created after the line began, not by its own stamp",
    ok: line26.length === 2 && line26.every((ms) => ms === NOW - 268 * DAY),
    detail: JSON.stringify(ui.releases),
  });
  // CONTROL, the other direction: a line that genuinely began last week reads last week.
  const fresh = await dockerDriver(
    () =>
      deps({
        json: () => ({
          results: [
            { name: '27.04', id: 2000, last_updated: iso(NOW - 6 * DAY) },
            { name: 'resolute-20260106', id: 1049, last_updated: iso(NOW - 268 * DAY) },
          ],
          next: null,
        }),
      }).deps,
    mutant
  ).inspect(ub, cu);
  out.push({
    name: 'docker: CONTROL a line whose first tag is a week old is dated a week old, older tags created before it are no evidence',
    ok:
      (fresh.releases[0] as { lineFirstMs?: number | null } | undefined)?.lineFirstMs ===
      NOW - 6 * DAY,
    detail: JSON.stringify(fresh.releases),
  });

  // THE DIGEST MOVES WITH THE TAG (#d4b2a051): a FROM pinned by tag AND index digest gets both rewritten.
  const pn = entry('image:proxy-node');
  const dA = `sha256:${'a'.repeat(64)}`;
  const dB = `sha256:${'b'.repeat(64)}`;
  const dC = `sha256:${'c'.repeat(64)}`;
  const proxyTree = () =>
    tree({
      'workers/proxy/Dockerfile': `FROM node:26.12.0-slim AS build\nFROM node:26.12.0-slim@${dA}\nCMD ["node"]\n`,
      'scripts/data/docker-image-freshness-baseline.json': '[]\n',
    });
  const listing = {
    results: [
      { name: '26.13.0-slim', last_updated: iso(OLD) },
      { name: '26.12.0-slim', last_updated: iso(OLD) },
    ],
    next: null,
  };
  const pnHub =
    (tagAnswer: () => unknown): ((u: string) => unknown) =>
    (u) =>
      u.includes('/tags/26.13.0-slim')
        ? tagAnswer()
        : u.includes('/tags/26.12.0-slim')
          ? { digest: dA, tag_last_pushed: iso(OLD) }
          : listing;
  const pc = ctxOf(proxyTree());
  const pd = dockerDriver(
    () => deps({ json: pnHub(() => ({ digest: dB, images: [{ digest: dC }] })) }).deps,
    mutant
  );
  const pi = await pd.inspect(pn, pc);
  const target = pi.releases.find((r) => r.version === 'node:26.13.0-slim');
  out.push({
    name: 'docker: CONTROL a pinned tag whose digest matches what Hub serves offers no re-digest, only the newer tag',
    ok: pi.releases.map((r) => r.version).join(',') === 'node:26.13.0-slim',
    detail: JSON.stringify(pi.releases),
  });
  const pp = target ? await pd.plan(pn, target, pc).catch(() => null) : null;
  const pw = pp ? (written(pp)['.:workers/proxy/Dockerfile'] ?? '') : '';
  out.push({
    name: "docker: a tag+digest FROM moves both: the tag to the target and the digest to Hub's top-level index digest for it, never images[] and never the old one",
    ok:
      pw.split('\n')[1] === `FROM node:26.13.0-slim@${dB}` &&
      pw.split('\n')[0] === 'FROM node:26.12.0-slim AS build' &&
      (pp?.changes ?? []).some((c) => c.includes('digest')),
    detail: JSON.stringify({ pw, changes: pp?.changes }),
  });
  const noDigest: [string, () => unknown][] = [
    ['no digest at all', () => ({ name: '26.13.0-slim' })],
    ['an images[]-only digest', () => ({ images: [{ digest: dC }] })],
    ['a malformed digest', () => ({ digest: 'sha256:abc' })],
    [
      'a failed lookup',
      () => {
        throw new Error('HTTP 429');
      },
    ],
  ];
  for (const [why, answer] of noDigest) {
    const err = target
      ? await rejects(
          dockerDriver(() => deps({ json: pnHub(answer) }).deps, mutant).plan(
            pn,
            target,
            ctxOf(proxyTree())
          )
        )
      : null;
    out.push({
      name: `docker: Hub answering ${why} for the target tag refuses the whole plan, naming the tag`,
      ok: err instanceof PlanRefused && err.message.includes('node:26.13.0-slim'),
      detail: String(err),
    });
  }
  const versionOnly: PinEntry = { ...pn, sites: pn.sites.filter((x) => x.role === 'version') };
  const gap = target
    ? await rejects(
        dockerDriver(() => deps({ json: pnHub(() => ({ digest: dB })) }).deps, mutant).plan(
          versionOnly,
          target,
          ctxOf(proxyTree())
        )
      )
    : null;
  out.push({
    name: 'docker: a version site whose line carries @sha256: in an entry with no digest site is refused, so a registry gap cannot keep the old digest',
    ok: gap instanceof PlanRefused && gap.message.includes('workers/proxy/Dockerfile:2'),
    detail: String(gap),
  });

  // THE RE-DIGEST: the tag is Hub's newest, and Hub re-pushed it, so the digest beside it is stale.
  const rdTree = () =>
    tree({
      'workers/proxy/Dockerfile': `FROM node:26.13.0-slim AS build\nFROM node:26.13.0-slim@${dA}\nCMD ["node"]\n`,
      'scripts/data/docker-image-freshness-baseline.json': '[\n  "node:26.13.0-slim"\n]\n',
    });
  const rdHub =
    (served: string, pushed = OLD): ((u: string) => unknown) =>
    (u) =>
      u.includes('/tags/26.13.0-slim')
        ? { digest: served, tag_last_pushed: iso(pushed), images: [{ digest: dC }] }
        : { results: [{ name: '26.13.0-slim', last_updated: iso(pushed) }], next: null };
  const rdLabel = `node:26.13.0-slim@${'b'.repeat(12)}`;
  const rc = ctxOf(rdTree());
  const rd = dockerDriver(() => deps({ json: rdHub(dB) }).deps, mutant);
  const ri = await rd.inspect(pn, rc);
  const redig = ri.releases.find((r) => r.version === rdLabel);
  out.push({
    name: 'docker: a pinned tag Hub re-pushed with another index digest is offered again as a re-digest, eligible once past the window, on the same major line',
    ok:
      ri.current === 'node:26.13.0-slim' &&
      ri.releases.length === 1 &&
      redig?.verdict?.eligible === true &&
      majorLineOf(rdLabel) === 26,
    detail: JSON.stringify(ri),
  });
  const rp = redig ? await rd.plan(pn, redig, rc).catch((e: Error) => e) : null;
  const rw = rp && !(rp instanceof Error) ? (written(rp)['.:workers/proxy/Dockerfile'] ?? '') : '';
  out.push({
    name: 'docker: a re-digest rewrites the digest alone: the tag and every other line unchanged, no version change named, no baseline drain',
    ok:
      rw === `FROM node:26.13.0-slim AS build\nFROM node:26.13.0-slim@${dB}\nCMD ["node"]\n` &&
      !(rp instanceof Error) &&
      rp?.changes.length === 1 &&
      rp.changes[0].includes('digest') &&
      rp.steps.length === 0,
    detail: JSON.stringify(
      rp instanceof Error ? String(rp) : { rw, changes: rp?.changes, steps: rp?.steps }
    ),
  });
  const same = await dockerDriver(() => deps({ json: rdHub(dA) }).deps, mutant).inspect(
    pn,
    ctxOf(rdTree())
  );
  out.push({
    name: 'docker: CONTROL a pinned tag whose digest matches is current, with no candidate',
    ok: same.releases.length === 0,
    detail: JSON.stringify(same.releases),
  });
  const again = redig
    ? await rejects(
        dockerDriver(() => deps({ json: rdHub(dC) }).deps, mutant).plan(pn, redig, ctxOf(rdTree()))
      )
    : null;
  out.push({
    name: 'docker: a re-digest label whose digest Hub has since moved again is refused, naming the status command',
    ok: again instanceof PlanRefused && again.message.includes('pins -- status image:proxy-node'),
    detail: String(again),
  });
  const freshRd = await dockerDriver(() => deps({ json: rdHub(dB, FRESH) }).deps, mutant).inspect(
    pn,
    ctxOf(rdTree())
  );
  out.push({
    name: 'docker: a re-push inside the release-age window is offered but not eligible',
    ok: freshRd.releases.length === 1 && freshRd.releases[0].verdict?.eligible === false,
    detail: JSON.stringify(freshRd.releases),
  });
  return out;
}

// ---- the run --------------------------------------------------------------------------------

function biomeSchemaCases(): Array<{ name: string; ok: boolean; detail?: string }> {
  const doc = (v: string): string =>
    `{\n  "$schema": "https://biomejs.dev/schemas/${v}/schema.json",\n  "vcs": { "enabled": true }\n}\n`;
  const step = (name: string, latest: string) => [{ packages: [{ name, latest }] }];
  const bumped = planBiomeSchema(doc('2.6.2'), step('@biomejs/biome', '2.6.3'));
  const other = planBiomeSchema(doc('2.6.2'), step('typescript', '6.0.1'));
  const same = planBiomeSchema(doc('2.6.3'), step('@biomejs/biome', '2.6.3'));
  // The wiring of stepsOf: the biome.json read, the write pushed into `writes`, and the note.
  const root = tree({ 'biome.json': doc('2.6.2'), 'package.json': '{}' });
  const wired = (name: string, latest: string) =>
    stepsOf(
      ctxOf(root),
      entry('npm'),
      [
        {
          cwd: root,
          args: ['install', `${name}@${latest}`],
          label: 'root',
          packages: [{ name, current: '2.6.2', latest }],
        } as never,
      ],
      '11.0.0'
    );
  const wiredBump = wired('@biomejs/biome', '2.6.3');
  const wiredOther = wired('typescript', '6.0.1');
  const biomeWrite = wiredBump.writes.find((w) => w.file === 'biome.json');
  return [
    {
      name: 'biome schema: stepsOf pushes the biome.json write and its note for an @biomejs/biome bump, and neither for another package',
      ok:
        biomeWrite?.after === doc('2.6.3') &&
        wiredBump.notes.some((n) => n.includes('biome.json')) &&
        !wiredOther.writes.some((w) => w.file === 'biome.json') &&
        !wiredOther.notes.some((n) => n.includes('biome.json')),
      detail: JSON.stringify({
        writes: wiredBump.writes.map((w) => w.file),
        notes: wiredBump.notes,
      }),
    },
    {
      name: 'biome schema: a planned @biomejs/biome bump writes the new version into biome.json $schema and nothing else',
      ok: bumped === doc('2.6.3'),
      detail: String(bumped),
    },
    {
      name: 'biome schema: a bump of any other package leaves biome.json untouched',
      ok: other === null,
      detail: String(other),
    },
    {
      name: 'biome schema: a schema already at the planned version is not rewritten',
      ok: same === null,
    },
  ];
}

// ---- npm: override ranges the lockfile does not meet (worklist #c97a62d9) ---------------------

async function npmOverrideCases(): Promise<Array<{ name: string; ok: boolean; detail?: string }>> {
  // The 2026-10-31 shape: the root vite override floor raised to >=8.3.5 by hand while the lock
  // holds 8.3.4, eleven unrelated packages inside the window, and gray-matter's nested js-yaml ^3
  // copy below a top-level js-yaml >=4.3.2 <5 override (the real tree carries both).
  const ON = Date.parse('2026-10-31T12:00:00Z');
  const WINDOW = 1440 * 60_000;
  const CUTOFF = '2026-10-29T23:59:59.999Z';
  const manifest = (vite: string, scoped = true): string =>
    `${JSON.stringify(
      {
        name: 'fixture',
        overrides: {
          vite,
          'js-yaml': '>=4.3.2 <5.0.0',
          ...(scoped ? { 'gray-matter': { 'js-yaml': '^3.15.2' } } : {}),
          zod: '$zod',
        },
      },
      null,
      2
    )}\n`;
  const lock = (vite: string): string =>
    `${JSON.stringify(
      {
        lockfileVersion: 3,
        packages: {
          '': { name: 'fixture' },
          'node_modules/vite': { version: vite },
          'node_modules/astro/node_modules/vite': { version: vite },
          'node_modules/js-yaml': { version: '4.3.2' },
          'node_modules/gray-matter': { version: '4.0.3' },
          'node_modules/gray-matter/node_modules/js-yaml': { version: '3.15.2' },
        },
      },
      null,
      2
    )}\n`;
  const npmTree = (vite: string, locked: string): string =>
    tree({
      '.devcontainer/toolchain.env': 'NPM_VERSION=11.21.0\n',
      'package.json': manifest(vite),
      'package-lock.json': lock(locked),
    });
  const viteDoc = (fresh855: boolean): Packument => ({
    versions: { '8.3.4': {}, '8.3.5': {}, '8.3.6': {}, '9.0.0': {}, '8.4.0-beta.1': {} },
    time: {
      '8.3.4': '2026-10-10T00:00:00Z',
      '8.3.5': fresh855 ? '2026-10-30T09:00:00Z' : '2026-10-21T08:00:00Z',
      '8.3.6': '2026-10-30T10:00:00Z',
      '9.0.0': '2026-09-01T00:00:00Z',
      '8.4.0-beta.1': '2026-09-01T00:00:00Z',
    },
    'dist-tags': { latest: '8.3.6' },
  });
  const asked: string[] = [];
  const docsOf =
    (doc: Packument) =>
    (name: string): Promise<Packument> => {
      asked.push(name);
      // js-yaml answers too, so a lost nested-scope skip shows as a named red control (a second move), not as a crash.
      return name === 'vite'
        ? Promise.resolve(doc)
        : name === 'js-yaml'
          ? Promise.resolve({
              versions: { '4.3.2': {} },
              time: { '4.3.2': '2026-09-01T00:00:00Z' },
              'dist-tags': { latest: '4.3.2' },
            })
          : Promise.reject(new Error(`no document for ${name}`));
    };
  const tooNew = Array.from({ length: 11 }, (_, i) => ({
    pkg: { name: `fresh-${i}`, current: '1.0.0', latest: '1.0.1' },
    manifest: '',
  }));
  const basePlan = (steps: NpmPlanJson['steps'] = []): NpmPlanJson => ({
    nowMs: ON,
    minReleaseAgeMs: WINDOW,
    steps,
    majors: [],
    tooNew,
    manifests: ['.'],
  });
  const refusal = (f: () => unknown): string | null => {
    try {
      f();
      return null;
    } catch (err) {
      return err instanceof PlanRefused ? err.message : `NOT A REFUSAL: ${String(err)}`;
    }
  };

  // A: the vite case.
  const viteRoot = npmTree('>=8.3.5 <9', '8.3.4');
  const viteOv = await judgeOverrides(
    entry('npm'),
    ctxOf(viteRoot),
    ON,
    WINDOW,
    docsOf(viteDoc(false))
  );
  const viteRel = inRangeReleases(basePlan(), viteOv);
  let vitePlan: PinPlan | null = null;
  const viteRefused = refusal(() => {
    vitePlan = inRangePlan(entry('npm'), ctxOf(viteRoot), basePlan(), viteOv);
  });
  const vp = vitePlan as PinPlan | null;
  const viteRuns = vp?.steps.map((x) => x.run) ?? [];

  // B: the same floor whose only admitted release is inside the window.
  const freshOv = await judgeOverrides(
    entry('npm'),
    ctxOf(viteRoot),
    ON,
    WINDOW,
    docsOf({
      versions: { '8.3.4': {}, '8.3.5': {} },
      time: { '8.3.4': '2026-10-10T00:00:00Z', '8.3.5': '2026-10-30T09:00:00Z' },
      'dist-tags': { latest: '8.3.5' },
    })
  );
  const freshRel = inRangeReleases(basePlan(), freshOv);
  const inRangeStep = {
    cwd: viteRoot,
    args: ['update', 'typescript', `--before=${CUTOFF}`],
    label: 'root',
    packages: [{ name: 'typescript', current: '6.0.0', latest: '6.0.1' }],
  };
  const freshRefused = refusal(() =>
    inRangePlan(entry('npm'), ctxOf(viteRoot), basePlan(), freshOv)
  );
  const freshWithSteps = refusal(() =>
    inRangePlan(entry('npm'), ctxOf(viteRoot), basePlan([inRangeStep]), freshOv)
  );

  // C: a lock that meets every override, and only deferrals: the registry is never asked.
  const metRoot = npmTree('>=8.3.5 <9', '8.3.5');
  const askedBefore = asked.length;
  const metOv = await judgeOverrides(
    entry('npm'),
    ctxOf(metRoot),
    ON,
    WINDOW,
    docsOf(viteDoc(false))
  );
  const metRel = inRangeReleases(basePlan(), metOv);
  const metRefused = refusal(() => inRangePlan(entry('npm'), ctxOf(metRoot), basePlan(), metOv));

  // D: a move check-deps already plans is not planned twice.
  const dupOv = await judgeOverrides(
    entry('npm'),
    ctxOf(viteRoot),
    ON,
    WINDOW,
    docsOf(viteDoc(false)),
    new Set([`${viteRoot}\0vite`])
  );

  const nestedOn = overrideDrift(manifest('>=8.3.5 <9', true), lock('8.3.5'));
  const nestedOff = overrideDrift(manifest('>=8.3.5 <9', false), lock('8.3.5'));
  const cut = Date.parse(CUTOFF);
  const tagPick = overrideTarget('>=8.3.5 <9', viteDoc(false), Date.parse('2026-10-31T00:00:00Z'));
  const undated = overrideTarget(
    '>=8.3.5 <9',
    { versions: { '8.3.5': {} }, time: {}, 'dist-tags': {} },
    cut
  );
  const noneAdmitted = overrideTarget('>=10', viteDoc(false), cut);
  const empty: OverrideJudgement = { moves: [], deferred: [], notes: [] };
  return [
    {
      name: 'npm override: a hand-raised transitive floor (vite >=8.3.5, lock 8.3.4) beside eleven deferrals plans npm update vite --before=<cutoff> and its guard, and is not refused',
      ok:
        viteRefused === null &&
        viteOv.moves.length === 1 &&
        viteOv.deferred.length === 0 &&
        viteRel.length === 1 &&
        viteRel[0].version === '1.1' &&
        viteRel[0].verdict?.eligible === true &&
        /override range/.test(viteRel[0].verdict.why) &&
        viteRuns.some(
          (r) => r === `npx -y npm@11.21.0 update vite --before=${CUTOFF} --loglevel=notice`
        ) &&
        viteRuns.some((r) => / guard /.test(r)) &&
        (vp?.changes.includes('root: vite 8.3.4 -> 8.3.5') ?? false) &&
        (vp?.changes.some((c) =>
          /overrides\["vite"\] >=8\.3\.5 <9: the lock holds 8\.3\.4/.test(c)
        ) ??
          false),
      detail: JSON.stringify({ viteRefused, viteOv, viteRel, viteRuns, changes: vp?.changes }),
    },
    {
      name: 'npm override: the deferred packages stay deferred and are named in the run label and the release verdict',
      ok:
        /11 deferred package\(s\) left \(fresh-0, fresh-1, fresh-2, fresh-3, fresh-4 and 6 more\)/.test(
          vp?.to.version ?? ''
        ) &&
        deferredNames(tooNew.slice(0, 3)) === 'fresh-0, fresh-1, fresh-2' &&
        /11 package\(s\) stay deferred/.test(viteRel[0]?.verdict?.why ?? '') &&
        !viteRuns.some((r) => /fresh-/.test(r)),
      detail: JSON.stringify({ to: vp?.to.version, why: viteRel[0]?.verdict?.why }),
    },
    {
      name: 'npm override: the target is the release npm picks under --before (8.3.5), never the newer latest tag (8.3.6) inside the window nor the 9.x major the bound excludes',
      ok:
        viteOv.moves[0]?.packages[0]?.latest === '8.3.5' &&
        tagPick.kind === 'target' &&
        tagPick.version === '8.3.6' &&
        noneAdmitted.kind === 'none',
      detail: JSON.stringify({ move: viteOv.moves[0], tagPick, noneAdmitted }),
    },
    {
      name: 'npm override: a target inside the release-age window is refused, alone and beside in-range packages, and the release is not eligible',
      ok:
        freshOv.moves.length === 0 &&
        freshOv.deferred.length === 1 &&
        freshRel.length === 1 &&
        freshRel[0].verdict?.eligible === false &&
        /vite/.test(freshRel[0].verdict.why) &&
        freshRefused !== null &&
        /overrides\["vite"\].*inside the release-age window/.test(freshRefused) &&
        freshWithSteps !== null &&
        /inside the release-age window/.test(freshWithSteps),
      detail: JSON.stringify({ freshOv, freshRel, freshRefused, freshWithSteps }),
    },
    {
      name: 'npm override: a release with no publish time is never old enough (fail closed)',
      ok: undated.kind === 'deferred',
      detail: JSON.stringify(undated),
    },
    {
      name: 'npm override: CONTROL a lock that meets every override, with only deferrals, still answers the 1.1 deferral as before and asks the registry nothing',
      ok:
        metOv.moves.length === 0 &&
        metOv.deferred.length === 0 &&
        asked.length === askedBefore &&
        metRel.length === 1 &&
        metRel[0].version === '1.1' &&
        metRel[0].verdict?.eligible === false &&
        metRel[0].verdict.why ===
          '11 package(s) newer than the lockfiles, all inside the release-age window' &&
        metRefused === `npm: nothing past the window to bump` &&
        inRangeReleases({ ...basePlan(), tooNew: [] }, empty).length === 0,
      detail: JSON.stringify({ metOv, metRel, metRefused, asked }),
    },
    {
      name: 'npm override: CONTROL a nested copy a scoped override governs (gray-matter js-yaml ^3) is not judged against the top-level range; without the scope it is',
      ok:
        nestedOn.length === 0 &&
        nestedOff.length === 1 &&
        nestedOff[0].name === 'js-yaml' &&
        nestedOff[0].outside.join() === '3.15.2',
      detail: JSON.stringify({ nestedOn, nestedOff }),
    },
    {
      name: 'npm override: a major run keeps the notes of the moves it keeps, not the note of a move its own plan already makes',
      ok: (() => {
        // Two moves, two notes (one per move, in order); the plan already makes the first.
        const mv = (name: string) => ({
          ...inRangeStep,
          packages: [{ name, current: '1.0.0', latest: '1.1.0' }],
        });
        const two: OverrideJudgement = {
          moves: [mv('alpha'), mv('beta')],
          deferred: [],
          notes: ['note-alpha', 'note-beta'],
        };
        const kept = keptMoves([mv('alpha')], two);
        // The buggy variant returns every note; it must fail the assertion below.
        const buggyNotes = two.notes;
        const assertion = (notes: string[]) => notes.length === 1 && notes[0] === 'note-beta';
        return (
          kept.moves.length === 1 &&
          kept.moves[0].packages[0].name === 'beta' &&
          assertion(kept.notes) &&
          !assertion(buggyNotes)
        );
      })(),
      detail: JSON.stringify({ notes: viteOv.notes }),
    },
    {
      name: 'npm override: a package deferred in two projects is counted once, matching the one name listed',
      ok: (() => {
        const t = [
          { pkg: { name: 'dup' }, manifest: 'a/package.json' },
          { pkg: { name: 'dup' }, manifest: 'b/package.json' },
        ];
        return deferredCount(t) === 1 && deferredNames(t) === 'dup' && t.length === 2;
      })(),
    },
    {
      name: 'npm override: a package check-deps already moves in the same project is not planned a second time',
      ok: dupOv.moves.length === 0 && viteOv.moves.length === 1,
      detail: JSON.stringify(dupOv),
    },
  ];
}

async function allCases(mutant?: T8Mutant) {
  return [
    ...(await actionsCases(mutant)),
    ...(await goCases(mutant)),
    ...(await osCases(mutant)),
    ...(await cephImageCases(mutant)),
    ...(await realProviderCases()),
    ...(await dockerCases(mutant)),
    ...biomeSchemaCases(),
    ...(await npmOverrideCases()),
  ];
}

async function main(): Promise<number> {
  const env = process.env.PINS_T8_MUTANT;
  if (env !== undefined && !(T8_MUTANTS as readonly string[]).includes(env)) {
    console.error(`PINS_T8_MUTANT=${env} refused: the mutants are ${T8_MUTANTS.join(', ')}`);
    return 2;
  }
  const mutant = env as T8Mutant | undefined;
  const cases = await allCases(mutant);
  let failed = runControls(cases);
  if (mutant === undefined) {
    // Every mutant, in-process: it must turn at least one control red.
    const mutantCases = [];
    for (const m of T8_MUTANTS) {
      const reds = (await allCases(m)).filter((c) => !c.ok);
      mutantCases.push({
        name: `MUTANT ${m} turns ${reds.length ? reds.length : 'no'} control(s) red`,
        ok: reds.length > 0,
        detail: `no control failed under ${m}: the property it disables is not tested`,
      });
    }
    failed += runControls(mutantCases);
  }
  for (const t of tmps) fs.rmSync(t, { recursive: true, force: true });
  return failed === 0 ? 0 : 1;
}

if (isEntryPoint(import.meta.filename)) {
  main().then(
    (rc) => process.exit(rc),
    (err) => {
      console.error(err);
      process.exit(1);
    }
  );
}
