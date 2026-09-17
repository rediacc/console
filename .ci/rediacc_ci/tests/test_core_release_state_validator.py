"""`rediacc_ci.core.release_state_validator` against the bash it was ported from.

WHAT EACH GROUP OF CASES GUARDS.

  the differential    Every assertion and the floor, run on BOTH sides over a
                      combinatorial corpus and compared byte-for-byte on stdout
                      AND on the exit code. This is the bulk of the file and it
                      is what makes the port evidence rather than a claim.
  the planted defect  A MUTATED COPY of the module must make that same
                      differential FAIL. A differential nobody has ever seen go
                      red is not a differential; it is a green light with a
                      comparison-shaped hole in it. The mutation is applied to a
                      throwaway copy on disk and the real file's sha256 is
                      re-asserted afterwards, so the control cannot damage the
                      thing it is proving.
  the three states    `Probe` must not be an `int`. In shell 0 is TRUE, in
                      Python 0 is FALSE, and `if sentinel_exists(...)` reading
                      backwards is the one bug a faithful port of this library
                      would have introduced.
  the twin's defects  Three findings are PINNED rather than fixed, because
                      `.ci/scripts/lib/` is outside this workstream's write
                      grant. Each pin goes RED the day the twin is repaired,
                      which is the point: a finding recorded only in prose is a
                      finding that rots.
  the anti-vacuity    The corpus must be non-trivial and the differential must
                      actually have compared something. A test that skipped
                      every case would otherwise pass.

THE FINDINGS, so they are not only in the module docstring:

  1. `log_error` is called at `release-state-validator.sh:145,178,187,227` and
     is defined NOWHERE in that file, which sources nothing. Every production
     caller happens to source `common.sh` first. Driven live: the call is
     `command not found` (127), errexit fires, and the function dies before its
     `rm -f "$err"` and before its documented `return 1`.
  2. `rsv_list_sentinels:112` conflates "the bucket is empty" with "the probe
     failed", which is exactly what the same file refuses for its three siblings
     at :128-132 and :194-200, and it is the one feeding the BLOCKER gate.
  3. `rsv_drop_pre_contract` is defined INSIDE `rsv_assert_bijection` (:365) and
     bash has no nested function scope, so the name leaks globally while
     reading a `local` from its definer.
"""

import hashlib
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import release_state_validator as rsv
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/lib/release-state-validator.sh"
PORT = ".ci/rediacc_ci/core/release_state_validator.py"

# The versions every case is built from. Deliberately mixed: * two that straddle the real ratchet floor (v1.2.21), * a pair whose STRING order and VERSION order disagree (v1.3.0 / v1.10.0), * a pre-release tag, which the contract excludes rather than judges, * a non-version and the empty string, which every loop must skip.
CORPUS = (
    "v1.0.0",
    "v1.2.21",
    "v1.2.3",
    "v1.3.0",
    "v1.3.1",
    "v1.10.0",
    "v2.0.0",
    "v1.2.21-rc1",
    "notaversion",
    "",
)

# A floor that is NOT the repository's own, so a case cannot pass by accident because the real ratchet happened to agree with it.
FLOORS = {
    "empty": "",
    "one": "v1.2.21\n",
    "two-oldest-second": "# comment\nv1.5.0\nv1.0.0\n",
    "blank": "\n",
    "junk": "junk\n",
}


class Deck:
    """A deterministic sampler. NOT `random`, and not only because of a lint rule.

    A corpus that is re-sampled by `random.Random` is reproducible only for as long as CPython's Mersenne stream and `random.sample`'s internals stay put. This is nine lines of arithmetic that will produce the same corpus on every interpreter forever, which is the actual property a frozen differential
    needs. The constants are the Numerical Recipes LCG; nothing here is
    cryptographic and nothing here pretends to be.
    """

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def _next(self) -> int:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state

    def below(self, bound: int) -> int:
        return self._next() % bound if bound > 0 else 0

    def choice(self, values: tuple) -> object:
        return values[self.below(len(values))]

    def sample(self, values: tuple, count: int) -> list:
        """`count` distinct members, in a stable order. Never repeats one."""
        pool = list(values)
        return [pool.pop(self.below(len(pool))) for _ in range(min(count, len(pool)))]


