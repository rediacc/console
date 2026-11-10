#!/usr/bin/env python3
"""Control harness for warn_writer_brief (agent/plans/PLAN-experience-feedback.md P1/P4, boxes A2 and A3).

WHY THIS FILE IS LOAD-BEARING. The guard declares `OWN_SUITE = True` (it was never bash), so it has no golden and `test_guards_differential.py` REQUIRES a `test-<stem>.py` beside it.

CONTROLS FIRST, each the half that must stay SILENT: not a spawn, a read-only type, `Owns: none`, no Owns line, an Owns on a file no review touched, a universal `**`, two fixed findings, a broken payload, and an Owns of `packages/www/src/**` for the gen-docs half. Then the firing half: three fixed findings on the Owns earn one review line, and an Owns on `.ci/config/env-manifest.json` earns the gen-docs line.

EVERY CASE ASSERTS rc 0 (the guard never refuses), stdout empty or exactly ONE JSON document, and under 3 s. The whole pre-agent chain is run once on a firing spawn, because the chain's stdout is the concatenation of every guard's and a second stdout speaker would break the document. Both delivery encodings are rendered and checked, the `updatedInput` one end to end with the constant flipped in process.

TWO ROOTS, as the guard has. The review history comes from a fixture project root (CLAUDE_PROJECT_DIR); the gen-docs question goes to this checkout's own generator, which is why the gen-docs cases need no fixture.

THE PIPE CASE IS THE www ONE. The guard hands gen-docs about 2,000 paths on a pipe; the first cut of `--could-affect` swallowed EAGAIN there and answered "no paths" (2026-11-10), which the `did not run` refusal needle on that case now catches.
"""

import importlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import types

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = HERE.parent
CLAUDE = HOOKS.parent
STOP = CLAUDE / "hooks" / "stop"
DISPATCH = str(HOOKS / "dispatch.py")
# The canonical sys.path hop, through rediacc_hooks/syspath.py loaded by file.
_SYSPATH = importlib.util.spec_from_file_location("rediacc_hooks_syspath", HOOKS / "syspath.py")
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
_syspath.on_sys_path(str(CLAUDE))
_syspath.on_sys_path(str(STOP))
R = importlib.import_module("wl_review")
dispatch = importlib.import_module("rediacc_hooks.dispatch")
guards = importlib.import_module("rediacc_hooks.guards")

STEM = "warn_writer_brief"
BUDGET_S = 3.0
SID = "c0ffee11-1111-2222-3333-444444444444"
AT = "2026-11-10T00:00:00Z"
FIXED = "fixed %s | abcdef01 %s" % ("f" * 40, AT)
DOC = "The docstring says the guard refuses, but it returns ALLOW on that path."
REVIEW_NEEDLE = "'doc-contradicts-code'"
GEN_NEEDLE = "gen-docs.ts --write"
NOT_RUN = "did not run"


def make_root(base, name, fixed_on_ax):
    """A fixture project root holding `fixed_on_ax` fixed medium doc findings on a/x.py."""
    root = pathlib.Path(base) / name
    (root / ".git").mkdir(parents=True)
    for n in range(fixed_on_ax):
        sha = ("%08x" % (n + 1)) + "0" * 32
        review = R.Review(
            sha=sha,
            subject="s",
            branch="1110-1",
            reviewed_at=AT,
            model="m",
            verdict="findings",
            findings=[R.Finding("%s.1" % sha[:8], "medium", "a/x.py", 1, "in-diff", DOC, FIXED)],
        )
        R.write_atomic(R.review_path(root, "1110-1", sha), R.render(review))
    return root


def spawn(prompt, kind="general-purpose", root=None):
    return {
        "tool_name": "Agent",
        "session_id": SID,
        "cwd": str(root or "/nonexistent-writer-brief-fixture"),
        "tool_input": {"subagent_type": kind, "description": "fixture", "prompt": prompt},
    }


def drive(payload, root, argv=(STEM,), extra_env=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    env.update(extra_env or {})
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, DISPATCH, *argv],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started


