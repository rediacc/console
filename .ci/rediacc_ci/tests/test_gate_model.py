"""`rediacc_ci.ci.gate_model` (PLAN-gate-scheduling-learned T4, T5, T9) on synthetic ledgers.

Each rule is shown firing AND shown not firing: the same sequence with the rule switched off (`Rules`) or with its evidence removed lands in another class. Gate ids here are fixture names (`x:a`), so nothing in this file depends on the real lock except the T9 scan, which reads it on purpose.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import stat
import sys
from typing import Any

from rediacc_ci import gitx, paths
from rediacc_ci.ci import gate_ledger as L
from rediacc_ci.ci import gate_model as M

DAY = 86400.0
T0 = L.epoch("2026-10-01T12:00:00Z") or 0.0
NOW = T0 + 10 * DAY
GLOBALS = ["**/package-lock.json"]
LOCK: list[dict[str, Any]] = [
    {
        "id": "x:a",
        "gate": True,
        "leaves": [],
        "paths": ["pkg/a/**"],
        "ci": {"kind": "step", "job": "j", "step": "A"},
    },
    {
        "id": "x:b",
        "gate": True,
        "leaves": [],
        "paths": ["pkg/a/**"],
        "ci": {"kind": "step", "job": "j", "step": "B"},
    },
    {
        "id": "x:c",
        "gate": True,
        "leaves": [],
        "needs": ["x:d"],
        "ci": {"kind": "step", "job": "j", "step": "S"},
    },
    {"id": "x:d", "gate": True, "leaves": [], "ci": {"kind": "step", "job": "j", "step": "S"}},
    {"id": "x:e", "gate": True, "leaves": [], "ci": {"kind": "local-only"}},
]


class Ledger:
    """A synthetic ledger: one run per `step`, each gate given (outcome, key)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.n = 0

    def run(
        self,
        at: float,
        gates: dict[str, tuple[str, str | None]],
        *,
        changed: list[str] | None = None,
        findings: dict[str, list[str]] | None = None,
        src: str = "quick",
        ci: dict[str, Any] | None = None,
        tree: str | None = None,
        branch: str = "b1",
    ) -> str:
        self.n += 1
        rid = "r%03d" % self.n
        self.rows.append(
            {
                "t": "run",
                "v": 1,
                "id": rid,
                "src": src,
                "at": L.iso(at),
                "branch": branch,
                "head": "h" + rid,
                "tree": tree or "T" + rid,
                "salt": "s",
                "clean": True,
                "whole": True,
                "base_tree": "prev" if changed is not None else None,
                "changed": changed or [],
                "changed_n": len(changed or []),
                "root": "/r",
                "ci": ci,
            }
        )
        for gid, (outcome, key) in gates.items():
            self.rows.append(
                {
                    "t": "g",
                    "v": 1,
                    "run": rid,
                    "gate": gid,
                    "outcome": outcome,
                    "wall_ms": 1000,
                    "t0_ms": 0,
                    "key": key or "T" + rid,
                    "key_kind": "tree" if key is None else "paths",
                    "findings": (findings or {}).get(gid),
                    "attr": "own",
                }
            )
        self.rows.append({"t": "end", "v": 1, "run": rid, "wall_ms": 1, "exit": 0, "cut": False})
        return rid

    def build(
        self, rules: M.Rules | None = None, lock: list[dict[str, Any]] | None = None
    ) -> M.Built:
        return M.build(
            self.rows, lock or LOCK, paths.repo_root(), now=NOW, rules=rules, globals_=GLOBALS
        )


def cls(b: M.Built, gid: str) -> str:
    return str(b.model["gates"][gid]["class"])


# ---------------------------------------------------------------------------- path classes


def test_path_class_is_the_longest_anchor() -> None:
    lock = [
        {"id": "x", "paths": [".ci/**", ".ci/rediacc_ci/ci/**", "pyproject.toml"], "leaves": []}
    ]
    anchors = M.anchors(lock, paths.repo_root(), ["**/uv.lock"])
    assert M.path_class(".ci/rediacc_ci/ci/gate_model.py", anchors) == ".ci/rediacc_ci/ci/**"
    assert M.path_class(".ci/config/x.json", anchors) == ".ci/**"
    assert M.path_class("pyproject.toml", anchors) == "pyproject.toml"
    assert M.path_class("deep/a/uv.lock", anchors) == "**/uv.lock"
    assert M.path_class("packages/www/src/x.ts", anchors) == "~packages/www"


