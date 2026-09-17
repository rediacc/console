"""The proof for every ported guard: a differential against its bash twin.

WHY A DIFFERENTIAL, restated for this phase because the argument is not the
same one `test_shellscan_differential` makes. That file compares 28 INTERNAL
fields, because `command-scan.sh` is a library whose functions are the surface.
A guard has no such surface. Its entire contract is what the harness observes:

    the exit code            0 allows the tool call, 2 refuses it
    stdout                   what the session sees
    stderr                   the message, which for at least 21 `check_out`
                             assertions in the suite IS the product ("an exit
                             code alone cannot tell 'blocked, here is the
                             correct command' from 'blocked, good luck'")

So three fields are compared, byte for byte, and the richness that the other
differential gets from field count this one gets from INPUT count: every guard
is run against the events its own suite cases pair with it, against a
deterministic sample of every OTHER guard's events, against 25 degenerate event
shapes the suite never produces, and against every edge case the port module
declares from its twin's comments. Cross-feeding is not padding: over-blocking
only ever shows up on somebody else's input.

WHAT MAKES THE COMPARISON FAIR, and each of these was a way to get a green that
means nothing:

  * THE BASH SIDE RUNS THE REAL FILE, never a copy. A differential against a
    transcription proves the transcription.
  * BOTH SIDES GET THE SAME ENVIRONMENT, built here rather than inherited. An
    inherited `CLAUDE_PROJECT_DIR`, `PATH` or `GIT_INDEX_FILE` would make the
    result depend on who ran it.
  * `gh` IS STUBBED, identically for both sides. Half these guards call it, and
    an unstubbed one makes the differential a network test: two runs seconds
    apart can disagree because a PR changed, and that disagreement would be
    reported as a port defect.
  * BYTES, NOT TEXT. `subprocess` in text mode translates universal newlines,
    so a lone `\\r` in a message would come back as `\\n` from the bash side
    and match a port that never emitted one. `test_shellscan_differential`
    records finding this the hard way; it is not re-learned here.

ANTI-VACUITY. Three separate controls, because each covers a different way this
file could pass while proving nothing:

  1. `test_every_guard_discriminates` -- a guard whose whole case set returns
     one exit code is a guard the corpus never exercised. Comparing two
     constants is not a comparison.
  2. `test_the_differential_can_fail` -- every port declares a DEFECT, one
     source substitution, and the differential must catch it. A green that has
     never been shown to be able to go red is not evidence.
  3. `test_corpus_is_real_and_large_enough` -- a recovery RATIO against the
     call sites counted in the same pass, so a parser that quietly stops
     understanding the suite reds instead of shrinking the corpus to three
     strings.

RUNNING THE DEEP SWEEP. `REDIACC_GUARD_DIFF_FULL=1` feeds EVERY payload to
EVERY guard instead of the cross sample. That is the full cross product and it
is slow, so it is not the default; the number it produced is recorded in the
phase report rather than asserted here, because a timing-shaped assertion in a
feature worktree is inadmissible (driver contract section 5).
"""

import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import tokenize

import pytest

from rediacc_hooks import dispatch, guards, hookio
from rediacc_hooks.tests import guardcorpus

US = "\x1f"
RS = "\x1e"

ROOT = guardcorpus.repo_root()
# THE ORACLE ROOT. The bash originals moved out of `.claude/hooks/` at the P7 cutover: nothing registers them any more, and `.ci/scripts/quality/check_hooks_resolvable.py` is right to refuse an unregistered guard sitting in a chain directory ("a guard nobody calls is worse than no guard: it reads as coverage"). They are kept, byte for byte, because this file is what they are FOR --
# see oracles/README.md. `TWIN` is unchanged and still chain-qualified, so it is a key into this root rather than a path into the live tree.
ORACLES = ROOT / ".claude" / "oracles"
ARTIFACT_DIR = pathlib.Path(__file__).resolve().parent / ".artifacts"

FULL = os.environ.get("REDIACC_GUARD_DIFF_FULL", "") not in ("", "0")

# Section 5c of the driver contract. Docstrings count as comments; a module
# docstring is the natural home for a file-header block.
COMMENT_RATIO_FLOOR = 0.90

# Every line of an original naming a DATE, an ISSUE, a REVIEW ROUND or a FILE:LINE. The ratio cannot see these -- prose can be padded while the one paragraph naming a dated incident is dropped -- so they are extracted mechanically and each must survive somewhere in the port.
ARCHAEOLOGY = (
    r"\b20\d\d-\d\d-\d\d\b",
    r"#\d+",
    r"[Rr]ounds? ?-?\d+(-\d+)?",
    r"\b[\w./-]+\.(?:sh|ts|py|cjs):\d+(-\d+)?\b",
    r"\brun \d{6,}\b",
)


# --------------------------------------------------------------------------- The stub environment ---------------------------------------------------------------------------

