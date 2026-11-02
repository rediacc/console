/**
 * Controls for the embed driver, run against a temporary copy of the live renet files and an
 * upstream answered from a URL map (nothing here reaches the network or writes the live tree).
 *
 *   npx tsx scripts/lib/pins/drivers/embed-selftest.ts
 *
 * Each refusal is proved by a mutant that removes it: the clean run passes every control, and
 * each mutant run must fail at least one.
 */
import { isEntryPoint } from '../../entry-point.js';
import '../driver.js';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { WK_GH_API_BASE } from '../../../../packages/shared/src/config/well-known.generated.js';
import { type ControlCase, runControls } from '../../controls.js';
import { policyPath } from '../../policy-paths.js';
import { keyOf, type PinPlan, PlanRefused } from '../driver.js';
import { type Runner, runTransaction } from '../txn.js';
import { createEmbedDriver, EMBED_MUTANTS, type EmbedMutant } from './embed.js';
import {
  ctxOf,
  entryOf,
  hex,
  LIVE_ROOT,
  liveFiles,
  makeTree,
  patchOf,
  proveMutants,
  removeRoots,
  stubUpstream,
} from './toolchain-fixture.js';

const GH = WK_GH_API_BASE;
const RAW = 'https://raw.githubusercontent.com';
const SNAP = 'kubernetes-csi/external-snapshotter';
const CRD_DIR = 'private/renet/pkg/kube/csidriver/crds';
const CRD_NAMES = [
  'snapshot.storage.k8s.io_volumesnapshotclasses.yaml',
  'snapshot.storage.k8s.io_volumesnapshotcontents.yaml',
  'snapshot.storage.k8s.io_volumesnapshots.yaml',
];

function treeFiles(): string[] {
  return [
    'private/renet/Dockerfile',
    'private/renet/embed-assets.lock.json',
    'private/renet/pkg/embed/embed.go',
    'private/renet/pkg/embed/credits_data.go',
    ...liveFiles('private/renet/pkg/kube/csidriver'),
    'docs/design/spec/09-csi-driver.md',
    'packages/cli/src/data/third-party-credits.json',
    'scripts/gen/generate-embed-credits.ts',
    'scripts/gates/check-embed-credits.ts',
    'scripts/lib/console.ts',
    'scripts/lib/dockerfile-versions.ts',
    'scripts/lib/entry-point.ts',
    'scripts/lib/repo-root.ts',
    'scripts/lib/submodule-presence.ts',
  ];
}

const tree = (blocklist = '# fixture blocklist\n'): string =>
  makeTree(treeFiles(), {
    'package.json': '{ "name": "fixture", "private": true }\n',
    '.ci/.keep': '',
    [policyPath('.embed-assets-upgrade-blocklist', '.')]: blocklist,
  });

const live = (rel: string): string => fs.readFileSync(path.join(LIVE_ROOT, rel), 'utf8');
const dockerArg = (text: string, name: string): string =>
  new RegExp(`^ARG ${name}=(\\S+)`, 'm').exec(text)?.[1] ?? '';

/** The URLs a csisnapshotter bump to `v` asks, answered; `crds` is what the new tag serves. */
function snapshotterAnswers(
  v: string,
  crds: Record<string, string> | null
): Record<string, string | object> {
  const a: Record<string, string | object> = {
    [`${GH}/repos/${SNAP}/commits/v${v}`]: { sha: hex('1', 40) },
  };
  if (crds) {
    a[`${GH}/repos/${SNAP}/contents/client/config/crd?ref=v${v}`] = [
      { name: 'groupsnapshot.storage.k8s.io_volumegroupsnapshots.yaml' },
      { name: 'kustomization.yaml' },
      ...Object.keys(crds).map((name) => ({ name })),
    ];
    for (const [name, text] of Object.entries(crds))
      a[`${RAW}/${SNAP}/v${v}/client/config/crd/${name}`] = text;
  }
  return a;
}

function vendored(): Record<string, string> {
  return Object.fromEntries(CRD_NAMES.map((n) => [n, live(`${CRD_DIR}/${n}`)]));
}

async function planOf(
  id: string,
  v: string,
  answers: Record<string, string | object>,
  mutant: EmbedMutant | null,
  root = tree()
): Promise<{ plan?: PinPlan; refused?: string; root: string }> {
  const drv = createEmbedDriver(stubUpstream(answers), mutant);
  try {
    const plan = await drv.plan(entryOf(id), { version: v, publishedMs: 0 }, ctxOf(root));
    return { plan, root };
  } catch (err) {
    if (err instanceof PlanRefused) return { refused: err.message, root };
    throw err;
  }
}

