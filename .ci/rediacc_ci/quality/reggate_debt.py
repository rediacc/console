"""check:ci-reggate-debt -- a capped regression-gate demand is a debt, and CI fails while a due one stays unpaid.

WHY THIS EXISTS. The Stop hook's regression-gate cap (operator ruling 2026-09-05) turns the eighth and later gate demands on a branch into a `debt` record in `agent/reggate/<branch>.jsonl` instead of a block. The design had three more steps and none landed: the debt never came back as an item, nothing failed while it stayed unpaid, and the docs never named the exception. By 2026-11-16 103 debts sat in the ledgers with nothing forcing them back, so the cap was a permanent deferral (agent/plans/PLAN-reggate-debt-collection.md). The hook half now materializes and discharges; this is the CI half.

ONE FOLD, NO TWIN. The ledgers are folded with the Stop hook's own readers (`wl_reggate.ledger_paths`, `read_ledger_path`, `debt_entries`, `debt_due`, `paid_sigs`), so the gate and the hook cannot disagree about what a ledger says. `$WORKLIST_STORE_DIR` redirects the ledger directory exactly as it does for the hook, which is how the planted-debt proof reaches a scratch ledger without touching the tree.

FINDINGS:
  RD1  a due debt (wl_reggate.debt_due: not the live branch, or past REGGATE_DEBT_GRACE_MIN) with no `discharge` and no ASKED-stamped `retire`, not in the legacy baseline;
  RD2  more than REGGATE_MAX_DEBTS unpaid debts on one branch, outside the baseline;
  RD3  a `discharge` or `retire` whose sig has no `debt` in its ledger;
  RD4  a malformed ledger line, or a ledger that cannot be read;
  RD5  a debt whose `blind_spot` is under 12 characters: a debt that does not say what it is about cannot be paid by anyone;
  RD6  baseline drift: a baseline sig that is now paid or names no debt (a stale entry; remove it), or a sig added to the baseline since the merge-base;
  RD7  vacuity: zero debt ledgers parsed is CANNOT RUN, exit 77, never a pass.

THE LIVE BRANCH is `$GITHUB_HEAD_REF` on a pull request (the checkout there is a detached HEAD, which reads as no branch, so every live-branch debt would fall due before its grace) and the checkout's own branch otherwise.

THE LEGACY BASELINE (.ci/policy/reggate-debt-legacy.json) froze the debts that existed when this gate landed. It is shrink-only through RD6 and is emptied and deleted by the plan's last box.

CONTROL FIRST. Every run starts with the in-process selftest: each finding is planted in a scratch ledger directory and the run fails (exit 1) if any control stays silent, or if a clean ledger reports anything. `--selftest` runs only that.

Exit 0 clean, 1 on a finding or a silent control, 2 on an unknown argument, 77 when no ledger was parsed.

---- gate ----
step: Reggate debt
needs: none
lane: quality-branch
env-GITHUB_HEAD_REF: ${{ github.head_ref }}
env-GITHUB_BASE_REF: ${{ github.base_ref }}
---- end gate ----
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import paths

ROOT = pathlib.Path(__file__).resolve().parents[3]
paths.on_sys_path(paths.hooks_stop_dir(ROOT))

try:
    import wl_core as C
    import wl_reggate as RG
except ImportError as _exc:  # pragma: no cover -- a broken tree, reported rather than passed
    print(
        "x reggate debt: cannot import the Stop hook's ledger readers from %s (%s); this gate folds ledgers ONLY through them"
        % (paths.hooks_stop_dir(ROOT), _exc),
        file=sys.stderr,
    )
    sys.exit(1)

BLIND_SPOT_MIN = 12
CANNOT_RUN = 77


def live_branch(root):
    """`$GITHUB_HEAD_REF` when set (a pull request), else the checkout's branch."""
    return os.environ.get("GITHUB_HEAD_REF") or C.git_branch(root)


def read_legacy(root):
    """(sigs, problem). A missing file is an empty baseline; an unreadable one is a problem."""
    path = pathlib.Path(root) / RG.LEGACY_REL
    if not path.exists():
        return set(), ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return set(), "%s is unreadable: %s" % (RG.LEGACY_REL, exc)
    sigs = data.get("sigs") if isinstance(data, dict) else None
    if not isinstance(sigs, list) or not all(isinstance(s, str) for s in sigs):
        return set(), "%s carries no `sigs` list of strings" % RG.LEGACY_REL
    reason = data.get("reason") if isinstance(data, dict) else None
    if not (isinstance(reason, str) and reason.startswith("BLOCKER:")):
        return set(), "%s carries no `reason` starting `BLOCKER:`" % RG.LEGACY_REL
    return set(sigs), ""


