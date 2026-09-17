"""Refuse an ad-hoc command when a sanctioned tool exists for it.

The rules live in .claude/hooks/lib/sanctioned.py, one row per class, so a new
class is a row rather than a 22nd copy of this file. See that module's header
for why a table replaced per-guard scripts, and for the deliberately-kept
false positive on prose that merely DESCRIBES a banned shape (operator ruling
2026-08-25, worklist #6a2c9652).

Fails OPEN on its own breakage: if python3 or the registry is unavailable this
exits 0 rather than blocking every command in the session. A guard that bricks
the shell when it breaks gets deleted, and then nothing is guarded.

PORT NOTE ON THE FORK THAT IS NOT ONE. The bash spells the lookup as
`python3 -c` with the command and the library directory in the ENV PREFIX, and
its comment records why:

    Both values go in the ENV PREFIX. An earlier draft passed LIB= as a python
    ARGUMENT, so os.environ["LIB"] raised, `|| exit 0` swallowed it, and the
    guard exited 0 for every command in both directions -- a guard that cannot
    fail. Caught only because the controls assert the BLOCK direction too.

Here the registry is imported into this interpreter instead, so there is no
argument to misplace; what survives from that finding is the shape of the
failure it names, which is why every step below still fails open and why the
differential asserts the block direction on its own cases.
"""

import importlib.util

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-adhoc-sanctioned.sh"
ORDER = 33

# HEREDOC BODIES ONLY: swapping in the full scanner is the failure the header below records, and it turns this guard's strongest fixture green while catching nothing.
DEFECT = ("shellscan._strip_heredocs(cmd)", "shellscan.scan_target(cmd)")

# DERIVED FROM THIS SCRIPT'S OWN LOCATION, not from CLAUDE_PROJECT_DIR. That variable is set by the agent harness and is ABSENT in CI and in a bare shell, where the fallback `.` made the registry unfindable -- and this guard fails open by design, so it silently allowed every banned command. Its own controls caught it, but only once they ran somewhere without the variable.
LIB = hookio.repo_root() / ".claude" / "hooks" / "lib"

_REGISTRY = []

EDGE_CASES = [
    ("the banned watch verb", "gh run watch 123 --exit-status --interval 100"),
    (
        "a hand-rolled poll, whose banned half lives INSIDE quotes",
        'until [ "$(gh run view $R --json status --jq .status)" = "completed" ]; do',
    ),
    # The counters from the registry's own rows: a legitimately different command that must NOT match.
    ("reading a run once is not watching it", "gh run view 123 --json conclusion,jobs"),
    ("the sanctioned tool itself", ".ci/scripts/ci/ci-trace.py --wait"),
    # A heredoc body is DATA, so a note quoting a banned recipe is allowed...
    ("a heredoc body is data", "cat > note.md <<'EOF'\ngh run watch 123\nEOF"),
    # ...while the quoted residue is refused, knowingly (operator ruling).
    ("quoted prose is still refused, and that is the ruling", "echo 'gh run watch 123'"),
]


def _registry():
    """`import sanctioned`, once, failing open exactly as the bash does.

    The bash's inner script wraps the import in `except Exception: sys.exit(0)`
    and lets any later failure fall to `|| exit 0`. Both are reproduced by the
    empty list this returns on any failure, since `match` over no rows is None.
    """
    if _REGISTRY:
        return _REGISTRY[0]
    path = LIB / "sanctioned.py"
    try:
        spec = importlib.util.spec_from_file_location("sanctioned", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 -- `except Exception: sys.exit(0)` in the twin
        module = None
    _REGISTRY.append(module)
    return module


def run(ev):
    # `CMD=$(... jq -r ...) || exit 0` followed by `[ -n "$CMD" ] || exit 0`:
    # a jq FAILURE and an empty command take the same branch, so one test covers both. An absent key is still the four characters `null`, which this guard scans like any other string.
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    if not (LIB / "sanctioned.py").is_file():
        return hookio.ALLOW
    if not hookio.have("python3"):
        return hookio.ALLOW

    # HEREDOC BODIES ONLY, and the quotes deliberately STAY. Every other guard
    # in this sweep moved to hook_scan_target, which also strips quoted spans;
    # doing that here broke the guard's best case, and the failure is worth recording because it marks the limit of the technique.
    #
    # This guard's targets legitimately live INSIDE quotes. Its strongest fixture is a hand-rolled watch loop -- `until [ "$(gh run view $R --json
    # status ...)" = completed ]` -- where the banned command sits in a command
    # substitution inside a quoted test. Prose-stripping deleted exactly the part that matters and the case went green while catching nothing.
    #
    # A heredoc body is different: it is DATA, never executed, so dropping it is safe and it kills the false positive that actually costs something here -- a worklist note or a doc quoting a banned recipe. The residue is that `echo 'gh run watch 123'` is still refused. That is the price of seeing inside quotes, it is paid knowingly, and the sanctioned alternative is in the message.
    scan = shellscan._command_substitution(shellscan._strip_heredocs(cmd))

    module = _registry()
    if module is None:
        return hookio.ALLOW
    try:
        row = module.match(scan)
        msg = shellscan._command_substitution(module.message(row) + "\n") if row else ""
    except Exception:  # noqa: BLE001 -- a raising registry is `|| exit 0` in the twin
        return hookio.ALLOW

    if msg != "":
        ev.warn(msg)
        return hookio.DENY
    return hookio.ALLOW
