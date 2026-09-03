"""wl_profile: derive STRUCTURAL findings from tree captures. Never blocks a stop.

WHERE THIS LIVES AND WHY. A sibling of the judge, not a fourth marker in it. Two
verified facts decide that: wl_checks.py:5352/5379 gate the judge on
`(something_remains or reg_signals)`, so a session that ran the battery, got green
and has a clean board never reaches it -- exactly the shape a resource verdict is
about; and the judge fails CLOSED by contract (worklist.py:91-94) while this signal
must never turn "we did not measure" into "you may not stop". Unjudgeable is
silence here, always.

THE ONE RULE EVERY PREDICATE MUST PASS: DILATION INVARIANCE. A finding may be
ENFORCED only if its verdict is unchanged when every duration in the capture is
multiplied by k>0. The worklist suite measured ~4 min standalone and ~9 min under
the full battery on identical code -- that is k=2.25 from machine load alone. And
load stretches WALL, not CPU, so `dilate()` scales timestamps and PSI and leaves
utime/stime/cutime/cstime alone. Under that operator `cpu/wall` is NOT invariant
(0.95 -> 0.42 at k=2.25), which is why "saturated" is an R-STATE FRACTION here: on
Linux `R` covers running AND runnable-but-preempted, so a CPU-bound process starved
of the CPU is still R. Every predicate below is a count, a ratio of counts, or a set
relation. Nothing is expressed in seconds, and control D2 reads this file's own
source to refuse any comparison of a duration field against a numeric literal.

MEASUREMENT REFUTES; IT NEVER PROPOSES. A sampled fd table is a LOWER bound on a
process's write set. A predicate whose safety depends on the ABSENCE of a shared
write (E1) therefore requires POSITIVE evidence of disjointness -- every child must
have an observed write set, and they must be pairwise disjoint; a child with nothing
observed is unresolved and kills the finding. E4 is the safe direction: it needs
positive evidence of a SHARED write and never certifies independence.

THE SILENCE PREDICATE, made computable. A class C may ENFORCE only while its fire
rate over JUDGEABLE captures satisfies `admissible(F, J)`: J >= 20 AND the one-sided
95% Wilson upper bound on F/J <= 0.05. Below J=20 the class is report-only "for lack
of denominator", which is a different and more honest reason than "too noisy". The
gate applies this per class; this module only emits findings with their class.

Findings (see agent/PLAN-shell-resource-profiling.md sections 3 and 3b):
  E1  SEQUENTIAL INDEPENDENT FANOUT   enforceable
  E4  UNDECLARED CONCURRENT WRITER    enforceable  (two captures, one run id)
  E5  INTRA-SHAPE MEMORY OUTLIER      report-only until J>=20 (sibling-relative, not MemTotal)
  E6  ZOMBIES UNDER A LIVE PARENT     enforceable  (a count at an instant)
Deliberately absent: anything in seconds; a poll-loop detector (fires on the
sanctioned waiters wl_wait.py and ci-trace.py --wait); the ~880-spawn count (the
process boundary IS the suite's fixture); fork depth (a fact, not a finding).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import sys
from pathlib import Path

# WHAT "WAITING ON MY OWN CHILD" ACTUALLY LOOKS LIKE ON THIS KERNEL, counted over
# the real corpus rather than guessed. The old set was three names and missed the
# single most common one: `do_sigtimedwait`, which is bashcov-sup waiting on the one
# child it supervises -- 4,422 samples, and the ROOT of every capture, which is why
# rank()'s blocked share below read 0% by construction. `pipe_read` never occurs on
# 6.18 at all; the kernel calls it `anon_pipe_read`. Symbol names move between
# kernels, so this set is a LABEL, never the verdict on its own.
DEFERRING = {
    "do_wait",
    "do_sigtimedwait",
    "anon_pipe_read",
    "pipe_wait_readable",
    "pipe_read",  # pre-6.x spelling; harmless where the symbol no longer exists
    "poll_schedule_timeout",
    "do_epoll_wait",
}
# A literal sleep is NOT deferring: it is the thing E3 exists to notice.
SLEEPING = {"hrtimer_nanosleep"}


def norm_wchan(w: str | None) -> str | None:
    """`do_sigtimedwait.isra.0` -> `do_sigtimedwait`.

    GCC clone suffixes (`.isra.N`, `.constprop.N`) vary per kernel BUILD, so a set
    membership test against the raw string silently stops matching after an upgrade.
    """
    if not w:
        return w
    return w.split(".", 1)[0]


E1_MIN_CHILDREN = 8
E1_SATURATION = 0.9  # R-fraction, a ratio of counts
E1_CPU_SHARE = (
    0.9  # children's CPU over tree CPU, both in ticks -- invariant under wall-only dilation
)
E5_MIN_SIBLINGS = 5
E5_RATIO = 8
E5_MIN_MEDIAN_KB = 1024  # below one MiB these are not the processes E5 is about
E6_MIN_ZOMBIES = 3
JUDGEABLE_FRACTION = 0.8
ADMISSION_MIN_J = 20
ADMISSION_MAX_RATE = 0.05


# ---------------------------------------------------------------- capture ---
class Capture:
    """One sampled tree: the S records and the trailing RUN record of one run."""

    def __init__(self, samples: list[dict], run: dict, source: str = ""):
        self.samples = samples
        self.run = run
        self.source = source
        # Judgeability is a property of the INSTRUMENT (did it sample enough), decided
        # once here and carried through dilate() unchanged: dilating a recording does
        # not retroactively change how many samples were taken.
        n, exp = int(run.get("samples_n", 0)), int(run.get("expected_n", 0))
        self.judgeable = (
            (not run.get("unsampled")) and n >= 3 and (exp == 0 or n >= JUDGEABLE_FRACTION * exp)
        )

    @property
    def run_id(self) -> str:
        return str(self.run.get("run", ""))


def load_capture(path: Path) -> Capture | None:
    samples, run = [], None
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            if rec.get("k") == "S":
                samples.append(rec)
            elif rec.get("k") == "RUN":
                run = rec
    except OSError:
        return None
    if run is None:
        return None
    return Capture(samples, run, str(path))


def dilate(cap: Capture, k: float) -> Capture:
    """Stretch WALL by k; leave CPU alone. This is what machine load does."""
    samples = []
    for s in cap.samples:
        s2 = dict(s)
        s2["t_ms"] = int(s["t_ms"] * k)
        samples.append(s2)
    run = dict(cap.run)
    for key in ("wall_ms", "expected_n"):
        if key in run:
            run[key] = int(run[key] * k)
    if isinstance(run.get("psi_us"), dict):
        run["psi_us"] = {
            a: (int(b * k) if isinstance(b, int) else b) for a, b in run["psi_us"].items()
        }
    out = Capture(samples, run, cap.source)
    out.judgeable = cap.judgeable
    return out


# ---------------------------------------------------------- per-pid views ---
def aggregate(cap: Capture) -> dict[int, dict]:
    """Per-pid lifetime, state histogram, peak memory, write set, last cpu ticks."""
    agg: dict[int, dict] = {}
    for s in cap.samples:
        t = s["t_ms"]
        for p in s["p"]:
            a = agg.setdefault(
                p["pid"],
                {
                    "pid": p["pid"],
                    "ppid": p["ppid"],
                    "comm": p["comm"],
                    "depth": p.get("depth", 0),
                    "first": t,
                    "last": t,
                    "hist": {},
                    "hwm_kb": 0,
                    "wfd": set(),
                    "cpu": 0,
                    "zombie_seen": 0,
                },
            )
            a["first"] = min(a["first"], t)
            a["last"] = max(a["last"], t)
            a["hist"][p["state"]] = a["hist"].get(p["state"], 0) + 1
            a["hwm_kb"] = max(a["hwm_kb"], int(p.get("hwm_kb") or 0))
            a["wfd"].update(p.get("wfd") or [])
            a["cpu"] = max(a["cpu"], int(p.get("utime", 0)) + int(p.get("stime", 0)))
            if p["state"] == "Z":
                a["zombie_seen"] += 1
    return agg


def r_fraction(a: dict) -> float:
    h = a["hist"]
    total = sum(h.get(st, 0) for st in ("R", "S", "D"))
    return (h.get("R", 0) / total) if total else 0.0


def overlaps(a: dict, b: dict) -> bool:
    """[a,b] ∩ [c,d] ≠ ∅ ⟺ a<d ∧ c<b -- an order relation, invariant under any k>0."""
    return a["first"] < b["last"] and b["first"] < a["last"]


# ------------------------------------------------------------- predicates ---
def logical_root(cap: Capture, agg: dict[int, dict]) -> int | None:
    """The pid whose children are the WORK. Under the Bash profiler every bash is
    re-exec'd in place under bashcov-sup, which then forks the real shell -- so a
    capture rooted at exec.ts's child sees a supervisor root with exactly one
    `bash` child, and a child-counting predicate would never see the fanout. The
    supervisor is transparent: descend through any chain of single-child
    bashcov-sup nodes. A supervisor with 0 or 2+ children is NOT descended (that
    is not the wrapper shape) -- unresolved stays unresolved."""
    root = cap.run.get("root_pid")
    while True:
        a = agg.get(root)
        if not a or a["comm"] != "bashcov-sup":
            return root
        kids = [b for b in agg.values() if b["ppid"] == root]
        if len(kids) != 1:
            return root
        root = kids[0]["pid"]


def e1_sequential_fanout(cap: Capture) -> list[dict]:
    if not cap.judgeable or not cap.samples:
        return []
    agg = aggregate(cap)
    root_pid = logical_root(cap, agg)
    kids = [a for a in agg.values() if a["ppid"] == root_pid]
    if len(kids) < E1_MIN_CHILDREN:
        return []
    # (1) strictly sequential: no two lifetimes overlap.
    if any(overlaps(x, y) for i, x in enumerate(kids) for y in kids[i + 1 :]):
        return []
    # (2) each saturated, as an R-fraction of samples -- NOT cpu/wall.
    if any(r_fraction(a) < E1_SATURATION for a in kids):
        return []
    # (3) the children ARE the work: their CPU ticks over the tree's, both un-dilated.
    tree_cpu = sum(a["cpu"] for a in agg.values()) or 1
    if sum(a["cpu"] for a in kids) / tree_cpu < E1_CPU_SHARE:
        return []
    # (4) POSITIVE evidence of disjoint write domains. Nothing observed = unresolved = no finding.
    if any(not a["wfd"] for a in kids):
        return []
    root = agg.get(root_pid, {"wfd": set()})
    if any(a["wfd"] & root["wfd"] for a in kids):
        return []
    if any(x["wfd"] & y["wfd"] for i, x in enumerate(kids) for y in kids[i + 1 :]):
        return []
    return [
        {
            "class": "E1",
            "enforce": True,
            "run": cap.run_id,
            "children": len(kids),
            "min_r_fraction": round(min(r_fraction(a) for a in kids), 3),
            "why": "%d children, pairwise-disjoint lifetimes, each >= %.2f R-fraction, disjoint observed write sets"
            % (len(kids), E1_SATURATION),
        }
    ]


def e4_concurrent_writers(
    caps: list[Capture], exclusions: set[frozenset] | None = None
) -> list[dict]:
    """Two captures under one run id, overlapping in wall, sharing a written repo path."""
    exclusions = exclusions or set()
    out: list[dict] = []
    by_run: dict[str, list[Capture]] = {}
    for c in caps:
        if c.judgeable and c.run_id:
            by_run.setdefault(c.run_id, []).append(c)
    for rid, group in by_run.items():
        views = []
        for c in group:
            agg = aggregate(c)
            wset: set[str] = set()
            for a in agg.values():
                wset |= a["wfd"]
            first = min((a["first"] for a in agg.values()), default=0)
            last = max((a["last"] for a in agg.values()), default=0)
            # Offset by the run-relative start so two captures' clocks are comparable:
            # each capture's t_ms is relative to its own start, and the RUN record carries
            # `t0_ms` (absolute) when the caller supplies it. Without it, overlap cannot be
            # decided and the pair is skipped -- unresolved is never "no overlap".
            t0 = c.run.get("t0_ms")
            views.append((c, wset, first, last, t0))
        for i, (ca, wa, fa, la, ta) in enumerate(views):
            for cb, wb, fb, lb, tb in views[i + 1 :]:
                if ta is None or tb is None:
                    continue
                if not (ta + fa < tb + lb and tb + fb < ta + la):
                    continue
                shared = wa & wb
                if not shared:
                    continue
                key = frozenset((Path(ca.source).name, Path(cb.source).name))
                if key in exclusions:
                    continue
                out.append(
                    {
                        "class": "E4",
                        "enforce": True,
                        "run": rid,
                        "a": Path(ca.source).name,
                        "b": Path(cb.source).name,
                        "shared": sorted(shared)[:5],
                        "why": "overlapping lifetimes and %d shared written path(s) with no declared exclusion"
                        % len(shared),
                    }
                )
    return out


def e5_memory_outlier(cap: Capture) -> list[dict]:
    if not cap.judgeable:
        return []
    agg = aggregate(cap)
    groups: dict[tuple[int, str], list[dict]] = {}
    for a in agg.values():
        groups.setdefault((a["ppid"], a["comm"]), []).append(a)
    out = []
    for (ppid, comm), sibs in groups.items():
        if len(sibs) < E5_MIN_SIBLINGS:
            continue
        hwms = sorted(a["hwm_kb"] for a in sibs)
        # UNMEASURED IS NOT SMALL. The first live run fired this twice -- `grep` x11 at
        # "2348x" and `basename` x5 at "12.5x" -- because short-lived siblings sampled
        # once carry hwm_kb=0, the median collapsed onto an `or 1` floor, and the ratio
        # exploded. A sibling with no measured peak is UNRESOLVED, and Rule 3 says an
        # unresolved input kills a finding rather than feeding it.
        if hwms[0] <= 0 or hwms[len(hwms) // 2] < E5_MIN_MEDIAN_KB:
            continue
        med = hwms[len(hwms) // 2]
        top = hwms[-1]
        if top / med >= E5_RATIO:
            worst = max(sibs, key=lambda a: a["hwm_kb"])
            out.append(
                {
                    "class": "E5",
                    "enforce": False,
                    "run": cap.run_id,
                    "ppid": ppid,
                    "comm": comm,
                    "siblings": len(sibs),
                    "ratio": round(top / med, 1),
                    "worst_pid": worst["pid"],
                    "why": "one of %d same-comm siblings peaks at %.1fx the median (sibling-relative, machine-free)"
                    % (len(sibs), top / med),
                }
            )
    return out


def e6_zombies(cap: Capture) -> list[dict]:
    if not cap.judgeable:
        return []
    # per sample: {ppid: set(zombie pids)}, then require >=E6_MIN at one sample AND
    # a non-decreasing set across >=2 consecutive samples with the parent still live.
    per_sample: list[dict[int, set[int]]] = []
    live_parents: list[set[int]] = []
    for s in cap.samples:
        z: dict[int, set[int]] = {}
        live: set[int] = set()
        for p in s["p"]:
            if p["state"] == "Z":
                z.setdefault(p["ppid"], set()).add(p["pid"])
            else:
                live.add(p["pid"])
        per_sample.append(z)
        live_parents.append(live)
    out = []
    seen: set[int] = set()
    for i in range(1, len(per_sample)):
        for ppid, zs in per_sample[i].items():
            prev = per_sample[i - 1].get(ppid, set())
            if (
                len(zs) >= E6_MIN_ZOMBIES
                and prev
                and prev <= zs
                and ppid in live_parents[i]
                and ppid not in seen
            ):
                seen.add(ppid)
                out.append(
                    {
                        "class": "E6",
                        "enforce": True,
                        "run": cap.run_id,
                        "parent": ppid,
                        "zombies": len(zs),
                        "why": "%d unreaped children under a live parent across consecutive samples"
                        % len(zs),
                    }
                )
    return out


def derive(caps: list[Capture], exclusions: set[frozenset] | None = None) -> list[dict]:
    out: list[dict] = []
    for c in caps:
        out += e1_sequential_fanout(c) + e5_memory_outlier(c) + e6_zombies(c)
    out += e4_concurrent_writers(caps, exclusions)
    return sorted(out, key=lambda f: json.dumps(f, sort_keys=True))


def admissible(fires: int, judgeable: int) -> tuple[bool, str]:
    """May a class ENFORCE? J>=20 and the one-sided 95% Wilson upper bound on F/J <= 0.05."""
    if judgeable < ADMISSION_MIN_J:
        return False, "report-only for lack of denominator (J=%d < %d)" % (
            judgeable,
            ADMISSION_MIN_J,
        )
    z = 1.645
    p = fires / judgeable
    denom = 1 + z * z / judgeable
    centre = p + z * z / (2 * judgeable)
    half = z * math.sqrt(p * (1 - p) / judgeable + z * z / (4 * judgeable * judgeable))
    upper = (centre + half) / denom
    if upper <= ADMISSION_MAX_RATE:
        return True, "fire rate %.3f, upper bound %.3f <= %.2f" % (p, upper, ADMISSION_MAX_RATE)
    return False, "demoted: fire rate %.3f, upper bound %.3f > %.2f" % (
        p,
        upper,
        ADMISSION_MAX_RATE,
    )


# --------------------------------------------------------------- controls ---
def _synthetic(
    children: int, sequential: bool, r_frac: float, wfd_disjoint: bool, wfd_any: bool = True
) -> Capture:
    """A root with N children; every field is synthetic and labelled so."""
    samples = []
    per_child = 10
    for i in range(children):
        for j in range(per_child):
            t = (i * per_child + j) * 100 if sequential else j * 100
            procs = [
                {
                    "pid": 1,
                    "ppid": 0,
                    "comm": "bash",
                    "state": "S",
                    "wchan": "do_wait",
                    "utime": 1,
                    "stime": 0,
                    "hwm_kb": 5000,
                    "wfd": [],
                    "depth": 0,
                }
            ]
            st = "R" if j < int(per_child * r_frac) else "S"
            wfd = [("out/%d.txt" % i) if wfd_disjoint else "out/shared.txt"] if wfd_any else []
            procs.append(
                {
                    "pid": 100 + i,
                    "ppid": 1,
                    "comm": "work",
                    "state": st,
                    "wchan": None,
                    "utime": 50,
                    "stime": 0,
                    "hwm_kb": 10000,
                    "wfd": wfd,
                    "depth": 1,
                }
            )
            samples.append({"k": "S", "run": "syn", "t_ms": t, "p": procs})
    n = len(samples)
    run = {
        "k": "RUN",
        "run": "syn",
        "root_pid": 1,
        "samples_n": n,
        "expected_n": n,
        "wall_ms": (samples[-1]["t_ms"] + 100) if samples else 0,
        "unsampled": False,
    }
    return Capture(samples, run, "syn-%d-%s" % (children, "seq" if sequential else "par"))


# A fixture that spawns bash must NOT be re-exec'd under the profiler's own
# supervisor (BASH_ENV is live on this machine): the tree would gain a
# bashcov-sup layer and every depth assertion shifts by one. Caught by the hook
# battery the first time it ran with profiling on -- the profiler measuring its
# own test. The BASH_ENV file honours WORKLIST_PROFILE=off.
_FIXTURE_ENV = {**os.environ, "WORKLIST_PROFILE": "off"}


def selftest() -> int:
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    import time  # noqa: PLC0415

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import wl_ressample as R  # noqa: PLC0415

    bad = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal bad
        print(
            "  %s  %s%s"
            % (
                "PASS" if ok else "FAIL",
                name,
                ("\n        " + detail) if (detail and not ok) else "",
            )
        )
        if not ok:
            bad += 1

    # ---- E1, fire and the four things that must each kill it ----
    fire = _synthetic(10, sequential=True, r_frac=1.0, wfd_disjoint=True)
    check(
        "E1 FIRES on 10 sequential saturated children with disjoint observed writes",
        [f["class"] for f in derive([fire])] == ["E1"],
    )
    check(
        "E1 silent when children OVERLAP (interval order relation)",
        not derive([_synthetic(10, False, 1.0, True)]),
    )
    check(
        "E1 silent when children are not R-saturated", not derive([_synthetic(10, True, 0.5, True)])
    )
    check(
        "E1 silent on a SHARED write (Rule 3: absence of disjointness kills it)",
        not derive([_synthetic(10, True, 1.0, False)]),
    )
    check(
        "E1 silent when NO write was observed (unresolved is never 'independent')",
        not derive([_synthetic(10, True, 1.0, True, wfd_any=False)]),
    )
    sup = _synthetic(10, sequential=True, r_frac=1.0, wfd_disjoint=True)
    for smp in sup.samples:  # wrap: a bashcov-sup root (pid 99) whose single child is the old root
        for pr in smp["p"]:
            pr["depth"] += 1
            if pr["pid"] == 1:
                pr["ppid"] = 99
        smp["p"].insert(
            0,
            {
                "pid": 99,
                "ppid": 0,
                "comm": "bashcov-sup",
                "state": "S",
                "wchan": "do_wait",
                "utime": 0,
                "stime": 0,
                "hwm_kb": 500,
                "wfd": [],
                "depth": 0,
            },
        )
    sup.run["root_pid"] = 99
    check(
        "E1 CONTROL: a bashcov-sup root is transparent -- the supervised fanout still fires",
        [f["class"] for f in derive([sup])] == ["E1"],
    )
    check(
        "E1 silent below the child floor",
        not derive([_synthetic(E1_MIN_CHILDREN - 1, True, 1.0, True)]),
    )

    # ---- D1: DILATION INVARIANCE, wall-only ----
    caps = [fire, _synthetic(10, False, 1.0, True), _synthetic(10, True, 0.5, True)]
    base = json.dumps(derive(caps), sort_keys=True)
    for k in (0.4, 2.3, 7.0):
        check(
            "D1: findings byte-identical under dilate(k=%.1f)" % k,
            json.dumps(derive([dilate(c, k) for c in caps]), sort_keys=True) == base,
        )
    # BOTH clocks must move, and this control was weaker than it claimed until a
    # mutant showed it: it checked only run.wall_ms, so stripping the SAMPLE t_ms
    # scaling left every verdict unchanged and the control green. Lifetimes are what
    # the concurrency predicates read, so the samples are the clock that matters.
    _d = dilate(fire, 2.3)
    _a0, _a1 = aggregate(fire), aggregate(_d)
    check(
        "D1 CONTROL: dilate really moves wall -- run.wall_ms AND every sample t_ms (a no-op operator would pass vacuously)",
        _d.run["wall_ms"] != fire.run["wall_ms"]
        and all(_a1[k]["last"] == int(_a0[k]["last"] * 2.3) for k in _a0 if _a0[k]["last"]),
    )

    check(
        "D1 CONTROL: dilate leaves CPU ticks alone",
        all(
            a["cpu"] == b["cpu"]
            for a, b in zip(
                aggregate(fire).values(), aggregate(dilate(fire, 2.3)).values(), strict=True
            )
        ),
    )

    # ---- D2: no duration literal comparisons in THIS file ----
    src = Path(__file__).read_text(encoding="utf-8")
    body = src.split('"""', 2)[2]  # skip the module docstring, which discusses seconds on purpose
    hits = [
        m.group(0)
        for m in re.finditer(r"\b[a-z_]*(?:_ms|_s|wall|t_ms)\b\s*(?:[<>]=?|==)\s*\d", body)
    ]
    hits += [
        m.group(0) for m in re.finditer(r"\d\s*(?:[<>]=?|==)\s*[a-z_]*(?:_ms|_s|wall|t_ms)\b", body)
    ]
    check(
        "D2: this module compares no duration field against a numeric literal", not hits, str(hits)
    )
    check(
        "D2 CONTROL: the scan would catch one",
        bool(
            re.search(
                r"\b[a-z_]*(?:_ms|_s|wall|t_ms)\b\s*(?:[<>]=?|==)\s*\d",
                "if wall" + "_m" + "s > 4000:",
            )
        ),
    )

    # ---- E6 zombies: a REAL fixture, then the transient control ----
    z_parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,time\nps=[subprocess.Popen(['true']) for _ in range(4)]\ntime.sleep(2.5)",
        ],
        env=_FIXTURE_ENV,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    d = Path(tempfile.mkdtemp(prefix="profile-"))
    try:
        time.sleep(0.4)
        R.watch(z_parent.pid, d / "z.jsonl", interval_ms=200, run_id="zt")
        zc = load_capture(d / "z.jsonl")
        zf = [f for f in derive([zc]) if f["class"] == "E6"] if zc else []
        check(
            "E6 FIRES on a real parent that never reaps 4 children",
            len(zf) == 1 and zf[0]["zombies"] >= 3,
            str(zf),
        )
        # Transient control: `a & b & c & wait` reaps; must be silent.
        w_parent = subprocess.Popen(
            ["bash", "-c", "true & true & true & true & wait; sleep 1.2"], stdin=subprocess.DEVNULL
        )
        time.sleep(0.2)
        R.watch(w_parent.pid, d / "w.jsonl", interval_ms=200, run_id="wt")
        wc = load_capture(d / "w.jsonl")
        check(
            "E6 CONTROL: a parent that `wait`s is silent",
            wc is not None and not [f for f in derive([wc]) if f["class"] == "E6"],
        )
        # Judgeability: a capture with too few samples yields nothing, and says so.
        starved = (
            Capture(zc.samples[:1], dict(zc.run, samples_n=1, expected_n=10), "starved")
            if zc
            else None
        )
        check(
            "an unjudgeable capture derives NOTHING (silence, never a verdict)",
            starved is not None and not starved.judgeable and not derive([starved]),
        )
    finally:
        with contextlib.suppress(Exception):
            z_parent.kill()
        import shutil  # noqa: PLC0415

        shutil.rmtree(d, ignore_errors=True)

    # ---- E5 sibling-relative outlier ----
    def sibs(hwms: list[int]) -> Capture:
        procs = [
            {
                "pid": 1,
                "ppid": 0,
                "comm": "xargs",
                "state": "S",
                "wchan": "do_wait",
                "utime": 0,
                "stime": 0,
                "hwm_kb": 1000,
                "wfd": [],
                "depth": 0,
            }
        ]
        procs += [
            {
                "pid": 10 + i,
                "ppid": 1,
                "comm": "shellcheck",
                "state": "R",
                "wchan": None,
                "utime": 5,
                "stime": 0,
                "hwm_kb": h,
                "wfd": [],
                "depth": 1,
            }
            for i, h in enumerate(hwms)
        ]
        s = [{"k": "S", "run": "e5", "t_ms": t, "p": procs} for t in range(0, 400, 100)]
        return Capture(
            s,
            {
                "k": "RUN",
                "run": "e5",
                "root_pid": 1,
                "samples_n": 4,
                "expected_n": 4,
                "unsampled": False,
            },
            "e5",
        )

    check(
        "E5 CONTROL: siblings with an UNMEASURED (0) peak are unresolved and stay silent -- the first live false positive",
        not derive([sibs([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2_714_000])]),
    )
    check(
        "E5 CONTROL: a tiny-median sibling set (short-lived greps) stays silent",
        not derive([sibs([40, 40, 40, 40, 40, 900])]),
    )
    check(
        "E5 fires on the shellcheck shape (one sibling at 27x the median) and is REPORT-ONLY",
        [(f["class"], f["enforce"]) for f in derive([sibs([98_000] * 11 + [2_714_000])])]
        == [("E5", False)],
    )
    check(
        "E5 silent on an even spread",
        not derive([sibs([98_000, 100_000, 95_000, 99_000, 97_000, 101_000])]),
    )
    check("E5 silent below the sibling floor", not derive([sibs([100] * 3 + [10_000])]))

    # ---- E4 two captures under one run id ----
    def cap_with_write(name: str, path: str, t0: int) -> Capture:
        s = [
            {
                "k": "S",
                "run": "r1",
                "t_ms": t,
                "p": [
                    {
                        "pid": 7,
                        "ppid": 0,
                        "comm": "bash",
                        "state": "R",
                        "wchan": None,
                        "utime": 1,
                        "stime": 0,
                        "hwm_kb": 1,
                        "wfd": [path],
                        "depth": 0,
                    }
                ],
            }
            for t in range(0, 500, 100)
        ]
        return Capture(
            s,
            {
                "k": "RUN",
                "run": "r1",
                "root_pid": 7,
                "samples_n": 5,
                "expected_n": 5,
                "unsampled": False,
                "t0_ms": t0,
            },
            name,
        )

    a, b = (
        cap_with_write("gate-a", ".ci/scripts/x.sh", 0),
        cap_with_write("gate-b", ".ci/scripts/x.sh", 200),
    )
    check(
        "E4 FIRES on two overlapping captures writing one repo path",
        [f["class"] for f in derive([a, b])] == ["E4"],
    )
    check(
        "E4 silent with a declared exclusion for the pair",
        not derive([a, b], exclusions={frozenset({"gate-a", "gate-b"})}),
    )
    check(
        "E4 silent when lifetimes do NOT overlap",
        not derive([a, cap_with_write("gate-c", ".ci/scripts/x.sh", 5000)]),
    )
    check(
        "E4 silent on different paths",
        not derive([a, cap_with_write("gate-d", ".ci/scripts/y.sh", 200)]),
    )
    check(
        "E4 UNRESOLVED (no t0) is skipped, never read as no-overlap",
        not derive(
            [a, Capture(b.samples, {k: v for k, v in b.run.items() if k != "t0_ms"}, "gate-e")]
        ),
    )

    # ---- admission floor ----
    check(
        "admission: J<20 is report-only for lack of denominator",
        admissible(0, 8) == (False, "report-only for lack of denominator (J=8 < 20)"),
    )
    # THE TWO CORRECTIONS OF THIS WAVE, planted. Both were silent defects: the set
    # missed the most common wchan in the corpus, and the share read the supervisor.
    check(
        "norm_wchan strips a GCC clone suffix",
        norm_wchan("do_sigtimedwait.isra.0") == "do_sigtimedwait"
        and norm_wchan("do_wait") == "do_wait"
        and norm_wchan(None) is None,
    )
    check(
        "the supervisor's own wait is DEFERRING (it was not, and it is 291/291 roots)",
        norm_wchan("do_sigtimedwait.isra.0") in DEFERRING,
    )
    check(
        "a literal sleep is NOT deferring -- that is the thing worth reporting",
        "hrtimer_nanosleep" not in DEFERRING and "hrtimer_nanosleep" in SLEEPING,
    )
    check("admission: 0 fires over 200 is admissible", admissible(0, 200)[0])
    check(
        "admission: 5%% point rate over 40 is NOT admissible (upper bound > 0.05)",
        not admissible(2, 40)[0],
    )
    return bad


