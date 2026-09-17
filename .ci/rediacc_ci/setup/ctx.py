"""The one seam every ported setup phase reaches the machine through.

WHY A SEAM AND NOT `shutil.which` EVERYWHERE. The bash this replaces is proven
by driving it, not by reading it: `.ci/rediacc_ci/setup/shadow_driver.py` runs
`bash -c 'source .ci/lib/setup.sh; setup_node_toolchain'` beside the Python and
compares. The bash side can only be steered by PATH and by the environment,
because there is nothing else to inject into a sourced function. So the Python
side must be steerable by exactly the same two things and by NOTHING ELSE. A
port that reads `shutil.which` (which consults `os.environ` at call time, but
also caches nothing and ignores an env dict a caller hands it) or `os.isatty(0)`
directly cannot be pointed at a fixture the way the bash can, and the
differential would then be comparing two different questions.

Hence: every probe in this package goes through a `Ctx`. `Ctx.which` resolves
against `ctx.env["PATH"]`, `Ctx.run` passes `ctx.env` down, and `ctx.stdin_tty`
is a value rather than a call. Point both sides at the same PATH and the same
env and they are answering the same question about the same machine.

WHAT IS DELIBERATELY NOT HERE. No installer, no sudo, no network. Those live in
the phase modules, are guarded by `ctx.stdin_tty` and `ctx.confirm`, and in the
differential they are never reached: both sides run with stdin closed, which is
the branch that PRINTS the command instead of running it. That is the branch
this repository's users meet most often (an agent session, a CI checkout, a
piped run), and it is the only branch a differential can honestly drive.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rediacc_ci import log

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

# `timeout(1)` is spelled out rather than imported from `rediacc_ci.proc` at module scope for one reason: `proc` is about wrapping a CHILD in the coreutils timeout binary, and everything here that needs a deadline gets it from
# `subprocess.run(timeout=...)`, which needs no binary at all and therefore has
# no macOS gap. The bash spells the same deadline `timeout 30 docker info`
# (.ci/lib/setup.sh:576); the number is carried, the mechanism is not.
DEFAULT_TIMEOUT = 30


@dataclass
class Result:
    """One finished child. `out` and `err` are text, never bytes.

    `rc` is the exit status, or 124 for a timeout, which is what coreutils
    `timeout` returns and therefore what every bash caller in this tree already
    branches on.
    """

    rc: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.rc == 0

    def first_line(self) -> str:
        """`| head -1`, with the trailing newline gone. "" for empty output."""
        return self.out.split("\n", 1)[0].strip()


@dataclass
class Ctx:
    """Everything a phase is allowed to know about the host.

    `env` is a COPY the caller owns. Nothing here writes to `os.environ`: the
    bash mutates its own process env with `export PATH=...` after installing
    node, and the Python equivalent is mutating `ctx.env`, which keeps the
    blast radius inside the object the differential controls.
    """

    root: pathlib.Path
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    stdin_tty: bool = False
    # BUILT IN `__post_init__` WHEN ABSENT, so the type is not Optional past construction and no call site needs an assert to satisfy a type checker.
    logger: log.Logger = None  # type: ignore[assignment]
    # ANSWERS EVERY PROMPT WITHOUT ASKING, and `None` means "there is nobody to ask". Held as data rather than as a method override so a fixture can say "the operator would have said yes" without subclassing anything.
    answer: bool | None = None

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = log.Logger()

    # -- probes ------------------------------------------------------------

    def which(self, name: str) -> str | None:
        """`command -v <name>`, resolved against THIS ctx's PATH.

        `shutil.which(name, path=...)` and not the bare form: the bare form
        reads `os.environ["PATH"]`, which is the process's PATH and not the
        fixture's, and a probe that ignores the fixture is a probe that reports
        on the developer's laptop while claiming to report on the tree.
        """
        return shutil.which(name, path=self.env.get("PATH", ""))

    def run(
        self,
        argv: list[str],
        *,
        timeout: int | None = DEFAULT_TIMEOUT,
        stdin_text: str | None = None,
    ) -> Result:
        """One child, both streams captured SEPARATELY, never merged.

        Merging them is how progress text ends up parsed as data. Every caller
        here reads exactly one of the two, and the other is still available when
        the call fails, which is the only moment it matters.
        """
        # `stdin=` AND `input=` TOGETHER IS A ValueError, not a preference:
        # `subprocess.run` refuses the pair outright ("stdin and input arguments may not both be used"). Found by running this driver rather than by reading it, which is the whole reason the differential exists. The two cases are therefore built separately: no input means stdin is CLOSED, which is what makes every `[[ -t 0 ]]` branch in the bash take its non-interactive arm here
        # too.
        common = {
            "cwd": str(self.root),
            "env": self.env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "timeout": timeout,
        }
        try:
            if stdin_text is None:
                proc = subprocess.run(argv, stdin=subprocess.DEVNULL, check=False, **common)
            else:
                proc = subprocess.run(argv, input=stdin_text, check=False, **common)
        except subprocess.TimeoutExpired:
            # 124, because that is what `timeout(1)` returns and what the bash this replaces would have propagated.
            return Result(124, "", "timed out after %ss: %s" % (timeout, " ".join(argv)))
        except OSError as exc:
            # 127, `command not found`. A missing binary must not raise out of a probe: "is it there" is the question the probe was asked.
            return Result(127, "", str(exc))
        return Result(proc.returncode, proc.stdout or "", proc.stderr or "")

    # -- output ------------------------------------------------------------
    #
    # log_* GOES TO STDERR AND PLAIN `print` GOES TO STDOUT, and the split is load-bearing rather than stylistic. `.ci/lib/setup.sh:21-23` states it: "refuses rather than hanging on a non-TTY, printing the command it would have run as PLAIN stdout so it can be pasted (log_* prefixes every line
    # with a coloured marker, which breaks a paste)". Carried exactly.

    # EVERY LEVEL GOES THROUGH `emit`, INCLUDING THE THREE THAT HAVE A NAMED METHOD. `Logger.warn` would trip ruff's G010 ("logging statement uses warn instead of warning"), a flake8-logging-format rule written about the STDLIB logging module -- and `rediacc_ci.log.Logger` is not one: it has no levels, no handlers and no `warning`. Routing all four through the one primitive keeps
    # the four call sites symmetrical instead of making one of them the odd one out for a reason that is not about this code.
    def info(self, message: str) -> None:
        self.logger.emit("info", message)

    def warn(self, message: str) -> None:
        self.logger.emit("warn", message)

    def error(self, message: str) -> None:
        self.logger.emit("error", message)

    def step(self, message: str) -> None:
        self.logger.emit("step", message)

    def say(self, message: str = "") -> None:
        """A pasteable line on STDOUT. The bash spells this bare `echo`."""
        print(message)

    def confirm(self, message: str) -> bool:
        """`prompt_continue`, .ci/lib/local-common.sh:371.

        `read -p "$message (y/N): " response; [[ "$response" =~ ^[yY]$ ]]` --
        so ONE character, y or Y, and nothing else. `yes` is a NO there, and
        that surprising detail is carried rather than improved: the differential
        would catch the improvement as a disagreement, and the bash is the
        specification until the day the bash is gone.
        """
        if self.answer is not None:
            return self.answer
        if not self.stdin_tty:
            # Never block. A prompt with nobody to answer it is the hang this whole package's non-TTY branches exist to avoid.
            return False
        try:
            response = input("%s (y/N): " % message)
        except EOFError:
            return False
        return response in ("y", "Y")

    def ask(self, message: str, *, hidden: bool = False) -> str:
        """`read -p` / `read -r -s -p`. "" when there is nobody to ask."""
        if not self.stdin_tty:
            return ""
        try:
            if hidden:
                return getpass.getpass(message)
            return input(message)
        except EOFError:
            return ""
