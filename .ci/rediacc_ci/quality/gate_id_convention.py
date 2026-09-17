"""A manifest entry that RUNS a gates/ script must be `gate-test:<name>`.

Ported from `.ci/scripts/quality/check-gate-id-convention.sh`, which is NOT deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the review quote, the narrowness argument, the accepted limitation and the subject change are each load-bearing:

    WHY THIS EXISTS. On 2026-08-08 a new gate under `.ci/scripts/test/gates/` was
    registered as `check:ci-edge-verify-retries` with a `package.json` script,
    while all 57 of its siblings used `id: 'gate-test:<name>'` and invoked the
    script directly. A reviewer caught it and said the thing that made it worth
    fixing:

      "It passes check-ci-parity's assertions either way (nothing enforces the
       gate-test: prefix), so it's not a defect, just an inconsistency for future
       maintainers to notice."

    A convention held by 57 entries and enforced by NONE is one that gets broken
    again by whoever copies the odd one out. This is the enforcement.

    THE INVARIANT IS NARROW, AND THE NARROWNESS IS THE POINT. It is NOT "any
    entry mentioning gates/". Several legitimate `check:ci-*` quality gates name
    a gates/ script in their `ci: { kind: 'test', test: ... }` field -- that
    field says which CI job covers them, not what they run. Flagging those would
    be a false positive that trains people to ignore this gate. The rule applies
    ONLY to what `run` actually executes.

    ACCEPTED LIMITATION (ruled on in the #557 review): the alias unwind is ONE
    hop. A two-hop chain (`run: npm run A` -> `A: npm run B` -> `B: gates/
    script`) would escape resolves_to_gate_script(). No such chain exists, and
    the design principle here is control-first against shapes that have actually
    shipped -- if a two-hop alias ever appears, plant it as a second control and
    widen the unwind THEN, rather than speculatively complicating the resolver
    now.

    ---------------------------------------------------------------------------
    THE SUBJECT IS gates.lock.json, NOT manifest.ts, SINCE 2026-09-06 (W2.4a).

    This gate used to run a regex over the 5,700-line TypeScript literal in
    `scripts/ci-runner/manifest.ts`:

        re.findall(r"\\{\\s*id:\\s*'([^']+)'\\s*,\\s*run:\\s*'([^']+)'", manifest)

    and it was WRONG, in the silent direction, for as long as it shipped.
    `\\{\\s*id:` allows only whitespace between the opening brace and `id:`, so
    every entry whose leading comment sits INSIDE the brace was invisible.
    Measured on 2026-09-06 at commit ac817a647:

        OLD regex pairs: 373   NEW lock pairs: 420   only in OLD: []
        entries resolving to a gates/ script: OLD 135, NEW 147

    Strict subset, never a superset: the regex saw 373 of 420 entries and 135 of
    the 147 gate scripts it exists to police. Twelve gate-test registrations --
    gate-header, gate-lanes, media-docs, media-portable, media-shims,
    rebase-resolve, resprofile, shadow-gate, shrink-only-composition,
    untagged-commit-branch, vacuity-floors, watchdog-monitor-ordering -- were
    outside the gate's field of view entirely, and the old FLOOR of 40 sailed
    past 373 without a murmur. This is the same scar
    `.claude/hooks/stop/wl_reggate.py` carries in its `_manifest_entries`
    docstring, found there on 2026-08-20 at 259 of 261 seen: a TS-shape nobody
    anticipated makes the set SHORTER while the green line still reads healthy.

    `scripts/ci-runner/gates.lock.json` is that same literal projected to JSON by
    `scripts/gen-gates-lock.ts` and kept faithful by `check:ci-gates-lock`, which
    fails when the two disagree. One parse, no regex archaeology, and a shape
    error is a JSON error rather than a quietly shorter list. Re-running the
    gate's own logic over all 420 entries produced ZERO findings, so widening the
    field of view did not re-scope what the tree is allowed to contain; it only
    stopped the gate lying about how much of it had been read.
    ---------------------------------------------------------------------------

    CONTROL-FIRST, and there are TWO controls because there are two ways to be
    wrong. The first plants the exact 2026-08-08 shape (a gates/ script invoked
    via an `npm run check:ci-*` alias) and requires detection. The second
    truncates the lock and requires the FLOOR to fire, which is the direction the
    old regex failed in and nothing noticed. If either plant passes, the gate
    declares ITSELF broken and exits non-zero.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`evaluate` WAS ALREADY PYTHON, as a heredoc, so this port is that program with the heredoc removed. Its comments are the twin's, kept at the lines they describe, including the two that explain why the floor is corpus-derived and why the sibling count in the CONVENTION message is computed rather than typed.

ARGUMENTS ARE PATHS, NOT CONTENTS, and that is a scar rather than a style choice. The twin's words, carried at the function:

    The previous version passed the whole manifest text through temp files
    precisely because it could not pass it through argv: Linux caps a single
    argument at MAX_ARG_STRLEN (32 pages = 131072 bytes), and manifest.ts crossed
    it on 2026-08-24 at 131359 bytes, one commit after sitting 96 bytes under.
    The symptom was not a gate finding but the interpreter refusing to start:
    "/usr/bin/python3: Argument list too long", exit 126, which reads like a
    broken runner rather than a gate that outgrew its own plumbing.
    gates.lock.json is 171 KB today and would hit the same wall, so the whole
    class is designed out: nothing but a path ever crosses argv, and the control
    writes its planted copies to temp FILES.

That constraint is gone the moment both sides are one process, and the port keeps the path-passing shape anyway. Not out of caution: the CONTROLS write planted copies to temp files and hand `evaluate` their paths, so a port taking contents would have to change the controls too, and a control rewritten during a port is a control nobody has watched fire in its new form.

THE SCOPE LINE IS ON STDERR AND IS NOT PRINTED BY EVERY PATH. `evaluate` writes `# SUBJECTS n of m entries, floor f` to stderr only after the PARSE and FLOOR branches have not fired, because both of those `raise SystemExit(0)` first. The success path then reformats it with `sed 's/^# / scope: /'`. Carried exactly: a reader who greps for `scope:` in a green log is reading the count
of what was actually judged.
"""