def rank(root: Path, days: int = 30) -> tuple[list[dict], list[dict]]:
    """High-to-low IMPACT over the time-based corpus (operator ruling 2026-09-03).

    Two tables. SHAPES from exit records: total CPU seconds is the primary key --
    it is what parallelism or caching would give back -- then invocations, peak RSS,
    and the wall share. GATES from captures: tree CPU ticks, peak RSS, and the blocked
    share (samples whose frontier wchan was DEFERRING or a sleep). Findings are counted
    per gate so a structural finding sits beside the cost it would recover.
    """
    import time  # noqa: PLC0415

    cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    shapes: dict[str, dict] = {}
    gates: dict[str, dict] = {}
    for day in sorted(p for p in root.iterdir() if p.is_dir() and p.name >= cutoff):
        ex = day / "exit.jsonl"
        if ex.exists():
            for ln in ex.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("v") != 1:
                    continue
                e = shapes.setdefault(
                    r["shape"],
                    {"shape": r["shape"], "n": 0, "cpu_ms": 0, "wall_ms": 0, "rss_kb_max": 0},
                )
                e["n"] += 1
                e["cpu_ms"] += int(r.get("cpu_ms", 0)) + int(r.get("child_cpu_ms", 0))
                e["wall_ms"] += int(r.get("wall_ms", 0))
                e["rss_kb_max"] = max(
                    e["rss_kb_max"], int(r.get("rss_kb", 0)), int(r.get("child_rss_kb_max", 0))
                )
        for run_dir in sorted(p for p in day.iterdir() if p.is_dir()):
            caps = [c for c in (load_capture(x) for x in sorted(run_dir.glob("*.jsonl"))) if c]
            found = {}
            for f in derive(caps):
                found[f.get("run", "")] = found.get(f.get("run", ""), 0) + 1
            for c in caps:
                name = Path(c.source).stem
                g = gates.setdefault(
                    name,
                    {
                        "gate": name,
                        "runs": 0,
                        "cpu_ticks": 0,
                        "rss_kb_max": 0,
                        "blocked": 0,
                        "samples": 0,
                        "findings": 0,
                    },
                )
                g["runs"] += 1
                agg = aggregate(c)
                g["cpu_ticks"] += sum(a["cpu"] for a in agg.values())
                g["rss_kb_max"] = max(
                    g["rss_kb_max"], max((a["hwm_kb"] for a in agg.values()), default=0)
                )
                for smp in c.samples:
                    g["samples"] += 1
                    # THE FRONTIER, NOT THE ROOT. This read `p[0]`, which under the
                    # supervisor IS the supervisor -- parked in do_sigtimedwait for
                    # 291 of 291 captures while the work happened underneath it. The
                    # share was 0% by construction and told the reader nothing.
                    #
                    # A tree counts as waiting only when NOTHING in it is running:
                    # no process in R or D, and at least one parked somewhere that is
                    # not "waiting on my own child". A deferring parent above a
                    # running child is the normal shape of every $( ) capture.
                    procs = smp.get("p") or []
                    if any(pr.get("state") in ("R", "D") for pr in procs):
                        continue
                    labels = {norm_wchan(pr.get("wchan")) for pr in procs}
                    if labels - DEFERRING - {None, "0"}:
                        g["blocked"] += 1
                g["findings"] += sum(1 for f in derive([c]))
    top_shapes = sorted(shapes.values(), key=lambda e: -e["cpu_ms"])
    top_gates = sorted(gates.values(), key=lambda g: -g["cpu_ticks"])
    return top_shapes, top_gates


