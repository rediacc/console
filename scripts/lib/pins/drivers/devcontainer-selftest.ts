/**
 * Controls for the devcontainer driver over a temporary copy of the live Dockerfiles and an
 * upstream answered from a URL map.
 *
 *   npx tsx scripts/lib/pins/drivers/devcontainer-selftest.ts             # the controls and their mutant
 *   npx tsx scripts/lib/pins/drivers/devcontainer-selftest.ts --live      # the registry's asset filenames against upstream
 *
 * `--live` reads the real release APIs (GitHub, and gitlab.com for glab) and checks that each
 * `asset` filename a hashed devcontainer site names exists upstream and carries the digest the
 * Dockerfile pins today. A registry asset written from a Dockerfile URL and never checked
 * upstream would fail here by name.
 */
import { isEntryPoint } from '../../entry-point.js';
import '../driver.js';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { WK_GH_API_BASE } from '../../../../packages/shared/src/config/well-known.generated.js';
import { type ControlCase, runControls } from '../../controls.js';
import { githubApiHeaders } from '../../github-token.js';
import { askUpstream } from '../../upstream.js';
import { keyOf, type PinPlan, PlanRefused } from '../driver.js';
import { goDirective, goModUrl, goTooNew } from '../go-directive.js';
import { loadRegistry, siteMatches } from '../registry.js';
import { judge } from '../soak.js';
import {
  createDevcontainerDriver,
  DEVCONTAINER_MUTANTS,
  type DevcontainerMutant,
} from './devcontainer.js';
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
const DF = '.devcontainer/Dockerfile';

const tree = (): string =>
  makeTree(
    [
      DF,
      '.ci/docker/web/Dockerfile',
      '.devcontainer/start-vscode.sh',
      'private/renet/.ci/scripts/quality/lint.sh',
      '.devcontainer/toolchain.env',
    ],
    {}
  );

const live = (rel: string): string => fs.readFileSync(path.join(LIVE_ROOT, rel), 'utf8');
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