# Credentials for the DEFECT 1 driver below. Pointed at `example.invalid`, so nothing here can reach a real endpoint even if the probe were to run.
FAKE_R2_ENV = {
    "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
    "AWS_ACCESS_KEY_ID": "x",
    "AWS_SECRET_ACCESS_KEY": "y",
}


def _q(value: str) -> str:
    """Single-quote for bash."""
    return "'" + value.replace("'", "'\\''") + "'"


def _twin() -> pathlib.Path:
    return paths.from_root(TWIN)


def _bash(function: str, args: list[str], **env: str) -> tuple[int, str, str]:
    """Source the twin and call ONE function. Returns (rc, stdout, stderr).

    `set -uo pipefail` and NOT `-e`, matching how every real caller invokes
    these: `rsv_assert_bijection ... || rc=$?` at check-release-state.sh:50 and
    `out="$(...)" || rc=$?` at test-release-state-consistency.sh:40. Adding `-e`
    here would make the harness abort where the callers keep going, which is a difference in the TEST rather than in the thing under test.
    """
    script = "set -uo pipefail\nsource %s\n%s %s\n" % (
        _q(str(_twin())),
        function,
        " ".join(_q(a) for a in args),
    )
    return diff.bash_streams(script, env=diff.env_for(**env))


def _joined(lines: list[str]) -> str:
    """The port's line list as the bytes the twin's `echo`s would produce."""
    return "".join(line + "\n" for line in lines)


# --------------------------------------------------------------------------- The differential: bijection ---------------------------------------------------------------------------


def _bijection_cases() -> list[tuple[str, str, str, str | None]]:
    """A deterministic sample of (cli, tags, in_flight, override).

    SEEDED, not random-per-run. A differential that samples a different corpus on every run is a differential that can pass today and fail tomorrow for a reason nobody can reproduce, and the first thing anyone does with that is re-run it until it is green.
    """
    rng = Deck(20260910)
    cases: list[tuple[str, str, str, str | None]] = []
    # Exhaustive over the small, interesting shapes first: these are the ones a reviewer can check by hand.
    for cli, tag in itertools.product(("", "v1.3.0", "v1.3.0\nv1.10.0"), repeat=2):
        cases.append((cli, tag, "", None))
        cases.append((cli, tag, "v1.10.0", None))
    # Then a seeded sample over the whole corpus, which is where the version ordering and the pre-release filter get exercised together.
    cases.extend(
        (
            "\n".join(rng.sample(CORPUS, rng.below(6))),
            "\n".join(rng.sample(CORPUS, rng.below(6))),
            rng.choice(("", "v1.3.1", "v2.0.0")),
            rng.choice((None, None, None, "v1.2.21", "v9.9.9", "junk")),
        )
        for _ in range(120)
    )
    return cases


BIJECTION_CASES = _bijection_cases()


@pytest.mark.parametrize(("cli", "tags", "in_flight", "override"), BIJECTION_CASES)
def test_bijection_matches_the_twin(
    cli: str, tags: str, in_flight: str, override: str | None
) -> None:
    """`rsv_assert_bijection` and `assert_bijection` agree on stdout AND rc.

    THE RATCHET IS PINNED AWAY ON BOTH SIDES with `RSV_FLOOR_FILE=/dev/null`, so
    the case is deciding what it says it is deciding. Without that the repo's own `.ci/config/release-contract-floor.txt` supplies a floor to every case and the `observed` half of the function is never exercised alone.
    """
    env = {"RSV_FLOOR_FILE": "/dev/null"}
    if override is not None:
        env["RSV_GRANDFATHER_BEFORE"] = override
    rc, out, _err = _bash("rsv_assert_bijection", [cli, tags, in_flight], **env)
    lines, prc = rsv.assert_bijection(rsv.records(cli), rsv.records(tags), in_flight, env=env)
    assert (out, rc) == (_joined(lines), prc)


