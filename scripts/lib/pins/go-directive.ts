/**
 * Which Go a `go install`ed devcontainer tool needs, read from its go.mod on the module proxy
 * (worklist #e023eb0d).
 *
 * On 2026-10-18 `npm run pins -- bump devcontainer:gopls` moved gopls 0.23.0 -> 0.24.0 and its
 * gate passed, but gopls 0.24.0's go.mod says `go 1.27.0` while the devcontainer builds Go
 * GO_VERSION=1.26.9 (.devcontainer/toolchain.env) with GOTOOLCHAIN=local, so the image build
 * failed (`gopls@v0.24.0 requires go >= 1.27.0 (running go 1.26.9; GOTOOLCHAIN=local)`). A
 * release like that is not a candidate: the devcontainer driver marks it ineligible (so a bump
 * takes the newest release that builds) and the freshness gate prints it as deferred, naming the
 * Go it needs, instead of calling the pin behind.
 *
 * FAIL CLOSED. A go.mod the proxy did not answer, or one with no `go` line, is never read as
 * eligible: the caller refuses the pin (driver) or reds it (gate) with the reason.
 *
 * The comparison is Go's own: GOTOOLCHAIN=local refuses a module whose `go` directive is newer
 * than the running toolchain, patch included (`go 1.26.10` does not build on 1.26.9), so the
 * whole version is compared, not only major.minor.
 */
import { UnreadableListing } from '../upstream.js';

export const TOOLCHAIN_ENV = '.devcontainer/toolchain.env';

/** The image's Go (GO_VERSION in .devcontainer/toolchain.env), or null when the file names none. */
export function imageGoVersion(toolchainEnv: string | null): string | null {
  return toolchainEnv === null ? null : (/^GO_VERSION=(\S+)$/m.exec(toolchainEnv)?.[1] ?? null);
}

/** The `go` directive of a go.mod, or null when it has none. */
export function goDirective(modText: string): string | null {
  return (
    /^go[ \t]+(\d+\.\d+(?:\.\d+)?(?:(?:rc|beta)\d+)?)[ \t]*(?:\/\/.*)?$/m.exec(modText)?.[1] ?? null
  );
}

/** Go's version order for `1.N[.P]`, `1.NrcK`, `1.NbetaK`: 1.27beta1 < 1.27rc1 < 1.27 = 1.27.0 < 1.27.1. */
function goKey(v: string): number[] {
  const m = /^(\d+)\.(\d+)(?:\.(\d+))?(?:(rc|beta)(\d+))?$/.exec(v);
  if (!m) throw new UnreadableListing(`"${v}" is not a Go version`);
  const pre = m[4] === 'beta' ? -2 : m[4] === 'rc' ? -1 : 0;
  return [Number(m[1]), Number(m[2]), pre === 0 ? Number(m[3] ?? 0) : -1, pre, Number(m[5] ?? 0)];
}

/** True when a module whose go.mod says `go <need>` does not build on Go `have` with GOTOOLCHAIN=local. */
export function goTooNew(need: string, have: string): boolean {
  const a = goKey(need);
  const b = goKey(have);
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] > b[i];
  return false;
}

/** The proxy's escaped module path (an upper-case letter is `!` and its lower case). */
export const escapeModule = (m: string): string =>
  m.replace(/[A-Z]/g, (c) => `!${c.toLowerCase()}`);

/** The proxy URL of a module version's go.mod. */
export const goModUrl = (module: string, version: string): string =>
  `https://proxy.golang.org/${escapeModule(module)}/@v/v${version.replace(/^v/, '')}.mod`;

/**
 * The `go` directive of `module@version`, read through `fetchText` (which throws when the proxy
 * does not answer). A go.mod with no `go` line throws UnreadableListing: its Go cannot be judged,
 * so it is not offered.
 */
export async function goNeeds(
  fetchText: (url: string) => Promise<string>,
  module: string,
  version: string
): Promise<string> {
  const url = goModUrl(module, version);
  const need = goDirective(await fetchText(url));
  if (need === null)
    throw new UnreadableListing(
      `${module}@v${version}: the go.mod at ${url} has no \`go\` line, so the Go it needs cannot be judged`
    );
  return need;
}

/** The deferral wording the driver's verdict and the gate's deferred line share. */
export const needsGoWhy = (module: string, version: string, need: string, have: string): string =>
  `${module}@v${version} needs go ${need} (its go.mod), newer than the image's Go ${have} (${TOOLCHAIN_ENV} GO_VERSION, GOTOOLCHAIN=local); it waits for \`npm run pins -- bump toolchain:go\``;