def rank_markdown(root: Path, days: int = 30) -> str:
    shapes, gates = rank(root, days)
    tot = sum(e["cpu_ms"] for e in shapes) or 1
    out = [
        "# Resource profile -- impact ranking (last %d days)" % days,
        "",
        "Generated by wl_profile.py --rank from %s" % root,
        "",
        "## Shapes by total CPU (what parallelism or caching would give back)",
        "",
        "| rank | shape | invocations | cpu s | cpu share | wall s | peak rss MB |",
        "|--:|---|--:|--:|--:|--:|--:|",
    ]
    for i, e in enumerate(shapes[:25], 1):
        out.append(
            "| %d | `%s` | %d | %.1f | %.0f%% | %.1f | %.0f |"
            % (
                i,
                e["shape"],
                e["n"],
                e["cpu_ms"] / 1000,
                100 * e["cpu_ms"] / tot,
                e["wall_ms"] / 1000,
                e["rss_kb_max"] / 1024,
            )
        )
    out += [
        "",
        "## CI gates by tree CPU (captures)",
        "",
        "| rank | gate | runs | cpu ticks | peak rss MB | blocked share | findings |",
        "|--:|---|--:|--:|--:|--:|--:|",
    ]
    for i, g in enumerate(gates[:25], 1):
        share = (100 * g["blocked"] / g["samples"]) if g["samples"] else 0
        out.append(
            "| %d | `%s` | %d | %d | %.0f | %.0f%% | %d |"
            % (
                i,
                g["gate"],
                g["runs"],
                g["cpu_ticks"],
                g["rss_kb_max"] / 1024,
                share,
                g["findings"],
            )
        )
    out += [
        "",
        "A high blocked share with low CPU is a wait that might be event-driven; high CPU with sequential children is what E1 looks for. Findings are report-only until the class is admissible (see check:ci-resprofile).",
        "",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        n = selftest()
        print("%s profile selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        sys.exit(1 if n else 0)
    if "--derive" in sys.argv:
        caps = [
            c
            for c in (load_capture(Path(p)) for p in sys.argv[sys.argv.index("--derive") + 1 :])
            if c
        ]
        print(
            json.dumps(
                {
                    "captures": len(caps),
                    "judgeable": sum(c.judgeable for c in caps),
                    "findings": derive(caps),
                },
                indent=1,
            )
        )
        sys.exit(0)
    if "--rank" in sys.argv:
        root = Path(sys.argv[sys.argv.index("--rank") + 1])
        days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 30
        md = rank_markdown(root, days)
        (root / "RANK.md").write_text(md, encoding="utf-8")
        print(md)
        sys.exit(0)
    print(
        "usage: wl_profile.py --selftest | --derive <capture.jsonl>... | --rank <stats-root> [--days N]",
        file=sys.stderr,
    )
    sys.exit(2)