# `gh`, stubbed to the shape every guard here already treats as its fail-open path: nothing on stdout, a non-zero exit. Guards that need it to SUCCEED declare their own stub through `ENVS` on the port module, exactly as the suite's own `stub_gh` and `_gc_shim` helpers do for the same guards.
#
# WHY STUB AT ALL, since both sides would call the same real `gh`. Because they would not call it at the same MOMENT. The bash side runs the whole corpus
# first and the Python side follows; a PR that changes state in between turns
# into a field that differs, reported as a port defect. Measured cost of the real thing on one case: a network round trip per invocation, times several hundred cases, times two sides.
DEFAULT_STUBS = {
    "gh": "#!/bin/sh\nexit 1\n",
}


def _stub_dir(tmp_path, stubs):
    directory = tmp_path / ("stubs-%s" % abs(hash(tuple(sorted(stubs.items())))))
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in stubs.items():
        path = directory / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    return directory


# --------------------------------------------------------------------------- Named git fixtures ---------------------------------------------------------------------------
#
# WHY THEY EXIST, and the control that demanded them. Roughly half these guards read local git state -- a branch name, whether the branch is ahead of its remote, whether a worktree is dirty. Run against THIS checkout they all take one branch of their logic, whichever branch this worktree happens to be in, and `test_every_guard_discriminates` then reports the guard as answering
# identically on every case. That is not a nuisance: it is the control saying the comparison could not have failed. `block_merge_with_unpushed` was the first port to trip it, on the first run, because no `origin/<branch>` ref exists in a feature worktree and the guard fails open on every input.
#
# So a module names the git worlds its twin distinguishes, the harness builds each one ONCE per session, and both sides are pointed at it through CLAUDE_PROJECT_DIR. The repositories are built with `git init`, never cloned and never fetched: no network, and nothing outside the temporary directory is read or written.
FIXTURE_TOKEN = "{FIXTURE:%s}"  # noqa: S105


def _git(cwd, *args):
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_NAME="Fixture",
            GIT_AUTHOR_EMAIL="fixture@example.invalid",
            GIT_COMMITTER_NAME="Fixture",
            GIT_COMMITTER_EMAIL="fixture@example.invalid",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_SYSTEM="/dev/null",
        ),
    )