const textOf = (p: PinPlan, rel: string): string | undefined =>
  p.writes.find((w) => keyOf(w) === rel)?.after;

/** The runner of the end-to-end case: the real credits generator and credits gate over the fixture, a stub for go and for the network gate. */
function fixtureRunner(root: string, ran: string[]): Runner {
  const tsx = path.join(LIVE_ROOT, 'node_modules/.bin/tsx');
  return (cmd, cwd) => {
    ran.push(`${path.relative(root, cwd) || '.'}: ${cmd}`);
    if (cmd.startsWith('npx tsx ')) {
      const r = spawnSync(tsx, cmd.slice('npx tsx '.length).split(' '), {
        cwd,
        encoding: 'utf8',
        env: Object.fromEntries(
          Object.entries(process.env).filter(([k]) => !k.startsWith('EMBED_CREDITS_'))
        ),
      });
      return { rc: r.status ?? 1, out: `${r.stdout}${r.stderr}` };
    }
    if (cmd.startsWith('go test ')) return { rc: 0, out: '' };
    if (cmd.startsWith('npm run ci -- --only ')) {
      const g = spawnSync(tsx, ['scripts/gates/check-embed-credits.ts'], {
        cwd: root,
        encoding: 'utf8',
      });
      return { rc: g.status ?? 1, out: `${g.stdout}${g.stderr}` };
    }
    return { rc: 127, out: `no stub for ${cmd}` };
  };
}