ROOMY_DEADLINE_S = 120.0


def drive_in_process(payload, root):
    """The guard run in this process with DEADLINE_S raised; the module constant and CLAUDE_PROJECT_DIR are restored in the finally."""
    module = guards.load(STEM)
    hookio = importlib.import_module("rediacc_hooks.hookio")
    saved_deadline = module.DEADLINE_S
    saved_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    started = time.monotonic()
    try:
        module.DEADLINE_S = ROOMY_DEADLINE_S
        os.environ["CLAUDE_PROJECT_DIR"] = str(root)
        event = hookio.Event(payload if isinstance(payload, str) else json.dumps(payload))
        result = event.result(module.run(event))
    finally:
        module.DEADLINE_S = saved_deadline
        if saved_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved_dir
    return result[0], result[1], result[2], time.monotonic() - started


def one_document(stdout):
    """The parsed document when stdout holds exactly one, else None. Empty stdout is {}."""
    if stdout.strip() == "":
        return {}
    try:
        return json.loads(stdout)
    except ValueError:
        return None


TALLY = {"fails": 0, "fired": 0, "silent": 0}

TIMED_OUT = "TimeoutExpired"


def check(name, ok, detail=""):
    TALLY["fails"] += not ok
    print("%-76s %s" % (name, "ok" if ok else "*** FAIL ***"))
    if not ok and detail:
        print("    %s" % str(detail)[:600])