import glob
import json
import os
import pathlib
import re
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The prefix that makes a `run` string a gates/ script. THE COLOURS ARE UNCONDITIONAL IN THE TWIN, and so they are here. The twin
# assigns `RED=$'\033[0;31m'` at check-gate-id-convention.sh:81-83 with no tty
# test at all, so it writes escape bytes into a pipe as readily as into a terminal. The first draft of this port printed the glyphs bare, and the W7 P4 cutover differential caught it: same exit code, same words, stdout 311 bytes against the twin's 322. Eleven bytes of escape is not a cosmetic gap, it is the differential failing, and a port that cannot be compared byte for byte
# cannot be cut over. Matching the twin exactly is the requirement; TTY-gating is a separate change for both sides at once, not something to introduce on one side during a move.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

GATES = ".ci/scripts/test/gates/test-"

# The alias form the 2026-08-08 entry used: `npm run [--silent] <key>`, anchored at both ends so a longer command line is not mistaken for a bare alias.
ALIAS_RE = re.compile(r"npm run (?:--silent )?([A-Za-z0-9:._-]+)$")

# The three inputs, repo-relative.
LOCK_REL = "scripts/ci-runner/gates.lock.json"
PKG_REL = "package.json"
GATES_DIR_REL = ".ci/scripts/test/gates"


def resolves_to_gate_script(run: str, scripts: dict) -> bool:
    """Does this `run` string actually EXECUTE a gates/ script?

    One hop of alias unwinding, deliberately. See the header's ACCEPTED LIMITATION: a two-hop chain would escape this, no such chain exists, and the design principle is control-first against shapes that have shipped.
    """
    if run.startswith(GATES):
        return True
    found = ALIAS_RE.match(run.strip())
    if found:
        return str(scripts.get(found.group(1), "")).strip().startswith(GATES)
    return False


