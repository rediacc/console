"""`rediacc_ci.core.release_age` against the live `release-age.sh`.

THE TWIN IS LIVE HERE, NOT FROZEN. `.ci/scripts/lib/release-age.sh` is still sourced by `.ci/scripts/security/audit.sh:39` and `.ci/scripts/quality/check-go-deps.sh:43`, so the real file is what runs on both sides of every comparison below.

BOTH SIDES DELEGATE TO THE SAME `scripts/lib/release-age.ts`, which is the point: this is a differential over a TRANSPORT, and any disagreement is a transport bug rather than a rounding argument. The rule itself is proved elsewhere (`scripts/lib/release-age.ts` is the only round-up in the tree).

FOUR FIXTURE TREES, because three of the interesting behaviours are unreachable against the real repository:

  `ft_ok`        `release-age.ts` present, `.npmrc` says 60 minutes  -> window 3600
  `ft_no_npmrc`  `release-age.ts` present, NO `.npmrc`               -> window 86400
  `ft_broken`    NO `release-age.ts`, a `tsx` stub that exits 1      -> loud refusal
  the real repo  window 86400

THE REAL REPO CANNOT DISTINGUISH THE FALLBACK FROM THE ANSWER, and that is why
`ft_no_npmrc` exists: this repo's `.npmrc` carries `minimum-release-age=1440`
MINUTES, which is 86400 seconds, exactly the number `RELEASE_AGE_DEFAULT_WINDOW_SECONDS` falls back to. A test written against the real tree would pass whether the delegate answered or not, which is the shape of a control that cannot fail.

TWO DEFECTS OF THE TWIN ARE PINNED HERE AS FACTS ABOUT THE BASH, not reproduced in the port. Both are argued in `rediacc_ci.core.release_age`'s docstring, and the tests that hold them (`test_the_twins_runner_memo_never_persists` and `test_the_twin_lets_bash_arithmetic_decide_an_unvalidated_now`) drive the TWIN, so if either is ever fixed in `.ci/scripts/lib/` these go red and say
so.
"""

import hashlib
import importlib.util
import pathlib
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.core import release_age as ra
from rediacc_ci.tests import differential as diff

TWIN_REL = ".ci/scripts/lib/release-age.sh"
TS_REL = "scripts/lib/release-age.ts"
PORT = ".ci/rediacc_ci/core/release_age.py"

# The bash driver, a string in this file rather than a script under `.ci/`: ruling 7 freezes the tracked `.sh` count and a driver belongs to the TEST. `$LIB` so the same driver serves the real tree and every fixture tree.
BASH_DRIVER = """
set -uo pipefail
source "$LIB"
case "$1" in
  window-seconds) release_age_window_seconds ;;
  eligible-epoch) release_eligible_epoch "$2" "${3:-}" ;;
  deferred)
    if is_release_deferred "$2" "${3:-}" "${4:-}"; then echo deferred; else echo eligible; exit 1; fi ;;
  *) echo "unknown verb $1" >&2; exit 2 ;;
esac
"""

PY = "PYTHONPATH=%s python3 -m rediacc_ci.core.release_age" % paths.from_root(".ci")


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def _both(argv: list[str], *, root: pathlib.Path | None = None):
    """Run the twin and the port over identical arguments, streams separate."""
    lib = str((root or paths.repo_root()) / TWIN_REL)
    quoted = " ".join(_sh(a) for a in argv)
    old = diff.bash_streams(
        "bash -c %s bash %s" % (_sh(BASH_DRIVER), quoted),
        env=diff.env_for(LIB=lib),
    )
    new_env = diff.env_for()
    if root is not None:
        new_env = diff.env_for(REDIACC_CI_ROOT=str(root))
    new = diff.bash_streams("%s %s" % (PY, quoted), env=new_env)
    return old, new


# --------------------------------------------------------------------------- The fixture trees ---------------------------------------------------------------------------


def _seed(root: pathlib.Path, *, with_ts: bool, npmrc: str | None, tsx_stub: bool) -> pathlib.Path:
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(paths.from_root(TWIN_REL), root / TWIN_REL)
    if with_ts:
        shutil.copy(paths.from_root(TS_REL), root / TS_REL)
    if npmrc is not None:
        (root / ".npmrc").write_text(npmrc, encoding="utf-8")
    if tsx_stub:
        binroot = root / "node_modules" / ".bin"
        binroot.mkdir(parents=True)
        stub = binroot / "tsx"
        # A stub that FAILS rather than one that is absent: absent would send the ladder to `npx tsx`, which resolves over the network and would make this suite depend on a registry.
        stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        stub.chmod(0o755)
    return root