def test_the_bijection_corpus_is_not_trivial() -> None:
    """ANTI-VACUITY. The cases above must produce BOTH verdicts and real drift.

    A corpus that only ever produced `OK` would pass the differential while proving nothing about the half of the function that finds things.
    """
    verdicts = set()
    drift_lines = 0
    for cli, tags, in_flight, override in BIJECTION_CASES:
        env = {"RSV_FLOOR_FILE": "/dev/null"}
        if override is not None:
            env["RSV_GRANDFATHER_BEFORE"] = override
        lines, rc = rsv.assert_bijection(rsv.records(cli), rsv.records(tags), in_flight, env=env)
        verdicts.add(rc)
        drift_lines += sum(1 for line in lines if line.startswith("DRIFT "))
    assert verdicts == {0, 1}, "the corpus never reached one of the two verdicts"
    assert drift_lines >= 50, "only %d DRIFT lines; the corpus has gone quiet" % drift_lines
    assert len(BIJECTION_CASES) >= 100


# --------------------------------------------------------------------------- The differential: the channel pointer ---------------------------------------------------------------------------


def _pointer_cases() -> list[tuple[str, str, str, str, str]]:
    rng = Deck(20260911)
    cases: list[tuple[str, str, str, str, str]] = []
    # The four hand-picked shapes the twin's own comments are about.
    cases.append(("edge", "", "v1.3.1", "v1.3.1", ""))  # unreadable latest
    cases.append(("edge", "v1.3.1", "", "v1.3.1", ""))  # unreadable manifest
    cases.append(("stable", "v1.3.1", "v1.3.0", "v1.3.1\nv1.3.0", ""))  # torn write
    cases.append(("edge", "v1.3.1", "v1.3.1", "v1.3.0", ""))  # named, untagged
    cases.append(("edge", "v1.3.1", "v1.3.1", "v1.3.0", "v1.3.1"))  # in-flight
    # AND THE CLEAN ONE, hand-picked rather than hoped for. The seeded sample below happened to produce zero of these, and `test_the_pointer_corpus_is _not_trivial` caught it: a corpus that only ever reaches the four FINDING branches proves nothing about the branch that says a pointer is fine.
    cases.append(("stable", "v1.3.0", "v1.3.0", "v1.3.0\nv1.10.0", ""))  # tagged, clean
    cases.extend(
        (
            rng.choice(rsv.CHANNELS),
            rng.choice(CORPUS),
            rng.choice(CORPUS),
            "\n".join(rng.sample(CORPUS, rng.below(5))),
            rng.choice(("", "v1.3.1", "v2.0.0")),
        )
        for _ in range(120)
    )
    return cases


POINTER_CASES = _pointer_cases()


@pytest.mark.parametrize(("channel", "latest", "manifest", "tags", "in_flight"), POINTER_CASES)
def test_channel_pointer_matches_the_twin(
    channel: str, latest: str, manifest: str, tags: str, in_flight: str
) -> None:
    """`rsv_assert_channel_pointer_tagged` and its port agree on stdout AND rc."""
    rc, out, _err = _bash(
        "rsv_assert_channel_pointer_tagged", [channel, latest, manifest, tags, in_flight]
    )
    lines, prc = rsv.assert_channel_pointer_tagged(
        channel, latest, manifest, rsv.records(tags), in_flight
    )
    assert (out, rc) == (_joined(lines), prc)


def test_the_pointer_corpus_is_not_trivial() -> None:
    """ANTI-VACUITY. All FOUR of the pointer's findings must appear."""
    seen = set()
    for channel, latest, manifest, tags, in_flight in POINTER_CASES:
        lines, _rc = rsv.assert_channel_pointer_tagged(
            channel, latest, manifest, rsv.records(tags), in_flight
        )
        for line in lines:
            if "could not read the channel pointer" in line:
                seen.add("unreadable")
            elif "torn write" in line:
                seen.add("torn")
            elif "has NO git tag" in line:
                seen.add("untagged")
            elif "tag not expected yet" in line:
                seen.add("in-flight")
            elif "which is tagged" in line:
                seen.add("ok")
    assert seen == {"unreadable", "torn", "untagged", "in-flight", "ok"}, sorted(seen)


# --------------------------------------------------------------------------- The differential: the pre-contract floor ---------------------------------------------------------------------------