def _build_repo(path, branch, ahead):
    """A repo on `branch` with `ahead` commits its origin has never seen."""
    bare = path.parent / (path.name + ".origin.git")
    bare.mkdir(parents=True)
    _git(bare, "init", "--bare", "--initial-branch=main", "-q")
    path.mkdir(parents=True)
    _git(path, "init", "--initial-branch=main", "-q")
    _git(path, "remote", "add", "origin", str(bare))
    (path / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-q", "-m", "seed")
    if branch != "main":
        _git(path, "checkout", "-q", "-b", branch)
    _git(path, "push", "-q", "origin", branch)
    for i in range(ahead):
        (path / ("local-%d.txt" % i)).write_text("x\n", encoding="utf-8")
        _git(path, "add", ".")
        _git(path, "commit", "-q", "-m", "local only %d" % i)
    return path


# Exposed for a port module's own `FIXTURES` table: `build_repo(path, branch, ahead)` is the whole vocabulary most git guards need, and re-deriving it per module would be four copies of `git init` semantics.
build_repo = _build_repo
git_in = _git

FIXTURE_BUILDERS = {
    # A feature branch with two commits the remote has never seen. This is the 2026-09-01 near-miss shape: pushed head, later commit still local.
    "git-ahead": lambda p: _build_repo(p, "0831-1", 2),
    # The same branch, fully pushed. The ALLOW side of the same guard.
    "git-synced": lambda p: _build_repo(p, "0831-1", 0),
    # On main, where /pr-merge deliberately ends.
    "git-main": lambda p: _build_repo(p, "main", 2),
}

_FIXTURES = {}


def all_builders():
    """The shared table plus every one a port module declares for itself.

    A guard whose twin distinguishes a world nothing else needs declares it in
    its own file, as `FIXTURES = {"name": builder}`, and the name is then usable
    in its `ENVS`. That keeps a port and the world it is judged in in ONE file,
    which matters when several agents are porting different guards into this
    package at once: a shared table is a shared edit, and a shared edit is a
    collision.
    """
    table = dict(FIXTURE_BUILDERS)
    for stem in guards.stems():
        for name, builder in getattr(guards.load(stem), "FIXTURES", {}).items():
            if name in table and table[name] is not builder:
                msg = (
                    "fixture %r is declared by %s and by another module with a different "
                    "builder; two worlds sharing a name would silently give one guard the "
                    "other's tree" % (name, stem)
                )
                raise AssertionError(msg)
            table[name] = builder
    return table


def fixture_path(work, name):
    if name not in _FIXTURES:
        target = pathlib.Path(work) / "fixtures" / name
        _FIXTURES[name] = str(all_builders()[name](target))
    return _FIXTURES[name]


def _resolve_fixtures(value, work):
    out = value
    for name in all_builders():
        token = FIXTURE_TOKEN % name
        if token in out:
            out = out.replace(token, fixture_path(work, name))
    return out


def _base_env(stub_dir, extra, work=None):
    """The environment BOTH sides run under, built rather than inherited.

    `PATH` keeps the real one behind the stub directory: these guards call
    `git`, `sed`, `awk` and `python3`, and an empty PATH would make every one
    of them fail identically on both sides -- agreement that proves nothing.
    """
    env = {
        "PATH": "%s:%s" % (stub_dir, os.environ.get("PATH", "/usr/bin:/bin")),
        "HOME": os.environ.get("HOME", "/"),
        "CLAUDE_PROJECT_DIR": str(ROOT),
        "LC_ALL": "C",
        "TZ": "UTC",
        # Deliberately NOT inherited. `test_shellscan_differential` records the same reasoning: a differential that depends on the caller's environment is one that passes for the wrong reason, and an inherited GIT_INDEX_FILE would reach every `git ls-files` in this chain.
    }
    env.update(extra)
    if work is not None:
        env = {k: _resolve_fixtures(v, work) for k, v in env.items()}
    return env


def environments(module):
    """`[(label, env_extra, stubs)]` for one port module.

    One variant by default. A module declares `ENVS` when its twin's behaviour
    genuinely forks on something outside the payload -- a `gh` that answers, an
    environment variable its own comments name -- and then both sides run every
    variant.
    """
    return getattr(module, "ENVS", None) or [("default", {}, {})]


# --------------------------------------------------------------------------- Building the case list ---------------------------------------------------------------------------


# The event a chain's guards are handed, when a port's EDGE_CASES entry is a bare string. A module whose twin reads `file_path` or `tool_name` declares its
# case as a dict instead and gets exactly that document.
#
# THE FIRST CUT PUT THE BARE COMMAND ON STDIN, and the anti-vacuity control is what found it: every edge case became an unparseable payload, `jq` returned "" for all of them, and each one exercised only the guard's empty-command branch. It passed the differential (both sides agree on nonsense) while testing none of the shapes it named, which is the exact failure this file's
# controls exist for.
CHAIN_BUILDER = {
    "pre-bash": "bash_json",
    "post-bash": "bash_json",
    "pre-edit": "edit_json",
    "pre-ask": "ask_json",
}


def edge_payload(module, spec):
    if isinstance(spec, dict):
        return json.dumps(spec)
    builder = getattr(module, "EVENT_BUILDER", None) or CHAIN_BUILDER[module.CHAIN]
    return json.dumps(guardcorpus.BUILDERS[builder]([spec]))


def divergence_cases():
    """`[(stem, label, payload, reason)]` a port DECLARES it does not match on.

    WHY A DECLARATION AND NOT A SILENT GAP, and this exists because the gap was
    real. `block-long-sleep.sh` reads its sleep value with bash arithmetic, so
    `sleep 08` is not a number in base 10 and the shell writes

        .claude/hooks/pre-bash/block-long-sleep.sh: line 45: [[: 08: value too
        great for base (error token is "08")

    to stderr and then PERMITS the command. The port cannot reproduce that line:
    it names the twin's own path and line number, which are facts about a file
    the port is replacing, so emitting them would be a lie rather than a
    transliteration. No suite case carries a leading-zero sleep, so the
    differential simply never saw it -- a divergence that exists and that
    nothing reported, which is the failure this whole file is built against.

    So the port declares it. The harness then runs the case and asserts the
    SHAPE of the disagreement: the exit code and stdout must still match, and
    stderr must still DIFFER. That last assertion is what stops the entry
    rotting: if a later change makes the two agree, the declaration is stale and
    this says so instead of quietly excusing a match.
    """
    out = []
    for stem in guards.stems():
        module = guards.load(stem)
        for label, spec, reason in getattr(module, "KNOWN_DIVERGENCES", []):
            out.append((stem, label, edge_payload(module, spec), reason))
    return out


def build_cases(twinned=True):
    """Every (guard, label, payload, env-variant) the differential will run.

    Only guards that have BEEN PORTED are included. That is not a way of
    excusing the rest: a port that does not exist has no twin to compare, and
    `test_every_ported_guard_is_registered` is what stops a module being
    written and then quietly left out of this list.

    `twinned=False` BUILDS THE COMPLEMENT: the cases for guards that were never
    bash and therefore have no oracle. They are built by the SAME function
    against the SAME corpus, and the split is only about which side the bash
    driver can run. Keeping one builder means an untwinned guard is still
    cross-fed every other guard's payloads and every degenerate shape, which is
    where over-blocking shows up; the only thing it loses is the comparison to
    bash, and `TWIN = None` is what declares that loss out loud.

    THE INDEX ALIGNMENT IS WHY THIS IS A SPLIT AND NOT A FILTER AT USE TIME. The
    bash driver writes one case file per element of `CASES` and the comparison
    reads `bash_results["records"][i]`, so a single untwinned entry anywhere in
    that list would shift every record after it by one and the differential would
    compare each guard against its neighbour while reporting agreement.
    """
    harvested, stats = guardcorpus.harvest_cases()
    pool = sorted({payload for _, payload, _, _ in harvested})
    own = {}
    for guard, payload, label, suite_rc in harvested:
        own.setdefault(guard, []).append((label, payload, suite_rc))

    cases = []
    for stem in guards.stems():
        module = guards.load(stem)
        if (module.TWIN is not None) != twinned:
            continue
        # THE SUITE'S KEY, which since the P7 cutover is the MODULE and not the twin: a case reads `check 2 guards/block_x.py`, because that is the key `check-hook-integrity.sh` inventories the live guard under and one spelling has to drive the suite, the coverage gate and this corpus. TWIN still names the bash original and is used, a few lines down, to find it in the oracle tree.
        key = "guards/%s.py" % stem
        named = own.get(key, [])
        seen = set()
        picked = []
        for label, payload, _ in named:
            if payload not in seen:
                seen.add(payload)
                picked.append(("suite-%s" % label, payload))
        for label, spec in getattr(module, "EDGE_CASES", []):
            payload = edge_payload(module, spec)
            if payload not in seen:
                seen.add(payload)
                picked.append(("edge-%s" % label, payload))
        for label, payload in guardcorpus.DEGENERATE_PAYLOADS:
            if payload not in seen:
                seen.add(payload)
                picked.append(("degen-%s" % label, payload))
        foreign = pool if FULL else guardcorpus.cross_sample(pool, key)
        for i, payload in enumerate(foreign):
            if payload not in seen:
                seen.add(payload)
                picked.append(("cross-%03d" % i, payload))
        for env_label, extra, stubs in environments(module):
            for label, payload in picked:
                cases.append((stem, "%s|%s" % (env_label, label), payload, env_label, extra, stubs))
    return cases, stats, pool


CASES, HARVEST_STATS, POOL = build_cases()
# The untwinned guards' cases, built the same way and run against the PYTHON side only. A separate list rather than a flag on each row, for the index-alignment reason `build_cases` states.
NATIVE_CASES, _NATIVE_STATS, _NATIVE_POOL = build_cases(twinned=False)


# --------------------------------------------------------------------------- The two sides ---------------------------------------------------------------------------

# The bash driver. A string rather than a checked-in `.sh` for the reason `test_shellscan_differential` gives: this workstream moves `.claude` to Python, and a second language checked in beside the port would be the thing the language gate exists to refuse. Written to a temporary directory, it is not a second language in the tree.
DRIVER = r"""#!/usr/bin/env bash
IN_DIR="$1"; ORACLES="$2"; WORK="$3"
US=$'\037'
RS=$'\036'
for meta in "$IN_DIR"/case-*.meta; do
    base="${meta%.meta}"
    guard=""; envfile=""
    IFS= read -r guard < "$meta"
    envfile="$base.env"
    printf 'case%s%s%s' "$US" "${base##*/}" "$RS"
    # `env -i` with an explicit list, NOT `set -a; . envfile`.
    #
    # THE SOURCING VERSION SHIPPED FIRST AND WAS SILENTLY BROKEN. On this host
    # PATH holds WSL entries with spaces and parentheses ("/mnt/c/Program Files
    # (x86)/..."), so every `.env` file failed with "syntax error near
    # unexpected token `('" and each guard then ran with NO
    # CLAUDE_PROJECT_DIR, NO stub directory and the driver's own PATH -- while
    # the Python side ran with the environment the case asked for. The
    # comparison still passed, because the first ported guard reads no
    # environment at all. That is a differential comparing two different
    # experiments and reporting agreement, which is why the caller now also
    # asserts this driver wrote nothing to stderr.
    mapfile -t ENVV < "$envfile"
    env -i "${ENVV[@]}" bash "$ORACLES/$guard" < "$base.json" > "$WORK/out" 2> "$WORK/err"
    rc=$?
    printf 'rc%s%s%s' "$US" "$rc" "$RS"
    printf 'out%s' "$US"; cat "$WORK/out"; printf '%s' "$RS"
    printf 'err%s' "$US"; cat "$WORK/err"; printf '%s' "$RS"
done
"""


def parse_stream(text):
    records = []
    current = None
    for chunk in text.split(RS):
        if chunk == "":
            continue
        key, _, value = chunk.partition(US)
        if key == "case":
            current = {"case": value}
            records.append(current)
            continue
        if current is None:
            msg = "field %r arrived before any case marker" % key
            raise AssertionError(msg)
        current[key] = value
    return records


# EVERY XDIST WORKER REBUILDS A SESSION FIXTURE, because "session" is scoped to a PROCESS and xdist workers ARE processes. The `bash_results` fixture below forks env -i bash once per case across 6017 cases, about 18,000 processes, and this module's tests are otherwise pure in-process comparison -- so without this declaration its cases scatter across every worker and each one pays
# the full driver again.
#
# Measured 2026-09-07: this file and test_shellscan_differential.py together serve 6446 of 8968 tests (72 percent of the corpus). At `-n 8` that is roughly 240,000 forks of duplicated setup before a single one of those tests does useful work, which is why the suite is 1.64x SLOWER under 8 workers than serial (619.17s vs 1013.59s on a quiesced box).
#
# The group pins all of this module's tests to ONE worker, so the fixture is built once. It is INERT without `--dist loadgroup`, so it changes nothing today.
XDIST_GROUP = "hooks-guards"


@pytest.fixture(scope="session")
def bash_results(tmp_path_factory):
    """Run every real guard over the whole corpus, once, in one bash process."""
    if not CASES:
        return {"records": [], "stderr": ""}
    work = tmp_path_factory.mktemp("guard-differential")
    inputs = work / "in"
    inputs.mkdir()
    scratch = work / "work"
    scratch.mkdir()
    for i, (stem, _, payload, _, extra, stubs) in enumerate(CASES):
        module = guards.load(stem)
        base = inputs / ("case-%05d" % i)
        base.with_suffix(".json").write_bytes(payload.encode("utf-8"))
        base.with_suffix(".meta").write_text(module.TWIN + "\n", encoding="utf-8")
        env = _base_env(_stub_dir(work, dict(DEFAULT_STUBS, **stubs)), extra, work)
        base.with_suffix(".env").write_text(
            "".join("%s=%s\n" % (k, v) for k, v in sorted(env.items())), encoding="utf-8"
        )
    driver = work / "driver.bash"
    driver.write_text(DRIVER, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(driver), str(inputs), str(ORACLES), str(scratch)],
        capture_output=True,
        check=False,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/")},
    )
    stdout = proc.stdout.decode("utf-8", "surrogateescape")
    stderr = proc.stderr.decode("utf-8", "surrogateescape")
    assert proc.returncode == 0, "driver failed: %s" % stderr
    # The driver itself must be silent. It is the only thing standing between "the two sides agreed" and "the two sides ran different experiments and agreed anyway": a driver that cannot build a case's environment says so here and nowhere else.
    assert stderr == "", (
        "the bash driver wrote to stderr, so at least one case did not run as asked and "
        "every comparison below is between two different experiments:\n%s" % stderr[:4000]
    )
    records = parse_stream(stdout)
    assert len(records) == len(CASES), (
        "driver returned %d records for %d cases -- the frame is out of step, which "
        "invalidates every comparison below" % (len(records), len(CASES))
    )
    return {"records": records, "stderr": stderr, "work": work}


