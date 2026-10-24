"""Differential: `rediacc_ci.deploy.deploy_proxy` against the frozen output of its retired twin `.ci/scripts/deploy/deploy-proxy.sh` (`tests/goldens/twins/deploy.deploy-proxy.jsonl`).

RECORDING FAKE `npm`, `npx` AND `curl` ON A SCRATCH PATH, AND A FIXTURE REPO ROOT WITH RECORDING FAKES OF `resolve-version.sh` AND `build-renet.sh` AT THEIR REAL PATHS. NOTHING IS BUILT OR FETCHED HERE. The twin's first real act is two `npm run build --workspace` runs from the repo root (:45-46), and the fake `npm` is what stops them: a differential that let those run would compile `@rediacc/shared` and `@rediacc/cli` for real, twice per case. The root is made to agree across the two
implementations exactly as in the two sibling differentials -- a COPY of `common.sh` inside `tmp_path` for the bash side, `$REDIACC_CI_ROOT` for the port -- and `test_the_copied_twin_is_the_real_twin` keeps the copy honest.

`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece. The twin is additionally MANUAL ONLY by its own header: no workflow invokes it, and CI drives only the `--dry-run` path.

WHAT THE STREAMS CANNOT SHOW, and therefore what the call log is compared for: which region reached wrangler (none: the twin printed the region and passed it nowhere; the port refuses any region but eu before any call), whether the dry run really passed `--outdir`, and whether the two builds ran BEFORE the worker directory was looked at. All three are recorded rather than inferred.

TWO DEFECTS IN THE TWIN ARE PINNED, NOT FIXED:
`test_the_build_runs_before_the_directory_is_checked` shows both builds completing and only then a failed `cd`, and `test_the_account_id_is_documented_and_never_checked` shows a run succeeding
with `CLOUDFLARE_ACCOUNT_ID` entirely absent, against a header that lists it as
required.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import types
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_proxy as port
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests.twin_names import as_twin
from rediacc_ci.well_known import (
    ACCOUNT_DEFAULT_ORIGIN,
    BENCH_ORIGIN,
    PROXY_BENCH_HOST,
    PROXY_EU_HOST,
)

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/deploy/deploy-proxy.sh"
TWIN = ROOT / TWIN_REL
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "deploy_proxy.py"

# The port is driven through this program, which swaps its two siblings for the recording fakes: `resolve_version.run` (in process) and the argv of the renet build (a child). The twin reached the same fakes by path.
DRIVER = """
import os
import sys

from rediacc_ci.deploy import deploy_proxy
from rediacc_ci.version import resolve_version


def fake_resolve(argv):
    with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
        fh.write("resolve-version.sh\\t" + "\\t".join(argv) + "\\n")
        fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
    return 0, os.environ.get("FAKE_VERSION", "1.2.3") + "\\n", ""


def fake_build_argv(repo_root, version):
    return [str(repo_root / ".ci" / "scripts" / "build" / "build-renet.sh"), "--version", version]


resolve_version.run = fake_resolve
deploy_proxy.build_renet_argv = fake_build_argv
sys.exit(deploy_proxy.main(sys.argv[1:]))
"""
BASH = shutil.which("bash") or "/bin/bash"

# `uname` and `dirname` are what `common.sh` needs at source time; `tr` is `to_upper` (common.sh:302), which every `parse_args` key goes through. `sed`, `head` and `cp` are the real deploy's renet staging and smoke-URL steps.
PATH_MINIMUM = ("tr", "uname", "dirname", "sed", "head", "cp")

FAKE_NPX = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")

rc = int(os.environ.get("FAKE_NPX_RC", "0"))
if rc:
    sys.stderr.write("wrangler: deploy failed\\n")
    sys.exit(rc)
sys.stdout.write("Total Upload: 1.00 KiB\\n")
"""

FAKE_NPM = """#!/usr/bin/python3
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("npm\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")

rc = int(os.environ.get("FAKE_NPM_RC", "0"))
if rc:
    sys.stderr.write("npm ERR! build failed\\n")
    sys.exit(rc)
sys.stdout.write("> build done\\n")
"""

