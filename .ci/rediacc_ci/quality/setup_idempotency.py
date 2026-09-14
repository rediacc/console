r"""The machine-setup path must stay idempotent, guarded, and honest.

Ported from `.ci/scripts/quality/check-setup-idempotency.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS. Seven invariants, each paid for by a defect
found while building this feature.
-----------------------------------------------------------------------------

  A. Every mutating step is GUARDED, so a second `./run.sh setup` is a no-op.
  B. `./run.sh setup --check` reports and mutates nothing.
  C. Port derivation is deterministic and per-worktree distinct, so a devbox
     URL survives a reboot and two worktrees never collide.
  D. A build helper never reports success from a file that already existed.
     `ensure_renet_built` used to run `(cd renet && ./build.sh dev)` without
     checking its exit code and then test only `[[ -f $renet_bin ]]`. A failed
     rebuild left the PREVIOUS binary in place, so the function reported
     success and wrote a content stamp for sources it had not built -- and the
     stamp matched forever after, making the failure unrepeatable. Observed
     live: asset staging aborted and the run still printed EXIT=0.
  E. A status label must never contradict its HTTP code. `devbox status` probes
     each proxy route and prints a word next to the code. "OK (404)" shipped for
     one commit: Drizzle Studio answers 404 at / by design, so calling that
     success is tempting -- and it would then hide a genuine 404 on any other
     route behind the same label. Reachability is not success. Static shell
     checks cannot see this: "OK" and "404" are both valid text.
  F. A path-scoped redirect must also be method-scoped. Paid for on 2026-08-24:
     a router matching Host(...) && Path(`/`) redirected the devbox database
     route's root to a hosted UI. Drizzle Studio's API endpoint IS `POST /`, so
     that rule 307'd the API itself and the UI spun in a retry loop -- invisible
     to every static check because the labels are just strings, and invisible to
     a GET-only probe because GET was the half that worked. The redirect has
     since been removed, so this assertion guards the CLASS, not the instance.
  G. setup() must initialise submodules BEFORE any phase that reads one. Paid
     for on 2026-08-24: setup() never initialised submodules at all, while
     CONTRIBUTING.md's quickstart is `git clone && ./run.sh setup` and its table
     claimed setup did it. The docker phase reads private/renet/go.mod to choose
     the Go version, so on a genuinely fresh clone setup died with "Cannot
     determine the required Go version" -- a message that names neither
     submodules nor the file. ORDER is the invariant, not mere presence: an init
     call placed after the phase that reads a submodule path fixes nothing, and
     reads as correct in a diff.

Control-first: every assertion is re-run against a copy carrying the original
defect, with a vacuity check that the mutation applied. A control that does not
fire fails this gate rather than letting it report a green it did not earn.

Hermetic: no docker, no network, no package installs.

-----------------------------------------------------------------------------
THE TWO INCIDENTS BEHIND CHECK B'S SETTLE POLL, both carried verbatim because
they are the reason the assertion has the shape it has.
-----------------------------------------------------------------------------

A NEIGHBOUR'S TEST FIXTURE IS NOT EVIDENCE ABOUT `setup --check`. This snapshot
is taken twice around one command, and under `npm run ci` twenty-two gates share
the tree. `gate-test:gate-paths-exist` plants a scan fixture INSIDE the repo on
purpose -- the detector it controls globs `.ci/scripts/**/*.ts`, so a fixture
outside the tree would prove nothing -- and names it
`.gate-paths-exist-<kind>-fixture.<pid>.ts`. If that lands between the two
snapshots, check B reports "setup --check changed the working tree" over a file
`run.sh` never touched. Observed 2026-08-31 in the pre-push lane:

    FAIL B: setup --check changed the working tree
    < ?? .ci/scripts/.gate-paths-exist-noise-fixture.2530850.ts

The filter is deliberately the DOTTED, PID-SUFFIXED fixture shape those gates
already share, applied to BOTH snapshots so it cannot hide a real change: a path
`setup --check` actually created would have to be named like another gate's
throwaway fixture to slip through, and nothing under run.sh is.

A DELTA MUST PERSIST BEFORE IT IS BLAMED ON `setup --check`. The filter above
pins ONE fixture shape, and shape-filtering is whack-a-mole: on 2026-09-03 this
assertion failed under `ci:quick` over a TRACKED file it had no pattern for --

    FAIL B: setup --check changed the working tree
    >  M .ci/scripts/version/resolve-version.sh

-- which `run.sh` never writes and which was byte-identical to HEAD moments
later. Some neighbour among the 291 gates sharing this tree had it open across
the two snapshots. So test the property that actually distinguishes the two: a
change `setup --check` made is STILL THERE afterwards, and a neighbour's scratch
is not. Poll back toward the `before` snapshot for a bounded window; recovering
means the delta was never ours. This keeps the assertion able to fail -- a real
mutation never reverts, so it burns the full window and is then reported --
while removing a false accusation that names the wrong command and sends the
reader hunting through run.sh.

THE POLL IS SCOPED TO THE DELTA PATHS, not to the whole tree, and that is the
difference between a settle test that can succeed and one that cannot. Comparing
the WHOLE snapshot means any unrelated neighbour among the 300 gates sharing
this tree -- one that touches a file this delta never mentioned -- keeps the
equality false for the rest of the window. B then reports "delta persisted 15s"
about a path that settled in one, which is the same false accusation the
paragraph above exists to remove, arriving by a second door.

-----------------------------------------------------------------------------
THE OTHER INLINE NOTES, carried across.
-----------------------------------------------------------------------------

CHECK C TAKES A ROOT, NOT A FILE. The subject moved in W7 phase 1 and moved
again in W7P5-b. `.ci/lib/find-port.sh` was a delegating shim over
rediacc_ci.core.ports, so mutating the shim proved nothing -- the digest it used
to compute was not there any more -- and the shim is now DELETED outright. What
this takes is a ROOT, turned into the PYTHONPATH the subprocess runs under, so
the control can point it at a COPY of the package with the digest line broken.
That is a strictly stronger control than the original: it fails unless the
derivation actually reaches that copy of the Python.

FIVE SAMPLES, NOT TWO. The control for check C plants a random digest, and a
random value mod 100 repeats itself about 1% of the time -- so a two-sample
comparison let the planted defect pass at that rate and the gate reported
"CONTROL DID NOT FIRE" at random. Five agreeing samples drops that to ~1e-8
while costing microseconds. A flaky control is worse than no control: it teaches
the reader to re-run until green. (The planted value was `$RANDOM` while the
implementation was bash; it is `random.randbytes` now that it is Python. The
arithmetic is unchanged.)

CHECK G STRIPS COMMENTS, and that is load-bearing. The first version matched
"private/renet/go.mod" inside the comment that explains the ordering and
concluded the real, correctly-ordered code was broken. Same family as the gate
that matched "binary" against a PATH: judge the code, not the prose describing
it.

WHERE setup() LIVES. The 2026-09-06 router split left run.sh a 120-line
dispatcher and moved every verb body to .ci/legacy/run-legacy.sh. This gate read
run.sh and said "no setup() function", which is the refusal working: a scan
whose subject moved must go red rather than pass over an empty function. One
name, three readers.

THE F CONTROL PLANTS THE EXACT DEFECT -- a redirect router on Path(`/`) with no
Method. The current tree has no redirect at all, so without that control the
assertion would be vacuously green.

THE G CONTROL IS TWO PLANTS, because presence and ORDER are different defects
and a check that only notices absence would pass the one that actually shipped
later.

THE C CONTROL COPIES THE PACKAGE rather than editing it in place, and that
matters twice over: this gate must never write into the tree it is checking, and
other sessions share this checkout.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

EVERY SUBPROCESS THE TWIN RUNS IS STILL RUN. The slot is derived by running
`rediacc_ci.core.ports derive-slot` as a CHILD under the control's PYTHONPATH
(it used to be sourced out of a bash shim, deleted in W7P5-b; importing the
module in-process instead would read THIS interpreter's copy and the broken-copy
control would go permanently green). `devbox_route_label` is still sourced out
of `devbox.sh` through `bash -c`, exactly as the twin invokes it.
Re-implementing either in Python would test this module's idea of what those
functions do rather than what they do, and check E in particular exists because
"OK" and "404" are both valid text to a static reader.

THE `awk` FUNCTION-BODY EXTRACTOR IS TRANSLATED, NOT SHELLED OUT, because it is
four lines and its exact semantics matter: it starts at a line matching
`^<name>\(\) \{`, prints every line from there INCLUDING the closing `}`, and
stops at the first line whose first character is `}`. A body containing an
indented `}` is unaffected; a body containing a column-0 `}` would be truncated,
which is the twin's behaviour and is why every function in the subject files is
written with its brace in column 0.

`fail()` WRITES `FAIL ` WITH ONE SPACE, so `scripts/lib/shadow-gate.ts` does not
recognise it through the `FAIL\s\s+` marker it carries for the `gate-controls.sh`
tally. The differential for this pair is therefore recorded with an explicit
`--finding-re`. Carried rather than "fixed": widening the marker would reclassify
prose across the whole estate, and adding a second space here would change the
bytes of a gate CI already reads.

`control()` RUNS ITS SUBJECT IN A SUBSHELL, so a `fail()` inside the mutated run
increments a counter that is then discarded and prints into a captured string
that is then discarded. That is deliberate: a control is asking "does this
assertion REJECT the defect", and the assertion's own complaint about the defect
is not a complaint about the tree. The Python version captures the streams and
the counter the same way.

STREAMS. `fail()` and every CONTROL line go to stderr; `pass()` and the offender
detail go to stdout. Nothing here uses `rediacc_ci.log`: the twin sources no
logger and its lines carry no glyph.
"""

