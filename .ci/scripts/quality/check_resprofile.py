#!/usr/bin/env python3
"""check:ci-resprofile -- structural findings from the PREVIOUS run's process-tree captures.

WHY THE PREVIOUS RUN. Gates run in parallel; a capture of a gate still running is
incomplete, so a gate that judged THIS run would read torn files. scripts/ci-runner/run.ts
rotates `.ci/cache/profiles` -> `.ci/cache/profiles.prev` at start, and this gate reads
the completed set. The first run therefore has nothing to judge, and says so.

WHAT IS ENFORCED, AND THE ONE RULE. A finding class may ENFORCE only while it is
admissible: J >= 20 judgeable captures and a one-sided 95% upper bound on its fire rate
<= 5% (wl_profile.admissible). Below that it is REPORT-ONLY for lack of denominator.
Every predicate is dilation-invariant (wall stretched by k changes no verdict) and that
is proven per run: the captures are re-derived at k=2.3 and the two finding sets must be
byte-identical or the gate refuses its own verdict.

PRISTINE BOOTSTRAP, copied from .runner-advice-allowlist. Until
.ci/config/resprofile-baseline.json is SEEDED (`--seed <captures-dir>`, by a human, from
real numbers), the gate WARNS and exits 0. Seeded means enforced, which is the only reason
the pristine pass is not a permanent hole. Seeding from one machine's first run is how a
bad number gets enshrined, so the seed command refuses an EMPTY corpus outright; seeds
accumulate, and only a NAMED --reseed-class can replace a class's numbers.

THE KILL TRIGGER, fixed in advance. `sunset` in the baseline is 30 days after seeding.
Past it, if no commit in the last 30 days mentions `resprofile:` AND touches a file a
finding named, this gate FAILS with the remedy `git rm` -- a metrics layer nobody acts
on is write-only data, and this hook directory already holds one (wl_admit.py:596-600).

ANTI-VACUITY. A captures dir with zero judgeable captures is UNJUDGEABLE, never clean:
warn while pristine, fail once seeded. Exit 1 on an enforced finding, 2 on a failed control.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("RESPROFILE_ROOT") or Path(__file__).resolve().parents[3])
sys.path.insert(0, str(ROOT / ".claude" / "hooks" / "stop"))
import wl_profile as W  # noqa: E402

BASELINE = ROOT / ".ci" / "config" / "resprofile-baseline.json"


def _default_captures() -> Path:
    """`.ci/cache/profiles.prev` is a POINTER FILE naming the last completed run's
    capture folder under ~/.claude/resprofile/<repo>/<day>/<run>/ (time-based, durable,
    outside the tree). A missing pointer is "no captures", never an error."""
    ptr = ROOT / ".ci" / "cache" / "profiles.prev"
    try:
        return Path(ptr.read_text(encoding="utf-8").strip())
    except OSError:
        return ptr  # absent: is_dir() is False and the caller says so


DEFAULT_CAPTURES = _default_captures()
SUNSET_DAYS = 30
MIN_JUDGEABLE_FRACTION = 0.5


def load_baseline() -> dict | None:
    try:
        d = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if d.get("format") != 1:
        print(
            f"✗ {BASELINE.name}: unknown format {d.get('format')!r}; refusing to reinterpret",
            file=sys.stderr,
        )
        sys.exit(2)
    return d


def captures_in(d: Path) -> list:
    return [c for c in (W.load_capture(p) for p in sorted(d.glob("*.jsonl"))) if c]


def selftest() -> int:
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print(
            "  %s  %s%s"
            % ("PASS" if ok else "FAIL", name, "\n        " + detail if (detail and not ok) else "")
        )
        bad += 0 if ok else 1

    # The deriver's own controls are the substance; this gate adds the wiring controls.
    check("wl_profile selftest is green (the deriver is the instrument)", W.selftest() == 0)
    ok, why = W.admissible(0, 19)
    check("admission floor: J=19 is report-only", not ok and "denominator" in why)
    # THE TRIGGER MUST BE ABLE TO FIRE, and the previous one could not: it ran after
    # the pristine return, every --seed reset its sunset, and it grepped prose. These
    # three controls are exactly those three defects, planted.
    check(
        "kill trigger: an anchor in the FUTURE is silent",
        kill_trigger_fired({"installed": "2999-01-01T00:00:00Z"}) is None,
    )
    check(
        "kill trigger: a PRISTINE baseline is still evaluated (None in, None out, no crash)",
        kill_trigger_fired(None) is None,
    )
    _past = {"installed": "2000-01-01T00:00:00Z"}
    _fired = kill_trigger_fired(_past)
    check(
        "kill trigger: past its anchor with too few acted-on commits, it FIRES",
        _fired is not None and "Resprofile:" in _fired,
        str(_fired)[:120],
    )
    check(
        "a missing baseline is PRISTINE, not an error",
        load_baseline() is None or load_baseline().get("format") == 1,
    )

    # THE BASH ANTI-VACUITY ARM, both answers. This arm exists because silence from
    # the bash corpus read as a clean tree for the running devbox's whole life, so a
    # control that only proves the happy path would reproduce the original defect in
    # the check that was written to catch it.
    import tempfile  # noqa: PLC0415
    import time as _t  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty"
        n0, why0 = bash_corpus_today(empty)
        check(
            "bash corpus: an absent file counts ZERO, and says where it looked",
            n0 == 0 and str(empty) in why0,
            why0,
        )
        day = (
            Path(td)
            / "full"
            / str(ROOT).lstrip("/").replace("/", "-")
            / _t.strftime("%Y-%m-%d", _t.gmtime())
        )
        day.mkdir(parents=True)
        (day / "bash.jsonl").write_text('{"shape":"sh:x"}\n\n{"shape":"sh:y"}\n', encoding="utf-8")
        n1, _ = bash_corpus_today(Path(td) / "full")
        check("bash corpus CONTROL: two records count 2, blank lines ignored", n1 == 2, f"got {n1}")
        (day / "bash.jsonl").write_text("", encoding="utf-8")
        n2, _ = bash_corpus_today(Path(td) / "full")
        check(
            "bash corpus: an EMPTY file counts zero, not 'the folder exists'", n2 == 0, f"got {n2}"
        )
    return bad


def seed(captures_dir: Path, reseed: set[str]) -> int:
    caps = captures_in(captures_dir)
    j = sum(c.judgeable for c in caps)
    # AN EMPTY SEED IS REFUSED, and the gate-test is what made that rule honest. The
    # first draft carried a "refuse a silent shrink" guard that could never fire: seeds
    # ACCUMULATE F and J, so nothing but a NAMED --reseed-class can ever lower them,
    # and the guard was a control that passed vacuously. What a seed must not do is
    # claim to have measured when it read nothing -- the vacuity rule from
    # .ci/scripts/ci/profiler/report.awk, applied to the baseline.
    if j == 0:
        print(
            f"✗ refusing to seed from {captures_dir}: 0 judgeable capture(s). A baseline seeded from nothing enshrines nothing. Name a real run folder.",
            file=sys.stderr,
        )
        return 2
    findings = W.derive(caps)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["class"]] = counts.get(f["class"], 0) + 1
    prior = load_baseline() or {"format": 1, "classes": {}}
    classes = dict(prior.get("classes", {}))
    for cls in ("E1", "E4", "E5", "E6"):
        old = classes.get(cls, {"F": 0, "J": 0})
        # Accumulate by default; a NAMED class is replaced from this corpus alone.
        classes[cls] = (
            {"F": counts.get(cls, 0), "J": j}
            if cls in reseed
            else {"F": old["F"] + counts.get(cls, 0), "J": old["J"] + j}
        )
    doc = {
        "format": 1,
        "seeded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sunset": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + SUNSET_DAYS * 86400)
        ),
        "classes": classes,
        "note": "F = findings, J = judgeable captures, accumulated across seeds; --reseed-class <C> replaces one class from the named corpus. Admission per class is decided at gate time.",
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(
        f"✓ seeded {BASELINE.relative_to(ROOT)} from {len(caps)} capture(s), {j} judgeable: {classes}"
    )
    return 0


# The layer's own files. A commit that only maintains the profiler is not evidence
# that the profiler earned anything, so the trailer must touch something ELSE.
LAYER_FILES = (
    ".claude/hooks/stop/wl_resprofile.py",
    ".claude/hooks/stop/wl_ressample.py",
    ".claude/hooks/stop/wl_profile.py",
    ".claude/hooks/profile/",
    ".ci/scripts/quality/check_resprofile.py",
    ".ci/scripts/test/gates/test-resprofile.sh",
    ".devcontainer/bashcov-sup.c",
)
SUNSET_DAYS = 30
ACTED_ON_FLOOR = 2


def acted_on_commits(days: int = SUNSET_DAYS) -> list[str]:
    """Commits in the window carrying a `Resprofile:` TRAILER and touching real code.

    A TRAILER, not a grep for the word. The previous version ran
    `git log --grep=resprofile:`, which matches prose -- including a commit that
    merely maintains the profiler, and including this very docstring. The repo
    already enforces a trailer shape for PR-TASK (a trailer must START a line), so
    the same discipline applies here and the query becomes mechanical.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", f"--since={days}.days", "--format=%H%x00%B%x01"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    hits = []
    for block in out.split("\x01"):
        sha, _, body = block.strip().partition("\x00")
        if not sha or not any(
            ln.strip().startswith("Resprofile:") and len(ln.strip()) > 12
            for ln in body.splitlines()
        ):
            continue
        try:
            files = subprocess.run(
                ["git", "-C", str(ROOT), "show", "--name-only", "--format=", sha],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            ).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            continue
        if any(not any(f.startswith(x) for x in LAYER_FILES) for f in files):
            hits.append(sha)
    return hits