@pytest.mark.parametrize("floor_name", sorted(FLOORS))
@pytest.mark.parametrize(
    "cli",
    ["", "v1.0.0", "v1.2.21", "v1.10.0\nv1.3.0", "junk\nv2.0.0", "v1.2.21-rc1"],
)
@pytest.mark.parametrize("override", [None, "v3.0.0"])
def test_pre_contract_floor_matches_the_twin(
    tmp_path: pathlib.Path, floor_name: str, cli: str, override: str | None
) -> None:
    """`rsv_pre_contract_floor` and its port agree, including the empty answer.

    The twin ALWAYS prints a trailing newline (`printf '%s\\n'`), even for an empty floor, so the comparison appends one rather than stripping it: a port that returned `None` instead of `""` would otherwise look equal here.
    """
    if FLOORS[floor_name] == "":
        floor_file = "/dev/null"
    else:
        target = tmp_path / floor_name
        target.write_text(FLOORS[floor_name], encoding="utf-8")
        floor_file = str(target)
    env = {"RSV_FLOOR_FILE": floor_file}
    if override is not None:
        env["RSV_GRANDFATHER_BEFORE"] = override
    _rc, out, _err = _bash("rsv_pre_contract_floor", [cli], **env)
    assert out == rsv.pre_contract_floor(rsv.records(cli), env=env) + "\n"


# --------------------------------------------------------------------------- The planted defect: this differential must be able to FAIL ---------------------------------------------------------------------------

# Each mutation is (a name, the text to find, the text to put there). They are chosen to be INVISIBLE to a reader skimming the diff and fatal to the verdict, which is what a real regression looks like.
MUTATIONS = (
    (
        "drift direction flipped",
        'out.append("DRIFT %s: cli sentinel present, git tag missing" % version)',
        'out.append("DRIFT %s: git tag present, cli sentinel missing" % version)',
    ),
    (
        "the floor short-circuit swallows every finding",
        "    floor = pre_contract_floor(cli_versions, root=root, env=env)\n    if not floor:",
        "    floor = pre_contract_floor(cli_versions, root=root, env=env)\n    if True:",
    ),
    (
        "an unreadable pointer becomes a pass",
        "    if not latest_ver or not manifest_ver:",
        "    if latest_ver and not manifest_ver:",
    ),
)


