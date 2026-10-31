#!/usr/bin/env python3
"""block-host-toolchain-run.sh: both directions.

The interesting half is the ALLOW half. A guard that pushes every `npm run` into a container would be routed around within a day: most gates are node and TypeScript, run identically on the host, and are faster there. This one fires only when the named gate needs a binary THIS host lacks.

PATH is manipulated per case rather than mocked, so "the host lacks it" is a fact the guard establishes with `command -v`, exactly as it does in the wild.
"""

import atexit
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks import guards

# THIS HARNESS SITS BESIDE ITS GUARD, which is what .ci/scripts/quality/check-hook-integrity.sh means by a dedicated test file: `test-<stem>.py` next to `<stem>.py` credits the guard with BOTH directions, and it is the only credit these four have because their block direction needs fixture work `test-hooks.sh`'s one-line `check` helper cannot express.
#
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it from a bash original that PLAN-retire-bash-oracles A3 later deleted, once the differential compared the two byte for byte and froze the result as a golden (tests/goldens/<stem>.jsonl). This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked.
DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_host_toolchain_run"]
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

# ONE PARENT DIRECTORY PER RUN, STAMPED WITH THE PID, and a sweep of every parent whose process is gone: `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop, which test_canonical_sys_path_hop.py freezes; it is stdlib-only for exactly this reason. `atexit` does not run when the harness kills a run on its timeout, and each `_path_without` shim was ~6,500 symlinks on a WSL host (its PATH carries every Windows executable under /mnt/c): 81 leaked shims held 538,000 of /tmp's 1,048,576 inodes on 2026-09-24 and Bash could no longer write its own output.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(REPO) / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)

RUN_TMP = runtmp.run_dir("hostguard-test-")

# A PATH with the real tools plus a shim dir we control.
shim = tempfile.mkdtemp(dir=RUN_TMP)
# Every temp directory here is registered for removal the moment it exists, because the explicit rmtree calls further down only run when the suite reaches them, and `_path_without` below is called once per stripped tool with no cleanup at all: ten directories leaked per run before this.
atexit.register(shutil.rmtree, shim, ignore_errors=True)


def fake(name):
    p = os.path.join(shim, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    # 0o700, not 0o755: the shim only has to be executable by THIS process, and mkdtemp() already made the parent owner-only, so the group/other bits were unreachable decoration.
    os.chmod(p, 0o700)


# EVERY CASE STARTS WITHOUT `AWS_BIN`. The guard asks the aws resolver's rungs (`AWS_BIN`, PATH, then the pinned repo cache), so an ambient `AWS_BIN` from a CI job or an operator's shell would decide the aws cases instead of the PATH each case constructs. A case that needs it passes it in `extra`.
def _case_env(path, extra):
    env = dict(os.environ)
    env.pop("AWS_BIN", None)
    if path is not None:
        env["PATH"] = path
    if extra:
        env.update(extra)
    return env


def run(cmd, path=None, extra=None):
    env = _case_env(path, extra)
    return subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    ).returncode


def run_full(cmd, path=None, extra=None):
    env = _case_env(path, extra)
    return subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


REAL = os.environ.get("PATH", "")
WITH_SHIM = f"{shim}:{REAL}"


# EVERY OTHER TOOL THIS TEST OR THE GUARD ITSELF NEEDS must stay resolvable through a "host lacks <tool>" PATH strip below, even when the excluded tool's own directory ALSO resolves one of them. Measured live, 2026-09-23, on this exact devbox image: `bash`, `docker` AND `shellcheck` all resolve to `/usr/bin`. A strip keyed only on "does this dir contain <tool>" removes the whole directory,
# which silently took `bash` out from under `subprocess.run(["bash", GUARD])` the first time this was hit, and, on a subtler path, took `docker` out from under the GUARD ITSELF the second time: the guard's own "is a devbox running" check shells out to `docker ps`, so stripping `/usr/bin` to hide `shellcheck` also hid `docker`, which made the guard report "no devbox" and fall back to its
# note-only branch instead of routing -- the exact shape of a false negative this constructed-absence design exists to prevent, just aimed at the guard's OWN toolchain rather than the one under test.
# The fix generalizes past bash specifically: `_path_without` below builds ONE shim directory holding a symlink to every real, resolvable executable found anywhere on `base`, EXCEPT the one being hidden, and uses that shim as the entire replacement PATH. Nothing that already resolved on `base` can stop resolving as a side effect of hiding an unrelated name, because every other name got its own
# symlink rather than inheriting its directory's fate.
def _path_without(tool, base):
    """A single shim directory symlinking every real, resolvable executable found on `base`, except `tool` -- replacing `base` entirely rather than filtering its directories.

    First `base` directory to offer a given name wins, matching normal PATH resolution order, so a name shadowed further down `base` stays shadowed here too.
    """
    shim_dir = tempfile.mkdtemp(dir=RUN_TMP)
    seen = set()
    for directory in base.split(os.pathsep):
        # WSL interop mounts (/mnt/c/Windows, ...) hold thousands of Windows executables and none of the tools this guard routes.
        if not directory or directory.startswith("/mnt/") or not os.path.isdir(directory):
            continue
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            if name == tool or name in seen:
                continue
            src = os.path.join(directory, name)
            if not os.path.isfile(src):
                continue
            try:
                os.symlink(src, os.path.join(shim_dir, name))
            except OSError:
                continue
            seen.add(name)
    return shim_dir


# Does a devbox exist? The refusal arm requires one; without it the guard correctly downgrades to a note, and asserting exit 2 would be asserting the wrong thing on a machine with no container.
box_name = subprocess.run(
    ["docker", "ps", "--filter", "label=com.rediacc.devbox.worktree", "--format", "{{.Names}}"],
    capture_output=True,
    text=True,
    check=False,
).stdout.strip()
have_box = box_name != ""

cases = []

# --- ALLOW: the half that decides whether this guard survives ---------------
cases.append(
    (0, run("npm run check:ci-parity"), "CONTROL: a gate needing no extra toolchain is untouched")
)
cases.append((0, run("npm run build:packages"), "CONTROL: an ordinary npm script is untouched"))
cases.append((0, run("git status"), "CONTROL: a non-npm command is out of scope"))
cases.append(
    (
        0,
        run("./run.sh devbox exec -- npm run check:ci-python-lint"),
        "CONTROL: already routed through the devbox is out of scope",
    )
)
cases.append(
    (
        0,
        run("echo 'run npm run check:ci-renet in the box'"),
        "CONTROL: prose about the command is not the command",
    )
)