# The two repo scripts a real deploy runs, faked INSIDE the fixture root at their real paths: both twins call them by path, not through PATH.
FAKE_RESOLVE_VERSION = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("resolve-version.sh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
sys.stdout.write(os.environ.get("FAKE_VERSION", "1.2.3") + "\\n")
"""

FAKE_BUILD_RENET = """#!/usr/bin/python3
import os
import pathlib
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("build-renet.sh\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
rc = int(os.environ.get("FAKE_RENET_RC", "0"))
if rc:
    sys.stderr.write("go: build failed\\n")
    sys.exit(rc)
if not os.environ.get("FAKE_RENET_NO_BINARY"):
    out = pathlib.Path(__file__).resolve().parents[3] / "private" / "bin"
    out.mkdir(parents=True, exist_ok=True)
    (out / "renet-linux-amd64").write_text("RENET " + sys.argv[2] + "\\n")
sys.stdout.write("renet built\\n")
"""

# A recording curl: the HTTP code comes from FAKE_HEALTH / FAKE_INFO by path, FAKE_CURL_RC makes it an unreachable host (curl prints 000 then fails).
FAKE_CURL = """#!/usr/bin/python3
import os
import sys

url = sys.argv[-1]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(sys.argv[1:]) + "\\n")
rc = int(os.environ.get("FAKE_CURL_RC", "0"))
if rc:
    sys.stdout.write("000")
    sys.stderr.write("curl: (6) Could not resolve host\\n")
    sys.exit(rc)
if url.endswith("/v1/health"):
    sys.stdout.write(os.environ.get("FAKE_HEALTH", "200"))
else:
    sys.stdout.write(os.environ.get("FAKE_INFO", "401"))
"""

SMOKE_HOST = "proxy.test.example"

# The smoke's resolution retry and DoH fallback are off in the subprocess runs: the frozen twin made one curl call per request and never touched the network.
BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok",
    "ACCOUNT_ED25519_PUBLIC_KEY": "pubkey",
    "REDIACC_SMOKE_RESOLVE_WINDOW_S": "0",
    "REDIACC_SMOKE_DOH_URL": "",
}

# The whole stderr of a successful real deploy, in order. Quoted once here because four tests need to say "and not this".
DEPLOY_STDERR = (
    "→ Building the CLI bundle the container image ships...\n"
    "→ Building the renet the container image ships...\n"
    "→ Deploying the proxy worker and container image (region: eu)...\n"
    "→ Smoke-testing https://proxy.test.example...\n"
    "✓ Smoke test passed: /v1/health 200, unauthenticated /v1/server-info 401.\n"
    "✓ Deployed. The executor still needs its own account token:\n"
    "✓   npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml\n"
    "✓ That token must carry the proxy:exec and audit:write scopes and belong to the Rediacc org.\n"
)


def _fixture_root(tmp_path: pathlib.Path, *, worker: str = "dir") -> pathlib.Path:
    """A repo root holding a COPY of the twin, its library, and `workers/proxy`.

    `worker` is `dir` for the normal case, `file` for the "Not a directory" one, and `absent` for the missing-directory defect.
    """
    root = tmp_path / "root"
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / "workers").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.env", root / ".ci" / "config" / "well-known.env"
    )
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.generated.sh",
        root / ".ci" / "config" / "well-known.generated.sh",
    )
    if TWIN.is_file():
        # Only while the twin exists, i.e. on a re-freeze from bash; compare mode never runs it.
        shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    for rel, body in (
        (("version", "resolve-version.sh"), FAKE_RESOLVE_VERSION),
        (("build", "build-renet.sh"), FAKE_BUILD_RENET),
    ):
        fake = root / ".ci" / "scripts" / rel[0] / rel[1]
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    target = root / "workers" / "proxy"
    if worker == "dir":
        target.mkdir(exist_ok=True)
        (target / "renet").mkdir(exist_ok=True)
        (target / "wrangler.toml").write_text(
            'name = "rediacc-proxy"\nroutes = [\n  { pattern = "%s", custom_domain = true }\n]\n'
            % SMOKE_HOST,
            encoding="utf-8",
        )
    elif worker == "file":
        target.write_text("not a directory\n", encoding="utf-8")
    return root


def _bin(tmp_path: pathlib.Path, name: str) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for fake_name, body in (("npx", FAKE_NPX), ("npm", FAKE_NPM), ("curl", FAKE_CURL)):
        fake = stub / fake_name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def _run(
    subject: pathlib.Path,
    tmp_path: pathlib.Path,
    root: pathlib.Path,
    args: tuple[str, ...],
    *,
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    side = "old" if subject.suffix == ".sh" else "new"
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    argv = [BASH, str(subject)] if subject.suffix == ".sh" else [sys.executable, "-c", DRIVER]
    proc = subprocess.run(
        [*argv, *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(
    tmp_path: pathlib.Path, root: pathlib.Path, *args: str, label: str | None = None, **kw
):
    """Both sides. `label` reads the golden under ANOTHER test's name: the key is `<test name>#<hash>`, so a test renamed after the twin was frozen names the old one to reach its records."""
    twin_copy = root / ".ci" / "scripts" / "deploy" / TWIN.name
    old, old_calls = diff.twin_result(
        TWIN_REL,
        ["args=%r" % (args,), "kw=%r" % (sorted(kw.items()),)],
        lambda: _run(twin_copy, tmp_path, root, args, **kw),
        work=(str(tmp_path),),
        label=label,
    )
    new, new_calls = _run(PORT, tmp_path, root, args, **kw)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert as_twin(new.stdout) == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {as_twin(new.stdout)!r}"
    )
    assert as_twin(new.stderr) == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {as_twin(new.stderr)!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: the recorded calls diverged:\nold: {old_calls!r}\nnew: {new_calls!r}"
        )


def _twin_source() -> str:
    """The twin's text, as frozen with its other answers."""
    return diff.twin_call(TWIN_REL, ["source"], lambda: (0, TWIN.read_text(encoding="utf-8"), ""))[
        1
    ]


def _twin_line(needle: str) -> int:
    """The 1-based line of the twin's only line starting with `needle`, as bash's own diagnostics number it.

    READ FROM THE TWIN, NOT HARD-CODED: c8f92eaa0 added `require_cmd curl` above both lines and a literal `line 36` / `line 48` went red on an unchanged behaviour.
    """
    hits = [
        n for n, line in enumerate(_twin_source().splitlines(), start=1) if line.startswith(needle)
    ]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


# --------------------------------------------------------------------------- The real deploy ---------------------------------------------------------------------------


def test_the_default_run_is_a_real_deploy_and_is_pinned_in_full(tmp_path: pathlib.Path) -> None:
    """TWO BUILDS FROM THE ROOT, A RENET BUILD AT THE RELEASE VERSION, ONE BARE `wrangler deploy` FROM THE WORKER DIRECTORY, THEN THE TWO SMOKE REQUESTS. Note the deploy carries no `--config`, unlike both siblings, and that `--dry-run` defaults to false so the DEFAULT is the deploying path."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    curl = "curl\t-sS\t-o\t/dev/null\t-w\t%{http_code}\t--max-time\t30\t"
    assert old_calls == (
        "npm\trun\tbuild\t--workspace\t@rediacc/shared\n"
        "  cwd=root\n"
        "npm\trun\tbuild\t--workspace\t@rediacc/cli\n"
        "  cwd=root\n"
        "resolve-version.sh\t--current\n"
        "  cwd=proxy\n"
        "build-renet.sh\t--version\t1.2.3\n"
        "  cwd=proxy\n"
        "npx\twrangler\tdeploy\n"
        "  cwd=proxy\n"
        f"{curl}https://{SMOKE_HOST}/v1/health\n"
        f"{curl}https://{SMOKE_HOST}/v1/server-info\n"
    )
    assert old.stderr == DEPLOY_STDERR
    assert old.stdout == "> build done\n> build done\nrenet built\nTotal Upload: 1.00 KiB\n"
    _assert_agree(old, new, "default-deploy", old_calls, new_calls)


def test_the_three_closing_lines_all_carry_the_check_glyph(tmp_path: pathlib.Path) -> None:
    """THEY GO THROUGH `log_info`, INCLUDING THE ONE THAT IS A COMMAND TO COPY (:80). A reader pasting that line pastes a `✓ ` and two spaces with it, so the port must not "clean up" the middle line into a plain print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    for line in port.CLOSING_LINES:
        assert "✓ %s\n" % line in old.stderr
    assert "✓   npx wrangler secret put" in old.stderr
    _assert_agree(old, new, "closing-lines", old_calls, new_calls)