@pytest.fixture(scope="module")
def ft_ok(tmp_path_factory):
    return _seed(
        tmp_path_factory.mktemp("ft_ok"),
        with_ts=True,
        npmrc="minimum-release-age=60\n",
        tsx_stub=False,
    )


@pytest.fixture(scope="module")
def ft_no_npmrc(tmp_path_factory):
    return _seed(tmp_path_factory.mktemp("ft_no"), with_ts=True, npmrc=None, tsx_stub=False)


@pytest.fixture(scope="module")
def ft_broken(tmp_path_factory):
    return _seed(tmp_path_factory.mktemp("ft_bad"), with_ts=False, npmrc=None, tsx_stub=True)


# --------------------------------------------------------------------------- 1. The verbs, byte for byte, against the real tree ---------------------------------------------------------------------------

CASES = [
    ("window-seconds", ["window-seconds"]),
    ("eligible-default-window", ["eligible-epoch", "1756000000"]),
    ("eligible-explicit-window", ["eligible-epoch", "1756000000", "3600"]),
    ("eligible-window-zero", ["eligible-epoch", "1756000000", "0"]),
    # `:179` accepts `^-?[0-9]+$`, one character wider than the two `^[0-9]+$` tests, so a pre-1970 publish epoch round-trips.
    ("eligible-negative-epoch", ["eligible-epoch", "-100", "86400"]),
    ("eligible-epoch-zero", ["eligible-epoch", "0", "86400"]),
    ("eligible-non-numeric", ["eligible-epoch", "not-a-number", "86400"]),
    ("eligible-empty-epoch", ["eligible-epoch", "", "86400"]),
    ("deferred-yes", ["deferred", "1756000000", "1756100000"]),
    ("deferred-no", ["deferred", "1756000000", "1900000000"]),
    # The boundary: `now == eligibleAt` is ELIGIBLE, because the comparison is
    # strict (`now < eligibleAt`). One second earlier is deferred.
    ("deferred-exactly-at-the-boundary", ["deferred", "1756000000", "1756166400", "86400"]),
    ("deferred-one-second-before", ["deferred", "1756000000", "1756166399", "86400"]),
    ("deferred-empty-publish", ["deferred", ""]),
    ("deferred-non-numeric-publish", ["deferred", "not-a-number"]),
    ("deferred-negative-publish", ["deferred", "-5"]),
    ("deferred-explicit-window", ["deferred", "1756000000", "1756100000", "3600"]),
]


@pytest.mark.parametrize(("case", "argv"), CASES, ids=[c[0] for c in CASES])
def test_the_verbs_agree_byte_for_byte(case, argv):
    old, new = _both(argv)
    assert old == new, "case %s: %r != %r" % (case, old, new)


@pytest.mark.parametrize(("case", "argv"), CASES, ids=[c[0] for c in CASES])
def test_the_verbs_agree_on_a_tree_whose_npmrc_says_sixty_minutes(ft_ok, case, argv):
    """The window is 3600 here, so every default-window answer MOVES.

    Against the real tree the window is 86400, which is also the fallback, so this fixture is what proves the delegate is being consulted at all.
    """
    old, new = _both(argv, root=ft_ok)
    assert old == new, "case %s: %r != %r" % (case, old, new)


def test_the_window_fixture_is_not_vacuous(ft_ok, ft_no_npmrc):
    """The three trees must give three DIFFERENT windows, or nothing above holds."""
    live, _ = _both(["window-seconds"])
    sixty, _ = _both(["window-seconds"], root=ft_ok)
    absent, _ = _both(["window-seconds"], root=ft_no_npmrc)
    assert live[1].strip() == "86400"
    assert sixty[1].strip() == "3600"
    assert absent[1].strip() == "86400"
    assert sixty[1] != absent[1], (
        "the .npmrc fixture changed nothing, so these tests cannot tell the delegate's "
        "answer from the 86400 fallback"
    )


# --------------------------------------------------------------------------- 2. The unreachable delegate, which is the branch that decides fail-closed ---------------------------------------------------------------------------

BROKEN_CASES = [
    ("window-seconds-falls-back", ["window-seconds"]),
    ("eligible-refuses-loudly", ["eligible-epoch", "1756000000", "86400"]),
    ("deferred-fails-closed", ["deferred", "1756000000", "1756100000", "86400"]),
    (
        "deferred-fails-closed-even-when-now-is-far-future",
        ["deferred", "1756000000", "1900000000", "86400"],
    ),
]


