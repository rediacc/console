"""Port of `.ci/scripts/test/gates/test-policy-path.sh`, retired in W7 P5.

`scripts/lib/policy-paths.ts` is the ONE seam that says where a suppression policy file lives. Fifteen allow / block / exempt files used to sit at the repository root with their readers mostly hard-coding that, and four of them read a BARE RELATIVE NAME which was correct only because the reader happened to `cd` to the repo root first. The move to `.ci/policy` landed 2026-09-06 at
b80552370.

THE THREE PROPERTIES PINNED HERE, each of them a refusal, and they are the twin's words because they are the reason the seam exists:

  1. PURE JOIN. `policyPath()` never touches the filesystem, so it answers the
     same string against a root containing nothing at all. A caller that cannot
     find the file gets its own ENOENT at its own path instead of the helper
     quietly resolving somewhere else.
  2. NO FALLBACK. Exactly one location at a time. A helper that tried the new
     location and fell back to the old one is precisely how a move half-lands
     with every gate still green.
  3. LOUD REFUSAL. An unknown name throws and names the valid set. Returning a
     plausible path for a typo reads to every consumer here as an EMPTY
     allowlist, which is indistinguishable from "nothing is suppressed".

Plus the liveness assertion that keeps the name list honest: every name the module knows must resolve to a file that is there TODAY.

WHY THE MODULE'S OWN CLI RATHER THAN AN IMPORT, carried over verbatim from the twin's reasoning. An earlier bash version generated a temp `.ts` that imported the module; that needed four more exports than any TypeScript caller wants, and `lint:unused` was right to refuse them. The workspace `tsx` binary is called directly rather than through `npx`, which also skips npx's
re-resolution -- and stdout and stderr are kept SEPARATE, because npx prints an unrelated "Unknown project config minimum-release-age" warning on stderr and the first run of the bash file compared a path against that warning.

NO `xdist_group`. Every case here reads the real tree and writes only into its own `mktemp -d`, and the one filesystem mutation (the fixture root) is created and removed inside a single case. Nothing is bound, nothing global is mutated.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

LIB = paths.from_root("scripts", "lib", "policy-paths.ts")
TSX = paths.from_root("node_modules", ".bin", "tsx")

# The floor the twin spells `$((n >= 15))`. Fifteen files travelled in the move,
# so a list that has collapsed below that is a reader pointed at nothing.
MIN_KNOWN_NAMES = 15


def pp(gate, *args: str) -> harness.RunResult:
    """Drive the module's own CLI from the repo root, streams kept apart."""
    if not TSX.is_file():
        gate.log_fail(
            "the workspace tsx binary is missing at %s, so this case could not run at "
            "all -- which is a FAILURE and not a pass. Fix: npm install && npm run "
            "install:natives" % paths.relative_to_root(TSX)
        )
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    return harness.run([str(TSX), str(LIB), *args], cwd=paths.repo_root())


def all_paths(gate) -> list[str]:
    """`pp --all-paths`, one path per line.

    ONE process, not one per name. The obvious loop calling `--path <name>` fifteen times cost fifteen node startups and made the bash twin the third-slowest gate in the quick lane; the answers are identical because `--all-paths` is `policyPath()` mapped over the same name list.
    """
    result = pp(gate, "--all-paths")
    gate.assert_exit_code(0, result.rc, "--all-paths must succeed (stderr: %s)" % result.err)
    return [line for line in result.out.splitlines() if line.strip()]