# The name the twin's region records were frozen under, before the port repaired the defect they show.
TWIN_REGION_LABEL = "test_the_region_is_printed_and_never_passed_to_wrangler"


def test_a_region_other_than_eu_refuses_before_any_build(tmp_path: pathlib.Path) -> None:
    """THE TWIN'S DEFECT, REPAIRED (PLAN-cloudflare-proxy.md, the `--region` box). The frozen twin answered `--region asia` with exit 0, a log line saying `asia`, and calls byte-identical to an eu run: a deploy of the eu config under a message naming another region. The port refuses any region but eu, exit 1, before the token check and before any build, so the call log stays empty."""
    root = _fixture_root(tmp_path)
    eu_old, eu_new, eu_old_calls, eu_new_calls = run_both(tmp_path, root, label=TWIN_REGION_LABEL)
    as_old, as_new, as_old_calls, as_new_calls = run_both(
        tmp_path, root, "--region", "asia", label=TWIN_REGION_LABEL
    )
    # What the twin did, from its golden: the defect this test exists for.
    assert as_old.returncode == 0, as_old.stderr
    assert "(region: asia)" in as_old.stderr
    assert as_old_calls == eu_old_calls
    # The default region still agrees with the twin in full.
    _assert_agree(eu_old, eu_new, "region-eu", eu_old_calls, eu_new_calls)
    # What the port does instead.
    assert as_new.returncode == 1, as_new.stderr
    assert as_new.stdout == ""
    assert as_new.stderr == "✗ %s\n" % port.region_refusal("asia")
    assert "workers/proxy/wrangler.toml" in as_new.stderr
    assert as_new_calls == "", (
        "nothing may be built or deployed for a region the config does not name"
    )


def test_a_region_refusal_needs_no_token(tmp_path: pathlib.Path) -> None:
    """The region is an argument error, checked before the token, so a caller with no credentials still learns the real problem."""
    root = _fixture_root(tmp_path)
    proc, calls = _run(PORT, tmp_path, root, ("--region", "us"), drop_env=("CLOUDFLARE_API_TOKEN",))
    assert proc.returncode == 1
    assert proc.stderr == "✗ %s\n" % port.region_refusal("us")
    assert calls == ""


def test_an_explicit_eu_region_deploys_exactly_as_the_default(tmp_path: pathlib.Path) -> None:
    """The refusal must not fire on the one region the config names."""
    root = _fixture_root(tmp_path)
    for side in ("d", "e"):
        (tmp_path / side).mkdir()
    default, default_calls = _run(PORT, tmp_path / "d", root, ())
    explicit, explicit_calls = _run(PORT, tmp_path / "e", root, ("--region", "eu"))
    assert explicit.returncode == 0, explicit.stderr
    assert explicit.stderr == default.stderr == DEPLOY_STDERR
    assert explicit_calls == default_calls != ""


def test_an_absent_region_defaults_to_eu(tmp_path: pathlib.Path) -> None:
    """`${ARG_REGION:-eu}` (:33), and `--region=` is EMPTY, which the `:-` form
    also replaces. A port using `args.get("ARG_REGION", "eu")` would print an empty region for the second case."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--region=")
    assert "(region: %s)" % port.DEFAULT_REGION in old.stderr
    _assert_agree(old, new, "empty-region", old_calls, new_calls)


# --------------------------------------------------------------------------- The dry run ---------------------------------------------------------------------------


def test_a_bare_dry_run_flag_takes_the_dry_run_path(tmp_path: pathlib.Path) -> None:
    """`parse_args` stores the string `true` for a flag with no value, which is
    exactly what `[[ "$DRY_RUN" == "true" ]]` (:50) wants. The run exits 0 at
    :54, so none of the three closing lines print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run")
    assert old.returncode == 0, old.stderr
    assert old_calls.endswith(
        "npx\twrangler\tdeploy\t--dry-run\t--outdir\t/tmp/rediacc-proxy-dry-run\n  cwd=proxy\n"
    )
    assert old.stderr == (
        "→ Building the CLI bundle the container image ships...\n"
        "→ Dry run: type-checking and compiling the worker without deploying...\n"
        "✓ Dry run passed. Nothing was deployed.\n"
    )
    assert "EXECUTOR_TOKEN" not in old.stderr
    _assert_agree(old, new, "dry-run-bare", old_calls, new_calls)