@pytest.mark.parametrize(("case", "argv"), BROKEN_CASES, ids=[c[0] for c in BROKEN_CASES])
def test_an_unreachable_delegate_behaves_identically(ft_broken, case, argv):
    old, new = _both(argv, root=ft_broken)
    assert old == new, "case %s: %r != %r" % (case, old, new)


def test_the_unreachable_delegate_is_loud_and_fails_closed(ft_broken):
    """The two halves of the policy, asserted rather than assumed from equality.

    A silent fallback here would make every version look eligible, or every one deferred, depending on the sentinel chosen, and a freshness gate that quietly stops deferring is exactly the shape this repo keeps getting caught by.
    """
    old, new = _both(["deferred", "1756000000", "1900000000", "86400"], root=ft_broken)
    expected = (
        "release-age: could not reach scripts/lib/release-age.ts (tsx missing or "
        "failing); treating '1756000000' as DEFERRED"
    )
    assert expected in old[2]
    assert expected in new[2]
    # 1900000000 is well past any eligibility, so a working delegate says ELIGIBLE. Both sides must say DEFERRED anyway.
    assert old[1].strip() == new[1].strip() == "deferred"
    assert old[0] == new[0] == 0
    working, _ = _both(["deferred", "1756000000", "1900000000", "86400"])
    assert working[1].strip() == "eligible", "the control is vacuous: this case is deferred anyway"


def test_a_failed_lookup_is_not_memoised(ft_broken):
    """`release-age.sh:190` writes the cache only AFTER the regex accepts.

    A transient delegate failure must be retried on the next call rather than frozen into the run; a port that cached `None` would make one network blip defer every remaining version in the gate.
    """
    shim = ra.ReleaseAge(ft_broken)
    assert shim.eligible_epoch(1756000000, 86400) is None
    assert (1756000000, 86400) not in shim._eligible
    assert shim.eligible_epoch(1756000000, 86400) is None


def test_a_successful_lookup_is_memoised(ft_ok):
    """The memo the twin's globals exist for, on the port's side."""
    shim = ra.ReleaseAge(ft_ok)
    first = shim.eligible_epoch(1756000000, 86400)
    calls = shim.delegate_calls
    assert first is not None
    assert shim.eligible_epoch(1756000000, 86400) == first
    assert shim.delegate_calls == calls, "the second lookup spawned the delegate again"
    assert shim.eligible_epoch(1756000001, 86400) is not None
    assert shim.delegate_calls == calls + 1, "a DIFFERENT key must miss the memo"


# --------------------------------------------------------------------------- 3. DEFECT 1: the twin's runner memo never persists ---------------------------------------------------------------------------


@pytest.fixture
def counting_node(tmp_path):
    """A `node` first on PATH that appends one line per invocation, then execs.

    Counting the CHILD PROCESSES is the only way to see this defect: the twin's verdicts are correct, and the only symptom is how many times it starts node.
    """
    real = shutil.which("node")
    if real is None:
        pytest.skip("node is not on PATH; the runner ladder's first rung cannot be observed")
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    log = tmp_path / "node-calls.log"
    wrapper = bindir / "node"
    wrapper.write_text(
        '#!/bin/bash\necho "$*" >> %s\nexec %s "$@"\n' % (log, real), encoding="utf-8"
    )
    wrapper.chmod(0o755)
    log.write_text("", encoding="utf-8")
    return bindir, log


def _counts(log: pathlib.Path) -> tuple[int, int]:
    """(total node starts, `--window-seconds` starts).

    THE SECOND NUMBER IS NOT THE PROBE COUNT, and conflating them cost this test its first run: the ladder's probe and the real window query are the SAME command line, so exactly one of the `--window-seconds` starts is a genuine query and the rest are probes.
    """
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    window = [line for line in lines if line.endswith("--window-seconds")]
    return len(lines), len(window)


