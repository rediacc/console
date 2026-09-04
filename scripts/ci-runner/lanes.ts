/**
 * Which quality job a gate can run in, DERIVED from the workflow rather than typed here.
 *
 * WHY THIS EXISTS. A gate's job is chosen by hand today, and a wrong choice is silent
 * until CI: check:ci-docker-npm-pins landed in `quality-static`, which checks out no
 * submodules, so `private/account/Dockerfile` dropped out of its enumeration and its
 * two entirely correct exclusions were reported as dead entries (CI job 100870135489).
 * check_syncpack_sources.py carries the identical scar from its own first run. Both
 * gates enumerate with `--recurse-submodules`; neither could say so anywhere a tool
 * would read.
 *
 * ONLY THE COST ORDER IS DECLARED HERE. Capabilities are read out of ci-quality.yml on
 * every call, because a table of them would be a second copy of the workflow and would
 * drift the first time a job changed. A lane whose job is no longer in the file is
 * REFUSED rather than skipped -- a missing lane silently narrows placement, which is
 * how a gate ends up somewhere cheaper and blinder than it needs.
 *
 * The cost order is cheapest-first: slim runners with no node before ubuntu-latest,
 * and within those, fewer setup steps before more. Placement picks the FIRST lane whose
 * capabilities are a superset of the gate's needs, so a gate that needs nothing lands
 * in the cheapest lane and one that needs submodules cannot land in a lane without them.
 */

/** Cheapest first. A job absent from the workflow is an error, never a skip. */
const LANE_ORDER = [
  'quality-static',
  'quality-branch',
  'quality-submodule-branches',
  'quality-code',
  'quality-content',
  'quality-i18n',
  'quality-security',
  'quality-packages',
  'quality-www-build',
  'quality-go',
] as const;

export interface LaneCapabilities {
  job: string;
  /** '' when the job declares none (it inherits the workflow default). */
  runsOn: string;
  timeoutMinutes: number | null;
  /** Every submodule path the job checks out; ['*'] when it takes all of them. */
  submodules: string[];
  /** setup-workspace ran, so node and the workspace deps are present. */
  node: boolean;
  /** Extra toolchains this job installs. */
  tools: string[];
}

const JOB_RE = /^ {2}([A-Za-z0-9_-]+):\s*$/;

/**
 * Capabilities of every job in one workflow, parsed by hand.
 *
 * A hand parser rather than PyYAML/`yaml`: this must run in the fast lane with no
 * dependency, and a gate that imports one dies with ModuleNotFoundError on a clean
 * runner while passing locally -- check:ci-python-gate-deps caught exactly that on a
 * gate written earlier tonight.
 */
export function laneCapabilities(workflowText: string): Map<string, LaneCapabilities> {
  const out = new Map<string, LaneCapabilities>();
  let job: LaneCapabilities | null = null;
  let inJobs = false;

  for (const raw of workflowText.split('\n')) {
    if (/^jobs:\s*$/.test(raw)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (raw !== '' && !/^\s/.test(raw) && !raw.startsWith('#')) break;

    const m = JOB_RE.exec(raw);
    if (m) {
      job = {
        job: m[1],
        runsOn: '',
        timeoutMinutes: null,
        submodules: [],
        node: false,
        tools: [],
      };
      out.set(m[1], job);
      continue;
    }
    if (job === null) continue;
    // PROSE IS NOT A CAPABILITY, and this module nearly shipped believing it was. The
    // first version matched `PyYAML` and `setup-go` anywhere in the job, and
    // quality-code MENTIONS both in comments ("ruff was pinned twice, PyYAML four
    // times", "actions/setup-go adds that directory itself") while installing neither.
    // It would therefore have placed a yaml-needing gate in a job with no PyYAML --
    // the exact silent mis-placement this file exists to prevent, committed by the
    // file itself. Caught by checking the derived table against the workflow instead
    // of trusting it.
    if (/^\s*#/.test(raw)) continue;

    const runsOn = /^\s{4}runs-on:\s*(\S+)\s*$/.exec(raw);
    if (runsOn) job.runsOn = runsOn[1];

    const timeout = /^\s{4}timeout-minutes:\s*(\d+)\s*$/.exec(raw);
    if (timeout) job.timeoutMinutes = Number(timeout[1]);

    // `submodules: true` on a checkout takes every submodule; a targeted
    // `git submodule update --init <path>` takes exactly one. Both are real, and
    // conflating them is how a gate needing renet lands in the job that only takes
    // account (quality-i18n does exactly that).
    if (/^\s+submodules:\s*(true|'true'|"true"|recursive)\s*$/.test(raw)) job.submodules = ['*'];
    const targeted = /git submodule update --init(?:\s+--depth\s+\d+)?\s+(private\/[\w-]+)/.exec(
      raw
    );
    if (targeted && !job.submodules.includes('*') && !job.submodules.includes(targeted[1])) {
      job.submodules.push(targeted[1]);
    }

    if (/^\s+(?:-\s+)?uses:\s*\.\/\.github\/actions\/setup-workspace/.test(raw)) job.node = true;
    if (/^\s+(?:-\s+)?uses:\s*actions\/setup-go/.test(raw) && !job.tools.includes('go')) {
      job.tools.push('go');
    }
    if (/pip install[^\n]*\bruff\b/.test(raw) && !job.tools.includes('ruff')) {
      job.tools.push('ruff');
    }
    if (/pip install[^\n]*PyYAML/.test(raw) && !job.tools.includes('python-yaml')) {
      job.tools.push('python-yaml');
    }
  }
  return out;
}

/** Does this lane provide everything the gate asked for? */
export function satisfies(lane: LaneCapabilities, needs: readonly string[]): boolean {
  return needs.every((need) => {
    if (need === 'submodules') return lane.submodules.length > 0;
    if (need.startsWith('private/')) {
      return lane.submodules.includes('*') || lane.submodules.includes(need);
    }
    if (need === 'node') return lane.node;
    return lane.tools.includes(need);
  });
}

/**
 * The cheapest lane that can run this gate, or a refusal saying what is missing.
 *
 * A LANE NAMED IN LANE_ORDER BUT ABSENT FROM THE WORKFLOW IS AN ERROR. Skipping it
 * would quietly narrow the choice and push gates into lanes they do not belong in,
 * which is the failure this module exists to prevent -- so the table cannot rot
 * silently against the file it describes.
 */
export function placeGate(
  caps: Map<string, LaneCapabilities>,
  needs: readonly string[]
): { lane: string } | { error: string } {
  const missing = LANE_ORDER.filter((j) => !caps.has(j));
  if (missing.length > 0) {
    return {
      error:
        `LANE_ORDER names ${missing.join(', ')}, which the workflow no longer defines. ` +
        'Placement cannot be trusted until the list and the file agree.',
    };
  }
  for (const j of LANE_ORDER) {
    const lane = caps.get(j);
    if (lane && satisfies(lane, needs)) return { lane: j };
  }
  return { error: `no lane provides all of: ${needs.join(', ')}` };
}