def test_global_inputs_are_parsed_from_the_runner() -> None:
    found = M.global_inputs(paths.repo_root())
    assert "pyproject.toml" in found
    assert len(found) >= 3


# ---------------------------------------------------------------------------- classification


def test_strong_key_makes_a_clock_and_its_control_makes_it_real() -> None:
    lg = Ledger()
    lg.run(T0, {"x:a": ("pass", "K1")})
    lg.run(T0 + 3600, {"x:a": ("fail", "K1")})
    lg.run(T0 + 7200, {"x:a": ("pass", "K2")})
    assert cls(lg.build(), "x:a") == "clock"
    assert cls(lg.build(M.Rules(strong_key=False)), "x:a") == "real"


def _midnight_onsets(lg: Ledger, n: int) -> None:
    for day in range(n):
        mid = T0 + (day + 1) * DAY - 12 * 3600  # T0 is noon, so this is midnight UTC
        lg.run(mid - 1800, {"x:a": ("pass", None)})
        lg.run(mid + 60, {"x:a": ("fail", None)})
        lg.run(mid + 3600, {"x:a": ("pass", None)})


def test_utc_boundary_makes_a_clock_and_its_controls_make_it_real() -> None:
    lg = Ledger()
    _midnight_onsets(lg, 2)
    assert cls(lg.build(), "x:a") == "clock"
    assert cls(lg.build(M.Rules(utc_boundary=False)), "x:a") == "real"
    one = Ledger()
    _midnight_onsets(one, 1)
    assert cls(one.build(), "x:a") == "real", "one onset cannot separate a clock from a coincidence"


def test_flaky_precedes_clock() -> None:
    lg = Ledger()
    lg.run(T0, {"x:a": ("pass", "K1")})
    lg.run(T0 + 60, {"x:a": ("fail", "K1")})
    lg.run(T0 + 120, {"x:a": ("pass", "K1")})
    assert cls(lg.build(), "x:a") == "flaky"
    ctrl = Ledger()
    ctrl.run(T0, {"x:a": ("pass", "K1")})
    ctrl.run(T0 + 60, {"x:a": ("fail", "K2")})
    ctrl.run(T0 + 120, {"x:a": ("pass", "K3")})
    assert cls(ctrl.build(), "x:a") == "real"


def test_weak_when_the_key_is_equal_and_the_tree_is_not() -> None:
    lg = Ledger()
    lg.run(T0, {"x:a": ("pass", "K1")})
    lg.run(T0 + 60, {"x:a": ("fail", "K1")})
    lg.run(T0 + 120, {"x:a": ("pass", "K2")})
    ep = next(e for e in lg.build().episodes if e.subject == "x:a")
    assert ep.cls == "clock"
    assert ep.weak
    same = Ledger()
    same.run(T0, {"x:a": ("pass", "K1")}, tree="T")
    same.run(T0 + 60, {"x:a": ("fail", "K1")}, tree="T")
    same.run(T0 + 120, {"x:a": ("pass", "K2")})
    assert not next(e for e in same.build().episodes if e.subject == "x:a").weak


def test_chronic_descends_to_findings() -> None:
    lg = Ledger()
    lg.run(T0, {"x:a": ("fail", None)}, findings={"x:a": ["k:always"]})
    lg.run(T0 + 60, {"x:a": ("fail", None)}, findings={"x:a": ["k:always", "k:once"]})
    lg.run(T0 + 120, {"x:a": ("fail", None)}, findings={"x:a": ["k:always"]})
    b = lg.build()
    assert cls(b, "x:a") == "chronic"
    assert b.model["gates"]["x:a"]["findings"] == {"k:always": "chronic", "k:once": "real"}
    assert any(t.startswith("[gate-model:chronic:x:a]") for t, _k, _x in b.items)