import contextlib
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The escapes, computed only when stdout is a tty and NO_COLOR is unset.
_ANSI = {"RED": "\033[0;31m", "GREEN": "\033[0;32m", "NC": "\033[0m"}

# The shape of another gate's throwaway fixture: a DOTTED, PID-SUFFIXED name.
# Applied to BOTH snapshots so it cannot hide a real change; see the header.
FIXTURE_NOISE_RE = re.compile(r"(^|/)\.[a-z0-9-]+-fixture\.[0-9]+\.[a-z]+$")

# The words a `setup --check` run must actually print. A check that prints
# nothing is indistinguishable from a check that did not run.
REQUIRED_ROWS = ("node", "docker", "image", "devbox", "port block")

# check E's oracle: any of these next to a 4xx/5xx is a contradiction.
SUCCESS_WORDS_RE = re.compile(r"\b(ok|OK|healthy|success|succeeded|fine|good|ready)\b")

# The settle window, in seconds, and the poll interval. See the header for the
# two false accusations that produced it.
SETTLE_SECONDS = 15


def colours(stream=None, env=None) -> dict[str, str]:
    """`[ -t 1 ] && [ -z "${NO_COLOR:-}" ]`, as the three names the twin uses."""
    environ = os.environ if env is None else env
    target = sys.stdout if stream is None else stream
    if environ.get("NO_COLOR"):
        return {"RED": "", "GREEN": "", "NC": ""}
    try:
        tty = bool(target.isatty())
    except (AttributeError, ValueError):
        tty = False
    return dict(_ANSI) if tty else {"RED": "", "GREEN": "", "NC": ""}


