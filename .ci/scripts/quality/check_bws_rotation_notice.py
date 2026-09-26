#!/usr/bin/env python3
"""check:ci-bws-rotation-notice -- ONE rotation notice, ONE classifier, five emitters that agree.

WHY THIS EXISTS. `agent/plans/PLAN-bws-rotation-on-failure.md` deletes the hand-maintained expiry date and makes a non-zero `bws` the only signal there is. The product of that signal is a procedure, and a procedure that five surfaces each carry their own copy of is five procedures that drift.
So the text lives in exactly one file and the DECISION about when to print it lives in exactly one function, and this gate is what keeps both claims true.

WHAT A GREEN HERE MEANS, stated narrowly. The notice exists and is actionable, the classifier is singular, the deleted expiry file has not come back, and five named emitters still reach the notice. It says nothing about whether any of them would fire against a real dead credential; that is what the gate test, the differential and the trapguard suite are for.

THE ASSERTIONS.
  N1  THE NOTICE IS REAL. Non-empty, and it names `scripts/dev/bws-rotate.py`,
      which is the one actionable line in the whole procedure. A notice that
      stopped naming the script would be a page of reasoning ending nowhere.
  N2  THE NOTICE SAYS THE SIX THINGS PART F DEMANDS, in order: what happened
      and that the four causes are indistinguishable; that nobody can mint
      from here; that a session's part is to report and stop; the three
      explicit prohibitions; what the script does; and what it cannot prove.
  N3  THE SCRIPT IS THERE AND EXECUTABLE. The notice tells an operator to run
      one command, so a missing or non-executable target makes the notice a
      dead end at the worst possible moment.
  N4  THE CLASSIFIER IS SINGULAR. `.claude/hooks/trapguard/dispatch.py` cannot
      import `rediacc_ci`, so it carries a COPY of the two marker tuples. This
      reads both by AST and requires them EQUAL. A copy nobody compares is a
      second implementation; a copy a gate compares is a cache.
  N5  NOBODY ELSE CARRIES A THIRD COPY. `scripts/ops/bws-map-refresh.py`
      delegates through the `rotation-notice` verb and must contain neither
      marker literal, or the delegation is decoration over a private decision.
  N6  THE EXPIRY FILE STAYS DELETED. The file is absent and no non-prose file
      reads it. This is the permanent form of the plan's C1 control, which
      otherwise holds only for as long as somebody remembers.
  N7  FIVE EMITTERS REACH THE NOTICE, each named and each printed. A count
      that silently fell to four is the shape this catches.

ANTI-VACUITY. The emitter set is a fixed list of five paths, every one of which must EXIST and must NAME the notice. A scan that found zero emitters, or a notice of zero bytes, is a failure rather than a quiet pass, and the count is printed on the success line so a reader can see it was not trivial.

THE CONTROLS ARE FIRST AND THEY ARE NOT OPTIONAL. Every assertion above is planted against an in-memory fixture and required to red; the clean fixture is required to stay green. If any control misbehaves this exits non-zero WITHOUT judging the real tree, because a gate whose own controls are broken has no standing to report on anything.

---- gate ----
step: BWS rotation notice
needs: none
selftest: true
lane: quality-security
why: The rotation notice is the entire product of a design that deleted its own
     early warning. One file, one classifier, five emitters: if any of those
     three claims quietly stops being true, the failure a dead credential
     produces goes back to naming nothing a reader can act on.
---- end gate ----
"""

import ast
import os
import pathlib
import subprocess
import sys

import _cipath  # noqa: F401
from rediacc_ci import controls, paths
from rediacc_ci.controls import plant
from rediacc_ci.core import bws_env

ROOT = pathlib.Path(paths.repo_root())

NOTICE_REL = ".ci/config/bws-rotation-notice.txt"
SCRIPT_REL = "scripts/dev/bws-rotate.py"
EXPIRY_REL = ".ci/config/bws-token-expiry.json"
TRAPGUARD_REL = ".claude/hooks/trapguard/dispatch.py"
REFRESH_REL = "scripts/ops/bws-map-refresh.py"

