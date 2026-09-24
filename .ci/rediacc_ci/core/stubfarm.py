"""A directory of scripted stand-ins for external programs, with a transcript of every call.

WHY THIS EXISTS. The W7P5-b library ports reached a wall at every function that CHANGES something: `service_start` builds an image, `account_dev` boots a stack, `ensure_deps` runs `npm ci`. Driving those for real, twice per observation and five times over, is slow, leaves state behind, and compares two runs of a network rather than two programs. The differential that does compare two
programs is this one: put a directory of stubs FIRST on PATH for both sides, have each stub append its argv to one transcript and answer from a scripted table, and compare rc, stdout, stderr AND the ordered transcript. A port then has to make the same calls, with the same arguments, in the same order, which is exactly what a lifecycle port claims.

THE STUB IS BASH, NOT PYTHON, because the bash side calls it hundreds of times per scenario in some drivers and a Python interpreter start per call would dominate the run. It is generated from one template for both sides, so neither side can see a different stub.

THE TABLE, one row per line, tab-separated, first match wins:

    name  glob  rc  out  err  times  sh

  name   the program (the stub's own basename)
  glob   a bash pattern matched against "$*", the arguments joined by single spaces
  rc     the exit status
  out    stdout, `printf %b` escapes (`\\n`, `\\t`, `\\\\`); `-` for nothing
  err    stderr, the same; `-` for nothing
  times  how many calls this row answers before it stops matching; `-` for always
  sh     base64 of a bash snippet the stub `eval`s before answering (a side effect: create a file, touch a pid); `-` for none

A call no row matches exits 0 silently, which is the answer most programs give to a flag the scenario does not care about. A scenario that needs a refusal says so with a row.

WHAT IS NOT LOGGED. A stub made with `logged=False` still answers from the table but writes nothing to the transcript. That is for CLOCK READS (`date +%s`) and similar, where the twin reaches a program and the port reads the same fact in-process: the call is an implementation detail of reading a value, not an action the port must reproduce.
"""

from __future__ import annotations

import base64
import os
import pathlib
import shlex
import shutil

STUB_TEMPLATE = r"""#!/bin/bash
me="${0##*/}"
if [[ "%(logged)s" == 1 ]]; then
    line="$me"
    for a in "$@"; do line+=" $(printf '%%q' "$a")"; done
    printf '%%s\n' "$line" >>"$STUB_LOG"
fi
joined="$*"
n=0
while IFS=$'\t' read -r name glob rc out err times sh || [[ -n "$name" ]]; do
    n=$((n + 1))
    [[ "$name" == "$me" ]] || continue
    # shellcheck disable=SC2053
    [[ "$joined" == $glob ]] || continue
    if [[ "$times" != "-" ]]; then
        c="$STUB_LOG.count.$n"
        used=0
        [[ -f "$c" ]] && used="$(<"$c")"
        ((used >= times)) && continue
        printf '%%s\n' "$((used + 1))" >"$c"
    fi
    if [[ "$sh" != "-" ]]; then
        eval "$(printf '%%s' "$sh" | base64 -d)"
    fi
    [[ "$out" == "-" ]] || printf '%%b' "$out"
    [[ "$err" == "-" ]] || printf '%%b' "$err" >&2
    exit "$rc"
done <"$STUB_TABLE"
exit 0
"""


def escape(text: str) -> str:
    """Encode `text` for a `printf %b` field. The empty string is `-`'s opposite: it prints nothing but is not "unset"."""
    if text is None:
        return "-"
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t")


class Farm:
    """One stub directory, one table, one transcript."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = pathlib.Path(root)
        self.bin = self.root / "stubbin"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.table = self.root / "stub.table"
        self.log = self.root / "stub.log"
        self.table.write_text("", encoding="utf-8")
        self.log.write_text("", encoding="utf-8")
        self.names: list[str] = []

    def stub(self, *names: str, logged: bool = True) -> Farm:
        for name in names:
            path = self.bin / name
            path.write_text(STUB_TEMPLATE % {"logged": "1" if logged else "0"}, encoding="utf-8")
            path.chmod(0o755)
            self.names.append(name)
        return self

    def respond(
        self,
        name: str,
        glob: str = "*",
        *,
        rc: int = 0,
        out: str | None = None,
        err: str | None = None,
        times: int | None = None,
        sh: str | None = None,
    ) -> Farm:
        if "\t" in glob or "\n" in glob:
            raise ValueError("a glob may not carry a tab or a newline: %r" % glob)
        fields = [
            name,
            glob,
            str(rc),
            "-" if out is None else escape(out),
            "-" if err is None else escape(err),
            "-" if times is None else str(times),
            "-" if sh is None else base64.b64encode(sh.encode()).decode(),
        ]
        with self.table.open("a", encoding="utf-8") as handle:
            handle.write("\t".join(fields) + "\n")
        return self

    def stub_at(self, path: pathlib.Path, logged: bool = True) -> Farm:
        """A stub at a fixed PATH rather than on PATH, for a program the twin runs by path (`./build.sh`). It answers from the same table under its basename."""
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STUB_TEMPLATE % {"logged": "1" if logged else "0"}, encoding="utf-8")
        path.chmod(0o755)
        return self

    def host_path(self, hidden: tuple[str, ...]) -> str:
        """A directory of symlinks to every program in the standard directories EXCEPT `hidden`.

        How a scenario makes a tool ABSENT: the stub directory can add a program but cannot take one away, and `command -v jq` on a machine with jq installed answers yes whatever comes first on PATH. A name the scenario also stubs is shadowed by the stub either way, so hiding only matters for names left unstubbed.
        """
        farm = self.root / "hostbin"
        if farm.exists():
            shutil.rmtree(farm)
        farm.mkdir()
        for directory in (
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
        ):
            try:
                names = sorted(os.listdir(directory))
            except OSError:
                continue
            for name in names:
                target = pathlib.Path(directory) / name
                link = farm / name
                if name in hidden or link.exists() or link.is_symlink():
                    continue
                if target.is_file() and os.access(target, os.X_OK):
                    link.symlink_to(target)
        return str(farm)

    def env(self, base: dict[str, str], hidden: tuple[str, ...] = ()) -> dict[str, str]:
        out = dict(base)
        rest = self.host_path(hidden) if hidden else base.get("PATH", "/usr/bin:/bin")
        out["PATH"] = "%s:%s" % (self.bin, rest)
        out["STUB_LOG"] = str(self.log)
        out["STUB_TABLE"] = str(self.table)
        out["STUB_ROOT"] = str(self.root)
        return out

    def transcript(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def reset_log(self) -> None:
        self.log.write_text("", encoding="utf-8")
        for counter in self.root.glob("stub.log.count.*"):
            counter.unlink()


def quote(argv: list[str]) -> str:
    """How a transcript line spells an argv, for a reader writing an expectation by hand."""
    return " ".join(shlex.quote(a) for a in argv)


def shadows(farm: Farm, name: str, env: dict[str, str]) -> bool:
    """True when `name` on `env`'s PATH resolves to the stub. The anti-vacuity check every driver makes."""
    for entry in env.get("PATH", "").split(os.pathsep):
        candidate = pathlib.Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.parent == farm.bin
    return False