async function build(mutant: DevcontainerMutant | null): Promise<ControlCase[]> {
  const cases: ControlCase[] = [];
  const add = (name: string, ok: boolean, detail?: string): void => {
    cases.push({ name, ok, detail });
  };
  const df = live(DF);
  const plan = async (id: string, to: string, answers: Record<string, string | object>) => {
    const drv = createDevcontainerDriver(stubUpstream(answers), mutant);
    try {
      return {
        plan: await drv.plan(entryOf(id), { version: to, publishedMs: 0 }, ctxOf(tree())),
      };
    } catch (err) {
      if (err instanceof PlanRefused) return { refused: err.message };
      throw err;
    }
  };

  // -- bw: a monorepo prefix, a version and both hashes by asset filename.
  {
    const v = patchOf(arg(df, 'BW_VERSION'));
    const list = `${GH}/repos/bitwarden/clients/releases?per_page=100`;
    const full = {
      [`bw-linux-${v}.zip`]: hex('a'),
      [`bw-linux-arm64-${v}.zip`]: hex('b'),
    };
    const r = await plan('devcontainer:bw', v, {
      [list]: [
        release('web-v9999.1.0', '2026-10-01T00:00:00Z'),
        release(`cli-v${v}`, '2026-10-01T00:00:00Z', full),
      ],
    });
    const out = textOf(r.plan, DF);
    add(
      'bw: the version and both sha256 ARGs move together, by the asset filenames the registry names',
      !!out &&
        arg(out, 'BW_VERSION') === v &&
        arg(out, 'BW_SHA256_AMD64') === hex('a') &&
        arg(out, 'BW_SHA256_ARM64') === hex('b'),
      r.refused
    );
    const partial = await plan('devcontainer:bw', v, {
      [list]: [release(`cli-v${v}`, '2026-10-01T00:00:00Z', { [`bw-linux-${v}.zip`]: hex('a') })],
    });
    add(
      'bw: a release with no digest for one hashed asset is refused, not moved with a stale hash',
      (partial.refused ?? '').includes('publishes no sha256 digest'),
      partial.refused ?? 'a plan was returned'
    );
    const drv = createDevcontainerDriver(
      stubUpstream({
        [list]: [
          release('web-v9999.1.0', '2026-10-09T00:00:00Z'),
          release(`cli-v${v}`, '2026-10-01T00:00:00Z', full),
          release(`cli-v${arg(df, 'BW_VERSION')}`, '2026-09-01T00:00:00Z'),
        ],
      }),
      mutant
    );
    const i = await drv.inspect(entryOf('devcontainer:bw'), ctxOf(tree()));
    add(
      'bw inspect: only the cli- tags are releases of the pin, newer than the pinned version',
      i.releases.length === 1 &&
        i.releases[0].version === v &&
        i.releases[0].publishedMs === Date.parse('2026-10-01T00:00:00Z'),
      JSON.stringify(i)
    );
  }

  // -- the eight ARGs outside the freshness gate's list.
  {
    const v = patchOf(arg(df, 'BTM_VERSION'));
    const r = await plan('devcontainer:btm', v, {
      [`${GH}/repos/ClementTsang/bottom/releases?per_page=100`]: [
        release(v, '2026-10-01T00:00:00Z', {
          [`bottom_${v}-1_amd64.deb`]: hex('c'),
          [`bottom_${v}-1_arm64.deb`]: hex('d'),
        }),
      ],
    });
    const out = textOf(r.plan, DF);
    add(
      'bottom (outside the freshness gate): version and both .deb hashes move',
      !!out &&
        arg(out, 'BTM_VERSION') === v &&
        arg(out, 'BTM_SHA256_AMD64') === hex('c') &&
        arg(out, 'BTM_SHA256_ARM64') === hex('d'),
      r.refused
    );
    const o = patchOf(arg(df, 'OPENVSCODE_VERSION'));
    const ov = await plan('devcontainer:openvscode', o, {
      [`${GH}/repos/gitpod-io/openvscode-server/releases?per_page=100`]: [
        release(`openvscode-server-v${o}`, '2026-10-01T00:00:00Z', {
          [`openvscode-server-v${o}-linux-x64.tar.gz`]: hex('e'),
          [`openvscode-server-v${o}-linux-arm64.tar.gz`]: hex('f'),
        }),
      ],
    });
    const od = textOf(ov.plan, DF);
    const sv = textOf(ov.plan, '.devcontainer/start-vscode.sh');
    add(
      'openvscode-server: both tarball hashes and the start-vscode.sh default move with the ARG',
      !!od &&
        arg(od, 'OPENVSCODE_SHA256_X64') === hex('e') &&
        arg(od, 'OPENVSCODE_SHA256_ARM64') === hex('f') &&
        !!sv?.includes(`DEFAULT_VERSION="${o}"`),
      ov.refused
    );
    const gv = patchOf(arg(df, 'GLAB_VERSION'));
    const drv = createDevcontainerDriver(stubUpstream({}), mutant);
    let why = '';
    try {
      await drv.inspect(entryOf('devcontainer:glab'), ctxOf(tree()));
    } catch (err) {
      why = (err as Error).message;
    }
    add(
      'glab (a gitlab.com release): reported as not compared with its BLOCKER reason, never guessed',
      why.startsWith('BLOCKER:') && gv !== '',
      why
    );
  }

  // -- version-only pins through npm and the Go proxy, and a pin written in two repos.
  {
    const cur = arg(df, 'CODEX_VERSION');
    const nv = patchOf(cur);
    const up = stubUpstream({
      'https://registry.npmjs.org/@openai%2Fcodex': {
        versions: { [cur]: {}, [nv]: {}, '9.9.9-beta.1': {} },
        time: {
          [cur]: '2026-09-01T00:00:00Z',
          [nv]: '2026-10-02T00:00:00Z',
          '9.9.9-beta.1': '2026-10-03T00:00:00Z',
        },
      },
    });
    const drv = createDevcontainerDriver(up, mutant);
    const i = await drv.inspect(entryOf('devcontainer:codex'), ctxOf(tree()));
    add(
      'codex: the npm registry time map dates the release and a prerelease is not offered',
      i.releases.length === 1 &&
        i.releases[0].version === nv &&
        i.releases[0].publishedMs === Date.parse('2026-10-02T00:00:00Z'),
      JSON.stringify(i)
    );
    const sc = arg(df, 'STATICCHECK_VERSION');
    const sv = patchOf(sc);
    const base = 'https://proxy.golang.org/honnef.co/go/tools/@v';
    const go = createDevcontainerDriver(
      stubUpstream({
        [`${base}/list`]: `v${sc}\nv${sv}\nv${sv}-rc1\nv2026.1.1\n`,
        [`${base}/v${sv}.info`]: { Time: '2026-10-05T00:00:00Z' },
        [`${base}/v2026.1.1.info`]: { Time: '2026-10-06T00:00:00Z' },
        [goModUrl('honnef.co/go/tools', sv)]: 'module honnef.co/go/tools\n\ngo 1.20\n',
        [goModUrl('honnef.co/go/tools', '2026.1.1')]: 'module honnef.co/go/tools\n\ngo 1.20.0\n',
      }),
      mutant
    );
    const gi = await go.inspect(entryOf('devcontainer:staticcheck'), ctxOf(tree()));
    add(
      'staticcheck: the Go proxy lists module versions, newest first, dated by .info, prerelease excluded',
      gi.releases.map((r) => r.version).join(',') === `2026.1.1,${sv}` &&
        gi.releases[1].publishedMs === Date.parse('2026-10-05T00:00:00Z'),
      JSON.stringify(gi)
    );
    const gl = arg(df, 'GOLANGCILINT_VERSION');
    const gn = patchOf(gl);
    const r = await plan('devcontainer:golangcilint', gn, {
      [`${GH}/repos/golangci/golangci-lint/releases?per_page=100`]: [
        release(`v${gn}`, '2026-10-01T00:00:00Z'),
      ],
      [goModUrl('github.com/golangci/golangci-lint/v2', gn)]:
        'module github.com/golangci/golangci-lint/v2\n\ngo 1.26.0\n',
    });
    const lint = textOf(r.plan, 'private/renet/.ci/scripts/quality/lint.sh');
    add(
      'golangci-lint: the Dockerfile ARG and the renet lint.sh pin move in one plan',
      !!lint?.includes(`GOLANGCI_VERSION="${gn}"`) &&
        arg(textOf(r.plan, DF) ?? '', 'GOLANGCILINT_VERSION') === gn,
      r.refused
    );
    const ab = arg(df, 'AGENT_BROWSER_VERSION');
    const abn = patchOf(ab);
    const web = await plan('devcontainer:agent-browser', abn, {});
    add(
      'agent-browser: the devcontainer Dockerfile and the web image Dockerfile move together',
      !!web.plan &&
        arg(textOf(web.plan, DF) ?? '', 'AGENT_BROWSER_VERSION') === abn &&
        arg(textOf(web.plan, '.ci/docker/web/Dockerfile') ?? '', 'AGENT_BROWSER_VERSION') === abn,
      web.refused
    );
  }

  // -- a `go install`ed pin takes only a release whose go.mod builds on the image's Go (worklist #e023eb0d: gopls 0.24.0 says `go 1.27.0`, the image builds a 1.26.x Go with GOTOOLCHAIN=local). Mutant `ignore-go` offers every release whatever its go.mod needs, which turns the first, second and fourth controls red; with it the driver never reads a go.mod, so the third (a proxy failure refuses) goes red too.
  {
    const cur = arg(df, 'GOPLS_VERSION');
    const fits = patchOf(cur);
    const tooNew = '999.0.0';
    const mod = 'golang.org/x/tools/gopls';
    const list = `${GH}/repos/golang/tools/releases?per_page=100`;
    const listing = [
      release(`gopls/v${tooNew}`, '2026-10-02T00:00:00Z'),
      release(`gopls/v${fits}`, '2026-10-01T00:00:00Z'),
      release(`gopls/v${cur}`, '2026-09-01T00:00:00Z'),
    ];
    const gomods = {
      [goModUrl(mod, tooNew)]: `module ${mod}\n\ngo 1.999.0\n`,
      [goModUrl(mod, fits)]: `module ${mod}\n\ngo 1.20.0 // older than any image Go\n`,
    };
    const soak = (r: {
      version: string;
      publishedMs: number | null;
      verdict?: { eligible: boolean; why: string };
    }) =>
      judge(entryOf('devcontainer:gopls'), r, Date.parse('2026-10-10T00:00:00Z'), 86_400_000, false)
        .eligible;
    const mixed = await createDevcontainerDriver(
      stubUpstream({ [list]: listing, ...gomods }),
      mutant
    ).inspect(entryOf('devcontainer:gopls'), ctxOf(tree()));
    const firstEligible = mixed.releases.find(soak)?.version;
    add(
      'gopls: a release whose go.mod needs a newer Go than the image is ineligible, naming the Go it needs, and the newest one that builds is taken',
      mixed.releases.length === 2 &&
        mixed.releases[0].verdict?.eligible === false &&
        (mixed.releases[0].verdict?.why ?? '').includes('needs go 1.999.0') &&
        firstEligible === fits,
      JSON.stringify(mixed)
    );
    const onlyNew = await createDevcontainerDriver(
      stubUpstream({ [list]: [listing[0], listing[2]], ...gomods }),
      mutant
    ).inspect(entryOf('devcontainer:gopls'), ctxOf(tree()));
    add(
      'gopls: when every newer release needs a newer Go, none is eligible (the pin waits, it is not behind)',
      onlyNew.releases.length === 1 && !onlyNew.releases.some(soak),
      JSON.stringify(onlyNew)
    );
    let failed = '';
    try {
      await createDevcontainerDriver(stubUpstream({ [list]: listing }), mutant).inspect(
        entryOf('devcontainer:gopls'),
        ctxOf(tree())
      );
    } catch (err) {
      failed = (err as Error).message;
    }
    const failedPlan = await plan('devcontainer:gopls', fits, { [list]: listing });
    add(
      'gopls: a go.mod the proxy does not answer fails closed: inspect throws and the plan is refused, never eligible',
      failed.includes('.mod') && (failedPlan.refused ?? '').includes('.mod'),
      `inspect: ${failed || 'answered'}; plan: ${failedPlan.refused ?? 'a plan was returned'}`
    );
    const refused = await plan('devcontainer:gopls', tooNew, { [list]: listing, ...gomods });
    add(
      'gopls: a plan to a release whose go.mod needs a newer Go is refused by name',
      (refused.refused ?? '').includes('needs go 1.999.0'),
      refused.refused ?? 'a plan was returned'
    );
  }

  // -- Go's own version order, as GOTOOLCHAIN=local applies it: the patch counts, and a prerelease sorts before its release.
  {
    const pairs: [string, string, boolean][] = [
      ['1.27.0', '1.26.5', true],
      ['1.26.0', '1.26.5', false],
      ['1.26.10', '1.26.5', true],
      ['1.26.5', '1.26.5', false],
      ['1.27rc1', '1.26.5', true],
      ['1.27rc1', '1.27.0', false],
      ['1.27', '1.27.0', false],
    ];
    const wrong = pairs.filter(([need, have, want]) => goTooNew(need, have) !== want);
    add(
      'go directive: a go.mod newer than the image Go (patch and prerelease included) does not build, an older or equal one does',
      wrong.length === 0 &&
        goDirective('module x\n\ngo 1.27.0\n\ntoolchain go1.27.1\n') === '1.27.0' &&
        goDirective('module x\n') === null,
      JSON.stringify(wrong)
    );
  }

  // -- a site that moved refuses the whole pin.
  {
    const root = tree();
    const ctx = ctxOf(root);
    ctx.overlay.set(DF, `${df}\nARG BW_VERSION=0.0.0\n`);
    const drv = createDevcontainerDriver(stubUpstream({}), mutant);
    let refused = '';
    try {
      await drv.plan(entryOf('devcontainer:bw'), { version: '99.0.0', publishedMs: 0 }, ctx);
    } catch (err) {
      refused = err instanceof PlanRefused ? err.message : `unexpected: ${err}`;
    }
    add(
      'a site matching other than its expected count refuses the whole pin',
      refused.includes('matches 2 time(s)'),
      refused
    );
  }
  return cases;
}

