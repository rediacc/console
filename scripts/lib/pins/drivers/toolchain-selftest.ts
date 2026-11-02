/**
 * Controls for the toolchain driver over a temporary copy of the live pin files and an upstream
 * answered from a URL map.
 *
 *   npx tsx scripts/lib/pins/drivers/toolchain-selftest.ts
 *
 * The Go case applies its plan to the temporary tree and runs the real
 * check:ci-toolchain-env-dockerfile-sync gate over it (REDIACC_CI_ROOT), and runs the same gate
 * over a tree where only toolchain.env moved, to show the gate can fail on what the plan prevents.
 */
import { isEntryPoint } from '../../entry-point.js';
import '../driver.js';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import {
  WK_GH_API_BASE,
  WK_GO_DL_BASE,
} from '../../../../packages/shared/src/config/well-known.generated.js';
import { type ControlCase, runControls } from '../../controls.js';
import { keyOf, type PinPlan, PlanRefused } from '../driver.js';
import { createToolchainDriver, TOOLCHAIN_MUTANTS, type ToolchainMutant } from './toolchain.js';
import {
  ctxOf,
  entryOf,
  hex,
  LIVE_ROOT,
  makeTree,
  patchOf,
  proveMutants,
  removeRoots,
  stubUpstream,
} from './toolchain-fixture.js';

const GH = WK_GH_API_BASE;
const ENV = '.devcontainer/toolchain.env';
const DF = '.devcontainer/Dockerfile';
const CONSTANTS = '.ci/config/constants.sh';
const LOCKS = [
  'package-lock.json',
  'workers/account/package-lock.json',
  'workers/mta-sts/package-lock.json',
  'workers/proxy/package-lock.json',
  'workers/www/package-lock.json',
  'private/account/package-lock.json',
  'private/account/web/package-lock.json',
  'private/account/e2e/package-lock.json',
];

function tree(locks: string[] = LOCKS): string {
  return makeTree(
    [
      ENV,
      DF,
      CONSTANTS,
      'Dockerfile',
      'workers/proxy/Dockerfile',
      'package.json',
      'packages/cli/package.json',
      // The second toolchain:wrangler site (.ci/config/pins.json).
      'workers/account/package.json',
      'private/renet/go.mod',
      '.ci/scripts/private/license-mint/go.mod',
    ],
    {
      ...Object.fromEntries(locks.map((l) => [l, '{}\n'])),
      'private/account/Dockerfile': fs.readFileSync(
        path.join(LIVE_ROOT, 'private/account/Dockerfile'),
        'utf8'
      ),
    },
    ['private/renet', 'private/account']
  );
}

const live = (rel: string): string => fs.readFileSync(path.join(LIVE_ROOT, rel), 'utf8');
const envVal = (text: string, key: string): string =>
  new RegExp(`^${key}=(\\S*)$`, 'm').exec(text)?.[1] ?? '';
const arg = (text: string, name: string): string =>
  new RegExp(`^ARG ${name}=(\\S+)`, 'm').exec(text)?.[1] ?? '';
const textOf = (p: PinPlan | undefined, rel: string): string | undefined =>
  p?.writes.find((w) => keyOf(w) === rel)?.after;

const release = (
  tag: string,
  at: string,
  digests: Record<string, string> = {}
): Record<string, unknown> => ({
  tag_name: tag,
  published_at: at,
  prerelease: false,
  draft: false,
  assets: Object.entries(digests).map(([name, d]) => ({ name, digest: `sha256:${d}` })),
});

/** The sync gate over `root`; its exit code. */
function syncGate(root: string): { rc: number; out: string } {
  const r = spawnSync(
    'python3',
    [path.join(LIVE_ROOT, '.ci/scripts/quality/check_toolchain_env_dockerfile_sync.py')],
    {
      cwd: LIVE_ROOT,
      encoding: 'utf8',
      env: { ...process.env, REDIACC_CI_ROOT: root, NO_COLOR: '1' },
    }
  );
  return { rc: r.status ?? 1, out: `${r.stdout}${r.stderr}` };
}

const apply = (root: string, p: PinPlan, only?: string[]): void => {
  for (const w of p.writes)
    if (only === undefined || only.includes(keyOf(w)))
      fs.writeFileSync(path.join(root, w.repo, w.file), w.after);
};