@pytest.mark.parametrize(
    ("name", "find", "replace"), list(MUTATIONS), ids=[m[0] for m in MUTATIONS]
)
def test_a_planted_defect_makes_the_differential_fail(
    tmp_path: pathlib.Path, name: str, find: str, replace: str
) -> None:
    """A MUTATED COPY must disagree with the twin on at least one live case.

    THE REAL FILE IS NEVER TOUCHED. The mutation is applied to a copy of the whole package under `tmp_path`, run in a child interpreter whose sys.path points at that copy, and the real file's sha256 is re-asserted at the end of the test. A control that edits the thing it is controlling has, at best, proved that it can break the build.

    THE ASSERTION IS THAT IT FAILS, and specifically that it fails on a case the UNMUTATED module passes. "The mutant disagrees with the twin" would also be satisfied by a mutant that crashes on every input, which proves nothing about the comparison being sensitive to the RIGHT thing.
    """
    real = paths.from_root(PORT)
    before = hashlib.sha256(real.read_bytes()).hexdigest()

    package = tmp_path / "rediacc_ci"
    shutil.copytree(
        paths.from_root(".ci/rediacc_ci"),
        package,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    (package / "tests").mkdir()
    (package / "tests" / "__init__.py").write_text("", encoding="utf-8")
    target = package / "core" / "release_state_validator.py"
    text = target.read_text(encoding="utf-8")
    assert text.count(find) == 1, "the mutation anchor %r moved" % name
    target.write_text(text.replace(find, replace), encoding="utf-8")

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "from rediacc_ci.core import release_state_validator as m\n"
        "cases = json.load(sys.stdin)\n"
        "out = []\n"
        "for cli, tags, inflight, latest, manifest in cases:\n"
        "    lines, rc = m.assert_bijection(m.records(cli), m.records(tags), inflight,"
        " env={'RSV_FLOOR_FILE': '/dev/null'})\n"
        "    ptr, prc = m.assert_channel_pointer_tagged('edge', latest, manifest,"
        " m.records(tags), inflight)\n"
        "    out.append([lines, rc, ptr, prc])\n"
        "json.dump(out, sys.stdout)\n" % str(tmp_path),
        encoding="utf-8",
    )

    # THE POINTER ARGUMENTS VARY, and that is not decoration. The first draft held them at ('v1.3.1', 'v1.3.1') for every case, so the "an unreadable pointer becomes a pass" mutation flipped a branch NO CASE EVER ENTERED and the control reported that the mutation "changed nothing
    # the differential can see". The mutation was fine; the probe was blind. A
    # control that cannot fire is a claim about the control before it is a claim about the code, so the empty-pointer shapes are here explicitly.
    cases = [
        ["v1.3.0", "v1.10.0", "", "v1.3.1", "v1.3.1"],
        ["v1.3.0\nv1.10.0", "v1.3.0", "", "", "v1.3.1"],
        ["", "v1.3.0", "", "v1.3.1", ""],
        ["v1.3.0", "v1.3.0", "", "v1.3.0", "v1.10.0"],
    ]
    proc = subprocess.run(
        [sys.executable, str(probe)],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stderr
    mutant = json.loads(proc.stdout)

    honest_agrees = 0
    mutant_disagrees = 0
    for (cli, tags, in_flight, latest, manifest), got in zip(cases, mutant, strict=True):
        rc, out, _err = _bash(
            "rsv_assert_bijection", [cli, tags, in_flight], RSV_FLOOR_FILE="/dev/null"
        )
        prc_lines, prc = rsv.assert_bijection(
            rsv.records(cli), rsv.records(tags), in_flight, env={"RSV_FLOOR_FILE": "/dev/null"}
        )
        honest_ptr, honest_prc = rsv.assert_channel_pointer_tagged(
            "edge", latest, manifest, rsv.records(tags), in_flight
        )
        if (out, rc) == (_joined(prc_lines), prc):
            honest_agrees += 1
        if (_joined(got[0]), got[1]) != (out, rc):
            mutant_disagrees += 1
        prc2, out2, _e2 = _bash(
            "rsv_assert_channel_pointer_tagged", ["edge", latest, manifest, tags, in_flight]
        )
        if (_joined(got[2]), got[3]) != (out2, prc2):
            mutant_disagrees += 1

        assert (_joined(honest_ptr), honest_prc) == (out2, prc2), (
            "the UNMUTATED pointer already disagrees with the twin on %r/%r" % (latest, manifest)
        )
    assert honest_agrees == len(cases), "the UNMUTATED module already disagrees; fix that first"
    assert mutant_disagrees > 0, "the mutation %r changed nothing the differential can see" % name
    assert hashlib.sha256(real.read_bytes()).hexdigest() == before, "the real port was modified"
    assert real.read_text(encoding="utf-8").count(find) == 1


# --------------------------------------------------------------------------- The three-state probes ---------------------------------------------------------------------------


def test_probe_is_not_an_int() -> None:
    """In shell 0 is TRUE and in Python 0 is FALSE. See the module docstring.

    `if sentinel_exists(...)` under an `IntEnum` would read correctly and mean the opposite of `if rsv_sentinel_exists ...`, in the direction that proceeds
    with an upload over a sealed release.
    """
    assert not issubclass(rsv.Probe, int)
    assert rsv.Probe.YES != 0
    assert bool(rsv.Probe.NO) is True  # every enum member is truthy; none is a verdict


def test_probe_return_codes_are_the_twins() -> None:
    """0 sealed / 1 absent / 2 could not tell, read out of the twin's comments."""
    assert (rsv.Probe.YES.rc, rsv.Probe.NO.rc, rsv.Probe.UNKNOWN.rc) == (0, 1, 2)
    text = _twin().read_text(encoding="utf-8")
    assert "`0` sealed, `1` genuinely absent, `2` COULD NOT TELL." in text


@pytest.mark.parametrize(
    ("stderr_text", "expected"),
    [
        ("An error occurred (404) when calling the HeadObject operation", rsv.Probe.NO),
        ("Not Found", rsv.Probe.NO),
        ("NoSuchKey", rsv.Probe.NO),
        ("nosuchkey", rsv.Probe.NO),
        ("An error occurred (ExpiredToken)", rsv.Probe.UNKNOWN),
        ("Could not connect to the endpoint URL", rsv.Probe.UNKNOWN),
        ("", rsv.Probe.UNKNOWN),
    ],
)
def test_sentinel_exists_only_calls_404_an_absence(
    monkeypatch: pytest.MonkeyPatch, stderr_text: str, expected: rsv.Probe
) -> None:
    """An unanswered question is not a `no`. The twin's rule at :221-222.

    The classifier is the same case-insensitive `404|Not Found|NoSuchKey` grep the twin runs over the CAPTURED STDERR, and the reason it is a text match and not an exit-code table is that the aws CLI returns 254 for both a 404 and an auth failure.
    """

    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 254, "", stderr_text)

    monkeypatch.setattr(rsv, "_run", fake)
    assert rsv.sentinel_exists("cli", "v1.0.0", "https://example.invalid") is expected