def test_the_twins_runner_memo_never_persists(ft_ok, counting_node):
    """N+1 PROBES FOR N VERDICTS. Measured, not asserted from reading.

    `__release_age_resolve_runner` assigns `__RELEASE_AGE_RUNNER`, but it is only
    ever reached from inside `answer=$(__release_age_delegate ...)`, which is a
    command SUBSTITUTION and therefore a subshell. The assignment dies with it, so every delegate call re-runs the `--window-seconds` probe before doing the real query. The file's own comment at `:140-147` diagnoses exactly this trap
    for the caches while the runner falls into it, and `:95-97` claims the runner
    is chosen "ONCE per shell process".

    IF THIS TEST GOES RED, THE TWIN WAS FIXED. Delete it, and delete DEFECT 1
    from `rediacc_ci.core.release_age`'s docstring.
    """
    bindir, log = counting_node
    epochs = [1756000001, 1756000002, 1756000003, 1756000004, 1756000005]
    script = "\n".join("is_release_deferred %d 1756100000 >/dev/null || true" % e for e in epochs)
    rc, out, err = diff.bash_streams(
        'source "$LIB"\n%s\necho "runner=[$__RELEASE_AGE_RUNNER]"' % script,
        env=diff.env_for(
            LIB=str(paths.from_root(TWIN_REL, root=ft_ok)),
            PATH="%s:%s" % (bindir, diff.BASE_ENV["PATH"]),
        ),
        cwd=str(ft_ok),
    )
    assert rc == 0, err
    assert "runner=[]" in out, (
        "the twin's runner variable survived a call, which means the memo works and "
        "this test is measuring something else"
    )
    total, window_starts = _counts(log)
    delegate_calls = len(epochs) + 1  # one window query plus one per epoch
    probes = window_starts - 1  # every `--window-seconds` start bar the real query
    assert probes == delegate_calls, (
        "expected ONE probe per delegate call (%d calls), saw %d probe(s) among %d "
        "`--window-seconds` start(s)" % (delegate_calls, probes, window_starts)
    )
    assert total == 2 * delegate_calls, (
        "expected %d node starts (a probe and a query per delegate call), saw %d"
        % (2 * delegate_calls, total)
    )


def test_the_port_probes_exactly_once(ft_ok, counting_node, monkeypatch):
    """The divergence, measured on the same instrument as the defect above."""
    bindir, log = counting_node
    monkeypatch.setenv("PATH", "%s:%s" % (bindir, diff.BASE_ENV["PATH"]))
    shim = ra.ReleaseAge(ft_ok)
    epochs = [1756000001, 1756000002, 1756000003, 1756000004, 1756000005]
    for epoch in epochs:
        shim.is_release_deferred(epoch, 1756100000)
    total, window_starts = _counts(log)
    assert window_starts == 2, (
        "expected exactly two `--window-seconds` starts (ONE probe for the whole "
        "process, plus the real window query), saw %d" % window_starts
    )
    assert total == len(epochs) + 2, "expected %d node starts, saw %d" % (
        len(epochs) + 2,
        total,
    )
    # AND THE VERDICTS ARE THE SAME ONES, which is what makes the divergence safe.
    old, new = _both(["deferred", "1756000001", "1756100000"], root=ft_ok)
    assert old == new


# --------------------------------------------------------------------------- 4. DEFECT 2: `now` is unvalidated on the twin, and its failure is fail-OPEN ---------------------------------------------------------------------------

# (case, now, what bash arithmetic makes of it, the verdict that follows)
NOW_SHAPES = [
    ("bare-word-resolves-as-an-unset-variable", "abc", "deferred"),
    ("subtraction", "9-9", "deferred"),
    ("hex-literal", "0x10", "deferred"),
    # THE ONE THAT MATTERS. A number with a stray suffix is an arithmetic ERROR, `(( ))` returns 1, and the twin reports ELIGIBLE: the exact false "must upgrade" its own fail-closed rule exists to prevent.
    ("number-with-a-suffix", "1756100000x", "eligible"),
]


@pytest.mark.parametrize(("case", "now", "expected"), NOW_SHAPES, ids=[c[0] for c in NOW_SHAPES])
def test_the_twin_lets_bash_arithmetic_decide_an_unvalidated_now(case, now, expected):
    """A FACT ABOUT THE BASH, pinned so it cannot change unnoticed.

    LATENT, NOT LIVE: both real call sites pass one argument (`audit.sh:271`, `check-go-deps.sh:151`), so `now` is always `date -u +%s` today. `.ci/scripts/lib/` is not this box's to edit, so the twin is not fixed here; the port refuses a non-integer `now` instead, which is the divergence.
    """
    rc, out, err = diff.bash_streams(
        'source "$LIB"\nif is_release_deferred 1756000000 %s 86400 2>/dev/null; '
        "then echo deferred; else echo eligible; fi" % _sh(now),
        env=diff.env_for(LIB=str(paths.from_root(TWIN_REL))),
    )
    assert rc == 0, err
    assert out.strip() == expected, "case %s: expected %s, got %r" % (case, expected, out)