def evaluate(lock_path: str, pkg_path: str, gates_dir: str) -> tuple[list[str], list[str]]:
    """One line per violation, plus the scope line. Empty findings means clean.

    Returns (stdout lines, stderr lines) rather than printing, so the two controls can inspect the result the way the twin inspects a captured string. The PARSE and FLOOR branches return with NO scope line, matching the twin's `raise SystemExit(0)` before it is written.
    """
    out: list[str] = []
    try:
        with open(lock_path, encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, ValueError) as exc:
        out.append(
            "PARSE: %s is not readable JSON (%s); cannot check anything. "
            "It is generated by scripts/gen-gates-lock.ts; run check:ci-gates-lock."
            % (lock_path, exc)
        )
        return out, []

    if not isinstance(parsed, list):
        out.append(
            "PARSE: %s is a %s, not the expected JSON array of entries"
            % (lock_path, type(parsed).__name__)
        )
        return out, []

    try:
        with open(pkg_path, encoding="utf-8") as handle:
            scripts = json.load(handle).get("scripts", {})
    except (OSError, ValueError):
        out.append("PARSE: package.json is not valid JSON; cannot resolve npm aliases")
        return out, []

    entries = [
        (g["id"], g["run"])
        for g in parsed
        if isinstance(g, dict) and isinstance(g.get("id"), str) and isinstance(g.get("run"), str)
    ]

    subjects = [(gid, run) for gid, run in entries if resolves_to_gate_script(run, scripts)]

    # THE FLOOR IS CORPUS-DERIVED, per driver-contract section 6: "a floor must be set-based or corpus-derived, never a hand-typed count". The old floor was the literal 40, and 40 is the number that let a 373-of-420 read look healthy.
    #
    # The corpus is the gate scripts ON DISK, deliberately not `git ls-files`. Section 5b of the contract records why: ls-files reads the INDEX, and this program keeps work uncommitted, so a newly written gate script is invisible to the index while being perfectly real to run-all.sh, which globs the directory exactly like this.
    #
    # The direction is the safe one. A NEW script not yet registered lifts the floor and reds this gate, which is a true finding (check:ci-gate-manifest asserts the same set equality). A COLLAPSED reader drops `subjects` below the floor and reds, which is the failure that went unseen for a month: at 135 subjects against 147 scripts, this floor would have fired on the old regex the
    # day it was written.
    on_disk = sorted(glob.glob(os.path.join(gates_dir, "test-*.sh")))
    if not on_disk:
        out.append(
            "FLOOR: no test-*.sh found under %s; the corpus the floor is derived "
            "from is empty, so every assertion below would pass while checking nothing" % gates_dir
        )
        return out, []
    if len(subjects) < len(on_disk):
        out.append(
            "FLOOR: only %d of %d lock entries resolve to a gates/ script, but %d "
            "test-*.sh files exist on disk. The reader is seeing less than the corpus, "
            "and every assertion below would pass over the gap."
            % (len(subjects), len(entries), len(on_disk))
        )
        return out, []

    for gid, run in subjects:
        if not gid.startswith("gate-test:"):
            # The sibling count is DERIVED, never typed. It read "57 siblings" when this gate was written and "147" would be right today, which is exactly how a number in a message goes stale and starts misleading the reader it exists to persuade. Driver contract section 6, applied to prose.
            conforming = sum(1 for i, _ in subjects if i.startswith("gate-test:"))
            out.append(
                "CONVENTION: '%s' runs a gates/ script but is not registered as "
                "gate-test:<name> (%d siblings are); run=%s" % (gid, conforming, run)
            )
        found = ALIAS_RE.match(run.strip())
        if found:
            out.append(
                "ALIAS: '%s' reaches its gates/ script through the npm alias '%s'; "
                "siblings invoke the script directly, so the alias is a second name "
                "for one thing and drifts" % (gid, found.group(1))
            )

    scope = ["# SUBJECTS %d of %d entries, floor %d" % (len(subjects), len(entries), len(on_disk))]
    return out, scope


