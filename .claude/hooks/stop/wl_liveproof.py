"""`worklist.py --live-proof`: record a live receipt for a plan's LP box and, with `--tick`, close the box in the same run (agent/plans/PLAN-tested-on-bench.md, Design item "Agent verb").

THE ENGINE IS NOT RESTATED HERE. The box's Accept sub-line is parsed by `rediacc_ci.proof.live_tier.accept_of`, the one definition the recorder and `check:ci-plan-live-proof` both read, loaded through `rediacc_hooks/syspath.py` (`import_from_ci`). The run itself is `python3 -m rediacc_ci.ops.live_proof record ...` as a SUBPROCESS, because the recorder re-executes itself under the `deploy-bench` Bitwarden profile and a bench check must not inherit a half-imported hook process. Its rc and stderr are surfaced as they came.

THE TICK IS `--plan-tick`'S OWN PATH. `worklist.py` hands `run` a `tick` callable that drives `_plantick_cli` (the dependency gate, `wl_planrec.plan_tick`, the plan plus `.ci/config/plan-boxes.json` written together), so a live-proof tick cannot drift from an ordinary one. It fires only after the recorder exited 0 under `--write` AND the VERIFIED row it named is read back out of `agent/ledgers/live-proof.jsonl` for this plan and box. The evidence line is the plan's: `live-proof <id> <target> <check> rc=0 v=<version>`.

NEVER COMMITS. The ledger row, the plan and the box ledger ride one commit, and the success message says so.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import TYPE_CHECKING, Any

import wl_planrec as R

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

HERE = pathlib.Path(__file__).resolve().parent

USAGE = (
    "usage: worklist.py --live-proof <me>\n"
    "       worklist.py --live-proof <me> <agent/plans/PLAN-x.md> <LP-box-sig> [--write] [--tick]\n"
    "\n"
    "  With only <me>: list every open `LP-<target> [live]` box and its Accept line.\n"
    "  With a plan and a box: read the box's `Accept: live-proof <target> <check> [machine=<alias>]`\n"
    "  sub-line and run `python3 -m rediacc_ci.ops.live_proof record` with those arguments.\n"
    "  --write   pass --write to the recorder, so a VERIFIED run appends its row to\n"
    "            agent/ledgers/live-proof.jsonl (without it the run is a dry run)\n"
    "  --tick    after a VERIFIED row is written, close the box through the --plan-tick path\n"
    "            with the evidence `live-proof <id> <target> <check> rc=0 v=<version>`;\n"
    "            needs --write and an investigation row for the box (--plan-investigate)\n"
    "  Never commits: the ledger row, the plan and .ci/config/plan-boxes.json ride one commit.\n"
)

LIST_HEADER = "open live-proof boxes (`LP-<target> [live]`) and the Accept line each one runs:"

#: `check_plan_live_proof.LP_BOX_RE`, the gate's own reading of an LP box, applied to the box body; `LP-none` is not a box this verb can run.
LP_BOX_RE = re.compile(r"^LP-([A-Za-z0-9_-]+)\b")
#: The recorder's success line (`log.info(f"{outcome.message}: ...")`, message `VERIFIED <row id>`), on stderr.
VERIFIED_RE = re.compile(r"\bVERIFIED (lp-[0-9a-f]{12})\b")
#: Any `Accept:` text, for the refusal that names a non-live-proof form; the live-proof form itself is live_tier's to parse.
ACCEPT_ANY_RE = re.compile(r"\bAccept:\s*(.*?)\s*$")
_BOX_LINE = re.compile(r"^\s*[-*]\s+\[[ xX?>]\]\s")
_HEADING = re.compile(r"^#{1,6}\s")
PLANS_DIR = "agent/plans/"
LEDGER_REL = "agent/ledgers/live-proof.jsonl"
FORM = "`live-proof <target> <check> [machine=<alias>]`"


class RefusedError(Exception):
    """A refusal before or after the recorder ran; `rc` is the exit code the verb ends with."""

    def __init__(self, message: str, rc: int = 2) -> None:
        super().__init__(message)
        self.rc = rc


def _live_tier() -> Any:
    """`rediacc_ci.proof.live_tier`, through the canonical `.claude` hop loaded BY FILE (the wl_prreview shape)."""
    hop = HERE.parents[1] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", hop)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % hop)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.import_from_ci("rediacc_ci.proof.live_tier")


def lp_boxes(text: str) -> list[tuple[int, str, str, str]]:
    """`wl_planrec.open_boxes` narrowed to the `LP-<target>` boxes, `LP-none` excluded; same 4-tuples."""
    out = []
    for box in R.open_boxes(text):
        m = LP_BOX_RE.match(box[2])
        if m and m.group(1) != "none":
            out.append(box)
    return out


def accept_raw(text: str, line: int) -> str | None:
    """The text after `Accept:` on the box at 0-based `line`: its sub-lines first (live_tier's termination rule), then the box line itself. Backticks dropped. None when the box carries no Accept at all."""
    lines = text.splitlines()
    for raw in lines[line + 1 :]:
        if _BOX_LINE.match(raw) or _HEADING.match(raw) or (raw and not raw[0].isspace()):
            break
        m = ACCEPT_ANY_RE.search(raw.replace("`", ""))
        if m:
            return m.group(1)
    if 0 <= line < len(lines):
        m = ACCEPT_ANY_RE.search(lines[line].replace("`", ""))
        if m:
            return m.group(1)
    return None


def parse_accept(text: str, line: int, lt: Any = None) -> tuple[str, str, str | None]:
    """(target, check, machine) of the box's live-proof Accept line. RefusedError for no Accept, a non-live-proof form, or an argument the registry does not take."""
    lt = lt or _live_tier()
    accept = lt.accept_of(text, line)
    if accept is None:
        raw = accept_raw(text, line)
        if raw is None:
            raise RefusedError(
                "the box carries no Accept line; an LP box needs `  - Accept: %s`" % FORM
            )
        raise RefusedError("the box's Accept line `%s` is not a live-proof form (%s)" % (raw, FORM))
    try:
        machine = lt.machine_of_args(accept.args)
    except lt.RegistryError as exc:
        raise RefusedError(
            "the box's Accept line `live-proof %s %s %s` is not a form the recorder runs: %s"
            % (accept.target, accept.check, " ".join(accept.args), exc)
        ) from exc
    return accept.target, accept.check, machine


def resolve_plan(root: pathlib.Path, rel: str) -> str:
    """The plan's path relative to `root`, under agent/plans/ and outside `_done/`/`_removed/`. RefusedError otherwise."""
    p = pathlib.Path(rel)
    cands = [p] if p.is_absolute() else [root / p, root / PLANS_DIR / p]
    for c in cands:
        try:
            out = c.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
        if c.is_file():
            if not out.startswith(PLANS_DIR) or "/_" in out or not out.endswith(".md"):
                raise RefusedError("%s is not a live plan under %s" % (out, PLANS_DIR))
            return out
    raise RefusedError("unknown plan %r: no such file under %s" % (rel, root / PLANS_DIR))


def recorder_argv(
    rel: str, sig: str, target: str, check: str, machine: str | None, me: str, write: bool
) -> list[str]:
    argv = [sys.executable, "-m", "rediacc_ci.ops.live_proof", "record"]
    argv += ["--plan", rel, "--box", sig, "--target", target, "--check", check]
    if machine:
        argv += ["--machine", machine]
    argv += ["--by", me[:8]]
    if write:
        argv.append("--write")
    return argv


def run_recorder(argv: Sequence[str], root: pathlib.Path) -> tuple[int, str, str]:
    """(rc, stdout, stderr) of the recorder, run from `root` with `.ci` on PYTHONPATH. Output is captured so the row id can be read; the caller re-prints both streams."""
    env = dict(os.environ)
    ci = str(root / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        list(argv), cwd=str(root), env=env, capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


def find_row(root: pathlib.Path, row_id: str) -> dict[str, Any] | None:
    """The ledger row carrying `row_id`, or None."""
    try:
        text = (root / LEDGER_REL).read_text(encoding="utf-8")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("id") == row_id:
            return row
    return None


def evidence(row: dict[str, Any]) -> str:
    """The plan's evidence line: `live-proof <id> <target> <check> rc=0 v=<version>`."""
    check = (row.get("check") or {}).get("id")
    version = (row.get("deploy") or {}).get("version_id")
    return "live-proof %s %s %s rc=0 v=%s" % (row.get("id"), row.get("target"), check, version)


def tick_precheck(root: pathlib.Path, rel: str, sig: str, me: str) -> str | None:
    """The refusal text when `--plan-tick` would refuse for want of a live investigation row, checked BEFORE a live run is spent; None when the row is there."""
    row = R.investigation_for(root, rel, sig)
    if row is not None and not row.get("retro"):
        return None
    return (
        "--tick needs a live investigation row for box %s of %s before the receipt "
        "(PLAN-tested-on-bench section 5: investigate, then the receipt, then the tick). Record it:\n"
        "    worklist.py --plan-investigate %s %s %s <absent|present|partial> "
        "<kind>:<token> <kind>:<token> -- <note> --write" % (sig, rel, me[:8], rel, sig)
    )


def listing(root: pathlib.Path, plan_records: Any) -> str:
    out = [LIST_HEADER]
    n = 0
    for rel, _boxes in R.tickable(root, plan_records):
        try:
            text = (pathlib.Path(root) / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        mine = lp_boxes(text)
        if not mine:
            continue
        out.append("  %s" % rel)
        for i, _line, body, sig in mine:
            n += 1
            out.append("    %s  %s" % (sig, body[:88]))
            out.append("      Accept: %s" % (accept_raw(text, i) or "(none)"))
    out.append("  %d open live-proof box(es)." % n)
    return "\n".join(out)


def _say(text: str, err: bool = False) -> None:
    if text:
        stream = sys.stderr if err else sys.stdout
        stream.write(text if text.endswith("\n") else text + "\n")


def run(
    root: pathlib.Path,
    me: str,
    args: Sequence[str],
    *,
    tick: Callable[[str, str, str], int],
    recorder: Callable[[Sequence[str], pathlib.Path], tuple[int, str, str]] = run_recorder,
    precheck: Callable[[pathlib.Path, str, str, str], str | None] = tick_precheck,
    lt: Any = None,
) -> int:
    """One `--live-proof <me> <plan> <sig> [--write] [--tick]` run; the exit code. `tick(rel, sig, evidence)` returns the --plan-tick exit code."""
    try:
        return _run(root, me, args, tick, recorder, precheck, lt)
    except RefusedError as exc:
        _say("live-proof REFUSED: %s" % exc, err=True)
        return exc.rc


def _run(root, me, args, tick, recorder, precheck, lt) -> int:
    root = pathlib.Path(root)
    pos = [a for a in args if not a.startswith("--")]
    flags = [a for a in args if a.startswith("--")]
    bad = [f for f in flags if f not in ("--write", "--tick")]
    if bad or len(pos) != 2:
        raise RefusedError(
            ("unknown flag %r\n\n" % bad[0] if bad else "pass a plan and one box\n\n") + USAGE
        )
    write, do_tick = "--write" in flags, "--tick" in flags
    if do_tick and not write:
        raise RefusedError(
            "--tick needs --write: the tick cites a receipt row, and a dry run writes none"
        )
    rel = resolve_plan(root, pos[0])
    text = (root / rel).read_text(encoding="utf-8", errors="replace")
    if R.is_record(text):
        raise RefusedError("%s is a compacted record; revive it before recording a receipt" % rel)
    try:
        i, _line, _body, sig = R.select_box(lp_boxes(text), pos[1], kind="OPEN LP")
    except R.RecordError as exc:
        raise RefusedError("%r is not an open LP box of %s: %s" % (pos[1], rel, exc)) from exc
    target, check, machine = parse_accept(text, i, lt)
    if do_tick:
        why = precheck(root, rel, sig, me)
        if why:
            raise RefusedError(why)

    argv = recorder_argv(rel, sig, target, check, machine, me, write)
    rc, out, err = recorder(argv, root)
    _say(out)
    _say(err, err=True)
    if rc != 0:
        tail = "\n".join(ln for ln in err.splitlines() if ln.strip())[-1200:]
        raise RefusedError(
            "the recorder exited rc=%d for %s box %s (%s %s); the box stays open.\n%s"
            % (rc, rel, sig, target, check, tail or "(the recorder wrote nothing to stderr)"),
            rc,
        )
    if not write:
        _say(
            "dry run: rc=0 for %s box %s (%s %s), nothing written. Rerun with --write --tick "
            "to append the row and close the box." % (rel, sig, target, check)
        )
        return 0
    m = VERIFIED_RE.search(err) or VERIFIED_RE.search(out)
    row = find_row(root, m.group(1)) if m else None
    if (
        row is None
        or row.get("status") != "VERIFIED"
        or row.get("plan") != rel
        or row.get("box") != sig
    ):
        named = (
            "named row %s, which %s holds as no VERIFIED row of this box" % (m.group(1), LEDGER_REL)
            if m
            else "named no VERIFIED row"
        )
        raise RefusedError(
            "the recorder exited 0 for %s box %s but %s; the box stays open" % (rel, sig, named),
            1,
        )
    ev = evidence(row)
    _say("receipt %s appended to %s: %s" % (row["id"], LEDGER_REL, ev))
    if not do_tick:
        _say(
            "box %s is still open. Close it with:\n    worklist.py --plan-tick %s %s %s '%s' --write"
            % (sig, me[:8], rel, sig, ev)
        )
        return 0
    trc = tick(rel, sig, ev)
    if trc:
        raise RefusedError(
            "receipt %s is in %s but the tick was refused (rc=%d, above). Once the refusal is "
            "fixed:\n    worklist.py --plan-tick %s %s %s '%s' --write"
            % (row["id"], LEDGER_REL, trc, me[:8], rel, sig, ev),
            trc,
        )
    _say(
        "commit %s together with the plan and .ci/config/plan-boxes.json: the receipt and the "
        "tick land in one commit." % LEDGER_REL
    )
    return 0