#: The five surfaces the plan names, and the token each must carry to prove it reaches the notice. Listed rather than discovered, because "every file that mentions bws" is a corpus that grows a sixth member by accident and shrinks to four without anyone noticing.
EMITTERS = {
    ".ci/rediacc_ci/core/bws_env.py": "ROTATION_NOTICE_REL",
    REFRESH_REL: "rotation-notice",
    ".github/actions/bws-secrets/action.yml": "bws-rotation-notice.txt",
    TRAPGUARD_REL: "bws-rotation-notice.txt",
    "private/account/scripts/rotation/lib/credentials.ts": "bws-rotation-notice.txt",
}

#: Part F's six required elements, each keyed on a phrase the notice must carry, IN THIS ORDER. Order is asserted because the notice is read top to bottom by someone whose build just died: the prohibitions after the procedure is a page that tells a reader what to do before telling them what not to.
REQUIRED_IN_ORDER = (
    ("the four causes are indistinguishable", "look identical"),
    ("nobody can mint one from here", "no verb that creates or rotates"),
    ("a session reports and stops", "REPORT THIS AND STOP"),
    ("do not ask for the token", "DO NOT ask for the token"),
    ("do not put it in a tracked file", "DO NOT put it in a tracked file"),
    ("do not offer to run the script", "DO NOT offer to run the script"),
)

#: Files allowed to name the deleted expiry file, BY NAME and with the reason, and PRINTED on every run. A quiet exemption is how a gate stops meaning what its name says, so these are listed in the success line rather than folded into it.
#:
#: There is exactly one, and it is the one file that CANNOT stop naming it: the pinned-divergence test asserts that the RECORDING of the retired bash twin still says what the twin said on the day it was recorded. Deleting that mention would delete the evidence that the port diverged on purpose rather than by accident.
EXPIRY_MENTIONS_ALLOWED = {
    ".ci/rediacc_ci/tests/test_core_bws_env.py": (
        "BLOCKER: pins the deliberate divergence. It asserts the GOLDEN recording still "
        "names the expiry file and that the port does not, which is the only thing "
        "separating a decision from drift."
    ),
    ".ci/scripts/quality/check_bws_rotation_notice.py": (
        "BLOCKER: this gate IS the check. Asserting that a file has not come back requires "
        "naming the file, so the checker is the one reader that can never be removed."
    ),
    "scripts/ci-runner/manifest.ts": (
        "BLOCKER: the manifest entry's own prose states WHAT this gate replaced, which is "
        "the only place a reader of the gate table learns why it exists. A rule that reds "
        "on that sentence would be satisfied by deleting the reason."
    ),
}

CONTROL_FLOOR = 29


def notice_findings(text: str) -> list[str]:
    """N1 and N2 over the notice's TEXT, so a control can drive them without a file."""
    out: list[str] = []
    if not text.strip():
        return ["the notice is empty, so every emitter below would print nothing at all"]
    if SCRIPT_REL not in text:
        out.append(
            "the notice does not name %s, which is the one actionable line in it" % SCRIPT_REL
        )
    at = -1
    for label, needle in REQUIRED_IN_ORDER:
        found = text.find(needle, at + 1)
        if found < 0:
            out.append("the notice does not say %s (looked for %r)" % (label, needle))
        else:
            at = found
    return out


