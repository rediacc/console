"""Refuse to edit a shell script that a process is CURRENTLY RUNNING.

WHY A HOOK. This is written down in full at docs/agent-reference/TRAPS.md ("Editing a shell script while a background job is RUNNING it"), with the mechanism, the 2026-08-09 incident, and the tell. It was hit again on 2026-08-26, on the SAME file, with the SAME signature: a backgrounded test-hooks.sh died at `line 1179: syntax error near unexpected token 'else'`
while `bash -n` on that exact file was clean. Cost a full suite pass. A trap
documented in that much detail and walked into anyway is one that needs a gate rather than another paragraph.

THE MECHANISM, because the error never points at it. Bash reads a script LAZILY, by byte offset, not into memory. Rewrite the file mid-run and the interpreter resumes at its old offset inside the NEW bytes, so it starts parsing mid-token. The line it names is innocent and may not even exist at that number any more. `bash -n` being clean is the tell: a syntax error the syntax
checker cannot reproduce is not in the file, it is in the READER.

HOOK-CHAIN SIBLINGS ARE NOT A RUNNING JOB. Every guard in a chain executes on every tool call in that chain, including the call carrying your edit -- so editing a pre-edit guard finds that guard "running", permanently, with no moment of quiet to wait for. Its Bash-side sibling hit this on 2026-08-27 and blocked four commands including its own repair. A chain evaluator lives for
milliseconds and is re-read from scratch next call, so the lazy-read window below does not exist for it; a suite or background job running for minutes, which is what this guard is for, still matches and still blocks.

SCOPE: shell scripts only, and only while something is actually running one. A .ts or .py file is read once into memory by its interpreter, so editing it mid-run is merely confusing rather than corrupting. Narrow on purpose -- a guard that refused every edit to any file with a live process would be the over-matching this repo has switched guards off for.

PORT NOTE ON THE THREE PROCESS READS. `pgrep -f`, `ps -o comm=` and
`tr '\\0' ' ' < /proc/<pid>/cmdline` are `proc.pgrep_full`, `proc.is_shell` and `proc.cmdline_tr`. That module exists because these two guards are the only consumers of the process table and each read has a trap attached: `comm` is
truncated to 15 characters on Linux, `ps -o args=` cannot say where the NUL
separators were, and a kernel thread's empty cmdline is invisible to `pgrep -f`. `cmdline_tr` in particular keeps the TRAILING SPACE that `tr` leaves behind, which `cut -d' ' -f1-4` and the grep below cannot see and which a port would therefore drop by accident.

`pattern_for` AND `live_shells` NOW LIVE IN `rediacc_hooks.runningscript`, shared with this guard's Bash-side sibling (PLAN-retire-bash-oracles A3, "P6 change, once there is no twin left to diverge from" -- both twins' own words). Until then each guard carried its own copy, because the two BASH originals duplicated them too and a port whose job was fidelity did not get to unify what its
twin kept apart. There is no twin left, so this file keeps only what is genuinely its own: `run()`, the fixture world and the message.

PORT NOTE ON WHY THIS GUARD'S FIXTURE STARTS A REAL PROCESS. Every branch that produces output is behind "an interpreter is executing this script right now", and nothing in the payload or the environment can fake that: the bash twin consults the real process table through real pgrep. So the fixture below LAUNCHES two `bash <script>` processes, in their own session, and kills them
when the interpreter that built them exits. Both sides then read the same two processes, and the pids in the message are identical because it is literally the same process. Its Bash-side sibling (block-bash-write-to-running-script.sh) reads the same world through the same token rather than starting two more.
"""

from rediacc_hooks import hookio, runningscript
from rediacc_hooks.guards import tables

__getattr__ = tables(
    "block_edit_of_running_script",
    "EDGE_CASES",
    "ENVS",
    "FIXTURES",
    "IDLE_SCRIPT",
    "LIVE_SCRIPT",
    "SIBLING_SCRIPT",
    "WORLD",
    "_BODY",
    "_CHILDREN",
    "_LOCK_FDS",
    "_await_visible",
    "_hold_world_lock",
    "_kill_stale",
    "_pause",
    "_reap",
    "_running_world",
    "_spawn",
)

CHAIN = "pre-edit"
ORDER = 7

# THE LIMIT ARGUMENT, ZEROED. `live_shells` truncates to the first N matches before this guard ever reads them, so pinning it at 0 answers every case as though nothing were running -- local to this file's own `run()`, unlike the old HOOK_CHAIN-exclusion defect this guard carried before its process-table scan moved to `rediacc_hooks.runningscript` (PLAN-retire-bash-oracles A3): a
# defect textually planted into THIS module's source can no longer reach into a function that lives in a different one.
DEFECT = (
    "runningscript.pattern_for(base), 3, path",
    "runningscript.pattern_for(base), 0, path",
)

MESSAGE = """BLOCKED: '%(base)s' is being executed by a live process right now.

  %(running)s

Bash reads a script LAZILY, by byte offset, not into memory. Editing it now
makes the running interpreter resume at its old offset inside your new bytes,
so it starts parsing mid-token and dies with a syntax error naming an INNOCENT
line -- often one that no longer exists at that number. `bash -n` on the file
stays clean throughout, which is what makes the failure so expensive to chase.

This is docs/agent-reference/TRAPS.md, "Editing a shell script while a
background job is RUNNING it". It cost a suite pass on 2026-08-09 and again on
2026-08-26, both times on test-hooks.sh.

Pick one:

  1. Let it finish. The run you would corrupt is usually the one you are
     waiting on anyway, so editing now costs you the result twice.
  2. Edit a COPY and move it into place once the run exits.
  3. If the process is stale rather than working, stop it first -- then the
     edit is safe and this guard goes quiet on its own.
"""

# --------------------------------------------------------------------------- The fixture world: two live shells, at deterministic paths ---------------------------------------------------------------------------


def indented(running):
    """`$(printf '%s\\n' "$RUNNING" | sed 's/^/    /')`, inside the heredoc."""
    return hookio._command_substitution(hookio.sed_sub(r"^", "    ", hookio._printf_line(running)))


def run(ev):
    typed = ev.field("tool_input", "file_path")
    if typed == "":
        return hookio.ALLOW
    # Judged where the write LANDS (`hookio.landing`, review 9c6817f3.1-.4 sweep) AND by the name that was typed (0067b4c2.2): the file edited is the one the edit lands in, whatever a link calls it, while the process table holds the name the script was STARTED under, which may be the link's. So both names are asked; the landing alone allowed an edit through `alias.sh` while `bash alias.sh` was running.
    landed = hookio.landing(typed, ev.field("cwd") or None)[0]
    for path in dict.fromkeys((landed, typed)):
        if not hookio.case_glob(path, "*.sh"):
            continue
        base = path.rsplit("/", 1)[-1]
        running = runningscript.live_shells(
            runningscript.pattern_for(base), 3, path, ev.field("cwd") or None
        )
        if running != "":
            ev.warn_raw(MESSAGE % {"base": base, "running": indented(running)})
            return hookio.DENY
    return hookio.ALLOW
