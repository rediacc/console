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
import '../driver.js';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';
import { WK_GH_API_BASE } from '../../../../packages/shared/src/config/well-known.generated.js';
import { type ControlCase, runControls } from '../../controls.js';
import { githubApiHeaders } from '../../github-token.js';
import { askUpstream } from '../../upstream.js';
import { keyOf, type PinPlan, PlanRefused } from '../driver.js';
import { loadRegistry, siteMatches } from '../registry.js';
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

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  main().then((n) => process.exit(n === 0 ? 0 : 1));
