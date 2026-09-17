"""The phase sequence of `./run.sh setup`, as data, plus the reader that proves it.

THE ORDER IS THE SPECIFICATION, not the set. `.ci/rediacc_ci/setup/tools.py:196` says it for the install table -- "ORDER IS THE DEPENDENCY ORDER a fresh machine needs, not alphabetical" -- and `setup()` is where that order is actually executed. Two of its edges are load-bearing and both were paid for:

  * the compiler comes before anything reached through npm, because
    `npm run install:natives` runs node-gyp (`.ci/lib/setup.sh:234-239`);
  * submodules are initialised BEFORE the first phase that reads one, because
    `setup_go_toolchain` reads `private/renet/go.mod` and a fresh clone
    otherwise fails with "Cannot determine the required Go version", a message
    that never mentions submodules (`.ci/legacy/run-legacy.sh:616-622`).

`.ci/rediacc_ci/quality/setup_idempotency.py:608` (check G) already refuses the second of those in the bash. This table is what lets the same claim be made about the Python, and `PHASE_KEY` is deliberately the BASH FUNCTION NAME rather than a friendly label: a translation table between the two sides is exactly where a reordering hides, so there is none.

TWO READERS, ASKING DIFFERENT QUESTIONS, AND BOTH ARE NEEDED.

    `from_source()`   reads the `setup()` body out of the bash and returns the
                      phase keys it CONTAINS, in the order they appear. Static,
                      cheap, and blind to a conditional: it reports the
                      submodule phase whether or not `.gitmodules` exists.

    `plan()`          returns the phase keys a given tree and set of flags will
                      actually EXECUTE, in order. Dynamic in the inputs, and
                      therefore the one that can be compared against a real
                      traced run of the bash.

A gate that only ran the first would pass a port that dropped a conditional; a gate that only ran the second would pass a port that dropped a phase nobody's fixture happened to enable. `shadow_driver.py` runs both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

# `setup()` lives here since the 2026-09-06 router split. Named once.
SETUP_BODY_FILE = (".ci", "legacy", "run-legacy.sh")


@dataclass(frozen=True)
class Phase:
    """One step of `setup()`.

    `key` is the bash callee's own name, or for the two phases the bash spells inline, the distinctive token of the command it runs. `fatal` records whether `setup()` writes `|| return 1` after it, which is not decoration: `setup_git_identity` is called WITHOUT it at `.ci/legacy/run-legacy.sh:650` while `setup_git_credentials` on the very next line has it, and that asymmetry is a
    decision the bash made on purpose.

    `condition` names the thing that has to be true for the phase to run at all, or "" for the unconditional ones. It is prose for the reader; `plan()` holds the executable form, because a predicate expressed as a string is a predicate nobody can test.
    """

    key: str
    owner: str
    fatal: bool
    condition: str = ""


# THE TABLE, IN `setup()`'s ORDER, `.ci/legacy/run-legacy.sh:600-698`.
PHASES: tuple[Phase, ...] = (
    Phase("setup_node_toolchain", ".ci/lib/setup.sh:43", True),
    Phase("check_node_version", ".ci/lib/local-common.sh:418", True),
    Phase("setup_system_tools", ".ci/lib/setup.sh:248", True),
    Phase(
        "init-submodules.sh",
        ".devcontainer/init-submodules.sh",
        # BEST EFFORT, `|| true`, for the same reason devcontainer.json is: a developer without access to every private submodule should still get a working devbox (.ci/legacy/run-legacy.sh:629-631).
        False,
        condition="$ROOT_DIR/.gitmodules exists",
    ),
    Phase("setup_go_toolchain", ".ci/lib/setup.sh:339", True),
    Phase("setup_gh_cli", ".ci/lib/setup.sh:485", True),
    Phase("ensure_host_tools", ".ci/lib/local-common.sh:587", True),
    Phase("ensure_bashcov_sup", ".ci/lib/local-common.sh:566", False),
    Phase("setup_git_identity", ".ci/lib/setup.sh:609", False),
    Phase("setup_git_credentials", ".ci/lib/setup.sh:689", True),
    # `ensure_deps` is called bare: its exit code is IGNORED by setup(), which is why `fatal` is False here even though the function itself can fail.
    Phase("ensure_deps", ".ci/lib/local-common.sh:203", False),
    Phase(
        "check:env-credential-drift",
        "package.json",
        # ADVISORY AND NEVER FATAL, and the bash argues the point at length (.ci/legacy/run-legacy.sh:660-670): "blocking a developer's bootstrap on a credential only an ops owner can rotate strands the one person who cannot fix it".
        False,
        condition="SKIP_ENV_DRIFT_CHECK != 1 and private/account/.env exists",
    ),
    Phase("ensure_docker_installed", ".ci/lib/local-common.sh:669", True),
    Phase("devbox_ensure_image", ".ci/lib/devbox.sh", True),
    Phase("devbox_up", ".ci/lib/devbox.sh", True, condition="--no-start was not given"),
)

# Every key, for the readers below. A tuple so a caller cannot reorder it.
PHASE_KEYS: tuple[str, ...] = tuple(phase.key for phase in PHASES)

# `setup_docker_probe` IS NOT HERE ON PURPOSE. It is defined at `.ci/lib/setup.sh:575` and called from no file in the repository, measured 2026-09-09 by `grep -rn setup_docker_probe` over the whole tree: the only two occurrences are its own definition and a prose list in `docs/ci-overhaul/06-progress.md:5109`. `setup()` runs `ensure_docker_installed` instead. `host.docker_probe`
# carries the port so the code is not lost; this list carries the truth about what runs.
DEFINED_BUT_UNCALLED: tuple[str, ...] = ("setup_docker_probe",)


def function_body(text: str, name: str) -> str:
    """The body of `<name>() {`, closing brace included. "" when absent.

    THE SAME EXTRACTOR `.ci/rediacc_ci/quality/setup_idempotency.py:240` USES, reimplemented rather than imported for one reason: importing a quality gate
    from a runtime module makes the gate a dependency of the thing it judges. The
    two are compared against each other by this package's tests instead, which is the check that catches a divergence without creating the cycle.
    """
    start = re.compile(r"^%s\(\) \{" % re.escape(name))
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if not inside and start.search(line):
            inside = True
        if inside:
            out.append(line)
            if line.startswith("}"):
                break
    return "\n".join(out)


def function_body_python(text: str, name: str) -> str:
    """The body of a top-level `def <name>(`, by INDENTATION. "" when absent.

    THE PYTHON TWIN OF `function_body`, and it is a separate function rather than a mode flag because the two languages disagree about where a body ends: bash
    ends at a `}` in column zero, Python ends at the next line that is neither
    blank nor indented. A shared implementation with a `language=` argument would
    be two functions wearing one name.

    BY TEXT AND NOT BY `ast`, deliberately. The caller wants SOURCE ORDER of textual mentions inside a function, including the ones inside comments so it can strip them itself; an AST has already thrown the comments away, so a reader could not tell whether a comment-only mention was excluded on purpose or lost by the parser.
    """
    start = re.compile(r"^def %s\(" % re.escape(name))
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if not inside:
            if start.search(line):
                inside = True
                out.append(line)
            continue
        if line.strip() == "" or line[:1] in (" ", "\t"):
            out.append(line)
            continue
        break
    return "\n".join(out)


def strip_comments(body: str) -> str:
    """Comments out, LOAD-BEARING and not tidiness.

    `setup_idempotency.py:127` records the defect this prevents: its first version "matched 'private/renet/go.mod' inside the comment that explains the ordering and concluded the real, correctly-ordered code was broken". The `setup()` body is roughly two thirds comment by line count, and several of those comments name phases in an order the code does not use.
    """
    return "\n".join(re.sub(r"[ \t]*#.*$", "", line) for line in body.split("\n"))


def from_source(root: pathlib.Path) -> list[str]:
    """The phase keys the bash `setup()` contains, in source order.

    A key is counted at its FIRST occurrence, so a phase named again in a later line (a message that mentions `ensure_deps`, say) does not move it. Comments are stripped first; see `strip_comments`.
    """
    path = root.joinpath(*SETUP_BODY_FILE)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    body = strip_comments(function_body(text, "setup"))
    if not body:
        return []
    seen: dict[str, int] = {}
    for number, line in enumerate(body.split("\n")):
        for key in PHASE_KEYS:
            if key in seen:
                continue
            if key in line:
                seen[key] = number
    return [key for key, _ in sorted(seen.items(), key=lambda item: item[1])]


def plan(
    root: pathlib.Path,
    env: dict[str, str],
    *,
    start: bool = True,
) -> list[str]:
    """The phase keys THIS tree and these flags will execute, in order.

    The three conditionals are the bash's, spelled as the bash spells them:

        .gitmodules                 `[[ -f "$ROOT_DIR/.gitmodules" ]]`
        credential drift            `[[ "${SKIP_ENV_DRIFT_CHECK:-}" != "1" ]] &&
                                     [[ -f "$ROOT_DIR/private/account/.env" ]]`
        devbox_up                   `[[ "$do_start" != true ]]` returns early

    NOTE THE THIRD IS A `return 0`, NOT A SKIP. Under `--no-start` the bash prints "Host prepared." and returns, so `devbox_up` is the only phase after the branch and dropping it is the whole of the difference. Written as a conditional here because there is nothing after it; a phase added below `devbox_up` later would have to become an early exit instead, and this comment is the
    warning.
    """
    keys: list[str] = []
    for phase in PHASES:
        if phase.key == "init-submodules.sh" and not (root / ".gitmodules").is_file():
            continue
        if phase.key == "check:env-credential-drift" and not (
            env.get("SKIP_ENV_DRIFT_CHECK", "") != "1"
            and (root / "private" / "account" / ".env").is_file()
        ):
            continue
        if phase.key == "devbox_up" and not start:
            continue
        keys.append(phase.key)
    return keys


def describe(keys: list[str]) -> list[str]:
    """One `NN key` line per phase, ordinal included.

    THE ORDINAL IS THE POINT. A differential that compares an unordered set of phase names passes a port that installs go before jq, which is exactly the trap `.ci/rediacc_ci/setup/tools.py:196-200` warns about. Numbering each line turns the order into part of the value being compared, so a swap changes two lines and the multiset comparison catches it.
    """
    return ["%02d %s" % (index, key) for index, key in enumerate(keys, start=1)]