def python_fields(stem, payload, extra, stubs, work):
    """The Python side of one case, field for field with the driver above.

    `os.environ` is swapped for the case environment rather than passed down,
    because a ported guard that shells out to `git` or `gh` inherits the
    process environment exactly as its bash twin inherits the shell's. Passing
    an `env` only to `dispatch` would leave those children reading the test
    runner's environment while the bash side read the case's.

    `time.tzset()` IS NOT DECORATION, and it is the one piece of libc state that
    an in-process side does not get from swapping a dict. `TZ` is read by libc
    once and cached, so `datetime.now()` here would keep answering in the test
    runner's own zone however the case set the variable, while the bash side --
    a fresh process per case -- read the case's zone. Measured 2026-09-07:
    without this call, `block_stale_pr_branch_date` reported the port as
    diverging under a pinned `TZ=UTC` when the port was right and the HARNESS was
    the thing ignoring the variable. Restoring the runner's own zone afterwards
    matters for the same reason.
    """
    env = _base_env(_stub_dir(work, dict(DEFAULT_STUBS, **stubs)), extra, work)
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    time.tzset()
    try:
        rc, out, err = dispatch.run_one(stem, payload, cwd=str(ROOT), env=env)
    finally:
        os.environ.clear()
        os.environ.update(saved)
        time.tzset()
    return {"rc": str(rc), "out": out, "err": err}