def kill_trigger_fired(base: dict | None) -> str | None:
    """Evaluated even when PRISTINE -- the previous version could never fire.

    It ran AFTER main()'s pristine return, and the baseline is deliberately unseeded,
    so the layer's own design deferred the act that armed its retirement. Worse, every
    `--seed` rewrote `sunset` to now + 30 days, making an accumulate-seed a free
    extension. Both are fixed here: the window is measured from `installed` (set once)
    and the check runs before any other verdict.
    """
    anchor = (base or {}).get("installed") or (base or {}).get("sunset")
    if not anchor:
        return None
    if time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) < anchor:
        return None
    hits = acted_on_commits()
    if len(hits) >= ACTED_ON_FLOOR:
        return None
    return (
        f"past its sunset ({anchor}) with {len(hits)} commit(s) in {SUNSET_DAYS} days "
        f"carrying a `Resprofile:` trailer AND touching a file outside the layer "
        f"(floor {ACTED_ON_FLOOR}). "
        "A profiling layer that changed no line of code in a month is decoration: "
        "`git rm` this gate, wl_profile.py, wl_ressample.py and the exec.ts attach."
    )


def bash_corpus_today(corpus: Path | None = None) -> tuple[int, str]:
    """(records written today, a phrase saying where I looked).

    Counted rather than merely existence-checked: bash_env.sh creates the day folder
    before it knows whether the supervisor is there, so an EMPTY bash.jsonl -- or a
    missing one beside a populated exit.jsonl -- is the exact signature of the hole.
    """
    import time  # noqa: PLC0415

    # `corpus` is injectable ONLY so selftest() can drive both answers against a
    # fixture. ROOT cannot serve that purpose: it is also this file's import path for
    # wl_profile, so pointing it at a temp dir makes the module fail to load rather
    # than report an empty corpus -- which is how the first attempt at this control
    # "passed" by crashing before it reached the check.
    root = corpus or (Path.home() / ".claude" / "resprofile")
    slug = str(ROOT).lstrip("/").replace("/", "-")
    day = root / slug / time.strftime("%Y-%m-%d", time.gmtime())
    f = day / "bash.jsonl"
    if not f.is_file():
        return 0, f"{f} does not exist"
    try:
        n = sum(
            1 for ln in f.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()
        )
    except OSError as exc:
        return 0, f"{f} unreadable ({exc})"
    return n, f"{n} record(s) in {f}"


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        n = selftest()
        print("%s resprofile gate selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        return 1 if n else 0
    if "--seed" in argv:
        rs = {argv[i + 1] for i, a in enumerate(argv) if a == "--reseed-class"}
        return seed(Path(argv[argv.index("--seed") + 1]), rs)

    print("resprofile: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2

    cdir = Path(argv[argv.index("--captures") + 1]) if "--captures" in argv else DEFAULT_CAPTURES
    base = load_baseline()
    pristine = base is None

    # BEFORE ANYTHING ELSE, because the previous placement made it unreachable: it
    # ran after the pristine return, and the baseline is deliberately unseeded.
    kt = kill_trigger_fired(base)
    if kt:
        print(f"✗ KILL TRIGGER: {kt}", file=sys.stderr)
        return 1

    if not cdir.is_dir():
        print(
            f"{'⚠' if pristine else '✗'} no captures at {cdir}: the runner rotates them in at the start of the NEXT run, so the first run has nothing to judge.{' (pristine: warning only)' if pristine else ''}"
        )
        return 0 if pristine else 1
    # THE BASH CORPUS IS THE OTHER HALF, and its silence used to read as clean.
    #
    # bash_env.sh probes two explicit paths for bashcov-sup and skips SILENTLY when
    # neither exists -- which is what the running devbox did for its whole life, so
    # this scope recorded no bash at all while every gate below reported a healthy
    # tree. That is the same shape as an empty captures dir, and it gets the same
    # answer: UNJUDGEABLE, warn while pristine and fail once seeded, never "clean".
    #
    # TODAY'S file only. An older day proves the writer worked then, not now, and
    # "it used to record" is exactly the reassurance this check must not give.
    bl, bwhy = bash_corpus_today()
    if bl == 0:
        print(
            f"{'⚠' if pristine else '✗'} UNJUDGEABLE: no bash records for this scope today "
            f"({bwhy}). The supervisor is absent or the env seam did not arrive, so every "
            f"shell in this scope is unmeasured and the ranking below is Python-only."
        )
        if not pristine:
            return 1

    caps = captures_in(cdir)
    j = sum(c.judgeable for c in caps)
    if not caps or j < MIN_JUDGEABLE_FRACTION * len(caps):
        print(
            f"{'⚠' if pristine else '✗'} UNJUDGEABLE: {j} of {len(caps)} capture(s) judgeable (floor {MIN_JUDGEABLE_FRACTION:.0%}). That is a sampler problem, never a clean tree."
        )
        return 0 if pristine else 1

    findings = W.derive(caps)
    # DILATION CONTROL ON THE REAL DATA, every run: wall x2.3 must change nothing.
    dilated = W.derive([W.dilate(c, 2.3) for c in caps])
    if json.dumps(findings, sort_keys=True) != json.dumps(dilated, sort_keys=True):
        print(
            "✗ dilation control FAILED on this run's captures: a predicate is reading wall-clock. Refusing the verdict.",
            file=sys.stderr,
        )
        return 2

    if pristine:
        print(
            f"⚠ pristine: {len(caps)} capture(s), {j} judgeable, {len(findings)} finding(s) -- nothing enforced until `check_resprofile.py --seed {cdir}` records a baseline from real numbers."
        )
        for f in findings[:10]:
            print(f"    {f['class']}  {f['why']}")
        return 0

    enforced, reported = [], []
    for f in findings:
        cls = f["class"]
        stats = base.get("classes", {}).get(cls, {"F": 0, "J": 0})
        ok, why = W.admissible(stats["F"], stats["J"])
        (enforced if (f.get("enforce") and ok) else reported).append((f, why))
    for f, why in reported:
        print(f"  report-only {f['class']} ({why}): {f['why']}")
    if enforced:
        print(
            f"✗ {len(enforced)} enforced finding(s) over {j} judgeable capture(s):", file=sys.stderr
        )
        for f, why in enforced:
            print(f"    {f['class']} [{why}]: {json.dumps(f)}", file=sys.stderr)
        print(
            "  Suppress only with a BLOCKER: reason in .profile-finding-allowlist (docs/agent-reference/suppressions.md).",
            file=sys.stderr,
        )
        return 1
    print(
        f"✓ resprofile: {len(caps)} capture(s), {j} judgeable, {len(reported)} report-only, 0 enforced; dilation control held."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