async function build(mutant: EmbedMutant | null): Promise<ControlCase[]> {
  const cases: ControlCase[] = [];
  const add = (name: string, ok: boolean, detail?: string): void => {
    cases.push({ name, ok, detail });
  };
  const cur = dockerArg(live('private/renet/Dockerfile'), 'CSISNAPSHOTTER_VERSION');
  const next = patchOf(cur);
  const ctlCur = dockerArg(live('private/renet/Dockerfile'), 'SNAPSHOTCONTROLLER_VERSION');

  // -- csisnapshotter with the CRDs unchanged: a byte-identity proof, no re-vendor.
  {
    const r = await planOf(
      'embed:csisnapshotter',
      next,
      snapshotterAnswers(next, vendored()),
      mutant
    );
    const p = r.plan;
    const paths = new Set(p?.writes.map(keyOf));
    const df = p ? textOf(p, 'private/renet/Dockerfile') : undefined;
    add(
      'csisnapshotter bump: Dockerfile commit and both versions move together',
      !!df &&
        dockerArg(df, 'CSISNAPSHOTTER_VERSION') === next &&
        dockerArg(df, 'SNAPSHOTCONTROLLER_VERSION') === next &&
        dockerArg(df, 'CSISNAPSHOTTER_COMMIT') === hex('1', 40),
      df ? undefined : (r.refused ?? 'no plan')
    );
    const lock = p ? textOf(p, 'private/renet/embed-assets.lock.json') : undefined;
    const doc = lock ? JSON.parse(lock).components : null;
    add(
      'csisnapshotter bump: the lockfile moves both components and the commit',
      !!doc &&
        doc.csisnapshotter.version === next &&
        doc.snapshotcontroller.version === next &&
        doc.csisnapshotter.source.commit === hex('1', 40) &&
        doc.snapshotcontroller.source.commit === hex('1', 40)
    );
    add(
      'csisnapshotter bump: the Go constants, both unit goldens and the spec table move',
      !!p &&
        paths.has('private/renet/pkg/kube/csidriver/units.go') &&
        paths.has('private/renet/pkg/kube/csidriver/testdata/rediacc-csi-snapshotter.service') &&
        paths.has(
          'private/renet/pkg/kube/csidriver/testdata/rediacc-csi-snapshot-controller.service'
        ) &&
        paths.has('docs/design/spec/09-csi-driver.md') &&
        (textOf(p, 'docs/design/spec/09-csi-driver.md') ?? '').split(`**v${next}**`).length >= 3,
      [...paths].join(', ')
    );
    const go = p ? textOf(p, 'private/renet/pkg/kube/csidriver/crds.go') : undefined;
    add(
      'CRD claim: identical CRDs at the new tag move the claim in crds.go and the lock notes, with the proof recorded and no CRD file rewritten',
      !!p &&
        !!go?.includes(`external-snapshotter v${next} client/config/crd`) &&
        !!lock?.includes(`vendored verbatim from the same v${next} tag`) &&
        p.changes.some((c) => c.includes('byte-identical')) &&
        !CRD_NAMES.some((n) => paths.has(`${CRD_DIR}/${n}`))
    );
    add(
      'a csidriver bump carries the golden and CRD proving step',
      !!p &&
        p.steps.some((s) => s.run === 'go test ./pkg/kube/csidriver' && s.cwd === 'private/renet')
    );
  }

  // -- the CRDs changed at the new tag: re-vendored verbatim.
  {
    const crds = vendored();
    crds[CRD_NAMES[1]] = `${crds[CRD_NAMES[1]]}# new in the tag\n`;
    const r = await planOf('embed:csisnapshotter', next, snapshotterAnswers(next, crds), mutant);
    add(
      'CRD claim: changed CRDs at the new tag are re-vendored verbatim, and only the changed file',
      !!r.plan &&
        textOf(r.plan, `${CRD_DIR}/${CRD_NAMES[1]}`) === crds[CRD_NAMES[1]] &&
        r.plan.writes.filter((w) => w.file.startsWith('pkg/kube/csidriver/crds/')).length === 1 &&
        r.plan.changes.some((c) => c.includes('re-vendored')),
      r.refused
    );
  }

  // -- no CRDs readable at the new tag: neither a re-vendor nor a proof, so the plan is refused.
  {
    const r = await planOf('embed:csisnapshotter', next, snapshotterAnswers(next, null), mutant);
    add(
      'CRD claim: a tag whose CRDs cannot be read is refused (no re-vendor, no proof)',
      (r.refused ?? '').includes('neither a re-vendor'),
      r.refused ?? 'a plan was returned'
    );
  }
  {
    const crds = vendored();
    delete crds[CRD_NAMES[2]];
    const r = await planOf('embed:csisnapshotter', next, snapshotterAnswers(next, crds), mutant);
    add(
      'CRD claim: a tag whose CRD set is not the vendored three is refused',
      (r.refused ?? '').includes('not the vendored set'),
      r.refused ?? 'a plan was returned'
    );
  }

  // -- no tag to resolve the commit from.
  {
    const a = snapshotterAnswers(next, vendored());
    delete a[`${GH}/repos/${SNAP}/commits/v${next}`];
    const r = await planOf('embed:csisnapshotter', next, a, mutant);
    add(
      'a release whose tag cannot be resolved to a commit is refused whole',
      (r.refused ?? '').includes('cannot resolve the commit'),
      r.refused ?? 'a plan was returned'
    );
  }

  // -- the sibling that shares the clone.
  {
    const held = tree(
      `# fixture blocklist\n# BLOCKER: held back for the fixture\nsnapshotcontroller\n`
    );
    const r = await planOf(
      'embed:csisnapshotter',
      next,
      snapshotterAnswers(next, vendored()),
      mutant,
      held
    );
    add(
      'a held sibling that shares the clone refuses the bump of the other',
      (r.refused ?? '').includes('shares its clone and is held'),
      r.refused ?? 'a plan was returned'
    );
    const ctl = await planOf(
      'embed:snapshotcontroller',
      next,
      snapshotterAnswers(next, vendored()),
      mutant
    );
    const df = ctl.plan ? textOf(ctl.plan, 'private/renet/Dockerfile') : undefined;
    add(
      'bumping snapshotcontroller moves csisnapshotter with it',
      !!df &&
        dockerArg(df, 'CSISNAPSHOTTER_VERSION') === next &&
        dockerArg(df, 'SNAPSHOTCONTROLLER_VERSION') === next,
      ctl.refused
    );
    add('the fixture starts with the shared clone in step', cur === ctlCur, `${cur} vs ${ctlCur}`);
  }

  // -- zot (a published checksum file) and rsync (none).
  {
    const df = live('private/renet/Dockerfile');
    const zv = patchOf(dockerArg(df, 'ZOT_VERSION'));
    const sums = `${hex('a')}  zot-linux-amd64\n${hex('b')}  zot-linux-arm64\n`;
    const url = `https://github.com/project-zot/zot/releases/download/v${zv}/checksums.sha256.txt`;
    const r = await planOf('embed:zot', zv, { [url]: sums }, mutant);
    const out = r.plan ? textOf(r.plan, 'private/renet/Dockerfile') : undefined;
    add(
      'zot bump: both architectures take their digest from the published checksum file, on every ARG line',
      !!out &&
        out.split(`ARG ZOT_VERSION=${zv}`).length === 3 &&
        out.includes(`ARG ZOT_SHA256_AMD64=${hex('a')}`) &&
        out.includes(`ARG ZOT_SHA256_ARM64=${hex('b')}`),
      r.refused
    );
    const rv = patchOf(dockerArg(df, 'RSYNC_VERSION'));
    const rs = await planOf('embed:rsync', rv, {}, mutant);
    add(
      'rsync bump: no published checksum, so the plan is refused rather than leaving the digest behind',
      (rs.refused ?? '').includes('sha256 pin cannot be resolved'),
      rs.refused ?? 'a plan was returned'
    );
  }

  // -- inspect: releases newer than the pin, monorepo client/ tags excluded, CRIU through its tags.
  {
    const rel = (tag: string, at: string) => ({
      tag_name: tag,
      published_at: at,
      prerelease: false,
      draft: false,
    });
    const up = stubUpstream({
      [`${GH}/repos/${SNAP}/releases?per_page=100`]: [
        rel(`v${next}`, '2026-10-13T14:06:03Z'),
        rel(`client/v${next}`, '2026-10-13T14:10:18Z'),
        rel(`v${cur}`, '2026-05-28T13:43:22Z'),
      ],
      [`${GH}/repos/checkpoint-restore/criu/releases?per_page=100`]: [],
      [`${GH}/repos/checkpoint-restore/criu/tags?per_page=100`]: [
        { name: 'v99.1.0' },
        { name: 'v4.0.0' },
        { name: 'v99.1.0-rc1' },
      ],
      [`${GH}/repos/checkpoint-restore/criu/commits/v99.1.0`]: {
        commit: { committer: { date: '2026-10-01T00:00:00Z' } },
      },
    });
    const drv = createEmbedDriver(up, mutant);
    const ctx = ctxOf(tree());
    const i = await drv.inspect(entryOf('embed:csisnapshotter'), ctx);
    add(
      'inspect: the monorepo client/ tag is not a release, and the date is the release instant',
      i.current === cur &&
        i.releases.length === 1 &&
        i.releases[0].version === next &&
        i.releases[0].publishedMs === Date.parse('2026-10-13T14:06:03Z'),
      JSON.stringify(i)
    );
    const c = await drv.inspect(entryOf('embed:criu'), ctx);
    add(
      'inspect: a repository that tags without releases is read through its tags and dated by the tag commit',
      c.releases.length === 1 &&
        c.releases[0].version === '99.1.0' &&
        c.releases[0].publishedMs === Date.parse('2026-10-01T00:00:00Z'),
      JSON.stringify(c)
    );
  }

  // -- the whole transaction on the fixture: sites, credits, goldens, constants in one run.
  if (mutant === null) {
    const root = tree();
    const answers = snapshotterAnswers(next, vendored());
    const drv = createEmbedDriver(stubUpstream(answers));
    const entry = entryOf('embed:csisnapshotter');
    const plan = await drv.plan(entry, { version: next, publishedMs: 0 }, ctxOf(root));
    const ran: string[] = [];
    const res = runTransaction([plan], {
      root,
      stamp: 'embed-selftest',
      runner: fixtureRunner(root, ran),
      mutant: null,
      npmVersion: null,
      submodules: ['private/renet'],
    });
    const credits = fs.existsSync(path.join(root, 'private/renet/pkg/embed/credits_data.go'))
      ? fs.readFileSync(path.join(root, 'private/renet/pkg/embed/credits_data.go'), 'utf8')
      : '';
    const json = fs.readFileSync(
      path.join(root, 'packages/cli/src/data/third-party-credits.json'),
      'utf8'
    );
    const gate = spawnSync(
      path.join(LIVE_ROOT, 'node_modules/.bin/tsx'),
      ['scripts/gates/check-embed-credits.ts'],
      {
        cwd: root,
        encoding: 'utf8',
      }
    );
    add(
      'transaction: Dockerfile, lockfile, constants, goldens, spec, CRD claim, credits inventories land in one run and check:ci-embed-credits exits 0',
      res.ok &&
        credits.includes(`"${next}"`) &&
        json.includes(`"${next}"`) &&
        gate.status === 0 &&
        ran.some((c) => c.includes('generate-embed-credits.ts')) &&
        ran.some((c) => c.includes('go test ./pkg/kube/csidriver')),
      `${res.failure ?? ''} gate rc=${gate.status} ${gate.stdout}${gate.stderr}`
    );
  }
  return cases;
}

async function main(): Promise<number> {
  try {
    const forced = process.argv[2] === '--mutant' ? (process.argv[3] as EmbedMutant) : null;
    if (forced) {
      if (!EMBED_MUTANTS.includes(forced)) throw new Error(`no mutant ${forced}`);
      return runControls(await build(forced));
    }
    const { clean, mutantFailures } = await proveMutants(EMBED_MUTANTS, build);
    const bad = runControls(clean);
    for (const m of mutantFailures) console.error(m);
    return bad + mutantFailures.length;
  } finally {
    removeRoots();
  }
}

if (isEntryPoint(import.meta.filename)) main().then((n) => process.exit(n === 0 ? 0 : 1));