def diff_fields(bash_side, python_side):
    diffs = []
    for key in ("rc", "out", "err"):
        want = bash_side.get(key, "<missing from bash>")
        got = python_side.get(key, "<missing from port>")
        if got != want:
            diffs.append((key, want, got))
    return diffs


def render(diffs, stem, label, payload):
    lines = ["%s diverged on %s for payload %r" % (stem, label, payload)]
    for key, want, got in diffs:
        lines.append("  field %s" % key)
        lines.append("    bash   %r" % want)
        lines.append("    python %r" % got)
    return "\n".join(lines)


# --------------------------------------------------------------------------- The corpus, before anything is compared against it ---------------------------------------------------------------------------


def test_corpus_is_real_and_large_enough():
    assert HARVEST_STATS["recovered"] >= guardcorpus.MIN_CASES, (
        "only %d suite cases recovered from %s; below %d the differential is proving "
        "the ports against a handful of strings"
        % (HARVEST_STATS["recovered"], HARVEST_STATS["source"], guardcorpus.MIN_CASES)
    )
    ratio = HARVEST_STATS["recovered"] / HARVEST_STATS["call_sites"]
    assert ratio >= guardcorpus.RECOVERY_FLOOR, (
        "recovered %d of %d check call sites (%.3f); the payload parser has stopped "
        "understanding the suite" % (HARVEST_STATS["recovered"], HARVEST_STATS["call_sites"], ratio)
    )


def test_builders_match_the_suite():
    """The transcribed event shapes are still the suite's own.

    If a builder changes and the table does not, every payload for that builder
    is silently the wrong shape, BOTH sides get it, and this file goes on
    passing while testing something else.
    """
    drift = guardcorpus.builder_shape_drift()
    assert not drift, "suite payload builders no longer match the corpus table: %r" % (drift,)