class Report:
    """The `fails` counter with its two printers. One object, one counter."""

    def __init__(self, colour: dict[str, str] | None = None) -> None:
        self.colour = colours() if colour is None else colour
        self.fails = 0

    def fail(self, message: str) -> None:
        print("%sFAIL%s %s" % (self.colour["RED"], self.colour["NC"], message), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.colour["GREEN"], self.colour["NC"], message))


def function_body(text: str, name: str) -> str:
    """The body of `<name>() {`, closing brace included. "" when absent.

    awk: `$0 ~ "^"f"\\(\\) \\{" {inside=1} inside {print} inside && /^}/ {exit}`
    The `{exit}` rule runs AFTER the print rule, so the `}` line is included.
    """
    start_re = re.compile(r"^%s\(\) \{" % re.escape(name))
    out: list[str] = []
    inside = False
    for line in text.split("\n"):
        if not inside and start_re.search(line):
            inside = True
        if inside:
            out.append(line)
            if line.startswith("}"):
                break
    # `$(...)` strips trailing newlines; an empty list is the empty string.
    return "\n".join(out)


def read_text(path: pathlib.Path) -> str:
    """File contents, or "" when it cannot be read.

    The twin's `awk ... "$file"` writes "cannot open" to stderr and produces no
    stdout, so the caller sees an empty body and reports the assertion's own
    "not found" message. Same outcome, one fewer stderr line.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def assert_guarded(report: Report, file: pathlib.Path, fn: str, mutation: str, guard: str) -> bool:
    """A: the function either does not mutate, or carries a guard. True when ok."""
    body = function_body(read_text(file), fn)
    if body == "":
        report.fail("A: no function %s in %s" % (fn, file.name))
        return False
    if not re.search(mutation, body):
        return True  # nothing mutating here
    if not re.search(guard, body):
        report.fail("A: %s mutates (%s) with no guard matching /%s/" % (fn, mutation, guard))
        return False
    return True


def check_a(report: Report, lib: pathlib.Path) -> bool:
    """Every mutating setup step is guarded."""
    ok = True
    # Installing Go must be skipped when a good enough Go is present.
    ok &= assert_guarded(
        report,
        lib / "local-common.sh",
        "ensure_go_installed",
        "tar -C /usr/local|curl -fL",
        "_version_gte|command -v go",
    )
    # Installing Docker must be skipped when docker already works.
    ok &= assert_guarded(
        report,
        lib / "local-common.sh",
        "ensure_docker_installed",
        "install-docker|ensure_go_installed",
        "docker version",
    )
    # Host tools must be skipped when already present.
    ok &= assert_guarded(
        report, lib / "local-common.sh", "ensure_host_tools", "apt-get install", "command -v"
    )
    # Creating the container must be skipped when one already runs.
    ok &= assert_guarded(
        report,
        lib / "devbox.sh",
        "devbox_up",
        r"docker run|\$d run",
        "devbox_container_running|devbox_container_id",
    )
    # Pulling the image must be skipped when it is present.
    ok &= assert_guarded(
        report, lib / "devbox.sh", "devbox_ensure_image", "pull", "devbox_image_present"
    )
    return bool(ok)


def tree_snapshot(root: pathlib.Path) -> str:
    """`git status --porcelain`, minus another gate's fixture noise, sorted."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    lines = [line for line in proc.stdout.split("\n") if line != ""]
    kept = [line for line in lines if not FIXTURE_NOISE_RE.search(line)]
    return "\n".join(sorted(kept))


def delta_paths(before: str, after: str) -> str:
    """The paths named by EITHER snapshot but not both, one per line, sorted.

    `diff | sed -n 's/^[<>] *//p' | awk '{print $NF}' | sort -u`: the LAST field
    of a porcelain line, so `?? p` and ` M p` alike yield `p`. A file that
    appeared and one that vanished are both ours to watch.
    """
    before_lines = before.split("\n")
    after_lines = after.split("\n")
    changed = set(before_lines).symmetric_difference(after_lines)
    out = set()
    for line in changed:
        fields = line.split()
        if fields:
            out.add(fields[-1])
    return "\n".join(sorted(out))


def scoped_to(snapshot: str, wanted_paths: str) -> str:
    """The snapshot lines mentioning one of `paths`, sorted. "" for no paths.

    `grep -F -f <(paths)` is a FIXED-STRING, SUBSTRING match, so a path that is
    a prefix of another matches both lines. Carried unchanged.
    """
    if wanted_paths == "":
        return ""
    needles = [p for p in wanted_paths.split("\n") if p != ""]
    kept = [
        line
        for line in snapshot.split("\n")
        if line != "" and any(needle in line for needle in needles)
    ]
    return "\n".join(sorted(kept))