def test_sentinel_exists_success_is_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control for the case above: something must also come back YES."""

    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    monkeypatch.setattr(rsv, "_run", fake)
    assert rsv.sentinel_exists("cli", "v1.0.0", "https://example.invalid") is rsv.Probe.YES


@pytest.mark.parametrize(
    ("rc", "stdout", "expected"),
    [
        (0, "3\n", 3),
        (0, "0\n", 0),
        (0, "None\n", 0),
        (0, "not-a-number\n", None),
        (1, "", None),
        (255, "17\n", None),
    ],
)
def test_binary_count_never_fabricates_a_zero(
    monkeypatch: pytest.MonkeyPatch, rc: int, stdout: str, expected: int | None
) -> None:
    """None, not 0, when the count could not be obtained. The twin's :161-166.

    0 is precisely the value callers act on: it is the "sealed-but-empty" signal that `write-release-sentinel.sh` and `upload-to-r2.sh` use to REFUSE a release, so an unreachable bucket returning 0 would refuse a healthy one.
    """

    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, rc, stdout, "boom\n")

    monkeypatch.setattr(rsv, "_run", fake)
    assert rsv.binary_count("cli/v1.0.0/", "https://example.invalid") == expected


@pytest.mark.parametrize(
    ("rc", "stdout", "expected"),
    [
        (0, "1\n", rsv.Probe.YES),
        (0, "0\n", rsv.Probe.NO),
        (0, "None\n", rsv.Probe.NO),
        (2, "", rsv.Probe.UNKNOWN),
    ],
)
def test_prefix_nonempty_keeps_its_third_state(
    monkeypatch: pytest.MonkeyPatch, rc: int, stdout: str, expected: rsv.Probe
) -> None:
    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, rc, stdout, "boom\n")

    monkeypatch.setattr(rsv, "_run", fake)
    assert rsv.prefix_nonempty("cli/v1.0.0/", "https://example.invalid") is expected


def test_list_sentinels_refuses_without_the_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`: "${AWS_ACCESS_KEY_ID:?...}"` at :100, checked at CALL time."""
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID must be exported"):
        rsv.list_sentinels("cli", "https://example.invalid")