def test_infra_is_excluded_and_its_control_counts() -> None:
    def world(category: str) -> M.Built:
        lg = Ledger()
        for i in range(3):
            lg.run(
                NOW - 3600 + i * 60,
                {"x:a": ("fail" if i == 1 else "pass", None)},
                src="ci-step",
                ci={"run": i, "attempt": 1, "job": "J", "category": category},
            )
        return lg.build()

    infra = world("infra-likely")
    assert cls(infra, "x:a") == "none"
    assert infra.model["gates"]["x:a"]["obs"] == 2
    assert any(t.startswith("[gate-model:infra:infra-likely:J]") for t, _k, _x in infra.items)
    assert cls(world("code-likely"), "x:a") == "real"


def test_ci_legs_of_one_run_are_one_observation() -> None:
    """Leg 1 green and leg 2 red at one commit would otherwise read as green again at the same key: flaky."""
    lg = Ledger()
    lg.run(
        T0, {"x:a": ("pass", "C1")}, src="ci-step", ci={"run": 1, "attempt": 1, "job": "J (1/2)"}
    )
    lg.run(
        T0 + 60,
        {"x:a": ("pass", "C2")},
        src="ci-step",
        ci={"run": 2, "attempt": 1, "job": "J (1/2)"},
    )
    lg.run(
        T0 + 61,
        {"x:a": ("fail", "C2")},
        src="ci-step",
        ci={"run": 2, "attempt": 1, "job": "J (2/2)"},
    )
    lg.run(
        T0 + 120,
        {"x:a": ("pass", "C3")},
        src="ci-step",
        ci={"run": 3, "attempt": 1, "job": "J (1/2)"},
    )
    assert cls(lg.build(), "x:a") == "real"
    ledger = M.fold_rows(lg.rows)
    assert sum(1 for o in ledger.obs if o.gate == "x:a") == 3
    assert len(M.merge_legs(list(ledger.obs), ledger.runs)) == 3
    assert lg.build().model["runs"] == 3, "four job rows are three CI attempts"


def test_probes_decide_between_clock_and_real(tmp_path: pathlib.Path) -> None:
    lg = Ledger()
    lg.run(NOW - 3 * 3600, {"x:a": ("pass", None)})
    lg.run(NOW - 2 * 3600, {"x:a": ("fail", None)})
    lg.run(NOW - 1 * 3600, {"x:a": ("pass", None)})
    b = lg.build()
    assert cls(b, "x:a") == "real"

    def world(green_head: str, control: str) -> M.Built:
        led = tmp_path / ("%s-%s" % (green_head, control))
        L.append_rows(led, lg.rows, now=NOW)
        heads = {r["head"]: r for r in lg.rows if r["t"] == "run"}
        ordered = sorted(heads)
        green, ctrl = ordered[0], ordered[2]

        def runner(_gate: str, head: str, _t: float) -> str:
            return green_head if head == green else control if head == ctrl else "unknown"

        counts = M.run_probes(
            led, b, {r["id"]: r for r in lg.rows if r["t"] == "run"}, runner, now=NOW
        )
        assert counts["probed"] == 1
        return M.build(L.read_rows(led)[0], LOCK, paths.repo_root(), now=NOW, globals_=GLOBALS)

    assert cls(world("pass", "pass"), "x:a") == "real"
    assert cls(world("fail", "pass"), "x:a") == "clock"
    assert cls(world("fail", "fail"), "x:a") == "real", (
        "a red probe in an environment that cannot go green proves nothing"
    )


# ---------------------------------------------------------------------------- relationships


def _co_onsets(lg: Ledger, times: int, gates: tuple[str, ...] = ("x:a", "x:e")) -> None:
    for i in range(times):
        base = T0 + i * 3600
        lg.run(base, dict.fromkeys(gates, ("pass", None)), changed=["pkg/a/x.py"])
        lg.run(base + 60, dict.fromkeys(gates, ("fail", None)), changed=["pkg/a/y.py"])
        lg.run(base + 120, dict.fromkeys(gates, ("pass", None)), changed=["docs/z.md"])
    for i in range(20):
        lg.run(T0 + 5 * DAY + i * 60, dict.fromkeys(gates, ("pass", None)), changed=["docs/q.md"])


