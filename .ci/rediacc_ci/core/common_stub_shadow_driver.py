#!/usr/bin/env python3
"""Both sides of the stub-farm half of the `core.common` differential: `r2_count_objects` against a STUB `aws`, and `wait_for` against a stub probe and `sleep`.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.common_stub_shadow_driver --side old --twin .ci/scripts/lib/common.sh --port .ci/rediacc_ci/core/common.py <scenario>
    PYTHONPATH=.ci python3 -m rediacc_ci.core.common_stub_shadow_driver --side new --twin .ci/scripts/lib/common.sh --port .ci/rediacc_ci/core/common.py <scenario>

WHY A STUB. `r2_count_objects` shells out to `aws s3api list-objects-v2` and this machine has no `aws`, which is why the 2026-09-10 port of `common.sh` left it out. `core/stubfarm.py` puts a scripted `aws` first on PATH for both sides, so the comparison covers rc, both streams and the exact argv the function builds, which is where its bugs would live (the optional `--endpoint-url`, the JMESPath query, the empty-versus-failed split). RUN AS A MODULE, never by path.

A pair of its own (`w7p5b-common-stub`) rather than rows in `w7p5b-common`, because that ledger's rows name scratch-local drivers and a row is one twin against one port BY ONE TECHNIQUE.

  count     a count, `None` (a missing prefix, which is 0), an empty answer, a word, a two-line answer, trailing blank lines (stripped by `$(...)`) and a space-padded count (NOT stripped, so refused).
  failure   `aws` failing with multi-line stderr, with stderr lacking a final newline, and with none at all.
  endpoint  the endpoint from the third argument, from `CLOUDFLARE_R2_ENDPOINT`, the argument beating the variable, and none.
  quoting   bucket and prefix values carrying spaces, shell metacharacters, a leading dash and a multibyte character, each reaching `aws` as ONE argument.
  wait      `wait_for` succeeding at once, after three failures, never (with `DEBUG=true`, so every `Waiting...` line is compared), with a probe that is not installed, and with a zero budget.
  refusal   no bucket, an empty prefix, and no `AWS_ACCESS_KEY_ID`: the three `${...:?}` deaths.
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.core.stubfarm import Farm

EXIT_CANNOT_RUN = 77


@dataclasses.dataclass
class Case:
    name: str
    args: list[str]
    rows: list[dict] = dataclasses.field(default_factory=list)
    env: dict[str, str | None] = dataclasses.field(default_factory=dict)
    verb: str = "r2"


def aws(out: str | None = None, rc: int = 0, err: str | None = None) -> dict:
    return {"name": "aws", "glob": "*", "out": out, "rc": rc, "err": err}


def probe(
    rc: int, times: int | None = None, out: str | None = None, err: str | None = None
) -> dict:
    return {"name": "probe", "glob": "*", "rc": rc, "times": times, "out": out, "err": err}


SCENARIOS: dict[str, list[Case]] = {
    "count": [
        Case("three", ["rediacc-www-media", "releases/v1/"], [aws("3\n")]),
        Case("none-is-zero", ["b", "p"], [aws("None\n")]),
        Case("empty-answer", ["b", "p"], [aws("")]),
        Case("a-word", ["b", "p"], [aws("lots\n")]),
        Case("two-lines", ["b", "p"], [aws("3\n4\n")]),
        Case("trailing-blank-lines", ["b", "p"], [aws("12\n\n\n")]),
        Case("padded", ["b", "p"], [aws(" 5 \n")]),
    ],
    "failure": [
        Case(
            "multi-line-stderr",
            ["b", "p"],
            [aws(rc=255, err="An error occurred (AccessDenied)\nsecond line\n")],
        ),
        Case(
            "no-final-newline",
            ["b", "p"],
            [aws(rc=254, err="Could not connect to the endpoint URL")],
        ),
        Case("silent-failure", ["b", "p"], [aws(out="7\n", rc=1)]),
    ],
    "endpoint": [
        Case("from-argument", ["b", "p", "https://acct.r2.example"], [aws("1\n")]),
        Case(
            "from-variable",
            ["b", "p"],
            [aws("1\n")],
            {"CLOUDFLARE_R2_ENDPOINT": "https://env.example"},
        ),
        Case(
            "argument-wins",
            ["b", "p", "https://arg.example"],
            [aws("1\n")],
            {"CLOUDFLARE_R2_ENDPOINT": "https://env.example"},
        ),
        Case("none", ["b", "p"], [aws("1\n")]),
        Case(
            "empty-argument-falls-back",
            ["b", "p", ""],
            [aws("1\n")],
            {"CLOUDFLARE_R2_ENDPOINT": "https://env.example"},
        ),
    ],
    "quoting": [
        Case("spaces", ["my bucket", "a prefix/with space/"], [aws("2\n")]),
        Case("metacharacters", ["b", "p/$(x)/`y`/*?[z]"], [aws("2\n")]),
        Case("dash-leading", ["-b", "--prefix"], [aws("2\n")]),
        Case("unicode", ["b", "p/über/"], [aws("2\n")]),
    ],
    "wait": [
        Case(
            "at-once", ["10", "2", "probe", "--ready"], [probe(0)], {"DEBUG": "true"}, verb="wait"
        ),
        Case(
            "after-three",
            ["10", "2", "probe", "x y"],
            [probe(1, times=3, out="noise\n", err="not yet\n"), probe(0)],
            {"DEBUG": "true"},
            verb="wait",
        ),
        Case("never-debug", ["7", "2", "probe"], [probe(1)], {"DEBUG": "true"}, verb="wait"),
        Case("never-quiet", ["6", "3", "probe"], [probe(1)], verb="wait"),
        Case("not-installed", ["4", "1", "no-such-probe-xyz"], [], {"DEBUG": "true"}, verb="wait"),
        Case("zero-budget", ["0", "1", "probe"], [probe(0)], verb="wait"),
    ],
    "refusal": [
        Case("no-bucket", [], [aws("1\n")]),
        Case("empty-prefix", ["b", ""], [aws("1\n")]),
        Case("no-key", ["b", "p"], [aws("1\n")], {"AWS_ACCESS_KEY_ID": None}),
        Case("empty-key", ["b", "p"], [aws("1\n")], {"AWS_ACCESS_KEY_ID": ""}),
    ],
}

OLD_PROGRAMS = {
    "r2": 'source "$1/.ci/scripts/lib/common.sh"; shift; r2_count_objects "$@"',
    "wait": 'source "$1/.ci/scripts/lib/common.sh"; shift; wait_for "$@"',
}
NEW_VERBS = {"r2": "r2-count-objects", "wait": "wait-for"}


def observe(side: str, repo: pathlib.Path, case: Case) -> list[str]:
    work = pathlib.Path(tempfile.mkdtemp(prefix="r2-shadow-"))
    try:
        farm = Farm(work)
        farm.stub("aws", "probe", "sleep")
        for spec in case.rows:
            fields = dict(spec)
            farm.respond(fields.pop("name"), fields.pop("glob"), **fields)
        base = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(work),
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
        }
        for key, value in case.env.items():
            if value is None:
                base.pop(key, None)
            else:
                base[key] = value
        env = farm.env(base)
        if side == "old":
            argv = ["bash", "-c", OLD_PROGRAMS[case.verb], "common-old", str(repo), *case.args]
        else:
            env["PYTHONPATH"] = str(repo / ".ci")
            argv = ["python3", "-m", "rediacc_ci.core.common", NEW_VERBS[case.verb], *case.args]
        proc = subprocess.run(
            argv, cwd=repo, env=env, capture_output=True, text=True, check=False, timeout=120
        )
        lines = ["obs %s rc=%d" % (case.name, proc.returncode)]
        lines += [
            "obs %s out#%d| %s" % (case.name, i, t) for i, t in enumerate(proc.stdout.splitlines())
        ]
        for i, raw in enumerate(proc.stderr.splitlines()):
            text = raw
            # `<file>: line <N>: ` is bash's own stamp on a `${...:?}` death; not reproducible by a port, dropped on both sides.
            if ": line " in raw and raw.split(": line ", 1)[1].split(":", 1)[0].isdigit():
                text = raw.split(": line ", 1)[1].split(": ", 1)[1]
            lines.append("obs %s err#%d| %s" % (case.name, i, text))
        lines += ["obs %s call#%d| %s" % (case.name, i, t) for i, t in enumerate(farm.transcript())]
        return lines
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="one side of the core.common stub-farm differential"
    )
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "common_stub_shadow_driver: the %s %s does not exist under %s\n"
                % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN
    for case in SCENARIOS[args.scenario]:
        for line in observe(args.side, repo, case):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