def case(
    name, payload, root, want_needles, refuse_needles=(), argv=(STEM,), extra_env=None, inproc=False
):
    """Run one case; `want_needles` empty means it must be silent on stdout. `inproc` is for the cases that ask the real gen-docs: they run the guard in process with a roomy DEADLINE_S, so a saturated box cannot turn the guard's 2.5 s deadline into a failure of its logic (2026-11-10, ci:quick 1137). The real deadline has its own cases in `deadline_cases`."""
    if inproc:
        if argv != (STEM,) or extra_env:
            raise ValueError(
                "an inproc case runs drive_in_process, which takes neither argv nor extra_env"
            )
        rc, out, err, took = drive_in_process(payload, root)
    else:
        rc, out, err, took = drive(payload, root, argv, extra_env)
    doc = one_document(out)
    context = ((doc or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""
    problems = []
    if rc != 0:
        problems.append("rc=%d (the guard must never refuse or crash)" % rc)
    if doc is None:
        problems.append("stdout is not one JSON document: %r" % out[:200])
    if took > BUDGET_S and not inproc:
        problems.append("took %.2fs, over the %.1fs budget" % (took, BUDGET_S))
    if want_needles:
        TALLY["fired"] += 1
        missing = [n for n in want_needles if n not in context]
        if missing:
            problems.append("additionalContext does not name %s" % missing)
    else:
        TALLY["silent"] += 1
        if out.strip():
            problems.append("must be silent on stdout, printed %r" % out[:200])
    present = [n for n in refuse_needles if n in context or n in err]
    if present:
        problems.append("must not carry %s" % present)
    tail = " | stderr: %s" % err.strip()[:300] if err.strip() else ""
    check(name, not problems, "; ".join(problems) + tail)


def encodings():
    module = guards.load(STEM)
    tool_input = {
        "subagent_type": "general-purpose",
        "prompt": "do it\nOwns: a/**",
        "isolation": "worktree",
    }
    spec = json.loads(
        module.render(["L1", "L2"], "general-purpose", tool_input, module.ADDITIONAL_CONTEXT)
    )["hookSpecificOutput"]
    check(
        "encoding additionalContext: names both lines, carries no updatedInput",
        spec["hookEventName"] == "PreToolUse"
        and "- L1\n- L2" in spec["additionalContext"]
        and "updatedInput" not in spec,
        spec,
    )
    spec = json.loads(
        module.render(["L1", "L2"], "general-purpose", tool_input, module.UPDATED_INPUT)
    )["hookSpecificOutput"]
    new_input = spec.get("updatedInput") or {}
    prompt = new_input.get("prompt", "")
    check(
        "encoding updatedInput: the prompt keeps its text and gains the lines",
        prompt.startswith("do it\nOwns: a/**\n\n")
        and prompt.endswith("- L1\n- L2\n")
        and module.PROMPT_HEAD in prompt,
        new_input,
    )
    check(
        "encoding updatedInput: every other tool_input key is passed through",
        {k: v for k, v in new_input.items() if k != "prompt"}
        == {k: v for k, v in tool_input.items() if k != "prompt"},
        new_input,
    )
    check(
        "encoding updatedInput: the lead is still told what was appended",
        "appended 2 line(s)" in spec.get("additionalContext", ""),
        spec,
    )
    check(
        "the shipped switch is additionalContext until E0 settles",
        module.DELIVERY == module.ADDITIONAL_CONTEXT,
    )
    return module


def flipped_end_to_end(module, hot):
    """The guard with DELIVERY flipped, in process; every seam it touches is restored in the finally."""
    saved_delivery = module.DELIVERY
    saved_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        module.DELIVERY = module.UPDATED_INPUT
        os.environ["CLAUDE_PROJECT_DIR"] = str(hot)
        rc, out, err = dispatch.run_one(STEM, json.dumps(spawn("go\nOwns: a/**", root=hot)))
    finally:
        module.DELIVERY = saved_delivery
        if saved_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved_dir
    flipped = one_document(out) or {}
    prompt = ((flipped.get("hookSpecificOutput") or {}).get("updatedInput") or {}).get("prompt", "")
    check(
        "end to end with DELIVERY flipped: rc 0 and the review line is appended to the prompt",
        rc == 0 and prompt.startswith("go\nOwns: a/**") and REVIEW_NEEDLE in prompt,
        (rc, out[:300], err[:300]),
    )
    check(
        "and the switch and CLAUDE_PROJECT_DIR are restored after the flip",
        module.DELIVERY == module.ADDITIONAL_CONTEXT
        and os.environ.get("CLAUDE_PROJECT_DIR") == saved_dir,
    )


def planted_defect(module, hot):
    """The guard's declared DEFECT applied to an in-process copy: the firing spawn must then go silent, or the suite could not see the defect it declares."""
    path = pathlib.Path(module.__file__)
    source = path.read_text(encoding="utf-8")
    needle, plant = module.DEFECT
    body = "\n".join(ln for ln in source.splitlines() if not ln.startswith("DEFECT = "))
    check("the DEFECT needle occurs exactly once outside its declaration", body.count(needle) == 1)
    copy = types.ModuleType("warn_writer_brief_planted")
    copy.__file__ = str(path)
    # Planted into `body`, never `source`: the first occurrence in `source` is the DEFECT declaration itself, and a plant there changes nothing (the first cut of this case did exactly that and stayed green).
    exec(compile(body.replace(needle, plant), str(path), "exec"), copy.__dict__)
    hookio = importlib.import_module("rediacc_hooks.hookio")
    saved_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = str(hot)
        real = hookio.Event(json.dumps(spawn("go\nOwns: a/**", root=hot)))
        real_rc = module.run(real)
        event = hookio.Event(json.dumps(spawn("go\nOwns: a/**", root=hot)))
        rc = copy.run(event)
    finally:
        if saved_dir is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved_dir
    _, real_out, _ = real.result(real_rc)
    _, out, _ = event.result(rc)
    check(
        "planted DEFECT: the same firing spawn goes silent (and the real guard, in process, speaks)",
        rc == 0 and out == "" and REVIEW_NEEDLE in real_out,
        (rc, out[:200], real_out[:200]),
    )


class _Fake:
    """A subprocess.run stand-in: records each call's argv head and timeout, sleeps `delay_git` on the listing, answers an empty verdict."""

    def __init__(self, clock, delay_git=0.0):
        self.calls = []
        self.delay_git = delay_git
        self.clock = clock

    def __call__(self, argv, **kw):
        self.calls.append((argv[0], kw.get("timeout")))
        if argv[0] == "git":
            self.clock.advance(self.delay_git)
            return subprocess.CompletedProcess(argv, 0, stdout=b"x.txt\0", stderr=b"")
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"affected": [], "targets": []}', stderr=""
        )


