"""Differential: `rediacc_ci.infra.ci_env` against the frozen answers of its retired twin `.ci/scripts/infra/ci-env.sh`.

THE TWIN IS DELETED (PLAN-tooling-transformation W7P5-c). Every `old` answer below comes out of `goldens/twins/infra.ci-env.jsonl` through `differential.twin_tuple`, recorded from the real bash with `--source bash` while the file still existed. The golden header's `twin_blob` (`TWIN_BLOB` here) is the git blob of the bash that produced them, so `git cat-file -p <blob>` still yields
the program. Retiring a sourced-only twin by freezing its outputs is the 2026-09-21 operator ruling for a licensed script whose differential executes the twin.

THE TWIN WAS SOURCED, NEVER EXECUTED, so "run both and compare stdout" was never the comparison. Sourcing it left FOUR observables behind and this file compares all four on every case:

  1. the exported environment (`env` after sourcing, versus the port's `env`
     verb), with the four shell-private names dropped from BOTH SIDES by the
     same helper -- never inside the port, because a filter the twin has no
     equivalent of is exactly how a port drops a name and still looks equal;
  2. `$CI_DOCKER_DIR/.env`, byte for byte;
  3. the bytes appended to `$GITHUB_ENV`;
  4. stdout: the `::add-mask::` directives and the three summary lines.

ONE TREE, TWO SEQUENTIAL RUNS, and that is deliberate. `CONSOLE_ROOT` is derived from the subject's own location on both sides, so one tree keeps `CI_DOCKER_DIR` and `CI_COMPOSE_FILE` identical; the scratch root is folded to a token in the golden and unfolded to this run's root on read, so the frozen answer compares against a live port exactly as the live bash did.

`node` AND `openssl` ARE RECORDING FAKES ON A PREPENDED PATH, for two reasons and only the first is speed. The second is that both real programs are RANDOM: a differential against the real ones can only ever compare shapes, and shapes are what a port gets right while producing a key that does not verify. With canned generators the comparison is byte-exact, and the ARGV the two
sides hand to `node` -- a 300-character program whose curve name is the only thing that varies -- is compared too.

THREE TWIN BEHAVIOURS PINNED BY NAME, all measured against the live bash on 2026-09-13 before the port was written:

  * `test_a_failing_openssl_yields_empty_secrets` -- A REAL DEFECT, reported
    and not repaired. Exit 0 with `ACCOUNT_SERVER_API_KEY=` and
    `ACCOUNT_JWT_SECRET=` empty and `STRIPE_WEBHOOK_SECRET=whsec_test_`, all
    three written into the `.env` file and appended to `$GITHUB_ENV`.
  * `test_a_private_key_without_its_public_leaves_the_public_unexported` --
    `export A B` marks B for export without assigning it, so the caller gets no
    public key while the `.env` file gets an empty one.
  * `test_a_missing_node_ends_the_sourcing_shell_at_127` -- the asymmetry with
    the openssl case: a PLAIN assignment propagates, an `export VAR=$(...)`
    does not.

K=5 LEDGER: `.ci/shadow/w7p6-ci-env.observations.jsonl`, recorded in a disposable scratch git repository outside this checkout. The two callers' cutover from sourcing the bash to calling this module is licensed separately by `w7p5c-ci-start-elite-cutover` and `w7p5c-ci-start-account-cutover`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import ci_env
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests.wkloader import copy_loader
from rediacc_ci.well_known import ADMIN_EMAIL_DEFAULT, IMAGE_REGISTRY

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/infra/ci-env.sh"
# `git hash-object .ci/scripts/infra/ci-env.sh` at the freeze. The golden header must carry the same value.
TWIN_BLOB = "e476e4af4dc58ced2e27f7978576756d0fce7768"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_env.py"
BASH = shutil.which("bash") or "/bin/bash"

# The twin's `<<ENVBLOCK` heredoc at TWIN_BLOB, extracted from its text at the freeze and written out here because the text is gone. `(name, default)` with the default only for the two `${NAME:-<default>}` lines. The order is the file's content.
FROZEN_PERSISTED = (
    ("DOCKER_REGISTRY", None),
    ("TAG", None),
    ("WEB_TAG", None),
    ("SYSTEM_DOMAIN", None),
    ("ENABLE_HTTPS", "false"),
    ("SYSTEM_ADMIN_EMAIL", None),
    ("SYSTEM_ADMIN_PASSWORD", None),
    ("SYSTEM_ORGANIZATION_NAME", None),
    ("SYSTEM_ORGANIZATION_VAULT_DEFAULTS", ""),
    ("SYSTEM_DEFAULT_BRIDGE_NAME", None),
    ("SYSTEM_DEFAULT_REGION_NAME", None),
    ("SYSTEM_DEFAULT_TEAM_NAME", None),
    ("CI_MODE", None),
    ("ACCOUNT_SERVER_URL", None),
    ("ACCOUNT_SERVER_API_KEY", None),
    ("ACCOUNT_ED25519_PRIVATE_KEY", None),
    ("ACCOUNT_ED25519_PUBLIC_KEY", None),
    ("ACCOUNT_X25519_PRIVATE_KEY", None),
    ("ACCOUNT_X25519_PUBLIC_KEY", None),
    ("STRIPE_WEBHOOK_SECRET", None),
    ("ACCOUNT_JWT_SECRET", None),
)

# Canned, so the comparison is byte-exact rather than shape-exact.
FAKE_NODE = """#!/usr/bin/python3
import json
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("node\\t" + "\\t".join(sys.argv[1:]).replace("\\n", "\\\\n") + "\\n")
rc = int(os.environ.get("FAKE_NODE_RC", "0"))
if rc:
    sys.stderr.write("node: fixture refuses\\n")
    sys.exit(rc)