def test_co_failure_edge_needs_min_support() -> None:
    lg = Ledger()
    _co_onsets(lg, M.MIN_SUPPORT)
    b = lg.build()
    assert any(e["origin"] == "co-failure" and {e["a"], e["b"]} == {"x:a", "x:e"} for e in b.edges)
    assert ["x:a", "x:b", "x:e"] in b.model["clusters"]
    ctrl = Ledger()
    _co_onsets(ctrl, M.MIN_SUPPORT - 1)
    assert not any(e["origin"] == "co-failure" for e in ctrl.build().edges)


def test_structural_edges_record_their_origin() -> None:
    edges = M.structural_edges(LOCK, paths.repo_root())
    origins = {(e["a"], e["b"], e["origin"]) for e in edges}
    assert ("x:a", "x:b", "paths") in origins
    assert ("x:c", "x:d", "needs") in origins
    assert ("x:c", "x:d", "step") in origins


def test_associations_follow_the_diff_class() -> None:
    lg = Ledger()
    _co_onsets(lg, 3)
    assoc = lg.build().model["associations"]
    assert "x:e" in assoc.get("pkg/a/**", {})
    assert "docs/z.md" not in json.dumps(assoc)


def test_paths_gap_opens_when_an_associated_class_is_undeclared() -> None:
    lg = Ledger()
    for i in range(M.MIN_SUPPORT):
        base = T0 + i * 3600
        lg.run(base, {"x:a": ("pass", "K%d" % i)}, changed=["docs/x.md"])
        lg.run(base + 60, {"x:a": ("fail", "L%d" % i)}, changed=["other/thing/y.py"])
        lg.run(base + 120, {"x:a": ("pass", "M%d" % i)}, changed=["docs/z.md"])
    for i in range(20):
        lg.run(T0 + 5 * DAY + i * 60, {"x:a": ("pass", "N%d" % i)}, changed=["docs/q.md"])
    toks = [t for t, _k, _x in lg.build().items]
    assert "[gate-model:paths-gap:x:a:~other/thing]" in toks


def test_companions_are_candidates_then_reliable() -> None:
    def world(times: int) -> M.Built:
        lg = Ledger()
        for i in range(times):
            base = T0 + i * 3600
            lg.run(base, {"x:a": ("fail", None), "x:b": ("pass", None)})
            lg.run(base + 60, {"x:a": ("pass", None), "x:b": ("fail", None)})
            lg.run(base + 120, {"x:a": ("pass", None), "x:b": ("pass", None)})
        return lg.build()

    one = world(1).model["companions"]
    assert {"from": "x:a", "to": "x:b", "support": 1, "reliable": False} in one
    two = world(M.COMPANION_MIN_SUPPORT)
    assert {"from": "x:a", "to": "x:b", "support": 2, "reliable": True} in two.model["companions"]
    assert any(t == "[gate-model:companion:x:a->x:b]" for t, _k, _x in two.items)


# ---------------------------------------------------------------------------- the contract


def test_model_json_v1_contract_exactly() -> None:
    lg = Ledger()
    _co_onsets(lg, 1)
    m = lg.build().model
    assert set(m) == {
        "v",
        "built_at",
        "cold_start",
        "runs",
        "gates",
        "clock_set",
        "clusters",
        "associations",
        "companions",
    }
    assert m["v"] == 1
    assert set(m["cold_start"]) == {"on", "reason"}
    for g in m["gates"].values():
        assert set(g) == {"obs", "p_red", "p_red_by_class", "wall_ms", "class", "findings"}
        assert g["class"] in M.CLASSES
        assert 0.0 <= g["p_red"] <= 1.0
    for c in m["companions"]:
        assert set(c) == {"from", "to", "support", "reliable"}
    json.dumps(m)


def test_cold_start_until_enough_whole_runs() -> None:
    lg = Ledger()
    for i in range(M.MIN_LEDGER_RUNS - 1):
        lg.run(T0 + i, {g["id"]: ("pass", None) for g in LOCK})
    assert lg.build().model["cold_start"]["on"]
    for i in range(M.MIN_GATE_OBS):
        lg.run(T0 + 100 + i, {g["id"]: ("pass", None) for g in LOCK})
    cold = lg.build().model["cold_start"]
    assert not cold["on"], cold