/** `--live`: each hashed devcontainer site's asset exists upstream with the digest the Dockerfile pins. */
async function liveAssets(): Promise<number> {
  const df = live(DF);
  const cases: ControlCase[] = [];
  const gh = async (url: string): Promise<unknown> =>
    JSON.parse(
      (await askUpstream({ url, headers: githubApiHeaders('rediacc-pins-selftest'), who: url }))
        .body
    );
  for (const e of loadRegistry().entries.filter((x) => x.driver === 'devcontainer')) {
    const hashed = e.sites.filter((s) => s.role.startsWith('sha256:'));
    if (hashed.length === 0) continue;
    const version =
      siteMatches(e.sites.find((s) => s.role === 'version') ?? e.sites[0], df)[0]?.value ?? '';
    const digests = new Map<string, string>();
    if (e.source.type === 'github-release' && e.source.repo) {
      const rel = (await gh(
        `${GH}/repos/${e.source.repo}/releases/tags/${e.source.tagPrefix ?? ''}${version}`
      )) as { assets?: Array<{ name?: string; digest?: string }> };
      for (const a of rel.assets ?? [])
        if (a.name && a.digest?.startsWith('sha256:')) digests.set(a.name, a.digest.slice(7));
    } else if (e.id === 'devcontainer:glab') {
      const url = `https://gitlab.com/api/v4/projects/gitlab-org%2Fcli/packages/generic/glab/${version.replaceAll('.', '%2E')}/checksums%2Etxt`;
      for (const line of (await askUpstream({ url, headers: {}, who: url })).body.split('\n')) {
        const [d, n] = line.trim().split(/\s+/);
        if (d && n) digests.set(n, d);
      }
    }
    for (const s of hashed) {
      const asset = (s.asset ?? '').replaceAll('{version}', version);
      const pinned = arg(df, s.arg ?? '');
      add2(
        cases,
        `${e.id} ${s.role}: ${asset} exists upstream with the pinned digest`,
        digests.get(asset) === pinned,
        `upstream has ${digests.get(asset) ?? 'no such asset'}, pinned ${pinned}`
      );
    }
  }
  return runControls(cases);
}

const add2 = (cases: ControlCase[], name: string, ok: boolean, detail?: string): void => {
  cases.push({ name, ok, detail });
};

async function main(): Promise<number> {
  try {
    if (process.argv[2] === '--live') return await liveAssets();
    if (process.argv[2] === '--mutant')
      return runControls(await build(process.argv[3] as DevcontainerMutant));
    const { clean, mutantFailures } = await proveMutants(DEVCONTAINER_MUTANTS, build);
    const bad = runControls(clean);
    for (const m of mutantFailures) console.error(m);
    return bad + mutantFailures.length;
  } finally {
    removeRoots();
  }
}

if (isEntryPoint(import.meta.filename)) main().then((n) => process.exit(n === 0 ? 0 : 1));
