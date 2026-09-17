"""Differential: `rediacc_ci.infra.ci_env` against its twin
`.ci/scripts/infra/ci-env.sh`.

THE TWIN IS SOURCED, NEVER EXECUTED, so "run both and compare stdout" is not
the comparison. Sourcing it leaves FOUR observables behind and this file
compares all four on every case:

  1. the exported environment (`env` after sourcing, versus the port's `env`
     verb), with the four shell-private names dropped from BOTH SIDES by the
     same helper -- never inside the port, because a filter the twin has no
     equivalent of is exactly how a port drops a name and still looks equal;
  2. `$CI_DOCKER_DIR/.env`, byte for byte;
  3. the bytes appended to `$GITHUB_ENV`;
  4. stdout: the `::add-mask::` directives and the three summary lines.

ONE TREE, TWO SEQUENTIAL RUNS, and that is deliberate. `CONSOLE_ROOT` is
derived from the script's own location on both sides, so giving each side its
own copy of the tree would make `CI_DOCKER_DIR` and `CI_COMPOSE_FILE`
legitimately differ and every case would need those two values normalised away.
Sharing one tree makes them identical and keeps the comparison exact; the
artifacts are captured after each run, before the other side overwrites them.

`node` AND `openssl` ARE RECORDING FAKES ON A PREPENDED PATH, for two reasons
and only the first is speed. The second is that both real programs are RANDOM:
a differential against the real ones can only ever compare shapes, and shapes
are what a port gets right while producing a key that does not verify. With
canned generators the comparison is byte-exact, and the ARGV the two sides hand
to `node` -- a 300-character program whose curve name is the only thing that
varies -- is compared too.

THREE TWIN BEHAVIOURS PINNED BY NAME, all measured against the live bash on
2026-09-13 before the port was written:

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

K=5 LEDGER: `.ci/shadow/w7p6-ci-env.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.infra import ci_env

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-env.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_env.py"
BASH = shutil.which("bash") or "/bin/bash"

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
    """One run's four observables."""

    __slots__ = ("chatter", "env", "env_file", "exit", "github_env", "stderr")

    def __init__(self, code, chatter, environ, env_file, github_env, stderr) -> None:
        self.exit = code
        self.chatter = chatter
        self.env = environ
        self.env_file = env_file
        self.github_env = github_env
        self.stderr = stderr

    def as_tuple(self):
        return (self.exit, self.chatter, self.env, self.env_file, self.github_env)