# ---------------------------------------------------------------------------- refresh and items


def _fake_worklist(tmp: pathlib.Path) -> list[str]:
    """A worklist CLI double: `--add` prints `Added #<id>:`, `--list --open` lists every added id, every call is logged."""
    script = tmp / "fakewl.py"
    script.write_text(
        "import json, sys, pathlib, hashlib\n"
        "st = pathlib.Path(%r)\n"
        "items = json.loads(st.read_text()) if st.exists() else {}\n"
        "a = sys.argv[1:]\n"
        "with open(%r, 'a') as log: log.write(json.dumps(a) + '\\n')\n"
        "if a[0] == '--add':\n"
        "    i = hashlib.sha1(a[2].encode()).hexdigest()[:8]; items[i] = a[2]; st.write_text(json.dumps(items)); print('Added #%%s: %%s' %% (i, a[2]))\n"
        "elif a[0] == '--update':\n"
        "    items[a[2]] = a[3]; st.write_text(json.dumps(items))\n"
        "elif a[0] == '--list':\n"
        "    print('\\n'.join('  - [ ] #%%s %%s' %% kv for kv in items.items()))\n"
        % (str(tmp / "state.json"), str(tmp / "calls.jsonl"))
    )
    return [sys.executable, str(script)]


def _calls(tmp: pathlib.Path) -> list[list[str]]:
    return [json.loads(ln) for ln in (tmp / "calls.jsonl").read_text().splitlines()]


def test_sync_items_adds_once_then_refreshes(tmp_path: pathlib.Path) -> None:
    cmd = _fake_worklist(tmp_path)
    items = [("[gate-model:chronic:x:a]", "chronic", "[gate-model:chronic:x:a] text one")]
    d = tmp_path / "ledger"
    assert M.sync_items(d, items, owner="deadbeef", worklist_cmd=cmd, cwd=tmp_path)["added"] == 1
    assert M.sync_items(d, items, owner="deadbeef", worklist_cmd=cmd, cwd=tmp_path) == {
        "added": 0,
        "updated": 1,
        "raced": 0,
        "failed": 0,
    }
    verbs = [c[0] for c in _calls(tmp_path)]
    assert verbs.count("--add") == 1
    assert verbs.count("--update") == 1


def test_sync_items_respects_a_concurrent_claim(tmp_path: pathlib.Path) -> None:
    cmd = _fake_worklist(tmp_path)
    tok = "[gate-model:chronic:x:a]"
    d = tmp_path / "ledger"
    claims = d / "claims"
    claims.mkdir(parents=True)
    (claims / (L.sha(tok)[:20] + ".claim")).write_text("{}")
    assert (
        M.sync_items(
            d, [(tok, "chronic", tok + " t")], owner="deadbeef", worklist_cmd=cmd, cwd=tmp_path
        )["raced"]
        == 1
    )
    assert not any(c[0] == "--add" for c in _calls(tmp_path))


def test_sync_items_against_the_real_worklist_in_a_temp_store(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert gitx.git(["init", "-q", str(repo)]).returncode == 0
    env = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "WORKLIST_SESSION_ID": "deadbeef-1111-2222-3333-444444444444",
        "WORKLIST_STORE_DIR": str(tmp_path / "store"),
        "TMPDIR": str(tmp_path / "tmp"),
    }
    (tmp_path / "tmp").mkdir()
    cmd = [sys.executable, str(paths.repo_root().joinpath(*M.WORKLIST_REL))]
    items = [
        (
            "[gate-model:clock-set:clock-set]",
            "clock-set",
            "[gate-model:clock-set:clock-set] clock-driven gates: x:a",
        )
    ]
    d = tmp_path / "ledger"
    assert (
        M.sync_items(d, items, owner="deadbeef", worklist_cmd=cmd, cwd=repo, env=env)["added"] == 1
    )
    assert (
        M.sync_items(d, items, owner="deadbeef", worklist_cmd=cmd, cwd=repo, env=env)["updated"]
        == 1
    )
    store = (tmp_path / "store" / "deadbeef.jsonl").read_text()
    assert store.count("[gate-model:clock-set:clock-set]") >= 2
    assert sum(1 for ln in store.splitlines() if '"add"' in ln or '"op":"add"' in ln) <= 1