def marker_tuples(source: str) -> dict[str, tuple[str, ...]]:
    """Every module-level assignment of a tuple of string literals, by name.

    AN AST WALK AND NOT A GREP, for the reason `test_canonical_sys_path_hop.py` gives about its own corpus: this tree comments heavily ABOUT the strings it matches, and the trapguard rule's own docstring quotes one of them. A grep would read the explanation as a second definition and be "fixed" by deleting the explanation, which is the most valuable text in the file.
    """
    out: dict[str, tuple[str, ...]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Tuple):
            continue
        items = [
            e.value
            for e in node.value.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if len(items) != len(node.value.elts):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = tuple(items)
    return out


def classifier_findings(trapguard_src: str) -> list[str]:
    """N4: the hook's cached copy of the markers must equal the canonical ones."""
    out: list[str] = []
    found = marker_tuples(trapguard_src)
    for name, want in (
        ("BWS_WIRING_MARKERS", bws_env.WIRING_MARKERS),
        ("BWS_ROTATION_MARKERS", bws_env.ROTATION_MARKERS),
    ):
        got = found.get(name)
        if got is None:
            out.append(
                "%s carries no %s, so the hook ring has no markers to key on"
                % (TRAPGUARD_REL, name)
            )
        elif got != tuple(want):
            out.append(
                "%s's %s has drifted from rediacc_ci.core.bws_env: %r against %r"
                % (TRAPGUARD_REL, name, got, tuple(want))
            )
    return out


def third_copy_findings(refresh_src: str) -> list[str]:
    """N5: the refresh script delegates, so it must carry no marker of its own."""
    out: list[str] = [
        "%s contains the marker %r. It reaches the ONE classifier through the "
        "rotation-notice verb; a literal here is a private second decision." % (REFRESH_REL, marker)
        for marker in tuple(bws_env.WIRING_MARKERS) + tuple(bws_env.ROTATION_MARKERS)
        if marker in refresh_src
    ]
    if "rotation-notice" not in refresh_src:
        out.append(
            "%s no longer calls the rotation-notice verb, so a failed bws there prints "
            "no procedure at all" % REFRESH_REL
        )
    return out


#: The path a reader would have to name. Held as a constant so the controls and the scan cannot disagree about the needle.
EXPIRY_NEEDLE = "bws-token-expiry"


def python_reads(source: str, needle: str) -> bool:
    """Does this Python file USE the needle, as opposed to writing ABOUT it?

    THE DISTINCTION IS THE WHOLE POINT, and the first version of this check did not make it. A record of WHY a file was deleted has to be able to name what was deleted; a rule that reds on the mention would be satisfied only by deleting the explanation, which is the most valuable text in the file and the exact inversion of what a liveness check should reward.

    A COMMENT IS INVISIBLE TO THE AST, which does the first half for free. The second half is docstrings: they ARE string constants, so they are collected and then subtracted by identity, leaving only the strings a program could actually open. A path a reader uses is one of those; a paragraph explaining its deletion is not.

    UNPARSEABLE MEANS UNCHECKED AND THEREFORE TRUE. A file this cannot read is a file whose reads it cannot rule out, and answering "no reader here" about bytes that were never parsed is precisely the vacuous green this estate exists to refuse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and needle in node.value
        and id(node) not in docstrings
        for node in ast.walk(tree)
    )


def expiry_readers(root: pathlib.Path) -> list[str]:
    """N6: tracked, non-prose files that still READ the deleted expiry file.

    PROSE IS EXCLUDED BY SUFFIX FIRST. A plan or a measurement record that describes the deletion has to be able to name what was deleted, so `.md` never appears here at all.

    THEN PYTHON IS FILTERED BY USE. `python_reads` separates a path a program could open from a paragraph about a path, which is what lets the two files that RECORD this deletion keep recording it.
    Other suffixes are judged on the mention alone: a `.ts`, `.sh`, `.yml` or `.json` naming a deleted config file is almost certainly pointing at it, and the handful of false positives that shape could produce are cheap to reword.
    """
    try:
        listed = subprocess.run(
            ["git", "grep", "-l", "--", EXPIRY_NEEDLE],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ["git grep could not run, so this assertion is UNCHECKED rather than clean"]
    code = (".py", ".ts", ".tsx", ".sh", ".yml", ".yaml", ".json", ".cjs", ".mjs")
    out = []
    for rel in sorted(q.strip() for q in listed.stdout.split("\n")):
        if not rel or not rel.endswith(code) or rel in EXPIRY_MENTIONS_ALLOWED:
            continue
        if rel.endswith(".py"):
            try:
                body = (root / rel).read_text(encoding="utf-8")
            except OSError:
                continue
            if not python_reads(body, EXPIRY_NEEDLE):
                continue
        out.append(rel)
    return out


def emitter_findings(root: pathlib.Path) -> tuple[list[str], int]:
    """N7: each of the five named surfaces exists and reaches the notice."""
    out: list[str] = []
    reached = 0
    for rel, token in sorted(EMITTERS.items()):
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            out.append("%s is missing, so one of the five emitters cannot emit anything" % rel)
            continue
        if token in text:
            reached += 1
        else:
            out.append(
                "%s no longer carries %r, so it has stopped reaching the notice" % (rel, token)
            )
    return out, reached


def selftest() -> int:
    """Every assertion planted, and every plant mirrored by the clean fixture it came from."""
    tally = controls.Controls("bws rotation notice", floor=CONTROL_FLOOR)
    clean = (ROOT / NOTICE_REL).read_text(encoding="utf-8")

    tally.check("N1/N2 the shipped notice is clean", notice_findings(clean), [])
    tally.truthy("an EMPTY notice is a finding, never a pass", notice_findings(""))
    tally.truthy("a whitespace-only notice is a finding too", notice_findings("   \n\n  "))
    misspelled = plant(clean, SCRIPT_REL, "scripts/dev/bws_rotate.sh")
    tally.truthy(
        "THE PLAN'S NAMED NEGATIVE: a misspelled script path FAILS", notice_findings(misspelled)
    )
    tally.check(
        "and it fails for exactly that reason",
        [f for f in notice_findings(misspelled) if "actionable line" in f],
        [notice_findings(misspelled)[0]],
    )
    for label, needle in REQUIRED_IN_ORDER:
        dropped = plant(clean, needle, "(this element was removed by a control)")
        tally.truthy("a notice missing %s FAILS" % label, notice_findings(dropped))

    # ORDER, not merely presence. The two halves are swapped and nothing is deleted.
    first, last = REQUIRED_IN_ORDER[0][1], REQUIRED_IN_ORDER[-1][1]
    swapped = plant(plant(clean, first, "\x00PLACEHOLDER\x00"), last, first)
    swapped = plant(swapped, "\x00PLACEHOLDER\x00", last)
    tally.truthy("a notice whose elements are OUT OF ORDER fails", notice_findings(swapped))

    trapguard = (ROOT / TRAPGUARD_REL).read_text(encoding="utf-8")
    tally.check(
        "N4 the hook's markers match the canonical ones", classifier_findings(trapguard), []
    )
    drifted = plant(trapguard, '"Missing access token",', '"Missing acces token",')
    tally.truthy("one character changed in ONE copy reds", classifier_findings(drifted))
    tally.truthy(
        "a hook with no marker tuple at all reds",
        classifier_findings("BWS_WIRING_MARKERS = None\n"),
    )
    tally.check(
        "the AST walk reads a tuple of literals and ignores everything else",
        marker_tuples('A = ("x", "y")\nB = ("z", 1)\nC = [1]\nD = f("q")\n'),
        {"A": ("x", "y")},
    )

    refresh = (ROOT / REFRESH_REL).read_text(encoding="utf-8")
    tally.check("N5 the refresh script carries no third copy", third_copy_findings(refresh), [])
    tally.truthy(
        "a marker literal reappearing in the refresh script reds",
        third_copy_findings(refresh + '\nif "Missing access token" in err: pass\n'),
    )
    tally.truthy(
        "a refresh script that stopped delegating reds",
        third_copy_findings(plant(refresh, "rotation-notice", "something-else")),
    )

    # N6, both directions, on the distinction that cost this gate a rewrite: a path a program could OPEN is a reader, and a paragraph about that path is a record. Ruling the second a finding would be an instruction to delete the explanation of the deletion.
    tally.truthy(
        "a module-level path CONSTANT is a reader",
        python_reads('EXPIRY = ROOT / ".ci/config/bws-token-expiry.json"\n', EXPIRY_NEEDLE),
    )
    tally.truthy(
        "an open() of the path is a reader",
        python_reads('open("bws-token-expiry.json").read()\n', EXPIRY_NEEDLE),
    )
    tally.falsy(
        "a COMMENT naming it is a record, not a reader",
        python_reads(
            "# the old bws-token-expiry.json was deleted on 2026-09-23\nX = 1\n", EXPIRY_NEEDLE
        ),
    )
    tally.falsy(
        "a DOCSTRING naming it is a record too",
        python_reads('"""It replaced bws-token-expiry.json."""\nX = 1\n', EXPIRY_NEEDLE),
    )
    tally.falsy(
        "a function docstring naming it is a record",
        python_reads(
            'def f():\n    """See bws-token-expiry.json."""\n    return 1\n', EXPIRY_NEEDLE
        ),
    )
    tally.truthy(
        "a file that will not parse is UNCHECKED and therefore reported",
        python_reads("def (:\n", EXPIRY_NEEDLE),
    )
    tally.check("the live tree has no reader left", expiry_readers(ROOT), [])

    problems, reached = emitter_findings(ROOT)
    tally.check("N7 all five emitters reach the notice", problems, [])
    tally.check("and there are exactly five of them", reached, len(EMITTERS))
    tally.check("the emitter table is not empty", len(EMITTERS) >= 5, True)

    return 0 if tally.report() else 1


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if selftest() != 0:
        print("REFUSING to report on the tree: this gate's own controls failed.", file=sys.stderr)
        return 1

    findings: list[str] = []
    notice_path = ROOT / NOTICE_REL
    try:
        text = notice_path.read_text(encoding="utf-8")
    except OSError:
        print(
            "✗ %s is missing. It is the ONE place the rotation procedure lives and five "
            "emitters read it; without it every one of them prints nothing." % NOTICE_REL,
            file=sys.stderr,
        )
        return 1
    findings += notice_findings(text)

    script = ROOT / SCRIPT_REL
    if not script.is_file():
        findings.append("%s is missing, and the notice tells the operator to run it" % SCRIPT_REL)
    elif not os.access(script, os.X_OK):
        findings.append(
            "%s is not executable, so the one command the notice names cannot run" % SCRIPT_REL
        )

    findings += classifier_findings((ROOT / TRAPGUARD_REL).read_text(encoding="utf-8"))
    findings += third_copy_findings((ROOT / REFRESH_REL).read_text(encoding="utf-8"))

    if (ROOT / EXPIRY_REL).exists():
        findings.append(
            "%s is back. It was deleted deliberately: it was a hand-written date that no "
            "gate read, and detection is now the FAILURE itself." % EXPIRY_REL
        )
    readers = expiry_readers(ROOT)
    findings += [
        "%s still names the deleted %s; repoint it at %s" % (r, EXPIRY_REL, NOTICE_REL)
        for r in readers
    ]

    emitter_problems, reached = emitter_findings(ROOT)
    findings += emitter_problems

    if reached == 0:
        print(
            "✗ ZERO of the %d emitters reach the notice. This gate is not seeing the tree, "
            "and its green would mean nothing." % len(EMITTERS),
            file=sys.stderr,
        )
        return 1

    if findings:
        print("\n✗ bws rotation notice: %d finding(s)\n" % len(findings), file=sys.stderr)
        for finding in findings:
            print("  %s" % finding, file=sys.stderr)
        print(
            "\n  The notice is the whole product of a design that deleted its own early\n"
            "  warning. Fix the text or the emitter; do not suppress this.",
            file=sys.stderr,
        )
        return 1

    print(
        "✓ bws rotation notice: %d bytes naming %s, %d/%d emitters reaching it, "
        "%d marker(s) agreeing across 2 copies, expiry file absent with 0 readers "
        "and %d named exemption(s)"
        % (
            len(text),
            SCRIPT_REL,
            reached,
            len(EMITTERS),
            len(bws_env.WIRING_MARKERS) + len(bws_env.ROTATION_MARKERS),
            len(EXPIRY_MENTIONS_ALLOWED),
        )
    )
    # PRINTED EVERY RUN, GREEN OR NOT. An exemption nobody sees is a hole nobody remembers, so the debt is on the screen beside the pass rather than only in the source.
    for rel, why in sorted(EXPIRY_MENTIONS_ALLOWED.items()):
        print("  exempt: %s" % rel)
        print("          %s" % why)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