def test_every_ported_guard_is_registered():
    """A module in `guards/` that this file does not exercise is invisible.

    Same failure the driver contract names for a gate the binder cannot see:
    "it is invisible, which is worse than unregistered, because nothing reports
    the absence".
    """
    exercised = {stem for stem, _, _, _, _, _ in CASES}
    exercised |= {stem for stem, _, _, _, _, _ in NATIVE_CASES}
    missing = sorted(set(guards.stems()) - exercised)
    assert not missing, "these guard modules exist but no case runs them: %s" % missing


def test_every_port_has_a_present_twin():
    """A twinned guard's oracle must exist. An UNTWINNED one must have a suite.

    THE SECOND HALF IS THE POINT, and it is what stops `TWIN = None` becoming the
    cheap way out of this whole file. A guard with no oracle is not judged
    against less evidence, it is judged against DIFFERENT evidence: a dedicated
    `test-<stem>.py` beside it, which `check-hook-integrity.sh` already treats as
    covering both directions. Without this arm, deleting a twin declaration would
    silently remove a guard from the differential AND from every other control,
    and the suite would go green faster than before.
    """
    for stem in guards.stems():
        module = guards.load(stem)
        if module.TWIN is None:
            suite = pathlib.Path(module.__file__).with_name("test-%s.py" % stem)
            assert suite.is_file(), (
                "%s declares TWIN = None, so this differential has no oracle for it. That is "
                "admitted -- see guards.twin_of -- but only in exchange for a dedicated suite "
                "at %s, which does not exist. A guard with neither an oracle nor its own "
                "suite has no evidence at all." % (stem, suite.relative_to(ROOT))
            )
            continue
        twin = ORACLES / module.TWIN
        assert twin.is_file(), (
            "%s names %s as its twin and that file is not in the oracle tree. The bash "
            "originals are kept at .claude/oracles/ precisely so this "
            "differential still has an oracle after the cutover; without it every "
            "comparison below is between the port and itself."
            % (stem, ".claude/oracles/%s" % module.TWIN)
        )


# --------------------------------------------------------------------------- The differential ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("index", "stem", "label", "payload", "extra", "stubs"),
    [(i, c[0], c[1], c[2], c[4], c[5]) for i, c in enumerate(CASES)],
    ids=["%s|%s" % (c[0], c[1]) for c in CASES],
)
def test_guard_matches_bash(bash_results, index, stem, label, payload, extra, stubs):
    bash_side = bash_results["records"][index]
    assert bash_side["case"] == "case-%05d" % index
    fields = python_fields(stem, payload, extra, stubs, bash_results["work"])
    diffs = diff_fields(bash_side, fields)
    assert not diffs, render(diffs, stem, label, payload)


def test_every_guard_discriminates(bash_results):
    """No guard may answer the same way on every case it was given.

    A guard that returns 0 on all of its inputs has been compared against a
    constant, which is the failure `test_shellscan_differential` found in its
    own field set: "the target_root field evaluated against an absent root was
    empty on all 385 cases -- a comparison that could not have failed".

    Exit code alone is not the test, because the four `warn-*` guards exit 0 by
    design and speak on stderr. The predicate is that SOMETHING varies.
    """
    seen = {}
    for i, (stem, _, _, _, _, _) in enumerate(CASES):
        record = bash_results["records"][i]
        seen.setdefault(stem, set()).add((record["rc"], record["out"], record["err"]))
    flat = sorted(stem for stem, values in seen.items() if len(values) < 2)
    assert not flat, (
        "these guards answered identically on every case, so comparing them proves "
        "nothing: %s" % flat
    )


def test_every_untwinned_guard_discriminates(bash_results):
    """The same anti-vacuity control as above, for the guards with no oracle.

    `test_every_guard_discriminates` reads the BASH side's records, so it cannot
    see a guard the bash driver never ran. Without this, an untwinned guard that
    returned 0 on all 400-odd of its cases -- a broken match, a raised-and-caught
    import, a chain it is not in -- would be invisible to every control in this
    file, and the file would go green faster for having it.

    THE PREDICATE IS "SOMETHING VARIES", not "some case exits 2", for the reason
    the twinned version gives: the `warn_*` guards exit 0 by design and speak on
    stderr, so an exit-code-only test would be wrong about them.
    """
    if not NATIVE_CASES:
        # An EMPTY set is a pass, not a skip: `check:ci-pytest` refuses a skip, and a repository with no untwinned guards is an honest state rather than an unrun test. See the NO_DIVERGENCE sentinel below, same lesson.
        assert not guards.untwinned(), (
            "%d guard(s) declare TWIN = None but NATIVE_CASES is empty, so none of them was "
            "exercised here" % len(guards.untwinned())
        )
        return
    work = bash_results["work"]
    seen = {}
    for stem, _, payload, _, extra, stubs in NATIVE_CASES:
        fields = python_fields(stem, payload, extra, stubs, work)
        seen.setdefault(stem, set()).add((fields["rc"], fields["out"], fields["err"]))
    flat = sorted(stem for stem, values in seen.items() if len(values) < 2)
    assert not flat, (
        "these untwinned guards answered identically on every case, so nothing here proves "
        "they do anything: %s" % flat
    )