curve = "x25519" if "x25519" in " ".join(sys.argv[1:]) else "ed25519"
print(json.dumps({"private": "PRIV-" + curve, "public": "PUB-" + curve}))
"""

FAKE_OPENSSL = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("openssl\\t" + "\\t".join(sys.argv[1:]) + "\\n")
rc = int(os.environ.get("FAKE_OPENSSL_RC", "0"))
if rc:
    sys.stderr.write("openssl: fixture refuses\\n")
    sys.exit(rc)
if "-hex" in sys.argv:
    print(os.environ.get("FAKE_OPENSSL_HEX", "0" * 64))
else:
    print(os.environ.get("FAKE_OPENSSL_B64", "aa/bb+cc=dd" + "x" * 60))
"""

# A supplied-everything base: no generator runs, so the case is deterministic even with the real node and openssl on PATH.
SUPPLIED = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "given-ed-priv",
    "ACCOUNT_ED25519_PUBLIC_KEY": "given-ed-pub",
    "ACCOUNT_X25519_PRIVATE_KEY": "given-x-priv",
    "ACCOUNT_X25519_PUBLIC_KEY": "given-x-pub",
    "ACCOUNT_SERVER_API_KEY": "given-api-key",
    "ACCOUNT_JWT_SECRET": "given-jwt",
    "STRIPE_WEBHOOK_SECRET": "given-whsec",
}

NAME_VALUE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Fixture values, held in constants so the assertions below do not put a string literal beside a `*_PASSWORD` / `*_SECRET` key: ruff's S105 reads that shape as a hardcoded credential, and none of these is one.
FIXTURE_REGISTRY_CRED = "ghs_fixture"
FIXTURE_ADMIN_WORD = "hunter2"
STUB_WEBHOOK_VALUE = "whsec_test_"


class Side:
    """One run's four observables, plus the generator calls it made."""

    __slots__ = ("calls", "chatter", "env", "env_file", "exit", "github_env", "stderr")

    def __init__(self, code, chatter, environ, env_file, github_env, stderr, calls) -> None:
        self.exit = code
        self.chatter = chatter
        self.env = environ
        self.env_file = env_file
        self.github_env = github_env
        self.stderr = stderr
        self.calls = calls

    def as_tuple(self):
        return (self.exit, self.chatter, self.env, self.env_file, self.github_env)