def test_the_port_refuses_a_now_it_cannot_read(ft_ok):
    """The divergence, in the direction the fail-closed policy points."""
    shim = ra.ReleaseAge(ft_ok)
    with pytest.raises(ValueError, match="invalid literal for int"):
        shim.is_release_deferred(1756000000, "1756100000x", 86400)  # type: ignore[arg-type]
    # A real integer still works, so the refusal is not blanket.
    assert shim.is_release_deferred(1756000000, 1756100000, 86400) is True


# --------------------------------------------------------------------------- 5. The ladder itself ---------------------------------------------------------------------------


def test_the_fast_rung_is_proven_before_it_is_adopted(ft_broken):
    """A node that cannot answer must fall THROUGH, not poison every verdict.

    `ft_broken` has no `release-age.ts`, so the probe runs, fails, and the ladder must land on the local `tsx` stub rather than on `node --experimental-strip-types`.
    """
    shim = ra.ReleaseAge(ft_broken)
    runner = shim.resolve_runner()
    assert runner == [str(ft_broken / "node_modules" / ".bin" / "tsx")], runner
    assert shim.probe_calls == 1, "the probe did not run, so nothing was proven"


def test_the_fast_rung_is_taken_when_it_answers(ft_ok):
    shim = ra.ReleaseAge(ft_ok)
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    assert shim.resolve_runner() == ["node", "--experimental-strip-types"]


# --------------------------------------------------------------------------- 6. The planted defects ---------------------------------------------------------------------------


def _digest(rel: str) -> str:
    return hashlib.sha256(pathlib.Path(paths.from_root(rel)).read_bytes()).hexdigest()


def _load_mutated(tmp_path, old: str, new: str, name: str):
    """Load a MUTATED COPY of the port from a tmpdir, under a fresh module name.

    The real file is never opened for writing, so an aborted test cannot leave the tree broken.
    """
    source = pathlib.Path(paths.from_root(PORT)).read_text(encoding="utf-8")
    assert old in source, "the plant did not land: %r is not in the port" % old
    target = tmp_path / ("%s.py" % name)
    target.write_text(source.replace(old, new, 1), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_planted_defect_in_the_port_is_caught(tmp_path, ft_ok, ft_broken):
    """THE CONTROL FOR EVERY CASE ABOVE. Three real mutations, each caught."""
    before = _digest(PORT)

    # PLANT 1: fail-OPEN on an unreachable delegate. This is the defect the twin's loud refusal exists to make impossible, and a gate carrying it would report every version as installable while the delegate was down.
    m1 = _load_mutated(
        tmp_path,
        "        if eligible is None:\n            return True",
        "        if eligible is None:\n            return False",
        "ra_p1",
    )
    assert ra.ReleaseAge(ft_broken).is_release_deferred(1756000000, 1756100000, 86400) is True
    assert m1.ReleaseAge(ft_broken).is_release_deferred(1756000000, 1756100000, 86400) is False, (
        "the mutation did not change the verdict, so this control proves nothing"
    )

    # PLANT 2: the window fallback made unconditional, which silently disables deferral tuning on every tree whose .npmrc says something else.
    m2 = _load_mutated(
        tmp_path,
        "        if answer is None or not _UNSIGNED.fullmatch(answer) or int(answer) <= 0:",
        "        if True:",
        "ra_p2",
    )
    assert ra.ReleaseAge(ft_ok).window_seconds() == 3600
    assert m2.ReleaseAge(ft_ok).window_seconds() == 86400, (
        "the fixture's 60-minute window did not survive, so plant 2 is invisible"
    )

    # PLANT 3: the strict comparison relaxed. `now == eligibleAt` is ELIGIBLE.
    m3 = _load_mutated(tmp_path, "return moment < eligible", "return moment <= eligible", "ra_p3")
    boundary = ra.ReleaseAge(ft_ok).eligible_epoch(1756000000, 86400)
    assert boundary is not None
    assert ra.ReleaseAge(ft_ok).is_release_deferred(1756000000, boundary, 86400) is False
    assert m3.ReleaseAge(ft_ok).is_release_deferred(1756000000, boundary, 86400) is True, (
        "the boundary moved by one second and nothing noticed"
    )

    assert _digest(PORT) == before, "a planted defect was written to the real module"


def test_the_differential_itself_can_fail():
    """A comparison that compares nothing scores everything as equivalent."""
    old, new = _both(["eligible-epoch", "1756000000", "86400"])
    assert old == new
    assert old != (new[0] + 1, new[1], new[2]), "the comparison ignores the exit code"
    assert old != (new[0], new[1] + "x", new[2]), "the comparison ignores stdout"
    assert old != (new[0], new[1], new[2] + "x"), "the comparison ignores stderr"
    assert old[1].strip() == "1756166400", "the case produced no answer to compare"