def check_b(report: Report, root: pathlib.Path) -> bool:
    """B: `setup --check` reports and mutates nothing."""
    before = tree_snapshot(root)
    env = dict(os.environ)
    env["NO_COLOR"] = "1"
    try:
        proc = subprocess.run(
            ["./run.sh", "setup", "--check"],
            cwd=str(root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        out = proc.stdout
        rc = proc.returncode
    except OSError:
        # `./run.sh: No such file or directory` under a shell is exit 127 with
        # the message on the captured stream. The message differs; the verdict
        # does not, because none of the required rows appears in either text.
        out = ""
        rc = 127
    after = tree_snapshot(root)

    if before != after:
        settled = False
        seconds = 0
        watched = delta_paths(before, after)
        for i in range(1, SETTLE_SECONDS + 1):
            time.sleep(1)
            seconds = i
            if scoped_to(tree_snapshot(root), watched) == scoped_to(before, watched):
                settled = True
                break
        if settled:
            print(
                "  note: the tree moved and came back within %ds -- a neighbouring gate's"
                % seconds,
                file=sys.stderr,
            )
            print(
                "        scratch file, not setup --check. Not counted against B.", file=sys.stderr
            )
        else:
            report.fail("B: setup --check changed the working tree (delta persisted 15s)")
            for line in _unified_delta(before, after):
                print(line, file=sys.stderr)
            return False

    # It must actually REPORT, not just exit quietly.
    lowered = out.lower()
    for row in REQUIRED_ROWS:
        if row not in lowered:
            report.fail("B: setup --check never mentioned '%s'" % row)
            return False
    # rc is 0 (nothing to do) or 1 (work pending); anything else is a crash.
    if rc > 1:
        report.fail("B: setup --check exited %d" % rc)
        for line in out.split("\n"):
            print("       %s" % line, file=sys.stderr)
        return False
    return True


def _unified_delta(before: str, after: str) -> list[str]:
    """`diff <(before) <(after)` in the shape the twin prints on failure.

    Only reached when B has already decided to fail, so its exact spelling is
    advisory rather than a verdict; the `<`/`>` prefixes are what a reader looks
    for and they are preserved.
    """
    before_set = before.split("\n")
    after_set = after.split("\n")
    out: list[str] = ["< %s" % line for line in before_set if line and line not in after_set]
    out.extend("> %s" % line for line in after_set if line and line not in before_set)
    return out


def derive_slot(root: str, key: str, modulus: str) -> str:
    """`rediacc_ci.core.ports derive-slot <key> <modulus>` out of `<root>/.ci`.

    Shelled out on purpose; see the port notes. It used to go through
    `source find-port.sh; derive_slot ...`, but that shim is DELETED (W7P5-b)
    and PYTHONPATH is what the shim was setting anyway. Prefixed, never
    appended, because the whole point of check C's control is that a broken
    COPY of the package at `<root>` must win over the real one.
    """
    env = dict(os.environ)
    ci_dir = str(pathlib.Path(root) / ".ci")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = ci_dir + (os.pathsep + existing if existing else "")
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.ports", "derive-slot", key, modulus],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def check_c(report: Report, root: str) -> bool:
    """C: port derivation is deterministic and per-worktree distinct."""
    a1 = derive_slot(root, "/home/x/console", "100")
    b1 = derive_slot(root, "/home/x/console/.worktrees/0824-1", "100")

    if a1 == "":
        report.fail("C: derive_slot produced nothing")
        return False

    # FIVE samples, not two. See the header for the 1%-flake this removes.
    for _ in range(4):
        sample = derive_slot(root, "/home/x/console", "100")
        if sample != a1:
            report.fail("C: derive_slot is not deterministic (%s then %s)" % (a1, sample))
            return False
    if a1 == b1:
        report.fail("C: two different worktrees derived the same slot (%s)" % a1)
        return False
    return True


# The four spellings that count as checking the build's exit code. An `if !`
# around the subshell, a `) ||` suffix, or a `|| {` block opener.
BUILD_GUARD_RE = re.compile(
    r'if ! \(cd "\$renet_dir" && \./build\.sh dev\)|build\.sh dev\) \|\||\|\| \{[ \t]*$',
    re.MULTILINE,
)


def check_d(report: Report, file: pathlib.Path) -> bool:
    """D: `ensure_renet_built` checks the build's exit code, not just the file."""
    body = function_body(read_text(file), "ensure_renet_built")
    if body == "":
        report.fail("D: ensure_renet_built not found in %s" % file.name)
        return False
    if not BUILD_GUARD_RE.search(body):
        report.fail("D: ensure_renet_built runs build.sh without checking its exit code")
        return False
    return True


def route_label(lib: pathlib.Path, code: str, hint: str = "") -> tuple[bool, str]:
    """(function exists, its output) for `devbox_route_label <code> [hint]`."""
    suffix = " '%s'" % hint if hint else ""
    proc = subprocess.run(
        ["bash", "-c", "source '%s' 2>/dev/null; devbox_route_label %s%s" % (lib, code, suffix)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.returncode == 0, proc.stdout.strip()


def check_e(report: Report, lib: pathlib.Path) -> bool:
    """E: no status label contradicts its HTTP code."""
    probe = subprocess.run(
        ["bash", "-c", "source '%s' 2>/dev/null; declare -f devbox_route_label >/dev/null" % lib],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode != 0:
        report.fail(
            "E: devbox_route_label is missing from %s; the label logic must stay testable"
            % lib.name
        )
        return False

    # Any 4xx/5xx must NOT be described with a success word.
    for code in ("400", "404", "418", "500", "502", "503"):
        _, out = route_label(lib, code, "hint")
        if out == "":
            report.fail("E: devbox_route_label produced nothing for %s" % code)
            return False
        if SUCCESS_WORDS_RE.search(out):
            report.fail('E: HTTP %s is labelled with a success word: "%s"' % (code, out))
            return False

    # A 502 must name the actual cause rather than a bare failure.
    _, out = route_label(lib, "502", "run account dev")
    if "no backend" not in out.lower():
        report.fail('E: a 502 must say no backend is listening, got: "%s"' % out)
        return False

    # 2xx/3xx must still be reported as reachable.
    for code in ("200", "301"):
        _, out = route_label(lib, code)
        if "live" not in out.lower():
            report.fail('E: HTTP %s should be reported live, got: "%s"' % (code, out))
            return False
    return True


REDIRECT_RE = re.compile(r"middlewares\.\$\{slug\}-[a-z-]+\.redirectregex")


def check_f(report: Report, lib: pathlib.Path) -> bool:
    """F: a path-scoped redirect must also be method-scoped."""
    text = read_text(lib)
    routers = sorted(
        {
            match.replace("middlewares.${slug}-", "").replace(".redirectregex", "")
            for match in REDIRECT_RE.findall(text)
        }
    )
    for router in routers:
        needle = "routers.${slug}-%s.rule=" % router
        rule = ""
        for line in text.split("\n"):
            if needle in line:
                rule = line
                break
        if rule == "":
            report.fail(
                "F: redirect middleware '%s' has no matching router rule in %s" % (router, lib.name)
            )
            return False
        if "Path(" in rule and "Method(" not in rule:
            report.fail(
                "F: router '%s' redirects a Path without scoping the Method; a non-GET "
                "request to that path (an API endpoint) would be redirected instead of "
                "served" % router
            )
            print("       %s" % rule, file=sys.stderr)
            return False
    return True


INIT_RE = re.compile(r"init-submodules\.sh|git submodule (update|init)")
READER_RE = re.compile(r"ensure_docker_installed|private/renet|private/account")


def python_function_body(text: str, name: str) -> str:
    """The body of a top-level `def <name>(`, by INDENTATION. "" when absent.

    THE PYTHON TWIN OF `function_body`, needed because the SUBJECT MOVED. See
    `check_g`: `setup()` was ported to `rediacc_ci.setup.machine.run_setup`, and
    an invariant that only knows how to read bash retires itself at the exact
    moment the port lands. Kept as text rather than `ast`, so the comment
    stripping in `check_g` still applies to the same string either way.
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


def check_g(report: Report, runsh: pathlib.Path) -> bool:
    """G: setup initialises submodules before any phase that reads one.

    TWO SUBJECTS, ONE INVARIANT, and the fallback is the whole point. `setup()`
    was ported to `rediacc_ci.setup.machine.run_setup`; the ordering rule it
    enforces did not move with it, it applies to whichever implementation is
    the live one. Written against the bash alone, this assertion would have gone
    RED at the moment the port succeeded, which is the same trap
    `.ci/scripts/test/gates/test-run-sh.sh:315-327` had to be rewritten to
    escape. `INIT_RE` and `READER_RE` match both languages unchanged: the Python
    names `init-submodules.sh` in its `ctx.run` and `ensure_docker_installed` in
    its `bridge.call`, which are the same two tokens the bash used.

    THE REFUSAL IS WHEN NEITHER EXISTS, which is a tree with no setup at all.
    """
    body = function_body(read_text(runsh), "setup")
    subject = runsh.name
    if body == "":
        port = runsh.parent.parent / "rediacc_ci" / "setup" / "machine.py"
        body = python_function_body(read_text(port), "run_setup")
        subject = "%s run_setup()" % port.name
    # COMMENTS STRIPPED, and that is load-bearing; see the header.
    body = "\n".join(re.sub(r"[ \t]*#.*$", "", line) for line in body.split("\n"))
    if body == "":
        report.fail(
            "G: no setup() in %s and no run_setup() in rediacc_ci/setup/machine.py. "
            "The subject has not moved, it is GONE, and this assertion is checking "
            "nothing." % runsh.name
        )
        return False
    del subject
    lines = body.split("\n")

    init_line = 0
    for number, line in enumerate(lines, start=1):
        if INIT_RE.search(line):
            init_line = number
            break
    if init_line == 0:
        report.fail(
            "G: setup() never initialises submodules. A fresh clone then fails in the "
            "docker phase, which reads private/renet/go.mod, with a message that never "
            "mentions submodules."
        )
        return False

    reader_line = 0
    for number, line in enumerate(lines, start=1):
        if READER_RE.search(line):
            reader_line = number
            break
    if reader_line and init_line > reader_line:
        report.fail(
            "G: setup() initialises submodules AFTER the first phase that reads one "
            "(init at body line %d, reader at %d). Order is the invariant; a late init "
            "reads as correct in a diff and fixes nothing." % (init_line, reader_line)
        )
        return False
    return True


def g_subject(root: pathlib.Path, tmpdir: pathlib.Path, body_file: pathlib.Path):
    """(text, make_copy, docker_anchor, init_line) for whichever setup `check_g` reads.

    ONE INVARIANT, TWO LANGUAGES. Before the cutover the subject is the bash
    `setup()`; after it, `rediacc_ci.setup.machine.run_setup`. The two plants
    below need the subject's TEXT, a place to write the mutated copy that
    `check_g` will find, and the line that marks the first phase which READS a
    submodule. All three differ by language and nothing else does.
    """
    bash_text = read_text(body_file)
    if function_body(bash_text, "setup"):
        return (
            bash_text,
            lambda tag: tmpdir / ("run-%s.sh" % tag),
            "if ! ensure_docker_installed; then",
            '        bash "$ROOT_DIR/.devcontainer/init-submodules.sh" --quiet || true',
        )
    port = root / ".ci" / "rediacc_ci" / "setup" / "machine.py"

    def make(tag: str) -> pathlib.Path:
        # `check_g` derives the port path as `runsh.parent.parent/rediacc_ci/
        # setup/machine.py`, so the copy has to sit in that shape rather than
        # anywhere convenient. The `runsh` it is handed must NOT define setup(),
        # which an empty file satisfies.
        base = tmpdir / tag
        (base / "rediacc_ci" / "setup").mkdir(parents=True, exist_ok=True)
        (base / "legacy").mkdir(parents=True, exist_ok=True)
        (base / "legacy" / "run-legacy.sh").write_text("", encoding="utf-8")
        return base / "rediacc_ci" / "setup" / "machine.py"

    return (
        read_text(port),
        make,
        'bridge.call("ensure_docker_installed"',
        '    ctx.run(["bash", "init-submodules.sh"])',
    )


def g_runsh(written: pathlib.Path) -> pathlib.Path:
    """The path to hand `check_g` for a copy `g_subject` produced.

    For the bash subject that is the file itself; for the Python subject it is
    the empty `legacy/run-legacy.sh` beside it, because `check_g` takes the
    LEGACY path and finds the port relative to it.
    """
    if written.name == "machine.py":
        return written.parent.parent.parent / "legacy" / "run-legacy.sh"
    return written


def run_control(label: str, fn, *args) -> bool:
    """True when the assertion REJECTED the planted defect.

    The twin captures both streams and the return code into one string and looks
    for `rc=0`. A control's own complaint about the defect is not a complaint
    about the tree, so the output is discarded and the counter is private; see
    the port notes.
    """
    private = Report(colour={"RED": "", "GREEN": "", "NC": ""})
    sink = io.StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = sink
    try:
        ok = fn(private, *args)
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    del label
    return not ok


def main(argv: list[str] | None = None) -> int:
    """Run the seven assertions, then the controls. 0 holds, 1 does not."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    lib = root / ".ci" / "lib"
    setup_body_file = root / ".ci" / "legacy" / "run-legacy.sh"
    report = Report()

    print("check-setup-idempotency: guards, report-only check, port derivation, exit-code honesty")

    if check_a(report, lib):
        report.ok("every mutating setup step is guarded")
    if check_b(report, root):
        report.ok("setup --check reports and mutates nothing")
    if check_c(report, str(root)):
        report.ok("port derivation is deterministic and per-worktree distinct")
    if check_d(report, lib / "local-common.sh"):
        report.ok("ensure_renet_built checks the build's exit code")
    if check_e(report, lib / "devbox.sh"):
        report.ok("no status label contradicts its HTTP code")
    if check_f(report, lib / "devbox.sh"):
        report.ok("no path-scoped redirect leaves its method unscoped")
    if check_g(report, setup_body_file):
        report.ok("setup initialises submodules before any phase that reads one")

    control_fails = 0
    red, nc = report.colour["RED"], report.colour["NC"]

    # B-scope controls: the settle poll must ignore a NEIGHBOUR and still catch
    # a real one. The unscoped form compared whole snapshots, so any of the ~300
    # gates sharing this tree touching an unrelated file kept the equality false
    # for the whole window. B then blamed `setup --check` for a path that had
    # settled in one second.
    b_before = "?? a.txt"
    b_after = "?? a.txt\n?? scratch.tmp"  # a neighbour's scratch appeared
    b_paths = delta_paths(b_before, b_after)
    b_settled = "?? a.txt\n?? unrelated-neighbour.tmp"  # scratch gone, a DIFFERENT one arrived
    if scoped_to(b_settled, b_paths) != scoped_to(b_before, b_paths):
        print(
            "%sCONTROL FAILED%s: B-scope -- an unrelated neighbour still blocks settling."
            % (red, nc),
            file=sys.stderr,
        )
        control_fails = 1
    b_persisted = "?? a.txt\n?? scratch.tmp"
    if scoped_to(b_persisted, b_paths) == scoped_to(b_before, b_paths):
        print(
            "%sCONTROL FAILED%s: B-scope -- a PERSISTING delta was reported as settled."
            % (red, nc),
            file=sys.stderr,
        )
        control_fails = 1

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        # C-control: a random slot must be rejected. The mutation lands on
        # rediacc_ci.core.ports, which is where the digest actually lives.
        broken_root = tmpdir / "broken-root"
        (broken_root / ".ci").mkdir(parents=True)
        with contextlib.suppress(OSError):
            # A copy that cannot be made leaves `ports.py` absent, which the
            # VACUOUS branch below reports. Swallowing here and reporting there
            # is the twin's shape: `cp -r` failing and the mutation not applying
            # are the same finding to a reader.
            shutil.copytree(root / ".ci" / "rediacc_ci", broken_root / ".ci" / "rediacc_ci")
        ports_py = broken_root / ".ci" / "rediacc_ci" / "core" / "ports.py"
        if ports_py.is_file():
            mutated = re.sub(
                r"(?m)^    digest = hashlib\.sha256.*$",
                '    digest = __import__("random").randbytes(4).hex()  # PLANTED',
                ports_py.read_text(encoding="utf-8"),
            )
            ports_py.write_text(mutated, encoding="utf-8")
        if not ports_py.is_file() or "PLANTED" not in ports_py.read_text(encoding="utf-8"):
            print(
                "%sCONTROL IS VACUOUS%s: C -- mutation did not apply." % (red, nc), file=sys.stderr
            )
            control_fails = 1
        elif not run_control("C (deterministic ports)", check_c, str(broken_root)):
            print(
                "%sCONTROL DID NOT FIRE%s: C (deterministic ports) -- the planted defect passed."
                % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

        # D-control: restore the unchecked invocation.
        lc_broken = tmpdir / "lc-broken.sh"
        lc_broken.write_text(
            read_text(lib / "local-common.sh").replace(
                'if ! (cd "$renet_dir" && ./build.sh dev); then',
                '(cd "$renet_dir" && ./build.sh dev); if false; then',
            ),
            encoding="utf-8",
        )
        if "if false; then" not in read_text(lc_broken):
            print(
                "%sCONTROL IS VACUOUS%s: D -- mutation did not apply." % (red, nc), file=sys.stderr
            )
            control_fails = 1
        elif not run_control("D (build exit code)", check_d, lc_broken):
            print(
                "%sCONTROL DID NOT FIRE%s: D (build exit code) -- the planted defect passed."
                % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

        # E-control: restore the "OK (404)" wording.
        devbox_broken = tmpdir / "devbox-broken.sh"
        devbox_broken.write_text(
            read_text(lib / "devbox.sh").replace('echo "live (HTTP $code)"', 'echo "OK ($code)"'),
            encoding="utf-8",
        )
        if 'echo "OK ($code)"' not in read_text(devbox_broken):
            print(
                "%sCONTROL IS VACUOUS%s: E -- mutation did not apply." % (red, nc), file=sys.stderr
            )
            control_fails = 1
        elif not run_control("E (label vs code)", check_e, devbox_broken):
            print(
                "%sCONTROL DID NOT FIRE%s: E (label vs code) -- the planted defect passed."
                % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

        # F-control: plant the exact defect -- a redirect router on Path(`/`)
        # with no Method. The current tree has no redirect at all, so without
        # this control the assertion would be vacuously green.
        devbox_redirect = tmpdir / "devbox-redirect.sh"
        devbox_redirect.write_text(
            read_text(lib / "devbox.sh") + "_planted_devbox_redirect() {\n"
            "    docker run \\\n"
            '        --label "traefik.http.routers.${slug}-dbui.rule=Host(\\`x\\`) '
            '&& Path(\\`/\\`)" \\\n'
            '        --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"\n'
            "}\n",
            encoding="utf-8",
        )
        if "dbui.redirectregex" not in read_text(devbox_redirect):
            print(
                "%sCONTROL IS VACUOUS%s: F -- the planted redirect was not written." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1
        elif not run_control("F (path redirect without method)", check_f, devbox_redirect):
            print(
                "%sCONTROL DID NOT FIRE%s: F (path redirect without method) -- the planted "
                "defect passed." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

        # G-controls: two plants, because presence and ORDER are different
        # defects and a check that only notices absence would pass the one that
        # actually shipped later.
        # THE CONTROLS FOLLOW THE SUBJECT. `check_g` reads the bash `setup()` while
        # it exists and `machine.run_setup` afterwards, so a control that always
        # plants into the bash goes VACUOUS at the cutover -- observed exactly
        # once, as `CONTROL IS VACUOUS: G(order)`, on a tree where the assertion
        # itself was passing against the Python. `g_subject` returns the file the
        # assertion will really read, the path to hand `check_g`, and the anchor
        # line the ORDER plant inserts after.
        legacy, g_arg, docker_anchor, late_line = g_subject(root, tmpdir, setup_body_file)
        run_noinit = g_arg("noinit")
        run_noinit.write_text(
            "\n".join(line for line in legacy.split("\n") if "init-submodules.sh" not in line),
            encoding="utf-8",
        )
        if "init-submodules" in read_text(run_noinit):
            print(
                "%sCONTROL IS VACUOUS%s: G(absent) -- the init call was not removed." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1
        elif not run_control("G (submodule init absent)", check_g, g_runsh(run_noinit)):
            print(
                "%sCONTROL DID NOT FIRE%s: G (submodule init absent) -- the planted defect "
                "passed." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

        # Move the init AFTER the docker phase: present, but useless.
        late: list[str] = []
        for line in legacy.split("\n"):
            if "init-submodules.sh" in line:
                continue
            late.append(line)
            if docker_anchor in line:
                late.append(late_line)
        run_lateinit = g_arg("lateinit")
        run_lateinit.write_text("\n".join(late), encoding="utf-8")
        if "init-submodules" not in read_text(run_lateinit):
            print(
                "%sCONTROL IS VACUOUS%s: G(order) -- the moved init did not land." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1
        elif not run_control("G (submodule init after the reader)", check_g, g_runsh(run_lateinit)):
            print(
                "%sCONTROL DID NOT FIRE%s: G (submodule init after the reader) -- the planted "
                "defect passed." % (red, nc),
                file=sys.stderr,
            )
            control_fails = 1

    if control_fails == 0:
        report.ok("controls fired: each assertion rejects the original defect")
    else:
        return 1

    if report.fails != 0:
        print(file=sys.stderr)
        print(
            "%s%d assertion(s) failed.%s Rerun: npm run check:ci-setup-idempotency"
            % (red, report.fails, nc),
            file=sys.stderr,
        )
        return 1
    print("%sSetup path invariants hold.%s" % (report.colour["GREEN"], nc))
    return 0


def selftest() -> int:
    """Both directions on every extractor and on the two settle oracles."""
    ctl = Controls("setup-idempotency", floor=27, verbose=True)
    plain = {"RED": "", "GREEN": "", "NC": ""}

    # -- function_body ------------------------------------------------------
    src = "before\nfoo() {\n  body\n}\nafter\n"
    ctl.check(
        "CONTROL: a function body is extracted with its closing brace",
        function_body(src, "foo"),
        "foo() {\n  body\n}",
    )
    ctl.check("VACUITY: an absent function yields nothing", function_body(src, "bar"), "")
    ctl.check(
        "CONTROL: an INDENTED closing brace does not end the body",
        function_body("foo() {\n  if x; then\n  }\n  more\n}\n", "foo"),
        "foo() {\n  if x; then\n  }\n  more\n}",
    )
    ctl.check(
        "MIRROR: a similarly-named function is not this one",
        function_body("foobar() {\n x\n}\n", "foo"),
        "",
    )

    # -- assert_guarded -----------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        target = tmpdir / "lib.sh"

        target.write_text("f() {\n  curl -fL x\n  command -v go\n}\n", encoding="utf-8")
        report = Report(colour=plain)
        ctl.truthy(
            "CONTROL: a mutation with its guard passes",
            assert_guarded(
                report, target, "f", "tar -C /usr/local|curl -fL", "_version_gte|command -v go"
            ),
        )
        target.write_text("f() {\n  curl -fL x\n}\n", encoding="utf-8")
        ctl.falsy(
            "PLANT: the same mutation with the guard REMOVED fails",
            assert_guarded(
                report, target, "f", "tar -C /usr/local|curl -fL", "_version_gte|command -v go"
            ),
        )
        target.write_text("f() {\n  echo nothing mutating\n}\n", encoding="utf-8")
        ctl.truthy(
            "MIRROR: a function that does not mutate needs no guard",
            assert_guarded(report, target, "f", "curl -fL", "command -v go"),
        )
        ctl.falsy(
            "VACUITY: a missing function is a FAILURE, never a silent pass",
            assert_guarded(report, target, "absent", "curl -fL", "command -v go"),
        )

        # -- check_d ---------------------------------------------------------
        report = Report(colour=plain)
        good = tmpdir / "good.sh"
        good.write_text(
            'ensure_renet_built() {\n  if ! (cd "$renet_dir" && ./build.sh dev); then\n'
            "    return 1\n  fi\n}\n",
            encoding="utf-8",
        )
        ctl.truthy("CONTROL: a guarded build passes D", check_d(report, good))
        bad = tmpdir / "bad.sh"
        bad.write_text(
            'ensure_renet_built() {\n  (cd "$renet_dir" && ./build.sh dev)\n'
            '  [[ -f "$renet_bin" ]]\n}\n',
            encoding="utf-8",
        )
        ctl.falsy("PLANT: the ORIGINAL unchecked invocation fails D", check_d(report, bad))
        ctl.falsy(
            "VACUITY: an absent ensure_renet_built is a FAILURE",
            check_d(report, tmpdir / "nothing.sh"),
        )

        # -- check_f ---------------------------------------------------------
        report = Report(colour=plain)
        clean = tmpdir / "devbox-clean.sh"
        clean.write_text("no redirects here\n", encoding="utf-8")
        ctl.truthy("MIRROR: a file with no redirect passes F", check_f(report, clean))
        planted = tmpdir / "devbox-planted.sh"
        planted.write_text(
            'x --label "traefik.http.routers.${slug}-dbui.rule=Host(`x`) && Path(`/`)"\n'
            'y --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"\n',
            encoding="utf-8",
        )
        ctl.falsy(
            "PLANT: the 2026-08-24 defect (Path with no Method) fails F", check_f(report, planted)
        )
        scoped = tmpdir / "devbox-scoped.sh"
        scoped.write_text(
            'x --label "traefik.http.routers.${slug}-dbui.rule=Host(`x`) && Path(`/`) '
            '&& Method(`GET`)"\n'
            'y --label "traefik.http.middlewares.${slug}-dbui.redirectregex.regex=.*"\n',
            encoding="utf-8",
        )
        ctl.truthy("MIRROR: the same redirect WITH a Method passes F", check_f(report, scoped))
        orphan = tmpdir / "devbox-orphan.sh"
        orphan.write_text(
            'y --label "traefik.http.middlewares.${slug}-nope.redirectregex.regex=.*"\n',
            encoding="utf-8",
        )
        ctl.falsy("PLANT: a redirect with no matching router rule fails F", check_f(report, orphan))

        # -- check_g -----------------------------------------------------------
        report = Report(colour=plain)
        ordered = tmpdir / "run-ordered.sh"
        ordered.write_text(
            "setup() {\n  bash init-submodules.sh\n  if ! ensure_docker_installed; then :; fi\n}\n",
            encoding="utf-8",
        )
        ctl.truthy("CONTROL: init BEFORE the reader passes G", check_g(report, ordered))
        late = tmpdir / "run-late.sh"
        late.write_text(
            "setup() {\n  if ! ensure_docker_installed; then :; fi\n  bash init-submodules.sh\n}\n",
            encoding="utf-8",
        )
        ctl.falsy(
            "PLANT: init AFTER the reader fails G (order is the invariant)", check_g(report, late)
        )
        absent = tmpdir / "run-absent.sh"
        absent.write_text(
            "setup() {\n  if ! ensure_docker_installed; then :; fi\n}\n", encoding="utf-8"
        )
        ctl.falsy("PLANT: no init at all fails G (the 2026-08-24 defect)", check_g(report, absent))
        commented = tmpdir / "run-commented.sh"
        commented.write_text(
            "setup() {\n  # reads private/renet/go.mod later on\n  bash init-submodules.sh\n"
            "  if ! ensure_docker_installed; then :; fi\n}\n",
            encoding="utf-8",
        )
        ctl.truthy(
            "MIRROR: a COMMENT naming private/renet is prose, not a reader",
            check_g(report, commented),
        )
        ctl.falsy(
            "VACUITY: an absent setup() is a FAILURE, not a pass over an empty function",
            check_g(report, tmpdir / "nothing.sh"),
        )

    # -- the two settle oracles, which are the B-scope controls -------------
    b_before = "?? a.txt"
    b_after = "?? a.txt\n?? scratch.tmp"
    b_paths = delta_paths(b_before, b_after)
    ctl.check("CONTROL: delta_paths names only the changed path", b_paths, "scratch.tmp")
    ctl.check(
        "CONTROL: an unrelated neighbour does not block settling",
        scoped_to("?? a.txt\n?? unrelated-neighbour.tmp", b_paths),
        scoped_to(b_before, b_paths),
    )
    ctl.truthy(
        "PLANT: a PERSISTING delta is not reported as settled",
        scoped_to("?? a.txt\n?? scratch.tmp", b_paths) != scoped_to(b_before, b_paths),
    )
    ctl.check("VACUITY: an empty path set scopes to nothing", scoped_to("?? a.txt", ""), "")
    ctl.check(
        "CONTROL: a vanished path is watched as well as an appeared one",
        delta_paths("?? a.txt\n?? gone.tmp", "?? a.txt"),
        "gone.tmp",
    )

    # -- the fixture-noise filter -------------------------------------------
    ctl.truthy(
        "CONTROL: another gate's pid-suffixed fixture is filtered out",
        bool(FIXTURE_NOISE_RE.search("?? .ci/scripts/.gate-paths-exist-noise-fixture.2530850.ts")),
    )
    ctl.falsy(
        "MIRROR: an ordinary tracked file is NOT filtered out",
        bool(FIXTURE_NOISE_RE.search(" M .ci/scripts/version/resolve-version.sh")),
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