def _tree(base: pathlib.Path) -> pathlib.Path:
    """A checkout-shaped tree holding the port at its real depth, and the twin only while it is being frozen.

    The depth is what matters: the port computes `CONSOLE_ROOT` as `parents[3]` of its own file, and the twin computed `<dir>/../../..`; both must land on `base`.
    """
    (base / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    (base / ".ci" / "docker" / "ci").mkdir(parents=True)
    if diff.regolden_mode(TWIN_REL) == "bash":
        (base / ".ci" / "scripts" / "infra").mkdir(parents=True)
        shutil.copy2(ROOT / TWIN_REL, base / TWIN_REL)
        (base / ".ci" / "config").mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            ROOT / ".ci" / "config" / "well-known.env", base / ".ci" / "config" / "well-known.env"
        )
        copy_loader(base)
    shutil.copy2(PORT, base / ".ci" / "rediacc_ci" / "infra" / "ci_env.py")
    return base


def _stub_bin(base: pathlib.Path) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    for name, body in (("node", FAKE_NODE), ("openssl", FAKE_OPENSSL)):
        fake = stub / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _curated_bin(base: pathlib.Path) -> str:
    """A PATH with the fakes, NO node, and only what the subject needs before it reaches node.

    The real PATH has a real node on it, and the point of the case that uses this is that there is none. `dirname` and `uname` are what the twin needed for its own SCRIPT_DIR and at source time; `python3` is the registry loader and the port's interpreter.
    """
    _stub_bin(base)
    (base / "bin" / "node").unlink()
    for name in ("dirname", "uname", "python3"):
        real = shutil.which(name)
        assert real is not None, name
        link = base / "bin" / name
        # Both sides run over one tree, so the second call finds the first call's links.
        if not link.is_symlink():
            link.symlink_to(real)
    return str(base / "bin")


def _split(stdout: bytes, environ_out: bool):
    """Separate the env dump from the chatter, and drop the shell-private names.

    A dump line is `NAME=value` with a shell-legal NAME; every mask directive
    starts with `:` and every summary line has no `=` before its first space,
    so the split is unambiguous. The filtering happens HERE, on both sides identically -- never in the port. See the module docstring.
    """
    chatter: list[str] = []
    found: dict[str, str] = {}
    for line in stdout.decode("utf-8", "surrogateescape").split("\n"):
        if line == "":
            continue
        if environ_out and NAME_VALUE.match(line):
            name, _, value = line.partition("=")
            # `WK_*` is the well-known registry the twin exported through scripts/lib/well-known.sh; it is not part of what ci-env hands its caller, and no caller reads it.
            if name not in ci_env.SHELL_PRIVATE and not name.startswith("WK_"):
                found[name] = value
            continue
        chatter.append(line)
    return chatter, found


def _run_live(
    base: pathlib.Path,
    which: str,
    env_extra: dict[str, str],
    *,
    dump: bool,
    curated_path: bool = False,
    github_env: bool = True,
) -> Side:
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    env_file = base / ".ci" / "docker" / "ci" / ".env"
    if env_file.exists():
        env_file.unlink()
    # ONE path for both sides, truncated before each run: the value lands in the environment dump, so two different paths would read as a divergence in the thing under test.
    github_env_path = base / "github-env"
    if github_env:
        github_env_path.write_text("", encoding="utf-8")

    env = {
        "PATH": _curated_bin(base) if curated_path else _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(log),
    }
    if github_env:
        env["GITHUB_ENV"] = str(github_env_path)
    env.update(env_extra)

    if which == "old":
        script = '. "$1"' + ("; env" if dump else "")
        argv = [BASH, "-c", script, "bash", str(base / TWIN_REL)]
    else:
        argv = [
            sys.executable,
            str(base / ".ci/rediacc_ci/infra/ci_env.py"),
            "env" if dump else "apply",
        ]
    proc = subprocess.run(
        argv, capture_output=True, env=env, check=False, cwd=str(base), timeout=120
    )
    chatter, environ = _split(proc.stdout, dump)
    return Side(
        proc.returncode,
        chatter,
        environ,
        env_file.read_bytes() if env_file.exists() else None,
        github_env_path.read_bytes() if github_env else None,
        proc.stderr,
        log.read_text(encoding="utf-8").splitlines(),
    )


