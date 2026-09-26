"""`.ci/docker/run-in-web.sh` and `.ci/docker/run-in-render.sh`, as one launcher.

WHAT MOVED. Two HOST-side launchers that assemble a `docker run` command line, 22 effective lines each. `.ci/policy/.language-policy-allowlist` carried a note declaring them deliberately NOT exempt from ruling 7: they were called container entrypoints by the plan box that scoped the exemptions, and they are not one. Nothing about either is structurally bash, so they were left in
the baseline where a drain could reach them. This is that drain.

ONE MODULE AND NOT TWO, and the two files are the argument. Strip the comments and they differ in exactly two tokens: the image tag and the last path segment of the build context. Two Python modules would be that duplication carried across the language boundary and then maintained twice, which is how `run-in-web.sh:31` came to point a reader at its sibling for the one comment
neither copy could hold alone. `TARGETS` is the table those two tokens live in, and every line of behaviour below is written once.

THE COMMAND FORM GAINS A WORD, and it is the only deliberate divergence:

    .ci/docker/run-in-web.sh    <command...>
    python3 -m rediacc_ci.docker.run_in_image web    <command...>
    python3 -m rediacc_ci.docker.run_in_image render <command...>

Nothing in the tree invoked either script. `git grep` over workflows, `package.json`, every other script and the docs finds the two file names only in their own headers, in the policy lists that track them, and in a comment inside one of them: the dead-bash allowlist carried `manual:.ci/docker/run-in-web.sh` precisely because it is the TOP of that chain and nothing above it
can name it. So there was no call site to flip and no caller whose spelling this could break; the target word is a better command line bought at no cost to anybody.

-----------------------------------------------------------------------------
THE WORKSPACE IS MOUNTED AT ITS IDENTICAL HOST PATH, NOT AT /work
-----------------------------------------------------------------------------
This is the load-bearing decision of both twins and the render one said why at length. `step6000_render.py` passes ABSOLUTE host paths (the output mp4, `--props`, and `--browser-executable` pointing at `remotion/chrome-cpu-raster.sh`) and sets cwd to the remotion directory; a `/work` mount makes every one of those dangle inside the container. The chrome wrapper then resolves
`node_modules/.remotion/chrome-headless-shell` relative to itself, so the SAME browser binary runs in both paths, against the image's system libraries.

`node_modules` therefore comes FROM the mounted host tree and is never shadowed by an image copy. Host and image are both glibc x86_64 and the Remotion compositor and chrome-headless-shell binaries are downloaded prebuilt rather than compiled against the host, so sharing them across the boundary is safe in a way that a Python venv, whose shebangs are absolute, is not.

The sibling launcher `rediacc_ci.quality.browser_smoke` binds at `/work` instead and its own docstring records the divergence. It can, because the gate it launches only ever prints paths relative to the root.

-----------------------------------------------------------------------------
THE FOUR THINGS A TRANSCRIPTION OF THESE TWO FILES GETS WRONG
-----------------------------------------------------------------------------
  THE NOTE IS ON STDERR, AND SO IS THE BUILD LINE. `note: docker not found` and
  `building <image> (first run only)` are both `>&2` in the twins, because stdout belongs to whatever command the caller asked for. A launcher that announced itself on stdout would corrupt every `$(run-in-web.sh ...)` capture, and a comparison that merged the two streams could not see it happen.

  A FAILED BUILD NEVER REACHES `docker run`. The twins run under
  `set -euo pipefail`, so a non-zero `docker build` aborts with the build's own exit code. `return rc` below is that `set -e`, spelled out. The healthy machine takes the other branch every time, which is why this half is driven by a scenario rather than left to a reading.

  `$(id -u)` INSIDE AN ARGUMENT LIST DOES NOT ABORT ON FAILURE. With `id`
  absent, bash prints `id: command not found` twice, substitutes the empty string for both, and hands docker a literal `-u :`. `id_value` reproduces that rather than calling `os.getuid()`, for the reason `browser_smoke.id_value` records at length: the twin's observable behaviour on a host with no `id` is part of what equivalence means, and a port that quietly improved it would
  be a different program.

  THE CONTAINER REPLACES THIS PROCESS. `os.execvp`, not `subprocess.run`. Both
  twins `exec`, so the caller's signals, exit code and terminal belong to docker and not to a Python parent in the middle.

-----------------------------------------------------------------------------
THE WORKING DIRECTORY, AND WHY IT IS NOT SIMPLY THE ROOT
-----------------------------------------------------------------------------
`case "$PWD" in "$ROOT" | "$ROOT"/*)` keeps the caller's own directory when it sits inside the workspace and falls back to the root when it does not. Since the mount reproduces the host path, that makes `cd packages/www && run-in-web.sh npm run build` behave inside the container exactly as it does outside it. `workdir` below is that `case`, including the part the glob gets right by
accident: `$ROOT-other` is not `$ROOT/*` and does not match, so a sibling directory whose name merely starts with the root's falls back to the root.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys

from rediacc_ci import paths

# How this program names itself in its own diagnostics. The twins used their own paths; a module has no such path, so the module name stands in.
SELF = "run_in_image.py"

# The escape hatch both twins carried, under the name both twins carried.
NO_DOCKER_ENV = "REDIACC_NO_DOCKER"

# Byte for byte the twins' two messages, and both belong on stderr.
NOTE_NO_DOCKER = "note: docker not found, running on the host"
BUILDING = "building %s (first run only)"

# A usage error, matching every other argv dispatcher in this package.
EXIT_USAGE = 2

# What bash reports for a command it cannot `exec`. The twin's own wording carries a line number inside a shell file, which a port cannot and should not reproduce; the code is what callers act on, so the code is what is kept.
EXIT_NOT_FOUND = 127

# Bash's own text for a program that is not on PATH, minus the `<file>: line <n>: ` prefix no port can reproduce.
NOT_FOUND = "%s: command not found"


@dataclasses.dataclass(frozen=True)
class Target:
    """One image this launcher can run in: the tag, and the context that builds it.

    `context` is a tuple of path segments rather than a string, so the build context is joined against the root the same way on every platform and no separator is ever written into a constant.
    """

    name: str
    image: str
    context: tuple[str, ...]


# THE TWO TOKENS THAT DIFFERED BETWEEN THE TWO TWINS, and the whole of what differed. `web` is the Astro plus agent-browser toolchain; `render` is Remotion plus chrome-headless-shell.
TARGETS = (
    Target("web", "rediacc/web:local", (".ci", "docker", "web")),
    Target("render", "rediacc/render:local", (".ci", "docker", "render")),
)


def target_names() -> list[str]:
    """The registered target names, in table order. The introspection seam."""
    return [target.name for target in TARGETS]


def target_for(name: str) -> Target | None:
    """The row `name` selects, or None when the table has no such row."""
    return next((target for target in TARGETS if target.name == name), None)


def id_value(flag: str) -> str:
    """`$(id <flag>)` as bash performs it, NOT `os.getuid()`.

    Two properties of a command substitution sitting INSIDE an argument list are reproduced here, and both are why this is not `str(os.getuid())`:

      * The exit status is DISCARDED. Whatever the command wrote to stdout is
        substituted even when it then failed.
      * A missing command yields the EMPTY STRING and does not abort the script,
        even under `set -euo pipefail`, so docker is handed a literal `-u :` and
        rejects it with an error of its own that names neither `id` nor the
        launcher.

    `id`'s stderr is inherited, exactly as a substitution inherits it.
    """
    try:
        proc = subprocess.run(
            ["id", flag],
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # bash prints `<script>: line 33: id: command not found` and carries on with an empty substitution. The line number is the only part not reproduced.
        print("%s: %s" % (SELF, NOT_FOUND % "id"), file=sys.stderr)
        return ""
    # A substitution strips TRAILING newlines and nothing else.
    return proc.stdout.rstrip("\n")


def workdir(root: str, cwd: str) -> str:
    """The twins' `case "$PWD" in "$ROOT" | "$ROOT"/*) ... ;; *) ... ;; esac`.

    Written as the two comparisons the glob really performs rather than as a prefix test on `root`, because a bare `cwd.startswith(root)` is the transcription bug this case protects against: it accepts `<root>-other`, which the glob does not.
    """
    if cwd == root or cwd.startswith(root + os.sep):
        return cwd
    return root


def docker_argv(
    target: Target, root: str, work: str, uid: str, gid: str, command: list[str]
) -> list[str]:
    """The twins' final `docker run` invocation, token for token.

    `--ipc=host` is load-bearing and both twins said why: Chromium crashes on the default 64MB `/dev/shm` in a container. `-u` drops to the invoking user so outputs land owned by the caller rather than by root, and `HOME` plus `npm_config_cache` are redirected to `/tmp` because that non-root user can write neither the image's baked-in home nor its npm cache.
    """
    return [
        "docker",
        "run",
        "--rm",
        "--ipc=host",
        "-u",
        "%s:%s" % (uid, gid),
        "-e",
        "HOME=/tmp",
        "-e",
        "npm_config_cache=/tmp/.npm",
        "-v",
        "%s:%s" % (root, root),
        "-w",
        work,
        target.image,
        *command,
    ]


def ensure_image(target: Target, root: str) -> int:
    """`docker image inspect || { echo ...; docker build ...; }`, with its exit code.

    Both of `inspect`'s streams are discarded, as the twins discard them: the question asked is whether the image is there, and the answer to "it is not" is the build, not docker's wording. The build's own streams are INHERITED, so its progress reaches the caller unaltered.
    """
    try:
        inspect = subprocess.run(
            ["docker", "image", "inspect", target.image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        inspect_rc = inspect.returncode
    except FileNotFoundError:
        # REACHABLE, AND NOT BY A ROUTE ANYONE WOULD GUESS. The `docker` guard in `main` cannot have run when this arm is entered with no command to run, because bash falls out of the escape hatch in that case; see the comment there. The twin reaches the same line and bash answers status 127, which the `||` then treats as "the image is absent".
        #
        # AND IT SAYS NOTHING WHILE DOING IT. Bash writes its own `docker: command not found` to the FAILING COMMAND'S stderr, and this line's stderr is the `2>&1` that follows it into `/dev/null`. A port that reported the absence here would be one line louder than the twin on a host with no docker, which is exactly what the first run of this differential caught.
        inspect_rc = EXIT_NOT_FOUND
    if inspect_rc == 0:
        return 0
    print(BUILDING % target.image, file=sys.stderr)
    sys.stderr.flush()
    try:
        build = subprocess.run(
            ["docker", "build", "-t", target.image, os.path.join(root, *target.context)],
            check=False,
        )
    except FileNotFoundError:
        # The same absence, one line later, where the `||` no longer catches it: `set -e` aborts the twin with bash's own 127.
        print("%s: %s" % (SELF, NOT_FOUND % "docker"), file=sys.stderr)
        return EXIT_NOT_FOUND
    return build.returncode


def _exec(argv: list[str]) -> int:
    """`exec argv`. Returns 127 the way bash does when it cannot start the program."""
    try:
        os.execvp(argv[0], argv)  # noqa: S606 -- forwarding exec, same shape as the twins'
    except OSError:
        # bash: `<script>: line 14: exec: <name>: not found`, exit 127. The prefix carries a line number this port does not reproduce; the code is compared verbatim.
        print("%s: exec: %s: not found" % (SELF, argv[0]), file=sys.stderr)
        return EXIT_NOT_FOUND
    return 1  # pragma: no cover - unreachable; execvp either replaces this process or raises


def usage(problem: str) -> int:
    """Say what is wrong and what the table serves, on stderr, and exit 2."""
    print("%s: %s" % (SELF, problem), file=sys.stderr)
    print(
        "%s: usage: python3 -m rediacc_ci.docker.run_in_image <%s> [command...]"
        % (SELF, "|".join(target_names())),
        file=sys.stderr,
    )
    return EXIT_USAGE


def main(argv: list[str]) -> int:
    """Run `argv[1:]` inside `argv[0]`'s image. Returns an exit code, or never returns."""
    if not argv:
        return usage("no target given")
    target = target_for(argv[0])
    if target is None:
        return usage("unknown target: %s" % argv[0])
    command = list(argv[1:])
    root = str(paths.repo_root())

    no_docker = os.environ.get(NO_DOCKER_ENV, "0")
    if no_docker == "1" or shutil.which("docker") is None:
        if no_docker != "1":
            print(NOTE_NO_DOCKER, file=sys.stderr)
            sys.stderr.flush()
        if command:
            return _exec(command)
        # AND WITH NO COMMAND THE ESCAPE HATCH IS NOT AN EXIT, which is the one thing about these two files a reading does not produce and the differential did. `exec` with no arguments and no redirections is a NO-OP in bash that returns success, so `exec "$@"` with zero positional parameters neither replaces the shell nor ends it: control falls out of the `if` and carries
        # straight on into the docker arm below. An early `return 0` here read as the right answer and disagreed with the twin on the first run. Reproduced rather than tidied, because the twins' behaviour is what equivalence means.

    rc = ensure_image(target, root)
    if rc != 0:
        return rc

    # ORDER IS THE TWINS'. The build happens first, then the `case` picks the working directory, then the two substitutions expand as the exec's argv is built. A port that resolved the ids before the build would exec the same command and exit the same way, and only the call log would show it.
    work = workdir(root, os.getcwd())
    uid = id_value("-u")
    gid = id_value("-g")
    return _exec(docker_argv(target, root, work, uid, gid, command))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
