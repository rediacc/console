"""Differential: `.ci/rediacc_ci/version/inject_env.py` against its twin `.ci/scripts/version/inject-env.sh`.

FOUR OBSERVABLES, NOT ONE, because this script's happy path exits 0 in every
case it has and comparing exit codes alone would compare almost nothing:

  1. the exit code;
  2. stdout -- the single version line `--print` produces, which two workflows
     capture as a release preflight;
  3. stderr -- the four refusal messages;
  4. THE EXPORTED SET the caller is left holding, which is the whole point of a
     script whose two production callers `source` it.

HOW THE EXPORTED SET IS COMPARED. The twin is sourced by a throwaway bash shell that then dumps `env -0`; the port's `inject()` is called and its mapping is dumped the same way. Only the four names the twin exports are compared, plus the FACT that nothing else changed -- a port that exported a fifth name would pass a four-name comparison. `_exports_twin` starts from a fixed
environment so the diff is against a known baseline rather than against whatever the test runner happened to inherit.

WHY THE RESOLVER IS A FIXTURE AND NOT THE REAL ONE. The twin resolves `resolve-version.sh` relative to its OWN directory, so a copy of the twin in a fixture finds the fixture's copy. That is the seam: `resolve-version.sh` here is a recording stub whose exit code and stdout are baked into its text, which makes the four fallback branches (fails / prints nothing / missing / not
executable) reachable without inventing git history. The port derives the same path from its own `__file__`, so the fixture copy of the port finds the same stub -- asserted by `test_the_resolver_stub_is_actually_reached`, without which every case below could be "two programs that both fell back to 0.0.0-dev".

TWO REAL DEFECTS IN THE TWIN ARE PINNED HERE, not fixed: `test_a_flag_swallowed_as_a_version_is_a_twin_defect` and `test_sourcing_the_twin_leaks_set_euo_pipefail_into_the_caller`. Both are reported to the campaign; the repair is a cutover-box decision.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "version" / "inject-env.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "version" / "inject_env.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/version/inject-env.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/version/inject_env.py")

# The four names, in the twin's own export order.
NAMES = ("APP_VERSION", "VITE_APP_VERSION", "CLI_VERSION", "TAG")

# The recording `resolve-version.sh` stub. Configured by its own TEXT rather than through the environment: the subject reads `$VERSION` itself, and a stub reading three more env vars would make an env-shaped divergence unattributable.
FAKE_RESOLVER = """#!/usr/bin/env python3
import pathlib, sys
LOG = %(log)r
RC = %(rc)d
OUT = %(out)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("resolve-version.sh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
sys.stdout.write(OUT)
sys.exit(RC)
"""

# A fixed baseline environment for every run, so the exported-set diff is against something stated rather than against the test runner's inheritance.
BASE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/nonexistent",
    "LC_ALL": "C",
    "PYTHONDONTWRITEBYTECODE": "1",
}

# Dumps the port's `inject()` result in the same shape `_exports_twin` reads out of a real shell. Loaded BY PATH so `__file__` is the fixture copy and the resolver stub beside it is the one that answers.
PORT_EXPORT_HARNESS = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("inject_env_under_test", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
code, exports, out, err = mod.inject(sys.argv[2:])
json.dump({"code": code, "exports": exports, "out": out, "err": err}, sys.stdout)
"""


def _fixture(
    where: pathlib.Path,
    *,
    resolver: bool = True,
    resolver_rc: int = 0,
    resolver_out: str = "1.2.3\n",
    resolver_exec: bool = True,
) -> pathlib.Path:
    """A tree holding COPIES of both subjects plus one resolver stub.

    Copies, because each subject finds the resolver relative to its own location (`BASH_SOURCE`/`__file__`). Driving the tracked files would consult the real `resolve-version.sh` and the real git tags, and the fallback branches would be unreachable.

    `.resolve()` on the root: bash's `cd X && pwd` reports the LOGICAL path while `pathlib.resolve()` follows symlinks. Nothing here prints the root, but the two subjects must agree on WHICH resolver they found, and an unresolved root on a host whose tmpdir is a symlink makes that a coin toss.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "version").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "version").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(PORT, root / PORT_REL)
    if resolver:
        stub = root / ".ci" / "scripts" / "version" / "resolve-version.sh"
        stub.write_text(
            FAKE_RESOLVER
            % {"log": str(root.parent / "resolverlog.txt"), "rc": resolver_rc, "out": resolver_out},
            encoding="utf-8",
        )
        stub.chmod(0o755 if resolver_exec else 0o644)
    return root


def _drain_log(root: pathlib.Path) -> list[str]:
    log = root.parent / "resolverlog.txt"
    if not log.exists():
        return []
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    log.unlink()
    return calls


def _cli_twin(root, argv, env_extra):
    proc = subprocess.run(
        ["bash", str(root / TWIN_REL), *argv],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **env_extra},
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _cli_port(root, argv, env_extra):
    proc = subprocess.run(
        ["python3", str(root / PORT_REL), *argv],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **env_extra, "PATH": "/usr/bin:/bin"},
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _exports_twin(root, argv, env_extra):
    """Source the twin in a throwaway shell and read the environment back.

    THREE THINGS HERE ARE LOAD-BEARING, and the first two were each a wrong first draft:

      * THE DUMP GOES TO A FILE, not to stdout. `--print` writes the version to
        stdout first, so a marker printed afterwards on the same stream is glued
        to it and every case that uses `--print` reads back a null exit code.
      * THE SOURCE IS WRAPPED IN `if`. Sourcing turns errexit ON in this shell
        (see `test_sourcing_the_twin_leaks_set_euo_pipefail_into_the_caller`), so
        a refusal path would kill the capture shell before it could dump
        anything. `if` suppresses errexit for its condition, which is also how
        build-cli-executables.sh:130 calls it.
      * `env -0` and not `env`: a version string cannot contain a newline today,
        but a resolver that printed two lines produces one that does, and a
        newline-delimited dump would split it into two bogus names.
    """
    quoted = " ".join("'%s'" % a.replace("'", "'\\''") for a in argv)
    dump = root.parent / "envdump"
    script = (
        "if . '%s' %s; then st=0; else st=$?; fi; { printf '__EXIT__=%%s\\0' \"$st\"; env -0; } > '%s'"
        % (
            root / TWIN_REL,
            quoted,
            dump,
        )
    )
    subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **env_extra},
        check=False,
        timeout=60,
    )
    fields = [f for f in dump.read_text(encoding="utf-8").split("\0") if f]
    exported = {}
    code = None
    for field in fields:
        name, _, value = field.partition("=")
        if name == "__EXIT__":
            code = int(value)
        elif name in NAMES:
            exported[name] = value
    # The names the sourced script did NOT touch, so a port that exported a fifth one is caught rather than ignored.
    extra = sorted(
        f.partition("=")[0]
        for f in fields
        if f.partition("=")[0]
        not in {*BASE_ENV, *NAMES, *env_extra, "__EXIT__", "PWD", "OLDPWD", "SHLVL", "_"}
    )
    return code, exported, extra


def _exports_port(root, argv, env_extra):
    proc = subprocess.run(
        ["python3", "-c", PORT_EXPORT_HARNESS, str(root / PORT_REL), *argv],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **env_extra, "PATH": "/usr/bin:/bin"},
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, "the export harness itself failed: %s" % proc.stderr
    payload = json.loads(proc.stdout)
    return payload["code"], payload["exports"], []


CASES = [
    pytest.param({}, (), {}, id="no-args"),
    pytest.param({}, ("--print",), {}, id="print"),
    pytest.param({}, ("--version", "9.9.9", "--print"), {}, id="version-override"),
    pytest.param({}, ("--version", "9.9.9"), {}, id="version-override-no-print"),
    pytest.param({}, ("--print",), {"VERSION": "7.7.7"}, id="version-env"),
    pytest.param(
        {},
        ("--version", "9.9.9", "--print"),
        {"VERSION": "7.7.7"},
        id="flag-beats-env",
    ),
    pytest.param({}, ("--strict", "--print"), {}, id="strict-happy"),
    pytest.param({}, ("--strict", "--strict", "--print"), {}, id="strict-twice"),
    pytest.param({}, ("--print", "--print"), {}, id="print-twice"),
    pytest.param({}, ("--version", "0.0.0-dev", "--strict"), {}, id="strict-rejects-dev"),
    pytest.param({}, ("--version", "latest", "--strict"), {}, id="strict-rejects-word"),
    pytest.param(
        {}, ("--version", "v1.2.3-rc.1", "--strict", "--print"), {}, id="strict-prerelease"
    ),
    pytest.param({}, ("--version", "1", "--strict", "--print"), {}, id="strict-single-component"),
    pytest.param({}, ("--version", "1.2.3+build.7", "--strict", "--print"), {}, id="strict-plus"),
    pytest.param({}, ("--version", "1.2.3 ", "--strict"), {}, id="strict-rejects-trailing-space"),
    pytest.param({}, ("--version", ""), {}, id="empty-version-is-an-error"),
    pytest.param({}, ("--version",), {}, id="version-without-value"),
    pytest.param({}, ("--bogus",), {}, id="unknown-arg"),
    pytest.param({}, ("--print", "--bogus"), {}, id="unknown-arg-after-a-good-one"),
    pytest.param({}, ("--version", "--strict", "--print"), {}, id="flag-swallowed-as-version"),
    pytest.param({"resolver_rc": 1}, ("--print",), {}, id="resolver-fails"),
    pytest.param({"resolver_out": ""}, ("--print",), {}, id="resolver-prints-nothing"),
    pytest.param(
        {"resolver_out": ""}, ("--strict", "--print"), {}, id="resolver-empty-under-strict"
    ),
    pytest.param({"resolver_rc": 1}, ("--strict",), {}, id="resolver-fails-under-strict"),
    pytest.param({"resolver": False}, ("--print",), {}, id="resolver-missing"),
    pytest.param({"resolver_exec": False}, ("--print",), {}, id="resolver-not-executable"),
    pytest.param({"resolver_out": "2.0.0\n\n\n"}, ("--print",), {}, id="resolver-trailing-blanks"),
    pytest.param({"resolver_out": "2.0.0\n3.0.0\n"}, ("--print",), {}, id="resolver-two-lines"),
    pytest.param(
        {"resolver_out": "2.0.0\n3.0.0\n"},
        ("--strict", "--print"),
        {},
        id="resolver-two-lines-under-strict",
    ),
    pytest.param({"resolver_out": "  1.4.0\n"}, ("--print",), {}, id="resolver-leading-space"),
]


@pytest.mark.parametrize(("fixture_kw", "argv", "env_extra"), CASES)
def test_cli_port_and_twin_agree(tmp_path, fixture_kw, argv, env_extra):
    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old = _cli_twin(root_a, argv, env_extra)
    old_calls = _drain_log(root_a)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new = _cli_port(root_b, argv, env_extra)
    new_calls = _drain_log(root_b)

    assert new == old, "CLI diverged for %r:\n twin: %r\n port: %r" % (argv, old, new)
    assert new_calls == old_calls, "resolver calls diverged: %r vs %r" % (old_calls, new_calls)


@pytest.mark.parametrize(("fixture_kw", "argv", "env_extra"), CASES)
def test_exported_set_port_and_twin_agree(tmp_path, fixture_kw, argv, env_extra):
    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old_code, old_exports, old_extra = _exports_twin(root_a, argv, env_extra)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new_code, new_exports, _ = _exports_port(root_b, argv, env_extra)

    assert new_code == old_code, "sourced exit diverged for %r: %r vs %r" % (
        argv,
        old_code,
        new_code,
    )
    assert new_exports == old_exports, "exported set diverged for %r:\n twin: %r\n port: %r" % (
        argv,
        old_exports,
        new_exports,
    )
    assert old_extra == [], (
        "the twin exported a name outside the four this port reproduces: %r" % old_extra
    )
    # ANTI-VACUITY, per case rather than once. Roughly a third of the table is a refusal, where BOTH sides correctly export nothing; without this the other two thirds could quietly join them and every row would read "two empty dicts agree".
    if old_code == 0:
        assert sorted(old_exports) == sorted(NAMES), (
            "a successful run exported %r, not the four names" % sorted(old_exports)
        )
        assert len(set(old_exports.values())) == 1, (
            "the four names must carry ONE synchronized value: %r" % old_exports
        )
    else:
        assert old_exports == {}, (
            "a refusal must leave the caller's previous values alone: %r" % old_exports
        )


def test_the_resolver_stub_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every fallback case above is worthless if neither subject ever ran the resolver -- they would both have taken the same shortcut."""
    for subject, runner in ((TWIN_REL, _cli_twin), (PORT_REL, _cli_port)):
        root = _fixture(tmp_path / ("v-%s" % subject.name))
        code, out, err = runner(root, ("--print",), {})
        calls = _drain_log(root)
        assert calls == ["resolve-version.sh\t--current"], (
            "%s did not run the stub exactly once with --current: %r" % (subject.name, calls)
        )
        assert (code, out, err) == (0, "1.2.3\n", ""), "%s: %r" % (subject.name, (code, out, err))


def test_an_override_short_circuits_the_resolver(tmp_path):
    """CONTROL for the case above, in the other direction: with `--version` or `$VERSION` set, the resolver must NOT be consulted. A port that always resolved would pass every comparison in this file while spawning a git process on the release path for a version it was handed."""
    for argv, env_extra in ((("--version", "9.9.9"), {}), (("--print",), {"VERSION": "7.7.7"})):
        for subject, runner in ((TWIN_REL, _cli_twin), (PORT_REL, _cli_port)):
            root = _fixture(tmp_path / ("c-%s-%s" % (subject.name, len(env_extra))))
            runner(root, argv, env_extra)
            assert _drain_log(root) == [], "%s consulted the resolver despite %r/%r" % (
                subject.name,
                argv,
                env_extra,
            )


def test_a_flag_swallowed_as_a_version_is_a_twin_defect(tmp_path):
    """A REAL DEFECT IN THE TWIN, pinned in BOTH implementations.

    `--version` consumes the next word unconditionally, so `--version --strict --print` sets the version to the literal "--strict", never enables strict mode, prints `--strict` and exits 0. The one guard this file exists to provide is switched off in silence -- and the way a caller reaches it is an unquoted `$NEXT_VERSION` that expanded to nothing, which DROPS the argument rather
    than passing "" and so sails past the twin's own `--version was given an empty value` check.

    Reproduced rather than repaired: a port that rejected it would fail differently from the script it claims to be equivalent to. Reported.
    """
    for subject, runner in ((TWIN_REL, _cli_twin), (PORT_REL, _cli_port)):
        root = _fixture(tmp_path / ("s-%s" % subject.name))
        code, out, err = runner(root, ("--version", "--strict", "--print"), {})
        assert (code, out, err) == (0, "--strict\n", ""), (
            "%s: the defect is gone and this test is stale: %r" % (subject.name, (code, out, err))
        )


def test_sourcing_the_twin_leaks_set_euo_pipefail_into_the_caller(tmp_path):
    """A SECOND REAL DEFECT IN THE TWIN, and one the port cannot have.

    inject-env.sh's own header says "All logic is wrapped in a function so `set -euo pipefail` stays scoped to this script and does not leak into the caller shell". That is false in bash: `set` options are SHELL-GLOBAL, not
    function-scoped, so sourcing the file turns errexit, nounset and pipefail on
    in whatever shell sourced it and leaves them on.

    Latent rather than active today -- both production sourcing callers (build-cli-executables.sh:18, build-cli-musl.sh:14) already set the same three at the top -- so this is recorded, not repaired. The port hands back a mapping and has no shell options to leak, which is why the observable does not appear in the comparison above.
    """
    root = _fixture(tmp_path / "leak")
    script = "set +euo pipefail; . '%s' --print >/dev/null; set -o" % (root / TWIN_REL)
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=dict(BASE_ENV),
        check=False,
        timeout=60,
    )
    on = {
        line.split()[0]
        for line in proc.stdout.splitlines()
        if line.split()[1:2] == ["on"]  # `set -o` prints "<name>\ton|off"
    }
    assert {"errexit", "nounset", "pipefail"} <= on, (
        "the leak is gone and this test is stale; options on: %r" % sorted(on)
    )