def _tree(base: pathlib.Path) -> pathlib.Path:
    """A checkout-shaped tree holding BOTH implementations at their real depths.

    The depth is what matters: each side computes `CONSOLE_ROOT` from its own
    file's location, the twin as `<dir>/../../..` and the port as `parents[3]`,
    and both must land on `base`.
    """
    (base / ".ci" / "scripts" / "infra").mkdir(parents=True)
    (base / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (base / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    (base / ".ci" / "docker" / "ci").mkdir(parents=True)
    shutil.copy2(TWIN, base / ".ci" / "scripts" / "infra" / "ci-env.sh")
    shutil.copy2(COMMON, base / ".ci" / "scripts" / "lib" / "common.sh")
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


def _split(stdout: bytes, environ_out: bool):
    """Separate the env dump from the chatter, and drop the shell-private names.

    A dump line is `NAME=value` with a shell-legal NAME; every mask directive
    starts with `:` and every summary line has no `=` before its first space,
    so the split is unambiguous. The filtering happens HERE, on both sides
    identically -- never in the port. See the module docstring.
    """
    chatter: list[str] = []
    found: dict[str, str] = {}
    for line in stdout.decode("utf-8", "surrogateescape").split("\n"):
        if line == "":
            continue
        if environ_out and NAME_VALUE.match(line):
            name, _, value = line.partition("=")
            if name not in ci_env.SHELL_PRIVATE:
                found[name] = value
            continue
        chatter.append(line)
    return chatter, found


def _run(base: pathlib.Path, which: str, env_extra: dict[str, str], *, dump: bool) -> Side:
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    env_file = base / ".ci" / "docker" / "ci" / ".env"
    if env_file.exists():
        env_file.unlink()
    # ONE path for both sides, truncated before each run: the value lands in the environment dump, so two different paths would read as a divergence in the thing under test.
    github_env = base / "github-env"
    github_env.write_text("", encoding="utf-8")

    env = {
        "PATH": _stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(log),
        "GITHUB_ENV": str(github_env),
    }
    env.update(env_extra)

    if which == "old":
        script = '. "$1"' + ("; env" if dump else "")
        argv = [BASH, "-c", script, "bash", str(base / ".ci/scripts/infra/ci-env.sh")]
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
        github_env.read_bytes(),
        proc.stderr,
    )


def _sides(name: str, env_extra: dict[str, str] | None = None, *, dump: bool = True):
    """Both implementations over ONE tree, in sequence. Returns (old, new, calls)."""
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        old = _run(base, "old", dict(env_extra or {}), dump=dump)
        old_calls = (base / "calls.log").read_text(encoding="utf-8").splitlines()
        new = _run(base, "new", dict(env_extra or {}), dump=dump)
        new_calls = (base / "calls.log").read_text(encoding="utf-8").splitlines()
    labels = ("exit", "chatter", "environment", ".env file", "GITHUB_ENV")
    for i, label in enumerate(labels):
        assert new.as_tuple()[i] == old.as_tuple()[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old.as_tuple()[i],
            new.as_tuple()[i],
        )
    assert new_calls == old_calls, "%s: generator calls diverged:\n twin: %r\n port: %r" % (
        name,
        old_calls,
        new_calls,
    )
    return old, new, old_calls


# --------------------------------------------------------------------------- Controls: a comparison against a file that is not there proves nothing. ---------------------------------------------------------------------------


def test_all_three_files_exist_where_this_file_says_they_do() -> None:
    for path in (TWIN, COMMON, PORT):
        assert path.is_file(), path


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_the_fakes_are_what_resolves() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("node", path=path) == str(base / "bin" / "node")
        assert shutil.which("openssl", path=path) == str(base / "bin" / "openssl")


def test_the_twin_is_sourced_by_two_scripts_and_executed_by_none() -> None:
    """THE REASON THIS PORT IS A LIBRARY, re-checked rather than inherited from
    the allowlist. If something ever starts EXECUTING the twin, this goes red
    and the port needs a real CLI."""
    hits = subprocess.run(
        ["git", "grep", "-n", "ci-env.sh", "--", "*.sh"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    ).stdout.splitlines()
    assert hits, "git grep found nothing at all; this control is not looking at the tree"
    sourcing: list[str] = []
    executed: list[str] = []
    for hit in hits:
        path, _, rest = hit.split(":", 2)
        text = rest.strip()
        if text.startswith("#"):
            continue
        if re.match(r'^(source|\.)\s+"?[^\s"]*ci-env\.sh', text):
            sourcing.append(path)
        elif re.search(r'(bash|sh|\./)\s*"?[^\s"]*ci-env\.sh', text):
            executed.append(hit)
    assert sorted(set(sourcing)) == [
        ".ci/scripts/infra/ci-start-account.sh",
        ".ci/scripts/infra/ci-start-elite.sh",
    ], sourcing
    assert executed == [], executed


# --------------------------------------------------------------------------- The constants are the twin's own text, not a paraphrase of it. ---------------------------------------------------------------------------


def test_the_node_programs_are_the_twins_own_text() -> None:
    source = TWIN.read_text(encoding="utf-8")
    for curve in ("ed25519", "x25519"):
        assert ci_env.KEYGEN_PROGRAM % curve in source, curve


def test_the_persisted_block_matches_the_twins_heredoc() -> None:
    """`check-compose-env.sh` parses this same heredoc out of the twin to decide
    whether a compose variable is persisted, so a name dropped from the port's
    table is a variable that silently arrives empty in a later workflow step."""
    source = TWIN.read_text(encoding="utf-8")
    body = source.split("<<ENVBLOCK\n", 1)[1].split("\nENVBLOCK", 1)[0]
    expected = []
    for line in body.split("\n"):
        name, _, expansion = line.partition("=")
        if ":-" in expansion:
            expected.append((name, expansion.split(":-", 1)[1].rstrip("}")))
        else:
            expected.append((name, None))
    assert list(ci_env.PERSISTED) == expected


def test_the_env_file_header_is_the_twins_byte_sequence() -> None:
    assert ci_env.ENV_HEADER in TWIN.read_text(encoding="utf-8")


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
        "  Docker Registry: ghcr.io/rediacc",
        "  Web Tag: latest",
        "  Account Server: http://account-server:3000",
    ]
    assert old.env["DOCKER_REGISTRY"] == "ghcr.io/rediacc"
    assert old.env["TAG"] == "latest"
    assert old.env["WEB_TAG"] == "latest"
    assert old.env["CI_MODE"] == "true"
    assert old.env["SYSTEM_PLAN_CODE"] == "COMMUNITY"
    assert old.env_file is not None
    assert old.env_file.startswith(b"# Auto-generated by ci-env.sh")
    assert b"ACCOUNT_SERVER_API_KEY=given-api-key\n" in old.env_file
    assert old.github_env.endswith(b"ACCOUNT_JWT_SECRET=given-jwt\n")
    assert b"DOCKER_REGISTRY_USERNAME" not in old.github_env


def test_the_generators_run_with_identical_argv_when_nothing_is_supplied() -> None:
    """The node program is 300 characters of JavaScript; the ARGV is compared,
    not merely the fact that node was called."""
    old, _, calls = _sides("generated", {})
    assert old.exit == 0
    verbs = [line.split("\t", 1)[0] for line in calls]
    assert verbs == ["node", "node", "openssl", "openssl", "openssl"], calls
    assert "ed25519" in calls[0]
    assert "x25519" in calls[1]
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
    """THE DEFECT, reproduced rather than repaired. Measured against the live
    twin on 2026-09-13: exit 0, two empty secrets and a stub webhook secret,
    all three written to the `.env` file and appended to `$GITHUB_ENV`.

    Two things have to be true at once for `set -e` to miss it: there is no
    `set -o pipefail`, and the three assignments are `export VAR=$(...)`, whose
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
    assert old.exit == 0, "the twin started refusing; the defect is fixed, update the port"
    assert old.env["ACCOUNT_SERVER_API_KEY"] == ""
    assert old.env["ACCOUNT_JWT_SECRET"] == ""
    assert old.env["STRIPE_WEBHOOK_SECRET"] == STUB_WEBHOOK_VALUE
    assert old.env_file is not None
    assert b"\nACCOUNT_SERVER_API_KEY=\n" in old.env_file
    assert b"\nACCOUNT_JWT_SECRET=\n" in old.env_file
    assert b"\nSTRIPE_WEBHOOK_SECRET=whsec_test_\n" in old.env_file
    assert b"\nACCOUNT_JWT_SECRET=\n" in old.github_env


def test_a_missing_node_ends_the_sourcing_shell_at_127() -> None:
    """THE ASYMMETRY WITH THE CASE ABOVE. `KEYS=$(node -e ...)` is a plain
    assignment, so its status IS the substitution's and `set -e` fires."""
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        _stub_bin(base)
        (base / "bin" / "node").unlink()
        # A CURATED PATH, because the real one has a real node on it and the point of this case is that there is none. `dirname` and `uname` are what the twin needs before it reaches node: its own SCRIPT_DIR, and common.sh's detect_os/detect_arch, which run at SOURCE time.
        for name in ("dirname", "uname"):
            real = shutil.which(name)
            assert real is not None, name
            (base / "bin" / name).symlink_to(real)
        results = []
        for which in ("old", "new"):
            log = base / "calls.log"
            log.write_text("", encoding="utf-8")
            github_env = base / "github-env"
            github_env.write_text("", encoding="utf-8")
            env = {
                "PATH": str(base / "bin"),
                "HOME": str(base),
                "LC_ALL": "C",
                "LANG": "C",
                "PYTHONPATH": str(ROOT / ".ci"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "FAKE_LOG": str(log),
                "GITHUB_ENV": str(github_env),
            }
            argv = (
                [BASH, "-c", '. "$1"', "bash", str(base / ".ci/scripts/infra/ci-env.sh")]
                if which == "old"
                else [sys.executable, str(base / ".ci/rediacc_ci/infra/ci_env.py"), "apply"]
            )
            results.append(
                subprocess.run(
                    argv, capture_output=True, env=env, check=False, cwd=str(base), timeout=60
                )
            )
        old, new = results
    assert old.returncode == new.returncode == 127
    assert old.stdout == new.stdout == b""
    assert not (base / ".ci" / "docker" / "ci" / ".env").exists()


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
    """The mask directive is still printed, with nothing after it. Preserved:
    it is what hazard (a) produces, and a port that skipped the line would
    change stdout on a path a real CI job can take."""
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
    """`ENABLE_HTTPS` and `SYSTEM_ORGANIZATION_VAULT_DEFAULTS` are never
    exported by this script; they are read straight out of the caller's
    environment when the block is expanded."""
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
    assert old.env["SYSTEM_ADMIN_EMAIL"] == "admin@rediacc.io"


def test_no_github_env_means_nothing_is_appended_anywhere() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = _tree(pathlib.Path(td))
        results = []
        for which in ("old", "new"):
            log = base / "calls.log"
            log.write_text("", encoding="utf-8")
            env = {
                "PATH": _stub_bin(base),
                "HOME": str(base),
                "LC_ALL": "C",
                "LANG": "C",
                "PYTHONPATH": str(ROOT / ".ci"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "FAKE_LOG": str(log),
                **SUPPLIED,
            }
            argv = (
                [BASH, "-c", '. "$1"', "bash", str(base / ".ci/scripts/infra/ci-env.sh")]
                if which == "old"
                else [sys.executable, str(base / ".ci/rediacc_ci/infra/ci_env.py"), "apply"]
            )
            results.append(
                subprocess.run(
                    argv, capture_output=True, env=env, check=False, cwd=str(base), timeout=60
                )
            )
        old, new = results
        assert old.returncode == new.returncode == 0
        assert old.stdout == new.stdout
        assert sorted(p.name for p in base.iterdir()) == sorted([".ci", "bin", "calls.log"]), (
            "something was written outside the tree"
        )


def test_an_unwritable_env_directory_stops_the_run_after_the_masks() -> None:
    """A NAMED DIVERGENCE, and the only one in this file. bash reports a failed
    redirection as `<script>: line 165: <path>: No such file or directory`; the
    port names the same path in its own words. Exit code, stdout and the
    absence of the file are identical, and that is what is asserted."""
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
    assert proc.returncode == 0
    assert proc.stdout.startswith(b"DOCKER_REGISTRY=\n"), proc.stdout[:60]
    assert not (base / ".ci" / "docker" / "ci" / ".env").exists()


def test_an_unknown_verb_and_no_verb_both_print_the_usage() -> None:
    for argv in ([], ["--help"], ["nonsense"]):
        assert ci_env.main(argv) == 2
