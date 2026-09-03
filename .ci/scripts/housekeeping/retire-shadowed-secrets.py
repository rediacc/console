#!/usr/bin/env python3
"""Retire a GitHub org secret whose Bitwarden twin is now the live source.

WHAT THIS IS FOR. The cutover flipped every CONSUMER read from `secrets.X` to
`env.BWS_X`. What is left of X in the tree is scaffolding that exists only to prove
the twin matched while the flip was in progress:

  1. the `GH_<NAME>:` line and the SHADOW_NAMES entry in each job's
     "Compare shadow secrets against GitHub" step -- and the whole step, but ONLY
     when it has no other name left to compare;
  2. the `<NAME>: ${{ secrets.<NAME> }}` passthrough in a caller's `secrets:` block,
     which exists solely so the callee's comparator can read it;
  3. the callee's `on.workflow_call.secrets.<NAME>` declaration, which is dead the
     moment nothing in it reads the name.

Deleting the GitHub secret itself is NOT done here and never will be: this script
PRINTS the `gh secret delete` lines and stops. An org secret cannot be restored, the
value is not in the tree, and a script that both edits code and destroys the only
copy of a credential is a script that can do half the job and leave no way back.

ORDER MATTERS AND THIS TOOL DOES NOT ENFORCE IT. Land the edit, let CI go green, and
only then run the printed commands. Doing it the other way round blanks the reads
this edit has not removed yet.

Usage:
  retire-shadowed-secrets.py <NAME> [<NAME>...]            # report only (default)
  retire-shadowed-secrets.py --apply <NAME> [<NAME>...]    # rewrite the files
  retire-shadowed-secrets.py --selftest

Exit: 0 clean, 1 nothing to do for a named secret, 2 a failed control.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("RETIRE_ROOT") or Path(__file__).resolve().parents[3])
COMPARE_STEP = "Compare shadow secrets against GitHub"


def files() -> list[Path]:
    out = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    tpl = ROOT / ".ci" / "breakpoint" / "workflow" / "breakpoint.yml"
    if tpl.is_file():
        out.append(tpl)
    return out


def step_span(lines: list[str], i: int) -> tuple[int, int]:
    """(start, end) of the `      - ` step containing line i; end excludes trailing blanks."""
    s = i
    while s > 0 and not re.match(r"^      - ", lines[s]):
        s -= 1
    e = s + 1
    while e < len(lines) and not re.match(r"^      - ", lines[e]):
        e += 1
    while e - 1 > s and not lines[e - 1].strip():
        e -= 1
    return s, e


def retire_in_text(text: str, names: set[str]) -> tuple[str, list[str]]:
    """Rewrite one workflow's text. Returns (new_text, what changed).

    Line-addressed and re-scanned after every removal rather than done in one pass:
    the three edits below overlap (removing a GH_ line can empty a SHADOW_NAMES list
    which empties a step), and a single pass over stale indices is how a rewrite lands
    in the neighbouring key.
    """
    lines = text.split("\n")
    changed: list[str] = []
    again = True
    while again:
        again = False
        for i, ln in enumerate(lines):
            st = ln.strip()

            # 1. the comparator's GH_ half
            m = re.match(r"^GH_([A-Z0-9_]+):\s*\$\{\{\s*secrets\.", st)
            if m and m.group(1) in names:
                s, _ = step_span(lines, i)
                if COMPARE_STEP in lines[s]:
                    del lines[i]
                    changed.append("comparator GH_%s" % m.group(1))
                    again = True
                    break

            # 2. SHADOW_NAMES entries, and the step when the list empties
            if st.startswith("SHADOW_NAMES:"):
                kept = [w for w in st[len("SHADOW_NAMES:") :].split() if w not in names]
                if len(kept) != len(st[len("SHADOW_NAMES:") :].split()):
                    s, e = step_span(lines, i)
                    if not kept:
                        del lines[s:e]
                        changed.append("whole comparator step (nothing left to compare)")
                    else:
                        ind = " " * (len(ln) - len(ln.lstrip()))
                        lines[i] = "%sSHADOW_NAMES: %s" % (ind, " ".join(kept))
                        changed.append("SHADOW_NAMES -> %s" % " ".join(kept))
                    again = True
                    break

            # 3. a caller's passthrough into a reusable workflow
            m = re.match(r"^([A-Z0-9_]+):\s*\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}$", st)
            if m and m.group(1) in names and m.group(2) in names:
                ind = len(ln) - len(ln.lstrip())
                parent = None
                for k in range(i - 1, -1, -1):
                    p = lines[k]
                    if not p.strip() or p.lstrip().startswith("#"):
                        continue
                    if len(p) - len(p.lstrip()) < ind:
                        parent = p.strip()
                        break
                if parent == "secrets:":
                    del lines[i]
                    changed.append("passthrough %s" % m.group(1))
                    again = True
                    break

            # 4. the callee's declaration
            if re.match(r"^[A-Z0-9_]+:$", st) and st[:-1] in names:
                ind = len(ln) - len(ln.lstrip())
                anc = [
                    lines[k].strip()
                    for k in range(i - 1, -1, -1)
                    if lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) < ind
                ]
                if "secrets:" in anc[:2] and "workflow_call:" in anc[:4]:
                    # The declaration owns its indented body (`required: true`), so the
                    # span runs to the next line at or above this indent. step_span is
                    # the wrong tool here: this is not a step.
                    j = i + 1
                    while j < len(lines) and (
                        not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > ind
                    ):
                        j += 1
                    del lines[i:j]
                    changed.append("workflow_call declaration %s" % st[:-1])
                    again = True
                    break
    return "\n".join(lines), changed


def selftest() -> int:
    bad = 0

    def check(label, ok, detail=""):
        nonlocal bad
        print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, "" if ok else "  <- " + str(detail)))
        if not ok:
            bad += 1

    # A comparator with two names loses one and SURVIVES.
    two = (
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        "      - name: " + COMPARE_STEP + "\n"
        "        env:\n"
        "          SHADOW_NAMES: KEEP_ME DROP_ME\n"
        "          GH_KEEP_ME: ${{ secrets.KEEP_ME }}\n"
        "          GH_DROP_ME: ${{ secrets.DROP_ME }}\n"
        "        run: x.sh"
    )
    got, _ = retire_in_text(two, {"DROP_ME"})
    check(
        "a comparator with another name left keeps the step",
        COMPARE_STEP in got and "KEEP_ME" in got and "DROP_ME" not in got,
        got,
    )

    # A comparator with only the retiring name loses the WHOLE step.
    one = two.replace("SHADOW_NAMES: KEEP_ME DROP_ME", "SHADOW_NAMES: DROP_ME").replace(
        "          GH_KEEP_ME: ${{ secrets.KEEP_ME }}\n", ""
    )
    got1, _ = retire_in_text(one, {"DROP_ME"})
    check("a comparator with nothing left loses the whole step", COMPARE_STEP not in got1, got1)

    # CONTROL: a LIVE consumer read is never touched. This is the whole risk.
    live = (
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        "      - uses: ./.github/actions/app-token\n"
        "        with:\n"
        "          private-key: ${{ secrets.DROP_ME }}"
    )
    got2, ch2 = retire_in_text(live, {"DROP_ME"})
    check("CONTROL: a live consumer read is left alone", got2 == live and not ch2, ch2)

    # A caller's passthrough goes; a same-shaped line NOT under `secrets:` does not.
    call = (
        "jobs:\n"
        "  j:\n"
        "    uses: ./.github/workflows/x.yml\n"
        "    secrets:\n"
        "      DROP_ME: ${{ secrets.DROP_ME }}\n"
        "  k:\n"
        "    steps:\n"
        "      - env:\n"
        "          DROP_ME: ${{ secrets.DROP_ME }}"
    )
    got3, _ = retire_in_text(call, {"DROP_ME"})
    check(
        "the passthrough goes and the step env of the same shape stays",
        got3.count("DROP_ME: ${{ secrets.DROP_ME }}") == 1,
        got3,
    )
    return bad


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        n = selftest()
        print("%s retire-shadowed-secrets selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        return 2 if n else 0

    print("retire-shadowed-secrets: controls first, then the edit")
    if selftest():
        print("✗ control failed; refusing to touch a workflow", file=sys.stderr)
        return 2

    apply = "--apply" in argv
    names = {a for a in argv[1:] if not a.startswith("--")}
    if not names:
        print(__doc__, file=sys.stderr)
        return 1

    touched = 0
    for f in files():
        text = f.read_text(encoding="utf-8")
        new, changed = retire_in_text(text, names)
        if not changed:
            continue
        touched += 1
        print("  %s" % f.relative_to(ROOT))
        for c in changed:
            print("      - %s" % c)
        if apply:
            f.write_text(new, encoding="utf-8")
    if not touched:
        print("nothing references %s as scaffolding; already retired?" % ", ".join(sorted(names)))
        return 1

    print("\n%s %d file(s)." % ("REWROTE" if apply else "WOULD REWRITE", touched))
    if not apply:
        print("Re-run with --apply to write. Then, and ONLY after CI is green on the result:")
    else:
        print("Land this, wait for CI to go green, and ONLY then run:")
    for n in sorted(names):
        print("    gh secret delete %s --org rediacc" % n)
    print(
        "\nThose commands are printed, never run: an org secret cannot be restored and its\n"
        "value is not in this tree. Running them before the edit lands blanks the reads it\n"
        "has not removed yet."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