def _run(
    base: pathlib.Path,
    which: str,
    env_extra: dict[str, str],
    *,
    dump: bool,
    curated_path: bool = False,
    github_env: bool = True,
) -> Side:
    """The port runs live; the twin answers from the golden (or, during the freeze, from the live bash).

    Every input that distinguishes one call from another is a key part, so two calls in one test with different inputs are different records rather than the n-th repeat of one.
    """
    kw = {"dump": dump, "curated_path": curated_path, "github_env": github_env}
    if which != "old":
        return _run_live(base, which, env_extra, **kw)

    def live():
        side = _run_live(base, "old", env_extra, **kw)
        return (
            side.exit,
            "",
            "",
            side.chatter,
            side.env,
            side.env_file,
            side.github_env,
            side.stderr.decode("utf-8", "surrogateescape"),
            side.calls,
        )

    parts = [
        "old",
        "dump=%d" % dump,
        "curated_path=%d" % curated_path,
        "github_env=%d" % github_env,
        *("%s=%s" % kv for kv in sorted(env_extra.items())),
    ]
    rc, _out, _err, chatter, environ, env_bytes, gh_bytes, stderr, calls = diff.twin_tuple(
        TWIN_REL, parts, live, work=(str(base),)
    )
    return Side(
        rc,
        chatter,
        environ,
        env_bytes,
        gh_bytes,
        stderr.encode("utf-8", "surrogateescape"),
        calls,
    )


def _sides(name: str, env_extra: dict[str, str] | None = None, *, dump: bool = True):
    """Both implementations over ONE tree, in sequence. Returns (old, new, calls)."""
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        old = _run(base, "old", dict(env_extra or {}), dump=dump)
        new = _run(base, "new", dict(env_extra or {}), dump=dump)
    labels = ("exit", "chatter", "environment", ".env file", "GITHUB_ENV")
    for i, label in enumerate(labels):
        assert new.as_tuple()[i] == old.as_tuple()[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old.as_tuple()[i],
            new.as_tuple()[i],
        )
    assert new.calls == old.calls, "%s: generator calls diverged:\n twin: %r\n port: %r" % (
        name,
        old.calls,
        new.calls,
    )
    return old, new, old.calls


# --------------------------------------------------------------------------- Controls: a comparison against a file that is not there proves nothing. ---------------------------------------------------------------------------


def test_the_port_exists_where_this_file_says_it_does() -> None:
    assert PORT.is_file(), PORT


@pytest.fixture
def compare_only():
    """The freeze runs against the live bash, before a golden exists and while the twin is still on disk."""
    if diff.regolden_mode(TWIN_REL) == "bash":
        pytest.skip("freezing from the original bash")


@pytest.mark.usefixtures("compare_only")
def test_the_golden_names_the_frozen_twin() -> None:
    """The provenance the 2026-09-21 ruling asks for: the golden says WHICH bash it was recorded from, and that it was recorded from bash at all."""
    header, _silent, records = diff.load_golden(TWIN_REL)
    assert header["twin"] == TWIN_REL, header
    assert header["twin_blob"] == TWIN_BLOB, header
    assert header["source"] == "bash", header
    assert len(records) >= 15, (
        "the golden holds %d records; the freeze did not cover the file" % len(records)
    )


def test_the_fakes_are_what_resolves() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("node", path=path) == str(base / "bin" / "node")
        assert shutil.which("openssl", path=path) == str(base / "bin" / "openssl")


SOURCE_OR_RUN_RE = re.compile(r"""(^|[\s;&|(])(source|\.|bash|sh)\s+["']?[^\s"']*ci-env\.sh""")