class _Clock:
    """A fake monotonic clock that moves only when the fake listing "takes" time, so the budget cases judge the guard's arithmetic and not how fast this machine runs."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _run_fake(module, stub, deadline, fake):
    """One spawn with `subprocess.run` replaced by `fake`, the guard's `time` replaced by the fake's clock, and REPO pointed at `stub`; every seam restored."""
    hookio = importlib.import_module("rediacc_hooks.hookio")
    saved = (module.DEADLINE_S, module.REPO, subprocess.run, os.environ.get("CLAUDE_PROJECT_DIR"))
    saved_time = module.time
    try:
        module.DEADLINE_S, module.REPO, subprocess.run = deadline, stub, fake
        module.time = fake.clock
        os.environ["CLAUDE_PROJECT_DIR"] = str(stub)
        event = hookio.Event(json.dumps(spawn("x\nOwns: x.txt", root=stub)))
        return event.result(module.run(event))
    finally:
        module.time = saved_time
        module.DEADLINE_S, module.REPO, subprocess.run = saved[:3]
        if saved[3] is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved[3]


def deadline_cases(base):
    """The guard's own 2.5 s deadline, which the in-process cases deliberately do not exercise."""
    module = guards.load(STEM)
    check("the shipped deadline is still 2.5 s", module.DEADLINE_S == 2.5, module.DEADLINE_S)

    stub = pathlib.Path(base) / "stub"
    (stub / "scripts" / "gen").mkdir(parents=True)
    (stub / ".git").mkdir()
    (stub / module.GEN_DOCS_REL).write_text("setTimeout(() => {}, 30000);\n", encoding="utf-8")
    # A real node child that never answers, under the real constant: the guard must stay in budget and say so.
    hookio = importlib.import_module("rediacc_hooks.hookio")
    saved = (module.REPO, module._tracked, os.environ.get("CLAUDE_PROJECT_DIR"))
    started = time.monotonic()
    try:
        module.REPO, module._tracked = stub, lambda _repo, _timeout: ["x.txt"]
        os.environ["CLAUDE_PROJECT_DIR"] = str(stub)
        event = hookio.Event(json.dumps(spawn("x\nOwns: x.txt", root=stub)))
        rc, out, err = event.result(module.run(event))
    finally:
        module.REPO, module._tracked = saved[:2]
        if saved[2] is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = saved[2]
    took = time.monotonic() - started
    check(
        "real deadline: a gen-docs child that never answers is cut at 2.5 s, rc 0, silent, one note",
        rc == 0 and out == "" and NOT_RUN in err and TIMED_OUT in err and took < BUDGET_S + 1.0,
        (rc, out[:100], err[:200], took),
    )

    # 530c1884.1: no child may be given more than what is left of the budget.
    fake = _Fake(_Clock(), delay_git=0.7)
    rc, out, err = _run_fake(module, stub, 0.6, fake)
    heads = [c[0] for c in fake.calls]
    check(
        "budget (530c1884.1): listing files past the deadline starts no gen-docs child",
        rc == 0 and "node" not in heads and NOT_RUN in err and "git" in heads,
        (fake.calls, err[:200]),
    )
    fake = _Fake(_Clock())
    rc, out, err = _run_fake(module, stub, 0.6, fake)
    git_t = [t for h, t in fake.calls if h == "git"]
    node_t = [t for h, t in fake.calls if h == "node"]
    check(
        "budget (530c1884.1): the listing's and the child's timeouts sit inside the budget",
        rc == 0 and len(git_t) == 1 and git_t[0] <= 0.6 and len(node_t) == 1 and node_t[0] <= 0.6,
        fake.calls,
    )
    rc, out, err = _run_fake(module, stub, 60.0, _Fake(_Clock()))
    check(
        "budget control: a roomy budget asks gen-docs and stays silent on an empty verdict",
        rc == 0 and out == "" and NOT_RUN not in err,
        (rc, out[:100], err[:200]),
    )