def test_list_sentinels_parses_the_tab_packed_key_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--output text` packs the array onto ONE tab-joined line; `tr` splits it.

    Without the tab split there are no records at all and the function returns an empty list, which is indistinguishable from an empty bucket. That is the vacuity this case exists to keep out.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "x")
    keys = (
        "cli/v1.0.0/.released\t"
        "cli/v1.10.0/.released\t"
        "cli/v1.2.0/.released\t"
        "cli/v1.2.0-rc1/.released\t"
        "cli/v1.3.0/rdc-linux-x64\t"
        "other/v9.9.9/.released"
    )

    def fake(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 0, keys + "\n", "")

    monkeypatch.setattr(rsv, "_run", fake)
    got = rsv.list_sentinels("cli", "https://example.invalid")
    # Semver-sorted, sentinel-only, product-scoped, pre-release excluded.
    assert got == ["v1.0.0", "v1.2.0", "v1.10.0"]


def test_get_sentinel_payload_fails_open_exactly_as_the_twin_does() -> None:
    """`|| true` plus `2>/dev/null`: an unreachable bucket yields "".

    PINNED, NOT FIXED. `write-release-sentinel.sh:140` uses this for a readback VERIFICATION, so a torn network read there reads as "the sentinel I just wrote is not there". Changing it here would make the port disagree with the twin about a release-path decision.
    """
    text = _twin().read_text(encoding="utf-8")
    body = text.split("rsv_get_sentinel_payload() {", 1)[1].split("\n}", 1)[0]
    assert "|| true" in body
    assert "2>/dev/null" in body


# --------------------------------------------------------------------------- The twin's defects, pinned so they cannot rot ---------------------------------------------------------------------------


def test_defect_1_the_twin_still_calls_an_undefined_log_error() -> None:
    """`log_error` at 4 sites, defined nowhere, and the file sources nothing.

    RED WHEN THE TWIN IS FIXED, which is the point of a pin. Whoever adds the `source common.sh` (or defines a fallback) deletes this case in the same change and the finding closes with evidence rather than by being forgotten.
    """
    text = _twin().read_text(encoding="utf-8")
    calls = [m.start() for m in re.finditer(r"^\s*log_error ", text, re.MULTILINE)]
    assert len(calls) == 4, "the log_error call count moved: %d" % len(calls)
    assert not re.search(r"^\s*(source|\.)\s+\S", text, re.MULTILINE), (
        "the twin now sources something; re-check whether log_error is defined"
    )
    assert "log_error()" not in text


def test_defect_1_is_live_when_the_library_is_sourced_alone() -> None:
    """Driven, not asserted from the source text. `command not found`, rc 127.

    The `rm -f "$err"` on the line after never runs either, so the failure also leaks the `mktemp` file the function created.
    """
    script = (
        "set -euo pipefail\n"
        "source %s\n"
        "rsv_binary_count 'cli/v0.0.0/'\n"
        "echo NEVER-REACHED\n" % _q(str(_twin()))
    )
    rc, out, err = diff.bash_streams(
        script,
        # Built as a dict and splatted rather than written as keyword literals, because ruff's S106 flags any literal assigned to an argument whose NAME looks like a secret, and it is right to: the exception belongs here, in a harness pointed at example.invalid, and nowhere a reader might copy from.
        env=diff.env_for(**FAKE_R2_ENV),
    )
    assert "log_error: command not found" in err
    assert "NEVER-REACHED" not in out
    assert rc != 0


def test_defect_2_only_one_probe_still_conflates_empty_with_unreachable() -> None:
    """Three siblings grew a third state; `rsv_list_sentinels` never did.

    Pinned as a COUNT so that fixing the fourth one, or regressing one of the three, both show up here.
    """
    text = _twin().read_text(encoding="utf-8")
    tri_state = [
        name
        for name in ("rsv_prefix_nonempty", "rsv_binary_count", "rsv_sentinel_exists")
        if "return 2" in text.split(name + "() {", 1)[1].split("\n}", 1)[0]
    ]
    assert sorted(tri_state) == [
        "rsv_binary_count",
        "rsv_prefix_nonempty",
        "rsv_sentinel_exists",
    ] or tri_state == ["rsv_prefix_nonempty", "rsv_sentinel_exists"], tri_state
    swallowing = text.split("rsv_list_sentinels() {", 1)[1].split("\n}", 1)[0]
    assert "|| true" in swallowing, "rsv_list_sentinels no longer swallows; close the finding"


def test_defect_2_the_ratchet_is_what_keeps_that_from_being_green() -> None:
    """With the probe dead and the ratchet present, the gate must still go RED.

    This is the load-bearing half of the finding. If it ever passes with rc 0, the BLOCKER gate has become a gate that can be satisfied by an outage.
    """
    ratchet = paths.from_root(".ci/config/release-contract-floor.txt")
    assert ratchet.is_file(), "the ratchet file is gone; DEFECT 2 is now LIVE"
    lines, rc = rsv.assert_bijection([], ["v9.9.9"], "", env={})
    assert rc == 1, lines
    assert any("git tag present, cli sentinel missing" in line for line in lines)
    # And the control: with the ratchet pinned away it DOES go green on nothing.
    empty_lines, empty_rc = rsv.assert_bijection(
        [], ["v9.9.9"], "", env={"RSV_FLOOR_FILE": "/dev/null"}
    )
    assert empty_rc == 0
    assert empty_lines == [
        "OK: release-state bijection holds -- no cli sentinels yet (contract not in effect)"
    ]


def test_defect_3_the_inner_function_leaks_into_the_global_shell() -> None:
    """`rsv_drop_pre_contract` survives the call that defined it. Driven live."""
    script = (
        "set -uo pipefail\n"
        "source %s\n"
        "declare -F rsv_drop_pre_contract >/dev/null && echo BEFORE-DEFINED || echo BEFORE-ABSENT\n"
        "rsv_assert_bijection 'v1.3.0' 'v1.3.0' '' >/dev/null\n"
        "declare -F rsv_drop_pre_contract >/dev/null && echo AFTER-DEFINED || echo AFTER-ABSENT\n"
        % _q(str(_twin()))
    )
    _rc, out, _err = diff.bash_streams(script, env=diff.env_for(RSV_FLOOR_FILE="/dev/null"))
    assert "BEFORE-ABSENT" in out
    assert "AFTER-DEFINED" in out


def test_the_bash_4_precondition_is_still_in_the_twin() -> None:
    """The port has no counterpart, so the twin's guard must not vanish quietly.

    A Python dict is a dict on every interpreter this repo supports. The guard exists because `declare -A` fails SILENTLY on bash 3.2 and turns a healthy release state into a red that names nothing.
    """
    text = _twin().read_text(encoding="utf-8")
    assert 'if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then' in text
    assert "needs bash 4.0 or newer" in text


# --------------------------------------------------------------------------- The duplicate, named so the collapse is a decision and not a discovery ---------------------------------------------------------------------------


def test_the_known_duplicate_still_exists_and_still_lacks_the_probes() -> None:
    """`quality/release_state.py` holds the assertion half and NOT the probes.

    If it grows one of the four probe functions, the two files have started drifting toward each other rather than collapsing, and this case says so before there are two implementations of a release-path decision.
    """
    other = paths.from_root(".ci/rediacc_ci/quality/release_state.py")
    text = other.read_text(encoding="utf-8")
    for shared in (
        "def assert_bijection",
        "def assert_channel_pointer_tagged",
        "def pre_contract_floor",
    ):
        assert shared in text, "the duplicate moved; re-derive the collapse notes"
    for only_here in (
        "def prefix_nonempty",
        "def binary_count",
        "def sentinel_exists",
        "def get_sentinel_payload",
    ):
        assert only_here not in text, (
            "%s has appeared in the gate too; collapse it onto "
            "rediacc_ci.core.release_state_validator instead of copying it" % only_here
        )


# --------------------------------------------------------------------------- The CLI ---------------------------------------------------------------------------


def _cli(args: list[str], stdin: str = "") -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.release_state_validator", *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.from_root(".ci")),
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "RSV_FLOOR_FILE": "/dev/null"},
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cli_bijection_agrees_with_the_function() -> None:
    rc, out, _err = _cli(["bijection", "--cli", "v1.3.0", "--tags", "v1.3.0\nv1.10.0"])
    lines, prc = rsv.assert_bijection(
        ["v1.3.0"], ["v1.3.0", "v1.10.0"], "", env={"RSV_FLOOR_FILE": "/dev/null"}
    )
    assert (rc, out) == (prc, _joined(lines))
    assert rc == 1


def test_cli_bijection_reads_stdin() -> None:
    rc, out, _err = _cli(["bijection", "--cli", "-", "--tags", "v1.3.0"], stdin="v1.3.0\n")
    assert rc == 0
    assert out.startswith("OK: release-state bijection holds (floor: v1.3.0")


def test_cli_pointer_keeps_the_positionals_apart_from_the_flags() -> None:
    """A `--tags` value must never be mistaken for the channel or a version."""
    rc, out, _err = _cli(
        ["pointer", "edge", "v1.3.1", "v1.3.1", "--tags", "v1.3.1", "--in-flight", "v2.0.0"]
    )
    assert rc == 0
    assert out == "OK: edge pointer names v1.3.1, which is tagged\n"


def test_cli_rejects_an_unknown_verb() -> None:
    rc, out, err = _cli(["nonsense"])
    assert rc == 2
    assert out == ""
    assert "unknown verb" in err


def test_cli_help_writes_nothing_to_stdout() -> None:
    """Every verb is read with `v="$(...)"`; a usage banner on stdout is a value."""
    rc, out, err = _cli(["--help"])
    assert rc == 2
    assert out == ""
    assert "bijection" in err