@pytest.mark.usefixtures("compare_only")
def test_nothing_in_the_tree_sources_or_runs_the_twin_any_more() -> None:
    """THE DELETION'S OWN GUARD. A caller that still sources or runs `ci-env.sh` would now fail at run time, and in a `-f` guarded caller it would be silently skipped. The two Python callers (`ci_start_elite`, `ci_start_account`) call `ci_env.apply()`; a reappearance of the sourcing shape anywhere tracked is a regression."""
    assert not (ROOT / TWIN_REL).exists(), "the twin is back on disk at %s" % TWIN_REL
    hits = subprocess.run(
        ["git", "grep", "-n", "-I", "-e", "ci-env.sh"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    ).stdout.splitlines()
    assert hits, "git grep found nothing at all; this control is not looking at the tree"
    live = []
    for hit in hits:
        path, _, rest = hit.partition(":")
        _lineno, _, text = rest.partition(":")
        if path.startswith((".ci/shadow/", "agent/", "docs/")) or path.endswith(".md"):
            continue
        stripped = text.strip()
        if stripped.startswith(("#", "//", "*", '"', "'")):
            continue
        if SOURCE_OR_RUN_RE.search(stripped):
            live.append(hit)
    assert live == [], live


def test_the_source_or_run_shape_fires_and_stays_quiet() -> None:
    """CONTROL for the guard above, in both directions, so its empty list means the pattern is live."""
    assert SOURCE_OR_RUN_RE.search('source "$CONSOLE_ROOT/.ci/scripts/infra/ci-env.sh"')
    assert SOURCE_OR_RUN_RE.search(". .ci/scripts/infra/ci-env.sh")
    assert SOURCE_OR_RUN_RE.search("bash .ci/scripts/infra/ci-env.sh")
    assert not SOURCE_OR_RUN_RE.search(
        "ENV_HEADER = '# Auto-generated by ci-env.sh -- do not edit'"
    )
    assert not SOURCE_OR_RUN_RE.search("the retired ci-env.sh twin")


# --------------------------------------------------------------------------- The constants are the twin's own text, frozen. ---------------------------------------------------------------------------


def test_the_persisted_block_matches_the_twins_frozen_heredoc() -> None:
    """`check:ci-compose-env` reads this table to decide whether a compose variable is persisted, so a name dropped from it is a variable that silently arrives empty in a later workflow step."""
    assert list(ci_env.PERSISTED) == list(FROZEN_PERSISTED)


def _bash_pipeline(text: str) -> str:
    out = subprocess.run(
        [BASH, "-c", "printf '%s\\n' \"$1\" | tr -d '/+=' | cut -c1-64", "bash", text],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return out.rstrip("\n")


def test_strip_and_cut_agrees_with_the_bash_pipeline() -> None:
    for text in (
        "aa/bb+cc=dd",
        "",
        "x" * 80,
        "/+=/+=",
        "abc" + "/" * 20 + "d" * 80,
        "MC4CAQAwBQYDK2VwBCIEIH+/abc=",
    ):
        assert ci_env.strip_and_cut(text) == _bash_pipeline(text), text


# --------------------------------------------------------------------------- The differential. ---------------------------------------------------------------------------


def test_the_supplied_everything_case_agrees_on_all_four_observables() -> None:
    old, _, calls = _sides("supplied", dict(SUPPLIED))
    assert old.exit == 0
    assert calls == [], "a generator ran even though every secret was supplied"
    assert old.chatter == [
        "CI environment configured:",
        ("  Docker Registry: " + IMAGE_REGISTRY),
        "  Web Tag: latest",
        "  Account Server: http://account-server:3000",
    ]
    assert old.env["DOCKER_REGISTRY"] == IMAGE_REGISTRY
    assert old.env["TAG"] == "latest"
    assert old.env["WEB_TAG"] == "latest"
    assert old.env["CI_MODE"] == "true"
    assert old.env["SYSTEM_PLAN_CODE"] == "COMMUNITY"
    assert old.env_file is not None
    assert old.env_file.startswith((ci_env.ENV_HEADER + "\n").encode("utf-8"))
    assert b"ACCOUNT_SERVER_API_KEY=given-api-key\n" in old.env_file
    assert old.github_env is not None
    assert old.github_env.endswith(b"ACCOUNT_JWT_SECRET=given-jwt\n")
    assert b"DOCKER_REGISTRY_USERNAME" not in old.github_env


def test_the_generators_run_with_identical_argv_when_nothing_is_supplied() -> None:
    """The node program is 300 characters of JavaScript; the ARGV is compared, not merely the fact that node was called. The frozen argv is also what pins `KEYGEN_PROGRAM` to the twin's own text now that the text is gone."""
    old, _, calls = _sides("generated", {})
    assert old.exit == 0
    verbs = [line.split("\t", 1)[0] for line in calls]
    assert verbs == ["node", "node", "openssl", "openssl", "openssl"], calls
    for i, curve in enumerate(("ed25519", "x25519")):
        assert calls[i] == "node\t-e\t" + (ci_env.KEYGEN_PROGRAM % curve).replace("\n", "\\n")
    assert calls[2] == "openssl\trand\t-base64\t48"
    assert calls[3] == "openssl\trand\t-base64\t48"
    assert calls[4] == "openssl\trand\t-hex\t32"
    assert old.env["ACCOUNT_ED25519_PRIVATE_KEY"] == "PRIV-ed25519"
    assert old.env["ACCOUNT_X25519_PUBLIC_KEY"] == "PUB-x25519"
    # `aa/bb+cc=dd` + 60 x, with `/+=` deleted and cut to 64.
    assert old.env["ACCOUNT_SERVER_API_KEY"] == "aabbccdd" + "x" * 56
    assert old.env["STRIPE_WEBHOOK_SECRET"] == STUB_WEBHOOK_VALUE + "0" * 64


def test_a_private_key_without_its_public_leaves_the_public_unexported() -> None:
    """PRESERVED QUIRK. `export A B` with B unassigned marks it for export and
    leaves it out of the environment, while `${B}` in the heredoc is empty."""
    old, _, calls = _sides(
        "half-supplied",
        {"ACCOUNT_ED25519_PRIVATE_KEY": "given-ed-priv", "ACCOUNT_X25519_PRIVATE_KEY": "given-x"},
    )
    assert old.exit == 0
    assert calls == [line for line in calls if not line.startswith("node")], calls
    assert "ACCOUNT_ED25519_PUBLIC_KEY" not in old.env
    assert "ACCOUNT_X25519_PUBLIC_KEY" not in old.env
    assert old.env_file is not None
    assert b"ACCOUNT_ED25519_PUBLIC_KEY=\n" in old.env_file
    assert b"ACCOUNT_X25519_PUBLIC_KEY=\n" in old.env_file


def test_a_failing_openssl_yields_empty_secrets() -> None:
    """THE DEFECT, reproduced rather than repaired. Measured against the live twin on 2026-09-13: exit 0, two empty secrets and a stub webhook secret, all three written to the `.env` file and appended to `$GITHUB_ENV`.

    Two things had to be true at once for `set -e` to miss it: there was no
    `set -o pipefail`, and the three assignments were `export VAR=$(...)`, whose
    status is `export`'s own. See the port's module docstring.
    """
    old, _, _ = _sides(
        "openssl-fails",
        {
            "FAKE_OPENSSL_RC": "1",
            "ACCOUNT_ED25519_PRIVATE_KEY": "p1",
            "ACCOUNT_X25519_PRIVATE_KEY": "p2",
        },
    )
    assert old.exit == 0, "the frozen twin refuses; the golden no longer records the defect"
    assert old.env["ACCOUNT_SERVER_API_KEY"] == ""
    assert old.env["ACCOUNT_JWT_SECRET"] == ""
    assert old.env["STRIPE_WEBHOOK_SECRET"] == STUB_WEBHOOK_VALUE
    assert old.env_file is not None
    assert b"\nACCOUNT_SERVER_API_KEY=\n" in old.env_file
    assert b"\nACCOUNT_JWT_SECRET=\n" in old.env_file
    assert b"\nSTRIPE_WEBHOOK_SECRET=whsec_test_\n" in old.env_file
    assert old.github_env is not None
    assert b"\nACCOUNT_JWT_SECRET=\n" in old.github_env


def test_a_missing_node_ends_the_sourcing_shell_at_127() -> None:
    """THE ASYMMETRY WITH THE CASE ABOVE. `KEYS=$(node -e ...)` was a plain
    assignment, so its status IS the substitution's and `set -e` fired."""
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        old = _run(base, "old", {}, dump=False, curated_path=True)
        new = _run(base, "new", {}, dump=False, curated_path=True)
        written = (base / ".ci" / "docker" / "ci" / ".env").exists()
    assert old.exit == new.exit == 127
    assert old.chatter == new.chatter == []
    assert old.env_file is None
    assert not written


def test_a_failing_node_propagates_its_own_exit_code() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        results = [_run(base, which, {"FAKE_NODE_RC": "3"}, dump=False) for which in ("old", "new")]
    old, new = results
    assert old.exit == new.exit == 3
    assert old.chatter == new.chatter == []
    assert old.env_file == new.env_file is None


def test_github_token_adds_the_registry_credentials() -> None:
    old, _, _ = _sides("gh-token", {**SUPPLIED, "GITHUB_TOKEN": FIXTURE_REGISTRY_CRED})
    assert old.env["DOCKER_REGISTRY_USERNAME"] == "github-actions"
    assert old.env["DOCKER_REGISTRY_PASSWORD"] == FIXTURE_REGISTRY_CRED
    assert old.env_file is not None
    assert b"DOCKER_REGISTRY_PASSWORD" not in old.env_file, "a token leaked into the .env file"


def test_github_actor_overrides_the_default_username() -> None:
    old, _, _ = _sides(
        "gh-actor", {**SUPPLIED, "GITHUB_TOKEN": FIXTURE_REGISTRY_CRED, "GITHUB_ACTOR": "octocat"}
    )
    assert old.env["DOCKER_REGISTRY_USERNAME"] == "octocat"


def test_the_masks_are_printed_only_under_github_actions_and_in_order() -> None:
    old, _, _ = _sides("masks", {**SUPPLIED, "GITHUB_ACTIONS": "true"}, dump=False)
    assert old.chatter[:8] == [
        "::add-mask::given-ed-priv",
        "::add-mask::given-ed-pub",
        "::add-mask::given-x-priv",
        "::add-mask::given-x-pub",
        "::add-mask::given-api-key",
        "::add-mask::given-jwt",
        "::add-mask::given-whsec",
        "::add-mask::admin",
    ]
    assert old.chatter[8] == "CI environment configured:"


def test_a_missing_public_key_masks_the_empty_string() -> None:
    """The mask directive is still printed, with nothing after it. Preserved: it is what hazard (a) produces, and a port that skipped the line would change stdout on a path a real CI job can take."""
    old, _, _ = _sides(
        "mask-empty",
        {
            "ACCOUNT_ED25519_PRIVATE_KEY": "p1",
            "ACCOUNT_X25519_PRIVATE_KEY": "p2",
            "ACCOUNT_SERVER_API_KEY": "k",
            "ACCOUNT_JWT_SECRET": "j",
            "STRIPE_WEBHOOK_SECRET": "s",
            "GITHUB_ACTIONS": "1",
        },
        dump=False,
    )
    assert "::add-mask::" in old.chatter
    assert old.chatter.count("::add-mask::") == 2


def test_the_workflow_tag_wins_and_web_tag_follows_it() -> None:
    old, _, _ = _sides("tag", {**SUPPLIED, "TAG": "v1.2.3"})
    assert old.env["TAG"] == "v1.2.3"
    assert old.env["WEB_TAG"] == "v1.2.3"
    assert old.chatter[2] == "  Web Tag: v1.2.3"


def test_a_web_tag_alone_does_not_move_the_tag() -> None:
    old, _, _ = _sides("web-tag", {**SUPPLIED, "WEB_TAG": "web-only"})
    assert old.env["TAG"] == "latest"
    assert old.env["WEB_TAG"] == "web-only"


def test_ci_mode_is_preserved_when_the_workflow_sets_it() -> None:
    old, _, _ = _sides("ci-mode", {**SUPPLIED, "CI_MODE": "false"})
    assert old.env["CI_MODE"] == "false"
    assert old.env_file is not None
    assert b"\nCI_MODE=false\n" in old.env_file


def test_the_two_defaulted_heredoc_names_come_from_the_caller() -> None:
    """`ENABLE_HTTPS` and `SYSTEM_ORGANIZATION_VAULT_DEFAULTS` are never exported by the subject; they are read straight out of the caller's environment when the block is expanded."""
    old, _, _ = _sides(
        "heredoc-defaults",
        {**SUPPLIED, "ENABLE_HTTPS": "true", "SYSTEM_ORGANIZATION_VAULT_DEFAULTS": "{}"},
    )
    assert old.env_file is not None
    assert b"\nENABLE_HTTPS=true\n" in old.env_file
    assert b"\nSYSTEM_ORGANIZATION_VAULT_DEFAULTS={}\n" in old.env_file
    assert "ENABLE_HTTPS" in old.env


def test_the_system_defaults_are_overridable_one_at_a_time() -> None:
    old, _, _ = _sides(
        "system",
        {**SUPPLIED, "SYSTEM_DOMAIN": "example.test", "SYSTEM_ADMIN_PASSWORD": FIXTURE_ADMIN_WORD},
    )
    assert old.env["SYSTEM_DOMAIN"] == "example.test"
    assert old.env["SYSTEM_ADMIN_PASSWORD"] == FIXTURE_ADMIN_WORD
    assert old.env["SYSTEM_ADMIN_EMAIL"] == ADMIN_EMAIL_DEFAULT


def test_no_github_env_means_nothing_is_appended_anywhere() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        _stub_bin(base)
        before = sorted(p.name for p in base.iterdir())
        old = _run(base, "old", dict(SUPPLIED), dump=False, github_env=False)
        new = _run(base, "new", dict(SUPPLIED), dump=False, github_env=False)
        after = sorted(p.name for p in base.iterdir())
    assert old.exit == new.exit == 0
    assert old.chatter == new.chatter
    assert old.env_file == new.env_file
    # `calls.log` is the harness's own record, written before every run; anything else new is a write outside the tree.
    assert sorted(set(after) - {"calls.log"}) == sorted(set(before) - {"calls.log"}), (
        "something was written outside the tree: %r -> %r" % (before, after)
    )


def test_an_unwritable_env_directory_stops_the_run_after_the_masks() -> None:
    """A NAMED DIVERGENCE, and the only one in this file. bash reported a failed redirection as `<script>: line 165: <path>: No such file or directory`; the port names the same path in its own words. Exit code, stdout and the absence of the file are identical, and that is what is asserted."""
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        shutil.rmtree(base / ".ci" / "docker" / "ci")
        results = [
            _run(base, which, {**SUPPLIED, "GITHUB_ACTIONS": "1"}, dump=False)
            for which in ("old", "new")
        ]
        old, new = results
    assert old.exit == new.exit == 1
    assert old.chatter == new.chatter
    assert old.chatter[0] == "::add-mask::given-ed-priv", old.chatter
    assert "CI environment configured:" not in old.chatter
    assert old.env_file is new.env_file is None
    assert b".env" in old.stderr
    assert b".env" in new.stderr


def test_the_persisted_verb_writes_nothing() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        proc = subprocess.run(
            [sys.executable, str(base / ".ci/rediacc_ci/infra/ci_env.py"), "persisted"],
            capture_output=True,
            env={
                "PATH": _stub_bin(base),
                "HOME": str(base),
                "PYTHONPATH": str(ROOT / ".ci"),
                "PYTHONDONTWRITEBYTECODE": "1",
                **SUPPLIED,
            },
            check=False,
            cwd=str(base),
        )
        written = (base / ".ci" / "docker" / "ci" / ".env").exists()
    assert proc.returncode == 0
    assert proc.stdout.startswith(b"DOCKER_REGISTRY=\n"), proc.stdout[:60]
    assert not written


def test_an_unknown_verb_and_no_verb_both_print_the_usage() -> None:
    for argv in ([], ["--help"], ["nonsense"]):
        assert ci_env.main(argv) == 2


def test_the_golden_round_trips_bytes_and_none() -> None:
    """The `.env` file and `$GITHUB_ENV` are recorded as bytes or None; a JSON round trip that turned None into "" or bytes into str would make two different answers compare equal."""
    assert json.loads(json.dumps(diff._to_json([None, b"x"]))) == [None, {"__bytes__": "eA=="}]
    assert diff._from_json([None, {"__bytes__": "eA=="}]) == [None, b"x"]