def test_the_differential_can_fail(tmp_path, bash_results):
    """Every port declares one defect, and the comparison must catch it.

    A differential that has never failed is not evidence. This plants each
    port's own declared defect -- a single source substitution naming the line
    its twin's comments say cost the most -- and requires the ported guard to
    answer differently on at least one case it was given.
    """
    work = bash_results["work"]
    unproven = []
    # BOTH LISTS. This control compares the port against ITSELF-WITH-A-BUG and never touches the bash side, so it works identically for an untwinned guard -- and an untwinned guard needs it MORE, being the one with no
    # oracle. Leaving NATIVE_CASES out here would have made `TWIN = None` skip
    # the one anti-vacuity control that does not depend on an oracle at all.
    all_cases = list(CASES) + list(NATIVE_CASES)
    for stem in guards.stems():
        module = guards.load(stem)
        defect = getattr(module, "DEFECT", None)
        assert defect, "%s declares no DEFECT, so nothing proves its differential can fail" % stem
        old, new = defect
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert old in source, "%s's declared DEFECT no longer applies to the port: %r" % (stem, old)
        broken_src = source.replace(old, new)
        assert broken_src != source
        broken_path = tmp_path / ("broken_%s.py" % stem)
        broken_path.write_text(broken_src, encoding="utf-8")
        namespace = {"__name__": "broken_%s" % stem, "__file__": str(broken_path)}
        exec(compile(broken_src, str(broken_path), "exec"), namespace)  # noqa: S102
        broken_run = namespace["run"]
        changed = False
        for cstem, _, payload, _, extra, stubs in all_cases:
            if cstem != stem:
                continue
            good = python_fields(stem, payload, extra, stubs, work)
            env = _base_env(_stub_dir(work, dict(DEFAULT_STUBS, **stubs)), extra, work)
            saved = dict(os.environ)
            os.environ.clear()
            os.environ.update(env)
            try:
                event = hookio.Event(payload, cwd=str(ROOT), env=env)
                rc = broken_run(event)
                bad = dict(zip(("rc", "out", "err"), event.result(rc), strict=True))
                bad["rc"] = str(bad["rc"])
            finally:
                os.environ.clear()
                os.environ.update(saved)
            if bad != good:
                changed = True
                break
        if not changed:
            unproven.append(stem)
    assert not unproven, (
        "these ports answered identically with their declared defect planted, so this "
        "file's green does not depend on that branch being right: %s" % unproven
    )


# --------------------------------------------------------------------------- Declared divergences ---------------------------------------------------------------------------

DIVERGENCES = divergence_cases()

# THE EMPTY SET IS A PASS, NOT A SKIP, and that distinction was live red at HEAD. Every port's KNOWN_DIVERGENCES is empty today (block_long_sleep's dissolved when its twin was fixed to force base ten on 2026-09-06), so `parametrize` was handed an empty list, and pytest turns an empty parameter set into a SKIP:
#
# SKIPPED [1] test_guards_differential.py:694: got empty parameter set for (stem, label, payload, reason)
#
# `check:ci-pytest` refuses a skip on purpose ("pytest exited 0 but reports 8467 passed out of 8468 collected. A skipped or deselected test is not a passing one, and the difference is invisible in the exit code"), so the whole gate exited 1
# while nothing was wrong. The honest empty state was being reported as an unrun
# test. A sentinel row runs the SAME function, asserts the table really is empty,
# and returns; the moment a port declares a divergence the sentinel disappears and
# the real cases run.
NO_DIVERGENCE = (None, "no port declares a divergence", "", "")


@pytest.mark.parametrize(
    ("stem", "label", "payload", "reason"),
    DIVERGENCES or [NO_DIVERGENCE],
    ids=["%s|%s" % (d[0], d[1]) for d in DIVERGENCES] or ["<none declared>"],
)
def test_declared_divergence_is_still_exactly_that(tmp_path, stem, label, payload, reason):
    """A declared divergence must diverge, and only where it says it does."""
    if stem is None:
        assert not DIVERGENCES, (
            "the sentinel row ran while %d divergence(s) are declared, so the real "
            "cases were skipped" % len(DIVERGENCES)
        )
        return
    module = guards.load(stem)
    twin = ORACLES / module.TWIN
    env = _base_env(_stub_dir(tmp_path, DEFAULT_STUBS), {}, tmp_path)
    proc = subprocess.run(
        ["bash", str(twin)],
        input=payload.encode("utf-8"),
        capture_output=True,
        check=False,
        env=env,
        cwd=str(ROOT),
    )
    bash_side = {
        "rc": str(proc.returncode),
        "out": proc.stdout.decode("utf-8", "surrogateescape"),
        "err": proc.stderr.decode("utf-8", "surrogateescape"),
    }
    python_side = python_fields(stem, payload, {}, {}, tmp_path)
    assert python_side["rc"] == bash_side["rc"], (
        "%s: %s -- the EXIT CODE may never diverge. A declared divergence is about what a "
        "guard says, never about what it decides.\n  reason given: %s" % (stem, label, reason)
    )
    assert python_side["out"] == bash_side["out"], (
        "%s: %s -- stdout diverged, and only stderr was declared.\n  reason given: %s"
        % (stem, label, reason)
    )
    assert python_side["err"] != bash_side["err"], (
        "%s: %s no longer diverges, so the declaration is STALE and is now excusing a "
        "match. Delete it and let the ordinary differential cover the case.\n"
        "  reason given: %s" % (stem, label, reason)
    )