def main():
    with tempfile.TemporaryDirectory(prefix="writer-brief-") as base:
        hot = make_root(base, "hot", 3)
        lukewarm = make_root(base, "lukewarm", 2)
        empty = make_root(base, "empty", 0)
        long_none = "Owns: none -- this writer only reads the review store and reports"

        # ---- controls: the halves that must stay silent ----
        bash = {"tool_name": "Bash", "tool_input": {"command": "true"}}
        case("control: not a spawn", bash, hot, [])
        case("control: a broken payload", "not json at all", hot, [])
        case("control: Explore on a hot Owns", spawn("x\nOwns: a/**", "Explore", hot), hot, [])
        case("control: Plan on a hot Owns", spawn("x\nOwns: a/**", "Plan", hot), hot, [])
        case("control: Owns: none", spawn("x\n" + long_none, root=hot), hot, [])
        case("control: no Owns line", spawn("fix the docstring in a/x.py", root=hot), hot, [])
        case("control: a malformed Owns line", spawn("x\nOwns: some prose here", root=hot), hot, [])
        case(
            "control: an Owns on an untouched file",
            spawn("x\nOwns: b/untouched.py", root=hot),
            hot,
            [],
        )
        case("control: a universal Owns", spawn("x\nOwns: **", root=hot), hot, [])
        case(
            "control: two fixed findings stay silent",
            spawn("x\nOwns: a/**", root=lukewarm),
            lukewarm,
            [],
        )
        case(
            "control (A3): Owns packages/www/src/** names no gen-docs step",
            spawn("x\nOwns: packages/www/src/**", root=empty),
            empty,
            [],
            refuse_needles=(GEN_NEEDLE, NOT_RUN),
            inproc=True,
        )

        # ---- the firing half ----
        case(
            "fires: three fixed doc findings on a/x.py earn the review line",
            spawn("x\nOwns: a/**", root=hot),
            hot,
            [REVIEW_NEEDLE, "a/x.py", "paste them into the brief"],
            refuse_needles=(GEN_NEEDLE, NOT_RUN),
        )
        case(
            "fires (A3): Owns .ci/config/env-manifest.json earns the gen-docs line",
            spawn("x\nOwns: .ci/config/env-manifest.json", root=empty),
            empty,
            [GEN_NEEDLE, "env-manifest"],
            refuse_needles=(REVIEW_NEEDLE, NOT_RUN),
            inproc=True,
        )
        case(
            "fires: review and gen-docs lines together",
            spawn("x\nOwns: a/**, .ci/config/env-manifest.json", root=hot),
            hot,
            [REVIEW_NEEDLE, GEN_NEEDLE],
            refuse_needles=(NOT_RUN,),
            inproc=True,
        )

        # ---- the whole chain: its concatenated stdout must still be one document ----
        store = pathlib.Path(base) / "store"
        store.mkdir()
        tmp = pathlib.Path(base) / "tmp"
        tmp.mkdir()
        case(
            "the pre-agent chain's stdout is one JSON document on a firing spawn",
            spawn("x\nOwns: a/**", root=hot),
            hot,
            [REVIEW_NEEDLE],
            argv=("--chain", "pre-agent"),
            extra_env={"WORKLIST_STORE_DIR": str(store), "TMPDIR": str(tmp)},
        )

        deadline_cases(base)

        module = encodings()
        flipped_end_to_end(module, hot)
        planted_defect(module, hot)

    print()
    # ANTI-VACUITY: a guard that answers one way on every input passes half of any suite.
    if TALLY["fired"] == 0 or TALLY["silent"] == 0:
        print(
            "*** FAIL *** %(fired)d fired, %(silent)d silent: the suite compared the guard "
            "against a constant." % TALLY,
            file=sys.stderr,
        )
        TALLY["fails"] += 1
    print("%(fired)d fired, %(silent)d silent" % TALLY)
    print("FAILURES: %(fails)d" % TALLY)
    return 1 if TALLY["fails"] else 0


if __name__ == "__main__":
    sys.exit(main())