# The planted entry CONTROL 1 appends. Kept as data so the shape the control plants and the shape the gate forbids are written down once, together.
PLANTED_ID = "check:ci-planted-defect"
PLANTED_ENTRY = {
    "id": PLANTED_ID,
    "run": "npm run %s" % PLANTED_ID,
    "gate": True,
    "leaves": [".ci/scripts/test/gates/test-planted.sh"],
    "ci": {"kind": "local-only", "blocker": "planted control, never real"},
}
PLANTED_SCRIPT = ".ci/scripts/test/gates/test-planted.sh"


def main(argv: list[str] | None = None) -> int:
    """Run both controls, then the real tree. 0 clean, 1 on a finding or a dead control."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    lock = root / LOCK_REL
    pkg = root / PKG_REL
    gates_dir = root / GATES_DIR_REL

    def fail(message: str) -> int:
        print("%s✗%s %s" % (RED, NC, message), file=sys.stderr)
        return 1

    if not lock.is_file():
        return fail(
            "check-gate-id-convention: %s not found; refusing to pass while measuring "
            "nothing. It is generated by scripts/gen-gates-lock.ts and guarded by "
            "check:ci-gates-lock." % lock
        )
    if not pkg.is_file():
        return fail("check-gate-id-convention: %s not found" % pkg)
    if not gates_dir.is_dir():
        return fail(
            "check-gate-id-convention: %s not found; the corpus the floor is derived "
            "from is missing" % gates_dir
        )

    with tempfile.TemporaryDirectory() as tmp:
        control_dir = pathlib.Path(tmp)

        # ---- CONTROL 1: plant the exact shape that shipped on 2026-08-08 ----
        entries = json.loads(lock.read_text(encoding="utf-8"))
        entries.append(PLANTED_ENTRY)
        (control_dir / "lock.json").write_text(json.dumps(entries), encoding="utf-8")

        manifest = json.loads(pkg.read_text(encoding="utf-8"))
        manifest.setdefault("scripts", {})[PLANTED_ID] = PLANTED_SCRIPT
        (control_dir / "package.json").write_text(json.dumps(manifest), encoding="utf-8")

        control_out, _ = evaluate(
            str(control_dir / "lock.json"), str(control_dir / "package.json"), str(gates_dir)
        )
        if not control_out:
            return fail(
                "check-gate-id-convention: CONTROL 1 DID NOT FIRE. A gates/ script "
                "registered under a check:ci-* id via an npm alias -- the exact "
                "2026-08-08 shape -- passed every assertion, so this gate cannot detect "
                "the defect it exists for."
            )
        if not any(line.startswith("CONVENTION:") for line in control_out):
            return fail(
                "check-gate-id-convention: CONTROL 1 fired but produced no CONVENTION "
                "line; it detected something other than the planted shape."
            )

        # ---- CONTROL 2: truncate the lock and require the FLOOR to fire -----
        #
        # This is the control the old version did not have, and its absence is why a reader that saw 373 of 420 entries reported success for a month. A short read must be a RED, not a quieter green.
        short = json.loads(lock.read_text(encoding="utf-8"))[:5]
        (control_dir / "short.json").write_text(json.dumps(short), encoding="utf-8")

        floor_out, _ = evaluate(str(control_dir / "short.json"), str(pkg), str(gates_dir))
        if not any(line.startswith("FLOOR:") for line in floor_out):
            return fail(
                "check-gate-id-convention: CONTROL 2 DID NOT FIRE. A five-entry lock -- a "
                "reader that has collapsed -- did not trip the corpus floor, so a "
                "shrinking field of view would still read as green. Output was: %s"
                % ("\n".join(floor_out) if floor_out else "<empty>")
            )

        # ---- the real run ---------------------------------------------------
        real_out, real_err = evaluate(str(lock), str(pkg), str(gates_dir))

    if real_out:
        print(
            "%s✗%s gate registration does not follow the gates/ convention:" % (RED, NC),
            file=sys.stderr,
        )
        # `printf ' %s\n' "$REAL_OUT"` is ONE format cycle over a quoted multi-line value, so only the first line carries the indent.
        print("  %s" % "\n".join(real_out), file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  Scripts under .ci/scripts/test/gates/ are registered as gate-test:<name>",
            file=sys.stderr,
        )
        print(
            "  with run pointing at the script directly, and no package.json entry.",
            file=sys.stderr,
        )
        print(
            "  The subject is scripts/ci-runner/gates.lock.json, regenerated from", file=sys.stderr
        )
        print(
            "  manifest.ts by scripts/gen-gates-lock.ts; if it is stale, check:ci-gates-lock",
            file=sys.stderr,
        )
        print("  is the gate that says so.", file=sys.stderr)
        return 1

    print(
        "%s✓%s every gates.lock.json entry that runs a gates/ script uses the "
        "gate-test: convention" % (GREEN, NC)
    )
    for line in real_err:
        print(re.sub(r"^# ", "  scope: ", line))
    print("  control 1 fired on the planted check:ci-* alias (%d finding(s))" % len(control_out))
    print(
        "  control 2 fired the corpus floor on a truncated lock, so a shrinking read reds "
        "rather than quietly passing"
    )
    return 0


# --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------


def _write(where: pathlib.Path, entries: list[dict], scripts: dict) -> tuple[str, str]:
    """A lock and a package.json, written by construction."""
    lock = where / "lock.json"
    pkg = where / "package.json"
    lock.write_text(json.dumps(entries), encoding="utf-8")
    pkg.write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return str(lock), str(pkg)


def selftest() -> int:
    """Both directions for the resolver, the floor and each violation class.

    The narrowness is what is being defended here: a `ci: { test: ... }` field
    naming a gates/ script must NOT be a subject, because flagging those "would be a false positive that trains people to ignore this gate".
    """
    ctl = Controls("gate-id-convention", floor=22, verbose=True)

    scripts = {
        "check:ci-alias": ".ci/scripts/test/gates/test-alias.sh",
        "check:ci-other": "tsx scripts/check-other.ts",
    }

    # -- the resolver, both directions --------------------------------------
    ctl.check(
        "PLANT: a direct gates/ invocation resolves",
        resolves_to_gate_script(".ci/scripts/test/gates/test-x.sh", scripts),
        True,
    )
    ctl.check(
        "PLANT: a one-hop npm alias to a gates/ script resolves",
        resolves_to_gate_script("npm run check:ci-alias", scripts),
        True,
    )
    ctl.check(
        "PLANT: the --silent spelling resolves too",
        resolves_to_gate_script("npm run --silent check:ci-alias", scripts),
        True,
    )
    ctl.check(
        "MIRROR: an alias to something that is NOT a gates/ script does not resolve",
        resolves_to_gate_script("npm run check:ci-other", scripts),
        False,
    )
    ctl.check(
        "MIRROR: an unknown alias does not resolve",
        resolves_to_gate_script("npm run check:ci-nope", scripts),
        False,
    )
    ctl.check(
        "MIRROR: a command that merely NAMES a gates/ script does not resolve",
        resolves_to_gate_script("tsx x.ts --covers .ci/scripts/test/gates/test-x.sh", scripts),
        False,
    )
    ctl.check(
        "ACCEPTED LIMITATION: a TWO-hop alias escapes the one-hop unwind",
        resolves_to_gate_script(
            "npm run hop1", {"hop1": "npm run hop2", "hop2": ".ci/scripts/test/gates/test-x.sh"}
        ),
        False,
    )

    with tempfile.TemporaryDirectory() as tmp:
        where = pathlib.Path(tmp)
        gates_dir = where / "gates"
        gates_dir.mkdir()
        for name in ("test-a.sh", "test-b.sh", "test-c.sh"):
            (gates_dir / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")

        conforming = [
            {"id": "gate-test:a", "run": ".ci/scripts/test/gates/test-a.sh"},
            {"id": "gate-test:b", "run": ".ci/scripts/test/gates/test-b.sh"},
            {"id": "gate-test:c", "run": ".ci/scripts/test/gates/test-c.sh"},
        ]

        # -- the clean case ---------------------------------------------------
        lock, pkg = _write(where, conforming, scripts)
        out, err = evaluate(lock, pkg, str(gates_dir))
        ctl.check("MIRROR: a conforming lock produces no finding", out, [])
        ctl.check(
            "and the scope line names what was judged",
            err,
            ["# SUBJECTS 3 of 3 entries, floor 3"],
        )

        # -- the 2026-08-08 shape ---------------------------------------------
        lock, pkg = _write(
            where,
            [*conforming, {"id": "check:ci-alias", "run": "npm run check:ci-alias"}],
            scripts,
        )
        out, _ = evaluate(lock, pkg, str(gates_dir))
        ctl.check("PLANT: the 2026-08-08 shape produces TWO findings", len(out), 2)
        ctl.truthy(
            "PLANT: one of them is the CONVENTION line",
            any(line.startswith("CONVENTION:") for line in out),
        )
        ctl.truthy(
            "PLANT: and one is the ALIAS line", any(line.startswith("ALIAS:") for line in out)
        )
        ctl.truthy(
            "the sibling count in the message is DERIVED, not typed",
            "(3 siblings are)" in out[0],
        )

        # -- a direct gates/ script under the wrong id ------------------------
        lock, pkg = _write(
            where,
            [*conforming, {"id": "check:ci-direct", "run": ".ci/scripts/test/gates/test-d.sh"}],
            scripts,
        )
        out, _ = evaluate(lock, pkg, str(gates_dir))
        ctl.check("PLANT: a direct invocation under a check:ci-* id is ONE finding", len(out), 1)
        ctl.truthy("and it is the CONVENTION line", out[0].startswith("CONVENTION:"))

        # -- the floor, both directions ---------------------------------------
        lock, pkg = _write(where, conforming[:2], scripts)
        out, err = evaluate(lock, pkg, str(gates_dir))
        ctl.truthy("PLANT: a collapsed reader trips the corpus floor", out[0].startswith("FLOOR:"))
        ctl.check("and the FLOOR branch prints NO scope line", err, [])
        lock, pkg = _write(where, conforming, scripts)
        out, _ = evaluate(lock, pkg, str(gates_dir))
        ctl.falsy(
            "MIRROR: a reader that sees the whole corpus does not trip it",
            any(line.startswith("FLOOR:") for line in out),
        )

        # -- an EMPTY corpus is a refusal, not a pass -------------------------
        empty_dir = where / "empty"
        empty_dir.mkdir()
        out, _ = evaluate(lock, pkg, str(empty_dir))
        ctl.truthy(
            "PLANT: an empty gates/ directory refuses rather than passing",
            out and out[0].startswith("FLOOR: no test-*.sh"),
        )

        # -- unreadable inputs ------------------------------------------------
        (where / "broken.json").write_text("{not json", encoding="utf-8")
        out, _ = evaluate(str(where / "broken.json"), pkg, str(gates_dir))
        ctl.truthy("PLANT: an unparseable lock is a PARSE finding", out[0].startswith("PARSE:"))
        out, _ = evaluate(lock, str(where / "broken.json"), str(gates_dir))
        ctl.truthy(
            "PLANT: an unparseable package.json is a PARSE finding too",
            out[0].startswith("PARSE: package.json"),
        )
        (where / "object.json").write_text('{"a":1}', encoding="utf-8")
        out, _ = evaluate(str(where / "object.json"), pkg, str(gates_dir))
        ctl.truthy(
            "PLANT: a lock that is an object rather than an array is refused",
            "not the expected JSON array" in out[0],
        )

        # -- the planted control entry itself ---------------------------------
        lock, pkg = _write(
            where, [*conforming, PLANTED_ENTRY], {**scripts, PLANTED_ID: PLANTED_SCRIPT}
        )
        out, _ = evaluate(lock, pkg, str(gates_dir))
        ctl.truthy(
            "CONTROL: the entry CONTROL 1 plants really does produce a CONVENTION line",
            any(line.startswith("CONVENTION:") for line in out),
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