# --------------------------------------------------------------------------- Section 5c of the driver contract: comment archaeology ---------------------------------------------------------------------------


def bash_comment_bytes(path):
    """Whole-line comments, with their newline. The shebang is not prose."""
    total = 0
    lines = 0
    for line in path.read_text(encoding="utf-8").split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith("#!"):
            total += len(line.encode("utf-8")) + 1
            lines += 1
    return total, lines


def python_comment_bytes(path):
    """`#` comments plus docstrings, counted CONSERVATIVELY.

    A comment token is counted from its `#` (its indentation is not counted,
    though the bash side's is), and a docstring from its opening quote. The
    asymmetry is deliberate and in the strict direction: the port is credited
    with less than it has, so a ratio that clears the floor clears it honestly.
    """
    text = path.read_text(encoding="utf-8")
    total = 0
    count = 0
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT:
                total += len(token.string.encode("utf-8")) + 1
                count += 1
    tree = ast.parse(text)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        for child in body:
            if (
                isinstance(child, ast.Expr)
                and isinstance(child.value, ast.Constant)
                and isinstance(child.value.value, str)
            ):
                segment = ast.get_source_segment(text, child)
                if segment:
                    total += len(segment.encode("utf-8")) + 1
                    count += 1
    return total, count


def archaeology_tokens(text):
    found = []
    for pattern in ARCHAEOLOGY:
        for m in re.finditer(pattern, text):
            token = m.group(0)
            if token not in found:
                found.append(token)
    return found


def test_comment_ratio_and_archaeology(bash_results):
    """Write the differential artifact, and refuse a port that lost the prose."""
    rows = []
    failures = []
    for stem in guards.stems():
        module = guards.load(stem)
        if module.TWIN is None:
            # NO ORACLE MEANS NO RATIO, because the ratio is `port bytes / twin bytes` and the denominator does not exist. Stated as a skip with a reason rather than a `bash_bytes or 1` fallback, which would have scored every untwinned guard at a ratio of `py_bytes` and passed
            # for a reason nobody intended. The archaeology sweep is the twin's
            # dated evidence surviving into the port; there is no twin, so there
            # is nothing to have survived.
            continue
        twin = ORACLES / module.TWIN
        port = pathlib.Path(module.__file__)
        bash_bytes, bash_lines = bash_comment_bytes(twin)
        py_bytes, py_units = python_comment_bytes(port)
        ratio = py_bytes / bash_bytes if bash_bytes else 1.0
        tokens = archaeology_tokens(twin.read_text(encoding="utf-8"))
        port_text = port.read_text(encoding="utf-8")
        lost = [t for t in tokens if t not in port_text]
        rows.append(
            {
                "guard": stem,
                "original": ".claude/oracles/%s" % module.TWIN,
                "port": str(port.relative_to(ROOT)),
                "original_comment_bytes": bash_bytes,
                "original_comment_lines": bash_lines,
                "port_comment_bytes": py_bytes,
                "port_comment_units": py_units,
                "comment_ratio": round(ratio, 4),
                "archaeology_tokens": tokens,
                "archaeology_lost": lost,
            }
        )
        if ratio < COMMENT_RATIO_FLOOR:
            failures.append(
                "%s carries %d comment bytes against %s's %d (%.3f), floor %.2f"
                % (stem, py_bytes, module.TWIN, bash_bytes, ratio, COMMENT_RATIO_FLOOR)
            )
        if lost:
            failures.append(
                "%s dropped the dated evidence in: %s -- the ratio cannot see this, which "
                "is why it is checked separately" % (stem, lost)
            )

    total_bash = sum(r["original_comment_bytes"] for r in rows)
    total_py = sum(r["port_comment_bytes"] for r in rows)
    artifact = {
        "guards_ported": len(rows),
        "cases": len(CASES),
        "fields_per_case": 3,
        "comparisons": len(CASES) * 3,
        "corpus": HARVEST_STATS,
        "declared_divergences": [
            {"guard": d[0], "case": d[1], "reason": d[3]} for d in DIVERGENCES
        ],
        "payload_pool": len(POOL),
        "cross_sample": "FULL" if FULL else guardcorpus.CROSS_SAMPLE,
        "degenerate_payloads": len(guardcorpus.DEGENERATE_PAYLOADS),
        "comment_ratio_floor": COMMENT_RATIO_FLOOR,
        "comment_bytes_bash_total": total_bash,
        "comment_bytes_port_total": total_py,
        "comment_ratio_total": round(total_py / total_bash, 4) if total_bash else None,
        "bash_driver_stderr": bash_results["stderr"][:2000],
        "per_guard": rows,
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (ARTIFACT_DIR / "guards-differential.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps({k: v for k, v in artifact.items() if k != "per_guard"}, indent=2),
        file=sys.stderr,
    )
    assert not failures, "\n".join(failures)
