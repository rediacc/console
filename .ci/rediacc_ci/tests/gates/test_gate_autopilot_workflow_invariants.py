"""Port of `.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh`.

Tests `.ci/scripts/security/check-autopilot-workflow-invariants.sh`, the static
gate over `.github/workflows/autopilot.yml` -- the workflow that hands a model a
shell over PR-authored code.

THE METHOD IS THE POINT, and it is carried over unchanged. A static grep that has
never been shown to FAIL is indistinguishable from `true` (this repo shipped
exactly that shape in a `--selftest` nothing invoked). So every invariant is proven
in both directions: the REAL workflow passes, and a MUTATED copy of the real
workflow with that one invariant broken must exit 1 with the pinned diagnostic.
Mutating the LIVE file rather than a frozen fixture keeps the proofs from rotting
as the workflow evolves: if the workflow's shape drifts so far that a mutation
stops landing, `assert_mutated` fails loudly instead of the test silently testing
nothing.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Every case reads
`.github/workflows/autopilot.yml` off the working tree and the first case drives
the subject at it in place. A battery step rewriting the workflow mid-read is a
divergence that would be blamed on this port. `REAL_TREE_TWIN = True` is what buys
the serialisation, and it is honoured only because this module declares no
`XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

WHAT IS REIMPLEMENTED, AND WHAT IS NOT. The SUBJECT is never reimplemented: every
verdict below comes from the real `bash check-autopilot-workflow-invariants.sh`.
What is reimplemented is the twin's MUTATION toolkit -- `perl -pe`, `perl -0pe`,
`sed` and `grep -v` -- as the four line helpers below. Their perl semantics are
reproduced deliberately and are documented on each helper, because a mutation that
lands in the wrong place is a control that fires for the wrong reason. Every
mutation is still checked against the real file by `assert_mutated`, which is the
thing that catches a helper whose semantics drifted.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-autopilot-workflow-invariants.sh"

# Reads and mutates copies of the real .github/workflows/autopilot.yml, and the first case drives the subject at the real file in place.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/security/check-autopilot-workflow-invariants.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
REAL_REL = ".github/workflows/autopilot.yml"
REAL = paths.from_root(*REAL_REL.split("/"))


def require_gate(gate) -> str:
    """The subject and its corpus, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    if not REAL.is_file():
        gate.log_fail(
            "the real workflow is missing at %s, so every mutation below would be a "
            "mutation of nothing and this file would prove nothing at all." % REAL_REL
        )
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def real_source(gate) -> str:
    """The real workflow's text, refused when empty.

    ANTI-VACUITY. Every case below derives its fixture from this string. An empty
    or truncated workflow would make the mutations no-ops, `assert_mutated` would
    fire with a confusing message, and a reader would hunt the mutation instead of
    the corpus. Refusing here names the real problem.
    """
    require_gate(gate)
    source = REAL.read_text(encoding="utf-8")
    if not source.strip():
        gate.log_fail(
            "%s is empty, so there is nothing to mutate and no invariant can be "
            "proven. Zero input is a failure here, not a pass." % REAL_REL
        )
    return source


def run_gate(gate, workflow_file) -> harness.RunResult:
    """`run_gate` from the twin: the real subject, WORKFLOW_FILE pointed at
    `workflow_file`, stdout and stderr kept APART.

    The twin captures the two streams into separate files and asserts on `err()`,
    because `common.sh`'s `log_error`/`log_info` write to stderr. Merging them here
    would hide a diagnostic that moved to the wrong stream, which is a real defect
    in a gate whose whole output is diagnostics.
    """
    bash = require_gate(gate)
    return harness.run(
        [bash, os.fspath(GATE)],
        cwd=paths.repo_root(),
        env={"WORKFLOW_FILE": os.fspath(workflow_file)},
    )