def test_the_dry_run_still_builds_first(tmp_path: pathlib.Path) -> None:
    """THE BUILD IS NOT SKIPPED ON A DRY RUN (:43-46 run before the branch at :50), which is what makes the dry run a real check of the CLI bundle."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run")
    assert old_calls.count("npm\trun\tbuild") == 2
    _assert_agree(old, new, "dry-run-builds", old_calls, new_calls)


def test_only_the_literal_true_is_a_dry_run(tmp_path: pathlib.Path) -> None:
    """`--dry-run yes` IS A REAL DEPLOY. The comparison at :38 is against the string `true` and nothing else, so a plausible-looking value deploys the executor. Driven in both directions rather than argued."""
    root = _fixture_root(tmp_path)
    for value, deploying in (("true", False), ("false", True), ("yes", True), ("1", True)):
        old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run", value)
        assert old.returncode == 0, old.stderr
        assert ("--dry-run" not in old_calls) is deploying, value
        assert ("EXECUTOR_TOKEN" in old.stderr) is deploying, value
        _assert_agree(old, new, "dry-run-%s" % value, old_calls, new_calls)


def test_the_dry_run_outdir_is_a_fixed_tmp_path(tmp_path: pathlib.Path) -> None:
    """NOT A `mktemp` (:52). Two concurrent dry runs write the same directory, and so does anything else that picks the name. Reproduced as the literal."""
    del tmp_path
    assert port.DRY_RUN_OUTDIR in _twin_source()
    assert "mktemp" not in _twin_source()


# --------------------------------------------------------------------------- Refusals and failures ---------------------------------------------------------------------------


def test_a_missing_token_refuses_before_the_build(tmp_path: pathlib.Path) -> None:
    """THE ONE DIVERGENCE ON THIS PATH, asserted from both sides: bash prefixes
    its `${VAR:?}` diagnostic with the script path as invoked and a line number.
    The doubled variable name is the twin's own message, not a mistake here.

    THE ORDER IS THE POINT: nothing is built, so the refusal is cheap."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, drop_env=("CLOUDFLARE_API_TOKEN",))
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stderr.endswith(port.MISSING_AUTH_MSG + "\n")
    assert ": line %d: " % _twin_line(': "${CLOUDFLARE_API_TOKEN:?') in old.stderr
    assert new.stderr == port.MISSING_AUTH_MSG + "\n"
    assert old.stdout == new.stdout == ""
    assert old_calls == new_calls == "", "nothing may be built before the token is checked"


def test_an_empty_token_refuses_exactly_as_an_absent_one_does(tmp_path: pathlib.Path) -> None:
    """`:?` IS AN UNSET-OR-EMPTY TEST."""
    root = _fixture_root(tmp_path)
    old, new, _, _ = run_both(tmp_path, root, CLOUDFLARE_API_TOKEN="")
    assert old.returncode == new.returncode == 1
    assert old.stderr.endswith(port.MISSING_AUTH_MSG + "\n")
    assert new.stderr == port.MISSING_AUTH_MSG + "\n"


