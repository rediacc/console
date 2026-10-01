"""Shared harness for the `rediacc_ci.testrun` differentials (B2 ports of `.ci/scripts/test/*.sh`).

A case runs the bash twin and the Python port on the SAME argv and environment with a FAKE-BINARY PATH, then compares stdout, stderr, exit code and the fake binaries' call log separately. The PATH is replaced, never prepended, and holds only the fakes, the directory of the real `node` (some twins spawn it), and the coreutils directories.

The call log is one JSON line per fake invocation: `{"tool", "argv", "cwd"}`, written to `$FAKE_LOG`, never to stdout, so a fake cannot disturb a stream under comparison.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.tests import differential as diff

ROOT = paths.repo_root()
BASH = shutil.which("bash") or "/bin/bash"
NODE = shutil.which("node")
SYSTEM_DIRS = ("/usr/bin", "/bin")

# Fake body. `FAKE_OUT_<TOOL>` is printed to stdout, `FAKE_ERR_<TOOL>` to stderr, `FAKE_RC_<TOOL>` is the exit code, applied only to calls whose argv contains the word in `FAKE_RCWHEN_<TOOL>` when that is set; a tool with none of them is silent and succeeds. `FAKE_CAT_<TOOL>` names a file the fake copies to the log at call time (used to read a temp config while it still exists).
FAKE_TEMPLATE = r"""#!/bin/bash
tool="$(basename "$0")"
up="$(echo "$tool" | tr '[:lower:]-' '[:upper:]_')"
node -e '
const fs = require("fs");
const rec = { tool: process.argv[1], argv: process.argv.slice(2), cwd: process.cwd() };
const cat = process.env["FAKE_CAT_" + process.argv[1].toUpperCase().replace(/-/g, "_")];
if (cat) {
  const i = process.argv.indexOf(cat);
  const f = i >= 0 ? process.argv[i + 1] : "";
  try { rec.config = fs.readFileSync(f, "utf8"); } catch (e) { rec.config = null; }
}
fs.appendFileSync(process.env.FAKE_LOG, JSON.stringify(rec) + "\n");
' "$tool" "$@"
out="FAKE_OUT_$up"; err="FAKE_ERR_$up"; rc="FAKE_RC_$up"; when="FAKE_RCWHEN_$up"
if [[ -n "${!when:-}" && " $* " != *" ${!when} "* ]]; then rc="FAKE_NONE"; fi
[[ -n "${!out:-}" ]] && printf '%s\n' "${!out}"
[[ -n "${!err:-}" ]] && printf '%s\n' "${!err}" >&2
exit "${!rc:-0}"
"""


@dataclasses.dataclass
class Outcome:
    code: int
    out: str
    err: str
    calls: list[dict[str, typing.Any]]


def make_fakes(
    directory: pathlib.Path, tools: typing.Iterable[str], bodies: dict[str, str] | None = None
) -> pathlib.Path:
    """Write one executable fake per name in `tools` into `directory/bin`; `bodies` replaces a fake's script wholesale."""
    bindir = directory / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    for tool in tools:
        target = bindir / tool
        target.write_text((bodies or {}).get(tool, FAKE_TEMPLATE))
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bindir


def sealed_path(bindir: pathlib.Path) -> str:
    parts = [str(bindir)]
    if NODE:
        parts.append(str(pathlib.Path(NODE).parent))
    parts.extend(SYSTEM_DIRS)
    return ":".join(parts)


def run_side(
    argv: list[str],
    directory: pathlib.Path,
    tools: typing.Iterable[str],
    env: dict[str, str] | None = None,
    cwd: pathlib.Path | None = None,
    timeout: float = 120,
    bodies: dict[str, str] | None = None,
) -> Outcome:
    """Run `argv` once under the sealed PATH and read back the call log."""
    bindir = make_fakes(directory, tools, bodies)
    log = directory / "calls.jsonl"
    log.write_text("")
    full = {
        "PATH": sealed_path(bindir),
        "HOME": str(directory),
        "FAKE_LOG": str(log),
        "TMPDIR": str(directory),
        "LC_ALL": "C",
        **(env or {}),
    }
    done = subprocess.run(
        argv,
        cwd=str(cwd or ROOT),
        env=full,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    return Outcome(done.returncode, done.stdout, done.stderr, calls)


def twin_run(
    twin: str,
    argv: list[str],
    directory: pathlib.Path,
    tools: typing.Iterable[str],
    env: dict[str, str] | None = None,
    cwd: pathlib.Path | None = None,
    timeout: float = 120,
    bodies: dict[str, str] | None = None,
    files: typing.Iterable[pathlib.Path] = (),
) -> Outcome:
    """What the retired bash twin `twin` answered for this case, from `goldens/twins/` (PLAN-retire-bash-oracles B3).

    `files` are paths the twin writes (a `$GITHUB_OUTPUT`): a re-freeze records them, every other run writes the frozen text back (or removes the path when the twin wrote none), so the caller reads them as it did live. Only a re-freeze (`REDIACC_CI_REGOLDEN=bash`, while the `.sh` still exists) runs `argv`; every other run reads the stored exit code, streams and fake-binary call log. The key is the argv, the environment and the tool list, with the scratch parent folded.
    """
    tools = list(tools)
    cell: dict[str, Outcome] = {}

    def go() -> tuple[int, str, str]:
        cell["o"] = run_side(argv, directory, tools, env, cwd, timeout, bodies)
        return cell["o"].code, cell["o"].out, cell["o"].err

    rc, out, err, got = diff.twin_run(
        twin,
        [
            "argv=%r" % (argv,),
            "env=%r" % (sorted((env or {}).items()),),
            "tools=%r" % (sorted(tools),),
            "cwd=%s" % (cwd or ROOT),
        ],
        go,
        files=tuple(str(f) for f in files),
        extras={"calls": lambda: json.dumps(cell["o"].calls)},
        work=(str(directory.parent),),
    )
    return Outcome(rc, out, err, json.loads(got["calls"]))


def bash_cmd(script_rel: str, *args: str) -> list[str]:
    return [BASH, str(ROOT / script_rel), *args]


def py_cmd(module: str, *args: str) -> list[str]:
    return [sys.executable, "-m", module, *args]


def py_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    return {"PYTHONPATH": str(ROOT / ".ci"), **(extra or {})}


TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.000Z")


def mask(text: str, directory: pathlib.Path) -> str:
    """Make a transcript comparable: the scratch directory and timestamps vary between runs."""
    return TIMESTAMP.sub("<NOW>", text.replace(str(directory), "<TMP>"))