def base_legacy(root):
    """The baseline's sigs at the merge-base with the base branch, or None when there is no usable base or the file did not exist there."""
    base = "origin/%s" % (os.environ.get("GITHUB_BASE_REF") or "main")
    try:
        mb = subprocess.run(
            ["git", "-C", str(root), "merge-base", "HEAD", base],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        if mb.returncode != 0 or not mb.stdout.strip():
            return None
        shown = subprocess.run(
            ["git", "-C", str(root), "show", "%s:%s" % (mb.stdout.strip(), RG.LEGACY_REL)],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if shown.returncode != 0:
        return None
    try:
        sigs = json.loads(shown.stdout).get("sigs")
    except (ValueError, AttributeError):
        return None
    return {s for s in sigs if isinstance(s, str)} if isinstance(sigs, list) else None


def findings(root, live, legacy, base=None, now=None):
    """(ledger_count, [(code, sig, text)]) over every ledger under wl_reggate.debt_dir(root)."""
    out = []
    ledgers = RG.ledger_paths(root)
    for path in ledgers:
        records, forgot = RG.read_ledger_path(path)
        if forgot:
            out.append(("RD4", "", "%s: a malformed line or an unreadable ledger" % path.name))
        debts = {r.get("sig") for r in records if r.get("kind") == "debt"}
        out.extend(
            ("RD3", str(r.get("sig") or ""), "%s: a %s with no debt" % (path.name, r["kind"]))
            for r in records
            if r.get("kind") in ("discharge", "retire") and r.get("sig") not in debts
        )
    entries = RG.debt_entries(root)
    known = {e["sig"] for e in entries}
    per_branch: dict[str, list[dict]] = {}
    for e in entries:
        if len(e["blind_spot"].strip()) < BLIND_SPOT_MIN:
            out.append(
                (
                    "RD5",
                    e["sig"],
                    "%s: blind_spot %r is under %d characters"
                    % (e["ledger"], e["blind_spot"], BLIND_SPOT_MIN),
                )
            )
        if e["paid"] or e["sig"] in legacy:
            continue
        per_branch.setdefault(e["br"], []).append(e["sig"])
        if RG.debt_due(e, live, now):
            out.append(
                (
                    "RD1",
                    e["sig"],
                    "%s: due since its branch is not the live one or its grace ran out (at %s), and unpaid: %s"
                    % (e["br"], e["at"], e["blind_spot"][:120]),
                )
            )
    for br, sigs in sorted(per_branch.items()):
        if len(sigs) > RG.REGGATE_MAX_DEBTS:
            out.append(
                (
                    "RD2",
                    "",
                    "%s: %d unpaid debts outside the baseline, above REGGATE_MAX_DEBTS=%d"
                    % (br, len(sigs), RG.REGGATE_MAX_DEBTS),
                )
            )
    paid = {e["sig"] for e in entries if e["paid"]}
    for sig in sorted(legacy):
        if sig in paid:
            out.append(
                ("RD6", sig, "baseline entry is paid now; remove it from %s" % RG.LEGACY_REL)
            )
        elif sig not in known:
            out.append(
                (
                    "RD6",
                    sig,
                    "baseline entry names no debt in any ledger; remove it from %s" % RG.LEGACY_REL,
                )
            )
    if base is not None:
        grew = "added to %s since the merge-base; the baseline only shrinks" % RG.LEGACY_REL
        out.extend(("RD6", sig, grew) for sig in sorted(legacy - base))
    return len(ledgers), out


@contextlib.contextmanager
def _scratch_ledgers():
    """A scratch ledger directory reached through WORKLIST_STORE_DIR, the same door the hook and the planted-debt proof use; the environment is restored after."""
    prev = os.environ.get("WORKLIST_STORE_DIR")
    with tempfile.TemporaryDirectory() as td:
        os.environ["WORKLIST_STORE_DIR"] = str(pathlib.Path(td) / "store")
        try:
            yield pathlib.Path(td)
        finally:
            if prev is None:
                os.environ.pop("WORKLIST_STORE_DIR", None)
            else:
                os.environ["WORKLIST_STORE_DIR"] = prev


def _write(td, branch, records):
    d = pathlib.Path(td) / "reggate"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ("%s.jsonl" % branch), "a", encoding="utf-8") as fh:
        fh.writelines((rec if isinstance(rec, str) else json.dumps(rec)) + "\n" for rec in records)


def selftest():
    """[failed control names]. Each RD is planted alone in a scratch ledger directory and must fire; a clean ledger must report nothing."""
    now = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=datetime.UTC)
    old = "2026-11-01T00:00:00Z"
    fresh = (now - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    spot = "a blind spot long enough to name its case"

    def debt(sig, br, at=old, blind=spot):
        return {"kind": "debt", "sig": sig, "br": br, "at": at, "blind_spot": blind}

    def run(plant, legacy=frozenset(), base=None):
        with _scratch_ledgers() as td:
            for branch, records in plant:
                _write(td, branch, records)
            return findings(td, "live", set(legacy), base, now)

    failed = []

    def expect(name, result, code, sig=None):
        hits = [f for f in result[1] if f[0] == code and (sig is None or f[1] == sig)]
        if not hits:
            failed.append("CONTROL %s did not fire: %s" % (code, name))

    clean = run(
        [
            (
                "old",
                [
                    debt("paid1", "old"),
                    {"kind": "discharge", "sig": "paid1", "artifact": "a", "proof": "p"},
                ],
            ),
            ("live", [debt("fresh1", "live", at=fresh)]),
        ]
    )
    if clean[1]:
        failed.append("CONTROL clean: a paid debt and a fresh live one reported %r" % (clean[1],))
    expect(
        "an unpaid debt on a landed branch", run([("old", [debt("due1", "old")])]), "RD1", "due1"
    )
    expect("an unpaid live debt past grace", run([("live", [debt("due2", "live")])]), "RD1", "due2")
    unstamped = [debt("due3", "old"), {"kind": "retire", "sig": "due3", "reason": "no stamp"}]
    expect("a retire with no ASKED stamp pays nothing", run([("old", unstamped)]), "RD1", "due3")
    six = [debt("m%d" % i, "live", at=fresh) for i in range(RG.REGGATE_MAX_DEBTS + 1)]
    expect("too many unpaid debts on one branch", run([("live", six)]), "RD2")
    orphan = [
        debt("x1", "old"),
        {"kind": "discharge", "sig": "nodebt", "artifact": "a", "proof": "p"},
    ]
    expect("a discharge with no debt", run([("old", orphan)], legacy={"x1"}), "RD3", "nodebt")
    expect(
        "a malformed ledger line",
        run([("old", [debt("x2", "old"), "{not json"])], legacy={"x2"}),
        "RD4",
    )
    expect(
        "a short blind spot",
        run([("old", [debt("x3", "old", blind="todo")])], legacy={"x3"}),
        "RD5",
        "x3",
    )
    paid_legacy = [
        debt("x4", "old"),
        {"kind": "discharge", "sig": "x4", "artifact": "a", "proof": "p"},
    ]
    expect("a paid baseline entry", run([("old", paid_legacy)], legacy={"x4"}), "RD6", "x4")
    expect(
        "a baseline entry with no debt",
        run([("old", [debt("x5", "old")])], legacy={"x5", "ghost"}),
        "RD6",
        "ghost",
    )
    expect(
        "a baseline sig added since the merge-base",
        run([("old", [debt("x6", "old")])], legacy={"x6"}, base=set()),
        "RD6",
        "x6",
    )
    if run([])[0] != 0:
        failed.append("CONTROL RD7: an empty ledger directory parsed a ledger")
    # A legacy sig is exempt from RD1, which is what the baseline is for; without this control a baseline that exempted nothing would still pass every plant above.
    if any(f[0] == "RD1" for f in run([("old", [debt("x7", "old")])], legacy={"x7"})[1]):
        failed.append("CONTROL baseline: a legacy sig was still reported RD1")
    return failed


def main(argv):
    failed = selftest()
    if failed:
        for name in failed:
            print("x %s" % name, file=sys.stderr)
        print(
            "x reggate debt: a control stayed silent; refusing to report a verdict", file=sys.stderr
        )
        return 1
    print("reggate debt: controls first, then the verdict (RD1-RD7 each fired on a plant)")
    if "--selftest" in argv:
        return 0
    legacy, problem = read_legacy(ROOT)
    if problem:
        print("x reggate debt: %s" % problem, file=sys.stderr)
        return 1
    base = base_legacy(ROOT)
    live = live_branch(ROOT)
    count, found = findings(ROOT, live, legacy, base)
    if count == 0:
        print(
            "! CANNOT RUN (exit 77, which is not a verdict): RD7 no debt ledger under %s"
            % RG.debt_dir(ROOT),
            file=sys.stderr,
        )
        return CANNOT_RUN
    if base is None:
        print(
            "  RD6 growth check skipped: no merge-base copy of %s to compare against"
            % RG.LEGACY_REL
        )
    if found:
        print("x reggate debt: %d finding(s)" % len(found), file=sys.stderr)
        for code, sig, text in found:
            print("  %s %s %s" % (code, sig or "-", text), file=sys.stderr)
        print(
            "  Pay a debt with its named artifact (the Stop hook discharges it), or retire it with "
            "`worklist.py --reggate-retire <me> <sig8> ASKED:<YYYY-MM-DDTHH:MM>Z <reason>` on an operator answer.",
            file=sys.stderr,
        )
        return 1
    entries = RG.debt_entries(ROOT)
    print(
        "v reggate debt: %d ledger(s), %d debt(s), %d paid, %d in the legacy baseline, live branch %s"
        % (count, len(entries), sum(1 for e in entries if e["paid"]), len(legacy), live or "(none)")
    )
    return 0


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse("reggate_debt.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(main(sys.argv[1:]))