def test_the_account_id_is_documented_and_never_checked(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. The header (:22) lists `CLOUDFLARE_ACCOUNT_ID` under "Requires:" and no line reads it, so a run without it builds the CLI and calls wrangler anyway."""
    source = _twin_source()
    assert source.count("CLOUDFLARE_ACCOUNT_ID") == 1, "the header mention, and nothing else"
    assert "require_var" not in source
    assert port.THE_ACCOUNT_ID_IS_DOCUMENTED_AND_UNCHECKED
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 0, old.stderr
    assert "npx\twrangler\tdeploy\n" in old_calls
    _assert_agree(old, new, "no-account-id", old_calls, new_calls)


def test_the_build_runs_before_the_directory_is_checked(tmp_path: pathlib.Path) -> None:
    """DEFECT, REPRODUCED NOT FIXED. There is no guard on `workers/proxy` (the twin's `cd "$WORKER_DIR"`), unlike the `-f` checks both siblings do FIRST, so a missing worker directory costs a full CLI build before bash's own `cd` diagnostic ends the run.

    The divergence in that diagnostic is the usual one: bash prefixes it with the script path and a line number."""
    root = _fixture_root(tmp_path, worker="absent")
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old_calls.count("npm\trun\tbuild") == 2, "both builds ran anyway"
    assert new_calls == old_calls
    tail = port.cd_failed(root / "workers" / "proxy", "No such file or directory")
    assert old.stderr.endswith(tail + "\n")
    assert ": line %d: " % _twin_line('cd "$WORKER_DIR"') in old.stderr
    assert new.stderr.endswith(tail + "\n")
    assert port.THE_BUILD_RUNS_BEFORE_THE_DIRECTORY_IS_CHECKED


def test_a_worker_path_that_is_a_file_says_not_a_directory(tmp_path: pathlib.Path) -> None:
    """THE REASON COMES FROM THE OPERATING SYSTEM, NOT FROM A LITERAL. A port that hard-coded "No such file or directory" would be wrong here, and the only way to notice is to drive the case."""
    root = _fixture_root(tmp_path, worker="file")
    old, new, old_calls, new_calls = run_both(tmp_path, root)
    assert old.returncode == new.returncode == 1
    tail = port.cd_failed(root / "workers" / "proxy", "Not a directory")
    assert old.stderr.endswith(tail + "\n")
    assert new.stderr.endswith(tail + "\n")
    assert new_calls == old_calls


def test_a_failed_first_build_stops_before_the_second(tmp_path: pathlib.Path) -> None:
    """`set -e` on :45. `@rediacc/cli` must NOT be built, and the status is npm's own."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPM_RC="2")
    assert old.returncode == 2
    assert old_calls.count("npm\trun\tbuild") == 1
    assert "@rediacc/cli" not in old_calls
    _assert_agree(old, new, "build-failed", old_calls, new_calls)


def test_a_failed_dry_run_propagates_wranglers_status(tmp_path: pathlib.Path) -> None:
    """`set -e` on :52: the "Dry run passed" line must NOT print."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--dry-run", FAKE_NPX_RC="5")
    assert old.returncode == 5
    assert "Dry run passed" not in old.stderr
    _assert_agree(old, new, "dry-run-failed", old_calls, new_calls)


def test_a_failed_deploy_prints_none_of_the_closing_lines(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_NPX_RC="6")
    assert old.returncode == 6
    for line in port.CLOSING_LINES:
        assert line not in old.stderr
    _assert_agree(old, new, "deploy-failed", old_calls, new_calls)


def test_a_flag_that_is_not_a_shell_identifier_exits_two(tmp_path: pathlib.Path) -> None:
    """`parse_args` IS CALLED HERE (:29), unlike in `deploy-edge.sh`, so a flag bash cannot turn into a variable name kills the run with `printf`'s status before the token is even looked at."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, "--foo.bar", "x")
    assert old.returncode == 2
    assert new.returncode == 2
    assert old.stderr.endswith("printf: `ARG_FOO.BAR': not a valid identifier\n")
    assert (
        new.stderr
        == "rediacc_ci.deploy.deploy_proxy: printf: `ARG_FOO.BAR': not a valid identifier\n"
    )
    assert old_calls == new_calls == ""


# --------------------------------------------------------------------------- Staleness alarms: the port copies six things out of the twin ---------------------------------------------------------------------------


def test_the_literals_are_still_the_twins(tmp_path: pathlib.Path) -> None:
    del tmp_path
    source = _twin_source()
    assert "workers/%s" % port.WORKER_SUBDIR[1] in source
    assert 'REGION="${ARG_REGION:-%s}"' % port.DEFAULT_REGION in source
    assert 'DRY_RUN="${ARG_DRY_RUN:-%s}"' % port.DEFAULT_DRY_RUN in source
    assert '"$DRY_RUN" == "%s"' % port.TRUE in source
    for workspace in port.WORKSPACES:
        assert "npm run build --workspace %s" % workspace in source
    for line in port.CLOSING_LINES:
        assert 'log_info "%s"' % line in source


def test_the_deploy_call_still_carries_no_config_flag(tmp_path: pathlib.Path) -> None:
    """THE DIFFERENCE FROM BOTH SIBLINGS, re-derived rather than remembered.

    The twin names `--config` exactly ONCE, and it is inside the closing `log_info` that tells a human what to paste next -- never on a line this script runs. If a `--config` ever appears on the deploy itself, this fails instead of the port silently deploying a different Worker."""
    del tmp_path
    source = _twin_source()
    assert "npx wrangler deploy\n" in source
    config_lines = [line for line in source.splitlines() if "--config" in line]
    assert config_lines == [
        'log_info "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml"'
    ]
    assert port.deploy_argv() == ["npx", "wrangler", "deploy"]


# --------------------------------------------------------------------------- Renet and the post-deploy smoke (B2, missing test 10) ---------------------------------------------------------------------------


def test_a_real_deploy_stages_the_renet_it_built_for_the_image(tmp_path: pathlib.Path) -> None:
    """B2: THE IMAGE HAD NO RENET. The deploy builds renet at the release version and copies `renet-linux-amd64` to `workers/proxy/renet/`, where the Dockerfile picks it up. Each side is run alone so the staged file is that side's own."""

    def staged_of(root: pathlib.Path) -> str:
        staged = root / "workers" / "proxy" / port.RENET_STAGE / port.RENET_BINARY
        return staged.read_text(encoding="utf-8") if staged.is_file() else ""

    def run_twin():
        side_tmp = tmp_path / "twin"
        root = _fixture_root(side_tmp)
        proc, calls = _run(
            root / ".ci" / "scripts" / "deploy" / TWIN.name,
            side_tmp,
            root,
            (),
            FAKE_VERSION="9.8.7",
        )
        return proc, calls, staged_of(root)

    twin_proc, twin_calls, twin_staged = diff.twin_result(
        TWIN_REL, ["stages renet"], run_twin, work=(str(tmp_path),)
    )
    port_root = _fixture_root(tmp_path / "port")
    port_proc, port_calls = _run(PORT, tmp_path / "port", port_root, (), FAKE_VERSION="9.8.7")
    for proc, calls, staged in (
        (twin_proc, twin_calls, twin_staged),
        (port_proc, port_calls, staged_of(port_root)),
    ):
        assert proc.returncode == 0, proc.stderr
        assert "build-renet.sh\t--version\t9.8.7\n" in calls
        assert staged == "RENET 9.8.7\n"


def test_the_port_stages_an_executable_renet_even_over_a_stale_non_executable_one(
    tmp_path: pathlib.Path,
) -> None:
    """The image's `test -x` guard refused the first Phase 2 deploy: `copyfile` drops the mode, and a stale 0644 stage survives the twin's `cp` too. The port makes the stage executable whatever was there before."""
    root = _fixture_root(tmp_path / "port")
    staged = root / "workers" / "proxy" / port.RENET_STAGE / port.RENET_BINARY
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text("stale\n", encoding="utf-8")
    staged.chmod(0o644)
    proc, _calls = _run(PORT, tmp_path / "port", root, (), FAKE_VERSION="9.8.7")
    assert proc.returncode == 0, proc.stderr
    assert os.access(staged, os.X_OK), oct(staged.stat().st_mode)


def test_a_real_deploy_without_the_licence_key_refuses_before_any_build(
    tmp_path: pathlib.Path,
) -> None:
    """A renet built without ACCOUNT_ED25519_PUBLIC_KEY cannot verify a licence, and the executor uploads its renet to machines. Refused first, so the refusal is cheap."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, drop_env=("ACCOUNT_ED25519_PUBLIC_KEY",)
    )
    assert old.returncode == 1
    assert old.stderr == "✗ %s\n" % port.MISSING_KEY
    assert old_calls == "", "nothing may be built before the key is checked"
    _assert_agree(old, new, "no-licence-key", old_calls, new_calls)


def test_a_dry_run_needs_no_licence_key_and_builds_no_renet(tmp_path: pathlib.Path) -> None:
    """`wrangler deploy --dry-run` never builds the image, so a dry run neither builds renet nor smoke-tests anything."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(
        tmp_path, root, "--dry-run", drop_env=("ACCOUNT_ED25519_PUBLIC_KEY",)
    )
    assert old.returncode == 0, old.stderr
    assert "build-renet.sh" not in old_calls
    assert "resolve-version.sh" not in old_calls
    assert "curl" not in old_calls
    _assert_agree(old, new, "dry-run-no-renet", old_calls, new_calls)


def test_a_failed_renet_build_deploys_nothing(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_RENET_RC="3")
    assert old.returncode == 3
    assert "npx\twrangler\tdeploy" not in old_calls
    _assert_agree(old, new, "renet-build-failed", old_calls, new_calls)


def test_the_smoke_url_is_the_route_wrangler_toml_names(tmp_path: pathlib.Path) -> None:
    """Not the region: the smoke asks the host the deployed config actually serves. The twin's frozen `--region asia` run proves the host never came from the flag; the port now refuses that run, so its side is the default region."""
    root = _fixture_root(tmp_path)
    _old, _new, old_calls, _new_calls = run_both(tmp_path, root, "--region", "asia")
    assert "https://%s/v1/health\n" % SMOKE_HOST in old_calls
    (tmp_path / "port").mkdir()
    new, new_calls = _run(PORT, tmp_path / "port", root, ())
    assert new.returncode == 0, new.stderr
    assert "https://%s/v1/health\n" % SMOKE_HOST in new_calls
    assert (
        port.smoke_host(
            f'routes = [\n  {{ pattern = "{PROXY_EU_HOST}", custom_domain = true }}\n]\n'
        )
        == PROXY_EU_HOST
    )


def test_the_real_wrangler_toml_names_a_route_the_smoke_can_reach(tmp_path: pathlib.Path) -> None:
    del tmp_path
    toml = (ROOT / "workers" / "proxy" / "wrangler.toml").read_text(encoding="utf-8")
    assert port.smoke_host(toml) == PROXY_EU_HOST


def test_an_unhealthy_deploy_fails_the_smoke_and_prints_no_closing_lines(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_HEALTH="503")
    assert old.returncode == 1
    assert "✗ Smoke test failed: /v1/health answered 503, expected 200\n" in old.stderr
    assert "/v1/server-info" not in old_calls, "the second request is not made"
    for line in port.CLOSING_LINES:
        assert line not in old.stderr
    _assert_agree(old, new, "smoke-health", old_calls, new_calls)


def test_an_open_server_info_fails_the_smoke(tmp_path: pathlib.Path) -> None:
    """An unauthenticated `/v1/server-info` that answers 200 means the auth gate is gone, which is the one thing the Worker exists to do."""
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_INFO="200")
    assert old.returncode == 1
    assert (
        "✗ Smoke test failed: an unauthenticated /v1/server-info answered 200, expected 401\n"
        in old.stderr
    )
    _assert_agree(old, new, "smoke-info", old_calls, new_calls)


