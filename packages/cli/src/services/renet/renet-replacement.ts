import { compareVersions } from '../update/updater.js';

/**
 * The named refusals of a provision. `RENET_DEV_ON_MACHINE`: a release binary would replace a dev build.
 * `RENET_DOWNGRADE_REFUSED`: an older release would replace a newer one. `RENET_BUILD_UNVERIFIED`: nothing
 * shows the binary is a build this CLI should deploy. `RENET_UPLOAD_REFUSED_IN_EXECUTOR`: a served request
 * reached the provisioner.
 */
export type RenetRefusalCode =
  | 'RENET_DEV_ON_MACHINE'
  | 'RENET_DOWNGRADE_REFUSED'
  | 'RENET_BUILD_UNVERIFIED'
  | 'RENET_UPLOAD_REFUSED_IN_EXECUTOR';

/** Where a Go binary's build info starts, for renet's own module: an embedded Go asset carries another. */
const RENET_MODINFO_START = Buffer.from('path\tgithub.com/rediacc/renet/cmd/renet\n');
/** The sentinel Go writes after the build info (cmd/go/internal/modload `infoEnd`). */
const GO_MODINFO_END = Buffer.from('f932433186182072008242104116d8f2', 'hex');
/** A bound on the build-info text, so a file with no end sentinel cannot make this read the rest. */
const MODINFO_MAX_BYTES = 256 * 1024;

/**
 * The version and revision a renet binary was stamped with, read from its own bytes. It runs nothing and
 * needs no Go toolchain, so it answers for a foreign-arch binary, on a machine with no `go` and inside the
 * executor image. A null field means the stamp is absent: a plain `go build` has no version ldflag, and
 * bytes that are not a renet build have neither.
 */
export function readRenetBuild(binary: Buffer): {
  version: string | null;
  revision: string | null;
} {
  const start = binary.indexOf(RENET_MODINFO_START);
  if (start < 0) return { version: null, revision: null };
  const window = binary.subarray(start, start + MODINFO_MAX_BYTES);
  const end = window.indexOf(GO_MODINFO_END);
  const info = (end < 0 ? window : window.subarray(0, end)).toString('latin1');
  return {
    version: /-X main\.Version=([^\s"]+)/.exec(info)?.[1] ?? null,
    revision: /vcs\.revision=([0-9a-f]+)/.exec(info)?.[1] ?? null,
  };
}

function bareVersion(version: string): string {
  return version.replace(/^v/, '');
}

/** A dev build: `build.sh dev` appends `-dev`, and the placeholder's core is 0.0.0, so it sorts below every release. */
function isDevVersion(version: string): boolean {
  return version.endsWith('-dev') || bareVersion(version).split('-')[0] === '0.0.0';
}

interface RenetReplacement {
  /** This CLI's VERSION. */
  cli: string;
  /** Whether the local binary is the one embedded in a SEA, built with the CLI as one unit. */
  embedded: boolean;
  /** The version stamped into the local binary; null when it carries none. */
  local: string | null;
  /** The version the machine's renet reports; null when it reports none. */
  running: string | null;
  /** The machine, for the message. */
  host: string;
}

type Refusal = { code: RenetRefusalCode; message: string };

/**
 * The verdict when the local binary carries no stamp or is a dev build, which the machine's own version cannot
 * overrule: null admits the replacement, a refusal names it, undefined means a stamped release was found and
 * the version comparison decides.
 */
function decideUnstampedOrDevLocal(
  r: RenetReplacement,
  running: string,
  unverified: (detail: string) => Refusal
): Refusal | null | undefined {
  const cliIsDev = isDevVersion(r.cli);
  if (r.local === null) {
    if (cliIsDev && isDevVersion(running)) return null;
    return unverified('The local renet binary carries no version stamp');
  }
  if (!isDevVersion(r.local)) return undefined;
  if (cliIsDev) return null;
  return unverified(`This CLI (v${r.cli}) holds a dev renet (v${r.local})`);
}

/**
 * Whether the local binary may replace the renet a machine runs, or the named refusal.
 *
 * A dev build's version says nothing about its age, so a release can never be shown to be newer than one:
 * only a dev CLI, deploying its own dev build, moves a machine onto or between dev builds. Otherwise the
 * machine's version must not be newer, and a binary outside a SEA must carry the version of the CLI sending
 * it, which is what shows it to be this CLI's build (the proxy image's 0.0.0-dev bundle held a 2.4.0 renet).
 * A machine whose renet reports no version has nothing to compare, and stays repairable.
 */
export function decideRenetReplacement(
  r: RenetReplacement
): { code: RenetRefusalCode; message: string } | null {
  if (r.running === null) return null;
  const override = 'set REDIACC_ALLOW_DOWNGRADE=1 to force it';
  const unverified = (detail: string) => ({
    code: 'RENET_BUILD_UNVERIFIED' as const,
    message: `${detail}, so nothing shows it is a build this CLI should deploy to ${r.host}, which runs renet v${r.running}. Rebuild with ./rdc.sh or run \`rdc update\`, or ${override}.`,
  });

  const unstampedOrDev = decideUnstampedOrDevLocal(r, r.running, unverified);
  if (unstampedOrDev !== undefined) return unstampedOrDev;
  if (r.local === null) return null;
  if (isDevVersion(r.running)) {
    return {
      code: 'RENET_DEV_ON_MACHINE',
      message: `${r.host} runs the dev build renet v${r.running}, and a release (v${r.local}) cannot be shown to be newer than it. Deploy a fresh dev build with ./rdc.sh, or, to move the machine back to the release, ${override}.`,
    };
  }
  if (compareVersions(r.local, r.running) < 0) {
    return {
      code: 'RENET_DOWNGRADE_REFUSED',
      message: `${r.host} runs renet v${r.running}, newer than the local binary v${r.local}. Run \`rdc update\` to upgrade this CLI, or ${override}.`,
    };
  }
  if (!r.embedded && bareVersion(r.local) !== bareVersion(r.cli)) {
    return unverified(`This CLI (v${r.cli}) holds a renet stamped v${r.local}`);
  }
  return null;
}