def test_pure_join_needs_no_filesystem(gate):
    gate.log_test("policyPath resolves against a root that contains nothing")
    with harness.temp_dir() as empty:
        # Deliberately EMPTY: no .ci, no .ci/policy, no dotfiles, nothing. A helper that stat'ed anything would have to either throw or answer a second location here; a pure join cannot tell the difference.
        result = pp(gate, "--path", ".deps-upgrade-blocklist", "--root", str(empty))
        gate.assert_eq(
            result.out.strip(),
            str(empty / ".ci" / "policy" / ".deps-upgrade-blocklist"),
            "resolves against a root containing no .ci directory at all",
        )
        # The bash twin's second assertion is `rmdir`, which REFUSES a non-empty directory, so a helper that had touched, cached or created anything under the fixture root would fail that line. `iterdir()` is the same claim stated positively: nothing was created either. It is spelled this way rather than as `find | wc -l` for the reason the twin records -- check:ci-silent-failures
        # refuses an unguarded pipeline there, and it is right to, since a find that errored would count 0 and read as success.
        leftovers = sorted(p.name for p in empty.iterdir())
        gate.assert_eq(
            leftovers, [], "and the fixture root is still empty, so nothing was created either"
        )
    gate.log_pass("policyPath is a pure join: no stat, no readdir, no fallback")


def test_every_known_name_resolves_to_a_real_file(gate):
    gate.log_test("every name the module knows must be a file that exists today")
    found = all_paths(gate)
    missing = [p for p in found if not pathlib.Path(p).is_file()]
    gate.assert_eq(missing, [], "every known policy name resolves to a file that exists today")
    # ANTI-VACUITY. An empty name list would pass the loop above without checking anything, which is the class this repo keeps getting caught by.
    gate.assert_eq(
        len(found) >= MIN_KNOWN_NAMES,
        True,
        "and the name list is populated (%d names, floor %d), so the loop asserted something"
        % (len(found), MIN_KNOWN_NAMES),
    )
    gate.log_pass("all %d known policy names resolve to real files" % len(found))


def test_unknown_name_is_refused_loudly(gate):
    gate.log_test("a typo must be refused, not resolved to something plausible")
    result = pp(gate, "--path", ".audit-allowlst")
    gate.assert_exit_code(2, result.rc, "a typo is refused, not resolved")
    gate.assert_eq(result.out, "", "and nothing plausible is printed on stdout")
    gate.assert_contains(result.err, "is not a known policy file", "says what went wrong")
    gate.assert_contains(
        result.err, ".audit-allowlist", "names the valid set so the typo is obvious"
    )
    gate.assert_contains(result.err, "POLICY_FILES", "names where to add a genuinely new one")
    gate.log_pass("an unknown name is refused loudly, naming the valid set")


def test_ci_trigger_is_not_a_policy_name(gate):
    gate.log_test(".ci-trigger is the one root dotfile in this family that is NOT policy")
    # It has no entries, no BLOCKER lines and no parser anywhere in the tree; its only effect is ROOT_MANIFESTS membership in .ci/scripts/ci/scope-map.cjs, which is what makes `touch .ci-trigger` force a full CI round. Naming it here would make the module claim a file it must not move.
    gate.assert_eq(
        pp(gate, "--is", ".ci-trigger").out.strip(),
        "false",
        ".ci-trigger is not one of the names policyPath answers for",
    )
    gate.assert_eq(
        pp(gate, "--is", ".deps-upgrade-blocklist").out.strip(),
        "true",
        "CONTROL: a name that IS policy answers true, so the check above is not always-false",
    )
    gate.assert_eq(
        paths.from_root(".ci-trigger").is_file(),
        True,
        "and it is still at the repository root, where its one gesture works",
    )
    gate.log_pass(".ci-trigger is excluded from the policy set and stays at the root")


def test_one_location_at_a_time(gate):
    gate.log_test("no transition fallback: exactly one live policy directory")
    # Every path the module hands out must live under the single directory --dir names. Two live locations is the failure this asserts against.
    directory = pp(gate, "--dir").out.strip()
    expected = paths.repo_root() / directory if directory else paths.repo_root()
    strays = [p for p in all_paths(gate) if pathlib.Path(p).parent != expected]
    gate.assert_eq(strays, [], "every policy path sits under exactly one directory")
    gate.log_pass("there is exactly one live location (%s), not two" % expected)