def test_an_unreachable_proxy_fails_the_smoke_with_curls_own_code(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    old, new, old_calls, new_calls = run_both(tmp_path, root, FAKE_CURL_RC="6")
    assert old.returncode == 1
    assert "curl: (6) Could not resolve host\n" in old.stderr
    assert "✗ Smoke test failed: /v1/health answered 000, expected 200\n" in old.stderr
    _assert_agree(old, new, "smoke-unreachable", old_calls, new_calls)


def test_diagnostics_are_prefixed_with_the_module_name() -> None:
    """The twin's `.sh` is deleted, so the prefix names the module a reader can run and find."""
    assert port.SELF == "rediacc_ci.deploy.deploy_proxy"
    assert port.__name__ == port.SELF


# --------------------------------------------------------------------------- The bench target and its bench-only gate (operator order 2026-10-24) ---------------------------------------------------------------------------

BENCH_TOML = ROOT / "workers" / "proxy" / "wrangler.bench.toml"
BENCH_PROFILE_ENV = {"REDIACC_BWS_PROFILES": "deploy-proxy-bench"}
BENCH_CURL = "curl\t-sS\t-o\t/dev/null\t-w\t%{http_code}\t--max-time\t30\t"


def _bench_root(tmp_path: pathlib.Path, text: str | None = None) -> pathlib.Path:
    """The fixture root plus a `wrangler.bench.toml`: the REAL one unless `text` plants another."""
    root = _fixture_root(tmp_path)
    body = BENCH_TOML.read_text(encoding="utf-8") if text is None else text
    (root / "workers" / "proxy" / "wrangler.bench.toml").write_text(body, encoding="utf-8")
    return root


def _plant(old: str, new: str) -> str:
    text = BENCH_TOML.read_text(encoding="utf-8")
    assert text.count(old) == 1, "the plant's anchor %r must occur exactly once" % old
    return text.replace(old, new)


def test_a_bench_deploy_names_its_config_and_smokes_the_bench_route(tmp_path: pathlib.Path) -> None:
    root = _bench_root(tmp_path)
    proc, calls = _run(PORT, tmp_path, root, ("--target", "bench"), **BENCH_PROFILE_ENV)
    assert proc.returncode == 0, proc.stderr
    assert calls == (
        "npm\trun\tbuild\t--workspace\t@rediacc/shared\n"
        "  cwd=root\n"
        "npm\trun\tbuild\t--workspace\t@rediacc/cli\n"
        "  cwd=root\n"
        "resolve-version.sh\t--current\n"
        "  cwd=proxy\n"
        "build-renet.sh\t--version\t1.2.3\n"
        "  cwd=proxy\n"
        "npx\twrangler\tdeploy\t--config\twrangler.bench.toml\n"
        "  cwd=proxy\n"
        f"{BENCH_CURL}https://{PROXY_BENCH_HOST}/v1/health\n"
        f"{BENCH_CURL}https://{PROXY_BENCH_HOST}/v1/server-info\n"
    )
    assert "(config: wrangler.bench.toml)" in proc.stderr
    assert "(region: eu)" not in proc.stderr
    for line in port.BENCH_CLOSING_LINES:
        assert "✓ %s\n" % line in proc.stderr
    assert "--config workers/proxy/wrangler.toml" not in proc.stderr


def test_a_bench_dry_run_names_its_config(tmp_path: pathlib.Path) -> None:
    root = _bench_root(tmp_path)
    proc, calls = _run(
        PORT, tmp_path, root, ("--target", "bench", "--dry-run"), **BENCH_PROFILE_ENV
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        "npx\twrangler\tdeploy\t--dry-run\t--outdir\t%s\t--config\twrangler.bench.toml\n"
        % port.DRY_RUN_OUTDIR
        in calls
    )
    assert "curl" not in calls
    assert "build-renet.sh" not in calls


def test_the_real_bench_config_passes_the_bench_gate() -> None:
    text = BENCH_TOML.read_text(encoding="utf-8")
    assert port.bench_refusals(text) == []
    assert port.smoke_host(text) == port.BENCH_ROUTE == PROXY_BENCH_HOST


def test_the_eu_config_is_refused_as_a_bench_config() -> None:
    """The control in the other direction: the eu file, handed to the bench gate, fails on every name."""
    reasons = port.bench_refusals((ROOT / "workers" / "proxy" / "wrangler.toml").read_text())
    joined = "\n".join(reasons)
    for fragment in ("rediacc-proxy-eu", PROXY_EU_HOST, ACCOUNT_DEFAULT_ORIGIN):
        assert fragment in joined
    assert "rediacc-account-eu" in joined


BENCH_PLANTS = (
    (
        "account-url-eu",
        (
            f'ACCOUNT_URL = "{BENCH_ORIGIN}"',
            f'ACCOUNT_URL = "{ACCOUNT_DEFAULT_ORIGIN}"',
        ),
        f"vars.ACCOUNT_URL is '{ACCOUNT_DEFAULT_ORIGIN}'",
    ),
    (
        "account-url-suffix",
        (
            f'ACCOUNT_URL = "{BENCH_ORIGIN}"',
            f'ACCOUNT_URL = "{BENCH_ORIGIN}/x"',
        ),
        f"vars.ACCOUNT_URL is '{BENCH_ORIGIN}/x'",
    ),
    (
        "binding-eu",
        ('service = "rediacc-account-bench"', 'service = "rediacc-account-eu"'),
        "the ACCOUNT service binding is ['rediacc-account-eu']",
    ),
    (
        "route-eu",
        (f'pattern = "{PROXY_BENCH_HOST}"', f'pattern = "{PROXY_EU_HOST}"'),
        f"route '{PROXY_EU_HOST}' names eu",
    ),
    (
        "route-production",
        (f'pattern = "{PROXY_BENCH_HOST}"', 'pattern = "proxy.rediacc.com"'),
        "routes are ['proxy.rediacc.com']",
    ),
    (
        "name-eu",
        ('name = "rediacc-proxy-bench"', 'name = "rediacc-proxy-eu"'),
        "name 'rediacc-proxy-eu' names eu",
    ),
    (
        "name-production",
        ('name = "rediacc-proxy-bench"', 'name = "rediacc-proxy-production"'),
        "name 'rediacc-proxy-production' names production",
    ),
    (
        "env-table",
        ("[observability]\n", '[env.production]\nname = "rediacc-proxy"\n\n[observability]\n'),
        "an [env.*] table",
    ),
    (
        "second-service",
        (
            'service = "rediacc-account-bench"',
            'service = "rediacc-account-bench"\n\n[[services]]\nbinding = "WWW"\nservice = "rediacc-www"',
        ),
        "[[services]] binds 'rediacc-www'",
    ),
)


@pytest.mark.parametrize(
    ("label", "plant", "fragment"), BENCH_PLANTS, ids=[p[0] for p in BENCH_PLANTS]
)
def test_a_bench_config_that_names_anything_but_bench_refuses_before_any_build(
    tmp_path: pathlib.Path, label: str, plant: tuple[str, str], fragment: str
) -> None:
    """Each plant refuses with exit 1, no stdout and an empty call log, WITH NO TOKEN AND NO PROFILE: the gate runs before both, so a config that reaches eu or production is never handed credentials."""
    del label
    root = _bench_root(tmp_path, _plant(*plant))
    proc, calls = _run(
        PORT, tmp_path, root, ("--target", "bench"), drop_env=("CLOUDFLARE_API_TOKEN",)
    )
    assert proc.returncode == 1, proc.stderr
    assert proc.stdout == ""
    assert calls == ""
    lines = proc.stderr.splitlines()
    assert lines, "a refusal names its reason"
    assert all(line.startswith("✗ --target bench refused: ") for line in lines), (
        "nothing may run after the gate, not even the profile re-exec: %r" % proc.stderr
    )
    assert fragment in proc.stderr, proc.stderr


def test_a_missing_bench_config_refuses_before_any_build(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(PORT, tmp_path, root, ("--target", "bench"))
    assert proc.returncode == 1
    assert calls == ""
    assert proc.stderr.startswith(
        "✗ --target bench refused: workers/proxy/wrangler.bench.toml cannot be read"
    )
    assert proc.stderr.count("\n") == 1, proc.stderr


def test_an_unparsable_bench_config_refuses(tmp_path: pathlib.Path) -> None:
    root = _bench_root(tmp_path, "name = \n")
    proc, calls = _run(PORT, tmp_path, root, ("--target", "bench"))
    assert proc.returncode == 1
    assert calls == ""
    assert proc.stderr.startswith(
        "✗ --target bench refused: workers/proxy/wrangler.bench.toml does not parse as TOML"
    )
    assert proc.stderr.count("\n") == 1, proc.stderr


def test_an_unknown_target_refuses_before_any_build(tmp_path: pathlib.Path) -> None:
    root = _bench_root(tmp_path)
    proc, calls = _run(PORT, tmp_path, root, ("--target", "production"))
    assert proc.returncode == 1
    assert proc.stderr == "✗ %s\n" % port.target_refusal("production")
    assert calls == ""


def test_an_explicit_eu_target_deploys_exactly_as_the_default(tmp_path: pathlib.Path) -> None:
    """`--target eu` is the twin's run, byte for byte: no `--config`, wrangler.toml's route, the eu closing lines."""
    root = _bench_root(tmp_path)
    for side in ("d", "e"):
        (tmp_path / side).mkdir()
    default, default_calls = _run(PORT, tmp_path / "d", root, ())
    explicit, explicit_calls = _run(PORT, tmp_path / "e", root, ("--target", "eu"))
    assert explicit.returncode == 0, explicit.stderr
    assert explicit.stderr == default.stderr == DEPLOY_STDERR
    assert explicit_calls == default_calls != ""
    assert "--config" not in default_calls


def test_a_bench_run_without_its_profile_reexecutes_under_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbound, the run hands itself to `bws_env exec --profile deploy-proxy-bench` and returns that child's status; nothing else runs in this process."""
    root = _bench_root(tmp_path)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    seen: list[tuple[list[str], dict | None]] = []

    def fake_run(argv: list[str], *, env: dict | None = None) -> int:
        seen.append((argv, env))
        return 7

    monkeypatch.setattr(port, "_run", fake_run)
    assert port.main(["--target", "bench"]) == 7
    assert len(seen) == 1
    argv, env = seen[0]
    assert argv == port.reexec_argv(["--target", "bench"])
    assert argv[1:7] == [
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        "deploy-proxy-bench",
        "--",
    ]
    assert argv[-4:] == ["-m", "rediacc_ci.deploy.deploy_proxy", "--target", "bench"]
    assert env is not None
    assert env["PYTHONPATH"].split(os.pathsep)[0] == port.PACKAGE_PARENT


def test_the_bench_profile_binds_the_dev_public_key_and_the_workers_token() -> None:
    """Bench signs licences with the DEV keypair, so the image's renet must verify with the DEV public key, under the name the build reads."""
    spec = json.loads((ROOT / ".ci" / "config" / "secret-supply.json").read_text(encoding="utf-8"))
    profile = spec["consumers"][port.BENCH_PROFILE]
    assert set(profile["required"]) == {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ACCOUNT_ED25519_PUBLIC_KEY_DEV > ACCOUNT_ED25519_PUBLIC_KEY",
    }


# --------------------------------------------------------------------------- The smoke survives a fresh domain's cached NXDOMAIN ---------------------------------------------------------------------------


def _clock(monkeypatch, ticks: list[float]) -> None:
    """Replace the module's `time` with a scripted monotonic clock, so the retry window is exact."""
    monkeypatch.setenv(port.RESOLVE_WINDOW_ENV, "50")
    monkeypatch.setattr(
        port, "time", types.SimpleNamespace(monotonic=iter(ticks).__next__, sleep=lambda _s: None)
    )


class _Curl:
    """A scripted `_curl`: answers per call, in order, as (code, rc); the last repeats. Records (url, pin)."""

    def __init__(self, answers: list[tuple[str, int]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, url: str, pin: str | None = None) -> tuple[str, int]:
        self.calls.append((url, pin))
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def _smoke_fixture(tmp_path: pathlib.Path, monkeypatch, answers, doh=None):
    (tmp_path / port.EU_CONFIG).write_text(
        'routes = [{ pattern = "proxy.test.example", custom_domain = true }]\n', encoding="utf-8"
    )
    fake = _Curl(answers)
    sleeps: list[float] = []
    monkeypatch.setattr(port, "_curl", fake)
    monkeypatch.setattr(port, "_sleep", sleeps.append)
    monkeypatch.setattr(port, "_doh_lookup", lambda _host: doh)
    monkeypatch.setenv(port.RESOLVE_WINDOW_ENV, "1000")
    monkeypatch.setenv(port.DOH_URL_ENV, "https://doh.invalid/dns-query")
    return fake, sleeps


def test_nxdomain_then_ok_passes_without_a_pin(tmp_path, monkeypatch) -> None:
    fake, sleeps = _smoke_fixture(tmp_path, monkeypatch, [("000", 6), ("200", 0), ("401", 0)])
    assert port.smoke(tmp_path) == 0
    assert [pin for _, pin in fake.calls] == [None, None, None]
    assert sleeps == [port.RESOLVE_INTERVAL_S]


def test_persistent_nxdomain_with_a_doh_answer_passes_through_a_pin(tmp_path, monkeypatch) -> None:
    fake, _ = _smoke_fixture(
        tmp_path, monkeypatch, [("000", 6), ("200", 0), ("401", 0)], doh="203.0.113.7"
    )
    _clock(monkeypatch, [0.0, 100.0, 200.0])
    assert port.smoke(tmp_path) == 0
    assert [pin for _, pin in fake.calls] == [None, "203.0.113.7", "203.0.113.7"]
    url = "https://proxy.test.example/v1/health"
    assert port.curl_argv(url, "203.0.113.7")[-3:] == [
        "--resolve",
        "proxy.test.example:443:203.0.113.7",
        url,
    ]
    assert port.curl_argv(url)[-1] == url
    assert "--resolve" not in port.curl_argv(url)


def test_a_500_fails_at_once_without_retry(tmp_path, monkeypatch, capsys) -> None:
    fake, sleeps = _smoke_fixture(tmp_path, monkeypatch, [("500", 0)])
    assert port.smoke(tmp_path) == 1
    assert len(fake.calls) == 1
    assert sleeps == []
    assert "/v1/health answered 500, expected 200" in capsys.readouterr().err


def test_persistent_resolution_failure_fails_with_a_clear_message(
    tmp_path, monkeypatch, capsys
) -> None:
    _smoke_fixture(tmp_path, monkeypatch, [("000", 6)], doh=None)
    _clock(monkeypatch, [0.0, 100.0])
    assert port.smoke(tmp_path) == 1
    err = capsys.readouterr().err
    assert "does not resolve locally" in err
    assert "DNS-over-HTTPS has no answer" in err
    assert "answered 000, expected 200" in err


def test_the_doh_lookup_reads_the_first_a_record(monkeypatch) -> None:
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"Answer": [{"type": 5, "data": "x."}, {"type": 1, "data": "198.51.100.9"}]}
            ).encode()

    seen = {}

    def fake_open(request, **_kw):
        seen["url"] = request.full_url
        return Resp()

    monkeypatch.setattr(port.https, "urlopen", fake_open)
    monkeypatch.delenv(port.DOH_URL_ENV, raising=False)
    assert port._doh_lookup("proxy.test.example") == "198.51.100.9"
    assert "name=proxy.test.example" in seen["url"]