# The host HAS the tool -> never route. Proven by shimming one onto PATH.
fake("ruff")
cases.append(
    (
        0,
        run("npm run check:ci-python-lint", WITH_SHIM),
        "CONTROL: host HAS ruff, so the guard leaves it alone",
    )
)

# A GATE THAT PROVISIONS ITS OWN PINNED TOOL MUST NEVER BE ROUTED. Three of the table's original six entries were this mistake, so it is pinned rather than remembered. These run with the REAL host PATH: if either tool is absent here (it is, on this host) the old table refused the command outright,
# while the gate itself acquires its pin and passes.
cases.extend(
    (
        0,
        run(f"npm run {gate}", REAL),
        f"CONTROL: {gate} self-provisions its pin, so it is never routed",
    )
    for gate in ("check:ci-shell-lint", "check:ci-shell-format", "check:ci-actionlint")
)

# --- REFUSE: only when the host lacks it and the box has it -----------------
if have_box:
    # Strip the shim so ruff is absent again; the real host has no ruff.
    if shutil.which("ruff", path=REAL) is None:
        cases.append(
            (
                2,
                run("npm run check:ci-python-lint", REAL),
                "host lacks ruff and the devbox has it -> REFUSED with the devbox form",
            )
        )
    else:
        cases.append(
            (
                0,
                run("npm run check:ci-python-lint", REAL),
                "CONTROL: this host actually has ruff, so no routing is correct",
            )
        )
else:
    cases.append(
        (
            0,
            run("npm run check:ci-python-lint", REAL),
            "CONTROL: no devbox running, so the guard notes rather than blocks",
        )
    )

# --- BARE TOOL: the same class, for a directly-typed command ---------------- The NEEDS table above matches a GATE KEY string in the command (`check:ci-python-lint`); it is blind to `go build ./...`, which names no gate at all. BARE_TOOLS exists to catch exactly that shape. Constructed rather than ambient: whether THIS host happens to have `go` on PATH must not decide which branch
# of the guard gets exercised. Strip every PATH entry that actually resolves `go`, so the REFUSE branch runs deterministically instead of silently degrading to a no-op CONTROL assertion on a host that has go (which is exactly what happened the first time this case was written: it passed while testing nothing, because `go` was on this host's PATH the whole time).
NOGO = _path_without("go", REAL)
if have_box:
    r = run_full("go build ./...", NOGO)
    cases.append((2, r.returncode, "bare 'go', host lacks it, devbox has it -> REFUSED"))
    cases.append(
        (
            True,
            "this command needs 'go'" in r.stderr and "gate 'go' needs" not in r.stderr,
            "bare-tool message reads 'this command needs', not 'gate <tool> needs'",
        )
    )
    cases.append(
        (
            True,
            "npm run go" not in r.stderr,
            "bare-tool routing never suggests the nonsensical 'npm run go'",
        )
    )
    cases.append((0, run("go build ./...", REAL), "CONTROL: with go restored to PATH, no routing"))
else:
    cases.append(
        (0, run("go build ./...", NOGO), "CONTROL: no devbox running, bare tool notes not blocks")
    )

# Prose mentioning a tracked tool name must never be mistaken for running it.
cases.append(
    (
        0,
        run('git commit -m "install ruff and go before running this"', REAL),
        "CONTROL: prose naming tool words is not a command",
    )
)

# --- NPX MISUSE: fires on shape, independent of host tool state ------------- npx resolves its argument as an npm package name; none of ruff/go/shfmt/ shellcheck/actionlint are npm packages, so this fails whether or not the tool is on PATH. Measured 2026-08-28: this exact shape, with ruff genuinely present on PATH the whole time.
cases.append(
    (2, run("npx --yes ruff format file.py", REAL), "npx cannot run a pinned non-npm tool")
)
cases.append((2, run("npx -y shfmt -l .", REAL), "npx misuse, short flag form"))
# #0c331972: the npx arm reads npm's own option grammar (shellscan._launches); it used to skip only -y/--yes, so both shapes below were allowed (rc 0, measured 2026-10-11 at 306285231).
cases.append(
    (2, run("npx --logl silent --yes ruff check", REAL), "npx misuse behind a value option")
)
cases.append((2, run("npm x -y ruff check", REAL), "npx misuse through the npm x alias"))
cases.append(
    (0, run("npx -c 'ruff check a.py'", REAL), "CONTROL: npx -c runs a shell, not a package")
)
cases.append((0, run("echo 'npm x -y ruff check'", REAL), "CONTROL: prose naming npm x ruff"))
cases.append(
    (0, run("npx --yes tsx scripts/foo.ts", REAL), "CONTROL: npx running a real npm package")
)
# #503f0ba8: an `npx <tool>` that `find -exec` launches is the same misuse, judged on `shellscan.every_run`; the base allowed it (rc 0, measured 2026-10-09).
cases.append(
    (
        2,
        run("find . -name '*.py' -exec npx ruff format {} +", REAL),
        "npx misuse launched by find -exec",
    )
)
cases.append(
    (
        0,
        run("echo find . -name x -exec npx ruff format {} +", REAL),
        "CONTROL: prose naming a find -exec npx run",
    )
)

# --------------------------------------------------------------------------- Submodule / non-submodule split, and the credential file. Both added 2026-08-28 after each failed for real.
#
# The property that decides routing is NOT "is this a submodule". It is whether the target owns a HOST-BUILT toolchain. private/renet is a submodule with neither a .venv nor node_modules, so it routes like the root repo. private/account is a submodule WITH node_modules, and private/growth/video_pipeline is not a submodule at all but carries its own .venv; neither can run in the
# container. Routing video_pipeline into the devbox produced ModuleNotFoundError: anyio. THE ROOT-REPO EXPECTATION IS DERIVED, NEVER HARDCODED. This case asserted a literal 2 for private/renet and went red on 2026-08-28 the moment `ruff` was installed on this host -- the guard then correctly declined to route, exactly as its own comment says it should ("THE HOST IS ASKED, NOT
# ASSUMED").
#
# The property under test is the one the section header states: a submodule with no host toolchain routes LIKE THE ROOT REPO. So compare it to the root repo's verdict rather than to a constant, which holds in both worlds and keeps the
# case meaningful on a machine that has ruff and on one that does not.
#
# SAME CLASS AS wl_git.py's force-push probe trio, found the same day: a control whose expectation was pinned to ambient machine state (there, a branch name
# from an earlier wave). Neither went green and lied -- both went RED for a
# reason unrelated to what they assert, which is worse, because a red nobody can explain is a red everybody learns to ignore.
_root_like = 2 if (have_box and shutil.which("ruff", path=REAL) is None) else 0
if have_box:
    for path, want, why in (
        ("private/growth/video_pipeline", 0, "a pipeline with its own .venv must NOT be routed"),
        ("private/account", 0, "a submodule with host-built node_modules must NOT be routed"),
        (
            "private/renet",
            _root_like,
            "a submodule with no host toolchain routes like the root repo (expected %d here)"
            % _root_like,
        ),
    ):
        if not os.path.exists(os.path.join(REPO, path)):
            continue
        cases.append((want, run(f"npm run check:ci-python-lint --prefix {path}", REAL), why))