async function build(mutant: ToolchainMutant | null): Promise<ControlCase[]> {
  const cases: ControlCase[] = [];
  const add = (name: string, ok: boolean, detail?: string): void => {
    cases.push({ name, ok, detail });
  };
  const env = live(ENV);
  const plan = async (
    id: string,
    to: string,
    answers: Record<string, string | object>,
    root = tree()
  ): Promise<{ root: string; plan?: PinPlan; refused?: string }> => {
    const drv = createToolchainDriver(stubUpstream(answers), mutant);
    try {
      return {
        root,
        plan: await drv.plan(entryOf(id), { version: to, publishedMs: 0 }, ctxOf(root)),
      };
    } catch (err) {
      if (err instanceof PlanRefused) return { root, refused: err.message };
      throw err;
    }
  };

  // -- toolchain:go
  {
    const cur = envVal(env, 'GO_VERSION');
    const next = patchOf(cur);
    const minor = `1.${Number(cur.split('.')[1]) + 1}.0`;
    const files = (v: string, a: string, b: string) => [
      { filename: `go${v}.src.tar.gz`, sha256: hex('9') },
      { filename: `go${v}.linux-amd64.tar.gz`, sha256: a },
      { filename: `go${v}.linux-arm64.tar.gz`, sha256: b },
    ];
    const answers = {
      [`${WK_GO_DL_BASE}/?mode=json`]: [
        { version: `go${minor}`, stable: true, files: files(minor, hex('7'), hex('8')) },
        { version: `go${next}`, stable: true, files: files(next, hex('a'), hex('b')) },
        { version: `go${cur}`, stable: true, files: files(cur, hex('c'), hex('d')) },
        { version: 'go1.99rc1', stable: false, files: [] },
      ],
      [`https://proxy.golang.org/golang.org/toolchain/@v/v0.0.1-go${next}.linux-amd64.info`]: {
        Time: '2026-10-02T20:28:03Z',
      },
      [`https://proxy.golang.org/golang.org/toolchain/@v/v0.0.1-go${minor}.linux-amd64.info`]: {
        Time: '2026-10-03T00:00:00Z',
      },
    };
    const drv = createToolchainDriver(stubUpstream(answers), mutant);
    const i = await drv.inspect(entryOf('toolchain:go'), ctxOf(tree()));
    // Red under line-not-breaking (the minor line comes back with no `breaking`, so a plain bump would take it).
    add(
      'go inspect: the proxy dates the release, the same-line patch is plain, and another minor line is marked breaking naming every go.mod',
      i.releases.length === 2 &&
        i.releases[1].version === next &&
        i.releases[1].publishedMs === Date.parse('2026-10-02T20:28:03Z') &&
        i.releases[1].breaking === undefined &&
        i.releases[1].verdict === undefined &&
        i.releases[0].version === minor &&
        i.releases[0].verdict === undefined &&
        i.releases[0].breaking?.line === minor.split('.').slice(0, 2).join('.') &&
        i.releases[0].breaking.why.includes('go directive of every go.mod') &&
        i.releases[0].breaking.why.includes('private/renet/go.mod') &&
        i.releases[0].breaking.why.includes('.ci/scripts/private/license-mint/go.mod'),
      JSON.stringify(i)
    );
    const rm = await plan('toolchain:go', minor, answers);
    add(
      'go bump of another minor line: both go.mod `go` directives move to it, and go mod tidy runs in both modules',
      !!rm.plan &&
        (textOf(rm.plan, 'private/renet/go.mod') ?? '').includes(`\ngo ${minor}\n`) &&
        (textOf(rm.plan, '.ci/scripts/private/license-mint/go.mod') ?? '').includes(
          `\ngo ${minor}\n`
        ) &&
        arg(textOf(rm.plan, DF) ?? '', 'GO_SHA256_AMD64') === hex('7') &&
        rm.plan.steps.filter((x) => x.run === 'go mod tidy').length === 2,
      rm.refused
    );
    const r = await plan('toolchain:go', next, answers);
    const p = r.plan;
    add(
      'go bump: toolchain.env, the Dockerfile ARG and both archive hashes, and both go.mod directives move',
      !!p &&
        envVal(textOf(p, ENV) ?? '', 'GO_VERSION') === next &&
        arg(textOf(p, DF) ?? '', 'GO_VERSION') === next &&
        arg(textOf(p, DF) ?? '', 'GO_SHA256_AMD64') === hex('a') &&
        arg(textOf(p, DF) ?? '', 'GO_SHA256_ARM64') === hex('b') &&
        (textOf(p, 'private/renet/go.mod') ?? '').includes(`\ngo ${next}\n`) &&
        (textOf(p, '.ci/scripts/private/license-mint/go.mod') ?? '').includes(`\ngo ${next}\n`),
      r.refused
    );
    add(
      'go bump: go mod tidy runs in both modules, declaring go.mod and go.sum',
      !!p &&
        ['private/renet', '.ci/scripts/private/license-mint'].every((cwd) =>
          p.steps.some((s) => s.run === 'go mod tidy' && s.cwd === cwd && s.writes.length === 2)
        )
    );
    if (p) {
      const root = r.root;
      apply(root, p);
      const g = syncGate(root);
      add(
        'go bump: check:ci-toolchain-env-dockerfile-sync exits 0 over the bumped tree',
        g.rc === 0,
        g.out.slice(-300)
      );
      const half = tree();
      apply(half, p, [ENV]);
      const h = syncGate(half);
      add(
        'the sync gate is red when only toolchain.env moves (the half-bump the plan prevents)',
        h.rc !== 0,
        h.out.slice(-200)
      );
    }
    const missing = await plan('toolchain:go', next, {
      ...answers,
      [`${WK_GO_DL_BASE}/?mode=json`]: [
        { version: `go${next}`, stable: true, files: files(next, hex('a'), '').slice(0, 2) },
      ],
    });
    add(
      'go bump: a release with no archive hash for an architecture is refused',
      (missing.refused ?? '').includes('publishes no sha256 digest'),
      missing.refused ?? 'a plan was returned'
    );
  }

  // -- toolchain:npm
  {
    const cur = envVal(env, 'NPM_VERSION');
    const next = `${cur.split('.').slice(0, 2).join('.')}.${Number(cur.split('.')[2]) + 1}`;
    const r = await plan('toolchain:npm', next, {});
    const p = r.plan;
    const npmSteps = p?.steps ?? [];
    add(
      // The proxy image runs no npm since PLAN-proxy-cd-six-targets A2 (it copies a staged bundle), so it restates no NPM_VERSION and the bump must not touch it.
      'npm bump: toolchain.env and the two Dockerfiles restating NPM_VERSION move, the proxy image is untouched',
      !!p &&
        envVal(textOf(p, ENV) ?? '', 'NPM_VERSION') === next &&
        arg(textOf(p, 'Dockerfile') ?? '', 'NPM_VERSION') === next &&
        arg(textOf(p, 'private/account/Dockerfile') ?? '', 'NPM_VERSION') === next &&
        textOf(p, 'workers/proxy/Dockerfile') === undefined,
      r.refused
    );
    add(
      'npm bump: every lockfile of the npm family scope gets the canonical pass under the NEW pinned npm, never the npm on PATH',
      npmSteps.length === LOCKS.length &&
        LOCKS.every((l) =>
          npmSteps.some((s) =>
            s.writes.some((w) => `${w.repo === '.' ? '' : `${w.repo}/`}${w.file}` === l)
          )
        ) &&
        npmSteps.every(
          (s) => s.run === `npx -y npm@${next} install --package-lock-only --ignore-scripts`
        ),
      npmSteps.map((s) => s.run).join(' | ')
    );
    add(
      'npm bump: each pass runs in its lockfile directory',
      npmSteps.some((s) => s.cwd === 'workers/proxy') &&
        npmSteps.some((s) => s.cwd === 'private/account/web') &&
        npmSteps.some((s) => s.cwd === '.' || s.cwd === '')
    );
  }

  // -- python tools: PyPI, GitHub with hashes, GitHub through constants.sh.
  {
    const cur = envVal(env, 'RUFF_VERSION');
    const nv = patchOf(cur);
    const up = stubUpstream({
      'https://pypi.org/pypi/ruff/json': {
        releases: {
          [cur]: [{ upload_time_iso_8601: '2026-09-01T00:00:00Z' }],
          [nv]: [
            { upload_time_iso_8601: '2026-10-02T00:00:00Z' },
            { upload_time_iso_8601: '2026-10-03T00:00:00Z' },
          ],
          [patchOf(nv)]: [{ upload_time_iso_8601: '2026-10-04T00:00:00Z', yanked: true }],
          '9.9.9rc1': [{ upload_time_iso_8601: '2026-10-05T00:00:00Z' }],
        },
      },
    });
    const drv = createToolchainDriver(up, mutant);
    const ctx = ctxOf(tree());
    const i = await drv.inspect(entryOf('toolchain:ruff'), ctx);
    add(
      'ruff: PyPI dates a release by its earliest upload, skips a yanked release and a prerelease',
      i.releases.length === 1 &&
        i.releases[0].version === nv &&
        i.releases[0].publishedMs === Date.parse('2026-10-02T00:00:00Z'),
      JSON.stringify(i)
    );
    const rp = await drv.plan(entryOf('toolchain:ruff'), i.releases[0], ctx);
    add(
      'ruff: the plan is the one RUFF_VERSION line',
      rp.writes.length === 1 &&
        envVal(rp.writes[0].after, 'RUFF_VERSION') === nv &&
        rp.steps.length === 0
    );

    const uv = envVal(env, 'UV_VERSION');
    const uvn = patchOf(uv);
    const sums: Record<string, string> = {
      [`uv-x86_64-unknown-linux-gnu.tar.gz`]: hex('1'),
      [`uv-aarch64-unknown-linux-gnu.tar.gz`]: hex('2'),
      [`uv-x86_64-apple-darwin.tar.gz`]: hex('3'),
      [`uv-aarch64-apple-darwin.tar.gz`]: hex('4'),
    };
    const u = await plan('toolchain:uv', uvn, {
      [`${GH}/repos/astral-sh/uv/releases?per_page=100`]: [
        release(uvn, '2026-10-01T00:00:00Z', sums),
      ],
    });
    const ue = textOf(u.plan, ENV) ?? '';
    add(
      'uv: the version and all four platform hashes move',
      envVal(ue, 'UV_VERSION') === uvn &&
        envVal(ue, 'UV_SHA256_LINUX_X86_64') === hex('1') &&
        envVal(ue, 'UV_SHA256_LINUX_AARCH64') === hex('2') &&
        envVal(ue, 'UV_SHA256_DARWIN_X86_64') === hex('3') &&
        envVal(ue, 'UV_SHA256_DARWIN_AARCH64') === hex('4'),
      u.refused
    );

    // toolchain:awscli: no release is cut, so the tags are read; AWS publishes no digest, so each
    // versioned installer named by URL in the registry is downloaded and hashed.
    const aw = envVal(env, 'AWSCLI_VERSION');
    const awn = patchOf(aw);
    const awsAnswers = (withDarwin: boolean): Record<string, string | object> => ({
      [`${GH}/repos/aws/aws-cli/releases?per_page=100`]: [],
      [`${GH}/repos/aws/aws-cli/tags?per_page=100`]: [{ name: awn }, { name: aw }],
      [`${GH}/repos/aws/aws-cli/commits/${awn}`]: {
        commit: { committer: { date: '2026-10-01T00:00:00Z' } },
      },
      [`sha256:https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${awn}.zip`]: hex('a'),
      [`sha256:https://awscli.amazonaws.com/awscli-exe-linux-aarch64-${awn}.zip`]: hex('b'),
      ...(withDarwin
        ? { [`sha256:https://awscli.amazonaws.com/AWSCLIV2-${awn}.pkg`]: hex('c') }
        : {}),
    });
    const a = await plan('toolchain:awscli', awn, awsAnswers(true));
    const ae = textOf(a.plan, ENV) ?? '';
    add(
      'awscli: the version and the three installer hashes move, each hashed from its versioned URL',
      envVal(ae, 'AWSCLI_VERSION') === awn &&
        envVal(ae, 'AWSCLI_SHA256_LINUX_X86_64') === hex('a') &&
        envVal(ae, 'AWSCLI_SHA256_LINUX_AARCH64') === hex('b') &&
        envVal(ae, 'AWSCLI_SHA256_DARWIN') === hex('c'),
      a.refused
    );
    const an = await plan('toolchain:awscli', awn, awsAnswers(false));
    add(
      'awscli: an installer that cannot be hashed refuses the pin rather than moving it with an old hash',
      an.plan === undefined && typeof an.refused === 'string',
      an.refused
    );

    const sf = envVal(env, 'SHFMT_VERSION');
    const sfn = patchOf(sf);
    const shfmt = (n: string, h: string) => ({
      [`shfmt_v${n}_linux_amd64`]: hex(h),
      [`shfmt_v${n}_linux_arm64`]: hex(h === '5' ? '6' : '7'),
      [`shfmt_v${n}_darwin_amd64`]: hex('8'),
      [`shfmt_v${n}_darwin_arm64`]: hex('9'),
    });
    const s = await plan('toolchain:shfmt', sfn, {
      [`${GH}/repos/mvdan/sh/releases?per_page=100`]: [
        release(`v${sfn}`, '2026-10-01T00:00:00Z', shfmt(sfn, '5')),
      ],
    });
    const c = textOf(s.plan, CONSTANTS) ?? '';
    add(
      'shfmt: the four hashes in constants.sh move by the asset filenames the registry names',
      c.includes(`SHFMT_SHA256_LINUX_AMD64="${hex('5')}"`) &&
        c.includes(`SHFMT_SHA256_DARWIN_ARM64="${hex('9')}"`) &&
        envVal(textOf(s.plan, ENV) ?? '', 'SHFMT_VERSION') === sfn,
      s.refused
    );
    const sc = envVal(env, 'SHELLCHECK_VERSION');
    const sk = await plan('toolchain:shellcheck', patchOf(sc), {
      [`${GH}/repos/koalaman/shellcheck/releases?per_page=100`]: [
        release(`v${patchOf(sc)}`, '2026-10-01T00:00:00Z'),
      ],
    });
    add(
      'shellcheck: a release that publishes no digest is refused rather than moved with the old hashes',
      (sk.refused ?? '').includes('publishes no sha256 digest'),
      sk.refused ?? 'a plan was returned'
    );
    const wr = (/^readonly WRANGLER_VERSION="([^"]+)"/m.exec(live(CONSTANTS)) ?? [])[1] ?? '';
    const w = await plan('toolchain:wrangler', patchOf(wr), {});
    add(
      'wrangler: the constants.sh version moves',
      (textOf(w.plan, CONSTANTS) ?? '').includes(`WRANGLER_VERSION="${patchOf(wr)}"`),
      w.refused
    );
    add(
      'wrangler: the workers/account lockfile gets the canonical pass under the pinned npm, so npm ci accepts the moved pin',
      (w.plan?.steps ?? []).some(
        (st) =>
          st.cwd === 'workers/account' &&
          st.writes.some((x) => x.file === 'workers/account/package-lock.json') &&
          st.run ===
            `npx -y npm@${envVal(env, 'NPM_VERSION')} install --package-lock-only --ignore-scripts`
      ),
      (w.plan?.steps ?? []).map((st) => `${st.cwd}: ${st.run}`).join(' | ') ||
        (w.refused ?? 'no steps')
    );
    add(
      'wrangler: the workers/account/package.json pin moves with it',
      (textOf(w.plan, 'workers/account/package.json') ?? '').includes(
        `"wrangler": "${patchOf(wr)}"`
      ),
      w.refused
    );
    const noLock = await plan(
      'toolchain:wrangler',
      patchOf(wr),
      {},
      tree(LOCKS.filter((l) => l !== 'workers/account/package-lock.json'))
    );
    add(
      'wrangler: a package.json site with no lockfile beside it gets no lockfile pass, so none is created',
      noLock.plan !== undefined &&
        !noLock.plan.steps.some(
          (st) =>
            st.cwd === 'workers/account' ||
            st.writes.some((x) => x.file === 'workers/account/package-lock.json')
        ),
      noLock.refused ?? (noLock.plan?.steps ?? []).map((st) => `${st.cwd}: ${st.run}`).join(' | ')
    );
    const noNpmRoot = tree();
    const envPath = path.join(noNpmRoot, ENV);
    fs.writeFileSync(
      envPath,
      fs
        .readFileSync(envPath, 'utf8')
        .split('\n')
        .filter((l) => !l.startsWith('NPM_VERSION='))
        .join('\n')
    );
    const noNpm = await plan('toolchain:wrangler', patchOf(wr), {}, noNpmRoot);
    add(
      'wrangler: a toolchain.env without NPM_VERSION refuses the plan rather than planning an ambient npm',
      (noNpm.refused ?? '').includes('NPM_VERSION is missing'),
      noNpm.refused ?? 'a plan was returned'
    );
    const node = createToolchainDriver(stubUpstream({}), mutant);
    let why = '';
    try {
      await node.inspect(entryOf('toolchain:node'), ctxOf(tree()));
    } catch (err) {
      why = (err as Error).message;
    }
    add(
      'node: a pin the operator chooses is reported with its BLOCKER reason, not compared',
      why.startsWith('BLOCKER:'),
      why
    );
  }
  return cases;
}

async function main(): Promise<number> {
  try {
    if (process.argv[2] === '--mutant')
      return runControls(await build(process.argv[3] as ToolchainMutant));
    const { clean, mutantFailures } = await proveMutants(TOOLCHAIN_MUTANTS, build);
    const bad = runControls(clean);
    for (const m of mutantFailures) console.error(m);
    return bad + mutantFailures.length;
  } finally {
    removeRoots();
  }
}

if (isEntryPoint(import.meta.filename)) main().then((n) => process.exit(n === 0 ? 0 : 1));
