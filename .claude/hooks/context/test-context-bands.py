#!/usr/bin/env python3
"""Controls for the context-band hooks, plus the controls on those controls.

A check that cannot fail is worse than no check, so this suite has two halves.
The first half asserts the hooks behave (fires here, silent there, resets on
PostCompact, never exits 2). The second half MUTATES the hooks -- breaks each
behaviour on purpose in a scratch copy -- and asserts the first half goes RED.
A green run therefore means both "the hooks work" and "these assertions can
detect them not working".

Everything runs against synthetic transcripts in a temp tree. It touches no
live state, no live transcript, and nothing in the repo.

Run:  python3 .claude/hooks/context/test-context-bands.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx_budget as B

HERE = Path(__file__).resolve().parent
SESSION = "abcd1234-0000-0000-0000-000000000000"
SLUG = "abcd1234"

# A negative token count in the notice, e.g. "-226,179 tokens". Matching a
# bare "-" caught the hyphen in a temp directory name and made this control
# fail on the hooks it was meant to clear.
NEG_TOKENS = re.compile(r"-\d[\d,]*\s*tokens")

FAILURES = []
CHECKS = [0]


def check(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s   %s" % (name, detail))
        FAILURES.append(name)
    return bool(cond)


class Sandbox:
    """A throwaway project + state dir + transcript."""

    def __init__(self, hooks_dir, window=900_000):
        self.root = Path(tempfile.mkdtemp(prefix="ctxband-"))
        self.hooks = hooks_dir
        self.project = self.root / "project"
        (self.project / ".claude").mkdir(parents=True)
        (self.project / ".claude" / "settings.json").write_text(
            json.dumps({"autoCompactWindow": window}), encoding="utf-8"
        )
        self.state = self.root / "state"
        self.state.mkdir()
        self.home = self.root / "home"
        (self.home / ".claude").mkdir(parents=True)
        (self.home / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
        self.transcript = self.root / "transcript.jsonl"

    def write_transcript(self, usage, model="claude-opus-5[1m]", sidechain_after=None):
        lines = [
            json.dumps(
                {
                    "type": "assistant",
                    "isSidechain": False,
                    "sessionId": SESSION,
                    "message": {
                        "model": model,
                        "usage": {
                            "input_tokens": 2,
                            "cache_creation_input_tokens": 500,
                            "cache_read_input_tokens": usage - 502,
                            "output_tokens": 900,
                        },
                    },
                }
            )
        ]
        if sidechain_after is not None:
            # A subagent entry after the real one: the hook must ignore it, or
            # every Task call would look like the context collapsing.
            lines.append(
                json.dumps(
                    {
                        "type": "assistant",
                        "isSidechain": True,
                        "message": {
                            "model": model,
                            "usage": {
                                "input_tokens": 1,
                                "cache_creation_input_tokens": 0,
                                "cache_read_input_tokens": sidechain_after,
                                "output_tokens": 10,
                            },
                        },
                    }
                )
            )
        self.transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_state_md(self, text="# STATE\n\nsome recovery notes\n"):
        d = self.project / "agent" / SLUG
        d.mkdir(parents=True, exist_ok=True)
        (d / "STATE.md").write_text(text, encoding="utf-8")

    def env(self):
        return {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.home),
            "CTX_BAND_STATE_DIR": str(self.state),
            "LC_ALL": "C",
        }

    def run(self, script, event):
        return subprocess.run(
            [sys.executable, str(self.hooks / script)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=self.env(),
            timeout=60,
            check=False,
        )

    def post_tool(self, **over):
        ev = {
            "session_id": SESSION,
            "transcript_path": str(self.transcript),
            "cwd": str(self.project),
            "hook_event_name": "PostToolUse",
        }
        ev.update(over)
        return self.run("band-notice.py", ev)

    def post_compact(self, trigger="auto", summary="a summary"):
        return self.run(
            "epoch-reset.py",
            {
                "session_id": SESSION,
                "cwd": str(self.project),
                "hook_event_name": "PostCompact",
                "trigger": trigger,
                "compact_summary": summary,
            },
        )

    def pre_compact(self, trigger="auto"):
        return self.run(
            "precompact-floor.py",
            {
                "session_id": SESSION,
                "transcript_path": str(self.transcript),
                "cwd": str(self.project),
                "hook_event_name": "PreCompact",
                "trigger": trigger,
                "custom_instructions": "",
            },
        )

    def band_state(self):
        f = self.state / ("%s.json" % SLUG)
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def fired(p):
    """Did the band hook return additionalContext?"""
    out = (p.stdout or "").strip()
    if not out:
        return None
    try:
        d = json.loads(out)
    except Exception:  # noqa: BLE001
        return None
    return (d.get("hookSpecificOutput") or {}).get("additionalContext")


# --------------------------------------------------------------------------
# arithmetic
# --------------------------------------------------------------------------


def test_arithmetic():
    print("\n[arithmetic]")
    r = B.resolve_threshold("claude-opus-5[1m]", None)
    # No project dir and no env: falls back to the model's own max.
    check(
        "1M model with no pin resolves to 985,000",
        r["threshold"] == 985_000,
        "got %s" % r["threshold"],
    )

    sb = Sandbox(HERE)
    try:
        os.environ.pop("CLAUDE_CODE_AUTO_COMPACT_WINDOW", None)
        r = B.resolve_threshold("claude-opus-5[1m]", str(sb.project))
        check(
            "900k pin resolves to 885,000",
            r["threshold"] == 885_000,
            "got %s from %s" % (r["threshold"], r["source"]),
        )
        check(
            "project settings.json is the source",
            "settings.json" in str(r["source"]),
            r["source"],
        )
        # The trap this guards: a 200K model with a 900K pin must NOT inherit
        # the 900K threshold, or the hook would sit silent through a
        # compaction that fired at 167,000.
        r200 = B.resolve_threshold("claude-opus-5", str(sb.project))
        check(
            "200K model caps the pinned window",
            r200["threshold"] == 185_000,
            "got %s" % r200["threshold"],
        )
        runknown = B.resolve_threshold("some-gateway/mystery", str(sb.project))
        check(
            "unknown model is flagged as not confident",
            runknown["confident"] is False and runknown["threshold"] == 885_000,
            "%s" % runknown,
        )
        check(
            "band_for picks the highest crossed band",
            (
                B.band_for(100, 867_000) == -1
                and B.band_for(int(885_000 * 0.80), 885_000) == 0
                and B.band_for(int(885_000 * 0.99), 885_000) == 1
            ),
        )
    finally:
        sb.cleanup()


# --------------------------------------------------------------------------
# band hook behaviour
# --------------------------------------------------------------------------


def test_bands(hooks_dir):
    """The behavioural half. The mutation half asserts that a broken hook
    makes specific checks fail via `must_fail` / `run_isolated`, not via an
    override here."""
    print("\n[band hook] %s" % hooks_dir)
    sb = Sandbox(hooks_dir)
    try:
        sb.write_state_md()

        # Below every band: silent.
        sb.write_transcript(400_000)
        p = sb.post_tool()
        check("silent below the early band", fired(p) is None, repr(p.stdout[:200]))
        check("exit 0 below the band", p.returncode == 0, str(p.returncode))

        # Early band (75% of 867,000 = 650,250).
        sb.write_transcript(670_000)
        p = sb.post_tool()
        ctx = fired(p)
        check("fires on the early band", ctx is not None)
        check(
            "early text carries the real numbers",
            bool(ctx) and "885,000" in ctx and "670,000" in ctx,
            repr(ctx)[:300] if ctx else "",
        )
        check(
            "early text names STATE.md",
            bool(ctx) and ("agent/%s/STATE.md" % SLUG) in ctx,
        )
        check(
            "text is factual, not an imperative",
            bool(ctx)
            and not any(
                w in ctx.lower() for w in ("you must", "you should", "rewrite now", "immediately")
            ),
        )

        # Debounce: same band, same epoch, nothing more to say.
        p = sb.post_tool()
        check("silent on a second call in the same epoch", fired(p) is None)
        sb.write_transcript(700_000)
        p = sb.post_tool()
        check("silent as usage grows inside the same band", fired(p) is None)

        # Late band (98% of 867,000 = 849,660).
        sb.write_transcript(870_000)
        p = sb.post_tool()
        ctx = fired(p)
        check("fires on the late band", ctx is not None)
        check(
            "late text reports headroom",
            bool(ctx) and "15,000" in ctx,
            repr(ctx)[:300] if ctx else "",
        )
        p = sb.post_tool()
        check("silent on a second call in the late band", fired(p) is None)

        # PostCompact opens a new epoch.
        before = sb.band_state()
        r = sb.post_compact()
        after = sb.band_state()
        check("PostCompact exits 0", r.returncode == 0)
        check(
            "PostCompact bumps the epoch",
            after.get("epoch", 0) == before.get("epoch", 0) + 1,
            "%s -> %s" % (before.get("epoch"), after.get("epoch")),
        )
        check("PostCompact clears the band ladder", after.get("band") == -1, str(after))
        check(
            "PostCompact records the summary size",
            after.get("compact_summary_chars") == len("a summary"),
            str(after),
        )

        # ...so the bands fire again on the way back up.
        sb.write_transcript(300_000)
        p = sb.post_tool()
        check("silent low in the new epoch", fired(p) is None)
        sb.write_transcript(670_000)
        p = sb.post_tool()
        check("early band fires again in the new epoch", fired(p) is not None)

        # The backstop: a compaction the hooks never saw.
        sb2 = Sandbox(hooks_dir)
        sb2.write_state_md()
        sb2.write_transcript(850_000)
        sb2.post_tool()
        sb2.write_transcript(120_000)  # compacted, PostCompact missed
        p = sb2.post_tool()
        check("usage-drop backstop is silent on the drop itself", fired(p) is None)
        check(
            "usage-drop backstop resets the ladder",
            sb2.band_state().get("reset_reason") == "usage_drop"
            and sb2.band_state().get("band") == -1,
            str(sb2.band_state()),
        )
        sb2.write_transcript(670_000)
        p = sb2.post_tool()
        check("bands fire again after the backstop reset", fired(p) is not None)
        sb2.cleanup()

        # The model cap must yield to evidence. A session reporting
        # `claude-opus-5` while carrying 395,590 tokens is running on the 1M
        # variant whatever the transcript says; the 167,000 threshold that id
        # implies is not merely imprecise, it is already behind us. This is a
        # live bug caught on a real session, not a hypothetical.
        sb6 = Sandbox(hooks_dir)
        sb6.write_state_md()
        sb6.write_transcript(395_590, model="claude-opus-5")
        p = sb6.post_tool()
        ctx = fired(p)
        check(
            "disproven cap does not fire a false late band",
            ctx is None,
            repr(ctx)[:200] if ctx else "",
        )
        check(
            "disproven cap is recorded",
            sb6.band_state().get("cap_disproven") is True,
            str(sb6.band_state()),
        )
        check(
            "disproven cap uses the configured window",
            sb6.band_state().get("threshold") == 885_000,
            str(sb6.band_state().get("threshold")),
        )
        # ...and it must stay disproven after a compaction drops usage back
        # under the fake hard limit, or the wrong cap re-arms silently.
        sb6.post_compact()
        sb6.write_transcript(150_000, model="claude-opus-5")
        p = sb6.post_tool()
        check("disproven cap survives a compaction", fired(p) is None, repr(fired(p))[:200])
        check(
            "disproven cap still recorded after compaction",
            sb6.band_state().get("cap_disproven") is True
            and sb6.band_state().get("threshold") == 885_000,
            str(sb6.band_state()),
        )
        sb6.cleanup()

        # The other direction: a genuine 200K session must keep its cap, or
        # the hook goes silent through the compaction it exists to predict.
        sb7 = Sandbox(hooks_dir)
        sb7.write_state_md()
        sb7.write_transcript(145_000, model="claude-opus-5")  # 78% of 185,000
        p = sb7.post_tool()
        ctx = fired(p)
        check("genuine 200K session keeps its cap and fires", ctx is not None)
        check(
            "200K notice quotes the 185,000 threshold",
            bool(ctx) and "185,000" in ctx,
            repr(ctx)[:250] if ctx else "",
        )
        check(
            "200K session is not marked disproven",
            not sb7.band_state().get("cap_disproven"),
            str(sb7.band_state()),
        )
        sb7.cleanup()

        # EVIDENCE BEATS CONFIGURATION. This is the second live bug: the pin
        # went into settings.json while sessions were already running, and
        # Claude Code reads settings once at start. A session at 894,963 under
        # a 900,000 pin is running on the old 1M window, and the only way to
        # know that is that it got there without compacting.
        sb8 = Sandbox(hooks_dir)
        sb8.write_state_md()
        sb8.write_transcript(894_963, model="claude-opus-5")
        p = sb8.post_tool()
        stt = sb8.band_state()
        check(
            "usage above the derived threshold corrects the window upward",
            stt.get("window_floor") == 1_000_000 and stt.get("threshold_corrected") is True,
            str(stt),
        )
        ctx = fired(p)
        check(
            "corrected notice never prints a negative headroom",
            not ctx or NEG_TOKENS.search(ctx) is None,
            repr(ctx)[:300] if ctx else "",
        )
        check(
            "corrected band is re-seated, not replayed",
            stt.get("band") == 0,
            "band=%s" % stt.get("band"),
        )
        # The correction is sticky: a compaction drops usage back under the
        # wrong threshold, and without stickiness the old denominator returns.
        sb8.post_compact()
        sb8.write_transcript(700_000, model="claude-opus-5")
        sb8.post_tool()
        check(
            "corrected window survives a compaction",
            sb8.band_state().get("window_floor") == 1_000_000,
            str(sb8.band_state()),
        )
        sb8.cleanup()

        # The invariant on its own, independent of how it got there: a session
        # observed past the threshold must never be told it has negative room.
        sb8b = Sandbox(hooks_dir, window=1_000_000)
        sb8b.write_state_md()
        sb8b.write_transcript(999_500, model="claude-opus-5")
        p = sb8b.post_tool()
        ctx = fired(p) or ""
        check(
            "no negative headroom is ever printed",
            NEG_TOKENS.search(ctx) is None,
            repr(ctx)[:300],
        )
        sb8b.cleanup()

        # A subagent must not be told about the main session's budget.
        sb3 = Sandbox(hooks_dir)
        sb3.write_state_md()
        sb3.write_transcript(850_000)
        p = sb3.post_tool(agent_id="agent_01xyz", agent_type="Explore")
        check("silent for a subagent event", fired(p) is None)
        sb3.cleanup()

        # A sidechain entry at the tail must not be mistaken for the session.
        sb4 = Sandbox(hooks_dir)
        sb4.write_state_md()
        sb4.write_transcript(850_000, sidechain_after=9_000)
        p = sb4.post_tool()
        check("sidechain tail entry is ignored", fired(p) is not None)
        sb4.cleanup()

        # Degenerate inputs: silent, and never non-zero.
        sb5 = Sandbox(hooks_dir)
        p = sb5.post_tool(transcript_path="/nonexistent/nope.jsonl")
        check("missing transcript is silent and exit 0", fired(p) is None and p.returncode == 0)
        sb5.transcript.write_text("not json at all\n{oops\n", encoding="utf-8")
        p = sb5.post_tool()
        check("garbage transcript is silent and exit 0", fired(p) is None and p.returncode == 0)
        p = sb5.run("band-notice.py", {})
        check("empty event is silent and exit 0", fired(p) is None and p.returncode == 0)
        sb5.cleanup()
    finally:
        sb.cleanup()


# --------------------------------------------------------------------------
# precompact floor
# --------------------------------------------------------------------------


def test_precompact(hooks_dir):
    print("\n[precompact floor] %s" % hooks_dir)
    sb = Sandbox(hooks_dir)
    try:
        sb.write_state_md()
        sb.write_transcript(850_000)
        p = sb.pre_compact()
        check("precompact exits 0", p.returncode == 0, str(p.returncode))
        check("precompact never exits 2", p.returncode != 2)
        snap = sb.state / ("%s-precompact-facts.md" % SLUG)
        check("precompact writes the facts snapshot", snap.is_file())
        body = snap.read_text(encoding="utf-8") if snap.is_file() else ""
        check(
            "snapshot records the trigger and the STATE.md path",
            "compaction trigger: auto" in body and ("agent/%s/STATE.md" % SLUG) in body,
            body[:300],
        )
        out = (p.stdout or "").strip()
        check("precompact prints summariser instructions", bool(out), repr(out[:200]))
        check(
            "instructions name the STATE.md path",
            ("agent/%s/STATE.md" % SLUG) in out,
            repr(out[:300]),
        )
        check(
            "precompact writes nothing to stderr",
            not (p.stderr or "").strip(),
            repr(p.stderr[:200]),
        )
        check(
            "instructions are not JSON (stdout becomes custom instructions)",
            not out.startswith("{"),
        )
        check(
            "instructions stay well under the 10,000-char hook output cap",
            len(out) < 10_000,
            "%d chars" % len(out),
        )

        # A session with a long worklist must not turn the instruction into a
        # list. 41 ids on one live session is what prompted the cap.
        sb9 = Sandbox(hooks_dir)
        sb9.write_state_md()
        fake = sb9.root / "fakebin"
        fake.mkdir()
        (fake / "git").write_text("#!/bin/sh\nexit 0\n")
        (fake / "git").chmod(0o755)
        wl = sb9.project / ".claude" / "hooks" / "stop"
        wl.mkdir(parents=True, exist_ok=True)
        (wl / "worklist.py").write_text(
            "print('\\n'.join('  - [ ] #%08x item %d' % (i, i) for i in range(60)))\n",
            encoding="utf-8",
        )
        p9 = sb9.pre_compact()
        out9 = (p9.stdout or "").strip()
        check("long worklist still exits 0", p9.returncode == 0)
        check(
            "long worklist id list is capped",
            "+35 more in the snapshot below" in out9,
            repr(out9[:400]),
        )
        check(
            "capped instruction stays short",
            len(out9) < 2_000,
            "%d chars" % len(out9),
        )
        sb9.cleanup()

        # Nothing to say: no STATE.md, no worklist, no git. Must stay silent so
        # the precompute cache is not invalidated for nothing.
        sb2 = Sandbox(hooks_dir)
        sb2.write_transcript(850_000)
        p2 = sb2.pre_compact()
        check(
            "precompact is silent with nothing to say",
            not (p2.stdout or "").strip(),
            repr(p2.stdout[:200]),
        )
        check("precompact still exits 0 with nothing to say", p2.returncode == 0)
        check(
            "precompact still writes the snapshot when silent",
            (sb2.state / ("%s-precompact-facts.md" % SLUG)).is_file(),
        )
        sb2.cleanup()

        # Hostile environment: no git binary, no worklist.py. Still exit 0.
        sb3 = Sandbox(hooks_dir)
        sb3.write_state_md()
        env = sb3.env()
        env["PATH"] = "/nonexistent"
        p3 = subprocess.run(
            [sys.executable, str(hooks_dir / "precompact-floor.py")],
            input=json.dumps(
                {
                    "session_id": SESSION,
                    "cwd": str(sb3.project),
                    "hook_event_name": "PreCompact",
                    "trigger": "auto",
                }
            ),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            check=False,
        )
        check("precompact exits 0 with no git on PATH", p3.returncode == 0, str(p3.returncode))
        sb3.cleanup()
    finally:
        sb.cleanup()


# --------------------------------------------------------------------------
# the controls on the controls
# --------------------------------------------------------------------------

MUTANTS = [
    (
        "bands fire always",
        "band-notice.py",
        None,
        (
            "ctx_budget.py",
            'BANDS = (("early", 0.75), ("late", 0.98))',
            'BANDS = (("early", 0.0), ("late", 0.0))',
        ),
        ["silent below the early band"],
    ),
    (
        "debounce removed",
        "band-notice.py",
        ('if band > int(st.get("band", -1)):', "if True:"),
        None,
        ["silent on a second call in the same epoch"],
    ),
    (
        "epoch reset neutered",
        "epoch-reset.py",
        ('"band": -1,', '"band": 1,'),
        None,
        ["PostCompact clears the band ladder", "early band fires again in the new epoch"],
    ),
    (
        "cap disproof removed",
        "band-notice.py",
        None,
        (
            "ctx_budget.py",
            "    return observed_usage > (mmax - HARD_LIMIT_MARGIN) and configured > mmax",
            "    return False",
        ),
        # NOT "does it fire": the window-floor correction added later catches
        # this case as well, so removing the cap disproof no longer produces a
        # false band. What it does produce is a threshold reached by the wrong
        # route and an unset flag, and those still tell them apart. Two
        # mechanisms covering one failure is the point; a mutant that cannot
        # distinguish them is not.
        ["disproven cap is recorded", "disproven cap uses the configured window"],
    ),
    (
        "cap disproof made unconditional",
        "band-notice.py",
        None,
        (
            "ctx_budget.py",
            "    return observed_usage > (mmax - HARD_LIMIT_MARGIN) and configured > mmax",
            "    return True",
        ),
        [
            "genuine 200K session keeps its cap and fires",
            "200K notice quotes the 185,000 threshold",
        ],
    ),
    (
        "window-floor correction removed",
        "band-notice.py",
        ('        if high > res["threshold"]:', "        if False:"),
        None,
        [
            "usage above the derived threshold corrects the window upward",
            "corrected window survives a compaction",
        ],
    ),
    (
        "negative headroom printed anyway",
        "band-notice.py",
        ("    if headroom >= 0:", "    if True:"),
        None,
        ["no negative headroom is ever printed"],
    ),
    (
        "cap disproof not sticky",
        "band-notice.py",
        (
            'sticky = bool(st.get("cap_disproven")) and st.get("cap_disproven_model") == model',
            "sticky = False",
        ),
        None,
        ["disproven cap still recorded after compaction"],
    ),
    (
        "model cap ignored",
        "band-notice.py",
        None,
        (
            "ctx_budget.py",
            "window = min(configured, mmax) if mmax else configured",
            "window = configured",
        ),
        ["200K model caps the pinned window"],
    ),
]

PRECOMPACT_MUTANTS = [
    (
        "precompact exits 2",
        ("    sys.exit(0)\n", "    sys.exit(2)\n"),
        ["precompact exits 0", "precompact never exits 2"],
    ),
    (
        "precompact always speaks",
        (
            "        if not have_doc and not ids:\n            return\n",
            "        if False:\n            return\n",
        ),
        ["precompact is silent with nothing to say"],
    ),
    (
        "precompact writes no snapshot",
        ("        os.replace(tmp, snapshot)", "        pass"),
        ["precompact writes the facts snapshot"],
    ),
]


def mutate(target_file, replacement):
    d = Path(tempfile.mkdtemp(prefix="ctxband-mutant-"))
    for f in ("ctx_budget.py", "band-notice.py", "epoch-reset.py", "precompact-floor.py"):
        shutil.copy2(HERE / f, d / f)
    old, new = replacement
    p = d / target_file
    src = p.read_text(encoding="utf-8")
    if old not in src:
        raise AssertionError("mutation anchor missing in %s: %r" % (target_file, old[:60]))
    p.write_text(src.replace(old, new, 1), encoding="utf-8")
    return d


def run_isolated(fn, hooks_dir):
    """Run one behavioural pass and return the set of failed check names."""
    saved = list(FAILURES)
    saved_n = CHECKS[0]
    FAILURES.clear()
    try:
        fn(hooks_dir)
        got = set(FAILURES)
    finally:
        FAILURES.clear()
        FAILURES.extend(saved)
        CHECKS[0] = saved_n
    return got


def test_mutations():
    print("\n[mutation controls] each mutant must turn specific checks RED")
    for name, _script, direct, indirect, must_fail in MUTANTS:
        if direct:
            d = mutate(_script, direct)
        else:
            tgt, old, new = indirect
            d = mutate(tgt, (old, new))
        try:
            if "200K model caps the pinned window" in must_fail:
                failed = run_isolated(test_arithmetic_in, d)
            else:
                failed = run_isolated(test_bands, d)
            missing = [m for m in must_fail if m not in failed]
            check(
                "mutant %r turns %s red" % (name, must_fail),
                not missing,
                "these checks stayed green: %s" % missing,
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)

    for name, direct, must_fail in PRECOMPACT_MUTANTS:
        d = mutate("precompact-floor.py", direct)
        try:
            failed = run_isolated(test_precompact, d)
            missing = [m for m in must_fail if m not in failed]
            check(
                "mutant %r turns %s red" % (name, must_fail),
                not missing,
                "these checks stayed green: %s" % missing,
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)


def test_arithmetic_in(hooks_dir):
    """The arithmetic check, but against a (possibly mutated) copy, driven
    through a subprocess so the mutated module is the one imported."""
    code = (
        "import sys, json; sys.path.insert(0, %r); import ctx_budget as B; "
        "print(json.dumps(B.resolve_threshold('claude-opus-5', sys.argv[1])))" % str(hooks_dir)
    )
    sb = Sandbox(hooks_dir)
    try:
        p = subprocess.run(
            [sys.executable, "-c", code, str(sb.project)],
            capture_output=True,
            text=True,
            env=sb.env(),
            timeout=60,
            check=False,
        )
        try:
            r = json.loads(p.stdout)
        except Exception:  # noqa: BLE001
            r = {}
        check(
            "200K model caps the pinned window",
            r.get("threshold") == 185_000,
            "got %s" % r.get("threshold"),
        )
    finally:
        sb.cleanup()


def main():
    test_arithmetic()
    test_arithmetic_in(HERE)
    test_bands(HERE)
    test_precompact(HERE)
    test_mutations()
    print("\n%d checks, %d failures" % (CHECKS[0], len(FAILURES)))
    if FAILURES:
        for f in FAILURES:
            print("  FAILED: %s" % f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