def test_refresh_honours_the_ttl_and_refuses_an_empty_ledger(tmp_path: pathlib.Path) -> None:
    root = paths.repo_root()
    empty = tmp_path / "empty"
    assert M.refresh(empty, root, ci=False, probe=False, backfill=False, now=NOW) == 1
    lg = Ledger()
    _co_onsets(lg, 1)
    d = tmp_path / "ledger"
    L.append_rows(d, lg.rows, now=NOW)
    out: list[str] = []
    assert M.refresh(d, root, ci=False, probe=False, backfill=False, now=NOW, out=out.append) == 0
    model = json.loads((d / "model.json").read_text())
    assert model["runs"] == lg.n
    assert (d / "reports" / "2026-10-11.md").is_file()
    assert "worklist: NOT written" in (d / "reports" / "2026-10-11.md").read_text()
    assert (
        M.refresh(d, root, ci=False, probe=False, backfill=False, now=NOW + 3600, out=out.append)
        == 0
    )
    assert "nothing to do" in out[-1]
    assert (
        M.refresh(
            d,
            root,
            ci=False,
            probe=False,
            backfill=False,
            now=NOW + M.MODEL_TTL_H * 3600 + 1,
            out=out.append,
        )
        == 0
    )
    assert "nothing to do" not in out[-1]


# ---------------------------------------------------------------------------- T9: no gate id in the source


# The model and ledger here, plus the runner's ranking and ledger writer (W2's, `scripts/ci-runner/`) once they exist: the plan's T9 covers all four.
SOURCES = (
    pathlib.Path(M.__file__).parent / "gate_model.py",
    pathlib.Path(M.__file__).parent / "gate_ledger.py",
    paths.repo_root() / "scripts" / "ci-runner" / "rank.ts",
    paths.repo_root() / "scripts" / "ci-runner" / "ledger.ts",
)


def gate_ids_in(text: str, ids: list[str]) -> list[str]:
    """Every lock id appearing in `text` as a whole token (not as the prefix of a longer id).

    An id with no `:` or `-` is an ordinary English word (`pins`), so prose using the word is not a mention of the gate; such an id counts only when it is quoted, which is how code names one.
    """
    found = []
    for i in ids:
        if re.fullmatch(r"\w+", i):
            pattern = r"""(["'`])%s\1""" % re.escape(i)
        else:
            pattern = r"(?<![\w:-])%s(?![\w:-])" % re.escape(i)
        if re.search(pattern, text):
            found.append(i)
    return found


def _ids() -> list[str]:
    lock = json.loads((paths.repo_root() / L.LOCK_REL).read_text(encoding="utf-8"))
    return [str(e["id"]) for e in lock]


def test_t9_no_gate_id_in_the_scheduler_model_or_ledger() -> None:
    ids = _ids()
    assert len(ids) > 100, "the lock was not read; the scan would pass on nothing"
    scanned = [p for p in SOURCES if p.is_file()]
    assert scanned[:2] == list(SOURCES[:2]), "the model and ledger sources must exist to be scanned"
    for p in scanned:
        assert gate_ids_in(p.read_text(encoding="utf-8"), ids) == [], (
            "%s names gate ids; derive them from the ledger or the lock" % p
        )


def test_t9_control_a_planted_id_is_found(tmp_path: pathlib.Path) -> None:
    ids = _ids()
    planted = tmp_path / "gate_model.py"
    src = (pathlib.Path(M.__file__)).read_text(encoding="utf-8")
    planted.write_text(src + "\nPINNED = %r\n" % ids[len(ids) // 2], encoding="utf-8")
    planted.chmod(planted.stat().st_mode | stat.S_IRUSR)
    assert gate_ids_in(planted.read_text(encoding="utf-8"), ids) == [ids[len(ids) // 2]]


def test_t9_a_bare_word_id_is_found_quoted_and_ignored_in_prose() -> None:
    ids = _ids()
    assert "pins" in ids, "the bare-word id this control is about left the lock"
    assert gate_ids_in("the safety search pins the gate whose start moved", ids) == []
    assert gate_ids_in("const g = 'pins';", ids) == ["pins"]
