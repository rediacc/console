"""The test tables of `block_self_matching_pgrep`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("the self-matching loop", "until pgrep -f wl_wait.py; do sleep 5; done"),
    ("the same with a negation", "while ! pgrep -f test-suite.sh; do sleep 5; done"),
    ("a quoted pattern", "until pgrep -f 'test-suite.sh' >/dev/null; do sleep 5; done"),
    ("a double-quoted pattern", 'until pgrep -f "test-suite.sh"; do sleep 5; done'),
    # The documented remedy, which must pass BY CONSTRUCTION.
    (
        "the bracket-class remedy",
        "until ! pgrep -f '[t]est-suite.sh' >/dev/null; do sleep 5; done",
    ),
    # SCOPE: loops only.
    ("a one-shot diagnostic is not blocked", "pgrep -cf wl_wait"),
    # The 2026-08-28 anchoring, in the sentence that found it.
    (
        "prose naming the trap is not the trap",
        "echo 'TRAPS.md explains why until pgrep -xf never exits'",
    ),
    # An unparseable regex is not a verdict: allow what cannot be judged.
    ("an unparseable pattern", "until pgrep -f '[' ; do sleep 5; done"),
    ("a flag cluster with f in it", "until pgrep -af wl_wait.py; do sleep 5; done"),
    ("a loop with no pgrep at all", "until [ -s out.txt ]; do sleep 5; done"),
    # 2026-09-24, #165e1017: a one-shot bracketed pgrep after a correct loop, its literal text elsewhere in the command.
    (
        "a one-shot pgrep after a correct loop is not judged",
        (
            "until ! pgrep -f '[r]x -n auto' >/dev/null; do sleep 10; done; "
            "setsid --wait uv-tools/bin/pytest -q t.py; pgrep -af '[u]v-tools/bin/pytest'"
        ),
    ),
    (
        "a loop in a heredoc body is text",
        "cat <<'EOF' > w.sh\nuntil pgrep -f wl_wait.py; do sleep 5; done\nEOF",
    ),
    (
        "a self-matching loop after a heredoc still fires",
        "cat <<EOF\nx\nEOF\nuntil pgrep -f wl_wait.py; do sleep 5; done",
    ),
    # 2026-09-24, #23430673: the two incidents, verbatim.
    (
        "a self-matching pgrep whose status is used",
        'pgrep -f "lead_run.py 10" >/dev/null && echo running',
    ),
    (
        "a self-matching pkill kills its own shell",
        'pkill -f "pytest -q -n 8 rediacc_hooks/tests" ; echo done',
    ),
    # The remedy the message gives, which must pass BY CONSTRUCTION.
    (
        "the bracket remedy for a status probe",
        "pgrep -f '[l]ead_run.py 10' >/dev/null && echo running",
    ),
    ("the bracket remedy for pkill", "pkill -f '[p]ytest -q -n 8 rediacc_hooks/tests'"),
    ("an if on a self-matching pgrep", "if pgrep -f wl_wait.py >/dev/null; then echo up; fi"),
    ("a negated status", "! pgrep -f wl_wait.py >/dev/null || echo gone"),
    ("the status read through $?", "pgrep -f wl_wait.py >/dev/null; echo $?"),
    ("pids fed to kill by substitution", "kill $(pgrep -f wl_wait.py)"),
    ("pids fed to kill through xargs", "pgrep -f wl_wait.py | xargs kill"),
    ("options before -f", "pgrep -u developer -f wl_wait.py && echo up"),
    ("a pkill signal before -f", "pkill -9 -f wl_wait.py"),
    ("a named pkill signal before -f", "pkill -HUP -f wl_wait.py"),
    ("pkill inside a shell wrapper", "bash -c 'pkill -f wl_wait.py'"),
    ("--full is -f", "pkill --full wl_wait.py"),
    # Not refused: no -f matches the process NAME, never a command line.
    ("pkill without -f", "pkill wl_wait"),
    ("pgrep without -f, status used", "pgrep wl_wait >/dev/null && echo up"),
    # Not refused: a listing's result is not used.
    ("a one-shot listing", "pgrep -af wl_wait.py"),
    # Not refused: a mention is not a run.
    ("pkill named in prose", "echo 'never pkill -f wl_wait.py here'"),
    ("pkill in a commit message", 'git commit -m "docs: pkill -f wl_wait.py kills its shell" -- a'),
    ("pkill in a heredoc body is text", "cat <<'EOF' > n.md\npkill -f wl_wait.py\nEOF"),
    # Not refused: the pattern cannot match the command that carries it.
    ("an anchored pattern", "pkill -f '^python3 lead_run'"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    ("a pkill -f launched by find -exec", r"find . -maxdepth 0 -exec pkill -f sleep \;"),
    ("prose naming a launched pkill", "echo find . -maxdepth 0 -exec pkill -f sleep"),
]