# A command that uploads to R2 without its credentials does not fail, it half-succeeds: 52 files copied locally, 0 uploaded, exit 0, and a closing warning that named the wrong cause. The credentials come from Bitwarden through `bws_env exec --profile publish-media` (PLAN-account-env-to-bws). Only asserted where the account submodule is checked out, since the guard is deliberately silent without it.
if os.path.exists(os.path.join(REPO, "private/account/package.json")):
    cases.append(
        (
            2,
            run("./run.sh --publish-www --langs en", REAL),
            "publish-www without the publish-media profile is refused",
        )
    )
    cases.append(
        (
            0,
            run(
                "PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile publish-media"
                " -- ./run.sh --publish-www --langs en",
                REAL,
            ),
            # THE FORM THIS GUARD ADVISES. Pinned here because the message and the predicate are in different functions and nothing else holds them together: a guard that recommends a command it then blocks is worse than one that recommends nothing.
            "CONTROL: the form the message advises is accepted",
        )
    )
    cases.append(
        (
            2,
            run("set -a; . private/account/.env; set +a; ./run.sh --publish-www --langs en", REAL),
            "the retired env-file form no longer counts as carrying the credentials",
        )
    )
    cases.append(
        (
            0,
            run("CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=x ./run.sh --publish-www --langs en", REAL),
            "CONTROL: setting the credential inline states the intent, so it is accepted",
        )
    )
    # THE REPORTED FALSE POSITIVE (agent/plans/PLAN-fix-is-invoked-sh-alternation.md): two `.sh` paths handed to grep, the second a NEEDS_ENV key. The old pattern read `run.sh`'s trailing `sh` as an interpreter and the next path as its script. Paired with `./run.sh --publish-www` above, which the SAME suffix match was the only thing catching, so neither direction can regress alone.
    cases.append(
        (
            0,
            run("grep -n R2 run.sh .ci/media/tools/upload-r2.sh", REAL),
            "CONTROL: two .sh paths handed to grep run neither",
        )
    )
    cases.append(
        (
            2,
            run("cd . && ./run.sh --publish-www --langs en", REAL),
            "a command after a separator still runs the key",
        )
    )
    # THE PYTHON PORT OF THE SAME UPLOAD, by module. aws is put on PATH so the toolchain arm cannot be what refuses: the refusal has to be the credential one, and the control has to clear both.
    _aws_dir = tempfile.mkdtemp(dir=RUN_TMP)
    with open(os.path.join(_aws_dir, "aws"), "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.chmod(os.path.join(_aws_dir, "aws"), 0o700)
    _port = run_full(
        "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.sync_media_to_r2", f"{_aws_dir}:{REAL}"
    )
    cases.append(
        (
            2,
            _port.returncode,
            "python -m: the sync-media-to-r2 port without the publish-media profile is refused",
        )
    )
    cases.append(
        (
            True,
            "--profile publish-media" in _port.stderr,
            "python -m: the port's refusal is the credential one",
        )
    )
    cases.append(
        (
            0,
            run(
                "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=x PYTHONPATH=.ci python3 -m"
                " rediacc_ci.deploy.sync_media_from_r2",
                f"{_aws_dir}:{REAL}",
            ),
            "CONTROL: python -m: the sync-media-from-r2 port with the credential inline is accepted",
        )
    )

# --------------------------------------------------------------------------- EVERY TOOL IN THE ARRAY, NOT JUST TWO OF FIVE. check-host-toolchain-coverage.sh proves NPX_TOOLS/BARE_TOOLS LIST the same tools GATED_TOOLS pins; it says nothing about whether the ROUTING REGEX actually FIRES for each of them at runtime. A tool could sit in the array and still be unreachable -- a name
# containing a regex metacharacter, a word-boundary edge case on a two-letter name like `go` -- and list-membership coverage would not catch it. Before this, npx-misuse was exercised for ruff and shfmt only, and bare-tool routing
# for ruff and go only: 2 of 5 tools on each path, with shellcheck, actionlint
# (both paths) and go/shfmt (npx path) never actually invoked.
#
# PATH is constructed per tool, never trusted to ambient host state: this host happens to lack shfmt/shellcheck/actionlint and have ruff/go, and a case written against today's ambient mix silently stops testing the branch it names the moment the host's toolset changes.
ALL_TOOLS = ["ruff", "go", "shfmt", "shellcheck", "actionlint"]


for tool in ALL_TOOLS:
    # npx-misuse: fires on SHAPE alone, so REAL PATH is the right environment -- it must refuse whether or not the tool happens to be installed.
    cases.append(
        (
            2,
            run(f"npx --yes {tool} --version", REAL),
            f"npx-misuse: {tool} refused regardless of host state",
        )
    )

    if not have_box:
        continue
    # Bare-tool routing, host lacks it, devbox has it: constructed absence, not assumed. `fake()` proves the opposite direction: with the tool shimmed onto PATH, the same command must NOT be routed.
    #
    # DEVBOX PRESENCE IS CHECKED, NOT ASSUMED, per tool. actionlint is DELIBERATELY absent from the baked image (its own gate downloads a pinned, checksum-verified release on demand -- see this guard's own comment on why it is not in NEEDS either), so on a host that also lacks it the guard correctly NOTES rather than blocks: there is nowhere to route TO. Hardcoding "devbox has it"
    # for every tool would have made this
    # case assert the wrong exit code for exactly the one tool the image
    # intentionally does not carry.
    tool_in_box = (
        subprocess.run(
            ["docker", "exec", "-u", "vscode", box_name, "bash", "-lc", f"command -v {tool}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    without = _path_without(tool, REAL)
    want = 2 if tool_in_box else 0
    label = (
        f"bare-tool: {tool} routed when constructed-absent from PATH"
        if tool_in_box
        else f"bare-tool: {tool} absent from host AND devbox -> notes, does not route"
    )
    cases.append((want, run(f"{tool} --version", without), label))
    fake(tool)
    with_shim = f"{shim}:{REAL}"
    cases.append(
        (0, run(f"{tool} --version", with_shim), f"CONTROL: {tool} present on PATH is left alone")
    )

# --------------------------------------------------------------------------- aws, bw, bws -- the three the tables did not cover until 2026-09-23.
#
# THE INCIDENT. A session ran `.ci/scripts/release/assert-edge-tag-exists.sh` on the HOST, read `Required command 'aws' is not available`, and began evaluating an `awscli` install on the host. The devbox has carried aws-cli 2.36.40 the whole time.
# Neither NEEDS nor BARE_TOOLS could see that command: it names no gate key, and `aws` appears nowhere in it -- the script reaches the binary from inside itself. NEEDS_SCRIPT is what closes that, and these cases are what stop it closing again.
#
# `aws` IS THE ONE THAT ROUTES HERE AND `bw`/`bws` ARE THE ONES THAT MUST NOT. Measured on this host: no aws, but `bw` and `bws` are both at /home/developer/.local/bin.
# So the same three-entry addition exercises both directions of "THE HOST IS ASKED, NOT ASSUMED" without a single constructed absence, and the loop below constructs the absence anyway, for the same reason the ALL_TOOLS loop does: whether this host happens to carry a tool must never decide which branch a case exercises.
AWS_ABSENT = _path_without("aws", REAL)
# PATH ALONE NO LONGER MAKES aws ABSENT. A host carrying the pinned cache `.ci/cache/toolchain/aws-cli/<AWSCLI_VERSION>/bin/aws` has aws as far as the resolver (and so the guard) is concerned, and this checkout may carry one. A set `AWS_BIN` that is not an executable file is the resolver's refusal and the guard's absence, and it is consulted before the cache, so it is what makes "host lacks aws" true here.
AWS_GONE = {"AWS_BIN": os.path.join(RUN_TMP, "no-such-aws")}


def _in_box(tool):
    """Does the running devbox resolve `tool`? Asked, never assumed."""
    if not have_box:
        return False
    return (
        subprocess.run(
            ["docker", "exec", "-u", "vscode", box_name, "bash", "-lc", f"command -v {tool}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


aws_in_box = _in_box("aws")

if aws_in_box:
    # The gate-key arm: check:ci-release-state require_cmd's aws up front and fails without it, which is the entry test NEEDS documents and three of its original six failed.
    cases.append(
        (
            2,
            run("npm run check:ci-release-state", AWS_ABSENT, AWS_GONE),
            "gate key: check:ci-release-state needs aws, host lacks it -> REFUSED",
        )
    )
    # The release entry's row, through the process: refused on a host without aws and routed as the npm script it is.
    r = run_full("npm run release:local -- --channel edge --dry-run", AWS_ABSENT, AWS_GONE)
    cases.append((2, r.returncode, "gate key: release:local needs aws, host lacks it -> REFUSED"))
    cases.append(
        (
            True,
            "gate 'release:local' needs 'aws'" in r.stderr
            and "devbox exec -- npm run release:local" in r.stderr,
            "gate key: release:local is named and routed as its npm script",
        )
    )

    # The NEEDS_SCRIPT arm, on the incident command as it is spelled now: the script was ported to `rediacc_ci.release.assert_edge_tag_exists` and deleted, so the module is what a session runs. THREE ASSERTIONS, not one. The exit code says it was refused; the other two say it was refused with advice a reader can act on.
    # `bare` is set True by the NEEDS_SCRIPT loop precisely so this message does not read "gate '<key>'" and then suggest `npm run <key>`, which is not a command that exists.
    r = run_full(
        "PYTHONPATH=.ci python3 -m rediacc_ci.release.assert_edge_tag_exists --version 1.3.0",
        AWS_ABSENT,
        AWS_GONE,
    )
    cases.append((2, r.returncode, "NEEDS_SCRIPT: the incident command itself is REFUSED"))
    cases.append(
        (
            True,
            "this command needs 'aws'" in r.stderr,
            "NEEDS_SCRIPT message reads 'this command needs', not 'gate <script> needs'",
        )
    )
    cases.append(
        (
            True,
            "npm run rediacc_ci." not in r.stderr,
            "NEEDS_SCRIPT routing never suggests the nonsensical 'npm run <module>'",
        )
    )

    # READING A SCRIPT IS NOT RUNNING IT, and this is the exact bug class `_is_invoked` was built for: `grep -n assets/videos .ci/scripts/deploy/sync-media-to-r2.sh` (a script since deleted) was once refused with a message about credentials a grep does not need.
    # Every NEEDS_SCRIPT key is a path a session has a real reason to open, so the regression is re-asserted for the new table rather than inherited from the old one.
    cases.extend(
        (
            0,
            run(reader, AWS_ABSENT, AWS_GONE),
            f"CONTROL: reading a NEEDS_SCRIPT path is not running it -- {reader.split()[0]}",
        )
        for reader in (
            "grep -n TODO .ci/rediacc_ci/release/assert_edge_tag_exists.py",
            "sed -n 1,5p .ci/media/tools/upload-r2.sh",
            "cat .ci/rediacc_ci/housekeeping/cleanup_versions.py",
        )
    )

    # THE TWO TABLES COMPOSE, IN THIS ORDER. The sync_media_to_r2 module is in NEEDS_ENV as well, so satisfying the credential arm must not satisfy the toolchain one: the credentials being in the shell says nothing about whether aws is on PATH.
    # The inline form is used rather than the profile form because the profile form runs the key under another interpreter, and the composition under test is about the key being invoked directly.
    cases.append(
        (
            2,
            run(
                "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=x PYTHONPATH=.ci python3 -m rediacc_ci.deploy.sync_media_to_r2",
                AWS_ABSENT,
                AWS_GONE,
            ),
            "two-stage: NEEDS_ENV satisfied, NEEDS_SCRIPT still catches the missing aws",
        )
    )

    # AWS_BIN NAMING AN EXECUTABLE IS aws ON THIS HOST, with PATH still stripped: the resolver execs it, so the guard must not route.
    exec_aws = os.path.join(tempfile.mkdtemp(dir=RUN_TMP), "aws")
    with open(exec_aws, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.chmod(exec_aws, 0o700)
    cases.append(
        (
            0,
            run("npm run check:ci-release-state", AWS_ABSENT, {"AWS_BIN": exec_aws}),
            "CONTROL: AWS_BIN names an executable aws, so the gate is left alone",
        )
    )

    fake("aws")
    cases.append(
        (
            0,
            run("npm run check:ci-release-state", f"{shim}:{REAL}"),
            "CONTROL: host HAS aws, so the gate is left alone",
        )
    )
    cases.append(
        (
            0,
            run(
                "PYTHONPATH=.ci python3 -m rediacc_ci.release.assert_edge_tag_exists --version 1.3.0",
                f"{shim}:{REAL}",
            ),
            "CONTROL: host HAS aws, so the port is left alone",
        )
    )
else:
    cases.append(
        (
            0,
            run("npm run check:ci-release-state", AWS_ABSENT, AWS_GONE),
            "CONTROL: no devbox with aws, so the guard notes rather than blocks",
        )
    )

# A SECOND, SMALLER LOOP, deliberately not folded into ALL_TOOLS above. That one asserts npx-misuse for every member, and none of these three is an npx hazard: NPX_TOOLS is unchanged because no `npx aws` incident has been measured, and asserting one here would be testing a branch this guard does not have.
for tool in ("aws", "bw", "bws"):
    if not have_box:
        continue
    tool_in_box = _in_box(tool)
    without = _path_without(tool, REAL)
    want = 2 if tool_in_box else 0
    cases.append(
        (
            want,
            run(f"{tool} --version", without, AWS_GONE if tool == "aws" else None),
            f"bare-tool: {tool} routed when constructed-absent from PATH"
            if tool_in_box
            else f"bare-tool: {tool} absent from host AND devbox -> notes, does not route",
        )
    )
    fake(tool)
    cases.append(
        (
            0,
            run(f"{tool} --version", f"{shim}:{REAL}"),
            f"CONTROL: {tool} present on PATH is left alone",
        )
    )

# --------------------------------------------------------------------------- The exception list.
#
# `_exception` IS DRIVEN AS A FUNCTION for the reason cases go through a process everywhere else in this file: the policy file's path is derived from the repository root, so a process-level case can only exercise it by writing into the real tracked file.
# One case below does exactly that, because the end-to-end path deserves one; the rest use a fixture root, which is also what makes the refusal cases affordable to enumerate.
#
# THE PARSER IS STILL THE REAL ONE. The fixture supplies only the file; `_ci_seams` reaches rediacc_ci.core.allowlist out of this checkout, so a harness copy of the BLOCKER grammar never gets a chance to disagree with the one every gate uses.
# The hop itself is made by `_hookpath` (imported above), which loads the canonical `.claude` helper, rediacc_hooks/syspath.py, BY PATH the same way runtmp is above, because `rediacc_hooks` is not importable by name until it has run.

GUARD = guards.load("block_host_toolchain_run")

# `python3 -m <module>` RUNS THE MODULE. The aws-needing scripts have Python ports under .ci/rediacc_ci, and `_is_invoked` judged a command by its first word, so `PYTHONPATH=.ci python3 -m rediacc_ci.ops.scrub_sentinel v1.0.5` opened with `python3`, which was neither an interpreter it knew nor the key, and the port never got the devbox routing hint its bash original did.
# Function-level, so neither the devbox nor the shipped exception list decides these.
SCRUB = "rediacc_ci.ops.scrub_sentinel"
cases.extend(
    (want, GUARD._is_invoked(SCRUB, cmd), f"python -m: {label}")
    for want, cmd, label in (
        (True, "PYTHONPATH=.ci python3 -m %s v1.0.5" % SCRUB, "python3 -m <module> invokes it"),
        (True, "cd .ci && python -m %s v1.0.5" % SCRUB, "after a separator, bare `python`"),
        (True, "/usr/bin/python3.14 -u -m %s v1.0.5" % SCRUB, "an absolute, versioned interpreter"),
        (True, "python3 -m%s v1.0.5" % SCRUB, "the attached -m<module> spelling"),
        (True, "python3 .ci/rediacc_ci/ops/scrub_sentinel.py", "a script path is the target too"),
        (False, "python3 -m pytest -k %s" % SCRUB, "CONTROL: the key as an argument to pytest"),
        (False, "python3 -c pass %s" % SCRUB, "CONTROL: -c runs a string, not the key"),
        (False, "echo python3 -m %s" % SCRUB, "CONTROL: echoing the command is not running it"),
        (False, "grep -n aws .ci/rediacc_ci/ops/scrub_sentinel.py", "CONTROL: reading the port"),
    )
)

# EVERY NEEDS_SCRIPT ROW NAMES SOMETHING THAT EXISTS. Until 2026-10-09 this loop asserted that every `.sh` row whose port existed also had its module row, which kept nine rows alive for scripts PLAN-retire-bash-oracles B3 had deleted: a row for a file nothing can run routes nothing, and its only readers were the cases that named the deleted paths. The rule now is the one that would have caught them: a `.sh` key is the basename of a tracked file, and a `rediacc_ci.` key is a module file under `.ci/`.
_LS = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True, check=False)
_TRACKED = _LS.stdout.split("\n") if _LS.returncode == 0 else []
_BASENAMES = {path.rsplit("/", 1)[-1] for path in _TRACKED if path}
cases.append((True, len(_BASENAMES) > 1000, "liveness: git ls-files saw the tree"))
for key, _tool in GUARD.NEEDS_SCRIPT:
    if key.endswith(".sh"):
        cases.append((True, key in _BASENAMES, f"liveness: NEEDS_SCRIPT {key} is a tracked script"))
    elif key.startswith("rediacc_ci."):
        module_file = pathlib.Path(REPO, ".ci", *key.split(".")).with_suffix(".py")
        cases.append(
            (True, module_file.is_file(), f"liveness: NEEDS_SCRIPT {key} is a module file")
        )
    else:
        cases.append(
            (True, False, f"liveness: NEEDS_SCRIPT {key} is neither a script nor a module")
        )
cases.append(
    (
        True,
        (SCRUB, "aws") in GUARD.NEEDS_SCRIPT,
        "python -m: the scrub_sentinel port is in NEEDS_SCRIPT",
    )
)

# THE LOCAL RELEASE ENTRY (agent/plans/PLAN-local-release.md W2-C) is a gate-key row: `npm run release:local` names an npm script, so it lives in NEEDS, and a NEEDS_SCRIPT row would fail the liveness loop above. Both directions of `_is_invoked`, decided in-process so they hold whether or not this host carries aws.
cases.append((True, ("release:local", "aws") in GUARD.NEEDS, "release:local: the row is in NEEDS"))
# The module spelling of the same entry (W2-B, f6fc296f2) is a NEEDS_SCRIPT row; the liveness loop above already proves its module file exists. Its key is a PREFIX of `rediacc_ci.release.local_gates`, which runs no aws, so the module is matched whole, never as a substring.
cases.append(
    (
        True,
        ("rediacc_ci.release.local", "aws") in GUARD.NEEDS_SCRIPT,
        "release.local: the module row is in NEEDS_SCRIPT",
    )
)
cases.extend(
    (want, GUARD._is_invoked("rediacc_ci.release.local", cmd), label)
    for want, cmd, label in (
        (
            True,
            "PYTHONPATH=.ci python3 -m rediacc_ci.release.local --channel edge",
            "release.local: python -m runs the module",
        ),
        (
            True,
            "python3 .ci/rediacc_ci/release/local.py --channel edge",
            "release.local: the script path runs the module",
        ),
        (
            False,
            "PYTHONPATH=.ci python3 -m rediacc_ci.release.local_gates --channel edge",
            "CONTROL: the gates module shares the prefix and is not the entry",
        ),
        (
            False,
            "python3 -m pytest -k rediacc_ci.release.local",
            "CONTROL: a pytest selection naming the module is a mention",
        ),
    )
)
cases.append(
    (
        False,
        any(key == "release:local" for key, _tool in GUARD.NEEDS_SCRIPT),
        "release:local: no NEEDS_SCRIPT row, which the liveness loop would refuse",
    )
)
cases.extend(
    (want, GUARD._is_invoked("release:local", cmd), label)
    for want, cmd, label in (
        (True, "npm run release:local -- --channel edge", "release:local: npm run is a run"),
        (
            True,
            "RELEASE_ASKED=ASKED:2026-01-01T00:00Z npm run release:local -- --channel edge",
            "release:local: an env prefix still runs it",
        ),
        (
            False,
            "grep -n release:local package.json",
            "CONTROL: grepping the key is not running it",
        ),
        (False, "echo npm run release:local", "CONTROL: echoing the command is not running it"),
    )
)

# THE OTHER DIRECTION (review 276a69db.1): every runnable module under .ci/rediacc_ci that puts `aws` at the head of an argv has its row, so a new aws-calling port cannot ship without the routing. A module counts as runnable when it carries `if __name__ == "__main__"`. The exemptions are named, each with its reason.
# TWO ARGV HEADS COUNT. Since e7e2ceec1 every aws call site writes `awscli.AWS` (which is "aws") as argv[0] and execs through `rediacc_ci.core.awscli`, and check:ci-aws-resolver refuses a literal "aws" head, so a scan for the literal alone found 2 modules and neither was a port. No module imports `AWS` from awscli by name, so the attribute spelling is the whole new form.
_AWS_ARGV = re.compile(r"""[\[(]\s*(?:["']aws["']|awscli\.AWS)\s*[,\]]""")
_AWS_EXEMPT = {
    # A multi-verb library CLI: aws is one verb (s3api list-objects-v2) of many, so a module row would refuse every other verb on a host without aws.
    "rediacc_ci.core.common",
    # A shadow-run driver for tests; it replays the bash common.sh, it is not run against R2.
    "rediacc_ci.core.common_stub_shadow_driver",
    # The check:ci-aws-resolver gate, which refuses a literal "aws" argv head; its selftest plants carry one, and it never runs aws.
    "rediacc_ci.quality.aws_resolver",
    # The toolchain doctor: `aws --version` is one probe among every pinned tool, and a row would refuse the doctor on exactly the host that lacks aws and needs it told so.
    "rediacc_ci.setup.tools",
}
_MODULE_ROWS = {
    key for key, tool in GUARD.NEEDS_SCRIPT if tool == "aws" and key.startswith("rediacc_ci.")
}
_AWS_MODULES = set()
for rel in _TRACKED:
    if not (rel.startswith(".ci/rediacc_ci/") and rel.endswith(".py")) or "/tests/" in rel:
        continue
    source = pathlib.Path(REPO, rel)
    # Tracked but absent from the working tree (mid-rename): nothing to scan.
    if not source.is_file():
        continue
    text = source.read_text(encoding="utf-8", errors="replace")
    if "__main__" in text and _AWS_ARGV.search(text):
        _AWS_MODULES.add(rel[len(".ci/") : -len(".py")].replace("/", "."))
cases.append(
    (
        True,
        len(_AWS_MODULES) >= 12,
        "coverage: the aws-argv scan found the ports (%d)" % len(_AWS_MODULES),
    )
)
cases.extend(
    (True, mod in _MODULE_ROWS, f"coverage: aws-calling module {mod} has its NEEDS_SCRIPT row")
    for mod in sorted(_AWS_MODULES - _AWS_EXEMPT)
)

# THE aws RUNGS, function-level, because the cache rung is read under the repository root and a process-level case could only plant a binary into the real `.ci/cache`. `_have_aws(root, environ)` takes both, and PATH is set to the constructed absence for the duration, since `hookio.command_v` reads PATH at call time.
AWS_PIN = GUARD._awscli_pin(REPO)
cases.append((True, AWS_PIN != "", "aws rungs: the pin is read from .devcontainer/toolchain.env"))
scratch_root = tempfile.mkdtemp(dir=RUN_TMP)
os.makedirs(os.path.join(scratch_root, ".devcontainer"))
with open(
    os.path.join(scratch_root, ".devcontainer", "toolchain.env"), "w", encoding="utf-8"
) as fh:
    fh.write("# pins\nAWSCLI_VERSION=%s\n" % AWS_PIN)
cached_aws = os.path.join(
    scratch_root, ".ci", "cache", "toolchain", "aws-cli", AWS_PIN, "bin", "aws"
)
saved_path = os.environ.get("PATH", "")
os.environ["PATH"] = AWS_ABSENT
try:
    cases.append(
        (False, GUARD._have_aws(scratch_root, {}), "aws rungs: no AWS_BIN, no PATH aws, no cache")
    )
    os.makedirs(os.path.dirname(cached_aws))
    with open(cached_aws, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.chmod(cached_aws, 0o600)
    cases.append(
        (False, GUARD._have_aws(scratch_root, {}), "aws rungs: a cache file that is not executable")
    )
    os.chmod(cached_aws, 0o700)
    cases.append(
        (True, GUARD._have_aws(scratch_root, {}), "CONTROL aws rungs: the pinned cache binary")
    )
    cases.append(
        (
            False,
            GUARD._have_aws(scratch_root, AWS_GONE),
            "aws rungs: an absent AWS_BIN is absent, and the cache behind it is not consulted",
        )
    )
    cases.append(
        (
            True,
            GUARD._have_aws(scratch_root, {"AWS_BIN": cached_aws}),
            "CONTROL aws rungs: AWS_BIN naming an executable",
        )
    )
    path_aws = tempfile.mkdtemp(dir=RUN_TMP)
    shutil.copy(cached_aws, os.path.join(path_aws, "aws"))
    os.environ["PATH"] = f"{path_aws}:{AWS_ABSENT}"
    cases.append(
        (True, GUARD._have_aws(tempfile.mkdtemp(dir=RUN_TMP), {}), "CONTROL aws rungs: aws on PATH")
    )
    with open(
        os.path.join(scratch_root, ".devcontainer", "toolchain.env"), "w", encoding="utf-8"
    ) as fh:
        fh.write("AWSCLI_VERSION=0.0.0\n")
    os.environ["PATH"] = AWS_ABSENT
    cases.append(
        (
            False,
            GUARD._have_aws(scratch_root, {}),
            "aws rungs: a cache at another version is not the pin",
        )
    )
finally:
    os.environ["PATH"] = saved_path

if aws_in_box:
    # The python -m spelling of the incident command, end to end. The module key is not what the shipped exception list names, so this case holds whatever that list says.
    r = run_full(
        "PYTHONPATH=.ci python3 -m rediacc_ci.release.assert_edge_tag_exists --version 1.3.0",
        AWS_ABSENT,
        AWS_GONE,
    )
    cases.append(
        (2, r.returncode, "NEEDS_SCRIPT: the python -m port of the incident command is REFUSED")
    )
    cases.append(
        (
            True,
            "this command needs 'aws'" in r.stderr,
            "NEEDS_SCRIPT: the python -m refusal reads 'this command needs'",
        )
    )

# A PARSE-ONLY SHELL AND TEXT BASH NEVER RUNS ARE NOT INVOCATIONS. Measured 2026-10-02: `bash -n .ci/scripts/deploy/promote-r2-to-stable.sh`, a syntax check after an edit, was refused as an aws run, once at the tail of a python heredoc whose comment named aws, which is where the writer laid the blame. The guard judged a flat text scan that kept comments and split on newlines; it now
# judges `shellscan._analyse(cmd).runs`, minus what a noexec shell only reads. Function-level first, so neither the host's aws nor the devbox decides these.
PROMOTE = "upload-r2.sh"
cases.extend(
    (want, GUARD._is_invoked(PROMOTE, cmd), f"parse-only: {label}")
    for want, cmd, label in (
        (False, "bash -n .ci/media/tools/%s" % PROMOTE, "bash -n parses and runs nothing"),
        (False, "sh -n .ci/media/tools/%s" % PROMOTE, "sh -n likewise"),
        (False, "bash -nv .ci/media/tools/%s" % PROMOTE, "-n inside a bundle"),
        (False, "bash -o noexec .ci/media/tools/%s" % PROMOTE, "-o noexec"),
        (False, "bash -n -c 'bash %s'" % PROMOTE, "a noexec shell's -c payload runs nothing"),
        (
            False,
            "python3 - <<'EOF'\n# aws and %s, in a comment\nprint(1)\nEOF" % PROMOTE,
            "a heredoc body read by python is data",
        ),
        (False, "true # bash %s" % PROMOTE, "a comment is not a command"),
        (
            False,
            'for f in a \\\n  .ci/media/tools/%s; do wc -l "$f"; done' % PROMOTE,
            "a for word list on a continuation line",
        ),
        (False, "bash -c 'grep -n aws %s'" % PROMOTE, "a -c string is not a script path"),
        (True, "bash .ci/media/tools/%s" % PROMOTE, "TRUE POSITIVE: bash runs the script"),
        (True, "bash -x .ci/media/tools/%s" % PROMOTE, "TRUE POSITIVE: -x still executes"),
        (True, "bash .ci/media/tools/%s -n" % PROMOTE, "TRUE POSITIVE: -n is the script's"),
        (True, "bash +n .ci/media/tools/%s" % PROMOTE, "TRUE POSITIVE: +n turns noexec off"),
        (True, "bash -c 'bash %s'" % PROMOTE, "TRUE POSITIVE: a -c payload that runs it"),
        (True, "bash <<'EOF'\nbash %s\nEOF" % PROMOTE, "TRUE POSITIVE: a heredoc fed to bash"),
        (
            True,
            "bash -n x.sh && .ci/media/tools/%s" % PROMOTE,
            "TRUE POSITIVE: a run after a parse-only one",
        ),
        (True, "x=$(.ci/media/tools/%s)" % PROMOTE, "TRUE POSITIVE: a substitution runs it"),
    )
)

if aws_in_box:
    # End to end, with aws off the host and in the devbox, so the toolchain arm is what would refuse.
    cases.extend(
        (want, run(cmd, AWS_ABSENT, AWS_GONE), f"parse-only end-to-end: {label}")
        for want, cmd, label in (
            (0, "bash -n .ci/media/tools/%s" % PROMOTE, "the 2026-10-02 syntax check"),
            (
                0,
                "python3 - <<'EOF'\n# aws matches the whole key\nprint(1)\nEOF\n"
                "bash -n .ci/media/tools/%s && echo syntax-ok" % PROMOTE,
                "the heredoc-then-syntax-check shape",
            ),
            (0, "echo hi # then; aws s3 ls", "aws named in a comment after a separator"),
            (0, "bash -n -c 'aws s3 ls'", "aws in a noexec shell's -c payload"),
            (2, "bash .ci/media/tools/%s" % PROMOTE, "TRUE POSITIVE: running the script"),
            (2, "bash -c 'aws s3 ls'", "TRUE POSITIVE: aws in a -c payload"),
            (2, "bash -n x.sh; aws s3 ls", "TRUE POSITIVE: aws after a parse-only shell"),
            (2, "x=$(aws s3 ls)", "TRUE POSITIVE: aws in a substitution"),
        )
    )

fixture_root = tempfile.mkdtemp(dir=RUN_TMP)
os.makedirs(os.path.join(fixture_root, ".ci", "policy"))
fixture_list = os.path.join(fixture_root, ".ci", "policy", ".host-toolchain-exceptions")

LEGIT = "the vault unlock is an interactive browser handoff the headless devbox cannot complete"

# THE ILLEGITIMATE HALF IS NINE CASES AND THE LEGITIMATE HALF IS TWO, and the ratio is the finding. The first cut of DEVBOX_GAP_PHRASES was a literal list, and the very first reason written against it -- "the devbox image does not have aws installed so the host is the only place this runs" -- was GRANTED. It says the banned thing in words no literal caught.
# Every paraphrase below was written to break the rule and now documents it instead.
for reason, want_grant, why in (
    (LEGIT, True, "a host-only interactive ceremony is the one category this list is for"),
    (
        "the devbox has no TTY, and this unlock prompts for a hardware key touch on the console",
        True,
        "a devbox-word plus an absence-word is not enough: the claim must be about a TOOL",
    ),
    (
        "the devbox image does not have aws installed so the host is the only place this runs",
        False,
        "a devbox gap is refused, and this is the wording that beat the first literal list",
    ),
    (
        "aws doesn't exist on devbox, so the host has to run it for the release pipeline to work",
        False,
        "a devbox gap is refused -- the plan's first named phrase",
    ),
    (
        "aws is absent from the devbox image and adding it there would take a full rebuild cycle",
        False,
        "a devbox gap is refused -- the plan's second named phrase",
    ),
    (
        "the devbox lacks it entirely, so running on the host is the only option available now",
        False,
        "a devbox gap is refused -- the plan's third named phrase",
    ),
    (
        "aws is not installed in devbox and nobody wants to rebuild the image for one command",
        False,
        "a devbox gap is refused -- the plan's fourth named phrase",
    ),
    (
        "the container image ships no aws binary at all, so this must stay on the host machine",
        False,
        "a devbox gap is refused through a verb the `has no` entry alone would have missed",
    ),
    (
        "the devcontainer is missing the aws cli, which makes the host the only usable place",
        False,
        "a devbox gap is refused when the subject is spelled devcontainer",
    ),
):
    with open(fixture_list, "w", encoding="utf-8") as fh:
        fh.write(f"# BLOCKER: {reason}\ncheck:ci-release-state@aws\n")
    granted, refused = GUARD._exception(fixture_root, "check:ci-release-state", "aws")
    cases.append((want_grant, bool(granted), f"exception: {why}"))
    if not want_grant:
        cases.append(
            (True, refused != "", f"exception: the ignored entry is REPORTED, not silent -- {why}")
        )

# THE GENERIC BLOCKER RULES STILL APPLY, and they are not re-implemented here: rediacc_ci.core.allowlist.verify is what rejects these, exactly as it does for every other list in the tree.
for body, why in (
    (
        "# BLOCKER: needed\ncheck:ci-release-state@aws\n",
        "a reason under the 30-character floor grants nothing",
    ),
    ("# BLOCKER: todo\ncheck:ci-release-state@aws\n", "a low-effort placeholder grants nothing"),
    ("check:ci-release-state@aws\n", "an entry with no BLOCKER line at all grants nothing"),
):
    with open(fixture_list, "w", encoding="utf-8") as fh:
        fh.write(body)
    granted, refused = GUARD._exception(fixture_root, "check:ci-release-state", "aws")
    cases.append((False, bool(granted), f"exception: {why}"))
    cases.append((True, refused != "", f"exception: and it says so -- {why}"))

# AN EXCEPTION IS FOR ONE COMMAND NEEDING ONE TOOL. A `<hit>@<tool>` key that does not match both halves must not be reached for, or the first exception written would quietly excuse every command that needs the same binary.
with open(fixture_list, "w", encoding="utf-8") as fh:
    fh.write(f"# BLOCKER: {LEGIT}\ncheck:ci-release-state@aws\n")
for hit, need, why in (
    ("upload-r2.sh", "aws", "another command needing the same tool is not covered"),
    ("check:ci-release-state", "ruff", "the same command needing another tool is not covered"),
):
    granted, _ = GUARD._exception(fixture_root, hit, need)
    cases.append((False, bool(granted), f"exception: {why}"))

# AN ABSENT LIST GRANTS NOTHING, and it fails in the direction that cannot hide: the command is still refused and routed, exactly as it was before this file existed.
os.remove(fixture_list)
cases.append(
    (
        True,
        GUARD._exception(fixture_root, "check:ci-release-state", "aws") == ("", ""),
        "exception: an absent list grants nothing and reports nothing",
    )
)
shutil.rmtree(fixture_root, ignore_errors=True)

# THE SHIPPED FILE IS EMPTY, and that is asserted rather than assumed. An entry landing here without the reasoning that belongs with it is the thing this whole mechanism is one edit away from becoming.
cases.append(
    (
        True,
        GUARD._exception(REPO, "check:ci-release-state", "aws") == ("", ""),
        "the shipped exception list grants nothing today",
    )
)

# ONE END-TO-END CASE, through the process, because every other exception case above stops at the function. The real tracked file is written and RESTORED under try/finally: this checkout is shared, and a harness that leaves a fixture entry in a policy file has suppressed something for everyone.
if aws_in_box:
    real_list = os.path.join(REPO, ".ci", "policy", ".host-toolchain-exceptions")
    with open(real_list, encoding="utf-8") as fh:
        saved = fh.read()
    try:
        with open(real_list, "w", encoding="utf-8") as fh:
            fh.write(f"{saved}\n# BLOCKER: {LEGIT}\ncheck:ci-release-state@aws\n")
        e2e = run_full("npm run check:ci-release-state", AWS_ABSENT, AWS_GONE)
    finally:
        with open(real_list, "w", encoding="utf-8") as fh:
            fh.write(saved)
    cases.append((0, e2e.returncode, "exception end-to-end: a valid entry ALLOWS the command"))
    cases.append(
        (
            True,
            LEGIT in e2e.stderr and "BLOCKED" not in e2e.stderr,
            "exception end-to-end: the note names the reason rather than standing in for it",
        )
    )
    with open(real_list, encoding="utf-8") as fh:
        cases.append(
            (
                True,
                fh.read() == saved,
                "exception end-to-end: the policy file is restored byte for byte",
            )
        )

shutil.rmtree(shim, ignore_errors=True)

bad = 0
for want, got, label in cases:
    if want != got:
        bad += 1
        print(f"  FAIL [{want}] {label} (got {got})")
print(f"FAILURES: {bad}  ({len(cases)} case(s), devbox_present={have_box})")
sys.exit(1 if bad else 0)