def assert_mutated(gate, mutated: str, label: str) -> None:
    """The mutation must actually differ from the real file.

    Without this, a "failure" case that no longer lands would silently re-run the
    control and stay green forever. `diff -q` in the twin; a byte comparison here,
    which is the same claim made exactly.
    """
    if mutated == REAL.read_text(encoding="utf-8"):
        gate.log_fail(
            "mutation produced an identical file: %s (the workflow's shape drifted; "
            "fix the mutation)" % label
        )


def write(directory, name: str, text: str):
    """Land a mutated workflow in the case's temp dir and hand back its path."""
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- The twin's mutation toolkit, with perl's semantics reproduced on purpose. ---------------------------------------------------------------------------


def _keeplines(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _matches(line: str, pattern: str) -> bool:
    """`perl -pe '... if /^X$/'` against `$_`.

    Perl's `$_` carries the trailing newline and its `$` matches BEFORE that
    newline, so stripping one trailing newline and asking for a full match is the
    same predicate. Doing it any other way is how an anchored mutation quietly
    stops landing.
    """
    return re.fullmatch(pattern, line.rstrip("\n")) is not None


def drop_lines_containing(text: str, needle: str) -> str:
    """`grep -v <needle>`."""
    return "".join(ln for ln in _keeplines(text) if needle not in ln)


def append_after(text: str, pattern: str, addition: str, nth: int | None = None) -> str:
    """`perl -pe '$_ .= "..." if /pattern/'`, optionally gated on `++$c == nth`.

    `nth=None` appends after EVERY match, which is what the un-counted twin
    mutations do. `nth=3` appends only after the third, which is what
    `&& ++$c == 3` does -- and the counter increments only on a match, because
    perl's `&&` short-circuits.
    """
    out: list[str] = []
    count = 0
    for line in _keeplines(text):
        out.append(line)
        if _matches(line, pattern):
            count += 1
            if nth is None or count == nth:
                out.append(addition)
    return "".join(out)


def insert_before(text: str, pattern: str, addition: str) -> str:
    """`perl -pe 'print "..." if /pattern/'`.

    `print` emits BEFORE the implicit print of `$_`, so the added text lands above
    the matched line. Getting this backwards would insert a token-minting step
    AFTER the model step, which is the position the invariant permits, and the
    control would not fire.
    """
    out: list[str] = []
    for line in _keeplines(text):
        if _matches(line, pattern):
            out.append(addition)
        out.append(line)
    return "".join(out)


def substitute_once(text: str, pattern: str, repl: str) -> str:
    """`perl -pe '$done ||= s/a/b/ unless $done'`: the FIRST hit in the whole file."""
    out: list[str] = []
    done = False
    for line in _keeplines(text):
        emit = line
        if not done:
            body = line.rstrip("\n")
            replaced, hits = re.subn(pattern, repl, body, count=1)
            if hits:
                done = True
                emit = replaced + ("\n" if line.endswith("\n") else "")
        out.append(emit)
    return "".join(out)


def substitute_each_line(text: str, pattern: str, repl: str) -> str:
    """`perl -pe 's/a/b/'` and `sed 's/a/b/'`: first hit PER LINE, every line.

    Note what `sed 's/^ *"Edit",$//'` does and does not do: it empties the line, it
    does not delete it. Deleting it would shift every following line and could
    change what an indentation-sensitive parser sees, so the difference matters.
    """
    out: list[str] = []
    for line in _keeplines(text):
        body = line.rstrip("\n")
        out.append(re.sub(pattern, repl, body, count=1) + ("\n" if line.endswith("\n") else ""))
    return "".join(out)


# ---------------------------------------------------------------------------


def test_real_workflow_passes(gate):
    result = run_gate(gate, REAL)
    gate.assert_exit_code(
        0,
        result.rc,
        "the real autopilot.yml satisfies every invariant (stderr: %s)" % result.err,
    )
    gate.assert_contains(
        result.err, "invariants hold", "and says so (common.sh log_info writes to stderr)"
    )
    gate.assert_contains(
        result.err,
        "5 jobs scanned",
        "across all five jobs (gate, model, finish, escalate, sweeper)",
    )
    gate.log_pass("control: the real workflow passes the gate")


def test_missing_workflow_fails_closed(gate):
    with harness.temp_dir() as work:
        result = run_gate(gate, work / "never-written.yml")
        gate.assert_exit_code(1, result.rc, "a missing workflow must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: workflow-missing",
            "as workflow-missing (a blind gate cannot pass)",
        )
        gate.log_pass("anti-vacuity: nothing to check is a failure, not a pass")


def test_wall4_comment_is_required(gate):
    source = real_source(gate)
    mutated = drop_lines_containing(source, "WALL 4")
    assert_mutated(gate, mutated, "no-wall4.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "no-wall4.yml", mutated))
        gate.assert_exit_code(1, result.rc, "stripping the WALL 4 comments must fail")
        gate.assert_contains(
            result.err, "INVARIANT-FAIL: wall4-comment-missing", "as wall4-comment-missing"
        )
        gate.log_pass("the trusted checkout must stay explained at the point of use")


def test_event_interpolation_in_run_fails(gate):
    """Plant a payload interpolation inside the FIRST run: block.

    `env:`-passed payload values are fine; `${{ github.event.* }}` inside shell is
    the injection surface the review pipeline's zero-interpolation rule closed.
    """
    source = real_source(gate)
    mutated = append_after(
        source,
        r"\s+run: \|",
        '            echo "${{ github.event.pull_request.title }}"\n',
        nth=1,
    )
    assert_mutated(gate, mutated, "inject.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "inject.yml", mutated))
        gate.assert_exit_code(1, result.rc, "payload interpolation in a run block must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: event-interpolation-in-run",
            "as event-interpolation-in-run",
        )
    # CONTROL for the parser's scoping: the real file DOES use github.event.* in
    # if:/env:/concurrency (that is the sanctioned route), and the control test
    # above already proves those do not fire.
    if not re.search(r"github\.event\.workflow_run\.head_branch", source):
        gate.log_fail("expected the real workflow to use github.event.* outside run blocks")
    gate.log_pass("github.event.* is banned inside run blocks and only there")


def test_token_before_model_fails(gate):
    source = real_source(gate)
    mutated = insert_before(
        source,
        r"      - name: Model round",
        "      - name: Premature token\n        uses: ./.github/actions/app-token\n",
    )
    assert_mutated(gate, mutated, "pre-token.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "pre-token.yml", mutated))
        gate.assert_exit_code(1, result.rc, "an app-token step before the model step must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: token-before-model",
            "as token-before-model (invariant 1: the model never holds a write token)",
        )
        gate.log_pass("a write token minted at or before the model step is structurally impossible")


def test_token_in_gate_fails(gate):
    source = real_source(gate)
    mutated = insert_before(
        source,
        r"      - name: Locate the armed PR",
        "      - name: Gate token\n        uses: ./.github/actions/app-token\n",
    )
    assert_mutated(gate, mutated, "gate-token.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "gate-token.yml", mutated))
        gate.assert_exit_code(1, result.rc, "an app-token step in the gate job must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: token-in-gate",
            "as token-in-gate (the gate decides with zero write capability)",
        )
        gate.log_pass("the gate job can never mint a token")


def test_persisted_credentials_fail(gate):
    source = real_source(gate)
    mutated = substitute_once(source, r"persist-credentials: false", "persist-credentials: true")
    assert_mutated(gate, mutated, "persist.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "persist.yml", mutated))
        gate.assert_exit_code(1, result.rc, "a persisting checkout must fail")
        gate.assert_contains(
            result.err, "INVARIANT-FAIL: persist-credentials", "as persist-credentials"
        )
        gate.log_pass("every checkout must refuse to persist a bearer token into the workspace")


def test_untrusted_first_checkout_fails(gate):
    source = real_source(gate)
    mutated = substitute_once(source, r"^(\s+)ref: main$", r"\1ref: pr-authored-branch")
    assert_mutated(gate, mutated, "untrusted.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "untrusted.yml", mutated))
        gate.assert_exit_code(1, result.rc, "a first checkout off the trusted ref must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: trusted-checkout-not-first",
            "as trusted-checkout-not-first (wall 4)",
        )
        gate.log_pass("the first checkout of every job is pinned to rediacc/console @ main")


def test_track_progress_armed_fails(gate):
    source = real_source(gate)
    mutated = substitute_each_line(source, r"track_progress: 'false'", "track_progress: 'true'")
    assert_mutated(gate, mutated, "track.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "track.yml", mutated))
        gate.assert_exit_code(1, result.rc, "arming track_progress must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: track-progress-armed",
            "as track-progress-armed (its tag-mode fetch is the credentialed path)",
        )
        gate.log_pass("track_progress stays the literal 'false'")


def test_cancel_in_progress_armed_fails(gate):
    source = real_source(gate)
    mutated = substitute_each_line(source, r"cancel-in-progress: false", "cancel-in-progress: true")
    assert_mutated(gate, mutated, "cancel.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "cancel.yml", mutated))
        gate.assert_exit_code(1, result.rc, "cancel-in-progress: true must fail")
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: cancel-in-progress-armed",
            "as cancel-in-progress-armed (never kill a round mid-push)",
        )
        gate.log_pass("concurrency can queue rounds but never cancel one mid-push")


def test_model_without_state_guard_fails(gate):
    """The model job's `if:` must require AUTOPILOT_ALLOW_STATE.

    Strip ONLY that clause: the state-write step further down still mentions the
    flag, so a checker that grepped the whole file would pass this mutation --
    which is exactly the substitute this invariant must refuse.
    """
    source = real_source(gate)
    mutated = re.sub(
        r"      vars\.AUTOPILOT_ALLOW_MODEL == 'true' &&\n"
        r"      vars\.AUTOPILOT_ALLOW_STATE == 'true'\n",
        "      vars.AUTOPILOT_ALLOW_MODEL == 'true'\n",
        source,
        count=1,
    )
    assert_mutated(gate, mutated, "nostate.yml")
    if "AUTOPILOT_ALLOW_STATE" not in mutated:
        gate.log_fail(
            "the mutation removed every mention of the flag; it must survive elsewhere "
            "or this proves nothing"
        )
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "nostate.yml", mutated))
        gate.assert_exit_code(
            1, result.rc, "a model job that can run without the state flag must fail"
        )
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: model-without-state-guard",
            "as model-without-state-guard (a round that cannot record itself breaks the "
            "round counter)",
        )
        gate.log_pass("the model job is structurally unable to run while state writes are disarmed")


def test_model_round_file_tools_required(gate):
    """The model round's permission allowlist must include the file tools.

    The handoff contract requires the model to edit files and write handoff.json,
    and an allowlist denies everything unlisted. Live proof: runs
    31321211521/31326053280 burned 41 turns with 21 denials on an allowlist that
    simply omitted Edit/Write. Strip ONLY "Edit"; every other permission entry
    survives, so a checker that merely counts entries or greps the file for the
    word Edit (it appears in prose comments) would pass this mutation.
    """
    source = real_source(gate)
    mutated = substitute_each_line(source, r'^                  "Edit",$', "")
    assert_mutated(gate, mutated, "noedit.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "noedit.yml", mutated))
        gate.assert_exit_code(1, result.rc, "an allowlist without Edit must fail")
        gate.assert_contains(
            result.err,
            "model-round-file-tools",
            "as model-round-file-tools (the omission class every other permission check passes)",
        )
        gate.log_pass("the model round cannot lose its file tools silently")


def test_unparsed_model_if_fails_closed(gate):
    """Anti-vacuity for the invariant above: if the model job's `if:` cannot be
    found at all, the check verified nothing and must say so rather than pass.
    Renaming the job is the cheapest way to make it unfindable."""
    source = real_source(gate)
    mutated = substitute_each_line(source, r"^  model:$", "  modelx:")
    assert_mutated(gate, mutated, "nomodeljob.yml")
    with harness.temp_dir() as work:
        result = run_gate(gate, write(work, "nomodeljob.yml", mutated))
        gate.assert_exit_code(1, result.rc, "an unfindable model if: must fail")
        gate.assert_contains(
            result.err, "an unparsed guard cannot pass", "naming the anti-vacuity reason"
        )
        gate.log_pass("anti-vacuity: an invariant that cannot locate its subject fails closed")


def test_submodule_checkout_before_model_fails(gate):
    """S6 makes submodule PUSHES possible after the model exits. The tempting
    follow-on is to let the model EDIT submodules by adding `submodules:` to its
    checkout -- but the four submodules are private, so that fetch needs a
    credential, and a credential before the model step is the one thing this design
    exists to prevent."""
    source = real_source(gate)
    with harness.temp_dir() as work:
        mutated = append_after(
            source, r"          filter: blob:none", "          submodules: recursive\n"
        )
        assert_mutated(gate, mutated, "sub-checkout.yml")
        result = run_gate(gate, write(work, "sub-checkout.yml", mutated))
        gate.assert_exit_code(
            1, result.rc, "a submodule-fetching checkout before the model must fail"
        )
        gate.assert_contains(
            result.err,
            "INVARIANT-FAIL: submodule-checkout-pre-model",
            "as submodule-checkout-pre-model",
        )
        gate.assert_contains(result.err, "(model)", "attributed to the model job")

        # CONTROL 1: an explicit `submodules: false` is the harmless spelling and must not fire, or the rule would ban writing the safe thing down.
        harmless = append_after(
            source, r"          filter: blob:none", "          submodules: false\n"
        )
        assert_mutated(gate, harmless, "sub-false.yml")
        result = run_gate(gate, write(work, "sub-false.yml", harmless))
        gate.assert_exit_code(
            0,
            result.rc,
            "an explicit submodules: false is fine (stderr: %s)" % result.err,
        )

        # CONTROL 2: the rule is about POSITION, not about the word. The finish job runs no model, so a submodule checkout there is not a pre-model credential and must pass.
        elsewhere = append_after(
            source, r"          ref: main", "          submodules: recursive\n", nth=3
        )
        assert_mutated(gate, elsewhere, "sub-finish.yml")
        result = run_gate(gate, write(work, "sub-finish.yml", elsewhere))
        gate.assert_exit_code(
            0,
            result.rc,
            "a submodule checkout in a modelless job is not a pre-model credential "
            "(stderr: %s)" % result.err,
        )
        gate.log_pass("submodules may be fetched after the model exits, never before it")


def test_the_mutated_corpus_is_non_trivial(gate):
    """ADDED BY THE PORT: print the shape, so a collapse is visible.

    Every case above mutates a copy of one file. If that file shrank to a stub the
    mutations would stop landing and `assert_mutated` would fire -- but the reader
    would be told "the mutation produced an identical file", which points at the
    mutation rather than at the corpus. This states the corpus size directly, and
    refuses a workflow with no jobs at all rather than letting an empty scan read
    as a clean one.
    """
    source = real_source(gate)
    lines = source.count("\n")
    jobs = len(re.findall(r"^  [A-Za-z_][A-Za-z0-9_-]*:[ \t]*$", source, re.MULTILINE))
    if jobs == 0 or lines == 0:
        gate.log_fail(
            "%s scanned %d line(s) and %d job-shaped key(s); a workflow the gate cannot "
            "see is not a workflow that passes." % (REAL_REL, lines, jobs)
        )
    gate.log_pass(
        "corpus is non-trivial: %s holds %d line(s) and %d job-shaped key(s)"
        % (REAL_REL, lines, jobs)
    )
